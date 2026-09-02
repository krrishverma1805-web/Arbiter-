"""Idempotency keys for mutating requests (docs/28 §2).

A client that retries `POST /v1/runs` or `.../resolve` after a network blip must
not enqueue a second run or apply a resolution twice. If the request carries an
`Idempotency-Key` header, the first response for `(org, key)` is stored and every
later request with the same key gets that stored response back — for 24 h.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlmodel import Field, Session, SQLModel, select

from arbiter_api.auth import _engine

TTL = timedelta(hours=24)


class IdempotencyRecord(SQLModel, table=True):
    __tablename__ = "idempotency_keys"

    id: int | None = Field(default=None, primary_key=True)
    org_id: str = Field(index=True)
    key: str = Field(index=True)
    request_hash: str
    response: str  # JSON
    status_code: int = 200
    created_at: str = ""


def _rhash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def lookup(org_id: str, key: str, request_payload: Any) -> tuple[int, Any] | None:
    """A stored (status, body) for this key, or None. Raises if the same key was
    used for a *different* request body (a client bug worth surfacing)."""
    if not key:
        return None
    cutoff = (datetime.now(UTC) - TTL).isoformat()
    with Session(_engine()) as s:
        row = s.exec(
            select(IdempotencyRecord).where(
                IdempotencyRecord.org_id == org_id,
                IdempotencyRecord.key == key,
                IdempotencyRecord.created_at >= cutoff,
            )
        ).first()
    if row is None:
        return None
    if row.request_hash != _rhash(request_payload):
        raise ValueError("Idempotency-Key reused with a different request body")
    return row.status_code, json.loads(row.response)


def store(org_id: str, key: str, request_payload: Any, status_code: int, body: Any) -> None:
    if not key:
        return
    with Session(_engine()) as s:
        s.add(
            IdempotencyRecord(
                org_id=org_id,
                key=key,
                request_hash=_rhash(request_payload),
                response=json.dumps(body, default=str),
                status_code=status_code,
                created_at=datetime.now(UTC).isoformat(),
            )
        )
        s.commit()
