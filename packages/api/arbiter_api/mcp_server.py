"""An MCP server exposing Arbiter's **read-only** reconciliation capabilities
(docs/28 §3 item 16).

Other agents — a controller's own assistant, a CFO copilot — can call
reconciliation as a capability: "what is the cash position of run X", "show me
the evidence behind this settlement", "has this counterparty misbehaved
before". Every tool here is a projection read; none of them mutates a match, a
record, money, or the event log. The same money-safety backstop as the
investigation agent's own tools (`arbiter_engine.agent.tools`).

Run it over stdio:  `arbiter-api mcp`   (needs the `arbiter-api[mcp]` extra).
Tenant scope comes from `ARBITER_MCP_ORG` (default `local`).
"""

from __future__ import annotations

import os
from typing import Any

from arbiter_engine.cash import cash_position
from arbiter_engine.events.fold import fold_run
from arbiter_engine.money import format_minor

from arbiter_api.deps import get_store

_ORG = os.environ.get("ARBITER_MCP_ORG", "local")


def _store() -> Any:
    return get_store(_ORG)


def _snapshot(run_id: str) -> Any:
    from arbiter_engine.agent.tools import RunSnapshot

    proj = fold_run(_store(), run_id)
    if not proj.started:
        raise ValueError(f"no such run: {run_id}")
    return proj, RunSnapshot.from_projection(proj)


def build_server() -> Any:
    """Construct the FastMCP server. Imported lazily so the module loads (for
    tests / `--help`) even when the `mcp` extra is not installed."""
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("arbiter", instructions=__doc__)

    @mcp.tool()
    def list_runs() -> dict[str, Any]:
        """List the reconciliation run ids visible to this tenant."""
        return {"org": _ORG, "runs": _store().runs()}

    @mcp.tool()
    def run_summary(run_id: str) -> dict[str, Any]:
        """Counts, completion status and the audit terminal hash for a run."""
        proj = fold_run(_store(), run_id)
        if not proj.started:
            raise ValueError(f"no such run: {run_id}")
        v = _store().verify(run_id)
        return {
            "run_id": run_id,
            "completed": proj.completed,
            "records": proj.record_count,
            "matches": len(proj.matches),
            "exceptions": len(proj.exceptions),
            "chain_intact": v["intact"],
            "terminal_hash": v["terminal_hash"],
        }

    @mcp.tool()
    def verify_run(run_id: str) -> dict[str, Any]:
        """Recompute the hash chain for a run and report whether it is intact."""
        return dict(_store().verify(run_id))

    @mcp.tool()
    def cash_position_for(run_id: str) -> dict[str, Any]:
        """The deterministic 4-bucket cash position (confirmed / in-transit /
        held / unexplained) for a run — always reconciles to net expected."""
        proj, _ = _snapshot(run_id)
        cp = cash_position(proj)
        return {
            "net_expected": format_minor(cp.net_expected_minor),
            "confirmed": format_minor(cp.confirmed_minor),
            "in_transit": format_minor(cp.in_transit_minor),
            "held": format_minor(cp.held_minor),
            "unexplained": format_minor(cp.unexplained_minor),
            "reconciling_delta": format_minor(cp.reconciling_delta_minor),
        }

    @mcp.tool()
    def query_evidence(
        run_id: str,
        source: str = "any",
        external_id: str | None = None,
        amount_minor_low: int | None = None,
        amount_minor_high: int | None = None,
        kind: str | None = None,
    ) -> dict[str, Any]:
        """Search a run's ingested records (bank / gateway rows). Account
        numbers are redacted."""
        from arbiter_engine.agent.tools import Tools

        _, snap = _snapshot(run_id)
        return Tools(snap).query_evidence(
            source=source,
            external_id=external_id,
            amount_minor_low=amount_minor_low,
            amount_minor_high=amount_minor_high,
            kind=kind,
        )

    @mcp.tool()
    def decomposition_detail(run_id: str, settlement_utr: str) -> dict[str, Any]:
        """The settlement-identity breakdown (gross − fees − tax − refunds …)
        for one settlement UTR, with the residual."""
        from arbiter_engine.agent.tools import Tools

        _, snap = _snapshot(run_id)
        return Tools(snap).decomposition_detail(settlement_utr=settlement_utr)

    @mcp.tool()
    def list_exceptions(run_id: str, limit: int = 25) -> dict[str, Any]:
        """Open exceptions for a run, ranked by absolute money impact."""
        proj, _ = _snapshot(run_id)
        rows = sorted(proj.exceptions, key=lambda e: abs(e.amount_impact_minor), reverse=True)[
            : max(1, limit)
        ]
        return {
            "exceptions": [
                {
                    "id": e.id,
                    "category": e.category,
                    "impact": format_minor(e.amount_impact_minor),
                    "record_ids": list(e.record_ids),
                    "status": e.status,
                }
                for e in rows
            ]
        }

    return mcp


def main() -> None:
    build_server().run()
