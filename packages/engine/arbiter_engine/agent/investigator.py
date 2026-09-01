"""The bounded investigation loop (docs/12 §3, docs/19).

  PLAN → INVESTIGATE (read-only tools) → HYPOTHESIZE & TEST → DECIDE
                                                              ↳ Proposal | Escalate

Bounded by a turn budget and a token budget. Every LLM request/response pair is
returned as an `interaction` dict so the caller can persist it as an
AGENT_INTERACTION event (making the run replayable without the API).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from arbiter_engine.agent.client import LLMClient, Turn
from arbiter_engine.agent.prompts import INVESTIGATOR_V1, INVESTIGATOR_V1_HASH
from arbiter_engine.agent.schemas import Escalate, Proposal
from arbiter_engine.agent.tools import Tools, build_task_message
from arbiter_engine.models import ReconException

_TOOL_DEFS: list[dict[str, Any]] = [
    {
        "name": "query_evidence",
        "description": "Fetch records in this run matching filters. Read-only.",
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "source": {"type": "string", "enum": ["razorpay_recon", "bank", "ledger", "any"]},
                "external_id": {"type": "string"},
                "amount_minor_low": {"type": "integer"},
                "amount_minor_high": {"type": "integer"},
                "kind": {"type": "string"},
            },
        },
    },
    {
        "name": "counterparty_history",
        "description": "How a counterparty / settlement account behaved in prior runs. Read-only.",
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "counterparty": {"type": "string"},
                "settlement_account": {"type": "string"},
            },
        },
    },
    {
        "name": "similar_exceptions",
        "description": "Prior exceptions of a similar shape and how humans resolved them.",
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {"category_hint": {"type": "string"}, "pattern": {"type": "string"}},
        },
    },
    {
        "name": "candidate_matches",
        "description": "Ranked fuzzy candidates for a record with the per-field weight breakdown.",
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {"record_id": {"type": "string"}},
            "required": ["record_id"],
        },
    },
    {
        "name": "decomposition_detail",
        "description": "Line-by-line settlement identity math for one settlement_utr group.",
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {"settlement_utr": {"type": "string"}, "group_id": {"type": "string"}},
        },
    },
]

_DECIDE_INSTRUCTION = (
    "You have gathered enough evidence, or your budget is nearly spent. Output ONLY a JSON "
    "object: either a Proposal {kind:'proposal', category, confidence, explanation, "
    "evidence_refs:[{claim,record_id,field}], hypotheses_tested:[...], "
    "suggested_action:{action,detail}, draft_rule?} or an Escalate {kind:'escalate', "
    "what_i_know, what_is_missing, question, reason}."
)


@dataclass
class Investigation:
    exception_id: str
    outcome: str  # "proposal" | "escalate"
    proposal: Proposal | None = None
    escalation: Escalate | None = None
    interactions: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: int = 0
    turns: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    model: str = ""
    prompt_hash: str = INVESTIGATOR_V1_HASH


def investigate(
    exc: ReconException,
    tools: Tools,
    client: LLMClient,
    spec: Any,
    *,
    turn_budget: int = 6,
    token_budget: int = 12000,
    thresholds: dict[str, float] | None = None,
) -> Investigation:
    thresholds = thresholds or {"theta_conclude": 0.8, "theta_escalate": 0.55}
    task = build_task_message(exc, tools.snap, spec, thresholds)
    messages: list[dict[str, Any]] = [{"role": "user", "content": task}]
    inv = Investigation(
        exception_id=exc.id, outcome="escalate", model=getattr(client, "model", "?")
    )

    for turn_no in range(turn_budget):
        inv.turns = turn_no + 1
        force = None
        if turn_no == turn_budget - 1 or inv.tokens_in + inv.tokens_out > token_budget:
            messages.append({"role": "user", "content": _DECIDE_INSTRUCTION})
            force = {"type": "json_schema", "schema": {"type": "object"}}

        t = client.complete(
            system=INVESTIGATOR_V1, messages=messages, tools=_TOOL_DEFS, force_structured=force
        )
        inv.tokens_in += t.tokens_in
        inv.tokens_out += t.tokens_out
        inv.interactions.append(_record(turn_no, t))

        if t.stop_reason == "refusal":
            return _escalate(inv, "provider_unavailable", "the model declined to investigate")

        # a terminal structured output?
        parsed = _try_parse(t, exc.id)
        if parsed is not None:
            if isinstance(parsed, Proposal):
                inv.outcome, inv.proposal = "proposal", parsed
            else:
                inv.outcome, inv.escalation = "escalate", parsed
            return inv

        if not t.tool_calls:
            # no tools, no structured output — nudge once, else force the decision
            messages.append({"role": "assistant", "content": t.text or "(thinking)"})
            messages.append({"role": "user", "content": _DECIDE_INSTRUCTION})
            continue

        # execute tool calls (all read-only)
        messages.append({"role": "assistant", "content": _assistant_blocks(t)})
        results = []
        for call in t.tool_calls:
            inv.tool_calls += 1
            try:
                fn = getattr(tools, call.name)
                out = fn(**call.arguments)
            except Exception as e:  # noqa: BLE001 - a tool error is data, not a crash
                out = {"error": str(e)}
            results.append(
                {"type": "tool_result", "tool_use_id": call.id, "content": json.dumps(out)}
            )
        messages.append({"role": "user", "content": results})

    return _escalate(inv, "budget", "turn budget exhausted before a conclusion")


def _record(turn_no: int, t: Turn) -> dict[str, Any]:
    return {
        "turn": turn_no,
        "stop_reason": t.stop_reason,
        "text": t.text,
        "tool_calls": [
            {"id": c.id, "name": c.name, "arguments": c.arguments} for c in t.tool_calls
        ],
        "structured": t.structured,
        "tokens_in": t.tokens_in,
        "tokens_out": t.tokens_out,
    }


def _assistant_blocks(t: Turn) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    if t.text:
        blocks.append({"type": "text", "text": t.text})
    for c in t.tool_calls:
        blocks.append({"type": "tool_use", "id": c.id, "name": c.name, "input": c.arguments})
    return blocks


def _try_parse(t: Turn, exception_id: str) -> Proposal | Escalate | None:
    data = t.structured
    if data is None and t.text.strip().startswith("{"):
        try:
            data = json.loads(t.text)
        except json.JSONDecodeError:
            return None
    if not isinstance(data, dict):
        return None
    data.setdefault("exception_id", exception_id)
    kind = data.get("kind")
    try:
        if kind == "proposal":
            return Proposal.model_validate(data)
        if kind == "escalate":
            return Escalate.model_validate(data)
    except Exception:  # noqa: BLE001 - malformed structured output → treat as none
        return None
    return None


def _escalate(inv: Investigation, reason: str, what_missing: str) -> Investigation:
    inv.outcome = "escalate"
    inv.escalation = Escalate(
        exception_id=inv.exception_id,
        what_i_know="Investigation did not reach a confident conclusion.",
        what_is_missing=what_missing,
        question="A human should review this exception directly.",
        reason=reason,  # type: ignore[arg-type]
    )
    return inv
