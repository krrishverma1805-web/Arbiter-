"""CSV ingestion (docs/13 §4, docs/14 C4).

Hardened: size + row caps, streaming read, formula-injection neutralization on
any value we might later export, duplicate-file guard via content hash.
"""

from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from arbiter_engine.events.payloads import EventType
from arbiter_engine.events.store import EventStore
from arbiter_engine.ingest.normalize import QuarantineRow, normalize_row
from arbiter_engine.specs.model import SourceSpec

MAX_BYTES = 50 * 1024 * 1024
MAX_ROWS = 100_000
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


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def neutralize_for_export(value: str) -> str:
    """Formula-injection guard for CSVs Arbiter *writes* (memo, audit pack).

    Applied on export only — never at ingest, where it would corrupt negative
    numbers like '-81348'. See docs/14 C4.
    """
    if value and value[0] in _DANGEROUS_PREFIX:
        return "'" + value
    return value


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

    fh_hash = _file_hash(p)
    if not force:
        for etype, payload in store.iter_payloads(run_id):
            if etype == EventType.SOURCE_INGESTED and payload.get("file_hash") == fh_hash:
                raise ValueError(
                    f"file {p.name} (hash {fh_hash[:12]}) already ingested in this run; "
                    "pass force=True to override"
                )

    result = IngestResult(source=source_name, file_hash=fh_hash)

    with p.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        for i, row in enumerate(reader):
            if i >= MAX_ROWS:
                raise ValueError(f"{p} exceeds the {MAX_ROWS} row cap")
            result.rows_in += 1
            row = {k: (v or "").strip() for k, v in row.items() if k is not None}
            source_row_id = row.get("entity_id") or row.get("id") or f"row{i}"
            try:
                outcome = normalize_row(
                    row,
                    source_name=source_name,
                    spec=spec,
                    run_id=run_id,
                    source_row_id=source_row_id,
                    file_hash=fh_hash,
                )
            except QuarantineRow as exc:
                result.rows_quarantined += 1
                result.quarantine_reasons.append(exc.reason)
                store.append(
                    run_id,
                    EventType.ROW_QUARANTINED,
                    {
                        "source": source_name,
                        "source_row_id": source_row_id,
                        "reason": exc.reason,
                        "raw": row,
                    },
                )
                continue

            for pii_field in outcome.pii_dropped:
                result.pii_dropped += 1
                store.append(
                    run_id,
                    EventType.PII_DROPPED,
                    {
                        "source": source_name,
                        "source_row_id": source_row_id,
                        "field": pii_field,
                        "kind": "card_number",
                    },
                )

            store.append(
                run_id,
                EventType.RECORD_INGESTED,
                {"record": outcome.record.model_dump(mode="json")},
            )
            result.rows_ok += 1

    store.append(
        run_id,
        EventType.SOURCE_INGESTED,
        {
            "source": source_name,
            "format": spec.format,
            "profile": profile,
            "rows_in": result.rows_in,
            "rows_ok": result.rows_ok,
            "rows_quarantined": result.rows_quarantined,
            "file_hash": fh_hash,
        },
    )
    return result
