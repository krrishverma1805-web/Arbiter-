"""Resolution memory: the agent recalls how a similar exception was resolved
before, across runs (docs/28 §1.3)."""

from __future__ import annotations

from pathlib import Path

from arbiter_datagen.generate import generate_dataset
from arbiter_engine.agent.memory import ResolutionMemory, features
from arbiter_engine.agent.tools import RunSnapshot, Tools
from arbiter_engine.events.payloads import EventType
from arbiter_engine.events.store import EventStore
from arbiter_engine.models import Exception_
from arbiter_engine.run import RunInputs, execute


def _resolve_first_unexplained(store: EventStore, proj, category: str, action: str) -> str:
    exc = next(e for e in proj.exceptions if e.category in (None, "UNEXPLAINED"))
    store.append(
        proj.run_id,
        EventType.RESOLUTION_APPLIED,
        {
            "exception_id": exc.id,
            "action": action,
            "detail": "",
            "actor": "tester",
            "prior_status": exc.status,
            "category": category,
        },
    )
    return exc.id


def test_memory_recalls_a_prior_resolution(tmp_path: Path, spec_path: Path):
    d1 = tmp_path / "b1"
    d2 = tmp_path / "b2"
    generate_dataset(scenario="d2c", records=260, seed=1, out_dir=d1, difficulty="hard")
    generate_dataset(scenario="d2c", records=260, seed=2, out_dir=d2, difficulty="hard")

    store = EventStore("sqlite://")
    p1 = execute(store, RunInputs(spec_path=spec_path, dataset_dir=d1, no_ai=True))
    _resolve_first_unexplained(store, p1, "SPLIT_SETTLEMENT", "accept_variance")

    p2 = execute(store, RunInputs(spec_path=spec_path, dataset_dir=d2, no_ai=True))
    mem = ResolutionMemory.from_store(store, exclude_run_id=p2.run_id)
    assert len(mem) >= 1

    target = next(e for e in p2.exceptions if e.category in (None, "UNEXPLAINED"))
    recs = [r for r in p2.records if r.id in set(target.record_ids)]
    hits = mem.recall(target, recs, k=5)
    assert hits, "expected at least one similar prior resolution"
    assert hits[0].similarity > 0.2
    assert hits[0].resolution.get("action") == "accept_variance"

    # the resolved run itself is excluded — no self-recall
    assert all(h.run_id != p2.run_id for h in hits)


def test_similar_exceptions_tool_uses_the_memory(adversarial_dataset: Path, spec_path: Path):
    store = EventStore("sqlite://")
    proj = execute(
        store, RunInputs(spec_path=spec_path, dataset_dir=adversarial_dataset, no_ai=True)
    )
    _resolve_first_unexplained(store, proj, "TIMING", "carry_forward")

    snap = RunSnapshot.from_projection(proj)
    snap.resolution_memory = ResolutionMemory.from_store(store, exclude_run_id="none")
    exc = next(e for e in proj.exceptions if e.category in (None, "UNEXPLAINED"))
    out = Tools(snap, exc).similar_exceptions()
    assert out["method"] == "semantic"


def _exc(cat: str, impact: int, ids: list[str]) -> Exception_:
    return Exception_(
        id=cat[:2].lower(),
        run_id="r",
        category=cat,
        classified_by="rule",
        amount_impact_minor=impact,
        record_ids=ids,
    )


def test_features_are_stable_and_shape_aware():
    a = _exc("ROUNDING", 42, ["x"])
    b = _exc("ROUNDING", 48, ["y"])
    c = _exc("CHARGEBACK", 500000, ["z"])
    fa, fb, fc = features(a, []), features(b, []), features(c, [])
    assert fa == features(a, [])  # deterministic
    # a and b share category + residual band; c shares neither
    assert len(set(fa) & set(fb)) > len(set(fa) & set(fc))
