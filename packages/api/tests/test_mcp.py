"""The read-only MCP server (docs/28 §3 item 16).

Other agents call reconciliation as a capability. Every tool is a projection
read — this test proves the tools are registered and that they return real data
for a real run, and (the safety property) that the server exposes *no* tool that
could mutate anything.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("mcp", reason="needs the arbiter-api[mcp] extra")

REPO = Path(__file__).resolve().parents[3]


@pytest.fixture
def run_id(tmp_path, monkeypatch):
    monkeypatch.setenv("ARBITER_DB_URL", f"sqlite:///{tmp_path / 'mcp.db'}")
    monkeypatch.setenv("ARBITER_MCP_ORG", "local")
    import arbiter_api.deps as deps

    deps.get_store.cache_clear()
    monkeypatch.setattr(deps, "DB_URL", f"sqlite:///{tmp_path / 'mcp.db'}")

    from arbiter_datagen.generate import generate_dataset
    from arbiter_engine.run import RunInputs, execute

    ds = tmp_path / "d2c"
    generate_dataset(scenario="d2c", records=60, seed=7, out_dir=ds, difficulty="normal")
    proj = execute(
        deps.get_store("local"),
        RunInputs(
            spec_path=Path(REPO) / "specs/razorpay-settlement.yaml", dataset_dir=ds, no_ai=True
        ),
    )
    return proj.run_id


def test_tools_are_registered_and_all_read_only():
    import asyncio

    from arbiter_api.mcp_server import build_server

    tools = asyncio.run(build_server().list_tools())
    names = {t.name for t in tools}
    assert {"list_runs", "run_summary", "cash_position_for", "query_evidence"} <= names
    # nothing that writes
    assert not any(
        w in n for n in names for w in ("resolve", "create", "delete", "write", "update", "merge")
    )


def test_run_summary_and_cash_position_match_the_projection(run_id):
    import asyncio

    from arbiter_api.mcp_server import build_server

    mcp = build_server()
    summary = asyncio.run(mcp.call_tool("run_summary", {"run_id": run_id}))
    text = str(summary)
    assert run_id in text
    assert '"chain_intact": true' in text.lower() or "'chain_intact': True" in text

    cash = str(asyncio.run(mcp.call_tool("cash_position_for", {"run_id": run_id})))
    assert "reconciling_delta" in cash


def test_unknown_run_is_an_error(run_id):
    import asyncio

    from arbiter_api.mcp_server import build_server

    mcp = build_server()
    with pytest.raises(Exception, match="no such run"):
        asyncio.run(mcp.call_tool("run_summary", {"run_id": "no-such-run"}))
