"""API authentication + a per-request principal (docs/28 §2).

Every request carries an `Authorization: Bearer <key>` header. The key is hashed
and looked up in the `api_keys` table; the row gives the org, the subject, and
the role. In `ARBITER_ENV=dev` a request with no key is allowed as the `local`
org with the `admin` role, so the demo and the test suite need no setup.

The resolved `Principal` lives in a `ContextVar` for the duration of the request,
so handlers reach it (and a tenant-scoped store) without threading it through
every signature.
"""

from __future__ import annotations

import hashlib
import secrets
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime

from arbiter_engine.events.store import EventStore
from sqlalchemy import Engine
from sqlmodel import Field, Session, SQLModel, select

from arbiter_api.deps import DB_URL, ENV, get_store

ROLES = ("viewer", "analyst", "admin")
_RANK = {r: i for i, r in enumerate(ROLES)}


class ApiKey(SQLModel, table=True):
    __tablename__ = "api_keys"

    id: int | None = Field(default=None, primary_key=True)
    key_hash: str = Field(index=True, unique=True)
    org_id: str = Field(index=True)
    subject: str
    role: str = "analyst"
    created_at: str = ""
    revoked: bool = False


@dataclass(frozen=True)
class Principal:
    org_id: str
    subject: str
    role: str


_LOCAL = Principal(org_id="local", subject="local-dev", role="admin")
_current: ContextVar[Principal] = ContextVar("principal", default=_LOCAL)


def _hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _engine() -> Engine:
    eng = get_store("local").engine  # any store; the api_keys table is not tenant-scoped
    SQLModel.metadata.create_all(eng)  # ensure api_keys exists
    return eng


def issue_key(org_id: str, subject: str, role: str = "analyst") -> str:
    if role not in ROLES:
        raise ValueError(f"role must be one of {ROLES}")
    raw = "ak_" + secrets.token_urlsafe(32)
    with Session(_engine()) as s:
        s.add(
            ApiKey(
                key_hash=_hash_key(raw),
                org_id=org_id,
                subject=subject,
                role=role,
                created_at=datetime.now(UTC).isoformat(),
            )
        )
        s.commit()
    return raw


def resolve(authorization: str | None) -> Principal | None:
    """Principal for a bearer token, or None when the token is missing/invalid.
    In dev, a missing token resolves to the local admin principal."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return _LOCAL if ENV == "dev" else None
    raw = authorization.split(" ", 1)[1].strip()
    with Session(_engine()) as s:
        row = s.exec(
            select(ApiKey).where(
                ApiKey.key_hash == _hash_key(raw),
                ApiKey.revoked == False,  # noqa: E712
            )
        ).first()
    if row is None:
        return None
    return Principal(org_id=row.org_id, subject=row.subject, role=row.role)


def set_current(p: Principal) -> None:
    _current.set(p)


def current_principal() -> Principal:
    return _current.get()


def current_store() -> EventStore:
    return get_store(_current.get().org_id)


def has_role(minimum: str) -> bool:
    return _RANK.get(current_principal().role, -1) >= _RANK[minimum]


_ = DB_URL  # keep the symbol importable for historical callers
