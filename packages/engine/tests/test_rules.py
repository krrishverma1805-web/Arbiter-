from types import SimpleNamespace

import pytest
from arbiter_engine.exceptions.rules import (
    RuleContext,
    RuleEngine,
    RuleError,
    compile_rule,
    evaluate,
)


def _ctx(**vars):
    return RuleContext(
        variables=vars,
        functions={
            "abs": abs,
            "is_empty": lambda x: not x,
            "ts_day": lambda d: getattr(d, "day", 99),
        },
    )


def test_safe_expression_evaluates():
    tree = compile_rule("exception.residual_minor != 0 and abs(exception.residual_minor) <= 100")
    assert evaluate(tree, _ctx(exception=SimpleNamespace(residual_minor=50))) is True
    assert evaluate(tree, _ctx(exception=SimpleNamespace(residual_minor=500))) is False
    assert evaluate(tree, _ctx(exception=SimpleNamespace(residual_minor=0))) is False


@pytest.mark.parametrize(
    "expr",
    [
        "__import__('os').system('rm -rf /')",
        "exception._private",
        "[x for x in range(10)]",
        "lambda: 1",
        "open('/etc/passwd')",
        "exception.__class__",
    ],
)
def test_unsafe_expressions_are_rejected(expr):
    with pytest.raises(RuleError):
        compile_rule(expr)


def test_unknown_name_raises_at_eval():
    tree = compile_rule("mystery_function(1)")
    with pytest.raises(RuleError):
        evaluate(tree, _ctx())


def test_disallowed_attribute_is_blocked():
    tree = compile_rule("record.raw")  # 'raw' is not in the record allow-list
    with pytest.raises(RuleError):
        evaluate(tree, _ctx(record=SimpleNamespace(raw={"secret": 1})))


def test_rule_engine_picks_first_matching_rule():
    engine = RuleEngine(
        [
            {"id": "r_big", "when": "exception.residual_minor > 1000", "classify": "UNEXPLAINED"},
            {
                "id": "r_small",
                "when": "abs(exception.residual_minor) <= 100",
                "classify": "ROUNDING",
                "resolve": "accept_variance",
            },
        ]
    )
    hit = engine.classify(_ctx(exception=SimpleNamespace(residual_minor=40)))
    assert hit is not None and hit.id == "r_small" and hit.classify == "ROUNDING"
    assert hit.resolve == "accept_variance"
    assert engine.classify(_ctx(exception=SimpleNamespace(residual_minor=50000))).id == "r_big"


def test_broken_rule_does_not_crash_the_engine():
    engine = RuleEngine(
        [
            {"id": "r_broken", "when": "nonexistent_fn(record.utr) > 0", "classify": "FOO"},
            {"id": "r_ok", "when": "True", "classify": "UNEXPLAINED"},
        ]
    )
    hit = engine.classify(_ctx(record=SimpleNamespace(utr=None)))
    assert hit is not None and hit.id == "r_ok"


def test_the_reference_spec_rules_all_compile():
    from pathlib import Path

    import yaml

    spec = yaml.safe_load(
        (Path(__file__).resolve().parents[3] / "specs" / "razorpay-settlement.yaml").read_text()
    )
    engine = RuleEngine(spec["rules"])
    assert len(engine.rules) == len(spec["rules"])
