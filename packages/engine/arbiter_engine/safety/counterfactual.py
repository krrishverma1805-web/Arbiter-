"""Deterministic counterfactual verification (ENGINEERING_AUDIT.md G3, spec §13).

The 2nd-model verifier asks an LLM "do the cited records support this?" — useful,
but it is still a model checking a model. This module does the arithmetic instead:
*if the proposed category were the true cause, what would the numbers look like —
and do they?*

Each check returns `(consistent, note)`:

* `consistent is False` — the hypothesis is arithmetically contradicted by the
  run's own deterministic decomposition. The Safety Kernel escalates.
* `consistent is True` and `note` starts with `"confirmed:"` — a category-specific
  arithmetic check actually *ran and passed*. This is a positive signal; the
  kernel needs it before it will mark a proposal SAFE (auto-resolvable).
* `consistent is True` and `note` is empty — no check applies to this category.
  This is silence, NOT a pass: the kernel will not mark such a proposal SAFE.
"""

from __future__ import annotations

from typing import Any

# how far the observed residual may sit from the amount the hypothesis predicts,
# as a fraction, before we call it a contradiction
_REL_TOL = 0.02
_ABS_TOL_MINOR = 200  # ₹2 — absolute floor so tiny residuals don't trip on rounding


def _residual_for(exc: Any, snap: Any) -> int | None:
    """The signed settlement residual most relevant to this exception
    (actual − expected; negative ⇒ short settlement).

    Linkage is by settlement_utr: a record carries it on `external_ids`, a
    `Decomposition` carries it as a top-level field. (The group_id spaces don't
    overlap the record-id space, so a group_id comparison never matches.)"""
    recs = _records(exc, snap)
    utrs = {
        r.external_ids.get("settlement_utr")
        for r in recs
        if getattr(r, "external_ids", None) and r.external_ids.get("settlement_utr")
    }
    rec_ids = {r.id for r in recs}
    for d in getattr(snap, "decompositions", []) or []:
        if getattr(d, "settlement_utr", None) in utrs or getattr(d, "group_id", "") in rec_ids:
            return int(d.residual_minor)
    # fall back to the exception's own signed impact
    imp = getattr(exc, "amount_impact_minor", None)
    return int(imp) if imp is not None else None


def _close(a: int, b: int) -> bool:
    return abs(a - b) <= max(_ABS_TOL_MINOR, int(abs(b) * _REL_TOL))


def _records(exc: Any, snap: Any) -> list[Any]:
    recs = getattr(snap, "records", {}) or {}
    return [recs[i] for i in getattr(exc, "record_ids", []) or [] if i in recs]


def check(proposal: Any, exc: Any, snap: Any) -> tuple[bool, str]:
    category = str(getattr(proposal, "category", ""))
    residual = _residual_for(exc, snap)
    recs = _records(exc, snap)

    # ---- REFUND-shaped hypotheses: a refund reduces the net, never raises it ----
    if category in ("PARTIAL_PAYMENT", "CHARGEBACK") and residual is not None:
        if residual > _ABS_TOL_MINOR:
            return (
                False,
                f"{category} implies money was withheld, but the settlement is "
                f"{residual} minor OVER expected, not short",
            )
        if residual < -_ABS_TOL_MINOR:
            return (
                True,
                f"confirmed: settlement is {abs(residual)} minor short, consistent with {category}",
            )

    # ---- ROUNDING: genuine rounding is a paise or two per line — a residual of
    # more than that is a fee/tax/partial issue wearing a ROUNDING label ----
    if category == "ROUNDING" and residual is not None:
        limit = max(20, len(recs) * 2)  # 2 paise/line, floor 20 paise
        if abs(residual) > limit:
            return (
                False,
                f"ROUNDING proposed but the residual is {abs(residual)} minor (> {limit} minor) — "
                "too large to be sub-rupee rounding",
            )
        return (
            True,
            f"confirmed: residual {abs(residual)} minor is within rounding tolerance {limit}",
        )

    # ---- FEE_DEDUCTION / TAX_DEDUCTION: a fee variance is small vs. gross ----
    if category in ("FEE_DEDUCTION", "TAX_DEDUCTION") and residual is not None:
        gross = 0
        for d in getattr(snap, "decompositions", []) or []:
            gross = max(gross, int(d.components.get("gross", 0)))
        if gross and abs(residual) > gross * 0.05:
            return (
                False,
                f"{category} implies a fee/tax variance, but the residual "
                f"{abs(residual)} minor is >5% of gross ({gross}) — too large for a fee drift",
            )
        if gross:
            return (
                True,
                f"confirmed: residual {abs(residual)} minor is "
                f"{abs(residual) / gross:.1%} of gross — plausible for a {category}",
            )

    # ---- DUPLICATE: a repeated payment id whose amount ≈ the residual ----
    if category == "DUPLICATE":
        ids: dict[str, int] = {}
        for r in recs:
            ext = getattr(r, "external_ids", {}) or {}
            key = str(ext.get("payment_id") or ext.get("entity_id") or "")
            if key:
                ids[key] = ids.get(key, 0) + 1
        if recs and not any(n >= 2 for n in ids.values()):
            return False, "DUPLICATE proposed but no payment_id/entity_id repeats among the records"
        dup_amt = max((abs(int(getattr(r, "amount_minor", 0))) for r in recs), default=0)
        if residual is not None and dup_amt and not _close(abs(residual), dup_amt):
            return (
                False,
                f"DUPLICATE proposed but the largest repeated amount ({dup_amt} minor) "
                f"does not match the residual ({abs(residual)} minor)",
            )
        if any(n >= 2 for n in ids.values()):
            return (
                True,
                "confirmed: a payment_id/entity_id repeats and its amount matches the residual",
            )

    # ---- TIMING: a residual explained by a settlement landing outside the
    # window. Two shapes count as positive confirmation:
    #   (a) a genuine cross-source date gap — a bank record and a settlement
    #       record for the same money on different dates; or
    #   (b) a period straddle — the WHOLE expected credit is outstanding
    #       (the generator drops the late batch's bank credit entirely).
    # A zero residual (nothing outstanding) or a partial short (a capture/refund
    # issue) is NOT timing. ----
    if category == "TIMING":
        bank_dates = {
            str(getattr(r, "value_date", "") or getattr(r, "settled_at", "") or "")
            for r in recs
            if getattr(r, "source", "") == "bank"
        }
        settle_dates = {
            str(getattr(r, "settled_at", "") or getattr(r, "value_date", "") or "")
            for r in recs
            if getattr(r, "source", "") != "bank"
        }
        bank_dates.discard("")
        settle_dates.discard("")
        cross_source = bool(bank_dates and settle_dates)
        settled = residual is not None and abs(residual) <= _ABS_TOL_MINOR

        if cross_source and bank_dates.isdisjoint(settle_dates):
            # a clean timing difference: the money DID land, just on a different
            # date. A non-zero residual means money is actually missing → a
            # capture/refund issue, not timing.
            if settled or residual is None:
                return True, "confirmed: a bank credit and its settlement carry different dates"
            return (
                False,
                f"TIMING proposed and the dates differ, but {abs(residual)} minor is still "
                "outstanding — a date difference does not explain missing money",
            )
        if cross_source:
            return (
                False,
                "TIMING proposed but the cited bank credit and settlement carry the same "
                "date — no spread to explain the gap",
            )
        if settled:
            return (
                False,
                "TIMING proposed but the settlement reconciles — nothing is outstanding "
                "to be explained by a timing difference",
            )
        expected = 0
        for d in getattr(snap, "decompositions", []) or []:
            expected = max(expected, abs(int(getattr(d, "expected_minor", 0) or 0)))
        if residual is not None and expected and _close(abs(residual), expected):
            return (
                True,
                "confirmed: the full expected credit is outstanding — consistent with a "
                "period straddle",
            )
        # outstanding, but only partially, and no cross-source date gap:
        # inconclusive for TIMING. Stay silent so the kernel will not mark SAFE.

    return True, ""
