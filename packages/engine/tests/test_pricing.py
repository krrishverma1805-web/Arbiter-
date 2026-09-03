from arbiter_engine.agent.pricing import ceiling_cost, estimate_cost


def test_known_model_gets_a_real_estimate():
    c = estimate_cost("gpt-4o", 18_932, 1_075)
    assert c is not None and c > 0.0
    # ~ 18932/1e6*2.5 + 1075/1e6*10
    assert abs(c - 0.0581) < 0.002


def test_unknown_model_returns_none_never_zero():
    assert estimate_cost("some-future-model", 10_000, 5_000) is None
    assert estimate_cost("gpt-4o", 0, 0) == 0.0  # a real zero (no tokens) is still fine


def test_ceiling_cost_falls_back_conservatively_for_unknown_models():
    known = ceiling_cost("claude-opus-5", 1_000_000, 1_000_000)
    unknown = ceiling_cost("mystery", 1_000_000, 1_000_000)
    assert unknown == known  # unknown → the conservative opus-tier rate, not free
    assert unknown > 0
