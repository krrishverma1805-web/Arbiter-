"""Cross-period carry-forward (docs/28 §1.2)."""

from __future__ import annotations

from pathlib import Path

from arbiter_engine.events.store import EventStore
from arbiter_engine.match.cross_period import PriorBatch, match_carry_forward, prior_open_batches
from arbiter_engine.specs import load_spec, spec_hash

SPEC = Path(__file__).resolve().parents[3] / "specs/razorpay-settlement.yaml"


def test_match_carry_forward_prefers_utr_then_amount():
    priors = [
        PriorBatch("UTRA", 100_00, "runX", "2024-01"),
        PriorBatch("UTRB", 250_00, "runX", "2024-01"),
    ]
    assert match_carry_forward(999_99, "UTRB", priors, tol=100).settlement_utr == "UTRB"
    assert match_carry_forward(250_00, None, priors, tol=100).settlement_utr == "UTRB"
    assert match_carry_forward(777_00, None, priors, tol=100) is None


def test_prior_open_batches_only_sees_completed_same_spec_runs(tmp_path):
    store = EventStore(f"sqlite:///{tmp_path / 'c.db'}", org_id="acme")
    sh = spec_hash(load_spec(SPEC))
    # no prior runs
    assert prior_open_batches(store, sh, exclude_run_id="whatever") == []


def test_a_late_bank_credit_is_labelled_timing_not_unexplained(tmp_path, monkeypatch):
    """Two runs over two months. A batch left open in month 1 (bank credit hadn't
    landed) is closed in month 2 by the late credit — and month 2 labels it
    TIMING with a note, instead of UNEXPLAINED."""
    from arbiter_engine.events.payloads import EventType

    store = EventStore(f"sqlite:///{tmp_path / 'x.db'}", org_id="acme")
    sh = spec_hash(load_spec(SPEC))

    # --- fabricate a completed month-1 run with one open UNEXPLAINED batch ---
    from arbiter_engine.models import ReconException, Record

    rec = Record(
        id="p1",
        run_id="run-jan",
        source="razorpay_recon",
        kind="payment",
        amount_minor=500_00,
        value_date=__import__("datetime").date(2024, 1, 31),
        external_ids={"settlement_utr": "UTRJAN0001"},
        org_id="acme",
    )
    exc = ReconException(
        id="e1",
        run_id="run-jan",
        category="TIMING",
        classified_by="rule",
        amount_impact_minor=500_00,
        record_ids=["p1"],
        status="open",
    )
    for et, payload in [
        (
            EventType.RUN_STARTED,
            {
                "spec_name": "s",
                "spec_version": 1,
                "spec_hash": sh,
                "dataset_hash": "d",
                "seed": None,
                "config_hash": "c",
                "no_ai": True,
                "engine_version": "0",
            },
        ),
        (EventType.RECORD_INGESTED, {"record": rec.model_dump(mode="json")}),
        (EventType.EXCEPTION_OPENED, {"exception": exc.model_dump(mode="json")}),
        (EventType.RUN_COMPLETED, {"status": "completed", "counts": {}}),
    ]:
        store.append("run-jan", et, payload)

    priors = prior_open_batches(store, sh, exclude_run_id="run-feb")
    assert any(p.settlement_utr == "UTRJAN0001" and p.net_minor == 500_00 for p in priors)

    # --- classify a month-2 orphan credit for the same UTR/amount ---
    from arbiter_engine.exceptions.classify import build_exceptions

    late_credit = Record(
        id="b1",
        run_id="run-feb",
        source="bank",
        kind="credit",
        amount_minor=500_00,
        value_date=__import__("datetime").date(2024, 2, 3),
        external_ids={"utr": "UTRJAN0001"},
        org_id="acme",
    )
    excs = build_exceptions("run-feb", [late_credit], [], [], load_spec(SPEC), prior_batches=priors)
    assert len(excs) == 1
    assert excs[0].category == "TIMING"
    assert excs[0].classified_by == "rule:r_cross_period"
    assert "carried forward" in (excs[0].note or "")


def test_no_priors_gives_the_old_unexplained_behaviour(tmp_path):
    from arbiter_engine.exceptions.classify import build_exceptions
    from arbiter_engine.models import Record

    orphan = Record(
        id="b1",
        run_id="r",
        source="bank",
        kind="credit",
        amount_minor=123_45,
        value_date=__import__("datetime").date(2024, 2, 3),
        external_ids={"utr": "NOPE"},
    )
    excs = build_exceptions("r", [orphan], [], [], load_spec(SPEC), prior_batches=[])
    assert excs[0].category == "UNEXPLAINED"
