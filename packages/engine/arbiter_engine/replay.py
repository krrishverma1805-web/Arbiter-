"""Deterministic replay (docs/12 §4, docs/adr/0002).

A completed run is reproducible from its event log. For M0 (no agent yet),
replay = rebuild the projection by folding the recorded events and confirm the
hash chain is intact and the terminal hash matches.

From M3, replay also re-plays recorded AGENT_INTERACTION events instead of
calling the API.
"""

from __future__ import annotations

from dataclasses import dataclass

from arbiter_engine.events.fold import RunProjection, fold_run
from arbiter_engine.events.store import EventStore


@dataclass
class ReplayResult:
    run_id: str
    intact: bool
    events: int
    terminal_hash: str
    projection: RunProjection

    @property
    def ok(self) -> bool:
        return self.intact and self.projection.completed


def replay(store: EventStore, run_id: str) -> ReplayResult:
    verify = store.verify(run_id)  # raises ChainBroken on tamper
    proj = fold_run(store, run_id)
    return ReplayResult(
        run_id=run_id,
        intact=verify["intact"],
        events=verify["events"],
        terminal_hash=verify["terminal_hash"],
        projection=proj,
    )
