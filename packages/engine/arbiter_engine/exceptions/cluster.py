"""Root-cause clustering (spec §24, docs/15 §4).

A monthly close can open 80+ exceptions. A controller does not want 80 rows —
they want "5 root causes, ₹X each, here's a representative one". This groups the
still-open exceptions of a run by a deterministic key and sums the ₹ impact per
group. Every number here is deterministic; an LLM may only attach a label to a
cluster (not done in this module — the key itself reads as the cause).

Cluster key  = (category, rule_id, direction, magnitude band)
  category    the exception category (UNCLASSIFIED if none)
  rule_id     the deterministic rule that classified it, else "agent" /
              "unclassified"
  direction   sign of the ₹ impact — "short" (money missing), "over" (money
              extra), "flat" (no ₹ delta)
  band        order-of-magnitude bucket of |impact|
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from arbiter_engine.models import ReconException

# statuses that still represent an unresolved root cause worth surfacing
_OPEN_STATES: frozenset[str] = frozenset(
    {"open", "proposed", "escalated", "security_review", "budget_exceeded"}
)

_BANDS: tuple[tuple[int, str], ...] = (
    (1_000_00, "<₹1k"),
    (10_000_00, "₹1k–₹10k"),
    (1_00_000_00, "₹10k–₹1L"),
    (10_00_000_00, "₹1L–₹10L"),
)


def _band(minor: int) -> str:
    a = abs(minor)
    for ceiling, label in _BANDS:
        if a < ceiling:
            return label
    return "₹10L+"


def _direction(minor: int) -> str:
    if minor < 0:
        return "short"
    if minor > 0:
        return "over"
    return "flat"


def _rule_id(exc: ReconException) -> str:
    cb = exc.classified_by or "unclassified"
    if cb.startswith("rule:"):
        return cb.split("rule:", 1)[1]
    if cb.startswith("human:"):
        return "human-corrected"
    return cb  # "agent" | "unclassified"


@dataclass(frozen=True)
class ClusterKey:
    category: str
    rule_id: str
    direction: str
    band: str

    def as_dict(self) -> dict[str, str]:
        return {
            "category": self.category,
            "rule_id": self.rule_id,
            "direction": self.direction,
            "band": self.band,
        }

    def headline(self) -> str:
        return f"{self.category} · {self.rule_id} · {self.direction} · {self.band}"


@dataclass
class Cluster:
    key: ClusterKey
    count: int
    gross_impact_minor: int  # Σ |impact| — the size of the problem
    net_impact_minor: int  # Σ signed impact — the P&L effect
    exception_ids: list[str]
    example_id: str  # a representative exception to open first

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key.as_dict(),
            "headline": self.key.headline(),
            "count": self.count,
            "gross_impact_minor": self.gross_impact_minor,
            "net_impact_minor": self.net_impact_minor,
            "exception_ids": self.exception_ids,
            "example_id": self.example_id,
        }


def cluster_exceptions(exceptions: Iterable[ReconException]) -> list[Cluster]:
    """Group open exceptions into root-cause clusters, largest ₹ first."""
    buckets: dict[ClusterKey, list[ReconException]] = {}
    for e in exceptions:
        if e.status not in _OPEN_STATES:
            continue
        key = ClusterKey(
            category=e.category or "UNCLASSIFIED",
            rule_id=_rule_id(e),
            direction=_direction(e.amount_impact_minor),
            band=_band(e.amount_impact_minor),
        )
        buckets.setdefault(key, []).append(e)

    clusters = [
        Cluster(
            key=key,
            count=len(members),
            gross_impact_minor=sum(abs(m.amount_impact_minor) for m in members),
            net_impact_minor=sum(m.amount_impact_minor for m in members),
            exception_ids=sorted(m.id for m in members),
            example_id=min(members, key=lambda m: (-abs(m.amount_impact_minor), m.id)).id,
        )
        for key, members in buckets.items()
    ]
    return sorted(
        clusters,
        key=lambda c: (-c.gross_impact_minor, c.key.category, c.key.rule_id, c.key.band),
    )


def summarize(exceptions: Iterable[ReconException]) -> dict[str, Any]:
    clusters = cluster_exceptions(exceptions)
    return {
        "cluster_count": len(clusters),
        "total_gross_minor": sum(c.gross_impact_minor for c in clusters),
        "total_net_minor": sum(c.net_impact_minor for c in clusters),
        "clusters": [c.as_dict() for c in clusters],
    }
