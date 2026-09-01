"""Event type vocabulary and payload models (docs/17 §2.1).

M0 implements the ingestion + run-lifecycle subset. Later milestones add
MATCH_*, DECOMPOSITION_COMPUTED, EXCEPTION_*, AGENT_*, SCORECARD_COMPUTED, etc.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel

from arbiter_engine.models import Decomposition, Match, ReconException, Record


class EventType(StrEnum):
    RUN_STARTED = "RUN_STARTED"
    SOURCE_INGESTED = "SOURCE_INGESTED"
    ROW_QUARANTINED = "ROW_QUARANTINED"
    PII_DROPPED = "PII_DROPPED"
    RECORD_INGESTED = "RECORD_INGESTED"
    MATCH_CONFIRMED = "MATCH_CONFIRMED"
    DECOMPOSITION_COMPUTED = "DECOMPOSITION_COMPUTED"
    EXCEPTION_OPENED = "EXCEPTION_OPENED"
    EXCEPTION_CLASSIFIED = "EXCEPTION_CLASSIFIED"
    SCORECARD_COMPUTED = "SCORECARD_COMPUTED"
    RUN_COMPLETED = "RUN_COMPLETED"
    RUN_PURGED = "RUN_PURGED"


class RunStarted(BaseModel):
    spec_name: str
    spec_version: int
    spec_hash: str
    dataset_hash: str
    seed: int | None
    config_hash: str
    no_ai: bool
    engine_version: str


class SourceIngested(BaseModel):
    source: str
    format: str
    profile: str | None
    rows_in: int
    rows_ok: int
    rows_quarantined: int
    file_hash: str


class RowQuarantined(BaseModel):
    source: str
    source_row_id: str
    reason: str
    raw: dict[str, str]


class PiiDropped(BaseModel):
    source: str
    source_row_id: str
    field: str
    kind: str  # e.g. "card_number"


class RecordIngested(BaseModel):
    record: Record


class MatchConfirmed(BaseModel):
    match: Match


class DecompositionComputed(BaseModel):
    decomposition: Decomposition


class ExceptionOpened(BaseModel):
    exception: ReconException


class ExceptionClassified(BaseModel):
    exception_id: str
    category: str
    classified_by: str
    confidence: float | None = None


class ScorecardComputed(BaseModel):
    scorecard: dict[str, Any]


class RunCompleted(BaseModel):
    status: str  # "completed" | "failed"
    counts: dict[str, int]
    # timing lives in Event.meta, not here — it must not affect the hash chain (docs/12 §4)


class RunPurged(BaseModel):
    reason: str
    by: str


EVENT_PAYLOADS: dict[EventType, type[BaseModel]] = {
    EventType.RUN_STARTED: RunStarted,
    EventType.SOURCE_INGESTED: SourceIngested,
    EventType.ROW_QUARANTINED: RowQuarantined,
    EventType.PII_DROPPED: PiiDropped,
    EventType.RECORD_INGESTED: RecordIngested,
    EventType.MATCH_CONFIRMED: MatchConfirmed,
    EventType.DECOMPOSITION_COMPUTED: DecompositionComputed,
    EventType.EXCEPTION_OPENED: ExceptionOpened,
    EventType.EXCEPTION_CLASSIFIED: ExceptionClassified,
    EventType.SCORECARD_COMPUTED: ScorecardComputed,
    EventType.RUN_COMPLETED: RunCompleted,
    EventType.RUN_PURGED: RunPurged,
}


def validate_payload(event_type: EventType, payload: dict[str, Any]) -> BaseModel:
    model = EVENT_PAYLOADS.get(event_type)
    if model is None:
        raise ValueError(f"unknown event type: {event_type}")
    return model.model_validate(payload)
