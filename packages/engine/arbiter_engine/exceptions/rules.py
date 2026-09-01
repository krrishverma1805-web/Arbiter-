"""Safe expression engine for spec-authored classification rules (docs/adr/0003).

A recon spec's `rules:` block contains `when:` expressions like

    "exception.residual_minor != 0 and abs(exception.residual_minor) <= 100"
    "unmatched('bank') and ts_day(record.settled_at) <= 3 and exists_match_in_prior_period(record)"

These are parsed with Python's `ast` module and evaluated against a *whitelist*
of node types and a fixed set of helper functions — never `eval`, no attribute
access outside a small allow-list, no imports, no comprehensions, no lambdas.
This makes customer- and (later) AI-authored rules safe to run and analyze.
"""

from __future__ import annotations

import ast
import operator
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

_ALLOWED_NODES = (
    ast.Expression,
    ast.BoolOp,
    ast.UnaryOp,
    ast.BinOp,
    ast.Compare,
    ast.Call,
    ast.keyword,
    ast.Name,
    ast.Load,
    ast.Constant,
    ast.Attribute,
    ast.And,
    ast.Or,
    ast.Not,
    ast.USub,
    ast.UAdd,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.In,
    ast.NotIn,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Mod,
    ast.FloorDiv,
)

_BINOPS: dict[type[ast.operator], Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
}
_CMPOPS: dict[type[ast.cmpop], Callable[[Any, Any], Any]] = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
}
# only these attributes may be read, and only on the named context objects
_ALLOWED_ATTRS = {
    "record",
    "exception",
    "match",
    "decomp",
    "spec",
}
_RECORD_ATTRS = {
    "amount_minor",
    "fee_minor",
    "tax_minor",
    "value_date",
    "posted_date",
    "settled_at",
    "kind",
    "source",
    "reference",
    "utr",
    "settlement_utr",
    "payment_id",
    "order_id",
    "dispute_id",
    "description",
    "notes",
    "day",
}
_EXC_ATTRS = {"residual_minor", "amount_impact_minor", "category", "record_count"}
_MATCH_ATTRS = {"residual_minor", "confidence", "expected_fee_minor"}
_DECOMP_ATTRS = {"residual_minor", "ledger_crosscheck_ok", "expected_minor", "actual_minor"}


class RuleError(ValueError):
    """A rule expression is unsafe or malformed."""


_BANNED_NAMES = frozenset(
    {
        "__import__", "eval", "exec", "compile", "open", "input", "globals", "locals",
        "vars", "getattr", "setattr", "delattr", "hasattr", "type", "object", "super",
        "breakpoint", "help", "exit", "quit", "memoryview",
    }
)


def compile_rule(expr: str) -> ast.Expression:
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise RuleError(f"rule is not valid syntax: {expr!r} ({e})") from e
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise RuleError(f"disallowed expression element {type(node).__name__} in {expr!r}")
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            raise RuleError(f"private attribute access is not allowed: {expr!r}")
        if isinstance(node, ast.Name) and (
            node.id.startswith("__") or node.id in _BANNED_NAMES
        ):
            raise RuleError(f"disallowed name {node.id!r} in {expr!r}")
    return tree


@dataclass
class RuleContext:
    variables: dict[str, Any]
    functions: dict[str, Callable[..., Any]]

    def get(self, name: str) -> Any:
        if name in self.variables:
            return self.variables[name]
        if name in self.functions:
            return self.functions[name]
        raise RuleError(f"unknown name in rule: {name!r}")


def evaluate(tree: ast.Expression, ctx: RuleContext) -> Any:
    return _eval(tree.body, ctx)


def _eval(node: ast.AST, ctx: RuleContext) -> Any:  # noqa: C901 - a small dispatcher
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return ctx.get(node.id)
    if isinstance(node, ast.BoolOp):
        vals = (_eval(v, ctx) for v in node.values)
        return all(vals) if isinstance(node.op, ast.And) else any(vals)
    if isinstance(node, ast.UnaryOp):
        v = _eval(node.operand, ctx)
        if isinstance(node.op, ast.Not):
            return not v
        if isinstance(node.op, ast.USub):
            return -v
        return +v
    if isinstance(node, ast.BinOp):
        fn = _BINOPS.get(type(node.op))
        if fn is None:
            raise RuleError(f"operator {type(node.op).__name__} not allowed")
        return fn(_eval(node.left, ctx), _eval(node.right, ctx))
    if isinstance(node, ast.Compare):
        left = _eval(node.left, ctx)
        for op, comparator in zip(node.ops, node.comparators, strict=False):
            right = _eval(comparator, ctx)
            if not _CMPOPS[type(op)](left, right):
                return False
            left = right
        return True
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise RuleError("only direct function calls are allowed")
        fn = ctx.get(node.func.id)
        if not callable(fn):
            raise RuleError(f"{node.func.id!r} is not callable in a rule")
        args = [_eval(a, ctx) for a in node.args]
        kwargs = {kw.arg: _eval(kw.value, ctx) for kw in node.keywords if kw.arg}
        return fn(*args, **kwargs)
    if isinstance(node, ast.Attribute):
        base = _eval(node.value, ctx)
        allowed = {
            "record": _RECORD_ATTRS,
            "exception": _EXC_ATTRS,
            "match": _MATCH_ATTRS,
            "decomp": _DECOMP_ATTRS,
        }
        root = node.value.id if isinstance(node.value, ast.Name) else None
        if root in allowed and node.attr not in allowed[root]:
            raise RuleError(f"attribute {root}.{node.attr} is not exposed to rules")
        if isinstance(base, dict):
            return base.get(node.attr)
        return getattr(base, node.attr, None)
    raise RuleError(f"cannot evaluate node {type(node).__name__}")


@dataclass
class Rule:
    id: str
    when: ast.Expression
    classify: str
    resolve: str


class RuleEngine:
    """Loads a spec's `rules:` and classifies a raw exception context."""

    def __init__(self, rules: list[dict[str, Any]]) -> None:
        self.rules: list[Rule] = []
        for r in rules:
            if "when" not in r or "classify" not in r:
                continue
            self.rules.append(
                Rule(
                    id=str(r.get("id", f"rule_{len(self.rules)}")),
                    when=compile_rule(str(r["when"])),
                    classify=str(r["classify"]),
                    resolve=str(r.get("resolve", "route_to_human")),
                )
            )

    def classify(self, ctx: RuleContext) -> Rule | None:
        for rule in self.rules:
            try:
                if evaluate(rule.when, ctx):
                    return rule
            except RuleError:
                continue  # a broken rule never crashes a run; it just doesn't fire
        return None
