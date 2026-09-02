from pathlib import Path

from arbiter_engine.events.store import EventStore
from arbiter_engine.memo import render_memo
from arbiter_engine.run import RunInputs, execute


def test_memo_renders_a_self_contained_document(adversarial_dataset: Path, spec_path: Path):
    store = EventStore("sqlite://")
    proj = execute(
        store, RunInputs(spec_path=spec_path, dataset_dir=adversarial_dataset, no_ai=True)
    )
    v = store.verify(proj.run_id)

    html = render_memo(
        proj,
        spec_name="razorpay-settlement",
        period=("2026-08-01", "2026-08-31"),
        terminal_hash=v["terminal_hash"],
    )
    assert html.startswith("<!doctype html>")
    assert "Reconciliation Close Memo" in html
    assert "Settlement decomposition" in html
    assert "Exception register" in html
    # the audit hash is embedded so `arbiter verify` can confirm the memo
    assert v["terminal_hash"] in html
    assert proj.run_id in html
    # no external resources — a memo must open offline
    assert "http://" not in html and "https://" not in html


def test_memo_lists_every_exception(adversarial_dataset: Path, spec_path: Path):
    store = EventStore("sqlite://")
    proj = execute(
        store, RunInputs(spec_path=spec_path, dataset_dir=adversarial_dataset, no_ai=True)
    )
    html = render_memo(
        proj, spec_name="s", period=None, terminal_hash=store.verify(proj.run_id)["terminal_hash"]
    )
    for e in proj.exceptions:
        assert e.category is None or e.category in html
