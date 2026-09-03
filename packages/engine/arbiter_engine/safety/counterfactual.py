"""Deterministic counterfactual verification (ENGINEERING_AUDIT.md G3, spec §13).

The 2nd-model verifier asks an LLM "do the cited records support this?" — useful,
but it is still a model checking a model. This module does the arithmetic instead:
*if the proposed category were the true cause, what would the numbers look like —
and do they?*

Each check returns `(consistent, note)`. `consistent is False` means the hypothesis
is arithmetically contradicted by the run's own deterministic decomposition, and
the Safety Kernel will escalate rather than present the proposal. `consistent is
True` with an empty note means "no counterfactual check applies to this category"
(not a pass — just silence).
"""

from __future__ import annotations

from typing import Any

# how far the observed residual may sit from the amount the hypothesis predicts,
# as a fraction, before we call it a contradiction
_REL_TOL = 0.02
_ABS_TOL_MINOR = 200  # ₹2 — absolute floor so tiny residuals don't trip on rounding


def _residual_for(exc: Any, snap: Any) -> int | None:
    """The signed settlement residual most relevant to this exception
    (actual − expected; negative ⇒ short settlement)."""
    rec_ids = set(getattr(exc, "record_ids", []) or [])
    for d in getattr(snap, "decompositions", []) or []:
        # a decomposition whose group overlaps this exception's records
        gid = getattr(d, "group_id", "")
        if gid in rec_ids or any(gid in r for r in rec_ids):
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
    if (
        category in ("PARTIAL_PAYMENT", "CHARGEBACK")
        and residual is not None
        and residual > _ABS_TOL_MINOR
    ):
        return (
            False,
            f"{category} implies money was withheld, but the settlement is "
            f"{residual} minor OVER expected, not short",
        )

    # ---- ROUNDING: the residual must actually be tiny ----
    if category == "ROUNDING" and residual is not None and abs(residual) > 500:
        return False, f"ROUNDING proposed but the residual is {abs(residual)} minor (> ₹5.00)"

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
        if residual is not None:
            dup_amt = max((abs(int(getattr(r, "amount_minor", 0))) for r in recs), default=0)
            if dup_amt and not _close(abs(residual), dup_amt):
                return (
                    False,
                    f"DUPLICATE proposed but the largest repeated amount ({dup_amt} minor) "
                    f"does not match the residual ({abs(residual)} minor)",
                )

    # ---- TIMING: at least one cited record settled outside the batch window ----
    if category == "TIMING" and recs:
        dates = {
            str(getattr(r, "settled_at", "") or getattr(r, "value_date", "") or "") for r in recs
        }
        dates.discard("")
        if len(dates) <= 1:
            return (
                False,
                "TIMING proposed but every cited record carries the same settlement/value "
                "date — no timing spread to explain the gap",
            )

    return True, ""
