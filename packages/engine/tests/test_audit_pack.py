"""`arbiter audit-pack` bundles a re-checkable record of one run."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from arbiter_engine.events.store import EventStore
from arbiter_engine.run import RunInputs, execute
from typer.testing import CliRunner

from arbiter_engine.cli import app  # isort: skip


def test_audit_pack_is_self_checkable(tmp_path: Path, adversarial_dataset: Path, spec_path: Path):
    db = f"sqlite:///{tmp_path / 'a.db'}"
    store = EventStore(db)
    proj = execute(
        store, RunInputs(spec_path=spec_path, dataset_dir=adversarial_dataset, no_ai=True)
    )
    v = store.verify(proj.run_id)

    out = tmp_path / "pack.zip"
    res = CliRunner().invoke(app, ["audit-pack", proj.run_id, "--out", str(out), "--db", db])
    assert res.exit_code == 0, res.output

    with zipfile.ZipFile(out) as z:
        names = set(z.namelist())
        assert names == {"event-log.jsonl", "close-memo.html", "manifest.json"}
        manifest = json.loads(z.read("manifest.json"))
        log = z.read("event-log.jsonl").decode().strip().splitlines()
        memo = z.read("close-memo.html").decode()

    assert manifest["terminal_hash"] == v["terminal_hash"]
    assert manifest["chain_intact"] is True
    assert len(log) == v["events"]
    # the log carries the chain, so an auditor can recompute it offline
    first = json.loads(log[0])
    assert first["prev_hash"] == "" and "hash" in first
    assert v["terminal_hash"] in memo
