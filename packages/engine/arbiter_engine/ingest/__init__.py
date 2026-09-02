"""Ingestion — normalise a source file into hash-chained RECORD_INGESTED events.

`ingest_source` dispatches on the file extension. All readers share the row loop,
header detection, and junk-row stripping in `ingest.tabular`.
"""

from __future__ import annotations

from pathlib import Path

from arbiter_engine.events.store import EventStore
from arbiter_engine.ingest.camt_source import ingest_camt
from arbiter_engine.ingest.csv_source import IngestResult, ingest_csv, neutralize_for_export
from arbiter_engine.ingest.mt940_source import ingest_mt940
from arbiter_engine.ingest.xlsx_source import ingest_xlsx
from arbiter_engine.specs.model import SourceSpec

__all__ = [
    "IngestResult",
    "ingest_camt",
    "ingest_csv",
    "ingest_mt940",
    "ingest_source",
    "ingest_xlsx",
    "neutralize_for_export",
]


def ingest_source(
    store: EventStore,
    run_id: str,
    source_name: str,
    spec: SourceSpec,
    path: str | Path,
    *,
    profile: str | None = None,
    force: bool = False,
) -> IngestResult:
    suffix = Path(path).suffix.lower()
    fmt = (getattr(spec, "format", "") or "").lower()
    # extension wins; the spec `format:` only disambiguates a bare `.txt`
    if suffix in (".xlsx", ".xlsm"):
        return ingest_xlsx(store, run_id, source_name, spec, path, profile=profile, force=force)
    if suffix in (".xml",) or (suffix not in (".csv",) and "camt" in fmt):
        return ingest_camt(store, run_id, source_name, spec, path, profile=profile, force=force)
    if suffix in (".sta", ".mt940", ".940") or (suffix not in (".csv",) and "mt940" in fmt):
        return ingest_mt940(store, run_id, source_name, spec, path, profile=profile, force=force)
    return ingest_csv(store, run_id, source_name, spec, path, profile=profile, force=force)
