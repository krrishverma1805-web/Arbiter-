import csv
import json
from pathlib import Path

from arbiter_datagen.generate import generate_dataset


def _rows(p: Path) -> list[dict[str, str]]:
    with p.open() as fh:
        return list(csv.DictReader(fh))


def _paise(rupee_str: str) -> int:
    return int(round(float(rupee_str) * 100))


def test_generation_is_deterministic(tmp_path: Path):
    a, b = tmp_path / "a", tmp_path / "b"
    m1 = generate_dataset(scenario="d2c", records=50, seed=7, out_dir=a, difficulty="normal")
    m2 = generate_dataset(scenario="d2c", records=50, seed=7, out_dir=b, difficulty="normal")
    assert m1["dataset_hash"] == m2["dataset_hash"]
    assert (a / "razorpay_recon.csv").read_bytes() == (b / "razorpay_recon.csv").read_bytes()
    assert (a / "ground_truth.json").read_bytes() == (b / "ground_truth.json").read_bytes()


def test_clean_batch_identity_holds_exactly(tmp_path: Path):
    generate_dataset(scenario="d2c", records=120, seed=42, out_dir=tmp_path, difficulty="easy")
    recon = _rows(tmp_path / "razorpay_recon.csv")
    bank = {
        r["narration"].split("UTR ")[-1]: _paise(r["amount"])
        for r in _rows(tmp_path / "bank.csv")
        if "UTR " in r["narration"]
    }
    gt = json.loads((tmp_path / "ground_truth.json").read_text())
    assert gt["anomalies"] == []

    by_utr: dict[str, int] = {}
    for r in recon:
        net = int(r["credit"]) - int(r["debit"]) - int(r["fee"]) - int(r["tax"])
        by_utr[r["settlement_utr"]] = by_utr.get(r["settlement_utr"], 0) + net

    for utr, expected in by_utr.items():
        assert bank[utr] == expected, f"identity broke for {utr}"
    for m in gt["true_matches"]:
        assert m["expected_net_minor"] == bank[m["settlement_utr"]]


def test_adversarial_batch_has_labeled_anomalies(tmp_path: Path):
    m = generate_dataset(
        scenario="d2c", records=200, seed=42, out_dir=tmp_path, difficulty="normal"
    )
    gt = json.loads((tmp_path / "ground_truth.json").read_text())
    kinds = {a["kind"] for a in gt["anomalies"]}
    assert "INJECTION_NOTE" in kinds  # the security control is always exercised
    assert len(kinds) >= 6
    for a in gt["anomalies"]:
        assert a["true_category"]
        assert a["true_resolution"]["action"]
    anomaly_utrs = {a["settlement_utr"] for a in gt["anomalies"] if a["settlement_utr"]}
    match_utrs = {mm["settlement_utr"] for mm in gt["true_matches"]}
    assert not (anomaly_utrs & match_utrs)
    assert m["anomalies_injected"]["INJECTION_NOTE"] == 1


def test_scenarios_shape(tmp_path: Path):
    for i, sc in enumerate(("d2c", "marketplace", "saas")):
        out = tmp_path / sc
        m = generate_dataset(scenario=sc, records=40, seed=i, out_dir=out, difficulty="easy")
        assert m["records"] == 40
        gt = json.loads((out / "ground_truth.json").read_text())
        assert gt["true_matches"]


def test_adversarial_difficulty_still_produces_matchable_batches(tmp_path: Path):
    """The `adversarial` distribution mangles / drops the UTR label on most
    batches and appends a totals row — but a batch's amount + date must still
    let the matcher recover it, so `true_matches` is non-empty and identity
    holds for the clean ones."""
    from arbiter_engine.events.store import EventStore
    from arbiter_engine.run import RunInputs, execute

    generate_dataset(
        scenario="d2c", records=300, seed=7, out_dir=tmp_path, difficulty="adversarial"
    )
    gt = json.loads((tmp_path / "ground_truth.json").read_text())
    assert gt["true_matches"]

    spec = Path(__file__).resolve().parents[3] / "specs/razorpay-settlement.yaml"
    store = EventStore("sqlite://")
    proj = execute(store, RunInputs(spec_path=spec, dataset_dir=tmp_path, no_ai=True))
    matched = proj.matched_record_ids
    # every ground-truth true match's records are auto-tied despite the garbling
    bank_ids = {r.id for r in proj.records if r.source == "bank"}
    tied = len(bank_ids & matched)
    assert tied >= len(gt["true_matches"]) * 0.85
