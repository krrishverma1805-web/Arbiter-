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
from typing import Literal

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


class RunConfig(BaseModel):
    """Everything that influences a run's output — hashed into RUN_STARTED."""

    model_config = {"frozen": True}

    spec_name: str
    spec_version: int
    spec_hash: str
    dataset_hash: str
    seed: int | None = None
    no_ai: bool = False
