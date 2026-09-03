"""Resolution memory — semantic recall of how similar exceptions were resolved
(docs/28 §1.3 / §4).

The agent's `similar_exceptions` tool was an exact-category filter. This makes it
a similarity search: an exception is turned into a bag of shape features
(category, residual band, record count band, the mix of sources / kinds,
reference and counterparty tokens), and past *resolved* exceptions are ranked by
IDF-weighted cosine similarity.

Deterministic and dependency-free — the corpus is the store's own
`RESOLUTION_APPLIED` history. A pgvector-backed, cross-tenant version is Phase 4;
the interface here does not change when that lands.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from arbiter_engine.events.store import EventStore
    from arbiter_engine.models import ReconException, Record

_TOKEN_MIN = 3


def _tokens(text: str | None) -> list[str]:
    if not text:
        return []
    out: list[str] = []
    cur = ""
    for ch in text.upper():
        if ch.isalnum():
            cur += ch
        else:
            if len(cur) >= _TOKEN_MIN:
                out.append(cur)
            cur = ""
    if len(cur) >= _TOKEN_MIN:
        out.append(cur)
    return out


def _band(value: int, edges: tuple[int, ...]) -> str:
    v = abs(value)
    for e in edges:
        if v <= e:
            return f"<={e}"
    return f">{edges[-1]}"


def features(exc: ReconException, records: list[Record]) -> Counter[str]:
    """The shape of one exception as a bag of feature tokens."""
    f: Counter[str] = Counter()
    f[f"cat:{exc.category or 'UNEXPLAINED'}"] += 3
    f[f"resid:{_band(exc.amount_impact_minor, (100, 500, 2000, 10000, 100000))}"] += 2
    f[f"nrec:{_band(len(records), (1, 3, 8, 20))}"] += 1
    from arbiter_engine.match.entity import canonical_entity

    for r in records:
        f[f"src:{r.source}"] += 1
        f[f"kind:{r.kind}"] += 1
        for tok in _tokens(r.reference)[:6]:
            f[f"ref:{tok}"] += 1
        for tok in canonical_entity(r.counterparty).split()[:4]:
            f[f"cp:{tok}"] += 1
        for k, v in r.external_ids.items():
            if k in ("dispute_id", "settlement_id") and v:
                f[f"has:{k}"] += 1
    return f


@dataclass
class MemoryHit:
    exception_id: str
    run_id: str
    category: str
    resolution: dict[str, Any]
    similarity: float


class ResolutionMemory:
    def __init__(self, entries: list[tuple[Counter[str], MemoryHit]]) -> None:
        self._entries = entries
        n = len(entries) or 1
        df: Counter[str] = Counter()
        for vec, _ in entries:
            df.update(vec.keys())
        self._idf = {t: math.log((n + 1) / (c + 1)) + 1.0 for t, c in df.items()}

    def __len__(self) -> int:
        return len(self._entries)

    def _weighted(self, vec: Counter[str]) -> dict[str, float]:
        return {t: c * self._idf.get(t, 1.0) for t, c in vec.items()}

    def recall(
        self, exc: ReconException, records: list[Record], *, k: int = 5, floor: float = 0.15
    ) -> list[MemoryHit]:
        if not self._entries:
            return []
        q = self._weighted(features(exc, records))
        qn = math.sqrt(sum(v * v for v in q.values())) or 1.0
        scored: list[MemoryHit] = []
        for vec, hit in self._entries:
            d = self._weighted(vec)
            dot = sum(q[t] * d.get(t, 0.0) for t in q)
            dn = math.sqrt(sum(v * v for v in d.values())) or 1.0
            sim = dot / (qn * dn)
            if sim >= floor:
                scored.append(
                    MemoryHit(
                        hit.exception_id, hit.run_id, hit.category, hit.resolution, round(sim, 4)
                    )
                )
        scored.sort(key=lambda h: (-h.similarity, h.exception_id))
        return scored[:k]

    @classmethod
    def from_store(
        cls, store: EventStore, *, exclude_run_id: str | None = None, org_id: str | None = None
    ) -> ResolutionMemory:
        """Build the memory from every prior run's resolved exceptions."""
        from arbiter_engine.events.fold import fold_run

        entries: list[tuple[Counter[str], MemoryHit]] = []
        for rid in store.runs():
            if rid == exclude_run_id:
                continue
            proj = fold_run(store, rid)
            if org_id is not None:
                recs0 = proj.records
                if recs0 and getattr(recs0[0], "org_id", "local") != org_id:
                    continue
            rec_by_id = {r.id: r for r in proj.records}
            for e in proj.exceptions:
                if not e.resolution:
                    continue
                recs = [rec_by_id[i] for i in e.record_ids if i in rec_by_id]
                hit = MemoryHit(
                    exception_id=e.id,
                    run_id=rid,
                    category=e.category or "UNEXPLAINED",
                    resolution=dict(e.resolution),
                    similarity=0.0,
                )
                entries.append((features(e, recs), hit))
        return cls(entries)
