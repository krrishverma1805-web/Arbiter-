"""Multi-currency / FX ingestion + classification (docs/28 §1.1)."""

from __future__ import annotations

from arbiter_engine.events.fold import fold_run
from arbiter_engine.events.store import EventStore
from arbiter_engine.ingest import ingest_source
from arbiter_engine.ingest.normalize import QuarantineRow, normalize_row
from arbiter_engine.specs.model import SourceSpec

_SPEC = SourceSpec(
    format="bank_csv",
    columns={"amount": "amount", "value_date": "value_date", "currency": "currency"},
    amount_scale="rupees_to_paise",
    fx={"base": "INR", "rates": {"USD": 83.2}},
)


def test_a_usd_row_is_converted_to_inr_and_keeps_the_original():
    out = normalize_row(
        {"amount": "100.00", "value_date": "2024-01-01", "currency": "USD", "entity_id": "x"},
        source_name="bank",
        spec=_SPEC,
        run_id="r",
        source_row_id="x",
        file_hash="h",
    )
    r = out.record
    assert r.currency == "INR"
    assert r.amount_minor == 832_000  # 100.00 USD * 83.2 -> 8310.00 INR -> paise
    assert r.external_ids["fx_orig_currency"] == "USD"
    assert r.external_ids["fx_orig_amount_minor"] == "10000"


def test_an_inr_row_is_untouched():
    out = normalize_row(
        {"amount": "500.00", "value_date": "2024-01-01", "currency": "INR", "entity_id": "y"},
        source_name="bank",
        spec=_SPEC,
        run_id="r",
        source_row_id="y",
        file_hash="h",
    )
    assert out.record.amount_minor == 50_000
    assert "fx_orig_currency" not in out.record.external_ids


def test_an_unknown_currency_is_quarantined():
    try:
        normalize_row(
            {"amount": "1", "value_date": "2024-01-01", "currency": "JPY", "entity_id": "z"},
            source_name="bank",
            spec=_SPEC,
            run_id="r",
            source_row_id="z",
            file_hash="h",
        )
    except QuarantineRow as e:
        assert "JPY" in str(e)
    else:
        raise AssertionError("expected a QuarantineRow for the unrated currency")


def test_end_to_end_csv_with_a_currency_column(tmp_path):
    csv = "amount,value_date,currency,entity_id\n100.00,2024-01-01,USD,a\n500.00,2024-01-02,INR,b\n"
    p = tmp_path / "bank.csv"
    p.write_text(csv)
    store = EventStore("sqlite://")
    ingest_source(store, "run1", "bank", _SPEC, p)
    recs = {r.external_ids.get("entity_id", r.id): r for r in fold_run(store, "run1").records}
    assert recs["a"].amount_minor == 832_000
    assert recs["b"].amount_minor == 50_000
