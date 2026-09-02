"""Per-tenant FS retraining behind an eval gate (docs/28 §3 item 14)."""

from __future__ import annotations

from pathlib import Path

import pytest
from arbiter_engine.events.store import EventStore
from arbiter_engine.learn.retrain import _auc, gather_pairs, retrain
from arbiter_engine.match.fellegi_sunter import FSModel
from arbiter_engine.match.fs_store import load_fs_model
from arbiter_engine.run import RunInputs, execute
from arbiter_engine.specs import load_spec, spec_hash

SPEC = Path(__file__).resolve().parents[3] / "specs/razorpay-settlement.yaml"


@pytest.fixture
def store_with_history(tmp_path):
    """Two runs over the same spec → a real pile of confirmed matches."""
    from arbiter_datagen.generate import generate_dataset

    store = EventStore(f"sqlite:///{tmp_path / 'h.db'}", org_id="acme")
    for seed in (1, 2, 3):
        ds = tmp_path / f"ds{seed}"
        generate_dataset(scenario="d2c", records=500, seed=seed, out_dir=ds, difficulty="normal")
        execute(store, RunInputs(spec_path=SPEC, dataset_dir=ds, no_ai=True))
    return store


def test_auc_separates_a_good_model_from_a_blind_one():
    pos = [{"amount": "exact", "date": "same_day"}] * 20
    neg = [{"amount": "none", "date": "none"}] * 20
    assert _auc(FSModel(), pos, neg) > 0.95
    # a model that ignores every signal scores like a coin flip
    flat = FSModel(mu={f: {lvl: (0.5, 0.5) for lvl in lv} for f, lv in FSModel().mu.items()})
    assert 0.4 < _auc(flat, pos, neg) < 0.6


def test_gather_pairs_finds_positives_and_negatives(store_with_history):
    spec = load_spec(SPEC)
    pos, neg = gather_pairs(store_with_history, spec)
    assert len(pos) >= 40
    assert len(neg) >= 10
    # positives really do look more like matches than the negatives
    assert _auc(FSModel(), pos, neg) > 0.8


def test_retrain_runs_the_gate_and_records_an_auditable_decision(store_with_history):
    spec = load_spec(SPEC)
    res = retrain(store_with_history, spec, trained_by="test")
    assert res.n_pairs > 0
    assert res.reason in {"promoted", "below_gate"}
    # exactly one FS_MODEL_* event landed on the tenant's learn pseudo-run
    events = store_with_history.events("__learn__acme")
    kinds = [e.type for e in events]
    assert kinds.count("FS_MODEL_PROMOTED") + kinds.count("FS_MODEL_REJECTED") == 1

    if res.promoted:
        model = load_fs_model(store_with_history, spec_hash(spec))
        assert model is not None
        # a subsequent run loads it and still produces a verifiable chain
        proj = execute(
            store_with_history,
            RunInputs(spec_path=SPEC, dataset_dir=_fresh_ds(store_with_history), no_ai=True),
        )
        assert store_with_history.verify(proj.run_id)["intact"] is True


def test_insufficient_history_is_a_clean_no_op(tmp_path):
    store = EventStore(f"sqlite:///{tmp_path / 'e.db'}", org_id="new")
    res = retrain(store, load_spec(SPEC), trained_by="test")
    assert res.promoted is False
    assert res.reason == "insufficient_data"
    assert store.events("__learn__new") == []


def _fresh_ds(store):
    from arbiter_datagen.generate import generate_dataset

    d = Path(store.engine.url.database).parent / "ds_after"
    if not d.exists():
        generate_dataset(scenario="d2c", records=300, seed=99, out_dir=d, difficulty="normal")
    return d
