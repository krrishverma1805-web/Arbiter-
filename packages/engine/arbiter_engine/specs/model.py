"""Recon spec model (docs/04 §5, docs/adr/0003).

M0 validates and uses the `sources` block (formats, column maps, amount scales,
untrusted fields, id fields). The `identity`, `passes`, `taxonomy`, `rules` and
`adjudication` blocks are accepted and stored now, exercised from M1 onward.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

AmountScale = Literal["rupees_to_paise", "already_paise", "already_minor"]


class SourceSpec(BaseModel):
    model_config = {"extra": "forbid"}

    format: str
    profiles: list[str] = Field(default_factory=list)
    columns: dict[str, str] = Field(default_factory=dict)  # canonical_field -> source_header
    id_fields: list[str] = Field(default_factory=list)
    derive: dict[str, str] = Field(default_factory=dict)
    amount_scale: AmountScale = "rupees_to_paise"
    sign_convention: dict[str, str] = Field(default_factory=dict)
    untrusted_fields: list[str] = Field(default_factory=list)
    kind: str | None = None  # default record kind if the source doesn't carry `type`


class ReconSpec(BaseModel):
    model_config = {"extra": "allow"}  # tolerate future blocks; M0 uses `sources`

    name: str
    version: int
    description: str = ""
    sources: dict[str, SourceSpec]
    identity: dict[str, Any] = Field(default_factory=dict)
    passes: dict[str, Any] = Field(default_factory=dict)
    confidence_weights: dict[str, float] = Field(default_factory=dict)
    thresholds: dict[str, float] = Field(default_factory=dict)
    taxonomy: list[str] = Field(default_factory=list)
    rules: list[dict[str, Any]] = Field(default_factory=list)
    adjudication: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check(self) -> ReconSpec:
        if not self.sources:
            raise ValueError("spec must define at least one source")
        if self.confidence_weights:
            total = sum(self.confidence_weights.values())
            if abs(total - 1.0) > 1e-6:
                raise ValueError(f"confidence_weights must sum to 1.0, got {total}")
        return self
