"""Live agent test — hits the Anthropic API. Runs only in the nightly `-m live`
suite (docs/25 §3). Skipped automatically without ANTHROPIC_API_KEY."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="no ANTHROPIC_API_KEY"),
]


def test_real_investigation_produces_a_terminal_state(adversarial_dataset: Path, spec_path: Path):
    from arbiter_engine.agent.client import AnthropicClient
    from arbiter_engine.agent.investigator import investigate
    from arbiter_engine.agent.tools import RunSnapshot, Tools
    from arbiter_engine.events.store import EventStore
    from arbiter_engine.run import RunInputs, execute
    from arbiter_engine.specs import load_spec

    store = EventStore("sqlite://")
    proj = execute(
        store, RunInputs(spec_path=spec_path, dataset_dir=adversarial_dataset, no_ai=True)
    )
    spec = load_spec(spec_path)
    exc = next(e for e in proj.exceptions if e.category in (None, "UNEXPLAINED"))

    inv = investigate(
        exc,
        Tools(RunSnapshot.from_projection(proj)),
        AnthropicClient(model="claude-haiku-4-5"),
        spec,
        turn_budget=4,
    )
    assert inv.outcome in ("proposal", "escalate")
    assert inv.turns >= 1
    if inv.outcome == "proposal":
        assert inv.proposal is not None
        assert inv.proposal.evidence_refs  # every proposal cites evidence
    else:
        assert inv.escalation is not None
        assert inv.escalation.question


def test_real_verifier_pass_returns_a_verdict(adversarial_dataset: Path, spec_path: Path):
    """The second-opinion verifier (docs/28 §1.3) against the real API — it must
    return a proposal or a `verifier_rejected` escalation, never crash."""
    from arbiter_engine.agent.client import AnthropicClient
    from arbiter_engine.agent.investigator import investigate
    from arbiter_engine.agent.tools import RunSnapshot, Tools
    from arbiter_engine.events.store import EventStore
    from arbiter_engine.run import RunInputs, execute
    from arbiter_engine.specs import load_spec

    store = EventStore("sqlite://")
    proj = execute(
        store, RunInputs(spec_path=spec_path, dataset_dir=adversarial_dataset, no_ai=True)
    )
    spec = load_spec(spec_path)
    exc = next(e for e in proj.exceptions if e.category in (None, "UNEXPLAINED"))

    inv = investigate(
        exc,
        Tools(RunSnapshot.from_projection(proj)),
        AnthropicClient(model="claude-haiku-4-5"),
        spec,
        turn_budget=4,
        verifier=AnthropicClient(model="claude-haiku-4-5", effort="low"),
    )
    assert inv.outcome in ("proposal", "escalate")
    if inv.outcome == "proposal":
        # a verifier turn was recorded alongside the investigation turns
        assert any(i.get("role") == "verifier" for i in inv.interactions)
