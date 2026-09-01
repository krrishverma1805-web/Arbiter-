"""The reconciliation run — M0 slice (docs/10 M0, docs/12 §2).

M0 pipeline:  RUN_STARTED -> ingest each source -> RUN_COMPLETED.
The deterministic skeleton FSM (MATCHING, DECOMPOSING, CLASSIFYING, INVESTIGATING,
SCORING, REPORTING) is added in M1-M3. Everything here is deterministic and
replayable.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from arbiter_engine import __version__
from arbiter_engine.events.fold import RunProjection, fold_run
from arbiter_engine.events.payloads import EventType
from arbiter_engine.events.store import EventStore
from arbiter_engine.hashing import canonical_json, sha256_hex
from arbiter_engine.ingest.csv_source import ingest_csv
from arbiter_engine.models import RunConfig
from arbiter_engine.specs import ReconSpec, load_spec, spec_hash


@dataclass
class RunInputs:
    spec_path: Path
    dataset_dir: Path
    no_ai: bool = False
    seed: int | None = None
    run_id: str | None = None


def _dataset_hash(dataset_dir: Path) -> str:
    parts = []
    for f in sorted(dataset_dir.glob("*.csv")):
        parts.append(f"{f.name}:{sha256_hex(f.read_bytes().decode('utf-8', 'replace'))}")
    return sha256_hex("|".join(parts))[:16]


def _deterministic_run_id(cfg_hash: str) -> str:
    # stable id from config so identical inputs are idempotent (docs/17 §7)
    return str(uuid.UUID(bytes=bytes.fromhex(sha256_hex(cfg_hash)[:32])))


def execute(store: EventStore, inputs: RunInputs) -> RunProjection:
    spec: ReconSpec = load_spec(inputs.spec_path)
    sh = spec_hash(spec)
    dh = _dataset_hash(inputs.dataset_dir)
    cfg = RunConfig(
        spec_name=spec.name,
        spec_version=spec.version,
        spec_hash=sh,
        dataset_hash=dh,
        seed=inputs.seed,
        no_ai=inputs.no_ai,
    )
    cfg_hash = sha256_hex(canonical_json(cfg.model_dump(mode="json")))[:16]
    run_id = inputs.run_id or _deterministic_run_id(cfg_hash)

    # idempotency: a completed run with this exact config already exists
    existing = fold_run(store, run_id)
    if existing.completed:
        return existing

    started = time.monotonic()
    store.append(
        run_id,
        EventType.RUN_STARTED,
        {
            "spec_name": spec.name,
            "spec_version": spec.version,
            "spec_hash": sh,
            "dataset_hash": dh,
            "seed": inputs.seed,
            "config_hash": cfg_hash,
            "no_ai": inputs.no_ai,
            "engine_version": __version__,
        },
    )

    for source_name, source_spec in sorted(spec.sources.items()):
        csv_path = _resolve_source_file(inputs.dataset_dir, source_name)
        if csv_path is None:
            continue
        ingest_csv(store, run_id, source_name, source_spec, csv_path)

    proj = fold_run(store, run_id)
    counts = {
        "records": proj.record_count,
        "quarantined": proj.quarantined,
        "pii_dropped": proj.pii_dropped,
        **proj.by_source(),
    }
    store.append(
        run_id,
        EventType.RUN_COMPLETED,
        {"status": "completed", "counts": counts},
        meta={"wallclock_ms": int((time.monotonic() - started) * 1000)},
    )
    return fold_run(store, run_id)


def _resolve_source_file(dataset_dir: Path, source_name: str) -> Path | None:
    for candidate in (f"{source_name}.csv", f"{source_name.replace('_', '-')}.csv"):
        p = dataset_dir / candidate
        if p.exists():
            return p
    # loose match: e.g. source "bank" -> "bank.csv"; "razorpay_recon" -> "razorpay_recon.csv"
    matches = sorted(p for p in dataset_dir.glob("*.csv") if source_name.split("_")[0] in p.stem)
    return matches[0] if matches else None
