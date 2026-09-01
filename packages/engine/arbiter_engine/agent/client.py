"""Pluggable LLM client for the investigation agent.

  AnthropicClient   — the real thing (needs ANTHROPIC_API_KEY)
  RecordedClient    — replays AGENT_INTERACTION events; used by `arbiter replay`
                      so a completed run reproduces without calling the API
  ScriptedClient    — canned turns; used by the offline test suite

Every client returns a `Turn` (assistant content blocks + stop reason + usage),
and the investigator records each request/response pair as an event.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


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
        resp = self._client.messages.create(**kwargs)
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
