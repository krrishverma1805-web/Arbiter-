"""Counterparty entity resolution (docs/28 §1.2)."""

from __future__ import annotations

from arbiter_engine.match.entity import canonical_entity, same_entity


def test_legal_forms_and_punctuation_collapse():
    forms = [
        "ACME SOFTWARE PVT LTD",
        "Acme Software Private Limited",
        "ACME SOFTWARE PVT. LTD.",
        "M/S Acme Software",
        "NEFT CR ACME SOFTWARE PVT LTD",
        "acme  software   pvt   ltd",
    ]
    keys = {canonical_entity(f) for f in forms}
    assert keys == {"acme software"}


def test_empty_and_none():
    assert canonical_entity(None) == ""
    assert canonical_entity("   ") == ""
    assert canonical_entity("PVT LTD") == ""  # all noise


def test_same_entity_handles_subsets_and_rejects_unknowns():
    assert same_entity("Acme Software Pvt Ltd", "ACME SOFTWARE")
    assert same_entity("Acme", "Acme Software Solutions")  # abbreviation
    assert not same_entity("Acme Software", "Globex Corp")
    assert not same_entity("Acme", None)


def test_counterparty_history_tool_resolves_name_variants():
    from arbiter_engine.agent.tools import RunSnapshot, Tools

    snap = RunSnapshot(
        records={},
        matches=[],
        decompositions=[],
        exceptions=[],
        prior_counterparties={"acme software": [{"run": "r1", "amount_minor": 100}]},
    )
    out = Tools(snap).counterparty_history(counterparty="ACME SOFTWARE PVT. LTD.")
    assert out["resolved_entity"] == "acme software"
    assert out["prior_activity"] == [{"run": "r1", "amount_minor": 100}]
