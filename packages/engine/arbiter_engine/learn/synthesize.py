"""Synthesise a candidate classification rule from a resolved exception.

The rule is deliberately conservative — it fires only for exceptions that look
like the one just resolved (same category shape, residual within the same band,
same source). A human reviews and merges it (docs/adr/0003).
"""

from __future__ import annotations

import hashlib
from typing import Any

from arbiter_engine.exceptions.rules import compile_rule
from arbiter_engine.models import Decomposition, ReconException, Record

# category -> the `when` template + default resolve, keyed on what the exception carries
_TEMPLATES: dict[str, tuple[str, str]] = {
    "ROUNDING": (
        "exception.residual_minor != 0 and abs(exception.residual_minor) <= {band}",
        "accept_variance",
    ),
    "SPLIT_SETTLEMENT": (
        "exception.record_count >= {rc} and abs(exception.residual_minor) <= {band}",
        "accept_variance",
    ),
    "FEE_DEDUCTION": (
        "abs(exception.residual_minor) <= expected_fee_minor(match) * {frac}",
        "flag_overcharge",
    ),
    "TIMING": (
        "unmatched('bank') and ts_day(record.settled_at) <= 3",
        "carry_forward",
    ),
    "MISSING_UTR": (
        "unmatched('bank') and is_empty(record.utr)",
        "route_to_human",
    ),
    "DUPLICATE": (
        "count_records(source='razorpay_recon', payment_id=record.payment_id, type='payment') > 1",
        "route_to_human",
    ),
    "CHARGEBACK": (
        "not is_empty(record.dispute_id)",
        "route_to_human",
    ),
}


def draft_rule_from_resolution(
    exc: ReconException,
    action: str,
    *,
    category: str | None = None,
    records: list[Record] | None = None,
    decomp: Decomposition | None = None,
) -> dict[str, Any] | None:
    """Return a {rule_id, when, classify, resolve, provenance_exception_id} dict, or
    None if this exception's shape isn't safely generalisable.

    `category` is the human's correction to the classifier — when a controller
    resolves an `UNEXPLAINED` residual as, say, `ROUNDING`, that judgement (not the
    classifier's blank) is what seeds the rule.
    """
    cat = category or exc.category
    if cat is None or cat in ("UNEXPLAINED", "AMBIGUOUS", "SECURITY_REVIEW"):
        return None
    tmpl = _TEMPLATES.get(cat)
    if tmpl is None:
        return None

    when_tmpl, default_resolve = tmpl
    resolve = action or default_resolve
    # the ceiling is the variance the human just accepted, with headroom — a larger
    # one still opens an exception. `rc` pins a split rule to multi-record batches.
    band = max(100, abs(exc.amount_impact_minor) * 2)
    # generalise the "multi-record batch" floor down from the resolved case so a
    # smaller split still matches, but keep it >= 3 so it can't catch a 1:1 residual
    rc = max(3, len(exc.record_ids) // 2)
    when = when_tmpl.format(band=band, frac=0.05, rc=rc)

    try:
        compile_rule(when)  # never emit a rule that won't parse safely
    except Exception:  # noqa: BLE001
        return None

    rid = "r_learned_" + hashlib.sha256(f"{cat}|{when}".encode()).hexdigest()[:8]
    return {
        "rule_id": rid,
        "when": when,
        "classify": cat,
        "resolve": resolve,
        "provenance_exception_id": exc.id,
    }
