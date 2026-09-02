"""Input-drift detection (docs/28 §3 item 16).

Each run gets a small numeric *profile* of its input — source mix, record-kind
mix, how often a reference / counterparty / value-date is present, amount spread,
counterparty cardinality. After a run we compare its profile against the mean of
the tenant's recent runs for the same spec; if the population-stability index
crosses a threshold we append an `INPUT_DRIFT_DETECTED` event naming the features
that moved. It never fails a run — it is the "something changed, re-check the
matcher" signal (a new bank statement format, a counterparty-mix shift).

Deterministic and LLM-free — pure arithmetic over the ingested records.
"""

from __future__ import annotations

import math
import statistics as stats

from arbiter_engine.events.payloads import EventType
from arbiter_engine.events.store import EventStore
from arbiter_engine.models import Record

_MIN_BASELINE = 3  # need at least this many prior runs to judge drift
_PSI_ALERT = 0.25  # summed PSI over all features
_FEATURE_ALERT = 0.10  # per-feature PSI to name it in `drifted`


def _learn_run(store: EventStore) -> str:
    """Drift events live on the tenant's learn pseudo-run, never the
    reconciliation run's hash chain (which must replay identically in a fresh
    store)."""
    return f"__learn__{getattr(store, 'org_id', 'local')}"


def feature_profile(records: list[Record]) -> dict[str, float]:
    n = max(1, len(records))
    amounts = sorted(abs(r.amount_minor) for r in records) or [0]
    med = amounts[len(amounts) // 2] or 1
    cv = (stats.pstdev(amounts) / (stats.fmean(amounts) + 1)) if len(amounts) > 1 else 0.0
    kinds = {r.kind for r in records}
    sources = {r.source for r in records}
    cps = {r.counterparty for r in records if r.counterparty}
    return {
        "record_count": float(len(records)),
        "source_count": float(len(sources)),
        "kind_count": float(len(kinds)),
        "payment_frac": sum(r.kind == "payment" for r in records) / n,
        "credit_frac": sum(r.kind == "credit" for r in records) / n,
        "has_reference_frac": sum(bool(r.reference) for r in records) / n,
        "has_counterparty_frac": sum(bool(r.counterparty) for r in records) / n,
        "has_value_date_frac": sum(r.value_date is not None for r in records) / n,
        "counterparty_cardinality": len(cps) / n,
        "amount_log_median": math.log10(med + 1),
        "amount_cv": cv,
    }


def _psi(baseline: float, current: float) -> float:
    """A one-bucket population-stability term. Both values are non-negative
    feature summaries; we compare them as proportions of their sum."""
    b = max(baseline, 1e-6)
    c = max(current, 1e-6)
    total = b + c
    pb, pc = b / total, c / total
    return (pc - pb) * math.log(pc / pb)


def _baseline_profiles(
    store: EventStore, spec_hash: str, exclude_run: str
) -> list[dict[str, float]]:
    out: list[dict[str, float]] = []
    for t, p in store.iter_payloads(_learn_run(store)):
        if (
            t == EventType.INPUT_DRIFT_DETECTED
            and p.get("spec_hash") == spec_hash
            and p.get("run_id") != exclude_run
            and isinstance(p.get("profile"), dict)
        ):
            out.append({k: float(v) for k, v in p["profile"].items()})
    return out


def check_drift(
    store: EventStore, run_id: str, spec_hash: str, records: list[Record]
) -> dict[str, float] | None:
    """Compute this run's profile, compare it to the tenant's baseline for this
    spec, and append an `INPUT_DRIFT_DETECTED` event (on the learn pseudo-run,
    not the reconciliation chain) carrying the profile so it seeds future
    baselines. Returns the drift summary if it alerted, else None."""
    for t, p in store.iter_payloads(_learn_run(store)):
        if t == EventType.INPUT_DRIFT_DETECTED and p.get("run_id") == run_id:
            return None  # already profiled this run

    profile = feature_profile(records)
    baseline = _baseline_profiles(store, spec_hash, run_id)

    drifted: list[str] = []
    total_psi = 0.0
    if len(baseline) >= _MIN_BASELINE:
        mean = {k: stats.fmean(b[k] for b in baseline if k in b) for k in profile}
        for k, cur in profile.items():
            term = abs(_psi(mean.get(k, cur), cur))
            total_psi += term
            if term >= _FEATURE_ALERT:
                drifted.append(k)

    alerted = len(baseline) >= _MIN_BASELINE and total_psi >= _PSI_ALERT
    store.append(
        _learn_run(store),
        EventType.INPUT_DRIFT_DETECTED,
        {
            "run_id": run_id,
            "spec_hash": spec_hash,
            "psi": round(total_psi, 6),
            "drifted": sorted(drifted) if alerted else [],
            "baseline_runs": len(baseline),
            "profile": {k: round(v, 6) for k, v in profile.items()},
        },
        actor="learn",
    )
    if alerted:
        return {"psi": round(total_psi, 4), "drifted": len(drifted)}
    return None
