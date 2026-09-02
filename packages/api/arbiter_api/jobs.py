"""A database-backed job queue for long-running runs (docs/28 §2).

`POST /v1/runs` records a `Job` and returns immediately. When `ARBITER_ASYNC=1`
the job is left `queued` for `arbiter-api worker` to pick up; otherwise it is
executed inline (the default, so the demo and the tests need no worker).

The queue is a single table with an atomic claim (`UPDATE … WHERE status='queued'
… RETURNING`), so it survives a restart and needs no Redis. Retries and a
dead-letter status are handled by the worker.
"""

from __future__ import annotations

import json
import os
import traceback
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlmodel import Field, Session, SQLModel, select

from arbiter_api.auth import _engine

MAX_ATTEMPTS = 3
ASYNC = os.environ.get("ARBITER_ASYNC", "") not in ("", "0", "false")


class Job(SQLModel, table=True):
    __tablename__ = "jobs"

    id: int | None = Field(default=None, primary_key=True)
    org_id: str = Field(index=True)
    kind: str = "run"
    payload: str  # JSON
    status: str = Field(default="queued", index=True)  # queued|running|done|failed
    attempts: int = 0
    run_id: str | None = None
    error: str = ""
    created_at: str = ""
    updated_at: str = ""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def enqueue(org_id: str, kind: str, payload: dict[str, Any]) -> int:
    with Session(_engine()) as s:
        job = Job(
            org_id=org_id,
            kind=kind,
            payload=json.dumps(payload),
            created_at=_now(),
            updated_at=_now(),
        )
        s.add(job)
        s.commit()
        s.refresh(job)
        assert job.id is not None
        return job.id


def get(job_id: int, org_id: str | None = None) -> Job | None:
    with Session(_engine()) as s:
        job = s.get(Job, job_id)
        if job is None or (org_id is not None and job.org_id != org_id):
            return None
        return job


def recent(org_id: str, limit: int = 50) -> list[Job]:
    with Session(_engine()) as s:
        rows = s.exec(
            select(Job)
            .where(Job.org_id == org_id)
            .order_by(Job.id.desc())  # type: ignore[union-attr]
            .limit(limit)
        )
        return list(rows)


def claim() -> Job | None:
    """Atomically take the oldest queued job. Postgres and SQLite both honour
    the single-statement UPDATE, so two workers never claim the same row."""
    with Session(_engine()) as s:
        row = (
            s.connection()
            .execute(
                text(
                    "UPDATE jobs SET status='running', attempts=attempts+1, updated_at=:t "
                    "WHERE id = (SELECT id FROM jobs WHERE status='queued' "
                    "ORDER BY id LIMIT 1) RETURNING id"
                ),
                {"t": _now()},
            )
            .first()
        )
        s.commit()
        if row is None:
            return None
        return s.get(Job, row[0])


def finish(job_id: int, *, run_id: str | None, error: str | None) -> None:
    with Session(_engine()) as s:
        job = s.get(Job, job_id)
        if job is None:
            return
        if error is None:
            job.status, job.run_id = "done", run_id
        elif job.attempts >= MAX_ATTEMPTS:
            job.status, job.error = "failed", error[:2000]
        else:
            job.status, job.error = "queued", error[:2000]  # retry
        job.updated_at = _now()
        s.add(job)
        s.commit()


def run_one(job: Job) -> None:
    """Execute a claimed job. Used by the worker and by the inline path."""
    from arbiter_engine.run import RunInputs, execute

    from arbiter_api.deps import get_store
    from arbiter_api.resolve import resolve_dataset, resolve_spec

    try:
        p = json.loads(job.payload)
        spec_path = resolve_spec(p["spec"])
        ds = resolve_dataset(job.org_id, p["dataset"])
        if spec_path is None or ds is None:
            raise FileNotFoundError(f"spec or dataset not found: {p['spec']} / {p['dataset']}")
        proj = execute(
            get_store(job.org_id),
            RunInputs(
                spec_path=spec_path,
                dataset_dir=ds,
                no_ai=p.get("no_ai", False),
                model=p.get("model"),
                rerun=p.get("rerun", False),
            ),
        )
        finish(job.id or 0, run_id=proj.run_id, error=None)
        _count_run("completed")
    except Exception:  # noqa: BLE001 - the failure is recorded on the job row
        finish(job.id or 0, run_id=None, error=traceback.format_exc())
        _count_run("failed")


def _count_run(outcome: str) -> None:
    try:
        from arbiter_api.obs import RUNS

        RUNS.labels(outcome).inc()
    except Exception:  # pragma: no cover
        pass


def worker_loop(poll_seconds: float = 1.0, *, once: bool = False) -> None:
    import time

    while True:
        job = claim()
        if job is not None:
            run_one(job)
            continue
        if once:
            return
        time.sleep(poll_seconds)
