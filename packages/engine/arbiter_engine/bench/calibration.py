"""Confidence calibration study (docs/12 §6.2, docs/16 §5.5).

Bucket predictions by stated confidence, compare to observed accuracy against
ground truth, report the reliability diagram + Expected Calibration Error, and —
if ECE exceeds the threshold — fit a monotonic (isotonic) recalibration map that
the FSModel then applies.
"""

from __future__ import annotations

from dataclasses import dataclass, field

_ECE_THRESHOLD = 0.05


@dataclass
class Bucket:
    lo: float
    hi: float
    n: int = 0
    correct: int = 0
    conf_sum: float = 0.0

    @property
    def accuracy(self) -> float:
        return self.correct / self.n if self.n else 0.0

    @property
    def mean_confidence(self) -> float:
        return self.conf_sum / self.n if self.n else (self.lo + self.hi) / 2


@dataclass
class CalibrationReport:
    buckets: list[Bucket] = field(default_factory=list)
    ece: float = 0.0
    n: int = 0
    recalibration: list[tuple[float, float]] = field(default_factory=list)
    applied: bool = False
    # what this diagram was measured on — a Claude ECE must never be shown for GPT
    model_key: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "ece": round(self.ece, 4),
            "n": self.n,
            "model_key": self.model_key,
            "well_calibrated": self.ece <= _ECE_THRESHOLD,
            "reliability": [
                {
                    "range": [round(b.lo, 2), round(b.hi, 2)],
                    "n": b.n,
                    "confidence": round(b.mean_confidence, 4),
                    "accuracy": round(b.accuracy, 4),
                }
                for b in self.buckets
                if b.n
            ],
            "recalibration": [[round(x, 4), round(y, 4)] for x, y in self.recalibration],
            "recalibration_applied": self.applied,
        }


def calibrate(
    predictions: list[tuple[float, bool]],
    *,
    n_buckets: int = 10,
    model_key: str | None = None,
) -> CalibrationReport:
    """predictions: (stated_confidence, is_correct).

    `model_key` (e.g. ``"gpt-4o@<prompt-hash>"``) records which provider/model/
    prompt this reliability diagram belongs to — a calibration measured on one
    model must never be presented as another model's."""
    report = CalibrationReport(n=len(predictions), model_key=model_key)
    if not predictions:
        return report

    edges = [i / n_buckets for i in range(n_buckets + 1)]
    report.buckets = [Bucket(edges[i], edges[i + 1]) for i in range(n_buckets)]
    for conf, correct in predictions:
        idx = min(int(conf * n_buckets), n_buckets - 1)
        b = report.buckets[idx]
        b.n += 1
        b.conf_sum += conf
        b.correct += int(correct)

    total = len(predictions)
    report.ece = sum(
        (b.n / total) * abs(b.mean_confidence - b.accuracy) for b in report.buckets if b.n
    )

    if report.ece > _ECE_THRESHOLD:
        report.recalibration = _isotonic(
            [(b.mean_confidence, b.accuracy) for b in report.buckets if b.n]
        )
        report.applied = bool(report.recalibration)
    return report


def _isotonic(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Pool-Adjacent-Violators — enforce a non-decreasing mapping."""
    if not points:
        return []
    pts = sorted(points)
    xs = [x for x, _ in pts]
    ys = [y for _, y in pts]
    weights = [1.0] * len(ys)
    i = 0
    while i < len(ys) - 1:
        if ys[i] > ys[i + 1]:
            new_y = (ys[i] * weights[i] + ys[i + 1] * weights[i + 1]) / (
                weights[i] + weights[i + 1]
            )
            ys[i] = new_y
            weights[i] += weights[i + 1]
            del ys[i + 1], weights[i + 1], xs[i + 1]
            if i > 0:
                i -= 1
        else:
            i += 1
    return list(zip(xs, ys, strict=False))
