"""Resumable runs + idempotency (docs/13 §4, docs/25 §2).

A run interrupted at any stage boundary must resume to the same terminal event
hash as an uninterrupted run.
"""

from pathlib import Path

import pytest
from arbiter_engine.events.payloads import EventType
from arbiter_engine.events.store import EventStore
from arbiter_engine.run import RunInProgress, RunInputs, execute


def _uninterrupted_hash(dataset: Path, spec: Path) -> str:
    store = EventStore("sqlite://")
    proj = execute(store, RunInputs(spec_path=spec, dataset_dir=dataset))
    return store.verify(proj.run_id)["terminal_hash"]


@pytest.mark.parametrize(
    "stop_after",
    [EventType.RUN_STARTED, EventType.SOURCE_INGESTED, EventType.MATCH_CONFIRMED],
)
def test_resume_from_every_stage_boundary(
    adversarial_dataset: Path, spec_path: Path, stop_after: EventType
):
    reference = _uninterrupted_hash(adversarial_dataset, spec_path)

    # a store that raises the moment we try to append the event *after* `stop_after`
    store = EventStore("sqlite://")
    real_append = store.append
    tripped = {"seen_stop": False}

    def flaky_append(run_id, event_type, payload, **kw):  # type: ignore[no-untyped-def]
        if tripped["seen_stop"] and event_type != stop_after:
            raise RuntimeError("simulated crash")
        ev = real_append(run_id, event_type, payload, **kw)
        if event_type == stop_after:
            tripped["seen_stop"] = True
        return ev

    store.append = flaky_append  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="simulated crash"):
        execute(store, RunInputs(spec_path=spec_path, dataset_dir=adversarial_dataset))

    store.append = real_append  # type: ignore[method-assign]
    proj = execute(
        store, RunInputs(spec_path=spec_path, dataset_dir=adversarial_dataset, resume=True)
    )
    assert proj.completed
    assert store.verify(proj.run_id)["terminal_hash"] == reference


def test_run_in_progress_without_resume_raises(adversarial_dataset: Path, spec_path: Path):
    store = EventStore("sqlite://")
    real = store.append

    def stop_after_started(run_id, event_type, payload, **kw):  # type: ignore[no-untyped-def]
        ev = real(run_id, event_type, payload, **kw)
        if event_type == EventType.RUN_STARTED:
            raise RuntimeError("crash")
        return ev

    store.append = stop_after_started  # type: ignore[method-assign]
    with pytest.raises(RuntimeError):
        execute(store, RunInputs(spec_path=spec_path, dataset_dir=adversarial_dataset))
    store.append = real  # type: ignore[method-assign]

    with pytest.raises(RunInProgress):
        execute(store, RunInputs(spec_path=spec_path, dataset_dir=adversarial_dataset))


def test_rerun_discards_and_reproduces(adversarial_dataset: Path, spec_path: Path):
    store = EventStore("sqlite://")
    a = execute(store, RunInputs(spec_path=spec_path, dataset_dir=adversarial_dataset))
    h1 = store.verify(a.run_id)["terminal_hash"]
    b = execute(store, RunInputs(spec_path=spec_path, dataset_dir=adversarial_dataset, rerun=True))
    assert b.run_id == a.run_id
    assert store.verify(b.run_id)["terminal_hash"] == h1
