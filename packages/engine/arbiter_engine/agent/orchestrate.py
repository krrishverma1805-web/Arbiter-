"""Drive the INVESTIGATING phase of a run (docs/12 §2).

For each exception whose category is in the spec's `adjudication.invoke_for`
(and never in `never_invoke_for`), run one bounded investigation and emit:
  AGENT_INVESTIGATION_STARTED · AGENT_INTERACTION* · (AGENT_PROPOSAL_CREATED | AGENT_ESCALATED)

`--no-ai` skips this phase entirely. `arbiter replay` re-runs it with a
RecordedClient built from the stored AGENT_INTERACTION events, so a completed run
reproduces without touching the API.
"""

from __future__ import annotations

import os
from functools import partial
from typing import Any

from arbiter_engine.agent.client import AnthropicClient, LLMClient, RecordedClient, Turn
from arbiter_engine.agent.investigator import investigate
from arbiter_engine.agent.memory import ResolutionMemory
from arbiter_engine.agent.prompts import INVESTIGATOR_V1_HASH
from arbiter_engine.agent.tools import RunSnapshot, Tools
from arbiter_engine.events.payloads import EventType
from arbiter_engine.events.store import EventStore


def _build_memory(store: EventStore, run_id: str, org: str | None) -> Any:
    """Prefer the persisted vector index (docs/28 §3 item 13); fall back to the
    in-process IDF-cosine memory if it can't be built (e.g. a read-only store)."""
    if os.environ.get("ARBITER_VECTOR_MEMORY", "1") not in ("", "0", "false"):
        try:
            from arbiter_engine.agent.vector_memory import VectorResolutionMemory

            return VectorResolutionMemory.from_store(store, exclude_run_id=run_id, org_id=org)
        except Exception:  # noqa: BLE001 - never fail the run over memory
            pass
    return ResolutionMemory.from_store(store, exclude_run_id=run_id, org_id=org)


# very rough per-model output pricing ($/Mtok) for the cost ceiling
_PRICE = {
    "claude-opus-5": (5.0, 25.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-sonnet-5": (2.0, 10.0),
}


def _adjudication(spec: Any) -> dict[str, Any]:
    return dict(getattr(spec, "adjudication", {}) or {})


def in_scope(spec: Any) -> tuple[set[str], set[str]]:
    adj = _adjudication(spec)
    invoke = set(adj.get("invoke_for", ["UNEXPLAINED", "AMBIGUOUS"]))
    never = set(adj.get("never_invoke_for", ["SECURITY_REVIEW"]))
    return invoke, never


def make_client(spec: Any, *, model_override: str | None = None, exc: Any = None) -> LLMClient:
    """Tiered triage (docs/12 §5): a small model handles the low-$ / well-shaped
    exceptions, the expensive model only the genuinely hard ones."""
    adj = _adjudication(spec)
    models = adj.get("models", {})
    effort_map = adj.get("effort", {}) or {}
    model = model_override or models.get("investigate", "claude-opus-5")
    effort = effort_map.get("investigate_default", "medium")

    if model_override is None and adj.get("model_policy") == "tiered" and exc is not None:
        triage_ceiling = int(adj.get("triage_below_minor", 5_000_00))
        if (
            abs(getattr(exc, "amount_impact_minor", 0)) < triage_ceiling
            and getattr(exc, "category", None) != "UNEXPLAINED"
        ):
            model = models.get("triage", model)
            effort = effort_map.get("triage", "low")
        elif getattr(exc, "category", None) == "UNEXPLAINED":
            effort = effort_map.get("unexplained", effort)
    return AnthropicClient(model=model, effort=effort)


def _self_consistent(run_once: Any, n: int) -> Any:
    """Self-consistency for high-$ exceptions (docs/28 §1.3): run the whole
    investigation `n` times and keep the run whose category is the majority
    vote; if the samples don't agree, the majority run is downgraded to an
    escalation so a human decides. Only the winning run's interactions are
    persisted, so `replay` reproduces it with one pass."""
    from collections import Counter

    runs = [run_once() for _ in range(n)]
    cats = Counter(
        (r.proposal.category if r.outcome == "proposal" and r.proposal else "__escalate__")
        for r in runs
    )
    winner_cat, votes = cats.most_common(1)[0]
    winner = next(
        r
        for r in runs
        if (r.proposal.category if r.outcome == "proposal" and r.proposal else "__escalate__")
        == winner_cat
    )
    total_in = sum(r.tokens_in for r in runs)
    total_out = sum(r.tokens_out for r in runs)
    winner.tokens_in, winner.tokens_out = total_in, total_out
    if votes <= n // 2 and winner.outcome == "proposal":
        from arbiter_engine.agent.investigator import _escalate

        return _escalate(
            winner,
            "inconsistent",
            f"{n} independent investigations did not agree on a category ({dict(cats)})",
        )
    return winner


def make_verifier(spec: Any) -> LLMClient | None:
    """A second, independent model that checks a proposal's cited evidence
    (docs/28 §1.3). Only built when a `verify` model is configured and a key is
    present; a subset of runs / high-$ exceptions actually invoke it."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    adj = _adjudication(spec)
    models = adj.get("models", {})
    vm = models.get("verify") or models.get("triage")
    return AnthropicClient(model=vm, effort="low") if vm else None


def recorded_client_for(store: EventStore, run_id: str, exception_id: str) -> RecordedClient:
    turns = [
        p
        for t, p in store.iter_payloads(run_id)
        if t == EventType.AGENT_INTERACTION and p["exception_id"] == exception_id
    ]
    turns.sort(key=lambda p: p["turn"])
    return RecordedClient(turns)


def run_investigations(
    store: EventStore,
    run_id: str,
    proj: Any,
    spec: Any,
    *,
    client: LLMClient | None = None,
    replay: bool = False,
    model_override: str | None = None,
) -> None:
    invoke, never = in_scope(spec)
    adj = _adjudication(spec)
    turn_budget = int(adj.get("turn_budget", 6))
    token_budget = int(adj.get("per_exception_token_budget", 12000))
    cost_ceiling = float(adj.get("per_run_cost_ceiling_usd", 2.0))
    thresholds = adj.get("stopping", {"theta_conclude": 0.8, "theta_escalate": 0.55})

    already = {
        p["exception_id"]
        for t, p in store.iter_payloads(run_id)
        if t in (EventType.AGENT_PROPOSAL_CREATED, EventType.AGENT_ESCALATED)
    }
    snap = RunSnapshot.from_projection(proj)
    snap.candidates = {e.id: e.candidates for e in proj.exceptions if e.candidates}
    org = next((r.org_id for r in proj.records if getattr(r, "org_id", None)), None)
    snap.resolution_memory = _build_memory(store, run_id, org)
    spent = 0.0

    verifier = None if (replay or client is not None) else make_verifier(spec)
    verify_above = int(adj.get("verify_above_minor", 100_00))
    self_consistency_above = int(adj.get("self_consistency_above_minor", 1_00_000_00))
    sc_samples = int(adj.get("self_consistency_samples", 3))

    targets = sorted(
        (
            e
            for e in proj.exceptions
            if (e.category in invoke or e.category is None)
            and e.category not in never
            and e.id not in already
        ),
        key=lambda e: (-abs(e.amount_impact_minor), e.id),
    )

    for exc in targets:
        if replay:
            active: LLMClient = recorded_client_for(store, run_id, exc.id)
        elif client is not None:
            active = client
        elif spent >= cost_ceiling or not os.environ.get("ANTHROPIC_API_KEY"):
            # no key or ceiling hit → escalate deterministically, no LLM call
            store.append(
                run_id,
                EventType.AGENT_INVESTIGATION_STARTED,
                {
                    "exception_id": exc.id,
                    "category_in": exc.category or "UNEXPLAINED",
                    "model": "none",
                    "prompt_hash": INVESTIGATOR_V1_HASH,
                },
            )
            store.append(
                run_id,
                EventType.AGENT_ESCALATED,
                {
                    "exception_id": exc.id,
                    "tool_calls": 0,
                    "turns": 0,
                    "escalation": {
                        "kind": "escalate",
                        "what_i_know": "AI investigation unavailable for this run.",
                        "what_is_missing": "an ANTHROPIC_API_KEY or remaining cost budget",
                        "question": "A human should review this exception.",
                        "reason": "budget",
                    },
                },
            )
            continue
        else:
            active = make_client(spec, model_override=model_override, exc=exc)

        store.append(
            run_id,
            EventType.AGENT_INVESTIGATION_STARTED,
            {
                "exception_id": exc.id,
                "category_in": exc.category or "UNEXPLAINED",
                "model": getattr(active, "model", "?"),
                "prompt_hash": INVESTIGATOR_V1_HASH,
            },
        )
        impact = abs(exc.amount_impact_minor)
        use_verifier = verifier if impact >= verify_above else None
        one = partial(
            investigate,
            exc,
            Tools(snap, exc),
            active,
            spec,
            turn_budget=turn_budget,
            token_budget=token_budget,
            thresholds=thresholds,
            verifier=use_verifier,
        )
        if not replay and client is None and impact >= self_consistency_above and sc_samples > 1:
            inv = _self_consistent(one, sc_samples)
        else:
            inv = one()
        for rec in inv.interactions:
            store.append(
                run_id,
                EventType.AGENT_INTERACTION,
                {"exception_id": exc.id, **rec},
                actor=f"agent:{getattr(active, 'model', '?')}@{INVESTIGATOR_V1_HASH}",
            )
        if not replay and client is None:
            pin, pout = _PRICE.get(getattr(active, "model", ""), (5.0, 25.0))
            spent += inv.tokens_in / 1e6 * pin + inv.tokens_out / 1e6 * pout

        if inv.outcome == "proposal" and inv.proposal is not None:
            store.append(
                run_id,
                EventType.AGENT_PROPOSAL_CREATED,
                {
                    "exception_id": exc.id,
                    "proposal": inv.proposal.model_dump(mode="json"),
                    "tool_calls": inv.tool_calls,
                    "turns": inv.turns,
                    "tokens_in": inv.tokens_in,
                    "tokens_out": inv.tokens_out,
                    "grounding": inv.grounding.as_dict() if inv.grounding else None,
                },
                actor=f"agent:{getattr(active, 'model', '?')}@{INVESTIGATOR_V1_HASH}",
            )
        else:
            esc = inv.escalation.model_dump(mode="json") if inv.escalation else {}
            store.append(
                run_id,
                EventType.AGENT_ESCALATED,
                {
                    "exception_id": exc.id,
                    "escalation": esc,
                    "tool_calls": inv.tool_calls,
                    "turns": inv.turns,
                },
                actor=f"agent:{getattr(active, 'model', '?')}@{INVESTIGATOR_V1_HASH}",
            )


__all__ = ["run_investigations", "make_client", "Turn"]
