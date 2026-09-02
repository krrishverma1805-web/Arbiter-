"""Cross-period carry-forward (docs/28 §1.2).

A settlement batch that this month's run couldn't close (the bank credit hadn't
landed yet, so it sat as a TIMING / MISSING_UTR / UNEXPLAINED exception) is often
closed *next* month by a credit that arrives late. Without this the late credit
looks like an unexplained orphan every time.

`prior_open_batches` folds the tenant's earlier completed runs for the same spec
and returns the settlement batches that ended a run still open. The classifier
then matches an otherwise-orphan bank credit against them by settlement_utr or by
net amount, and labels it `TIMING` with a note pointing at the originating run —
explained, not unexplained. It is deliberately *not* an auto-match: the batch
lives in another run's ledger, so a human still confirms the carry-forward.
"""

from __future__ import annotations

from dataclasses import dataclass

from arbiter_engine.events.fold import fold_run
from arbiter_engine.events.payloads import EventType
from arbiter_engine.events.store import EventStore

_OPEN_CARRYABLE = {"TIMING", "MISSING_UTR", "SPLIT_SETTLEMENT", "UNEXPLAINED", "PARTIAL_PAYMENT"}


@dataclass(frozen=True)
class PriorBatch:
    settlement_utr: str
    net_minor: int
    from_run_id: str
    period: str


def prior_open_batches(
    store: EventStore, spec_hash: str, *, exclude_run_id: str
) -> list[PriorBatch]:
    out: list[PriorBatch] = []
    for rid in store.runs():
        if rid == exclude_run_id:
            continue
        types = {t for t, _ in store.iter_payloads(rid)}
        if EventType.RUN_COMPLETED not in types:
            continue
        started = next((p for t, p in store.iter_payloads(rid) if t == EventType.RUN_STARTED), None)
        if not started or started.get("spec_hash") != spec_hash:
            continue
        proj = fold_run(store, rid)
        rec_by_id = {r.id: r for r in proj.records}
        for exc in proj.exceptions:
            open_ = exc.status in ("open", "escalated", "proposed")
            if not open_ or exc.category not in _OPEN_CARRYABLE:
                continue
            recs = [rec_by_id[i] for i in exc.record_ids if i in rec_by_id]
            utrs = {r.external_ids.get("settlement_utr") or r.external_ids.get("utr") for r in recs}
            utrs.discard(None)
            if not utrs:
                continue
            net = sum(r.amount_minor for r in recs if r.kind == "payment") - sum(
                r.fee_minor + r.tax_minor for r in recs
            )
            magnitude = abs(net) or abs(exc.amount_impact_minor)
            period = min((r.value_date.isoformat() for r in recs if r.value_date), default=rid[:8])[
                :7
            ]
            out.extend(PriorBatch(str(u), magnitude, rid, period) for u in utrs)
    return out


def match_carry_forward(
    bank_amount_minor: int, bank_utr: str | None, priors: list[PriorBatch], *, tol: int
) -> PriorBatch | None:
    if bank_utr:
        for p in priors:
            if p.settlement_utr == bank_utr:
                return p
    for p in priors:
        if abs(abs(bank_amount_minor) - p.net_minor) <= tol:
            return p
    return None
