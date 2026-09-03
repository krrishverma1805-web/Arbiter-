"""Attack Arbiter regression gate (spec §29).

Runs the full deterministic adversarial suite against the seed dataset and
asserts the safety invariant: the matcher never asserts a confident clean tie
over a tampered record, and no rupees silently disappear.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from arbiter_engine.attack import ATTACKS, run_all

_SPEC = Path("specs/razorpay-settlement.yaml")
_DATASET = Path("datasets/seed")


@pytest.mark.skipif(
    not (_SPEC.exists() and (_DATASET / "manifest.json").exists()),
    reason="seed dataset not generated",
)
def test_no_attack_is_unsafe_and_nothing_goes_unaccounted() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        results = run_all(_SPEC, _DATASET, Path(tmp))

    assert len(results) == len(ATTACKS)
    unsafe = [r.scenario for r in results if r.verdict == "UNSAFE"]
    missed = [r.scenario for r in results if r.verdict == "MISSED"]
    leaked = [
        (r.scenario, r.rupees_unaccounted_minor)
        for r in results
        if r.rupees_unaccounted_minor > 200
    ]

    assert not unsafe, f"matcher asserted a false confident clean tie: {unsafe}"
    assert not missed, f"attack produced no detectable signal: {missed}"
    assert not leaked, f"rupees unaccounted after attack: {leaked}"
