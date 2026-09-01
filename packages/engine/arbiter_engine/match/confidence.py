"""The per-match confidence formula (docs/16 §5, §6.1).

M1 uses an explicit weighted score. The Fellegi–Sunter match-weight model with
m/u probabilities estimated from labeled data, and calibration (ECE / isotonic),
land in M2–M3 (ADR-0005). The interface here does not change when that happens:
`score_match` returns a calibrated P(match) in [0, 1] plus the per-field
contributions for the evidence drawer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class FieldScores:
    key_agreement: float = 0.0
    amount_score: float = 0.0
    date_score: float = 0.0
    reference_similarity: float = 0.0
    shared_external_id: float = 0.0

    def as_dict(self) -> dict[str, float]:
        return {
            "key_agreement": round(self.key_agreement, 4),
            "amount_score": round(self.amount_score, 4),
            "date_score": round(self.date_score, 4),
            "reference_similarity": round(self.reference_similarity, 4),
            "shared_external_id": round(self.shared_external_id, 4),
        }


@dataclass
class ConfidenceModel:
    weights: dict[str, float] = field(
        default_factory=lambda: {
            "key_agreement": 0.45,
            "amount_score": 0.25,
            "date_score": 0.15,
            "reference_similarity": 0.10,
            "shared_external_id": 0.05,
        }
    )

    def __post_init__(self) -> None:
        total = sum(self.weights.values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"confidence weights must sum to 1.0, got {total}")

    def score(self, fs: FieldScores) -> float:
        raw = (
            self.weights["key_agreement"] * fs.key_agreement
            + self.weights["amount_score"] * fs.amount_score
            + self.weights["date_score"] * fs.date_score
            + self.weights["reference_similarity"] * fs.reference_similarity
            + self.weights["shared_external_id"] * fs.shared_external_id
        )
        return max(0.0, min(1.0, raw))


def amount_score(delta_minor: int, tolerance_minor: int) -> float:
    if delta_minor == 0:
        return 1.0
    if tolerance_minor <= 0:
        return 0.0
    return max(0.0, 1.0 - abs(delta_minor) / tolerance_minor)


def date_score(a: date | None, b: date | None, window_days: int) -> float:
    if a is None or b is None:
        return 0.0
    diff = abs((a - b).days)
    if diff == 0:
        return 1.0
    if window_days <= 0:
        return 0.0
    return max(0.0, 1.0 - diff / window_days)
