"""Build the RuleContext (variables + safe helper functions) that spec `when:`
expressions are evaluated against (docs/adr/0003)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from types import SimpleNamespace
from typing import Any

from arbiter_engine.exceptions.injection import injection_signal
from arbiter_engine.exceptions.rules import RuleContext
from arbiter_engine.models import Decomposition, Match, Record


def _record_ns(r: Record | None) -> SimpleNamespace:
    if r is None:
        return SimpleNamespace()
    return SimpleNamespace(
        amount_minor=r.amount_minor,
        fee_minor=r.fee_minor,
        tax_minor=r.tax_minor,
        value_date=r.value_date,
        posted_date=r.posted_date,
        settled_at=r.settled_at,
        kind=r.kind,
        source=r.source,
        reference=r.reference,
        type=r.kind,
        debit=(-r.amount_minor if r.amount_minor < 0 else 0),
        utr=r.external_ids.get("utr"),
        settlement_utr=r.external_ids.get("settlement_utr"),
        payment_id=r.external_ids.get("payment_id"),
        order_id=r.external_ids.get("order_id"),
        dispute_id=r.external_ids.get("dispute_id"),
        description=r.untrusted.get("description"),
        notes=r.untrusted.get("notes"),
        narration=r.untrusted.get("narration"),
    )


def build_context(
    *,
    all_records: list[Record],
    exception_records: list[Record],
    residual_minor: int | None = None,
    amount_impact_minor: int = 0,
    match: Match | None = None,
    decomp: Decomposition | None = None,
    unmatched_sources: set[str] | None = None,
    prior_period_utrs: set[str] | None = None,
) -> RuleContext:
    primary = exception_records[0] if exception_records else None
    unmatched_srcs = unmatched_sources or set()
    prior_utrs = prior_period_utrs or set()

    def _count_records(**filters: Any) -> int:
        n = 0
        for r in all_records:
            ns = _record_ns(r)
            if all(getattr(ns, k, None) == v for k, v in filters.items()):
                n += 1
        return n

    def _unmatched(source: str) -> bool:
        return source in unmatched_srcs

    def _exists_match_in_prior_period(_rec: Any = None) -> bool:
        return bool(prior_utrs)

    def _reverses_a_payment(_rec: Any = None) -> bool:
        return bool(primary and primary.external_ids.get("dispute_id"))

    def _expected_fee_minor(_m: Any = None) -> int:
        return sum(r.fee_minor + r.tax_minor for r in exception_records) or 1

    def _ts_day(d: date | None) -> int:
        return d.day if isinstance(d, date) else 99

    functions: dict[str, Callable[..., Any]] = {
        "abs": abs,
        "is_empty": lambda x: x is None or x == "" or x == 0,
        "injection_signal": lambda *t: injection_signal(*t),
        "count_records": _count_records,
        "unmatched": _unmatched,
        "exists_match_in_prior_period": _exists_match_in_prior_period,
        "reverses_a_payment": _reverses_a_payment,
        "expected_fee_minor": _expected_fee_minor,
        "ts_day": _ts_day,
    }
    variables = {
        "record": _record_ns(primary),
        "bank": _record_ns(next((r for r in exception_records if r.source == "bank"), None)),
        "exception": SimpleNamespace(
            residual_minor=residual_minor if residual_minor is not None else 0,
            amount_impact_minor=amount_impact_minor,
            record_count=len(exception_records),
        ),
        "match": SimpleNamespace(
            residual_minor=match.residual_minor if match else (residual_minor or 0),
            confidence=match.confidence if match else 0.0,
            expected_fee_minor=_expected_fee_minor(),
        ),
        "decomp": SimpleNamespace(
            residual_minor=decomp.residual_minor if decomp else 0,
            ledger_crosscheck_ok=decomp.ledger_crosscheck_ok if decomp else True,
            expected_minor=decomp.expected_minor if decomp else 0,
            actual_minor=decomp.actual_minor if decomp else 0,
        ),
    }
    return RuleContext(variables=variables, functions=functions)
