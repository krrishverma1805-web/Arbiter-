"""Validated exception status transitions (spec §21, docs/17 §5).

`ExceptionStatus` is a plain `Literal`, and in practice the pipeline only ever
advances an exception forward — but nothing *enforced* that. This module is the
one place the legal moves live, so a replay, a second API call, or a future
caller cannot slip an exception out of a terminal state (`resolved` /
`wont_fix`) without a fresh, verified path.

Deterministic, no LLM.
"""

from __future__ import annotations

from arbiter_engine.models import ExceptionStatus, ReconException

#: once here, an exception is done — any onward move needs a new investigation.
TERMINAL: frozenset[str] = frozenset({"resolved", "wont_fix"})

#: src -> the statuses it may legally move to (excluding a no-op move to itself).
_ALLOWED: dict[str, frozenset[str]] = {
    "open": frozenset(
        {"proposed", "escalated", "security_review", "budget_exceeded", "resolved", "wont_fix"}
    ),
    "proposed": frozenset({"open", "escalated", "resolved", "wont_fix"}),
    "escalated": frozenset({"open", "resolved", "wont_fix"}),
    "security_review": frozenset({"escalated", "resolved", "wont_fix"}),
    "budget_exceeded": frozenset({"open", "escalated", "resolved", "wont_fix"}),
    "resolved": frozenset(),
    "wont_fix": frozenset(),
}


class IllegalTransition(ValueError):
    """Raised when a status change is not on the allowed graph."""


def can_transition(src: str, dst: str) -> bool:
    if src == dst:
        return True
    if src in TERMINAL:
        return False
    return dst in _ALLOWED.get(src, frozenset())


def check_transition(src: str, dst: str) -> None:
    if not can_transition(src, dst):
        if src in TERMINAL:
            raise IllegalTransition(
                f"exception is already {src!r} — a terminal state cannot move to {dst!r}"
            )
        raise IllegalTransition(f"{src!r} -> {dst!r} is not a legal exception transition")


def transition(exc: ReconException, dst: ExceptionStatus) -> ReconException:
    """Return a copy of `exc` in status `dst`, or raise `IllegalTransition`."""
    check_transition(exc.status, dst)
    return exc.model_copy(update={"status": dst})


def resolution_target(action: str) -> ExceptionStatus:
    """The status a RESOLUTION_APPLIED with this action drives the exception to."""
    return "wont_fix" if action == "wont_fix" else "resolved"
