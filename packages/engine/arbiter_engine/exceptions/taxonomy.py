"""The exception taxonomy (docs/15 §3, specs/razorpay-settlement.yaml)."""

from __future__ import annotations

TAXONOMY: tuple[str, ...] = (
    "FEE_DEDUCTION",
    "TAX_DEDUCTION",
    "ROUNDING",
    "PARTIAL_PAYMENT",
    "TIMING",
    "DUPLICATE",
    "CHARGEBACK",
    "ADJUSTMENT",
    "FX_DIFFERENCE",
    "MISSING_UTR",
    "WRONG_ACCOUNT",
    "SECURITY_REVIEW",
    "SPLIT_SETTLEMENT",
    "UNEXPLAINED",
    "AMBIGUOUS",
)

# Categories that must never be routed to the AI agent (docs/14 C2).
NEVER_ADJUDICATE: frozenset[str] = frozenset({"SECURITY_REVIEW"})

# Categories a deterministic rule can fully resolve (docs/15 §3.1-3.2).
AUTO_RESOLVABLE: frozenset[str] = frozenset(
    {"ROUNDING", "FEE_DEDUCTION", "TAX_DEDUCTION", "TIMING", "FX_DIFFERENCE", "SPLIT_SETTLEMENT"}
)
