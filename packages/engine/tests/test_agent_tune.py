"""Re-fit the agent's escalation threshold from human feedback (docs/28 §3 item 14)."""

from __future__ import annotations

from pathlib import Path

from arbiter_engine.events.payloads import EventType
from arbiter_engine.events.store import EventStore
from arbiter_engine.learn.agent_tune import (
    load_escalation_threshold,
    tune_escalation_threshold,
)
from arbiter_engine.models import ReconException, Record
from arbiter_engine.specs import load_spec, spec_hash

SPEC = Path(__file__).resolve().parents[3] / "specs/razorpay-settlement.yaml"


def _run_with_feedback(
    store: EventStore, rid: str, sh: str, rows: list[tuple[float, bool]]
) -> None:
    store.append(
        rid,
        EventType.RUN_STARTED,
        {
            "spec_name": "s",
            "spec_version": 1,
            "spec_hash": sh,
            "dataset_hash": "d",
            "seed": None,
            "config_hash": "c",
            "no_ai": False,
            "engine_version": "0",
        },
    )
    for i, (conf, accepted) in enumerate(rows):
        eid = f"{rid}-e{i}"
        rec = Record(id=f"{eid}r", run_id=rid, source="bank", kind="credit", amount_minor=100)
        exc = ReconException(
            id=eid,
            run_id=rid,
            category="TIMING",
            classified_by="rule",
            amount_impact_minor=100,
            record_ids=[rec.id],
        )
        store.append(rid, EventType.RECORD_INGESTED, {"record": rec.model_dump(mode="json")})
        store.append(rid, EventType.EXCEPTION_OPENED, {"exception": exc.model_dump(mode="json")})
        store.append(
            rid,
            EventType.AGENT_PROPOSAL_CREATED,
            {
                "exception_id": eid,
                "proposal": {"suggested_action": {"action": "carry_forward"}},
                "tool_calls": 1,
                "turns": 1,
                "tokens_in": 1,
                "tokens_out": 1,
                "grounding": {"grounded_confidence": conf},
            },
        )
        store.append(
            rid,
            EventType.RESOLUTION_APPLIED,
            {
                "exception_id": eid,
                "action": "carry_forward" if accepted else "route_to_human",
                "detail": "",
                "actor": "h",
                "prior_status": "proposed",
                "category": "TIMING",
            },
        )
    store.append(rid, EventType.RUN_COMPLETED, {"status": "completed", "counts": {}})


def test_threshold_settles_between_accepted_and_overridden_bands(tmp_path):
    store = EventStore(f"sqlite:///{tmp_path / 't.db'}", org_id="acme")
    sh = spec_hash(load_spec(SPEC))
    # humans accepted every proposal with grounded_confidence >= 0.70, overrode below
    rows = [(0.9, True)] * 8 + [(0.75, True)] * 6 + [(0.6, False)] * 6 + [(0.4, False)] * 4
    _run_with_feedback(store, "run-1", sh, rows)

    res = tune_escalation_threshold(store, load_spec(SPEC), trained_by="test")
    assert res.tuned
    assert 0.6 < res.theta_escalate <= 0.75
    assert res.accepted == 14 and res.overridden == 10
    assert load_escalation_threshold(store, sh) == res.theta_escalate


def test_too_little_feedback_is_a_no_op(tmp_path):
    store = EventStore(f"sqlite:///{tmp_path / 'u.db'}", org_id="acme")
    sh = spec_hash(load_spec(SPEC))
    _run_with_feedback(store, "run-1", sh, [(0.9, True)] * 3 + [(0.5, False)] * 2)
    res = tune_escalation_threshold(store, load_spec(SPEC))
    assert res.tuned is False
    assert load_escalation_threshold(store, sh) is None


def test_a_tuned_threshold_is_loaded_by_orchestrate(tmp_path):
    from arbiter_engine.agent.orchestrate import _adjudication

    store = EventStore(f"sqlite:///{tmp_path / 'v.db'}", org_id="acme")
    spec = load_spec(SPEC)
    sh = spec_hash(spec)
    rows = [(0.9, True)] * 10 + [(0.55, False)] * 10
    _run_with_feedback(store, "run-1", sh, rows)
    tune_escalation_threshold(store, spec)

    loaded = load_escalation_threshold(store, sh)
    assert loaded is not None
    # the spec default is 0.55; the tuned value replaces it
    assert loaded != _adjudication(spec)["stopping"]["theta_escalate"] or loaded == 0.55
