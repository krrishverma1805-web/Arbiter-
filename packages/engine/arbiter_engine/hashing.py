"""Canonical serialization and hashing for the event log.

The event store is a hash chain (docs/adr/0002). Determinism requires that the
same logical payload always serializes to the same bytes: sorted keys, no
whitespace, stable number formatting, UTC-normalized timestamps.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(obj: Any) -> str:
    """Deterministic JSON: sorted keys, compact separators, UTF-8, no NaN."""
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=_default,
    )


def _default(value: Any) -> Any:
    # pydantic models expose model_dump; fall back to str for dates etc.
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "isoformat"):
        return value.isoformat()
    raise TypeError(f"cannot serialize {type(value).__name__} in canonical_json")


def sha256_hex(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def chain_hash(prev_hash: str, *, event_type: str, actor: str, payload: Any) -> str:
    """hash = sha256(prev_hash || type || actor || canonical(payload))."""
    material = f"{prev_hash}|{event_type}|{actor}|{canonical_json(payload)}"
    return sha256_hex(material)
