"""Shared config + store dependency (docs/13 §2)."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from arbiter_engine.events.store import EventStore

DB_URL = os.environ.get("ARBITER_DB_URL", "sqlite:///./data/arbiter.db")
SPECS_DIR = Path(os.environ.get("ARBITER_SPECS_DIR", "specs"))
DATASETS_DIR = Path(os.environ.get("ARBITER_DATASETS_DIR", "datasets"))
ENV = os.environ.get("ARBITER_ENV", "dev")


@lru_cache(maxsize=1)
def get_store() -> EventStore:
    if DB_URL.startswith("sqlite:///"):
        Path(DB_URL.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    return EventStore(DB_URL)
