"""A deterministic cash-position readout off the reconciled ledger (docs/10 M5).

Every rupee the processor says it settled belongs to exactly one settlement batch
(by `settlement_utr`). Each batch is in one of four places: confirmed in the bank,
in transit (bank credit lands next period), held (disputes / wrong account / under
review), or unexplained. We partition the batches — so the four buckets always
sum back to the processor-side net — and read the bucket from the batch's
exception, or from its clean decomposition. Pure arithmetic, no LLM, no estimate.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from arbiter_engine.events.fold import RunProjection
from arbiter_engine.models import Record

_IN_TRANSIT = {"TIMING"}
_HELD = {
    "CHARGEBACK",
    "WRONG_ACCOUNT",
    "PARTIAL_PAYMENT",
    "DUPLICATE",
    "MISSING_UTR",
    "SECURITY_REVIEW",
}
_MONEY_FOUND = {"FEE_DEDUCTION"}  # a processor over-charge to claw back — owed back, not missing


@dataclass
class CashPosition:
    run_id: str
    gross_minor: int = 0
    mdr_minor: int = 0
    gst_minor: int = 0
    refunds_minor: int = 0
    net_expected_minor: int = 0

    confirmed_minor: int = 0
    confirmed_count: int = 0
    in_transit_minor: int = 0
    held_minor: int = 0
    unexplained_minor: int = 0
    unbatched_minor: int = 0  # rows with no settlement_utr (shouldn't happen; surfaced if it does)

    money_found_minor: int = 0  # a memo line, not part of the partition

    by_bucket: dict[str, int] = field(default_factory=dict)

    @property
    def accounted_minor(self) -> int:
        return (
            self.confirmed_minor
            + self.in_transit_minor
            + self.held_minor
            + self.unexplained_minor
            + self.unbatched_minor
        )

    @property
    def reconciling_delta_minor(self) -> int:
        """net expected − everything the partition places. 0 ⇒ every rupee is placed."""
        return self.net_expected_minor - self.accounted_minor


def _batch_net(items: list[Record]) -> int:
    gross = sum(r.amount_minor for r in items if r.kind == "payment")
    fee = sum(r.fee_minor for r in items)
    tax = sum(r.tax_minor for r in items)
    other = sum(-r.amount_minor for r in items if r.kind in ("refund", "adjustment"))
    return gross - fee - tax - other


def cash_position(proj: RunProjection, *, rounding_tolerance_minor: int = 100) -> CashPosition:
    cp = CashPosition(run_id=proj.run_id)

    recon = [r for r in proj.records if r.source == "razorpay_recon"]
    cp.gross_minor = sum(r.amount_minor for r in recon if r.kind == "payment")
    cp.mdr_minor = sum(r.fee_minor for r in recon)
    cp.gst_minor = sum(r.tax_minor for r in recon)
    cp.refunds_minor = sum(-r.amount_minor for r in recon if r.kind in ("refund", "adjustment"))
    cp.net_expected_minor = cp.gross_minor - cp.mdr_minor - cp.gst_minor - cp.refunds_minor

    # group processor rows by settlement batch
    batches: dict[str, list[Record]] = {}
    for r in recon:
        utr = r.external_ids.get("settlement_utr")
        if utr:
            batches.setdefault(utr, []).append(r)
        else:
            cp.unbatched_minor += _batch_net([r])

    # each batch's exception category (highest-severity if several touch it)
    rec_by_id = {r.id: r for r in proj.records}
    _sev = {**{c: 3 for c in _HELD}, "UNEXPLAINED": 2, **{c: 1 for c in _IN_TRANSIT}}
    batch_cat: dict[str, str] = {}
    for e in proj.exceptions:
        cat = e.category or "UNEXPLAINED"
        if cat == "SECURITY_REVIEW" and not any(
            rec_by_id.get(rid) and rec_by_id[rid].source == "razorpay_recon" for rid in e.record_ids
        ):
            continue
        if cat in _MONEY_FOUND:
            cp.money_found_minor += abs(e.amount_impact_minor)
        for rid in e.record_ids:
            rec = rec_by_id.get(rid)
            u = rec.external_ids.get("settlement_utr") if rec else None
            if not u or u not in batches:
                continue
            if u not in batch_cat or _sev.get(cat, 2) > _sev.get(batch_cat[u], 2):
                batch_cat[u] = cat

    clean_utrs = {
        d.settlement_utr
        for d in proj.decompositions
        if abs(d.residual_minor) <= rounding_tolerance_minor and d.ledger_crosscheck_ok
    }

    for utr, items in batches.items():
        net = _batch_net(items)
        bcat = batch_cat.get(utr)
        if bcat in _IN_TRANSIT:
            cp.in_transit_minor += net
            cp.by_bucket["in_transit"] = cp.by_bucket.get("in_transit", 0) + net
        elif bcat in _HELD:
            cp.held_minor += net
            cp.by_bucket["held"] = cp.by_bucket.get("held", 0) + net
        elif bcat == "UNEXPLAINED":
            cp.unexplained_minor += net
            cp.by_bucket["unexplained"] = cp.by_bucket.get("unexplained", 0) + net
        elif utr in clean_utrs:
            cp.confirmed_minor += net
            cp.confirmed_count += 1
        else:
            # matched-but-not-clean with no exception, or unmatched with no exception
            cp.unexplained_minor += net
            cp.by_bucket["unexplained"] = cp.by_bucket.get("unexplained", 0) + net

    return cp
