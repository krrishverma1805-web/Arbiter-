import pytest
from arbiter_engine.events.payloads import EventType
from arbiter_engine.events.store import ChainBroken, EventStore
from sqlmodel import Session, text


def _store() -> EventStore:
    return EventStore("sqlite://")


def test_append_builds_a_hash_chain():
    s = _store()
    s.append(
        "r1",
        EventType.RUN_STARTED,
        {
            "spec_name": "x",
            "spec_version": 1,
            "spec_hash": "h",
            "dataset_hash": "d",
            "seed": 1,
            "config_hash": "c",
            "no_ai": False,
            "engine_version": "0.0.1",
        },
    )
    s.append("r1", EventType.RUN_COMPLETED, {"status": "completed", "counts": {}})
    evs = s.events("r1")
    assert [e.seq for e in evs] == [0, 1]
    assert evs[0].prev_hash == ""
    assert evs[1].prev_hash == evs[0].hash
    assert s.verify("r1")["intact"] is True


def test_verify_detects_tampering():
    s = _store()
    s.append(
        "r2",
        EventType.RUN_STARTED,
        {
            "spec_name": "x",
            "spec_version": 1,
            "spec_hash": "h",
            "dataset_hash": "d",
            "seed": 1,
            "config_hash": "c",
            "no_ai": False,
            "engine_version": "0.0.1",
        },
    )
    with Session(s.engine) as ses:
        ses.exec(
            text("UPDATE events SET payload = :p WHERE seq = 0").bindparams(p='{"tampered":1}')
        )
        ses.commit()
    with pytest.raises(ChainBroken):
        s.verify("r2")


def test_unknown_event_type_is_rejected():
    s = _store()
    with pytest.raises(ValueError, match="unknown event type|not a valid"):
        s.append("r3", "NOT_A_REAL_EVENT", {})  # type: ignore[arg-type]


def test_bad_payload_is_rejected():
    s = _store()
    with pytest.raises(Exception):  # noqa: B017 - pydantic ValidationError
        s.append("r4", EventType.RUN_COMPLETED, {"status": "completed"})  # missing fields
