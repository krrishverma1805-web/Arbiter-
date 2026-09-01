"""Fold events into projections (docs/17 §1).

M0 projects only `records` and a run summary. Later milestones fold MATCH_*,
EXCEPTION_*, etc. The fold is pure: (events) -> projection, no IO.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from arbiter_engine.events.payloads import EventType
from arbiter_engine.events.store import EventStore
from arbiter_engine.models import Record


@dataclass
class RunProjection:
    run_id: str
    started: bool = False
    completed: bool = False
    status: str | None = None
    config_hash: str | None = None
    records: list[Record] = field(default_factory=list)
    quarantined: int = 0
    pii_dropped: int = 0
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def record_count(self) -> int:
        return len(self.records)

    def by_source(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for r in self.records:
            out[r.source] = out.get(r.source, 0) + 1
        return out


def fold_run(store: EventStore, run_id: str) -> RunProjection:
    proj = RunProjection(run_id=run_id)
    for etype, payload in store.iter_payloads(run_id):
        match etype:
            case EventType.RUN_STARTED:
                proj.started = True
                proj.config_hash = payload["config_hash"]
            case EventType.RECORD_INGESTED:
                proj.records.append(Record.model_validate(payload["record"]))
            case EventType.ROW_QUARANTINED:
                proj.quarantined += 1
            case EventType.PII_DROPPED:
                proj.pii_dropped += 1
            case EventType.RUN_COMPLETED:
                proj.completed = True
                proj.status = payload["status"]
                proj.counts = payload["counts"]
            case _:
                pass
    # records are deterministically ordered by id for stable downstream folds
    proj.records.sort(key=lambda r: r.id)
    return proj
