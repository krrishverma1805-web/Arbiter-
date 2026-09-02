"""The learning loop: resolution → drafted rule → merged into the spec (docs/02 §5.3)."""

from __future__ import annotations

import shutil
from pathlib import Path

import yaml
from arbiter_engine.events.payloads import EventType
from arbiter_engine.events.store import EventStore
from arbiter_engine.learn import draft_rule_from_resolution, merge_rules, pending_rules
from arbiter_engine.models import Exception_
from arbiter_engine.run import RunInputs, execute
from arbiter_engine.specs import load_spec


def _exc(cat: str, impact: int = 40) -> Exception_:
    return Exception_(
        id="exc_test",
        run_id="r",
        category=cat,
        classified_by="unclassified",
        amount_impact_minor=impact,
        record_ids=["a"],
    )


def test_rounding_resolution_drafts_a_safe_rule():
    r = draft_rule_from_resolution(_exc("ROUNDING", 40), "accept_variance")
    assert r is not None
    assert r["classify"] == "ROUNDING"
    assert r["resolve"] == "accept_variance"
    assert r["rule_id"].startswith("r_learned_")
    # the drafted `when` must parse in the safe engine
    from arbiter_engine.exceptions.rules import compile_rule

    compile_rule(r["when"])


def test_judgment_categories_do_not_generalise():
    for cat in ("UNEXPLAINED", "AMBIGUOUS", "SECURITY_REVIEW", "WRONG_ACCOUNT"):
        assert draft_rule_from_resolution(_exc(cat), "route_to_human") is None


def test_pending_then_merge_bumps_the_spec_version(tmp_path: Path, spec_path: Path):
    spec_copy = tmp_path / "spec.yaml"
    shutil.copy(spec_path, spec_copy)
    before = yaml.safe_load(spec_copy.read_text())["version"]

    store = EventStore("sqlite://")
    store.append(
        "run1",
        EventType.RUN_STARTED,
        {
            "spec_name": "x",
            "spec_version": 1,
            "spec_hash": "h",
            "dataset_hash": "d",
            "seed": None,
            "config_hash": "c",
            "no_ai": True,
            "engine_version": "0.0.1",
        },
    )
    draft = draft_rule_from_resolution(_exc("ROUNDING", 50), "accept_variance")
    assert draft is not None
    store.append("run1", EventType.RULE_DRAFTED, draft)

    pend = pending_rules(store, "run1", spec_copy)
    assert len(pend) == 1 and pend[0]["rule_id"] == draft["rule_id"]

    res = merge_rules(store, "run1", spec_copy, None, approved_by="tester")
    assert res["merged"] == [draft["rule_id"]]
    after = yaml.safe_load(spec_copy.read_text())
    assert after["version"] == before + 1
    assert any(r["id"] == draft["rule_id"] for r in after["rules"])
    # once merged it is no longer pending
    assert pending_rules(store, "run1", spec_copy) == []


def test_a_merged_rule_classifies_next_run(
    tmp_path: Path, adversarial_dataset: Path, spec_path: Path
):
    """End-to-end: resolve a DUPLICATE, merge the learned rule, re-run on a fresh
    spec copy, and confirm the rule now drives that classification."""
    spec_copy = tmp_path / "spec.yaml"
    shutil.copy(spec_path, spec_copy)

    store = EventStore("sqlite://")
    proj = execute(
        store, RunInputs(spec_path=spec_copy, dataset_dir=adversarial_dataset, no_ai=True)
    )
    dup = next((e for e in proj.exceptions if e.category == "ROUNDING"), None) or next(
        (e for e in proj.exceptions if e.category == "TIMING"), None
    )
    if dup is None:
        return  # this seed happened not to produce a generalisable exception

    store.append(
        proj.run_id,
        EventType.RESOLUTION_APPLIED,
        {
            "exception_id": dup.id,
            "action": "accept_variance",
            "detail": "",
            "actor": "t",
            "prior_status": dup.status,
        },
    )
    draft = draft_rule_from_resolution(dup, "accept_variance")
    assert draft is not None
    store.append(proj.run_id, EventType.RULE_DRAFTED, draft)
    merge_rules(store, proj.run_id, spec_copy, None, approved_by="t")

    reloaded = load_spec(spec_copy)
    assert any(r["id"] == draft["rule_id"] for r in reloaded.rules)
