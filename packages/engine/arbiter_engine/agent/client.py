"""Pluggable LLM client for the investigation agent.

  AnthropicClient   — the default (needs ANTHROPIC_API_KEY)
  OpenAIClient      — a drop-in adapter for OpenAI Chat Completions, so the agent
                      can run against GPT models (needs OPENAI_API_KEY and
                      ARBITER_LLM_PROVIDER=openai). Same Turn contract, so replay,
                      grounding, the verifier and the scorecard are unchanged.
  RecordedClient    — replays AGENT_INTERACTION events; used by `arbiter replay`
                      so a completed run reproduces without calling the API
  ScriptedClient    — canned turns; used by the offline test suite

Every client returns a `Turn` (assistant content blocks + stop reason + usage),
and the investigator records each request/response pair as an event.
"""

from __future__ import annotations

import json
import os
import random
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

_MAX_RETRY_DELAY = 90.0  # a single attempt never sleeps longer than this


def _with_retry(call: Any, rate_limit_error: type[BaseException], *, max_attempts: int = 8) -> Any:
    """Retry `call()` on a provider rate-limit error with exponential backoff.

    Real accounts (this includes low-tier / unfunded API keys) can have TPM
    limits far below what a 99-case agent-bench run needs; without this, one
    429 aborts the whole run instead of the client just slowing down. 8
    attempts gives ~4 minutes of cumulative patience for a short rolling-
    window throttle (e.g. Gemini's free-tier RPM cap, which recovers in
    seconds) without letting a single delay balloon — a server that reports a
    much longer wait (e.g. a daily quota, seen on Groq/Gemini's stricter
    tiers) is capped at `_MAX_RETRY_DELAY` per attempt, so the whole retry
    budget is bounded at max_attempts * _MAX_RETRY_DELAY (~12 min) rather than
    parking on a server-reported wait of tens of minutes."""
    for attempt in range(max_attempts):
        try:
            return call()
        except rate_limit_error as e:
            if attempt == max_attempts - 1:
                raise
            retry_after = None
            resp = getattr(e, "response", None)
            if resp is not None:
                retry_after = getattr(resp, "headers", {}).get("retry-after")
            delay = float(retry_after) if retry_after else (2.0 * (2**attempt))
            delay = min(delay, _MAX_RETRY_DELAY) + random.uniform(0, 0.5)
            print(f"  rate limited, retrying in {delay:.1f}s…", file=sys.stderr)
            time.sleep(delay)
    raise AssertionError("unreachable")  # pragma: no cover


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]
    raw: dict[str, Any] | None = None  # provider passthrough, e.g. Gemini's thought_signature


@dataclass
class Turn:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str = "end_turn"  # "tool_use" | "end_turn" | "refusal" | "max_tokens"
    structured: dict[str, Any] | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    raw: dict[str, Any] = field(default_factory=dict)


class LLMClient(Protocol):
    model: str

    def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        force_structured: dict[str, Any] | None = None,
    ) -> Turn: ...


# --------------------------------------------------------------------------- real
class AnthropicClient:
    def __init__(self, model: str = "claude-opus-5", *, effort: str = "medium") -> None:
        import anthropic  # imported lazily so the engine works without the dep at runtime

        self.model = model
        self.effort = effort
        self._client = anthropic.Anthropic()
        self._rate_limit_error = anthropic.RateLimitError

    def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        force_structured: dict[str, Any] | None = None,
    ) -> Turn:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": 8000,
            "system": system,
            "messages": messages,
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": self.effort},
        }
        if force_structured is not None:
            kwargs["output_config"] = {"effort": self.effort, "format": force_structured}
        else:
            kwargs["tools"] = tools
        resp = _with_retry(lambda: self._client.messages.create(**kwargs), self._rate_limit_error)
        return _turn_from_anthropic(resp)


def _turn_from_anthropic(resp: Any) -> Turn:
    text_parts: list[str] = []
    tool_calls: list[ToolCall] = []
    for block in resp.content:
        btype = getattr(block, "type", None)
        if btype == "text":
            text_parts.append(block.text)
        elif btype == "tool_use":
            tool_calls.append(ToolCall(id=block.id, name=block.name, arguments=dict(block.input)))
    structured: dict[str, Any] | None = None
    joined = "".join(text_parts)
    if resp.stop_reason not in ("tool_use", "refusal") and joined.strip().startswith("{"):
        try:
            structured = json.loads(joined)
        except json.JSONDecodeError:
            structured = None
    usage = getattr(resp, "usage", None)
    return Turn(
        text=joined,
        tool_calls=tool_calls,
        stop_reason=resp.stop_reason or "end_turn",
        structured=structured,
        tokens_in=getattr(usage, "input_tokens", 0) if usage else 0,
        tokens_out=getattr(usage, "output_tokens", 0) if usage else 0,
        raw={"stop_reason": resp.stop_reason},
    )


# --------------------------------------------------------------------------- openai
class _OpenAICompatibleClient:
    """Shared Chat Completions wire format for OpenAI and any OpenAI-compatible
    endpoint (Groq's `/openai/v1`, etc.) — same request/response shape, only the
    base URL, API key and default model differ per subclass.

    Arbiter builds messages, tool schemas and the "force a decision" instruction
    in Anthropic's shape; `complete` translates that shape to Chat Completions on
    the way in and normalises the reply back to a `Turn` on the way out, so
    nothing downstream (the investigator loop, grounding, replay) has to know.
    """

    model: str
    effort: str
    _client: Any
    _rate_limit_error: type[BaseException]
    max_completion_tokens: int = 8000

    def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        force_structured: dict[str, Any] | None = None,
    ) -> Turn:
        oai_msgs: list[dict[str, Any]] = [{"role": "system", "content": system}]
        for m in messages:
            oai_msgs.extend(_to_openai_messages(m))

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": oai_msgs,
            "max_completion_tokens": self.max_completion_tokens,
        }
        if force_structured is not None:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "decision", "strict": False, "schema": _DECISION_SCHEMA},
            }
        elif tools:
            kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t.get("description", ""),
                        "parameters": t.get("input_schema", {"type": "object"}),
                    },
                }
                for t in tools
            ]
        create = self._client.chat.completions.create
        resp = _with_retry(lambda: create(**kwargs), self._rate_limit_error)
        return _turn_from_openai(resp)


class OpenAIClient(_OpenAICompatibleClient):
    """Real OpenAI Chat Completions (needs `OPENAI_API_KEY`)."""

    def __init__(self, model: str = "gpt-4o", *, effort: str = "medium") -> None:
        import openai  # lazy: the engine runs without the dep

        self.model = model
        self.effort = effort  # kept for parity; OpenAI reasoning models read it below
        self._client = openai.OpenAI()
        self._rate_limit_error = openai.RateLimitError


class GroqClient(_OpenAICompatibleClient):
    """Groq's OpenAI-compatible endpoint (needs `GROQ_API_KEY`) — same wire
    format as `OpenAIClient`, so the base class's `complete` is unchanged.
    Defaults to `openai/gpt-oss-120b`, the model Groq hosts that supports both
    tool calling and the structured decision schema.

    Groq's free/on-demand tier caps this model at 8000 tokens/min *per
    request* (prompt + completion combined), not just per minute — a single
    oversized request is rejected outright, not merely throttled, so unlike
    the plain rate-limit case `_with_retry` handles, there is no backoff that
    fixes it. `max_completion_tokens` is kept small here to leave headroom for
    the prompt; the investigator's per-exception token budget bounds the rest.
    Any request that still doesn't fit is escalated by the caller — see
    `orchestrate.py` (the real run) and `bench/agent_bench.py::evaluate` (the
    benchmark) — never a crash."""

    max_completion_tokens = 2000

    def __init__(self, model: str = "openai/gpt-oss-120b", *, effort: str = "medium") -> None:
        import openai  # lazy: the engine runs without the dep; Groq speaks its wire format

        key = os.environ.get("GROQ_API_KEY")
        if not key:
            raise RuntimeError("GROQ_API_KEY is not set")
        self.model = model
        self.effort = effort
        self._client = openai.OpenAI(api_key=key, base_url="https://api.groq.com/openai/v1")
        self._rate_limit_error = openai.RateLimitError


class GeminiClient(_OpenAICompatibleClient):
    """Google Gemini's OpenAI-compatible endpoint (needs `GEMINI_API_KEY`) —
    full parity with tool calling and the structured decision schema, unlike
    Groq's per-request size wall.

    Defaults to `gemini-3.5-flash-lite`, not the larger `gemini-3.6-flash`:
    empirically, the free tier caps `gemini-3.6-flash` at a hard 20
    requests/*day*/project (`GenerateRequestsPerDayPerProjectPerModel-FreeTier`
    — exhausted in one sitting, only resets on a day boundary), while
    `gemini-3.5-flash-lite` is throttled by a short rolling-window RPM limit
    instead (~15/min, recovers in well under a minute) — the kind of limit
    `_with_retry`'s backoff is built for. A full run completes; it is just
    slower, not structurally blocked."""

    def __init__(self, model: str = "gemini-3.5-flash-lite", *, effort: str = "medium") -> None:
        import openai  # lazy: the engine runs without the dep; Gemini speaks its wire format

        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        self.model = model
        self.effort = effort
        self._client = openai.OpenAI(
            api_key=key, base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
        )
        self._rate_limit_error = openai.RateLimitError


# The investigator's terminal contract (schemas.py). OpenAI models don't have
# Anthropic's `output_config.format` schema enforcement, so we (a) hand OpenAI a
# json_schema on the forced turn and (b) coerce a near-miss back onto the
# contract — the deterministic grounding layer still vets the substance.
_ACTIONS = (
    "accept_variance",
    "attribute_to",
    "carry_forward",
    "flag_overcharge",
    "raise_dispute",
    "void_duplicate_of",
    "request_data",
    "route_to_human",
    "wont_fix",
)
_CATEGORIES = (
    "FEE_DEDUCTION",
    "TAX_DEDUCTION",
    "ROUNDING",
    "PARTIAL_PAYMENT",
    "TIMING",
    "DUPLICATE",
    "CHARGEBACK",
    "ADJUSTMENT",
    "FX_DIFFERENCE",
    "MISSING_UTR",
    "WRONG_ACCOUNT",
    "SPLIT_SETTLEMENT",
    "UNEXPLAINED",
)
_DECISION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": ["proposal", "escalate"]},
        "category": {"type": "string", "enum": list(_CATEGORIES)},
        "confidence": {"type": "number"},
        "explanation": {"type": "string"},
        "evidence_refs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string"},
                    "record_id": {"type": "string"},
                    "field": {"type": "string"},
                },
            },
        },
        "suggested_action": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": list(_ACTIONS)},
                "detail": {"type": "string"},
            },
        },
        "what_i_know": {"type": "string"},
        "what_is_missing": {"type": "string"},
        "question": {"type": "string"},
    },
}


def _nearest_action(a: str) -> str:
    a = (a or "").lower().strip().replace(" ", "_")
    if a in _ACTIONS:
        return a
    hits = {
        "review": "route_to_human",
        "manual": "route_to_human",
        "investigate": "route_to_human",
        "resolve": "route_to_human",
        "dispute": "raise_dispute",
        "chargeback": "raise_dispute",
        "duplicate": "void_duplicate_of",
        "overcharge": "flag_overcharge",
        "fee": "flag_overcharge",
        "carry": "carry_forward",
        "timing": "carry_forward",
        "accept": "accept_variance",
        "variance": "accept_variance",
        "data": "request_data",
        "ignore": "wont_fix",
    }
    for k, v in hits.items():
        if k in a:
            return v
    return "route_to_human"


def _coerce_decision(text: str) -> str:
    """Best-effort: pull a proposal/escalate object out of a non-Anthropic reply
    and snap it onto the strict contract (drop unknown keys, map the action to
    the nearest allowed value). Returns `text` unchanged if it isn't one."""
    s = text.strip()
    if not s.startswith("{"):
        return text
    try:
        d = json.loads(s)
    except json.JSONDecodeError:
        return text
    if not isinstance(d, dict) or d.get("kind") not in ("proposal", "escalate"):
        return text
    keep = set(_DECISION_SCHEMA["properties"])
    out: dict[str, Any] = {k: v for k, v in d.items() if k in keep}
    out.setdefault("kind", d["kind"])
    if isinstance(out.get("suggested_action"), dict):
        sa = out["suggested_action"]
        out["suggested_action"] = {
            "action": _nearest_action(str(sa.get("action", ""))),
            "detail": str(sa.get("detail", "") or "see explanation"),
        }
    if isinstance(out.get("evidence_refs"), list):
        out["evidence_refs"] = [
            {
                "claim": str(r.get("claim", "")),
                "record_id": str(r.get("record_id", "")),
                "field": str(r.get("field", "")),
            }
            for r in out["evidence_refs"]
            if isinstance(r, dict)
        ]
    return json.dumps(out)


def _to_openai_messages(m: dict[str, Any]) -> list[dict[str, Any]]:
    role, content = m.get("role"), m.get("content")
    if isinstance(content, str):
        return [{"role": role, "content": content}]
    # a list of Anthropic-style blocks
    if role == "assistant":
        text_parts: list[str] = []
        calls: list[dict[str, Any]] = []
        for b in content or []:
            if b.get("type") == "text":
                text_parts.append(b.get("text", ""))
            elif b.get("type") == "tool_use":
                call: dict[str, Any] = {
                    "id": b["id"],
                    "type": "function",
                    "function": {
                        "name": b["name"],
                        "arguments": json.dumps(b.get("input", {})),
                    },
                }
                if b.get("raw"):
                    # e.g. Gemini's thought_signature — required on the *next*
                    # turn's replay of this same tool call, or it 400s asking
                    # for it by name (ai.google.dev/gemini-api/docs/thought-signatures)
                    call["extra_content"] = b["raw"]
                calls.append(call)
        msg: dict[str, Any] = {"role": "assistant", "content": "".join(text_parts) or None}
        if calls:
            msg["tool_calls"] = calls
        return [msg]
    # user turn carrying tool_result blocks → one OpenAI `tool` message each
    out: list[dict[str, Any]] = []
    for b in content or []:
        if b.get("type") == "tool_result":
            out.append(
                {
                    "role": "tool",
                    "tool_call_id": b["tool_use_id"],
                    "content": b.get("content", ""),
                }
            )
        elif b.get("type") == "text":
            out.append({"role": "user", "content": b.get("text", "")})
    return out or [{"role": "user", "content": ""}]


_OPENAI_STOP = {
    "stop": "end_turn",
    "tool_calls": "tool_use",
    "function_call": "tool_use",
    "length": "max_tokens",
    "content_filter": "refusal",
}


def _turn_from_openai(resp: Any) -> Turn:
    choice = resp.choices[0]
    msg = choice.message
    text = _coerce_decision(msg.content or "")
    tool_calls: list[ToolCall] = []
    for tc in getattr(msg, "tool_calls", None) or []:
        try:
            args = json.loads(tc.function.arguments or "{}")
        except json.JSONDecodeError:
            args = {}
        tool_calls.append(
            ToolCall(
                id=tc.id,
                name=tc.function.name,
                arguments=args,
                raw=getattr(tc, "extra_content", None),
            )
        )
    stop = _OPENAI_STOP.get(choice.finish_reason or "stop", "end_turn")
    structured: dict[str, Any] | None = None
    if not tool_calls and text.strip().startswith("{"):
        try:
            structured = json.loads(text)
        except json.JSONDecodeError:
            structured = None
    usage = getattr(resp, "usage", None)
    return Turn(
        text=text,
        tool_calls=tool_calls,
        stop_reason=stop,
        structured=structured,
        tokens_in=getattr(usage, "prompt_tokens", 0) if usage else 0,
        tokens_out=getattr(usage, "completion_tokens", 0) if usage else 0,
        raw={"finish_reason": choice.finish_reason},
    )


# ----------------------------------------------------------------------- recorded
class RecordedClient:
    """Replays a list of recorded turns in order (for `arbiter replay`)."""

    def __init__(self, turns: Sequence[dict[str, Any]], model: str = "recorded") -> None:
        self.model = model
        self._turns = list(turns)
        self._i = 0

    def complete(self, **_: Any) -> Turn:
        if self._i >= len(self._turns):
            return Turn(text="", stop_reason="end_turn")
        rec = self._turns[self._i]
        self._i += 1
        return Turn(
            text=rec.get("text", ""),
            tool_calls=[ToolCall(**tc) for tc in rec.get("tool_calls", [])],
            stop_reason=rec.get("stop_reason", "end_turn"),
            structured=rec.get("structured"),
            tokens_in=rec.get("tokens_in", 0),
            tokens_out=rec.get("tokens_out", 0),
        )


# ----------------------------------------------------------------------- scripted
class ScriptedClient:
    """Deterministic canned responses keyed by turn index (offline tests)."""

    def __init__(self, turns: list[Turn], model: str = "scripted") -> None:
        self.model = model
        self._turns = turns
        self._i = 0

    def complete(self, **_: Any) -> Turn:
        t = self._turns[min(self._i, len(self._turns) - 1)]
        self._i += 1
        return t
