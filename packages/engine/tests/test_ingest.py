from pathlib import Path

from arbiter_engine.events.store import EventStore
from arbiter_engine.ingest.csv_source import ingest_csv
from arbiter_engine.specs import load_spec


def test_ingests_the_clean_dataset(clean_dataset: Path, spec_path: Path):
    spec = load_spec(spec_path)
    store = EventStore("sqlite://")
    res = ingest_csv(
        store,
        "run1",
        "razorpay_recon",
        spec.sources["razorpay_recon"],
        clean_dataset / "razorpay_recon.csv",
    )
    assert res.rows_ok > 0
    assert res.rows_quarantined == 0
    assert res.file_hash


def test_duplicate_file_is_refused(clean_dataset: Path, spec_path: Path):
    spec = load_spec(spec_path)
    store = EventStore("sqlite://")
    src = spec.sources["bank"]
    ingest_csv(store, "run2", "bank", src, clean_dataset / "bank.csv")
    try:
        ingest_csv(store, "run2", "bank", src, clean_dataset / "bank.csv")
    except ValueError as exc:
        assert "already ingested" in str(exc)
    else:
        raise AssertionError("expected a duplicate-file ValueError")


def test_row_with_no_amount_is_quarantined(tmp_path: Path, spec_path: Path):
    spec = load_spec(spec_path)
    bad = tmp_path / "bank.csv"
    bad.write_text(
        "amount,value_date,narration,account_no\n"
        ",2026-08-04,NEFT CR UTR RZP123,XX01\n"
        "5000,2026-08-04,NEFT CR UTR RZP124,XX01\n"
    )
    store = EventStore("sqlite://")
    res = ingest_csv(store, "run3", "bank", spec.sources["bank"], bad)
    assert res.rows_in == 2
    assert res.rows_ok == 1
    assert res.rows_quarantined == 1


def test_full_card_number_is_dropped_and_flagged(tmp_path: Path, spec_path: Path):
    spec = load_spec(spec_path)
    f = tmp_path / "razorpay_recon.csv"
    # 4111111111111111 is a well-known Luhn-valid test PAN
    f.write_text(
        "entity_id,type,debit,credit,amount,fee,tax,currency,settlement_utr,settlement_id,"
        "created_at,settled_at,payment_id,order_id,order_receipt,method,card_network,card_type,"
        "dispute_id,description,notes\n"
        "pay_1,payment,0,100000,100000,1800,324,INR,RZP1,setl_1,1754000000,1754200000,"
        "pay_1,ord_1,rc1,card,VISA,credit,,Paid with 4111 1111 1111 1111,\n"
    )
    store = EventStore("sqlite://")
    res = ingest_csv(store, "run4", "razorpay_recon", spec.sources["razorpay_recon"], f)
    assert res.pii_dropped >= 1
    from arbiter_engine.events.fold import fold_run

    proj = fold_run(store, "run4")
    assert "4111111111111111" not in str(proj.records[0].untrusted)
