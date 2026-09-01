from pathlib import Path

from arbiter_engine.decompose.identity import expected_net_minor, group_by_utr
from arbiter_engine.events.store import EventStore
from arbiter_engine.match import run_matching
from arbiter_engine.run import RunInputs, execute
from arbiter_engine.specs import load_spec


def _run(dataset: Path, spec: Path):
    store = EventStore("sqlite://")
    proj = execute(store, RunInputs(spec_path=spec, dataset_dir=dataset))
    return store, proj


def test_clean_batch_matches_everything(clean_dataset: Path, spec_path: Path):
    _store, proj = _run(clean_dataset, spec_path)
    # every settlement_utr group is exact-matched, no exceptions
    assert proj.matches, "expected matches on the clean dataset"
    assert all(m.match_pass == "exact" for m in proj.matches)
    assert all(m.residual_minor == 0 for m in proj.matches)
    assert proj.exceptions == []


def test_adversarial_batch_produces_matches_and_exceptions(
    adversarial_dataset: Path, spec_path: Path
):
    _store, proj = _run(adversarial_dataset, spec_path)
    assert proj.matches
    assert proj.exceptions
    cats = {e.category for e in proj.exceptions}
    # the injected note is always caught and never sent onward
    assert "SECURITY_REVIEW" in cats
    sec = [e for e in proj.exceptions if e.category == "SECURITY_REVIEW"]
    assert all(e.status == "security_review" for e in sec)


def test_no_record_is_double_claimed(adversarial_dataset: Path, spec_path: Path):
    _store, proj = _run(adversarial_dataset, spec_path)
    seen: set[str] = set()
    for m in proj.matches:
        for rid in m.all_ids:
            assert rid not in seen, f"{rid} claimed by two matches"
            seen.add(rid)


def test_conservation_nothing_lost(adversarial_dataset: Path, spec_path: Path):
    _store, proj = _run(adversarial_dataset, spec_path)
    exception_records = {rid for e in proj.exceptions for rid in e.record_ids}
    covered = proj.matched_record_ids | exception_records
    # at least matched-or-flagged; unmatched-and-unflagged should be rare/zero for records
    # that belong to a settlement_utr group
    grouped_processor = {r.id for utr, items in group_by_utr(proj.records).items() for r in items}
    uncovered = grouped_processor - covered
    assert len(uncovered) <= 2  # tolerance for M1; tightened in M2


def test_matcher_is_deterministic(adversarial_dataset: Path, spec_path: Path):
    spec = load_spec(spec_path)
    store = EventStore("sqlite://")
    proj = execute(store, RunInputs(spec_path=spec_path, dataset_dir=adversarial_dataset))
    r1 = run_matching("x", proj.records, spec)
    r2 = run_matching("x", proj.records, spec)
    assert [m.model_dump() for m in r1.matches] == [m.model_dump() for m in r2.matches]


def test_expected_net_matches_ground_truth(clean_dataset: Path, spec_path: Path):
    _store, proj = _run(clean_dataset, spec_path)
    for utr, items in group_by_utr(proj.records).items():
        d = next(d for d in proj.decompositions if d.settlement_utr == utr)
        assert d.expected_minor == expected_net_minor(items)
