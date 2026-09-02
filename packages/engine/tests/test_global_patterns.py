"""Opt-in global pattern library (docs/28 §3 item 15)."""

from __future__ import annotations

import json

from arbiter_engine.learn import global_patterns as gp
from arbiter_engine.models import ReconException, Record


def _exc(cat: str = "ROUNDING", impact: int = 40) -> tuple[ReconException, list[Record]]:
    recs = [
        Record(
            id="r1",
            run_id="run",
            source="bank",
            kind="credit",
            amount_minor=500_00,
            counterparty="ACME PVT LTD",
            reference="UTR123456789",
            external_ids={"settlement_utr": "UTR123456789"},
        )
    ]
    exc = ReconException(
        id="e1",
        run_id="run",
        category=cat,
        classified_by="rule",
        amount_impact_minor=impact,
        record_ids=["r1"],
    )
    return exc, recs


def test_anon_shape_leaks_no_identifiers():
    exc, recs = _exc()
    shape = gp.anon_shape(exc, recs)
    blob = json.dumps(shape).upper()
    for secret in ("ACME", "UTR123456789", "50000", "R1", "RUN"):
        assert secret not in blob
    assert shape["category"] == "ROUNDING"
    assert shape["has_counterparty"] is True and shape["has_reference"] is True


def test_off_by_default_is_a_hard_no_op(tmp_path, monkeypatch):
    monkeypatch.setattr(gp, "_MODE", "off")
    monkeypatch.setattr(gp, "_DB", f"sqlite:///{tmp_path / 'g.db'}")
    exc, recs = _exc()
    assert gp.contribute("acme", exc, recs, "accept_variance") is False
    assert gp.recall_global(exc, recs) == []


def test_local_org_never_contributes(tmp_path, monkeypatch):
    monkeypatch.setattr(gp, "_MODE", "contribute")
    monkeypatch.setattr(gp, "_DB", f"sqlite:///{tmp_path / 'g.db'}")
    exc, recs = _exc()
    assert gp.contribute("local", exc, recs, "accept_variance") is False


def test_two_tenants_same_shape_aggregate_without_identity(tmp_path, monkeypatch):
    monkeypatch.setattr(gp, "_MODE", "contribute")
    monkeypatch.setattr(gp, "_DB", f"sqlite:///{tmp_path / 'g.db'}")
    exc, recs = _exc()
    gp.contribute("acme", exc, recs, "accept_variance")
    gp.contribute("beta", exc, recs, "accept_variance")
    gp.contribute("beta", *_exc(), "accept_variance")  # same tenant again

    hits = gp.recall_global(exc, recs)
    assert hits and hits[0].action == "accept_variance"
    assert hits[0].distinct_tenants == 2
    assert hits[0].occurrences == 3

    # a consumer that only reads still sees the aggregate
    monkeypatch.setattr(gp, "_MODE", "consume")
    assert gp.recall_global(exc, recs)[0].distinct_tenants == 2
    assert gp.contribute("gamma", exc, recs, "x") is False


def test_similar_exceptions_tool_surfaces_the_network(tmp_path, monkeypatch):
    monkeypatch.setattr(gp, "_MODE", "contribute")
    monkeypatch.setattr(gp, "_DB", f"sqlite:///{tmp_path / 'g.db'}")
    exc, recs = _exc()
    gp.contribute("acme", exc, recs, "accept_variance")

    from arbiter_engine.agent.tools import RunSnapshot, Tools

    snap = RunSnapshot(records={"r1": recs[0]}, matches=[], decompositions=[], exceptions=[exc])
    out = Tools(snap, exc).similar_exceptions()
    assert out["from_the_network"][0]["resolution"] == "accept_variance"
