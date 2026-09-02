"""The reconciliation run — deterministic skeleton FSM (docs/12 §2).

M1 pipeline:
  RUN_STARTED
  -> INGESTING     (ingest each source -> RECORD_INGESTED)
  -> MATCHING      (pass 1 exact, pass 2 tolerant -> MATCH_CONFIRMED)
  -> DECOMPOSING   (settlement identity per utr -> DECOMPOSITION_COMPUTED)
  -> CLASSIFYING   (deterministic classifier -> EXCEPTION_OPENED / _CLASSIFIED)
  -> RUN_COMPLETED

INVESTIGATING (the agent, M3), SCORING/REPORTING (bench + memo) follow.
Everything here is deterministic and replayable.
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
from arbiter_engine.exceptions import build_exceptions
from arbiter_engine.hashing import canonical_json, sha256_hex
from arbiter_engine.ingest import ingest_source
from arbiter_engine.match import run_matching
from arbiter_engine.models import RunConfig
from arbiter_engine.specs import ReconSpec, load_spec, spec_hash


class RunInProgress(RuntimeError):
    def __init__(self, run_id: str) -> None:
        super().__init__(
            f"run {run_id} started but did not complete; pass resume=True to continue "
            "or rerun=True to start over"
        )
        self.run_id = run_id


@dataclass
class RunInputs:
    spec_path: Path
    dataset_dir: Path
    no_ai: bool = False
    seed: int | None = None
    run_id: str | None = None
    resume: bool = False  # continue a crashed run from its last committed state
    rerun: bool = False  # force a fresh run even if a completed one exists
    model: str | None = None  # override the agent model (e.g. for `bench --ablate`)


def _dataset_hash(dataset_dir: Path) -> str:
    parts = []
    for f in sorted(dataset_dir.iterdir()):
        if f.suffix.lower() in (".csv", ".xlsx", ".xlsm"):
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
    cfg_payload = cfg.model_dump(mode="json")
    if inputs.model:
        cfg_payload["agent_model"] = inputs.model
    cfg_hash = sha256_hex(canonical_json(cfg_payload))[:16]
    run_id = inputs.run_id or _deterministic_run_id(cfg_hash)

    existing = fold_run(store, run_id)
    if existing.completed and not inputs.rerun:
        return existing  # idempotent: identical config → the existing run
    if existing.started and not (inputs.resume or inputs.rerun):
        raise RunInProgress(run_id)
    if inputs.rerun and (existing.started or existing.completed):
        store.purge(run_id, reason="rerun", by="engine")

    seen = {t for t, _ in store.iter_payloads(run_id)}
    started = time.monotonic()

    if EventType.RUN_STARTED not in seen:
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

    # -- INGESTING (resumable: skip sources already ingested) --
    ingested = {
        p["source"] for t, p in store.iter_payloads(run_id) if t == EventType.SOURCE_INGESTED
    }
    for source_name, source_spec in sorted(spec.sources.items()):
        if source_name in ingested:
            continue
        src_path = _resolve_source_file(inputs.dataset_dir, source_name)
        if src_path is None:
            continue
        ingest_source(store, run_id, source_name, source_spec, src_path)

    proj = fold_run(store, run_id)
    records = proj.records

    # -- MATCHING + DECOMPOSING (deterministic; re-run in memory, emit once) --
    mr = run_matching(run_id, records, spec)
    if EventType.MATCH_CONFIRMED not in seen and EventType.DECOMPOSITION_COMPUTED not in seen:
        for decomp in mr.decompositions:
            store.append(
                run_id,
                EventType.DECOMPOSITION_COMPUTED,
                {"decomposition": decomp.model_dump(mode="json")},
            )
        for match in mr.matches:
            store.append(
                run_id, EventType.MATCH_CONFIRMED, {"match": match.model_dump(mode="json")}
            )

    # -- CLASSIFYING --
    if EventType.EXCEPTION_OPENED not in seen:
        exceptions = build_exceptions(
            run_id, records, mr.matches, mr.decompositions, spec, candidates=mr.candidates
        )
        for exc in exceptions:
            store.append(
                run_id, EventType.EXCEPTION_OPENED, {"exception": exc.model_dump(mode="json")}
            )
            if exc.classified_by != "unclassified":
                store.append(
                    run_id,
                    EventType.EXCEPTION_CLASSIFIED,
                    {
                        "exception_id": exc.id,
                        "category": exc.category or "UNEXPLAINED",
                        "classified_by": exc.classified_by,
                        "confidence": exc.confidence,
                    },
                )

    proj = fold_run(store, run_id)

    # -- INVESTIGATING (the agent — ADR-0004; skipped entirely with --no-ai) --
    if not inputs.no_ai and EventType.RUN_COMPLETED not in seen:
        from arbiter_engine.agent.orchestrate import run_investigations

        replaying = EventType.AGENT_INTERACTION in seen
        run_investigations(store, run_id, proj, spec, replay=replaying, model_override=inputs.model)
        proj = fold_run(store, run_id)

    if EventType.RUN_COMPLETED in seen:
        return proj
    counts = {
        "records": proj.record_count,
        "matched_records": len(proj.matched_record_ids),
        "matches": len(proj.matches),
        "exceptions": len(proj.exceptions),
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


_SOURCE_EXTS = (".csv", ".xlsx", ".xlsm")


def _resolve_source_file(dataset_dir: Path, source_name: str) -> Path | None:
    for ext in _SOURCE_EXTS:
        for stem in (source_name, source_name.replace("_", "-")):
            p = dataset_dir / f"{stem}{ext}"
            if p.exists():
                return p
    # loose match: e.g. source "bank" -> "bank.csv"; "razorpay_recon" -> "razorpay_recon.xlsx"
    prefix = source_name.split("_")[0]
    matches = sorted(
        p for p in dataset_dir.iterdir() if p.suffix.lower() in _SOURCE_EXTS and prefix in p.stem
    )
    return matches[0] if matches else None
