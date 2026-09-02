"""MT940 bank-statement ingestion (docs/28 §1.1).

MT940 is the SWIFT end-of-day statement most Indian and European banks still
ship. It is plain text — tag lines like `:61:` (a transaction) and `:86:`
(its narration) — so no dependency. Each `:61:` becomes one row with the same
canonical keys a `bank_csv` source produces (`amount` / `debit`, `value_date`,
`posted_date`, `narration`, `account_no`), so the existing spec column mapping,
`extract_utr(reference)` derive, and PII scrub all apply unchanged.

Tolerant by design: a malformed `:61:` is quarantined, not fatal; balance lines
(`:60F:` / `:62F:`) are ignored.
"""

from __future__ import annotations

import re
from pathlib import Path

from arbiter_engine.events.store import EventStore
from arbiter_engine.ingest.csv_source import IngestResult, _guard_duplicate, file_hash
from arbiter_engine.ingest.tabular import ingest_rows
from arbiter_engine.specs.model import SourceSpec

MAX_BYTES = 25 * 1024 * 1024

# :61:YYMMDD[MMDD](C|D|RC|RD|CR|DR)[funds]amount,cc N<3-char type><customer ref>[//<bank ref>]
_LINE_61 = re.compile(
    r"^(?P<vdate>\d{6})(?P<edate>\d{4})?(?P<mark>RC|RD|CR|DR|C|D)(?P<funds>[A-Z](?=\d))?"
    r"(?P<amount>[\d.,]+)N(?P<ttype>.{3})(?P<ref>[^/\n]*)(?://(?P<bankref>.*))?$"
)
_DEBIT_MARKS = ("D", "RD", "DR")


def _statement_lines(text: str) -> list[tuple[str, str]]:
    """Fold physical lines into (tag, body) pairs; continuation lines (no leading
    `:NN:`) append to the previous body."""
    out: list[list[str]] = []
    for raw in text.replace("\r\n", "\n").split("\n"):
        line = raw.rstrip()
        if not line:
            continue
        m = re.match(r"^:(\w+):(.*)$", line)
        if m:
            out.append([m.group(1), m.group(2)])
        elif out:
            out[-1][1] += " " + line.strip()
    return [(t, b) for t, b in out]


def _yymmdd(s: str) -> str:
    y = int(s[:2])
    century = 2000 if y < 70 else 1900
    return f"{century + y:04d}-{s[2:4]}-{s[4:6]}"


def mt940_rows(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    account = ""
    pending: dict[str, str] | None = None
    seq = 0

    def _flush() -> None:
        nonlocal pending
        if pending is not None:
            rows.append(pending)
            pending = None

    for tag, body in _statement_lines(text):
        if tag == "25":
            account = body.strip().split(" ")[0]
        elif tag == "61":
            _flush()
            seq += 1
            g = _LINE_61.match(body.strip())
            if g is None:  # keep it — normalize_row will quarantine "missing amount"
                pending = {"entity_id": f"mt940-{seq}", "narration": body.strip()}
                continue
            d = g.groupdict()
            amount = d["amount"].replace(".", "").replace(",", ".")
            vdate = _yymmdd(d["vdate"])
            edate = f"{vdate[:7]}-{d['edate'][2:]}" if d.get("edate") else vdate
            is_debit = d["mark"] in _DEBIT_MARKS
            pending = {
                "entity_id": f"mt940-{seq}",
                "value_date": vdate,
                "posted_date": edate,
                "type": "credit" if not is_debit else "adjustment",
                "narration": " ".join(x for x in (d.get("ref"), d.get("bankref")) if x).strip(),
                "amount": amount,  # magnitude; `debit` flips the sign downstream
            }
            if is_debit:
                pending["debit"] = amount
        elif tag == "86" and pending is not None:
            pending["narration"] = f"{pending.get('narration', '')} {body}".strip()
    _flush()
    for r in rows:
        r["account_no"] = account
    return rows


def ingest_mt940(
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

    text = p.read_text(encoding="utf-8", errors="replace")
    rows = mt940_rows(text)

    rows_in, rows_ok, rows_q, pii, reasons = ingest_rows(
        store, run_id, source_name, spec, rows, fmt="mt940", profile=profile, file_hash=fh_hash
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
