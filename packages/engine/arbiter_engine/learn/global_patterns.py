"""Opt-in global pattern library (docs/28 §3 item 15) — the network effect.

When a tenant resolves an exception, the *shape* of that exception (never its
content) plus the resolution action can be contributed to a shared library.
Another tenant hitting the same shape then sees "N other teams resolved this as
`accept_variance`". Strict anonymisation and a hard kill-switch.

What crosses the boundary (`anon_shape`): the category, the residual **band**,
the record-count **band**, the sorted set of source *types* and record *kinds*,
and three booleans (a reference / a counterparty / a dispute id is present).
**No amounts, no names, no ids, no free text, no org id.** The contributor is
recorded as `sha256(org_id + salt)` so distinct-tenant counts work without
knowing who.

`ARBITER_GLOBAL_PATTERNS`:
  - `off` (default) — contribute nothing, consult nothing.
  - `consume`       — read the library, contribute nothing.
  - `contribute`    — read and contribute.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import (
    Column,
    Engine,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    insert,
    select,
)

if TYPE_CHECKING:
    from arbiter_engine.models import ReconException, Record

# A private MetaData — the global library is its own database and must never
# land in the tenant schema / the API's Alembic migrations.
_META = MetaData()
_PATTERNS = Table(
    "global_patterns",
    _META,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("shape_key", String, index=True),
    Column("category", String, index=True),
    Column("resid_band", String),
    Column("action", String),
    Column("contributor", String),  # sha256(org_id + salt) — not reversible
    Column("shape_json", String),
)

_MODE = os.environ.get("ARBITER_GLOBAL_PATTERNS", "off").strip().lower()
_DB = os.environ.get("ARBITER_GLOBAL_DB_URL", "sqlite:///data/global_patterns.db")
_SALT = os.environ.get("ARBITER_GLOBAL_SALT", "arbiter-global-v1")
_RESID_EDGES = (100, 500, 2000, 10000, 100000)
_NREC_EDGES = (1, 3, 8, 20)


def contributing() -> bool:
    return _MODE == "contribute"


def consulting() -> bool:
    return _MODE in ("consume", "contribute")


def _band(value: int, edges: tuple[int, ...]) -> str:
    v = abs(value)
    for e in edges:
        if v <= e:
            return f"<={e}"
    return f">{edges[-1]}"


def anon_shape(exc: ReconException, records: list[Record]) -> dict[str, object]:
    """The only thing that ever leaves a tenant. Identifier-free by construction."""
    return {
        "category": exc.category or "UNEXPLAINED",
        "resid_band": _band(exc.amount_impact_minor, _RESID_EDGES),
        "nrec_band": _band(len(records), _NREC_EDGES),
        "sources": sorted({r.source for r in records}),
        "kinds": sorted({r.kind for r in records}),
        "has_reference": any(r.reference for r in records),
        "has_counterparty": any(r.counterparty for r in records),
        "has_dispute_id": any(r.external_ids.get("dispute_id") for r in records),
    }


def shape_key(shape: dict[str, object]) -> str:
    return hashlib.sha256(json.dumps(shape, sort_keys=True).encode()).hexdigest()[:24]


def _contributor(org_id: str) -> str:
    return hashlib.sha256(f"{org_id}|{_SALT}".encode()).hexdigest()[:16]


def _engine() -> Engine:
    if _DB.startswith("sqlite:///"):
        from pathlib import Path

        Path(_DB.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    eng = create_engine(_DB)
    _META.create_all(eng)
    return eng


@dataclass
class GlobalHit:
    action: str
    occurrences: int
    distinct_tenants: int


def contribute(org_id: str, exc: ReconException, records: list[Record], action: str) -> bool:
    if not contributing() or org_id == "local":
        return False
    shape = anon_shape(exc, records)
    with _engine().begin() as conn:
        conn.execute(
            insert(_PATTERNS).values(
                shape_key=shape_key(shape),
                category=str(shape["category"]),
                resid_band=str(shape["resid_band"]),
                action=action,
                contributor=_contributor(org_id),
                shape_json=json.dumps(shape, sort_keys=True),
            )
        )
    return True


def recall_global(exc: ReconException, records: list[Record], *, k: int = 3) -> list[GlobalHit]:
    """Canonical resolutions for this exception's shape across the network —
    exact shape first, then same-category + same-residual-band."""
    if not consulting():
        return []
    shape = anon_shape(exc, records)
    key = shape_key(shape)
    c = _PATTERNS.c
    with _engine().connect() as conn:
        rows = list(conn.execute(select(c.action, c.contributor).where(c.shape_key == key)))
        if not rows:
            rows = list(
                conn.execute(
                    select(c.action, c.contributor).where(
                        c.category == shape["category"], c.resid_band == shape["resid_band"]
                    )
                )
            )
    if not rows:
        return []
    occ: Counter[str] = Counter(r.action for r in rows)
    tenants: dict[str, set[str]] = {}
    for r in rows:
        tenants.setdefault(r.action, set()).add(r.contributor)
    hits = [GlobalHit(a, occ[a], len(tenants[a])) for a in occ]
    hits.sort(key=lambda h: (h.distinct_tenants, h.occurrences), reverse=True)
    return hits[:k]
