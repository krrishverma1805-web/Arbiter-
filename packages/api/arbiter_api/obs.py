"""Observability — structured logs, request correlation, Prometheus metrics
(docs/28 §3).

- structlog emits one JSON line per request with `request_id`, `org_id`, method,
  path, status, and duration_ms.
- every response carries `X-Request-Id` (from the client's header or a fresh id),
  so a log line, a trace, and a support ticket all point at the same request.
- `GET /metrics` exposes request counts/latency, run outcomes, and the job-queue
  depth in Prometheus text format.
"""

from __future__ import annotations

import logging
import time
import uuid
from contextvars import ContextVar
from typing import Any

import structlog
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

_request_id: ContextVar[str] = ContextVar("request_id", default="-")

REQUESTS = Counter("arbiter_http_requests_total", "HTTP requests", ["method", "path", "status"])
LATENCY = Histogram("arbiter_http_request_seconds", "HTTP request latency", ["method", "path"])
RUNS = Counter("arbiter_runs_total", "Reconciliation runs", ["outcome"])
QUEUE_DEPTH = Gauge("arbiter_job_queue_depth", "Queued jobs")


def configure() -> None:
    logging.basicConfig(format="%(message)s", level=logging.INFO)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=True,
    )


log = structlog.get_logger("arbiter.api")


def current_request_id() -> str:
    return _request_id.get()


def _route_label(path: str) -> str:
    """Collapse ids so cardinality stays bounded: /v1/runs/abc -> /v1/runs/{id}."""
    parts = []
    for seg in path.split("/"):
        parts.append("{id}" if len(seg) > 20 or (seg and any(c.isdigit() for c in seg)) else seg)
    return "/".join(parts) or "/"


async def middleware(request, call_next):  # type: ignore[no-untyped-def]
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
    _request_id.set(rid)
    structlog.contextvars.bind_contextvars(request_id=rid)
    route = _route_label(request.url.path)
    start = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        response.headers["x-request-id"] = rid
        return response
    finally:
        dur = time.perf_counter() - start
        REQUESTS.labels(request.method, route, str(status)).inc()
        LATENCY.labels(request.method, route).observe(dur)
        try:
            org = request.headers.get("x-org", "-")
        except Exception:  # pragma: no cover
            org = "-"
        log.info(
            "request",
            method=request.method,
            path=request.url.path,
            status=status,
            duration_ms=round(dur * 1000, 1),
            org=org,
        )
        structlog.contextvars.clear_contextvars()


def metrics_response() -> Any:
    from fastapi.responses import Response

    try:
        from sqlmodel import Session, func, select

        from arbiter_api.auth import _engine
        from arbiter_api.jobs import Job

        with Session(_engine()) as s:
            QUEUE_DEPTH.set(
                s.exec(select(func.count()).select_from(Job).where(Job.status == "queued")).one()
            )
    except Exception:  # pragma: no cover - metrics must never 500
        pass
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
