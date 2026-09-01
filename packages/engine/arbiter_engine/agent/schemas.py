"""The strict output contract for the investigation agent (docs/19 §4).

The agent's terminal turn produces EITHER a Proposal OR an Escalate. Both are
validated against these models; a malformed output is discarded and the
exception stays UNEXPLAINED (logged).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# Kept in sync with specs/*.yaml `taxonomy:` — the agent cannot invent a category.
PROPOSAL_CATEGORIES = (
    "FEE_DEDUCTION",
    "TAX_DEDUCTION",
    "ROUNDING",
    "PARTIAL_PAYMENT",
    "TIMING",
    "DUPLICATE",
    "CHARGEBACK",
    "ADJUSTMENT",
    "FX_DIFFERENCE",
    "MISSING_UTR",
    "WRONG_ACCOUNT",
    "SPLIT_SETTLEMENT",
    "UNEXPLAINED",
)
RESOLUTION_ACTIONS = (
    "accept_variance",
    "attribute_to",
    "carry_forward",
    "flag_overcharge",
    "raise_dispute",
    "void_duplicate_of",
    "request_data",
    "route_to_human",
    "wont_fix",
)


class EvidenceRef(BaseModel):
    model_config = {"extra": "forbid"}
    claim: str
    record_id: str
    field: str


class SuggestedAction(BaseModel):
    model_config = {"extra": "forbid"}
    action: Literal[
        "accept_variance",
        "attribute_to",
        "carry_forward",
        "flag_overcharge",
        "raise_dispute",
        "void_duplicate_of",
        "request_data",
        "route_to_human",
        "wont_fix",
    ]
    detail: str


class DraftRule(BaseModel):
    model_config = {"extra": "forbid"}
    when: str
    classify: str
    resolve: str


class Proposal(BaseModel):
    model_config = {"extra": "forbid"}
    kind: Literal["proposal"] = "proposal"
    exception_id: str = ""
    category: Literal[
        "FEE_DEDUCTION",
        "TAX_DEDUCTION",
        "ROUNDING",
        "PARTIAL_PAYMENT",
        "TIMING",
        "DUPLICATE",
        "CHARGEBACK",
        "ADJUSTMENT",
        "FX_DIFFERENCE",
        "MISSING_UTR",
        "WRONG_ACCOUNT",
        "SPLIT_SETTLEMENT",
        "UNEXPLAINED",
    ]
    confidence: float = Field(ge=0.0, le=1.0)
    explanation: str = Field(max_length=1400)
    evidence_refs: list[EvidenceRef] = Field(min_length=1)
    hypotheses_tested: list[str] = Field(default_factory=list)
    suggested_action: SuggestedAction
    draft_rule: DraftRule | None = None


class Escalate(BaseModel):
    model_config = {"extra": "forbid"}
    kind: Literal["escalate"] = "escalate"
    exception_id: str = ""
    what_i_know: str = Field(max_length=900)
    what_is_missing: str = Field(max_length=500)
    question: str = Field(max_length=350)
    reason: Literal[
        "evidence_exhausted", "contradictory", "budget", "provider_unavailable", "malformed_output"
    ]


AgentOutput = Proposal | Escalate


def output_json_schema() -> dict[str, object]:
    """The JSON schema passed to `output_config.format` (docs/19 §4)."""
    return {
        "type": "json_schema",
        "schema": {
            "type": "object",
            "oneOf": [Proposal.model_json_schema(), Escalate.model_json_schema()],
        },
    }
