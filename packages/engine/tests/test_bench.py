from pathlib import Path

from arbiter_engine.bench import score_run
from arbiter_engine.events.store import EventStore
from arbiter_engine.run import RunInputs, execute


def _score(dataset: Path, spec: Path):
    store = EventStore("sqlite://")
    proj = execute(store, RunInputs(spec_path=spec, dataset_dir=dataset))
    return score_run(
        proj, dataset, spec_name="razorpay-settlement", wallclock_ms=100, replay_hash_match=True
    )


def test_clean_dataset_scores_perfectly(clean_dataset: Path, spec_path: Path):
    card = _score(clean_dataset, spec_path)
    assert card.matching.auto_match_rate == 1.0
    assert card.matching.false_match_rate == 0.0
    assert card.matching.dollar_coverage == 1.0
    assert card.exceptions.total == 0
    assert card.determinism["replay_hash_match"] is True


def test_adversarial_scorecard_is_honest(adversarial_dataset: Path, spec_path: Path):
    card = _score(adversarial_dataset, spec_path)
    m = card.matching
    # a real, sub-perfect but strong deterministic baseline
    assert 0.7 <= m.auto_match_rate <= 1.0
    assert m.precision >= 0.8
    assert m.false_match_rate <= 0.15
    assert card.exceptions.total > 0
    assert card.exceptions.detected_anomalies >= card.exceptions.total_anomalies * 0.6
    assert 0.0 <= card.exceptions.category_accuracy <= 1.0
    d = card.to_dict()
    assert set(d) == {
        "run_id", "spec", "dataset", "matching", "exceptions", "throughput", "determinism", "ai"
    }
    assert d["ai"]["enabled"] is False  # agent lands in M3


def test_scorecard_is_serializable(adversarial_dataset: Path, spec_path: Path):
    import json

    card = _score(adversarial_dataset, spec_path)
    json.dumps(card.to_dict())  # must not raise
