"""Deterministic matching engine (docs/16).

Passes run in fixed order over the not-yet-matched remainder:
  1. exact     — settlement_utr join, zero residual
  2. tolerant  — settlement_utr join, amount within tolerance / date within window
  (3. subset, 4. fuzzy — M2)

No LLM anywhere in here. All iteration is over sorted record ids so two runs
produce an identical result (docs/16 §9).
"""

from arbiter_engine.match.engine import MatchResult, run_matching

__all__ = ["MatchResult", "run_matching"]
