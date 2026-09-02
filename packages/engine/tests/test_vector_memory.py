"""pgvector-backed resolution memory (docs/28 §3 item 13)."""

from __future__ import annotations

from collections import Counter

from arbiter_engine.agent.vector_memory import VectorResolutionMemory, hash_embed
from arbiter_engine.events.store import EventStore
from arbiter_engine.models import ReconException, Record


def test_hash_embed_is_deterministic_and_unit_norm():
    bag = Counter({"cat:ROUNDING": 3, "src:bank": 1, "kind:credit": 1})
    a, b = hash_embed(bag), hash_embed(bag)
    assert a == b
    assert abs(sum(x * x for x in a) ** 0.5 - 1.0) < 1e-9
    # a different bag → a different vector
    assert hash_embed(Counter({"cat:DUPLICATE": 3})) != a


def _resolved_exc(store: EventStore, run_id: str, cat: str, eid: str) -> None:
    from arbiter_engine.events.payloads import EventType

    rec = Record(
        id=f"{eid}-r",
        run_id=run_id,
        source="bank",
        kind="credit",
        amount_minor=500_00,
        org_id="acme",
    )
    exc = ReconException(
        id=eid,
        run_id=run_id,
        category=cat,
        classified_by="rule",
        amount_impact_minor=40,
        record_ids=[rec.id],
    )
    store.append(
        run_id,
        EventType.RUN_STARTED,
        {
            "spec_name": "s",
            "spec_version": 1,
            "spec_hash": "h",
            "dataset_hash": "d",
            "seed": None,
            "config_hash": "c",
            "no_ai": True,
            "engine_version": "0",
        },
    )
    store.append(run_id, EventType.RECORD_INGESTED, {"record": rec.model_dump(mode="json")})
    store.append(run_id, EventType.EXCEPTION_OPENED, {"exception": exc.model_dump(mode="json")})
    store.append(
        run_id,
        EventType.RESOLUTION_APPLIED,
        {
            "exception_id": eid,
            "action": "accept_variance",
            "detail": "",
            "actor": "h",
            "prior_status": "open",
            "category": cat,
        },
    )
    store.append(run_id, EventType.RUN_COMPLETED, {"status": "completed", "counts": {}})


def test_index_persists_and_recall_finds_the_similar_resolution(tmp_path):
    url = f"sqlite:///{tmp_path / 'v.db'}"
    store = EventStore(url, org_id="acme")
    _resolved_exc(store, "run-a", "ROUNDING", "e-round")
    _resolved_exc(store, "run-b", "DUPLICATE", "e-dup")

    mem = VectorResolutionMemory.from_store(store, org_id="acme")
    assert len(mem) == 2

    # a fresh instance must reuse the persisted vectors, not rebuild blindly
    mem2 = VectorResolutionMemory.from_store(store, org_id="acme")
    assert len(mem2) == 2

    query = ReconException(
        id="q",
        run_id="run-c",
        category="ROUNDING",
        classified_by="rule",
        amount_impact_minor=45,
        record_ids=["qr"],
    )
    qrec = Record(id="qr", run_id="run-c", source="bank", kind="credit", amount_minor=501_00)
    hits = mem2.recall(query, [qrec], k=2, floor=0.0)
    assert hits and hits[0].category == "ROUNDING"
    assert hits[0].resolution["action"] == "accept_variance"


def test_recall_matches_the_feature_bag_it_was_built_from(tmp_path):
    store = EventStore(f"sqlite:///{tmp_path / 'w.db'}", org_id="acme")
    _resolved_exc(store, "run-a", "TIMING", "e1")
    mem = VectorResolutionMemory.from_store(store, org_id="acme")

    exc = ReconException(
        id="e1",
        run_id="run-a",
        category="TIMING",
        classified_by="rule",
        amount_impact_minor=40,
        record_ids=["x"],
    )
    rec = Record(id="x", run_id="run-a", source="bank", kind="credit", amount_minor=500_00)
    # querying with the exact shape it stored → near-perfect cosine
    hit = mem.recall(exc, [rec], k=1, floor=0.0)[0]
    assert hit.similarity > 0.99
