import csv
import json
from pathlib import Path

from arbiter_datagen.generate import generate_dataset


def _rows(p: Path) -> list[dict[str, str]]:
    with p.open() as fh:
        return list(csv.DictReader(fh))


def test_generation_is_deterministic(tmp_path: Path):
    a, b = tmp_path / "a", tmp_path / "b"
    m1 = generate_dataset(scenario="d2c", records=50, seed=7, out_dir=a)
    m2 = generate_dataset(scenario="d2c", records=50, seed=7, out_dir=b)
    assert m1["dataset_hash"] == m2["dataset_hash"]
    assert (a / "razorpay_recon.csv").read_bytes() == (b / "razorpay_recon.csv").read_bytes()


def _paise(rupee_str: str) -> int:
    return int(round(float(rupee_str) * 100))


def test_settlement_identity_holds_for_every_batch(tmp_path: Path):
    generate_dataset(scenario="d2c", records=120, seed=42, out_dir=tmp_path)
    recon = _rows(tmp_path / "razorpay_recon.csv")
    bank = {
        r["narration"].split("UTR ")[-1]: _paise(r["amount"]) for r in _rows(tmp_path / "bank.csv")
    }
    gt = json.loads((tmp_path / "ground_truth.json").read_text())

    by_utr: dict[str, int] = {}
    for r in recon:
        net = int(r["credit"]) - int(r["debit"]) - int(r["fee"]) - int(r["tax"])
        by_utr[r["settlement_utr"]] = by_utr.get(r["settlement_utr"], 0) + net

    for utr, expected in by_utr.items():
        assert bank[utr] == expected, f"identity broke for {utr}"

    for m in gt["true_matches"]:
        assert m["expected_net_minor"] == bank[m["settlement_utr"]]


def test_scenarios_and_ground_truth_shape(tmp_path: Path):
    for i, sc in enumerate(("d2c", "marketplace", "saas")):
        out = tmp_path / sc
        m = generate_dataset(scenario=sc, records=40, seed=i, out_dir=out)
        assert m["records"] == 40
        gt = json.loads((out / "ground_truth.json").read_text())
        assert gt["true_matches"]
        assert gt["anomalies"] == []  # M0: clean batches only
