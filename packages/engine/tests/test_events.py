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


def test_two_tenants_over_one_database_are_isolated(tmp_path):
    """Org A and Org B share a database file; neither can see the other's runs,
    even for the identical spec + dataset (docs/28 §2)."""
    from arbiter_engine.events.payloads import EventType

    url = f"sqlite:///{tmp_path / 'shared.db'}"
    a = EventStore(url, org_id="org_a")
    b = EventStore(url, org_id="org_b")

    payload = {
        "spec_name": "s",
        "spec_version": 1,
        "spec_hash": "h",
        "dataset_hash": "d",
        "seed": None,
        "config_hash": "c",
        "no_ai": True,
        "engine_version": "0.0.1",
    }
    a.append("run_x", EventType.RUN_STARTED, {**payload, "org_id": "org_a"})
    b.append("run_x", EventType.RUN_STARTED, {**payload, "org_id": "org_b"})

    assert a.runs() == ["run_x"]
    assert b.runs() == ["run_x"]
    # same run_id string, but each store sees only its own event
    assert a.verify("run_x")["events"] == 1
    assert b.verify("run_x")["events"] == 1
    a_ev = a.events("run_x")
    b_ev = b.events("run_x")
    assert a_ev[0].org_id == "org_a" and a_ev[0].seq == 0
    assert b_ev[0].org_id == "org_b" and b_ev[0].seq == 0
    assert a_ev[0].hash != b_ev[0].hash  # payloads differ by org_id

    # a purge in one tenant does not touch the other
    a.purge("run_x", reason="test", by="t")
    assert a.runs() == []
    assert b.runs() == ["run_x"]


def test_execute_partitions_run_ids_by_tenant(tmp_path, spec_path, clean_dataset):
    from arbiter_engine.run import RunInputs, execute

    url = f"sqlite:///{tmp_path / 'multi.db'}"
    pa = execute(
        EventStore(url, org_id="a"), RunInputs(spec_path=spec_path, dataset_dir=clean_dataset)
    )
    pb = execute(
        EventStore(url, org_id="b"), RunInputs(spec_path=spec_path, dataset_dir=clean_dataset)
    )
    assert pa.run_id != pb.run_id  # same spec+dataset, different tenant -> different run
    # and the default (local) path is unchanged
    pl = execute(EventStore("sqlite://"), RunInputs(spec_path=spec_path, dataset_dir=clean_dataset))
    assert pl.completed
