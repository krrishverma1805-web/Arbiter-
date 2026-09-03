"""Bring-your-own LLM key — header parsing and per-run env application.

(The API-level "async mode is rejected" guard is covered in test_api.py, which
has the client fixture.)
"""

from __future__ import annotations

import os

from arbiter_api import llm_ctx


class _H:
    def __init__(self, d: dict[str, str]) -> None:
        self._d = {k.lower(): v for k, v in d.items()}

    def get(self, k: str) -> str | None:
        return self._d.get(k.lower())


def test_from_headers_openai() -> None:
    env = llm_ctx.from_headers(
        _H({"X-LLM-Provider": "openai", "X-LLM-Key": "sk-abc", "X-LLM-Model": "gpt-4o"})
    )
    assert env == {
        "ARBITER_LLM_PROVIDER": "openai",
        "OPENAI_API_KEY": "sk-abc",
        "ARBITER_OPENAI_MODEL": "gpt-4o",
    }


def test_from_headers_infers_provider_from_key_shape() -> None:
    a = llm_ctx.from_headers(_H({"X-LLM-Key": "sk-ant-xyz"}))
    o = llm_ctx.from_headers(_H({"X-LLM-Key": "sk-proj-xyz"}))
    assert a and a["ARBITER_LLM_PROVIDER"] == "anthropic"
    assert o and o["ARBITER_LLM_PROVIDER"] == "openai"


def test_from_headers_none_without_key() -> None:
    assert llm_ctx.from_headers(_H({"X-LLM-Provider": "openai"})) is None
    assert llm_ctx.from_headers(None) is None


def test_applied_sets_and_restores_and_hides_the_server_key() -> None:
    had = os.environ.get("ANTHROPIC_API_KEY")
    os.environ["ANTHROPIC_API_KEY"] = "server-key"
    os.environ.pop("OPENAI_API_KEY", None)
    try:
        with llm_ctx.applied({"ARBITER_LLM_PROVIDER": "openai", "OPENAI_API_KEY": "caller-key"}):
            assert os.environ["OPENAI_API_KEY"] == "caller-key"
            assert os.environ["ARBITER_LLM_PROVIDER"] == "openai"
            assert "ANTHROPIC_API_KEY" not in os.environ  # server key hidden for the run
        assert os.environ["ANTHROPIC_API_KEY"] == "server-key"
        assert "OPENAI_API_KEY" not in os.environ
        assert "ARBITER_LLM_PROVIDER" not in os.environ
    finally:
        if had is None:
            os.environ.pop("ANTHROPIC_API_KEY", None)
        else:
            os.environ["ANTHROPIC_API_KEY"] = had


def test_applied_noop_without_env() -> None:
    before = dict(os.environ)
    with llm_ctx.applied(None):
        pass
    assert dict(os.environ) == before
