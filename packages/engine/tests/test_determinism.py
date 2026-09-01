"""The determinism guarantee (docs/04 P2, docs/16 §9, docs/25 §2).

Two runs over the same dataset + spec must produce an identical event hash chain.
This test is the anti-cherry-pick guarantee and fails CI loudly if it breaks.
"""

from pathlib import Path

from arbiter_engine.events.store import EventStore
from arbiter_engine.replay import replay
from arbiter_engine.run import RunInputs, execute


def _terminal_hash(dataset: Path, spec: Path) -> str:
    store = EventStore("sqlite://")
    proj = execute(store, RunInputs(spec_path=spec, dataset_dir=dataset))
    return store.verify(proj.run_id)["terminal_hash"]


def test_two_runs_produce_identical_hash_chains(clean_dataset: Path, spec_path: Path):
    h1 = _terminal_hash(clean_dataset, spec_path)
    h2 = _terminal_hash(clean_dataset, spec_path)
    assert h1 == h2


def test_run_id_is_deterministic_from_config(clean_dataset: Path, spec_path: Path):
    s1 = EventStore("sqlite://")
    s2 = EventStore("sqlite://")
    r1 = execute(s1, RunInputs(spec_path=spec_path, dataset_dir=clean_dataset))
    r2 = execute(s2, RunInputs(spec_path=spec_path, dataset_dir=clean_dataset))
    assert r1.run_id == r2.run_id


def test_replay_reproduces_the_run(clean_dataset: Path, spec_path: Path):
    store = EventStore("sqlite://")
    proj = execute(store, RunInputs(spec_path=spec_path, dataset_dir=clean_dataset))
    res = replay(store, proj.run_id)
    assert res.ok
    assert res.projection.record_count == proj.record_count
    assert res.terminal_hash == store.verify(proj.run_id)["terminal_hash"]


def test_rerun_is_idempotent(clean_dataset: Path, spec_path: Path):
    store = EventStore("sqlite://")
    a = execute(store, RunInputs(spec_path=spec_path, dataset_dir=clean_dataset))
    n_events = store.verify(a.run_id)["events"]
    b = execute(store, RunInputs(spec_path=spec_path, dataset_dir=clean_dataset))
    assert b.run_id == a.run_id
    assert store.verify(b.run_id)["events"] == n_events  # no duplicate events appended
