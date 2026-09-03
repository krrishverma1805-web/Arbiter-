"""PDF bank-statement ingestion (docs/28 §1.1)."""

from __future__ import annotations

import pytest

pytest.importorskip("pypdf", reason="needs the arbiter-engine[pdf] extra")

from arbiter_engine.ingest.pdf_source import ingest_pdf, pdf_rows  # noqa: E402
from arbiter_engine.specs.model import SourceSpec  # noqa: E402

_TEXT = """\
HDFC BANK — Statement of account 00123456789
Date        Narration                                   Withdrawal   Deposit    Balance
2024-01-01  NEFT CR RAZORPAY SOFTWARE PVT LTD UTR AXISN52024010145678   12,345.67  1,00,000.00
2024-01-02  RTGS DR VENDOR PAYOUT BANKREF9              2,000.00                  98,000.00
Opening Balance                                                       0.00
2024-01-03  UPI CR CUSTOMER REFUND                                      500.00    98,500.00
"""


def test_pdf_rows_pulls_dated_amount_lines():
    rows = pdf_rows(_TEXT)
    assert len(rows) == 3
    r0 = rows[0]
    assert r0["value_date"] == "2024-01-01"
    assert r0["amount"] == "12345.67" and "debit" not in r0
    assert "AXISN52024010145678" in r0["narration"]
    assert rows[1]["debit"] == "2000.00"  # "DR" on the line


def test_pdf_rows_ignores_headers_and_balance_lines():
    rows = pdf_rows(_TEXT)
    assert not any("Statement of account" in r["narration"] for r in rows)
    assert not any("Opening Balance" in r["narration"] for r in rows)


def test_a_pdf_with_no_text_layer_raises_clearly(tmp_path):
    from arbiter_engine.events.store import EventStore
    from pypdf import PdfWriter

    w = PdfWriter()
    w.add_blank_page(width=200, height=200)
    p = tmp_path / "scan.pdf"
    with p.open("wb") as fh:
        w.write(fh)

    spec = SourceSpec(format="bank_pdf", columns={"amount": "amount"})
    with pytest.raises(ValueError, match="no text layer"):
        ingest_pdf(EventStore("sqlite://"), "r", "bank", spec, p)
