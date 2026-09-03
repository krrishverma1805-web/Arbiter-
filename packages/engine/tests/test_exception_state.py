import pytest
from arbiter_engine.exceptions.state import (
    IllegalTransition,
    can_transition,
    check_transition,
    resolution_target,
    transition,
)
from arbiter_engine.models import ReconException


def _exc(status: str) -> ReconException:
    return ReconException(id="exc_1", run_id="r", status=status)  # type: ignore[arg-type]


def test_forward_moves_are_allowed():
    assert can_transition("open", "proposed")
    assert can_transition("open", "escalated")
    assert can_transition("proposed", "resolved")
    assert can_transition("escalated", "resolved")
    assert can_transition("security_review", "escalated")


def test_terminal_states_are_final():
    assert not can_transition("resolved", "open")
    assert not can_transition("resolved", "wont_fix")
    assert not can_transition("wont_fix", "resolved")
    with pytest.raises(IllegalTransition, match="terminal"):
        check_transition("resolved", "wont_fix")


def test_same_status_is_a_noop_not_an_error():
    check_transition("resolved", "resolved")  # must not raise
    assert transition(_exc("resolved"), "resolved").status == "resolved"


def test_illegal_forward_move_is_rejected():
    with pytest.raises(IllegalTransition):
        check_transition("proposed", "security_review")


def test_transition_returns_a_copy():
    e = _exc("open")
    moved = transition(e, "escalated")
    assert moved.status == "escalated"
    assert e.status == "open"  # original untouched (model is frozen)


def test_resolution_target_maps_action_to_status():
    assert resolution_target("wont_fix") == "wont_fix"
    assert resolution_target("carry_forward") == "resolved"
    assert resolution_target("accept_variance") == "resolved"
