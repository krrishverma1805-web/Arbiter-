"""A tiny read-through cache (docs/28 §3 item 12).

`cache.get_or_set(key, ttl, fn)` memoises expensive derived reads — the
scorecard (folds the whole run + re-verifies the chain + re-scores), a parsed
spec. Backed by Redis when `REDIS_URL` is set (shared across API replicas), an
in-process TTL dict otherwise (fine for a single node / the demo / tests).

Keys are scoped by tenant. Anything cached here is a pure function of immutable,
append-only state (a completed run never changes), so there is no invalidation
problem — entries just expire.
"""

from __future__ import annotations

import contextlib
import json
import os
import time
from collections.abc import Callable
from typing import Any

_TTL_DEFAULT = 300
_REDIS_URL = os.environ.get("REDIS_URL", "")

_local: dict[str, tuple[float, str]] = {}
_redis: Any = None


def _client() -> Any:
    global _redis
    if not _REDIS_URL:
        return None
    if _redis is None:
        try:
            import redis

            _redis = redis.Redis.from_url(_REDIS_URL, socket_timeout=0.5)
        except Exception:  # pragma: no cover - redis optional
            _redis = False
    return _redis or None


def get_or_set(key: str, ttl: int, fn: Callable[[], Any]) -> Any:
    r = _client()
    if r is not None:  # pragma: no cover - needs a live Redis
        try:
            hit = r.get(key)
            if hit is not None:
                return json.loads(hit)
        except Exception:
            r = None
    else:
        row = _local.get(key)
        if row is not None and row[0] > time.monotonic():
            return json.loads(row[1])

    value = fn()
    blob = json.dumps(value)
    if r is not None:  # pragma: no cover
        with contextlib.suppress(Exception):
            r.setex(key, ttl, blob)
    else:
        _local[key] = (time.monotonic() + ttl, blob)
        if len(_local) > 512:  # bound the in-process cache
            for k in list(_local)[:128]:
                _local.pop(k, None)
    return value


def scoped(org_id: str, *parts: str) -> str:
    return "arb:" + org_id + ":" + ":".join(parts)


def clear() -> None:
    _local.clear()
    r = _client()
    if r is not None:  # pragma: no cover
        try:
            for k in r.scan_iter("arb:*"):
                r.delete(k)
        except Exception:
            pass


def default_ttl() -> int:
    return int(os.environ.get("ARBITER_CACHE_TTL", str(_TTL_DEFAULT)))
