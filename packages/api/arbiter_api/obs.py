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
import os
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


def configure_sentry() -> bool:
    """Error + performance monitoring, on only when `SENTRY_DSN` is set and the
    optional `sentry-sdk` is installed (the `[observability]` extra)."""
    dsn = os.environ.get("SENTRY_DSN")
    if not dsn:
        return False
    try:
        import sentry_sdk
    except Exception:  # pragma: no cover - extra not installed
        log.warning("sentry_dsn_set_but_sdk_missing")
        return False
    sentry_sdk.init(  # pragma: no cover - needs the extra + a DSN
        dsn=dsn,
        environment=os.environ.get("ARBITER_ENV", "dev"),
        release=os.environ.get("ARBITER_RELEASE"),
        traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
        send_default_pii=False,
    )
    return True


def configure_tracing(app: Any = None) -> bool:
    """OpenTelemetry span export, on only when `OTEL_EXPORTER_OTLP_ENDPOINT` is
    set and the `[observability]` extra is installed. Instruments FastAPI and
    SQLAlchemy, and wires the engine's `tracing.span(...)` calls into the same
    provider so the trace is one tree: request → run → pass → tool → LLM call."""
    if not os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        return False
    try:  # pragma: no cover - needs the extra
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except Exception:  # pragma: no cover
        log.warning("otel_endpoint_set_but_sdk_missing")
        return False

    svc = os.environ.get("OTEL_SERVICE_NAME", "arbiter-api")
    provider = TracerProvider(  # pragma: no cover - needs the extra
        resource=Resource.create({"service.name": svc})
    )
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)

    try:  # pragma: no cover - needs the extra
        if app is not None:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

            FastAPIInstrumentor.instrument_app(app)
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        SQLAlchemyInstrumentor().instrument()
    except Exception:  # pragma: no cover
        pass

    from arbiter_engine.tracing import configure_tracing as _engine_tracing  # pragma: no cover

    _engine_tracing("arbiter-engine")  # pragma: no cover
    return True


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
