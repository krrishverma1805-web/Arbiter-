import json
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
        "run_id",
        "spec",
        "dataset",
        "matching",
        "exceptions",
        "throughput",
        "determinism",
        "agent",
    }


def test_scorecard_is_serializable(adversarial_dataset: Path, spec_path: Path):
    import json

    card = _score(adversarial_dataset, spec_path)
    json.dumps(card.to_dict())  # must not raise


def test_agent_scorecard_reads_grounding(adversarial_dataset: Path, spec_path: Path):
    """A proposal event carrying a grounding block feeds grounded_rate + the
    confidence-calibration ECE (docs/28 §1.3)."""
    store = EventStore("sqlite://")
    proj = execute(store, RunInputs(spec_path=spec_path, dataset_dir=adversarial_dataset))
    exc = proj.exceptions[0]
    agent_events: list[tuple[str, dict]] = [
        (
            "AGENT_INVESTIGATION_STARTED",
            {"exception_id": exc.id, "category_in": "UNEXPLAINED", "model": "claude-opus-5"},
        ),
        (
            "AGENT_PROPOSAL_CREATED",
            {
                "exception_id": exc.id,
                "proposal": {
                    "category": exc.category or "UNEXPLAINED",
                    "confidence": 0.9,
                    "evidence_refs": [{"record_id": exc.record_ids[0], "field": "amount"}],
                },
                "tool_calls": 2,
                "turns": 3,
                "tokens_in": 1000,
                "tokens_out": 400,
                "grounding": {
                    "grounded": True,
                    "fabricated": [],
                    "grounded_confidence": 0.82,
                },
            },
        ),
    ]
    card = score_run(
        proj,
        adversarial_dataset,
        spec_name="razorpay-settlement",
        wallclock_ms=100,
        replay_hash_match=True,
        agent_events=agent_events,
    )
    a = card.agent
    assert a.enabled and a.proposals == 1
    assert a.grounded_rate == 1.0  # the grounding block said grounded=True
    assert a.hallucination_rate == 0.0  # no fabricated citation

    # a fabricated citation flips hallucination_rate
    agent_events[1][1]["grounding"] = {"grounded": False, "fabricated": ["ghost:1"]}
    card2 = score_run(
        proj,
        adversarial_dataset,
        spec_name="razorpay-settlement",
        wallclock_ms=100,
        replay_hash_match=True,
        agent_events=agent_events,
    )
    assert card2.agent.hallucination_rate == 1.0
    assert card2.agent.grounded_rate == 0.0


def test_scorecard_holds_at_scale(tmp_path: Path, spec_path: Path):
    """The CI gate runs on 800 records; the false-match rate must stay low there
    and the anomaly density must stay realistic (a minority of batches)."""
    from arbiter_datagen.generate import generate_dataset

    ds = tmp_path / "scale"
    generate_dataset(scenario="d2c", records=800, seed=42, out_dir=ds, difficulty="normal")
    card = _score(ds, spec_path)
    assert card.matching.false_match_rate <= 0.015, card.matching.false_match_rate
    assert card.matching.auto_match_rate >= 0.80, card.matching.auto_match_rate

    import json

    gt = json.loads((ds / "ground_truth.json").read_text())
    n_batches = 800 // 6
    assert len(gt["anomalies"]) <= n_batches * 0.25  # anomalies are a minority


def test_hard_difficulty_degrades_visibly(tmp_path: Path):
    from arbiter_datagen.generate import generate_dataset

    normal = tmp_path / "n"
    hard = tmp_path / "h"
    generate_dataset(scenario="d2c", records=400, seed=3, out_dir=normal, difficulty="normal")
    generate_dataset(scenario="d2c", records=400, seed=3, out_dir=hard, difficulty="hard")
    import json

    n_anom = len(json.loads((normal / "ground_truth.json").read_text())["anomalies"])
    h_anom = len(json.loads((hard / "ground_truth.json").read_text())["anomalies"])
    assert h_anom > n_anom


def test_regression_gate_catches_a_drop():
    from arbiter_engine.bench.gate import check_regression

    base = {
        "matching": {"auto_match_rate": 0.93, "false_match_rate": 0.0, "dollar_coverage": 1.0},
        "exceptions": {"category_accuracy": 0.75},
        "agent": {"hallucination_rate": 0.0, "grounded_rate": 1.0},
    }
    assert check_regression(base, base) == []

    worse = json.loads(json.dumps(base))
    worse["matching"]["auto_match_rate"] = 0.80  # −0.13, well past tol
    worse["matching"]["false_match_rate"] = 0.02  # +0.02, past tol
    fails = check_regression(base, worse)
    assert any("auto_match_rate" in f for f in fails)
    assert any("false_match_rate" in f for f in fails)

    # within tolerance → no failure
    ok = json.loads(json.dumps(base))
    ok["matching"]["auto_match_rate"] = 0.92  # −0.01, inside the 0.02 tol
    assert check_regression(base, ok) == []
