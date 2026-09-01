from arbiter_engine.match.compare import amount_level, date_level, reference_level
from arbiter_engine.match.fellegi_sunter import FSModel
from arbiter_engine.match.subset import subset_sum_match
from arbiter_engine.models import Record


def _rec(rid: str, amount: int, fee: int = 0, tax: int = 0) -> Record:
    return Record(
        id=rid,
        run_id="t",
        source="razorpay_recon",
        kind="payment",
        amount_minor=amount,
        fee_minor=fee,
        tax_minor=tax,
    )


def test_strong_agreement_gives_high_probability():
    m = FSModel()
    comp = {"amount": "exact", "date": "same_day", "reference": "exact", "idlink": "shared"}
    weight, per_field = m.weight(comp)
    assert weight > 0
    assert all(v > 0 for v in per_field.values())
    p = m.probability(weight, prior=0.05)
    assert p > 0.99


def test_all_disagreement_gives_low_probability():
    m = FSModel()
    comp = {"amount": "none", "date": "none", "reference": "none", "idlink": "none"}
    weight, _ = m.weight(comp)
    assert weight < 0
    assert m.probability(weight, prior=0.05) < 0.01


def test_calibration_map_is_monotonic_and_applied():
    m = FSModel(calibration=[(0.0, 0.0), (0.5, 0.3), (1.0, 1.0)])
    assert m.probability(0.0, prior=0.5) == m._calibrate(0.5)  # weight 0 -> raw 0.5 -> 0.3
    assert abs(m._calibrate(0.5) - 0.3) < 1e-9
    assert m._calibrate(0.25) < m._calibrate(0.75)


def test_mu_estimation_from_labeled_data():
    matches = [{"amount": "exact"}] * 8 + [{"amount": "within_tol"}] * 2
    nonmatches = [{"amount": "none"}] * 9 + [{"amount": "exact"}] * 1
    m = FSModel.from_labeled(matches, nonmatches)
    m_exact, u_exact = m.mu["amount"]["exact"]
    assert m_exact > u_exact  # "exact" is far more common among matches
    assert m.field_weight("amount", "exact") > 0


def test_comparison_levels():
    assert amount_level(0, rounding=100, tol=200, expected=100000) == "exact"
    assert amount_level(50, rounding=100, tol=200, expected=100000) == "within_rounding"
    assert amount_level(150, rounding=100, tol=200, expected=100000) == "within_tol"
    assert amount_level(9999, rounding=100, tol=200, expected=100000) == "none"
    assert reference_level("RZP123ABC", "RZP123ABC") == "exact"
    assert reference_level("RZP123ABC", "XXXYYYZZZ") == "none"
    from datetime import date

    assert date_level(date(2026, 8, 4), date(2026, 8, 4), window=4) == "same_day"
    assert date_level(date(2026, 8, 4), date(2026, 8, 10), window=4) == "none"


def test_subset_sum_finds_a_unique_subset():
    items = [_rec("a", 100), _rec("b", 250), _rec("c", 700), _rec("d", 999)]
    r = subset_sum_match(items, 350, tolerance_minor=1)
    assert r is not None and not r.ambiguous
    assert sorted(i.id for i in r.items) == ["a", "b"]
    assert r.residual_minor == 0


def test_subset_sum_flags_ambiguity():
    # two different subsets both sum to 100
    items = [_rec("a", 100), _rec("b", 60), _rec("c", 40), _rec("d", 5000)]
    r = subset_sum_match(items, 100, tolerance_minor=0)
    assert r is not None
    assert r.ambiguous


def test_subset_sum_returns_none_when_impossible():
    items = [_rec("a", 100), _rec("b", 250)]
    assert subset_sum_match(items, 999999, tolerance_minor=1) is None
