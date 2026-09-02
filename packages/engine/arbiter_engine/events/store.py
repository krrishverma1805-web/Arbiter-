"""Append-only, hash-chained event store over SQLite/Postgres (docs/17 §2).

Guarantees:
  - append only: no UPDATE, no DELETE (except `purge`, which is audited)
  - per-run hash chain: event.hash = sha256(prev_hash || type || actor || canonical(payload))
  - `verify()` recomputes the chain and reports any break
"""

from __future__ import annotations

import json
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import Engine, text
from sqlmodel import Field, Session, SQLModel, col, create_engine, select

from arbiter_engine.events.payloads import EventType, validate_payload
from arbiter_engine.hashing import canonical_json, chain_hash

GENESIS = ""  # prev_hash for seq 0


class Event(SQLModel, table=True):
    __tablename__ = "events"

    id: int | None = Field(default=None, primary_key=True)
    org_id: str = Field(default="local", index=True)  # tenant scope (docs/28 §2)
    run_id: str = Field(index=True)
    seq: int
    ts: str  # informational only — NOT hashed
    type: str = Field(index=True)
    payload: str  # canonical JSON — the semantic content, hash-chained
    payload_schema: int = 1
    meta: str = "{}"  # observability sidecar (timing, tokens, cost) — NOT hashed
    actor: str
    prev_hash: str
    hash: str


class ChainBroken(RuntimeError):
    def __init__(self, run_id: str, seq: int, detail: str) -> None:
        super().__init__(f"event chain broken in run {run_id} at seq {seq}: {detail}")
        self.run_id, self.seq = run_id, seq


class EventStore:
    """One instance is scoped to one tenant. Every read and write is filtered to
    `org_id`; two stores over the same database with different `org_id` cannot
    see each other's runs (docs/28 §2)."""

    def __init__(self, url: str = "sqlite://", *, org_id: str = "local") -> None:
        self.org_id = org_id
        kwargs: dict[str, Any] = {}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
        if url in ("sqlite://", "sqlite:///:memory:"):
            # a shared in-memory DB that survives across connections (for the API + tests)
            from sqlalchemy.pool import StaticPool

            kwargs["poolclass"] = StaticPool
        self.engine: Engine = create_engine(url, **kwargs)
        self._is_pg = self.engine.dialect.name == "postgresql"
        SQLModel.metadata.create_all(self.engine)

    @contextmanager
    def _session(self) -> Generator[Session]:
        """A session whose transaction is pinned to this tenant. On Postgres a
        `SET LOCAL arbiter.org_id` makes the row-level-security policy the last
        line of defence even if a query forgets its `WHERE org_id =` filter."""
        with Session(self.engine) as s:
            if self._is_pg:
                s.connection().execute(
                    text("SELECT set_config('arbiter.org_id', :o, true)"), {"o": self.org_id}
                )
            yield s

    # -- append ---------------------------------------------------------------
    def append(
        self,
        run_id: str,
        event_type: EventType,
        payload: dict[str, Any] | Any,
        *,
        actor: str = "engine",
        meta: dict[str, Any] | None = None,
    ) -> Event:
        model = validate_payload(event_type, _as_dict(payload))
        payload_json = canonical_json(model.model_dump(mode="json"))
        with self._session() as session:
            last = session.exec(
                select(Event)
                .where(Event.run_id == run_id, Event.org_id == self.org_id)
                .order_by(col(Event.seq).desc())
            ).first()
            seq = 0 if last is None else last.seq + 1
            prev_hash = GENESIS if last is None else last.hash
            h = chain_hash(
                prev_hash,
                event_type=str(event_type),
                actor=actor,
                payload=json.loads(payload_json),
            )
            ev = Event(
                org_id=self.org_id,
                run_id=run_id,
                seq=seq,
                ts=datetime.now(UTC).isoformat(),
                type=str(event_type),
                payload=payload_json,
                meta=canonical_json(meta or {}),
                actor=actor,
                prev_hash=prev_hash,
                hash=h,
            )
            session.add(ev)
            session.commit()
            session.refresh(ev)
            return ev

    # -- read ---------------------------------------------------------------
    def events(self, run_id: str) -> list[Event]:
        with self._session() as session:
            return list(
                session.exec(
                    select(Event)
                    .where(Event.run_id == run_id, Event.org_id == self.org_id)
                    .order_by(col(Event.seq))
                )
            )

    def runs(self, *, include_internal: bool = False) -> list[str]:
        """Distinct run ids for this tenant. `__`-prefixed ids are internal
        pseudo-runs (e.g. the learning loop's retrain log) and are hidden unless
        `include_internal` is set."""
        with self._session() as session:
            rows = session.exec(
                select(col(Event.run_id)).where(Event.org_id == self.org_id).distinct()
            ).all()
            ids = sorted(set(rows))
            if include_internal:
                return ids
            return [r for r in ids if not r.startswith("__")]

    def iter_payloads(self, run_id: str) -> Iterator[tuple[str, dict[str, Any]]]:
        for ev in self.events(run_id):
            yield ev.type, cast(dict[str, Any], json.loads(ev.payload))

    # -- integrity --------------------------------------------------------------
    def verify(self, run_id: str) -> dict[str, Any]:
        prev = GENESIS
        events = self.events(run_id)
        for ev in events:
            if ev.prev_hash != prev:
                raise ChainBroken(run_id, ev.seq, "prev_hash mismatch")
            expected = chain_hash(
                prev,
                event_type=ev.type,
                actor=ev.actor,
                payload=cast(dict[str, Any], json.loads(ev.payload)),
            )
            if expected != ev.hash:
                raise ChainBroken(run_id, ev.seq, "hash mismatch (payload tampered?)")
            prev = ev.hash
        return {"intact": True, "events": len(events), "terminal_hash": prev}

    _PURGE_LOG_DDL = (
        "CREATE TABLE IF NOT EXISTS purge_log (run_id TEXT, reason TEXT, by_actor TEXT, at TEXT)"
    )

    def purge(self, run_id: str, *, reason: str, by: str) -> None:
        """Hard-delete a run; record the deletion in a separate audited table."""
        with self._session() as session:
            conn = session.connection()
            conn.exec_driver_sql(self._PURGE_LOG_DDL)
            conn.exec_driver_sql(
                "INSERT INTO purge_log VALUES (?, ?, ?, ?)",
                (run_id, reason, by, datetime.now(UTC).isoformat()),
            )
            for ev in session.exec(
                select(Event).where(Event.run_id == run_id, Event.org_id == self.org_id)
            ):
                session.delete(ev)
            session.commit()


def _as_dict(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        return cast(dict[str, Any], payload)
    if hasattr(payload, "model_dump"):
        return cast(dict[str, Any], payload.model_dump(mode="python"))
    raise TypeError(f"payload must be a dict or pydantic model, got {type(payload).__name__}")
