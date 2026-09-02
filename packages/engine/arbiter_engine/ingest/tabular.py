"""Shared tabular ingestion — the row loop, header detection, and junk-row
stripping used by both the CSV and the XLSX readers (docs/28 §1.1).

Real bank / processor exports are not clean tables: they have title/preamble
lines above the header, a "Grand Total" or "Closing Balance" row at the bottom,
merged cells, and blank separator rows. `detect_header` finds the real header
row by matching the spec's expected column names; `is_junk_row` drops the rest.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any

from arbiter_engine.events.payloads import EventType
from arbiter_engine.events.store import EventStore
from arbiter_engine.ingest.normalize import QuarantineRow, normalize_row
from arbiter_engine.specs.model import SourceSpec

MAX_ROWS = 100_000
_TOTALS_MARKERS = (
    "grand total",
    "total",
    "closing balance",
    "opening balance",
    "subtotal",
    "balance c/f",
    "balance b/f",
)


def _norm(s: Any) -> str:
    return str(s or "").strip().lower()


def detect_header(grid: list[list[Any]], spec: SourceSpec, *, scan: int = 25) -> int:
    """Index of the row that is the real column header. Matches the spec's mapped
    source headers (case-insensitive); falls back to the first non-empty row."""
    wanted = {_norm(v) for v in spec.columns.values()} | {_norm(k) for k in spec.columns}
    wanted.discard("")
    best_i, best_hits = 0, -1
    for i, row in enumerate(grid[:scan]):
        cells = {_norm(c) for c in row if _norm(c)}
        if not cells:
            continue
        hits = len(cells & wanted)
        if hits > best_hits:
            best_i, best_hits = i, hits
        if wanted and hits >= min(2, len(wanted)):
            return i
    # no strong match — first row that has at least two non-empty cells
    if best_hits <= 0:
        for i, row in enumerate(grid[:scan]):
            if sum(1 for c in row if _norm(c)) >= 2:
                return i
    return best_i


def is_junk_row(row: dict[str, str]) -> bool:
    """A totals / balance / separator row that must not become a Record.

    Conservative: junk only when every populated cell is either a number or an
    exact totals marker, and at least one marker is present (so a narration that
    merely *contains* the word "total" never trips it)."""
    non_empty = [v.strip() for v in row.values() if v and v.strip()]
    if not non_empty:
        return True
    markers = [v for v in non_empty if _norm(v) in _TOTALS_MARKERS]
    if not markers:
        return False
    rest = [v for v in non_empty if _norm(v) not in _TOTALS_MARKERS]
    return all(_is_number(v) for v in rest)


def _is_number(s: str) -> bool:
    try:
        float(s.replace(",", "").replace("₹", "").strip())
        return True
    except ValueError:
        return False


def rows_from_grid(grid: list[list[Any]], header_idx: int) -> Iterator[dict[str, str]]:
    if header_idx >= len(grid):
        return
    headers = [str(h or "").strip() for h in grid[header_idx]]
    seen: dict[str, int] = {}
    uniq: list[str] = []
    for h in headers:
        if h in seen:
            seen[h] += 1
            uniq.append(f"{h}.{seen[h]}")
        else:
            seen[h] = 0
            uniq.append(h or f"col{len(uniq)}")
    for raw in grid[header_idx + 1 :]:
        yield {
            uniq[i]: str(raw[i]).strip() if i < len(raw) and raw[i] is not None else ""
            for i in range(len(uniq))
        }


def ingest_rows(
    store: EventStore,
    run_id: str,
    source_name: str,
    spec: SourceSpec,
    rows: Iterable[dict[str, str]],
    *,
    fmt: str,
    profile: str | None,
    file_hash: str,
) -> tuple[int, int, int, int, list[str]]:
    """Normalize an iterable of row dicts into events. Returns
    (rows_in, rows_ok, rows_quarantined, pii_dropped, quarantine_reasons)."""
    rows_in = rows_ok = rows_quarantined = pii_dropped = 0
    reasons: list[str] = []

    for i, row in enumerate(rows):
        if i >= MAX_ROWS:
            raise ValueError(f"{source_name} exceeds the {MAX_ROWS} row cap")
        row = {k: (v or "").strip() for k, v in row.items() if k is not None}
        if not any(row.values()) or is_junk_row(row):
            continue
        rows_in += 1
        source_row_id = row.get("entity_id") or row.get("id") or f"row{i}"
        try:
            outcome = normalize_row(
                row,
                source_name=source_name,
                spec=spec,
                run_id=run_id,
                source_row_id=source_row_id,
                file_hash=file_hash,
            )
        except QuarantineRow as exc:
            rows_quarantined += 1
            reasons.append(exc.reason)
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
            pii_dropped += 1
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
        rows_ok += 1

    store.append(
        run_id,
        EventType.SOURCE_INGESTED,
        {
            "source": source_name,
            "format": fmt,
            "profile": profile,
            "rows_in": rows_in,
            "rows_ok": rows_ok,
            "rows_quarantined": rows_quarantined,
            "file_hash": file_hash,
        },
    )
    return rows_in, rows_ok, rows_quarantined, pii_dropped, reasons
