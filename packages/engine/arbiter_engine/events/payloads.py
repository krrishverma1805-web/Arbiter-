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
    AGENT_INVESTIGATION_STARTED = "AGENT_INVESTIGATION_STARTED"
    AGENT_INTERACTION = "AGENT_INTERACTION"
    AGENT_PROPOSAL_CREATED = "AGENT_PROPOSAL_CREATED"
    AGENT_ESCALATED = "AGENT_ESCALATED"
    RESOLUTION_APPLIED = "RESOLUTION_APPLIED"
    RULE_DRAFTED = "RULE_DRAFTED"
    RULE_MERGED = "RULE_MERGED"
    SCORECARD_COMPUTED = "SCORECARD_COMPUTED"
    FS_CALIBRATION_FITTED = "FS_CALIBRATION_FITTED"
    FS_MODEL_PROMOTED = "FS_MODEL_PROMOTED"
    FS_MODEL_REJECTED = "FS_MODEL_REJECTED"
    INPUT_DRIFT_DETECTED = "INPUT_DRIFT_DETECTED"
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
    org_id: str = "local"


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


class AgentInvestigationStarted(BaseModel):
    exception_id: str
    category_in: str
    model: str
    prompt_hash: str


class AgentInteraction(BaseModel):
    exception_id: str
    turn: int
    stop_reason: str
    text: str = ""
    tool_calls: list[dict[str, Any]] = []
    structured: dict[str, Any] | None = None
    tokens_in: int = 0
    tokens_out: int = 0


class AgentProposalCreated(BaseModel):
    exception_id: str
    proposal: dict[str, Any]
    tool_calls: int
    turns: int
    tokens_in: int
    tokens_out: int
    grounding: dict[str, Any] | None = None  # evidence-ref resolution + category check


class AgentEscalated(BaseModel):
    exception_id: str
    escalation: dict[str, Any]
    tool_calls: int
    turns: int


class ResolutionApplied(BaseModel):
    exception_id: str
    action: str
    detail: str = ""
    actor: str
    prior_status: str
    source: str = "human"
    category: str | None = None  # a human correction to the classifier's category


class RuleDrafted(BaseModel):
    rule_id: str
    when: str
    classify: str
    resolve: str
    provenance_exception_id: str


class RuleMerged(BaseModel):
    rule_id: str
    spec_version_before: int
    spec_version_after: int
    approved_by: str


class ScorecardComputed(BaseModel):
    scorecard: dict[str, Any]


class FSCalibrationFitted(BaseModel):
    spec_hash: str
    points: list[list[float]]  # isotonic recalibration map [[x, y], ...]
    n_samples: int
    ece_before: float


class FSModelPromoted(BaseModel):
    """A per-tenant Fellegi–Sunter m/u table retrained from this tenant's own
    confirmed matches and promoted because it beat the incumbent on a held-out
    set (docs/28 §3 item 14). The next run over this spec loads it."""

    spec_hash: str
    mu: dict[str, dict[str, list[float]]]  # {field: {level: [m, u]}}
    auc_before: float
    auc_after: float
    n_pairs: int
    trained_by: str


class FSModelRejected(BaseModel):
    """A retrain that did not clear the eval gate — recorded so the decision is
    auditable and the same data isn't retried forever."""

    spec_hash: str
    auc_before: float
    auc_after: float
    n_pairs: int
    reason: str
    trained_by: str


class InputDriftDetected(BaseModel):
    """The shape of this run's input moved away from the tenant's recent runs for
    the same spec (docs/28 §3 item 16) — a new bank format, a counterparty-mix
    shift, a drop in reference coverage. Informational; the run still completes.
    A signal to re-check the matcher / re-run `arbiter retrain`."""

    run_id: str  # the reconciliation run this profile is for
    spec_hash: str
    psi: float  # population-stability index, summed across features
    drifted: list[str]  # feature names past the per-feature threshold
    baseline_runs: int
    profile: dict[str, float]


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
    EventType.AGENT_INVESTIGATION_STARTED: AgentInvestigationStarted,
    EventType.AGENT_INTERACTION: AgentInteraction,
    EventType.AGENT_PROPOSAL_CREATED: AgentProposalCreated,
    EventType.AGENT_ESCALATED: AgentEscalated,
    EventType.RESOLUTION_APPLIED: ResolutionApplied,
    EventType.RULE_DRAFTED: RuleDrafted,
    EventType.RULE_MERGED: RuleMerged,
    EventType.SCORECARD_COMPUTED: ScorecardComputed,
    EventType.FS_CALIBRATION_FITTED: FSCalibrationFitted,
    EventType.FS_MODEL_PROMOTED: FSModelPromoted,
    EventType.FS_MODEL_REJECTED: FSModelRejected,
    EventType.INPUT_DRIFT_DETECTED: InputDriftDetected,
    EventType.RUN_COMPLETED: RunCompleted,
    EventType.RUN_PURGED: RunPurged,
}


def validate_payload(event_type: EventType, payload: dict[str, Any]) -> BaseModel:
    model = EVENT_PAYLOADS.get(event_type)
    if model is None:
        raise ValueError(f"unknown event type: {event_type}")
    return model.model_validate(payload)
