"""Build and deterministically classify exceptions (docs/15 §3).

M1 classifier — a fixed set of built-in predicates covering the documented
taxonomy. M2 swaps these for the spec's safe-AST `rules:` engine.

An exception is opened for:
  - a settlement_utr group whose decomposition residual exceeds the rounding
    tolerance (or whose bank credit is missing / duplicated / orphaned)
  - a processor payment with no ledger order, or vice versa
  - any record carrying an injection-shaped untrusted field
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from arbiter_engine.decompose.identity import expected_net_minor
from arbiter_engine.exceptions.context import build_context
from arbiter_engine.exceptions.injection import injection_signal
from arbiter_engine.exceptions.rules import RuleEngine
from arbiter_engine.models import Decomposition, Match, MatchCandidate, ReconException, Record
from arbiter_engine.specs.model import ReconSpec


@dataclass
class _Ctx:
    run_id: str
    rounding_minor: int
    period_start: str
    period_end: str
    engine: RuleEngine | None = None
    all_records: list[Record] = field(default_factory=list)


def _eid(run_id: str, *parts: str) -> str:
    return "exc_" + hashlib.sha256(f"{run_id}|{'|'.join(parts)}".encode()).hexdigest()[:12]


def _period(spec: ReconSpec) -> tuple[str, str]:
    p = (spec.identity or {}).get("period")
    if isinstance(p, list) and len(p) == 2:
        return str(p[0]), str(p[1])
    return "0000-01-01", "9999-12-31"


def build_exceptions(
    run_id: str,
    records: list[Record],
    matches: list[Match],
    decompositions: list[Decomposition],
    spec: ReconSpec,
    *,
    candidates: dict[str, list[MatchCandidate]] | None = None,
    prior_batches: list[Any] | None = None,
) -> list[ReconException]:
    from arbiter_engine.match.cross_period import match_carry_forward

    priors = prior_batches or []
    rounding = int((spec.identity or {}).get("rounding_tolerance_minor", 100))
    p_start, p_end = _period(spec)
    try:
        engine: RuleEngine | None = RuleEngine(spec.rules) if spec.rules else None
    except Exception:  # noqa: BLE001 - a bad spec rule must not crash a run
        engine = None
    ctx = _Ctx(run_id, rounding, p_start, p_end, engine=engine, all_records=list(records))
    cand_map = candidates or {}

    by_id = {r.id: r for r in records}
    matched_ids = {rid for m in matches for rid in m.all_ids}
    processor = sorted((r for r in records if r.source == "razorpay_recon"), key=lambda r: r.id)
    bank = sorted((r for r in records if r.source == "bank"), key=lambda r: r.id)
    ledger_orders = {r.external_ids.get("order_id", r.id) for r in records if r.source == "ledger"}

    out: list[ReconException] = []
    seen: set[str] = set()

    # 1. security scan — highest priority, bypasses everything else
    for r in processor + bank:
        sig = injection_signal(*r.untrusted.values())
        if sig:
            eid = _eid(run_id, "sec", r.id)
            if eid in seen:
                continue
            seen.add(eid)
            out.append(
                ReconException(
                    id=eid,
                    run_id=run_id,
                    record_ids=[r.id],
                    category="SECURITY_REVIEW",
                    classified_by="rule:r_security_scan",
                    amount_impact_minor=abs(r.amount_minor),
                    confidence=1.0,
                    status="security_review",
                )
            )

    # 2. group-level: decomposition residual / missing / orphan / duplicate
    proc_blocks: dict[str, list[Record]] = {}
    for r in processor:
        utr = r.external_ids.get("settlement_utr")
        if utr:
            proc_blocks.setdefault(utr, []).append(r)
    bank_utrs = {b.external_ids.get("utr") for b in bank if b.external_ids.get("utr")}
    matched_utrs = {m.id.removeprefix("m_") for m in matches}

    for utr in sorted(proc_blocks):
        items = sorted(proc_blocks[utr], key=lambda r: r.id)
        grp_decomp = next((d for d in decompositions if d.settlement_utr == utr), None)

        if utr in matched_utrs:
            # matched, but a component may still be off
            if grp_decomp and abs(grp_decomp.residual_minor) > rounding:
                out.append(_classify_residual(ctx, utr, items, grp_decomp))
            elif grp_decomp and not grp_decomp.ledger_crosscheck_ok:
                out.append(
                    ReconException(
                        id=_eid(run_id, "partial", utr),
                        run_id=run_id,
                        record_ids=[it.id for it in items],
                        category="PARTIAL_PAYMENT",
                        classified_by="unclassified",
                        amount_impact_minor=grp_decomp.residual_minor or -1,
                        confidence=None,
                        status="open",
                    )
                )
            cb = [
                it for it in items if it.external_ids.get("dispute_id") or it.kind == "chargeback"
            ]
            if cb:
                out.append(
                    ReconException(
                        id=_eid(run_id, "cb", utr),
                        run_id=run_id,
                        record_ids=[it.id for it in cb],
                        category="CHARGEBACK",
                        classified_by="rule:r_chargeback",
                        amount_impact_minor=sum(abs(it.amount_minor) for it in cb),
                        confidence=0.85,
                        status="open",
                    )
                )
            continue
        expected = expected_net_minor(items)
        # duplicate payment inside the block?
        pay_ids = [it.external_ids.get("payment_id") for it in items if it.kind == "payment"]
        if len(pay_ids) != len(set(pay_ids)):
            out.append(
                ReconException(
                    id=_eid(run_id, "dup", utr),
                    run_id=run_id,
                    record_ids=[it.id for it in items],
                    category="DUPLICATE",
                    classified_by="rule:r_duplicate_payment",
                    amount_impact_minor=abs(expected),
                    confidence=0.9,
                    status="open",
                )
            )
            continue
        if utr not in bank_utrs:
            # settled by the processor but no bank credit in this statement:
            # if it settles after the period end it's a timing item; else the money
            # went to another account.
            settled = max((it.settled_at for it in items if it.settled_at), default=None)
            after_period = settled is not None and settled.isoformat() > ctx.period_end
            near_start = settled is not None and settled.day <= 3
            if after_period or near_start:
                cat, rule = "TIMING", "rule:r_timing_period_boundary"
            else:
                cat, rule = "WRONG_ACCOUNT", "rule:r_wrong_account"
            out.append(
                ReconException(
                    id=_eid(run_id, "nobank", utr),
                    run_id=run_id,
                    record_ids=[it.id for it in items],
                    category=cat,
                    classified_by=rule,
                    amount_impact_minor=abs(expected),
                    confidence=0.7,
                    status="open",
                )
            )
            continue
        # bank credit exists for this utr but wasn't matched → residual out of tolerance
        if grp_decomp:
            out.append(_classify_residual(ctx, utr, items, grp_decomp))
        else:
            out.append(
                ReconException(
                    id=_eid(run_id, "unexp", utr),
                    run_id=run_id,
                    record_ids=[it.id for it in items],
                    category="UNEXPLAINED",
                    classified_by="unclassified",
                    amount_impact_minor=abs(expected),
                    confidence=None,
                    status="open",
                )
            )

    # 3. orphan bank credits (no settlement_utr match / not matched)
    unmatched_block_nets = [
        expected_net_minor(items) for utr, items in proc_blocks.items() if utr not in matched_utrs
    ]
    for b in bank:
        if b.id in matched_ids:
            continue
        utr = b.external_ids.get("utr")
        if utr and utr in proc_blocks:
            continue  # handled above
        cands = cand_map.get(b.id, [])
        # if the bank amount ties an unmatched settlement batch's net, the UTR was
        # just lost from the narration; otherwise it's a genuine orphan credit
        ties_a_batch = any(abs(b.amount_minor - net) <= rounding for net in unmatched_block_nets)
        carried = match_carry_forward(b.amount_minor, utr, priors, tol=rounding) if priors else None
        note = None
        if ties_a_batch:
            cat, rule, conf = "MISSING_UTR", "rule:r_missing_utr", 0.7
        elif carried is not None:
            cat, rule, conf = "TIMING", "rule:r_cross_period", 0.75
            note = (
                f"carried forward — settles batch {carried.settlement_utr} left open by "
                f"run {carried.from_run_id[:8]} (period {carried.period})"
            )
        else:
            cat, rule, conf = "UNEXPLAINED", "unclassified", None
        out.append(
            ReconException(
                id=_eid(run_id, "orphan", b.id),
                run_id=run_id,
                record_ids=[b.id],
                category=cat,
                classified_by=rule,
                amount_impact_minor=abs(b.amount_minor),
                confidence=conf,
                candidates=cands,
                note=note,
                status="open",
            )
        )

    # 4. unmapped orders / partial payments
    for r in processor:
        if r.kind != "payment" or r.id in matched_ids:
            continue
        oid = r.external_ids.get("order_id")
        if oid and oid not in ledger_orders:
            out.append(
                ReconException(
                    id=_eid(run_id, "unmapped", r.id),
                    run_id=run_id,
                    record_ids=[r.id],
                    category="UNEXPLAINED",
                    classified_by="unclassified",
                    amount_impact_minor=abs(r.amount_minor),
                    confidence=None,
                    status="open",
                )
            )

    _ = by_id
    dedup: dict[str, ReconException] = {}
    for e in out:
        dedup.setdefault(e.id, e)
    return sorted(dedup.values(), key=lambda e: (-abs(e.amount_impact_minor), e.id))


def _classify_residual(
    ctx: _Ctx, utr: str, items: list[Record], decomp: Decomposition
) -> ReconException:
    residual = decomp.residual_minor
    abs_res = abs(residual)
    eid = _eid(ctx.run_id, "resid", utr)
    ids = [it.id for it in items]

    total_fee = sum(it.fee_minor + it.tax_minor for it in items) or 1

    # first: let the spec's `rules:` decide (docs/adr/0003)
    if ctx.engine is not None:
        rctx = build_context(
            all_records=ctx.all_records,
            exception_records=items,
            residual_minor=residual,
            amount_impact_minor=residual,
            decomp=decomp,
        )
        hit = ctx.engine.classify(rctx)
        if hit is not None:
            return ReconException(
                id=eid,
                run_id=ctx.run_id,
                record_ids=ids,
                category=hit.classify,
                classified_by=f"rule:{hit.id}",
                amount_impact_minor=residual,
                confidence=0.9 if hit.classify != "UNEXPLAINED" else None,
                resolution={"action": hit.resolve} if hit.resolve else None,
                status="open",
            )

    # fallback: built-in heuristics (M1 behaviour, retained until every case is a rule)
    if abs_res <= ctx.rounding_minor:
        cat, rule, conf = "ROUNDING", "rule:r_rounding", 0.95
    elif not decomp.ledger_crosscheck_ok:
        cat, rule, conf = "PARTIAL_PAYMENT", "unclassified", 0.6
    elif abs_res <= total_fee * 0.25:
        # the gap is the size of a fee component: the recorded MDR/GST does not
        # match what the bank actually deducted — an over/under-charge (docs/15 §3.1)
        cat, rule, conf = "FEE_DEDUCTION", "rule:r_fee_drift", 0.7
    else:
        cat, rule, conf = "UNEXPLAINED", "unclassified", None

    return ReconException(
        id=eid,
        run_id=ctx.run_id,
        record_ids=ids,
        category=cat,
        classified_by=rule,
        amount_impact_minor=residual,
        confidence=conf,
        status="open",
    )
