"""Fold events into projections (docs/17 §1).

The fold is pure: (events) -> projection, no IO. Projections are always
rebuildable from the log.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from arbiter_engine.events.payloads import EventType
from arbiter_engine.events.store import EventStore
from arbiter_engine.models import Decomposition, Match, ReconException, Record


@dataclass
class RunProjection:
    run_id: str
    started: bool = False
    completed: bool = False
    status: str | None = None
    config_hash: str | None = None
    records: list[Record] = field(default_factory=list)
    matches: list[Match] = field(default_factory=list)
    decompositions: list[Decomposition] = field(default_factory=list)
    exceptions: list[ReconException] = field(default_factory=list)
    scorecard: dict[str, object] | None = None
    quarantined: int = 0
    pii_dropped: int = 0
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def record_count(self) -> int:
        return len(self.records)

    @property
    def matched_record_ids(self) -> set[str]:
        out: set[str] = set()
        for m in self.matches:
            out.update(m.all_ids)
        return out

    def by_source(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for r in self.records:
            out[r.source] = out.get(r.source, 0) + 1
        return out


def fold_run(store: EventStore, run_id: str) -> RunProjection:
    proj = RunProjection(run_id=run_id)
    classified: dict[str, tuple[str, str, float | None]] = {}
    agent_outcomes: dict[str, tuple[str, dict[str, object]]] = {}
    resolutions: dict[str, dict[str, str]] = {}
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
            case EventType.MATCH_CONFIRMED:
                proj.matches.append(Match.model_validate(payload["match"]))
            case EventType.DECOMPOSITION_COMPUTED:
                proj.decompositions.append(Decomposition.model_validate(payload["decomposition"]))
            case EventType.EXCEPTION_OPENED:
                proj.exceptions.append(ReconException.model_validate(payload["exception"]))
            case EventType.EXCEPTION_CLASSIFIED:
                classified[payload["exception_id"]] = (
                    payload["category"],
                    payload["classified_by"],
                    payload.get("confidence"),
                )
            case EventType.AGENT_PROPOSAL_CREATED:
                agent_outcomes[payload["exception_id"]] = ("proposal", payload["proposal"])
            case EventType.AGENT_ESCALATED:
                agent_outcomes[payload["exception_id"]] = ("escalate", payload["escalation"])
            case EventType.RESOLUTION_APPLIED:
                resolutions[payload["exception_id"]] = {
                    "action": payload["action"],
                    "detail": payload.get("detail", ""),
                    "actor": payload["actor"],
                }
                if payload.get("category"):
                    resolutions[payload["exception_id"]]["category"] = payload["category"]
            case EventType.SCORECARD_COMPUTED:
                proj.scorecard = payload["scorecard"]
            case EventType.RUN_COMPLETED:
                proj.completed = True
                proj.status = payload["status"]
                proj.counts = payload["counts"]
            case _:
                pass

    if classified or agent_outcomes or resolutions:
        rebuilt: list[ReconException] = []
        for e in proj.exceptions:
            update: dict[str, object] = {}
            if e.id in classified:
                update["category"] = classified[e.id][0]
                update["classified_by"] = classified[e.id][1]
                update["confidence"] = classified[e.id][2]
            if e.id in agent_outcomes:
                kind, payload = agent_outcomes[e.id]
                if kind == "proposal":
                    update["agent_proposal"] = payload
                    update["status"] = "proposed"
                else:
                    update["agent_escalation"] = payload
                    update["status"] = "escalated"
            if e.id in resolutions:
                update["resolution"] = resolutions[e.id]
                update["status"] = (
                    "wont_fix" if resolutions[e.id]["action"] == "wont_fix" else "resolved"
                )
                if resolutions[e.id].get("category"):
                    update["category"] = resolutions[e.id]["category"]
                    update["classified_by"] = "human:" + resolutions[e.id]["actor"]
            rebuilt.append(e.model_copy(update=update) if update else e)
        proj.exceptions = rebuilt

    proj.records.sort(key=lambda r: r.id)
    proj.matches.sort(key=lambda m: m.id)
    proj.decompositions.sort(key=lambda d: d.group_id)
    proj.exceptions.sort(key=lambda e: (-abs(e.amount_impact_minor), e.id))
    return proj
