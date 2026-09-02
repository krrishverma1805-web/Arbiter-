"""Persist and load the Fellegi–Sunter recalibration map (docs/28 §1.2).

`arbiter bench --calibration` fits an isotonic map from stated confidence to
observed accuracy. Persisting it as an `FS_CALIBRATION_FITTED` event, keyed to the
spec hash, means the *next* run over the same spec loads it and the matcher's
`P(match)` is already calibrated to that customer's data — the matcher gets
better with use, deterministically (it folds from the event log; `replay` is
unaffected because it never re-runs matching).

Conservative by design: the map is monotonic and bounded to [0, 1], and it is
only adopted once at least `_MIN_SAMPLES` predictions have been scored.
"""

from __future__ import annotations

from arbiter_engine.events.payloads import EventType
from arbiter_engine.events.store import EventStore

_MIN_SAMPLES = 12
_MIN_POINTS = 2


def persist_calibration(
    store: EventStore,
    run_id: str,
    spec_hash: str,
    points: list[tuple[float, float]],
    *,
    n_samples: int,
    ece_before: float,
) -> bool:
    """Emit an FS_CALIBRATION_FITTED event. Returns whether it was persisted —
    a map needs at least `_MIN_POINTS` points from `_MIN_SAMPLES` predictions to
    be worth carrying forward."""
    if len(points) < _MIN_POINTS or n_samples < _MIN_SAMPLES:
        return False
    store.append(
        run_id,
        EventType.FS_CALIBRATION_FITTED,
        {
            "spec_hash": spec_hash,
            "points": [[round(x, 6), round(y, 6)] for x, y in points],
            "n_samples": n_samples,
            "ece_before": round(ece_before, 6),
        },
    )
    return True


def load_calibration(store: EventStore, spec_hash: str) -> list[tuple[float, float]]:
    """The most recent fitted map for this spec across every run, or []."""
    latest: list[tuple[float, float]] = []
    best_n = -1
    for rid in store.runs():
        for t, p in store.iter_payloads(rid):
            if t != EventType.FS_CALIBRATION_FITTED or p.get("spec_hash") != spec_hash:
                continue
            if p.get("n_samples", 0) >= best_n:
                best_n = p["n_samples"]
                latest = [(float(x), float(y)) for x, y in p["points"]]
    return latest
