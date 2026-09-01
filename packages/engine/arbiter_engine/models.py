"""Canonical domain models (docs/17 §3).

`Record` is the normalized shape every source is mapped into. It deliberately
separates:
  - matching fields (amount, dates, reference, external_ids) — used in logic
  - `untrusted` (description/notes/narration) — NEVER used in logic, only ever
    shown to the agent inside <untrusted-record-data> fences (docs/14 C1)
  - `raw` — the original row, verbatim, for the audit trail

Note: there is no card-number (PAN) field. Full card numbers are dropped at
ingest and a PII_DROPPED event is emitted (docs/26 §1).
"""

from __future__ import annotations

import hashlib
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field

Source = str  # "razorpay_recon" | "bank" | "ledger" | ...
RecordKind = Literal[
    "payment", "refund", "adjustment", "chargeback", "transfer", "credit", "order", "fee"
]


class Record(BaseModel):
    model_config = {"frozen": True}

    id: str
    run_id: str
    source: Source
    kind: RecordKind
    amount_minor: int  # signed: credit +, debit −
    fee_minor: int = 0
    tax_minor: int = 0
    currency: str = "INR"
    value_date: date | None = None
    posted_date: date | None = None
    settled_at: date | None = None
    counterparty: str | None = None
    reference: str | None = None  # normalized ref used in matching
    external_ids: dict[str, str] = Field(default_factory=dict)
    untrusted: dict[str, str] = Field(default_factory=dict)  # never used in logic
    raw: dict[str, str] = Field(default_factory=dict)
    ingest_file_hash: str = ""
    org_id: str = "local"

    @staticmethod
    def make_id(source: str, source_row_id: str, run_id: str) -> str:
        h = hashlib.sha256(f"{source}|{source_row_id}|{run_id}".encode())
        return h.hexdigest()[:16]


MatchPass = Literal["exact", "tolerant", "subset", "subset_heuristic", "transitive"]
MatchStatus = Literal["auto", "low_confidence", "human_confirmed"]
ExceptionStatus = Literal[
    "open", "proposed", "escalated", "resolved", "wont_fix", "budget_exceeded", "security_review"
]


class Match(BaseModel):
    """A group of records representing the same money (docs/17 §4)."""

    model_config = {"frozen": True}

    id: str
    run_id: str
    left_ids: list[str] = Field(default_factory=list)  # processor side
    right_ids: list[str] = Field(default_factory=list)  # bank side
    group_ids: list[str] = Field(default_factory=list)  # ledger side
    match_pass: MatchPass
    weight_bits: float | None = None  # Fellegi–Sunter match weight
    per_field_weights: dict[str, float] = Field(default_factory=dict)
    confidence: float  # calibrated P(match)
    rule_id: str | None = None
    residual_minor: int = 0
    status: MatchStatus = "auto"

    @property
    def all_ids(self) -> list[str]:
        return sorted({*self.left_ids, *self.right_ids, *self.group_ids})


class Decomposition(BaseModel):
    """The settlement identity, evaluated for one settlement_utr group (docs/15 §2)."""

    model_config = {"frozen": True}

    group_id: str
    run_id: str
    settlement_utr: str | None
    expected_minor: int  # what the bank credit should be
    actual_minor: int  # what it was
    residual_minor: int  # actual − expected (0 ⇒ clean)
    ledger_crosscheck_ok: bool
    components: dict[str, int] = Field(default_factory=dict)  # gross, mdr, gst, refunds, ...

    @property
    def clean(self) -> bool:
        return self.residual_minor == 0


class MatchCandidate(BaseModel):
    model_config = {"frozen": True}

    hypothesis: str
    record_ids: list[str]
    score_bits: float
    per_field_weights: dict[str, float] = Field(default_factory=dict)


class Exception_(BaseModel):
    """A non-match / broken identity that needs classification (docs/17 §5).

    Named `Exception_` to avoid shadowing the builtin; exported as `ReconException`.
    """

    model_config = {"frozen": True}

    id: str
    run_id: str
    record_ids: list[str] = Field(default_factory=list)
    category: str | None = None
    classified_by: str = "unclassified"  # "rule:<id>" | "agent" | "unclassified"
    amount_impact_minor: int = 0  # signed ₹ at stake — ranking key
    confidence: float | None = None
    candidates: list[MatchCandidate] = Field(default_factory=list)
    agent_proposal: dict[str, Any] | None = None  # a Proposal (docs/19 §4), gated
    agent_escalation: dict[str, Any] | None = None  # an Escalate
    resolution: dict[str, str] | None = None
    status: ExceptionStatus = "open"


ReconException = Exception_


class RunConfig(BaseModel):
    """Everything that influences a run's output — hashed into RUN_STARTED."""

    model_config = {"frozen": True}

    spec_name: str
    spec_version: int
    spec_hash: str
    dataset_hash: str
    seed: int | None = None
    no_ai: bool = False
