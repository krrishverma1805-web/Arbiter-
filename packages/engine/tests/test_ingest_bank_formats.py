"""MT940 + CAMT.053 bank-statement ingestion (docs/28 §1.1)."""

from __future__ import annotations

from arbiter_engine.events.fold import fold_run
from arbiter_engine.events.store import EventStore
from arbiter_engine.ingest import ingest_source
from arbiter_engine.ingest.camt_source import camt_rows
from arbiter_engine.ingest.mt940_source import mt940_rows
from arbiter_engine.specs.model import SourceSpec

_BANK_SPEC = SourceSpec(
    format="mt940",
    columns={
        "amount": "amount",
        "value_date": "value_date",
        "posted_date": "posted_date",
        "reference": "narration",
        "account": "account_no",
    },
    id_fields=["utr"],
    derive={"utr": "extract_utr(reference)"},
    amount_scale="rupees_to_paise",
    untrusted_fields=["narration"],
)

MT940 = """:20:STMT-01
:25:HDFC0001234
:28C:1/1
:60F:C240101INR0,00
:61:2401010101CR12345,67NTRFRAZORPAY REF//AXISN52024010145678
:86:NEFT CR RAZORPAY SOFTWARE PVT LTD REF P2401010001
:61:2401020102D2000,00NTRFVENDOR PAYOUT//BANKREF9
:86:RTGS DR VENDOR
:62F:C240102INR10345,67
"""

CAMT = """<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02">
  <BkToCstmrStmt><Stmt>
    <Acct><Id><IBAN>IN00HDFC0001234</IBAN></Id></Acct>
    <Ntry>
      <Amt Ccy="INR">12345.67</Amt><CdtDbtInd>CRDT</CdtDbtInd>
      <BookgDt><Dt>2024-01-01</Dt></BookgDt><ValDt><Dt>2024-01-01</Dt></ValDt>
      <NtryDtls><TxDtls>
        <Refs><EndToEndId>AXISN52024010145678</EndToEndId></Refs>
        <RmtInf><Ustrd>NEFT CR RAZORPAY SOFTWARE PVT LTD</Ustrd></RmtInf>
      </TxDtls></NtryDtls>
    </Ntry>
    <Ntry>
      <Amt Ccy="INR">2000.00</Amt><CdtDbtInd>DBIT</CdtDbtInd>
      <BookgDt><Dt>2024-01-02</Dt></BookgDt><ValDt><Dt>2024-01-02</Dt></ValDt>
      <NtryDtls><TxDtls><RmtInf><Ustrd>RTGS DR VENDOR</Ustrd></RmtInf></TxDtls></NtryDtls>
    </Ntry>
  </Stmt></BkToCstmrStmt>
</Document>
"""


def test_mt940_rows_split_credit_and_debit():
    rows = mt940_rows(MT940)
    assert len(rows) == 2
    credit, debit = rows
    assert credit["amount"] == "12345.67" and "debit" not in credit
    assert credit["value_date"] == "2024-01-01"
    assert credit["account_no"] == "HDFC0001234"
    assert "AXISN52024010145678" in credit["narration"]
    assert debit["debit"] == "2000.00"  # magnitude on `amount`, sign via `debit`


def test_camt_rows_split_credit_and_debit():
    rows = camt_rows(CAMT.encode())
    assert len(rows) == 2
    assert rows[0]["amount"] == "12345.67" and "debit" not in rows[0]
    assert "AXISN52024010145678" in rows[0]["narration"]
    assert rows[1]["debit"] == "2000.00"
    assert rows[0]["account_no"] == "IN00HDFC0001234"


def _ingest(tmp_path, name: str, body: str) -> list:
    store = EventStore("sqlite://")
    p = tmp_path / name
    p.write_text(body)
    ingest_source(store, "run1", "bank", _BANK_SPEC, p)
    return fold_run(store, "run1").records


def test_mt940_end_to_end_extracts_the_utr_and_paise(tmp_path):
    recs = _ingest(tmp_path, "bank.sta", MT940)
    assert len(recs) == 2
    credit = next(r for r in recs if r.amount_minor > 0)
    assert credit.amount_minor == 1234567  # 12345.67 rupees -> paise
    assert credit.external_ids.get("utr") == "AXISN52024010145678"
    debit = next(r for r in recs if r.amount_minor < 0)
    assert debit.amount_minor == -200000


def test_camt_end_to_end(tmp_path):
    recs = _ingest(tmp_path, "bank.xml", CAMT)
    assert len(recs) == 2
    credit = next(r for r in recs if r.amount_minor > 0)
    assert credit.amount_minor == 1234567
    assert credit.external_ids.get("utr") == "AXISN52024010145678"


def test_malformed_mt940_line_is_quarantined_not_fatal(tmp_path):
    bad = MT940.replace(":61:2401020102D2000,00NTRFVENDOR PAYOUT//BANKREF9", ":61:GARBAGE")
    store = EventStore("sqlite://")
    p = tmp_path / "bank.sta"
    p.write_text(bad)
    res = ingest_source(store, "r", "bank", _BANK_SPEC, p)
    assert res.rows_ok == 1 and res.rows_quarantined == 1
