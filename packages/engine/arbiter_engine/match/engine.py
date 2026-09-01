"""Matching engine orchestration (docs/16 §2).

M1: blocking by settlement_utr, then pass 1 (exact) and pass 2 (tolerant) over
each block, with settlement decomposition applied to every candidate match.
Pass 3 (subset) and pass 4 (fuzzy) arrive in M2.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from arbiter_engine.decompose.identity import decompose_group, expected_net_minor
from arbiter_engine.match.confidence import (
    ConfidenceModel,
    FieldScores,
    amount_score,
    date_score,
)
from arbiter_engine.models import Decomposition, Match, Record
from arbiter_engine.specs.model import ReconSpec


@dataclass
class MatchResult:
    matches: list[Match] = field(default_factory=list)
    decompositions: list[Decomposition] = field(default_factory=list)
    matched_ids: set[str] = field(default_factory=set)

    def unmatched(self, records: list[Record]) -> list[Record]:
        return sorted((r for r in records if r.id not in self.matched_ids), key=lambda r: r.id)


@dataclass
class _Tolerances:
    amount_minor: int
    date_window_days: int
    rounding_minor: int
    auto: float
    review: float


def _tolerances(spec: ReconSpec) -> _Tolerances:
    tol = spec.passes.get("tolerant") or [{}]
    first = tol[0] if isinstance(tol, list) and tol else {}
    ident = spec.identity or {}
    thr = spec.thresholds or {}
    return _Tolerances(
        amount_minor=int(first.get("amount_tolerance_minor", 200)),
        date_window_days=int(first.get("date_window_days", 4)),
        rounding_minor=int(ident.get("rounding_tolerance_minor", 100)),
        auto=float(thr.get("auto", 0.90)),
        review=float(thr.get("review", 0.70)),
    )


def run_matching(run_id: str, records: list[Record], spec: ReconSpec) -> MatchResult:
    tol = _tolerances(spec)
    conf_model = (
        ConfidenceModel(spec.confidence_weights) if spec.confidence_weights else ConfidenceModel()
    )
    result = MatchResult()

    by_id = {r.id: r for r in records}
    processor = sorted((r for r in records if r.source == "razorpay_recon"), key=lambda r: r.id)
    bank = sorted((r for r in records if r.source == "bank"), key=lambda r: r.id)
    ledger = sorted((r for r in records if r.source == "ledger"), key=lambda r: r.id)

    # blocking: processor items by settlement_utr; bank credits by parsed utr
    proc_blocks: dict[str, list[Record]] = {}
    for r in processor:
        utr = r.external_ids.get("settlement_utr")
        if utr:
            proc_blocks.setdefault(utr, []).append(r)

    bank_by_utr: dict[str, list[Record]] = {}
    for b in bank:
        utr = b.external_ids.get("utr")
        if utr:
            bank_by_utr.setdefault(utr, []).append(b)

    ledger_by_order = {r.external_ids.get("order_id", r.id): r for r in ledger}

    for utr in sorted(proc_blocks):
        items = sorted(proc_blocks[utr], key=lambda r: r.id)
        bank_candidates = sorted(bank_by_utr.get(utr, []), key=lambda r: r.id)
        expected = expected_net_minor(items)

        order_ids = [
            it.external_ids["order_id"]
            for it in items
            if it.kind == "payment" and it.external_ids.get("order_id")
        ]
        ledger_matches = [ledger_by_order[oid] for oid in order_ids if oid in ledger_by_order]
        ledger_total = sum(m.amount_minor for m in ledger_matches) or None

        if not bank_candidates:
            continue  # no bank credit for this batch → handled as an exception downstream

        # deterministic: take the closest bank credit by |Δ| then id
        bank_rec = min(
            bank_candidates,
            key=lambda b: (abs(b.amount_minor - expected), b.id),
        )
        delta = bank_rec.amount_minor - expected

        within_amount = abs(delta) <= tol.amount_minor
        d_score = date_score(
            bank_rec.value_date,
            max((it.settled_at for it in items if it.settled_at), default=None),
            tol.date_window_days,
        )

        if delta == 0:
            match_pass = "exact"
            confidence = 1.0
            fs = FieldScores(
                key_agreement=1.0,
                amount_score=1.0,
                date_score=1.0,
                reference_similarity=1.0,
                shared_external_id=1.0,
            )
        elif within_amount:
            match_pass = "tolerant"
            fs = FieldScores(
                key_agreement=1.0,  # settlement_utr matched exactly
                amount_score=amount_score(delta, tol.amount_minor),
                date_score=d_score,
                reference_similarity=1.0,
                shared_external_id=1.0 if order_ids else 0.0,
            )
            confidence = conf_model.score(fs)
        else:
            # utr matches but the amount is out of tolerance — not an auto match;
            # decomposition + the classifier (M1c) will make this an exception
            decomp = decompose_group(
                run_id,
                utr,
                items,
                bank_amount_minor=bank_rec.amount_minor,
                ledger_total_minor=ledger_total,
            )
            result.decompositions.append(decomp)
            continue

        status = "auto" if confidence >= tol.auto else "low_confidence"
        left_ids = [it.id for it in items]
        right_ids = [bank_rec.id]
        group_ids = [m.id for m in ledger_matches]

        decomp = decompose_group(
            run_id,
            utr,
            items,
            bank_amount_minor=bank_rec.amount_minor,
            ledger_total_minor=ledger_total,
        )
        result.decompositions.append(decomp)

        residual = decomp.residual_minor
        if abs(residual) > tol.rounding_minor and match_pass == "exact":
            # exact on the recorded total but the identity does not close cleanly
            match_pass = "tolerant"
            status = "low_confidence"
            confidence = min(confidence, tol.review)

        match = Match(
            id=f"m_{utr}",
            run_id=run_id,
            left_ids=sorted(left_ids),
            right_ids=sorted(right_ids),
            group_ids=sorted(group_ids),
            match_pass=match_pass,  # type: ignore[arg-type]
            weight_bits=None,
            per_field_weights=fs.as_dict(),
            confidence=round(confidence, 4),
            rule_id=None,
            residual_minor=residual,
            status=status,  # type: ignore[arg-type]
        )
        result.matches.append(match)
        result.matched_ids.update(match.all_ids)
        _ = by_id  # reserved for M2 transitive closure

    result.matches.sort(key=lambda m: m.id)
    result.decompositions.sort(key=lambda d: d.group_id)
    return result
