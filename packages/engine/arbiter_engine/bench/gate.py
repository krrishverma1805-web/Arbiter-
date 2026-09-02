"""Regression gate — compare a fresh scorecard against a committed baseline
(docs/28 §1.4).

Every metric that should only ever improve (or hold) gets a direction and a
tolerance. The gate fails the build if any of them moves the wrong way by more
than its tolerance, so a change that quietly trades match rate for coverage
cannot land unnoticed. The baseline is regenerated deliberately when a genuine
improvement lands.
"""

from __future__ import annotations

from typing import Any

# (json path, direction, absolute tolerance). direction "up" ⇒ must not fall;
# "down" ⇒ must not rise.
_CHECKS: list[tuple[str, str, float]] = [
    ("matching.auto_match_rate", "up", 0.02),
    ("matching.precision", "up", 0.02),
    ("matching.recall", "up", 0.02),
    ("matching.dollar_coverage", "up", 0.01),
    ("matching.false_match_rate", "down", 0.005),
    ("matching.dollar_unexplained", "down", 0.01),
    ("exceptions.category_accuracy", "up", 0.05),
    ("agent.hallucination_rate", "down", 0.02),
    ("agent.grounded_rate", "up", 0.05),
]


def _get(d: dict[str, Any], path: str) -> float | None:
    cur: Any = d
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return float(cur) if isinstance(cur, int | float) else None


def check_regression(baseline: dict[str, Any], current: dict[str, Any]) -> list[str]:
    """Return a list of human-readable failure lines; empty ⇒ the gate passes."""
    failures: list[str] = []
    for path, direction, tol in _CHECKS:
        b = _get(baseline, path)
        c = _get(current, path)
        if b is None or c is None:
            continue
        if direction == "up" and c < b - tol:
            failures.append(f"{path}: {c:.4f} < baseline {b:.4f} (−{b - c:.4f}, tol {tol})")
        elif direction == "down" and c > b + tol:
            failures.append(f"{path}: {c:.4f} > baseline {b:.4f} (+{c - b:.4f}, tol {tol})")
    return failures
