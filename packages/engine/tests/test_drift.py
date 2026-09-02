"""Input-drift detection (docs/28 §3 item 16)."""

from __future__ import annotations

from pathlib import Path

import pytest
from arbiter_engine.events.store import EventStore
from arbiter_engine.learn.drift import _psi, check_drift, feature_profile
from arbiter_engine.run import RunInputs, execute
from arbiter_engine.specs import load_spec, spec_hash

SPEC = Path(__file__).resolve().parents[3] / "specs/razorpay-settlement.yaml"


def test_psi_is_zero_for_identical_and_grows_with_divergence():
    assert _psi(1.0, 1.0) == pytest.approx(0.0, abs=1e-9)
    near = abs(_psi(0.5, 0.55))
    far = abs(_psi(0.5, 0.9))
    assert far > near > 0


def test_profile_reacts_to_a_missing_reference_column():
    from arbiter_engine.models import Record

    with_ref = [
        Record(
            id=f"r{i}",
            run_id="x",
            source="bank",
            kind="credit",
            amount_minor=100 + i,
            reference="UTR",
        )
        for i in range(20)
    ]
    without = [r.model_copy(update={"reference": None}) for r in with_ref]
    assert feature_profile(with_ref)["has_reference_frac"] == 1.0
    assert feature_profile(without)["has_reference_frac"] == 0.0


def test_drift_stays_off_the_reconciliation_chain(tmp_path):
    """The drift event must land on __learn__<org>, never the run's hash chain —
    otherwise a replay in a fresh store would diverge."""
    from arbiter_datagen.generate import generate_dataset

    store = EventStore(f"sqlite:///{tmp_path / 'd.db'}", org_id="acme")
    ds = tmp_path / "ds"
    generate_dataset(scenario="d2c", records=150, seed=3, out_dir=ds, difficulty="normal")
    proj = execute(store, RunInputs(spec_path=SPEC, dataset_dir=ds, no_ai=True))

    run_events = {e.type for e in store.events(proj.run_id)}
    assert "INPUT_DRIFT_DETECTED" not in run_events
    learn_events = [e.type for e in store.events("__learn__acme")]
    assert learn_events.count("INPUT_DRIFT_DETECTED") == 1
    # the run still verifies
    assert store.verify(proj.run_id)["intact"] is True


def test_drift_alerts_when_the_input_shape_moves(tmp_path):
    store = EventStore(f"sqlite:///{tmp_path / 'd2.db'}", org_id="acme")
    sh = spec_hash(load_spec(SPEC))
    from arbiter_engine.models import Record

    def batch(kind: str, ref: bool, k: int) -> list[Record]:
        return [
            Record(
                id=f"{kind}{k}-{i}",
                run_id=f"run{k}",
                source="bank",
                kind=kind,  # type: ignore[arg-type]
                amount_minor=1000 + i,
                reference="R" if ref else None,
            )
            for i in range(40)
        ]

    # three baseline runs of one shape
    for k in range(3):
        assert check_drift(store, f"run{k}", sh, batch("credit", True, k)) is None
    # a run with a very different shape → alert
    hit = check_drift(store, "run_new", sh, batch("payment", False, 9))
    assert hit is not None and hit["drifted"] >= 1
