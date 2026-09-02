"""CSV ingestion (docs/13 §4, docs/14 C4).

Hardened: size + row caps, formula-injection neutralization on any value we might
later export, duplicate-file guard via content hash. The row loop, header
detection, and junk-row stripping are shared with the XLSX reader
(`ingest.tabular`).
"""

from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from arbiter_engine.events.payloads import EventType
from arbiter_engine.events.store import EventStore
from arbiter_engine.ingest.tabular import detect_header, ingest_rows, rows_from_grid
from arbiter_engine.specs.model import SourceSpec

MAX_BYTES = 50 * 1024 * 1024
_DANGEROUS_PREFIX = ("=", "+", "-", "@")


@dataclass
class IngestResult:
    source: str
    rows_in: int = 0
    rows_ok: int = 0
    rows_quarantined: int = 0
    pii_dropped: int = 0
    file_hash: str = ""
    quarantine_reasons: list[str] = field(default_factory=list)


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


_file_hash = file_hash  # backwards-compatible alias


def neutralize_for_export(value: str) -> str:
    """Formula-injection guard for CSVs Arbiter *writes* (memo, audit pack).

    Applied on export only — never at ingest, where it would corrupt negative
    numbers like '-81348'. See docs/14 C4.
    """
    if value and value[0] in _DANGEROUS_PREFIX:
        return "'" + value
    return value


def _guard_duplicate(store: EventStore, run_id: str, name: str, fh_hash: str, force: bool) -> None:
    if force:
        return
    for etype, payload in store.iter_payloads(run_id):
        if etype == EventType.SOURCE_INGESTED and payload.get("file_hash") == fh_hash:
            raise ValueError(
                f"file {name} (hash {fh_hash[:12]}) already ingested in this run; "
                "pass force=True to override"
            )


def _read_csv_grid(path: Path) -> list[list[str]]:
    """Best-effort text decode, then the whole sheet as rows of strings."""
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = path.read_text(encoding=enc)
            break
        except UnicodeDecodeError:
            continue
    else:  # pragma: no cover - latin-1 never raises
        text = path.read_text(encoding="latin-1", errors="replace")
    # pick the delimiter only if a non-comma clearly dominates the first line
    first = next((ln for ln in text.splitlines() if ln.strip()), "")
    delim = ","
    for cand in (";", "\t", "|"):
        if first.count(cand) > first.count(delim):
            delim = cand
    return [list(row) for row in csv.reader(text.splitlines(), delimiter=delim)]


def ingest_csv(
    store: EventStore,
    run_id: str,
    source_name: str,
    spec: SourceSpec,
    path: str | Path,
    *,
    profile: str | None = None,
    force: bool = False,
) -> IngestResult:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"source file not found: {p}")
    if p.stat().st_size > MAX_BYTES:
        raise ValueError(f"{p} exceeds the {MAX_BYTES // 1024 // 1024} MB cap")

    fh_hash = file_hash(p)
    _guard_duplicate(store, run_id, p.name, fh_hash, force)

    grid = _read_csv_grid(p)
    header_idx = spec.header_row if spec.header_row is not None else detect_header(grid, spec)
    rows = rows_from_grid(grid, header_idx)

    rows_in, rows_ok, rows_q, pii, reasons = ingest_rows(
        store, run_id, source_name, spec, rows, fmt="csv", profile=profile, file_hash=fh_hash
    )
    return IngestResult(
        source=source_name,
        rows_in=rows_in,
        rows_ok=rows_ok,
        rows_quarantined=rows_q,
        pii_dropped=pii,
        file_hash=fh_hash,
        quarantine_reasons=reasons,
    )
