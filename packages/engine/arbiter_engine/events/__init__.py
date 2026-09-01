"""The append-only, hash-chained event store (docs/17 §2, docs/adr/0002).

Business logic writes only events. Projections (records, matches, exceptions)
are a fold over events and can always be rebuilt.
"""

from arbiter_engine.events.payloads import EVENT_PAYLOADS, EventType
from arbiter_engine.events.store import Event, EventStore

__all__ = ["Event", "EventStore", "EventType", "EVENT_PAYLOADS"]
