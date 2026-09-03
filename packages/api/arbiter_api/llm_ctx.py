"""Per-request LLM credentials (bring-your-own-key).

The cockpit can send an LLM provider + key + model as request headers on
``POST /v1/runs``. For the **inline** run path this module applies them to the
process environment for the duration of that one ``execute()`` call and restores
the previous values afterwards, under a lock. The key is never written to the
job payload, the event log, or a request log — it lives only for the run.

Async (worker) runs don't get this: the worker is a separate process, so a
bring-your-own key would have to be persisted. Set the key in the worker's
environment instead.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager

_lock = threading.Lock()

# every LLM-selecting variable the engine reads — cleared before the override is
# applied so a server-side key can't leak into a caller's run
_MANAGED = (
    "ARBITER_LLM_PROVIDER",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "ARBITER_OPENAI_MODEL",
)


def from_headers(headers: object) -> dict[str, str] | None:
    """Parse ``X-LLM-Provider`` / ``X-LLM-Key`` / ``X-LLM-Model`` into an env
    override, or ``None`` if no key was sent."""
    get = getattr(headers, "get", None)
    if get is None:
        return None
    key = (get("x-llm-key") or "").strip()
    if not key:
        return None
    provider = (get("x-llm-provider") or "").strip().lower()
    model = (get("x-llm-model") or "").strip()
    if provider not in ("openai", "anthropic"):
        provider = "anthropic" if key.startswith("sk-ant") else "openai"
    env: dict[str, str] = {"ARBITER_LLM_PROVIDER": provider}
    if provider == "openai":
        env["OPENAI_API_KEY"] = key
        if model:
            env["ARBITER_OPENAI_MODEL"] = model
    else:
        env["ANTHROPIC_API_KEY"] = key
    return env


@contextmanager
def applied(env: dict[str, str] | None) -> Iterator[None]:
    if not env:
        yield
        return
    with _lock:
        saved = {k: os.environ.get(k) for k in _MANAGED}
        try:
            for k in _MANAGED:
                os.environ.pop(k, None)
            os.environ.update(env)
            yield
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
