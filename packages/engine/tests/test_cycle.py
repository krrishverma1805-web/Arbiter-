"""The cycle demo (docs/02 §5.3): a learned rule, carried forward, clears a
settlement-residual shape that the base spec leaves UNEXPLAINED."""

from __future__ import annotations

from pathlib import Path

import yaml
from arbiter_datagen.generate import generate_dataset
from arbiter_engine.learn.cycle import run_cycle_demo


def _batches(root: Path, n: int, records: int = 300) -> list[Path]:
    out = []
    for seed in range(1, n + 1):
        d = root / f"b{seed}"
        generate_dataset(scenario="d2c", records=records, seed=seed, out_dir=d, difficulty="hard")
        out.append(d)
    return out


def test_learned_rule_carries_forward_and_recovers_money(tmp_path: Path, spec_path: Path):
    datasets = _batches(tmp_path, 3)
    result = run_cycle_demo(spec_path, datasets, tmp_path / "work")

    # cycle 1 drafted and merged a rule from the resolved split-settlement residual
    assert result.drafted_rule is not None
    assert result.drafted_rule["classify"] == "SPLIT_SETTLEMENT"
    assert result.spec_version_after == result.spec_version_before + 1

    # the merged rule is real YAML in the carried-forward spec
    after = yaml.safe_load(result.spec_path.read_text())
    assert any(r["id"] == result.drafted_rule["rule_id"] for r in after["rules"])

    # cycle 1: base == learned (the rule isn't merged until after cycle 1 is scored)
    assert result.rows[0].money_recovered_minor == 0
    # later cycles: the learned spec never does worse, and at least one close
    # recovers money the base spec left UNEXPLAINED
    later = result.rows[1:]
    assert all(r.money_recovered_minor >= 0 for r in later)
    assert result.total_recovered_minor > 0


def test_cycle_demo_needs_at_least_two_batches(tmp_path: Path, spec_path: Path):
    datasets = _batches(tmp_path, 1)
    try:
        run_cycle_demo(spec_path, datasets, tmp_path / "work")
    except ValueError as e:
        assert "two" in str(e)
    else:
        raise AssertionError("expected a ValueError for a single batch")
