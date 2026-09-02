"""The cash-position readout partitions every settled rupee — it always reconciles."""

from __future__ import annotations

from pathlib import Path

from arbiter_engine.cash import cash_position
from arbiter_engine.events.store import EventStore
from arbiter_engine.run import RunInputs, execute


def test_cash_position_always_reconciles(adversarial_dataset: Path, spec_path: Path):
    store = EventStore("sqlite://")
    proj = execute(
        store, RunInputs(spec_path=spec_path, dataset_dir=adversarial_dataset, no_ai=True)
    )
    cp = cash_position(proj)

    # the four buckets partition the processor-side net exactly
    assert cp.reconciling_delta_minor == 0
    assert cp.accounted_minor == cp.net_expected_minor
    assert cp.confirmed_minor > 0  # a real batch has money that landed
    assert cp.confirmed_count >= 1
    # net = gross − MDR − GST − refunds
    assert cp.net_expected_minor == cp.gross_minor - cp.mdr_minor - cp.gst_minor - cp.refunds_minor


def test_cash_position_is_deterministic(adversarial_dataset: Path, spec_path: Path):
    def _run() -> tuple[int, int, int]:
        store = EventStore("sqlite://")
        proj = execute(
            store, RunInputs(spec_path=spec_path, dataset_dir=adversarial_dataset, no_ai=True)
        )
        cp = cash_position(proj)
        return cp.confirmed_minor, cp.held_minor, cp.unexplained_minor

    assert _run() == _run()
