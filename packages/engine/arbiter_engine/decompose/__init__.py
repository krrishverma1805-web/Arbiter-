"""Settlement decomposition — the identity Arbiter verifies (docs/15 §2).

For every settlement_utr group:
  expected_bank_credit = Σ credit − Σ debit − Σ fee − Σ tax   (over the group's items)

A match on the payout total that does not decompose is a false match. The
residual (actual − expected) drives classification: 0 ⇒ clean; small ⇒ ROUNDING;
otherwise a typed exception.
"""

from arbiter_engine.decompose.identity import decompose_group, group_by_utr

__all__ = ["decompose_group", "group_by_utr"]
