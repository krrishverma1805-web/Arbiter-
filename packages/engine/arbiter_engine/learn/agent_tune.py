"""Re-fit the agent's escalation threshold from human feedback (docs/28 §3 item 14).

Every proposal the agent made carries a `grounded_confidence`. Later, a human
either kept its suggested action (accept) or changed it (override). Over enough
history we can pick the `theta_escalate` that best separates the two: proposals
the human would have accepted should auto-conclude, the rest should have
escalated.

Concretely — for each spec, gather `(grounded_confidence, accepted?)` pairs from
`AGENT_PROPOSAL_CREATED` → `RESOLUTION_APPLIED`, then choose the threshold that
maximises `accepted-above + overridden-below`. Written as an
`AGENT_THRESHOLD_TUNED` event on the `__learn__<org>` pseudo-run; `run.py` loads
it. Deterministic, LLM-free.
"""

from __future__ import annotations

from dataclasses import dataclass

from arbiter_engine.events.fold import fold_run
from arbiter_engine.events.payloads import EventType
from arbiter_engine.events.store import EventStore
from arbiter_engine.specs import ReconSpec, spec_hash

_MIN_PAIRS = 20
_FLOOR, _CEIL = 0.45, 0.9  # keep the threshold sane whatever the data says


@dataclass
class TuneResult:
    tuned: bool
    theta_escalate: float
    accepted: int
    overridden: int


def _learn_run(store: EventStore) -> str:
    return f"__learn__{getattr(store, 'org_id', 'local')}"


def _feedback_pairs(store: EventStore, sh: str) -> list[tuple[float, bool]]:
    pairs: list[tuple[float, bool]] = []
    for rid in store.runs():
        types = {t for t, _ in store.iter_payloads(rid)}
        if EventType.AGENT_PROPOSAL_CREATED not in types:
            continue
        started = next((p for t, p in store.iter_payloads(rid) if t == EventType.RUN_STARTED), None)
        if not started or started.get("spec_hash") != sh:
            continue
        proj = fold_run(store, rid)
        proposals = {
            p["exception_id"]: p
            for t, p in store.iter_payloads(rid)
            if t == EventType.AGENT_PROPOSAL_CREATED
        }
        for exc in proj.exceptions:
            prop = proposals.get(exc.id)
            if prop is None or not exc.resolution:
                continue
            g = (prop.get("grounding") or {}).get("grounded_confidence")
            if g is None:
                continue
            proposed = (prop.get("proposal") or {}).get("suggested_action", {}).get("action")
            accepted = proposed is not None and exc.resolution.get("action") == proposed
            pairs.append((float(g), bool(accepted)))
    return pairs


def tune_escalation_threshold(
    store: EventStore, spec: ReconSpec, *, trained_by: str = "nightly"
) -> TuneResult:
    sh = spec_hash(spec)
    pairs = _feedback_pairs(store, sh)
    accepted = sum(1 for _, ok in pairs if ok)
    overridden = len(pairs) - accepted
    if len(pairs) < _MIN_PAIRS or accepted == 0 or overridden == 0:
        return TuneResult(False, 0.0, accepted, overridden)

    # try every observed confidence as a cut point; score = correctly-classified
    cuts = sorted({round(c, 3) for c, _ in pairs})
    best_theta, best_score = cuts[0], -1
    for theta in cuts:
        score = sum(1 for c, ok in pairs if (ok and c >= theta) or (not ok and c < theta))
        if score > best_score:
            best_theta, best_score = theta, score

    theta = min(_CEIL, max(_FLOOR, best_theta))
    store.append(
        _learn_run(store),
        EventType.AGENT_THRESHOLD_TUNED,
        {
            "spec_hash": sh,
            "theta_escalate": round(theta, 4),
            "accepted": accepted,
            "overridden": overridden,
            "trained_by": trained_by,
        },
        actor="learn",
    )
    return TuneResult(True, round(theta, 4), accepted, overridden)


def load_escalation_threshold(store: EventStore, sh: str) -> float | None:
    """The most recent tuned `theta_escalate` for this spec, or None."""
    latest: float | None = None
    best_n = -1
    for t, p in store.iter_payloads(_learn_run(store)):
        if t != EventType.AGENT_THRESHOLD_TUNED or p.get("spec_hash") != sh:
            continue
        n = int(p.get("accepted", 0)) + int(p.get("overridden", 0))
        if n >= best_n:
            best_n, latest = n, float(p["theta_escalate"])
    return latest
