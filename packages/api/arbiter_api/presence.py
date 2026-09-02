"""In-process presence + fan-out hub for the cockpit's WebSocket (docs/28 §5).

Each open cockpit joins a room keyed by `(org_id, run_id)`. The hub tells every
member who else is looking at the same run, and relays small events — an
exception was resolved, the run advanced — so two analysts on the same run stay
in sync without polling.

Single-node by design: for a multi-replica deployment swap `_Hub` for one backed
by Redis pub/sub (the interface — `join`, `leave`, `broadcast` — stays the
same). The cockpit degrades to its existing SSE + manual refresh if the socket
is unavailable.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class _Member:
    viewer_id: str
    name: str
    send: Any  # Callable[[dict], Awaitable[None]]


def _rooms_factory() -> dict[tuple[str, str], list[_Member]]:
    return defaultdict(list)


@dataclass
class _Hub:
    _rooms: dict[tuple[str, str], list[_Member]] = field(default_factory=_rooms_factory)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _loop: asyncio.AbstractEventLoop | None = None

    async def join(self, org_id: str, run_id: str, member: _Member) -> None:
        self._loop = asyncio.get_running_loop()
        async with self._lock:
            self._rooms[(org_id, run_id)].append(member)
        await self._announce(org_id, run_id)

    def broadcast_soon(self, org_id: str, run_id: str, message: dict[str, Any]) -> None:
        """Fire-and-forget from a sync request handler (which runs off the event
        loop). No-op if no cockpit has ever connected."""
        loop = self._loop
        if loop is None or not self._rooms.get((org_id, run_id)):
            return

        def _fire() -> None:
            loop.create_task(self.broadcast(org_id, run_id, message))

        loop.call_soon_threadsafe(_fire)

    async def leave(self, org_id: str, run_id: str, viewer_id: str) -> None:
        async with self._lock:
            room = self._rooms.get((org_id, run_id), [])
            self._rooms[(org_id, run_id)] = [m for m in room if m.viewer_id != viewer_id]
            if not self._rooms[(org_id, run_id)]:
                self._rooms.pop((org_id, run_id), None)
        await self._announce(org_id, run_id)

    def viewers(self, org_id: str, run_id: str) -> list[dict[str, str]]:
        return [
            {"viewer_id": m.viewer_id, "name": m.name}
            for m in self._rooms.get((org_id, run_id), [])
        ]

    async def broadcast(self, org_id: str, run_id: str, message: dict[str, Any]) -> None:
        for m in list(self._rooms.get((org_id, run_id), [])):
            with contextlib.suppress(Exception):
                await m.send(message)

    async def _announce(self, org_id: str, run_id: str) -> None:
        await self.broadcast(
            org_id, run_id, {"type": "presence", "viewers": self.viewers(org_id, run_id)}
        )


hub = _Hub()
