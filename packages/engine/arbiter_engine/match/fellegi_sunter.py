"""The Fellegi–Sunter probabilistic record-linkage model (docs/16 §5, ADR-0005).

For a candidate record pair, each comparison field is evaluated at a discrete
*agreement level*. Each (field, level) has:
  - m = P(this level | the pair is a true match)     — "how often matches look like this"
  - u = P(this level | the pair is a non-match)       — "how often coincidences look like this"

match weight (bits) = Σ_f log2( m_{f,level} / u_{f,level} )

posterior odds = prior odds · 2^weight ;  P(match) = odds / (1 + odds)

M2 ships domain-prior m/u (seeded from the reasoning in docs/16 §5.2). Estimation
from the labeled synthetic data — direct frequency counting against
ground_truth.json — plugs into `FSModel.from_labeled` and is exercised by
`arbiter bench --recalibrate`; the resulting table is frozen per spec version
(docs/17 §7).
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, field

# ---- comparison levels -----------------------------------------------------

AMOUNT_LEVELS = ("exact", "within_rounding", "within_tol", "within_1pct", "none")
DATE_LEVELS = ("same_day", "within_1", "within_window", "none")
REF_LEVELS = ("exact", "jaro_hi", "jaro_mid", "none")
IDLINK_LEVELS = ("shared", "none")

# domain-prior m/u (docs/16 §5.2). u for a strong agreement is low (coincidence
# is rare); m is high but not 1 because real data is noisy.
_PRIOR_MU: dict[str, dict[str, tuple[float, float]]] = {
    "amount": {
        "exact": (0.82, 0.02),
        "within_rounding": (0.10, 0.03),
        "within_tol": (0.05, 0.05),
        "within_1pct": (0.02, 0.10),
        "none": (0.01, 0.80),
    },
    "date": {
        "same_day": (0.55, 0.05),
        "within_1": (0.30, 0.08),
        "within_window": (0.13, 0.17),
        "none": (0.02, 0.70),
    },
    "reference": {
        "exact": (0.90, 0.001),
        "jaro_hi": (0.06, 0.02),
        "jaro_mid": (0.03, 0.10),
        "none": (0.01, 0.879),
    },
    "idlink": {
        "shared": (0.95, 0.01),
        "none": (0.05, 0.99),
    },
}


@dataclass
class FSModel:
    mu: dict[str, dict[str, tuple[float, float]]] = field(
        default_factory=lambda: {k: dict(v) for k, v in _PRIOR_MU.items()}
    )
    # calibration: monotonic map applied to the raw posterior (docs/16 §5.5).
    # empty ⇒ identity. Filled by `arbiter bench --calibration`.
    calibration: list[tuple[float, float]] = field(default_factory=list)

    def field_weight(self, field_name: str, level: str) -> float:
        m, u = self.mu[field_name][level]
        m = min(max(m, 1e-6), 1 - 1e-6)
        u = min(max(u, 1e-6), 1 - 1e-6)
        return math.log2(m / u)

    def weight(self, comparison: dict[str, str]) -> tuple[float, dict[str, float]]:
        per_field: dict[str, float] = {}
        total = 0.0
        for field_name, level in comparison.items():
            if field_name not in self.mu or level not in self.mu[field_name]:
                continue
            w = self.field_weight(field_name, level)
            per_field[field_name] = round(w, 3)
            total += w
        return total, per_field

    def probability(self, weight_bits: float, *, prior: float) -> float:
        prior = min(max(prior, 1e-9), 1 - 1e-9)
        prior_odds = prior / (1 - prior)
        odds = prior_odds * (2.0**weight_bits)
        raw = odds / (1 + odds)
        return self._calibrate(raw)

    def _calibrate(self, p: float) -> float:
        if not self.calibration:
            return p
        pts = sorted(self.calibration)
        if p <= pts[0][0]:
            return pts[0][1]
        if p >= pts[-1][0]:
            return pts[-1][1]
        for (x0, y0), (x1, y1) in zip(pts, pts[1:], strict=False):
            if x0 <= p <= x1:
                if x1 == x0:
                    return y1
                return y0 + (y1 - y0) * (p - x0) / (x1 - x0)
        return p

    # ---- estimation from labeled data (docs/16 §5.2) ----
    @classmethod
    def from_labeled(
        cls,
        match_comparisons: Iterable[dict[str, str]],
        nonmatch_comparisons: Iterable[dict[str, str]],
    ) -> FSModel:
        model = cls()
        m_counts: dict[str, dict[str, int]] = {}
        u_counts: dict[str, dict[str, int]] = {}
        m_tot: dict[str, int] = {}
        u_tot: dict[str, int] = {}

        for comp in match_comparisons:
            for f, lvl in comp.items():
                m_counts.setdefault(f, {}).setdefault(lvl, 0)
                m_counts[f][lvl] += 1
                m_tot[f] = m_tot.get(f, 0) + 1
        for comp in nonmatch_comparisons:
            for f, lvl in comp.items():
                u_counts.setdefault(f, {}).setdefault(lvl, 0)
                u_counts[f][lvl] += 1
                u_tot[f] = u_tot.get(f, 0) + 1

        for f, levels in model.mu.items():
            for lvl in levels:
                # Laplace-smoothed frequencies; fall back to the prior if unseen
                mc = m_counts.get(f, {}).get(lvl, 0)
                uc = u_counts.get(f, {}).get(lvl, 0)
                mt = m_tot.get(f, 0)
                ut = u_tot.get(f, 0)
                if mt == 0 or ut == 0:
                    continue
                k = len(levels)
                m = (mc + 1) / (mt + k)
                u = (uc + 1) / (ut + k)
                model.mu[f][lvl] = (m, u)
        return model
