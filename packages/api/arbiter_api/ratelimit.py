"""Per-tenant token-bucket rate limiting (docs/28 §2).

In-memory — correct for a single API instance. A Redis-backed bucket (shared
across instances) is the multi-node upgrade and does not change this interface.

Two buckets per principal: a generous one for reads, a tight one for the
expensive writes (starting a run, merging rules).
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

_READ_RATE = float(os.environ.get("ARBITER_RL_READ_PER_MIN", "600")) / 60.0
_WRITE_RATE = float(os.environ.get("ARBITER_RL_WRITE_PER_MIN", "60")) / 60.0
_READ_BURST = float(os.environ.get("ARBITER_RL_READ_BURST", "120"))
_WRITE_BURST = float(os.environ.get("ARBITER_RL_WRITE_BURST", "20"))


@dataclass
class _Bucket:
    tokens: float
    updated: float


class RateLimiter:
    def __init__(self) -> None:
        self._b: dict[tuple[str, str], _Bucket] = {}

    def allow(self, key: str, *, write: bool) -> tuple[bool, float]:
        """(allowed, retry_after_seconds)."""
        rate = _WRITE_RATE if write else _READ_RATE
        burst = _WRITE_BURST if write else _READ_BURST
        bk = ("w" if write else "r", key)
        now = time.monotonic()
        b = self._b.get(bk)
        if b is None:
            b = _Bucket(tokens=burst, updated=now)
            self._b[bk] = b
        b.tokens = min(burst, b.tokens + (now - b.updated) * rate)
        b.updated = now
        if b.tokens >= 1.0:
            b.tokens -= 1.0
            return True, 0.0
        return False, (1.0 - b.tokens) / rate if rate > 0 else 3600.0

    def reset(self) -> None:
        self._b.clear()


limiter = RateLimiter()
