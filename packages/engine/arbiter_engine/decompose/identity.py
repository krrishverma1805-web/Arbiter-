from __future__ import annotations

from collections.abc import Iterable

from arbiter_engine.models import Decomposition, Record


def group_by_utr(
    records: Iterable[Record], *, source: str = "razorpay_recon"
) -> dict[str, list[Record]]:
    """Group processor records by their settlement_utr (docs/15 §2)."""
    groups: dict[str, list[Record]] = {}
    for r in sorted(records, key=lambda x: x.id):
        if r.source != source:
            continue
        utr = r.external_ids.get("settlement_utr")
        if not utr:
            continue
        groups.setdefault(utr, []).append(r)
    return groups


def _components(items: list[Record]) -> dict[str, int]:
    gross = sum(r.amount_minor for r in items if r.kind == "payment")
    refunds = sum(-r.amount_minor for r in items if r.kind == "refund")
    debits = sum(
        -r.amount_minor
        for r in items
        if r.kind in ("adjustment", "chargeback") and r.amount_minor < 0
    )
    credits_adj = sum(
        r.amount_minor for r in items if r.kind == "adjustment" and r.amount_minor > 0
    )
    mdr = sum(r.fee_minor for r in items)
    gst = sum(r.tax_minor for r in items)
    return {
        "gross": gross,
        "refunds": refunds,
        "adjustment_debits": debits,
        "adjustment_credits": credits_adj,
        "mdr": mdr,
        "gst_on_mdr": gst,
    }


def expected_net_minor(items: list[Record]) -> int:
    """Σ credit − Σ debit − Σ fee − Σ tax — the settlement identity (docs/15 §2)."""
    total = 0
    for r in items:
        if r.amount_minor >= 0:
            total += r.amount_minor  # credit
        else:
            total += r.amount_minor  # debit is already negative
        total -= r.fee_minor
        total -= r.tax_minor
    return total


def decompose_group(
    run_id: str,
    settlement_utr: str,
    items: list[Record],
    *,
    bank_amount_minor: int | None,
    ledger_total_minor: int | None = None,
) -> Decomposition:
    expected = expected_net_minor(items)
    actual = bank_amount_minor if bank_amount_minor is not None else expected
    residual = actual - expected

    crosscheck_ok = True
    if ledger_total_minor is not None:
        payment_gross = sum(r.amount_minor for r in items if r.kind == "payment")
        crosscheck_ok = payment_gross == ledger_total_minor

    return Decomposition(
        group_id=f"grp_{settlement_utr}",
        run_id=run_id,
        settlement_utr=settlement_utr,
        expected_minor=expected,
        actual_minor=actual,
        residual_minor=residual,
        ledger_crosscheck_ok=crosscheck_ok,
        components=_components(items),
    )
