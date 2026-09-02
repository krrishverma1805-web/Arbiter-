"""A zero-dependency tracing shim (docs/28 §3 item 11).

`span("match", records=len(records))` is a context manager that:
  - does nothing measurable if OpenTelemetry is not installed / not configured
    (the default — `make demo`, the test suite, the CI docker image all stay
    dependency-free), so the engine never hard-depends on OTel;
  - opens a real OTel span with those attributes when a tracer provider is
    configured (the API sets one up from `OTEL_EXPORTER_OTLP_ENDPOINT` — see
    `arbiter_api.obs`), giving the span tree the roadmap wants: run → each pass
    → each tool call → each LLM call.

Nothing here changes the event stream or any hash — traces are a pure sidecar.
"""

from __future__ import annotations

import contextlib
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

_tracer: Any | None = None


def configure_tracing(service_name: str = "arbiter") -> bool:
    """Wire the engine's spans to whatever tracer provider the process has set
    up. Safe to call more than once and safe to call when OTel is absent."""
    global _tracer
    try:
        from opentelemetry import trace
    except Exception:
        return False
    _tracer = trace.get_tracer(service_name)
    return True


@contextmanager
def span(name: str, **attrs: Any) -> Generator[None]:
    if _tracer is None:
        yield
        return
    with _tracer.start_as_current_span(name) as sp:  # pragma: no cover - needs OTel
        for k, v in attrs.items():
            with contextlib.suppress(Exception):
                sp.set_attribute(k, v)
        yield


def set_attribute(key: str, value: Any) -> None:
    if _tracer is None:
        return
    with contextlib.suppress(Exception):  # pragma: no cover - needs OTel
        from opentelemetry import trace

        trace.get_current_span().set_attribute(key, value)
