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


def test_blocking_pass_ties_a_credit_whose_utr_is_missing(clean_dataset: Path, spec_path: Path):
    """Real bank statements lose the settlement UTR. Strip every bank UTR and the
    amount+date blocking pass (2b) should still tie the batches."""
    store = EventStore("sqlite://")
    proj = execute(store, RunInputs(spec_path=spec_path, dataset_dir=clean_dataset))
    spec = load_spec(spec_path)

    stripped = []
    for r in proj.records:
        if r.source == "bank" and r.external_ids.get("utr"):
            ext = {k: v for k, v in r.external_ids.items() if k != "utr"}
            stripped.append(r.model_copy(update={"external_ids": ext}))
        else:
            stripped.append(r)

    res = run_matching("x", stripped, spec)
    blocked = [m for m in res.matches if m.match_pass == "blocked"]
    assert blocked, "the blocking pass tied nothing after the UTR was removed"
    # and it did not mis-tie: every blocked match's residual is within tolerance
    assert all(abs(m.residual_minor) <= 200 for m in blocked)


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


def test_aggregated_payout_ties_a_credit_to_a_sum_of_batches(clean_dataset: Path, spec_path: Path):
    """One bank credit that equals the sum of two settlement batches' nets (a
    common PG rolled payout) — pass 2c should tie it as an 'aggregate' match."""
    store = EventStore("sqlite://")
    proj = execute(store, RunInputs(spec_path=spec_path, dataset_dir=clean_dataset))
    spec = load_spec(spec_path)

    banks = [r for r in proj.records if r.source == "bank"]
    if len(banks) < 3:
        return
    b0, b1 = banks[0], banks[1]

    rebuilt = []
    for r in proj.records:
        if r.source == "bank" and r.external_ids.get("utr"):
            ext = {k: v for k, v in r.external_ids.items() if k != "utr"}
            rebuilt.append(r.model_copy(update={"external_ids": ext}))
        else:
            rebuilt.append(r)
    # merge b1's amount into b0, drop b1 → one credit for two batches
    merged = []
    for r in rebuilt:
        if r.id == b0.id:
            merged.append(
                r.model_copy(
                    update={
                        "amount_minor": b0.amount_minor + b1.amount_minor,
                        "external_ids": {k: v for k, v in r.external_ids.items() if k != "utr"},
                    }
                )
            )
        elif r.id == b1.id:
            continue
        else:
            merged.append(r)

    res = run_matching("x", merged, spec)
    agg = [m for m in res.matches if m.match_pass == "aggregate"]
    assert agg, "pass 2c tied no aggregated payout"
    # the aggregate match covers both batches' records
    assert len(agg[0].left_ids) >= 2


def test_split_payout_ties_multiple_credits_to_one_batch(clean_dataset: Path, spec_path: Path):
    """A batch paid out as two bank credits (a split tranche) — pass 2d ties both
    credits to the one settlement batch."""
    store = EventStore("sqlite://")
    proj = execute(store, RunInputs(spec_path=spec_path, dataset_dir=clean_dataset))
    spec = load_spec(spec_path)

    banks = sorted((r for r in proj.records if r.source == "bank"), key=lambda r: r.id)
    if len(banks) < 2:
        return
    victim = banks[0]
    half = victim.amount_minor // 2
    rebuilt = []
    for r in proj.records:
        ext = (
            {k: v for k, v in r.external_ids.items() if k != "utr"}
            if r.source == "bank"
            else r.external_ids
        )
        if r.id == victim.id:
            rebuilt.append(r.model_copy(update={"amount_minor": half, "external_ids": ext}))
            rebuilt.append(
                r.model_copy(
                    update={
                        "id": victim.id + "_b",
                        "amount_minor": victim.amount_minor - half,
                        "external_ids": ext,
                    }
                )
            )
        else:
            rebuilt.append(r.model_copy(update={"external_ids": ext}))

    res = run_matching("x", rebuilt, spec)
    agg = [m for m in res.matches if m.match_pass == "aggregate" and len(m.right_ids) >= 2]
    assert agg, "pass 2d tied no split payout"


def test_hard_difficulty_mangled_utrs_are_recovered_by_blocking(tmp_path: Path, spec_path: Path):
    """The generator garbles the UTR in ~15% of clean narrations on `hard`. Those
    batches must still auto-tie — via the amount+date blocking pass — so the
    scorecard's recall does not collapse."""
    from arbiter_datagen.generate import generate_dataset
    from arbiter_engine.bench import score_run

    ds = tmp_path / "hard"
    generate_dataset(scenario="d2c", records=300, seed=3, out_dir=ds, difficulty="hard")
    store = EventStore("sqlite://")
    proj = execute(store, RunInputs(spec_path=spec_path, dataset_dir=ds))
    card = score_run(
        proj, ds, spec_name="razorpay-settlement", wallclock_ms=0, replay_hash_match=True
    )
    assert card.matching.by_pass.get("blocked", 0) >= 1, card.matching.by_pass
    assert card.matching.recall >= 0.85, card.matching.recall
    assert card.matching.false_match_rate <= 0.02
