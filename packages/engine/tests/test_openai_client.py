"""The OpenAI adapter's translation layer (no network).

Covers the three risky pieces: Anthropic-shaped messages -> OpenAI chat shape,
an OpenAI reply -> `Turn`, and coercing a near-miss decision back onto the
strict investigator contract.
"""

from __future__ import annotations

from types import SimpleNamespace

from arbiter_engine.agent.client import (
    _coerce_decision,
    _nearest_action,
    _to_openai_messages,
    _turn_from_openai,
)


def test_plain_messages_pass_through() -> None:
    assert _to_openai_messages({"role": "user", "content": "hi"}) == [
        {"role": "user", "content": "hi"}
    ]


def test_assistant_tool_use_becomes_openai_tool_calls() -> None:
    m = {
        "role": "assistant",
        "content": [
            {"type": "text", "text": "checking"},
            {"type": "tool_use", "id": "t1", "name": "query_evidence", "input": {"source": "bank"}},
        ],
    }
    (out,) = _to_openai_messages(m)
    assert out["role"] == "assistant"
    assert out["content"] == "checking"
    assert out["tool_calls"][0]["id"] == "t1"
    assert out["tool_calls"][0]["function"]["name"] == "query_evidence"
    assert out["tool_calls"][0]["function"]["arguments"] == '{"source": "bank"}'


def test_tool_result_becomes_one_tool_message_per_call() -> None:
    m = {
        "role": "user",
        "content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": "{}"},
            {"type": "tool_result", "tool_use_id": "t2", "content": "[]"},
        ],
    }
    out = _to_openai_messages(m)
    assert [o["role"] for o in out] == ["tool", "tool"]
    assert [o["tool_call_id"] for o in out] == ["t1", "t2"]


def test_turn_from_openai_maps_tool_calls_and_stop() -> None:
    resp = SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason="tool_calls",
                message=SimpleNamespace(
                    content=None,
                    tool_calls=[
                        SimpleNamespace(
                            id="c1",
                            function=SimpleNamespace(
                                name="decomposition_detail", arguments='{"settlement_utr": "U1"}'
                            ),
                        )
                    ],
                ),
            )
        ],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=3),
    )
    t = _turn_from_openai(resp)
    assert t.stop_reason == "tool_use"
    assert t.tool_calls[0].name == "decomposition_detail"
    assert t.tool_calls[0].arguments == {"settlement_utr": "U1"}
    assert (t.tokens_in, t.tokens_out) == (10, 3)


def test_coerce_snaps_a_freeform_action_onto_the_enum() -> None:
    raw = (
        '{"kind":"proposal","category":"TIMING","confidence":0.8,'
        '"explanation":"late settlement",'
        '"evidence_refs":[{"claim":"c","record_id":"r","field":"settled_at"}],'
        '"hypotheses_tested":["x"],'  # not in the contract — must be dropped
        '"suggested_action":{"action":"review and resolve","detail":"look"}}'
    )
    import json

    fixed = json.loads(_coerce_decision(raw))
    assert "hypotheses_tested" not in fixed
    assert fixed["suggested_action"]["action"] == "route_to_human"
    assert fixed["category"] == "TIMING"


def test_coerce_leaves_non_decisions_alone() -> None:
    assert _coerce_decision("just some analysis text") == "just some analysis text"
    assert _coerce_decision('{"foo": 1}') == '{"foo": 1}'


def test_nearest_action() -> None:
    assert _nearest_action("accept_variance") == "accept_variance"
    assert _nearest_action("raise a dispute") == "raise_dispute"
    assert _nearest_action("flag the overcharge") == "flag_overcharge"
    assert _nearest_action("something unmappable") == "route_to_human"
