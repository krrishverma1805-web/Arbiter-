"""The benchmark — score a run against labeled ground truth (docs/07).

M1: the matching scorecard (auto-match rate, precision, recall, false-match
rate, ₹ coverage) + the deterministic classifier's category accuracy against
the anomaly labels. The agent scorecard (docs/12 §6) arrives with M3.
"""

from arbiter_engine.bench.scorecard import SafetyScore, Scorecard, score_run

__all__ = ["SafetyScore", "Scorecard", "score_run"]
