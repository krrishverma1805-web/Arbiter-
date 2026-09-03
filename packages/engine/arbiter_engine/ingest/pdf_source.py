"""PDF bank-statement ingestion (docs/28 §1.1).

Text-layer extraction only, via `pypdf` (pure-Python, no native deps — the
`[pdf]` extra). A scanned/image PDF with no text layer raises a clear error
rather than silently ingesting nothing; OCR is a separate, heavier concern.

The parser is deliberately forgiving: it walks the extracted lines, and any line
that carries a date and at least one currency amount becomes a row with the same
canonical keys a `bank_csv` source produces (`amount` / `debit`, `value_date`,
`narration`). The narration is everything on the line that isn't the date or the
amounts — the spec's `extract_utr` derive then pulls the UTR out of it.
"""

from __future__ import annotations

import re
from pathlib import Path

from arbiter_engine.events.store import EventStore
from arbiter_engine.ingest.csv_source import IngestResult, _guard_duplicate, file_hash
from arbiter_engine.ingest.tabular import ingest_rows
from arbiter_engine.specs.model import SourceSpec

MAX_BYTES = 30 * 1024 * 1024

_DATE = re.compile(
    r"\b("
    r"\d{4}-\d{2}-\d{2}"  # 2024-01-31
    r"|\d{1,2}[-/][A-Za-z]{3}[-/]\d{2,4}"  # 31-Jan-2024
    r"|\d{1,2}[-/]\d{1,2}[-/]\d{2,4}"  # 31/01/2024
    r")\b"
)
_AMOUNT = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{2,3})*(?:\.\d{2})|\d+\.\d{2})(?![\w.])")
_DR_CR = re.compile(r"\b(DR|CR|DEBIT|CREDIT)\b", re.I)


def pdf_rows(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seq = 0
    for raw in text.replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        d = _DATE.search(line)
        amounts = _AMOUNT.findall(line)
        if not d or not amounts:
            continue
        seq += 1
        # the transaction amount is the first money token; a trailing token is
        # usually the running balance — ignore it
        amt = amounts[0].replace(",", "")
        mark = _DR_CR.search(line)
        is_debit = mark is not None and mark.group(1).upper().startswith("D")
        narration = _AMOUNT.sub("", _DATE.sub("", line)).strip(" .-|")
        row: dict[str, str] = {
            "entity_id": f"pdf-{seq}",
            "value_date": d.group(1),
            "narration": narration,
            "amount": amt,
        }
        if is_debit:
            row["debit"] = amt
        rows.append(row)
    return rows


def ingest_pdf(
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

    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - the [pdf] extra isn't installed
        raise RuntimeError("PDF ingestion needs `pip install 'arbiter-engine[pdf]'`") from exc

    fh_hash = file_hash(p)
    _guard_duplicate(store, run_id, p.name, fh_hash, force)

    reader = PdfReader(str(p))
    text = "\n".join((page.extract_text() or "") for page in reader.pages)
    if not text.strip():
        raise ValueError(f"{p.name}: no text layer (a scanned PDF needs OCR, not supported here)")
    rows = pdf_rows(text)

    rows_in, rows_ok, rows_q, pii, reasons = ingest_rows(
        store, run_id, source_name, spec, rows, fmt="pdf", profile=profile, file_hash=fh_hash
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
