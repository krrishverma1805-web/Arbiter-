"""pgvector-backed resolution memory (docs/28 §3 item 13).

`ResolutionMemory` re-folds every run of the tenant on every construction to
build its IDF-cosine index — fine for a demo, O(runs) for a real tenant. This
version:

  * turns each resolved exception's shape (`agent.memory.features`) into a
    fixed-width dense vector by **signed feature hashing** (deterministic, no
    embedding model — the deterministic core stays LLM-free);
  * persists `(exception_id → vector, category, resolution)` in a
    `resolution_vectors` table on the store's own database, tenant-scoped, and
    only indexes what it hasn't seen before (incremental `sync`);
  * recalls by cosine top-k — a `pgvector` `<=>` ANN query when the extension is
    present, an in-Python scan otherwise.

The `recall(exc, records, *, k, floor)` signature matches `ResolutionMemory`, so
`agent.tools.similar_exceptions` doesn't know which one it has.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from arbiter_engine.agent.memory import MemoryHit, features

if TYPE_CHECKING:
    from arbiter_engine.events.store import EventStore
    from arbiter_engine.models import ReconException, Record

_DIM = 256


def hash_embed(bag: Counter[str], dim: int = _DIM) -> list[float]:
    """Signed feature hashing → an L2-normalised dense vector. Deterministic."""
    v = [0.0] * dim
    for tok, weight in bag.items():
        h = hashlib.blake2b(tok.encode(), digest_size=8).digest()
        idx = int.from_bytes(h[:4], "big") % dim
        sign = 1.0 if h[4] & 1 else -1.0
        v[idx] += sign * float(weight)
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norm for x in v]


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=False))


@dataclass
class _Row:
    exception_id: str
    run_id: str
    category: str
    resolution: dict[str, Any]
    vec: list[float]


class VectorResolutionMemory:
    def __init__(self, store: EventStore, org_id: str, exclude_run_id: str | None = None) -> None:
        self._store = store
        self._org = org_id
        self._exclude = exclude_run_id
        self._is_pg = getattr(store, "_is_pg", False)
        self._ddl()
        self._sync()

    def __len__(self) -> int:
        with self._store.engine.connect() as c:
            return int(
                c.execute(
                    text("SELECT count(*) FROM resolution_vectors WHERE org_id = :o"),
                    {"o": self._org},
                ).scalar_one()
            )

    # -- build -------------------------------------------------------------
    def _ddl(self) -> None:
        col = f"vector({_DIM})" if self._has_pgvector() else "TEXT"
        with self._store.engine.begin() as c:
            c.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS resolution_vectors ("
                    "org_id TEXT, run_id TEXT, exception_id TEXT, category TEXT, "
                    f"resolution TEXT, vec {col}, PRIMARY KEY (org_id, exception_id))"
                )
            )

    def _has_pgvector(self) -> bool:
        if not self._is_pg:
            return False
        try:  # pragma: no cover - needs Postgres + the extension
            with self._store.engine.begin() as c:
                c.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            return True
        except Exception:  # pragma: no cover
            return False

    def _indexed(self) -> set[str]:
        with self._store.engine.connect() as c:
            return {
                r[0]
                for r in c.execute(
                    text("SELECT exception_id FROM resolution_vectors WHERE org_id = :o"),
                    {"o": self._org},
                )
            }

    def _sync(self) -> None:
        from arbiter_engine.events.fold import fold_run

        done = self._indexed()
        pgv = self._has_pgvector()
        for rid in self._store.runs():
            if rid == self._exclude:
                continue
            proj = fold_run(self._store, rid)
            recs0 = proj.records
            if recs0 and getattr(recs0[0], "org_id", "local") != self._org:
                continue
            rec_by_id = {r.id: r for r in proj.records}
            for e in proj.exceptions:
                if not e.resolution or e.id in done:
                    continue
                recs = [rec_by_id[i] for i in e.record_ids if i in rec_by_id]
                vec = hash_embed(features(e, recs))
                stored = _pg_vec(vec) if pgv else json.dumps(vec)
                with self._store.engine.begin() as c:
                    c.execute(
                        text(
                            "INSERT INTO resolution_vectors "
                            "(org_id, run_id, exception_id, category, resolution, vec) "
                            "VALUES (:o, :r, :e, :cat, :res, :v) "
                            "ON CONFLICT (org_id, exception_id) DO NOTHING"
                        ),
                        {
                            "o": self._org,
                            "r": rid,
                            "e": e.id,
                            "cat": e.category or "UNEXPLAINED",
                            "res": json.dumps(e.resolution),
                            "v": stored,
                        },
                    )
                done.add(e.id)

    # -- query ------------------------------------------------------------
    def recall(
        self, exc: ReconException, records: list[Record], *, k: int = 5, floor: float = 0.15
    ) -> list[MemoryHit]:
        q = hash_embed(features(exc, records))
        if self._has_pgvector():  # pragma: no cover - needs Postgres
            return self._recall_pg(q, k, floor)
        rows = self._load_rows()
        scored = [
            MemoryHit(
                r.exception_id, r.run_id, r.category, r.resolution, round(_cosine(q, r.vec), 4)
            )
            for r in rows
        ]
        scored = [h for h in scored if h.similarity >= floor]
        scored.sort(key=lambda h: (-h.similarity, h.exception_id))
        return scored[:k]

    def _recall_pg(
        self, q: list[float], k: int, floor: float
    ) -> list[MemoryHit]:  # pragma: no cover
        with self._store.engine.connect() as c:
            rows = c.execute(
                text(
                    "SELECT run_id, exception_id, category, resolution, "
                    "1 - (vec <=> :q) AS sim FROM resolution_vectors "
                    "WHERE org_id = :o ORDER BY vec <=> :q LIMIT :k"
                ),
                {"q": _pg_vec(q), "o": self._org, "k": k},
            ).all()
        return [
            MemoryHit(
                r.exception_id, r.run_id, r.category, json.loads(r.resolution), round(r.sim, 4)
            )
            for r in rows
            if r.sim >= floor
        ]

    def _load_rows(self) -> list[_Row]:
        with self._store.engine.connect() as c:
            raw = c.execute(
                text(
                    "SELECT run_id, exception_id, category, resolution, vec "
                    "FROM resolution_vectors WHERE org_id = :o"
                ),
                {"o": self._org},
            ).all()
        return [
            _Row(r.exception_id, r.run_id, r.category, json.loads(r.resolution), json.loads(r.vec))
            for r in raw
        ]

    @classmethod
    def from_store(
        cls, store: EventStore, *, exclude_run_id: str | None = None, org_id: str | None = None
    ) -> VectorResolutionMemory:
        org: str = org_id or str(getattr(store, "org_id", "local"))
        return cls(store, org, exclude_run_id)


def _pg_vec(v: list[float]) -> str:  # pragma: no cover - needs Postgres
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"
