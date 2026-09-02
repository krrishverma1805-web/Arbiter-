"""ISO 20022 CAMT.053 bank-statement ingestion (docs/28 §1.1).

CAMT.053 is the XML statement that is replacing MT940 at most banks. Parsed with
the stdlib (`xml.etree`) — no dependency. Each `<Ntry>` (booked entry) becomes
one row with the same canonical keys as a `bank_csv` source, so the spec's
column mapping / `extract_utr` derive / PII scrub all apply unchanged.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from arbiter_engine.events.store import EventStore
from arbiter_engine.ingest.csv_source import IngestResult, _guard_duplicate, file_hash
from arbiter_engine.ingest.tabular import ingest_rows
from arbiter_engine.specs.model import SourceSpec

MAX_BYTES = 25 * 1024 * 1024


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _find(el: ET.Element, *path: str) -> ET.Element | None:
    cur: ET.Element | None = el
    for name in path:
        if cur is None:
            return None
        cur = next((c for c in cur if _local(c.tag) == name), None)
    return cur


def _text(el: ET.Element | None) -> str:
    return (el.text or "").strip() if el is not None and el.text else ""


def _all_text(el: ET.Element | None, name: str) -> list[str]:
    if el is None:
        return []
    return [_text(c) for c in el.iter() if _local(c.tag) == name and _text(c)]


def camt_rows(xml_bytes: bytes) -> list[dict[str, str]]:
    root = ET.fromstring(xml_bytes)  # noqa: S314 - bank file, not attacker XML; no external entities in etree
    rows: list[dict[str, str]] = []
    seq = 0
    for stmt in (e for e in root.iter() if _local(e.tag) == "Stmt"):
        acct = "".join(
            _all_text(_find(stmt, "Acct"), "IBAN") or _all_text(_find(stmt, "Acct"), "Id")
        )
        for ntry in (e for e in stmt if _local(e.tag) == "Ntry"):
            seq += 1
            amt_el = _find(ntry, "Amt")
            amount = _text(amt_el)
            is_debit = _text(_find(ntry, "CdtDbtInd")).upper().startswith("DB")
            vdate = _text(_find(ntry, "ValDt", "Dt")) or _text(_find(ntry, "ValDt", "DtTm"))[:10]
            bdate = (
                _text(_find(ntry, "BookgDt", "Dt")) or _text(_find(ntry, "BookgDt", "DtTm"))[:10]
            )
            refs = (
                _all_text(ntry, "EndToEndId") + _all_text(ntry, "TxId") + _all_text(ntry, "Ustrd")
            )
            addtl = _all_text(ntry, "AddtlNtryInf")
            narration = " ".join(x for x in [*refs, *addtl] if x) or _text(
                _find(ntry, "AcctSvcrRef")
            )
            row: dict[str, str] = {
                "entity_id": f"camt-{seq}",
                "value_date": vdate or bdate,
                "posted_date": bdate or vdate,
                "type": "adjustment" if is_debit else "credit",
                "narration": narration,
                "account_no": acct,
                "amount": amount,  # magnitude; `debit` flips the sign downstream
            }
            if is_debit:
                row["debit"] = amount
            rows.append(row)
    return rows


def ingest_camt(
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

    rows = camt_rows(p.read_bytes())

    rows_in, rows_ok, rows_q, pii, reasons = ingest_rows(
        store, run_id, source_name, spec, rows, fmt="camt053", profile=profile, file_hash=fh_hash
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
