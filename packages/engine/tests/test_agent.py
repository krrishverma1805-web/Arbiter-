"""The investigation agent — offline (no API key needed).

Uses ScriptedClient / a fake to drive the loop deterministically. The live path
(AnthropicClient) is exercised only by the nightly `-m live` suite.
"""

from __future__ import annotations

from pathlib import Path

from arbiter_engine.agent.client import ToolCall, Turn
from arbiter_engine.agent.investigator import investigate
from arbiter_engine.agent.schemas import Escalate, Proposal
from arbiter_engine.agent.tools import RunSnapshot, Tools
from arbiter_engine.events.payloads import EventType
from arbiter_engine.events.store import EventStore
from arbiter_engine.models import ReconException
from arbiter_engine.run import RunInputs, execute
from arbiter_engine.specs import load_spec


class _Client:
    """Returns pre-scripted turns; records the messages it was given."""

    model = "test"

    def __init__(self, turns: list[Turn]) -> None:
        self.turns = turns
        self.i = 0
        self.seen_system: list[str] = []
        self.seen_messages: list[list] = []

    def complete(self, *, system, messages, tools, force_structured=None):  # noqa: ANN001
        self.seen_system.append(system)
        self.seen_messages.append(messages)
        t = self.turns[min(self.i, len(self.turns) - 1)]
        self.i += 1
        return t


def _snapshot(dataset: Path, spec_path: Path):
    store = EventStore("sqlite://")
    proj = execute(store, RunInputs(spec_path=spec_path, dataset_dir=dataset, no_ai=True))
    return store, proj, load_spec(spec_path)


def _first_unexplained(proj) -> ReconException:  # noqa: ANN001
    return next(e for e in proj.exceptions if e.category in (None, "UNEXPLAINED"))


def test_agent_investigates_then_proposes(adversarial_dataset: Path, spec_path: Path):
    _store, proj, spec = _snapshot(adversarial_dataset, spec_path)
    exc = _first_unexplained(proj)
    snap = RunSnapshot.from_projection(proj)

    client = _Client(
        [
            Turn(  # turn 0: plan + a tool call
                text="Plan: check whether a settlement batch nets to this credit.",
                tool_calls=[ToolCall("t1", "query_evidence", {"source": "razorpay_recon"})],
                stop_reason="tool_use",
                tokens_in=500,
                tokens_out=120,
            ),
            Turn(  # turn 1: conclude with a proposal
                text="",
                structured={
                    "kind": "proposal",
                    "category": "TIMING",
                    "confidence": 0.86,
                    "explanation": "The settlement lands one day after the period end.",
                    "evidence_refs": [
                        {
                            "claim": "settled_at is after the period close",
                            "record_id": exc.record_ids[0],
                            "field": "settled_at",
                        }
                    ],
                    "hypotheses_tested": ["delayed settlement", "second processor"],
                    "suggested_action": {"action": "carry_forward", "detail": "clears next cycle"},
                },
                stop_reason="end_turn",
                tokens_in=300,
                tokens_out=200,
            ),
        ]
    )
    inv = investigate(exc, Tools(snap), client, spec, turn_budget=6)
    assert inv.outcome == "proposal"
    assert isinstance(inv.proposal, Proposal)
    assert inv.proposal.category == "TIMING"
    assert inv.tool_calls == 1
    assert inv.turns == 2
    assert inv.tokens_in + inv.tokens_out > 0
    # grounding ran and the citation resolved to a real record
    assert inv.grounding is not None
    assert inv.grounding.grounded and not inv.grounding.fabricated
    assert inv.grounding.grounded_confidence > 0.55
    # the frozen system prompt was used verbatim
    assert "You are Arbiter's exception investigator." in client.seen_system[0]


def _proposal_turn(exc: ReconException, **over: object) -> Turn:
    body: dict[str, object] = {
        "kind": "proposal",
        "category": "TIMING",
        "confidence": 0.9,
        "explanation": "x",
        "evidence_refs": [{"claim": "c", "record_id": exc.record_ids[0], "field": "settled_at"}],
        "hypotheses_tested": ["h"],
        "suggested_action": {"action": "carry_forward", "detail": "d"},
    }
    body.update(over)
    return Turn(structured=body, stop_reason="end_turn", tokens_in=100, tokens_out=80)


def test_fabricated_evidence_ref_escalates(adversarial_dataset: Path, spec_path: Path):
    """A proposal that cites a record id which isn't in the run is a hallucination
    — it must not reach the human as a proposal (docs/28 §1.3)."""
    _store, proj, spec = _snapshot(adversarial_dataset, spec_path)
    exc = _first_unexplained(proj)
    snap = RunSnapshot.from_projection(proj)
    client = _Client(
        [
            _proposal_turn(
                exc,
                evidence_refs=[
                    {
                        "claim": "fake",
                        "record_id": "razorpay_recon:9999:deadbeef",
                        "field": "amount",
                    }
                ],
            )
        ]
    )
    inv = investigate(exc, Tools(snap), client, spec)
    assert inv.outcome == "escalate"
    assert inv.escalation is not None and inv.escalation.reason == "contradictory"
    assert inv.grounding is not None and inv.grounding.fabricated


def test_weak_grounded_confidence_escalates(adversarial_dataset: Path, spec_path: Path):
    """A grounded but low-confidence proposal falls back to the human."""
    _store, proj, spec = _snapshot(adversarial_dataset, spec_path)
    exc = _first_unexplained(proj)
    snap = RunSnapshot.from_projection(proj)
    inv = investigate(exc, Tools(snap), _Client([_proposal_turn(exc, confidence=0.3)]), spec)
    assert inv.outcome == "escalate"
    assert inv.grounding is not None and inv.grounding.grounded_confidence < 0.55


def test_category_inconsistent_with_evidence_is_penalised(
    adversarial_dataset: Path, spec_path: Path
):
    """DUPLICATE proposed with no repeated payment_id → category check fails,
    confidence is capped, and the exception escalates."""
    _store, proj, spec = _snapshot(adversarial_dataset, spec_path)
    exc = _first_unexplained(proj)
    snap = RunSnapshot.from_projection(proj)
    inv = investigate(
        exc,
        Tools(snap),
        _Client([_proposal_turn(exc, category="DUPLICATE", confidence=0.95)]),
        spec,
    )
    assert inv.grounding is not None
    assert not inv.grounding.category_consistent
    assert inv.outcome == "escalate"


def test_agent_escalates_when_told(adversarial_dataset: Path, spec_path: Path):
    _store, proj, spec = _snapshot(adversarial_dataset, spec_path)
    exc = _first_unexplained(proj)
    snap = RunSnapshot.from_projection(proj)
    client = _Client(
        [
            Turn(
                structured={
                    "kind": "escalate",
                    "what_i_know": "orphan credit, no matching batch",
                    "what_is_missing": "whether a second processor exists",
                    "question": "Is there another payment processor feeding this account?",
                    "reason": "evidence_exhausted",
                },
                stop_reason="end_turn",
            )
        ]
    )
    inv = investigate(exc, Tools(snap), client, spec)
    assert inv.outcome == "escalate"
    assert isinstance(inv.escalation, Escalate)
    assert inv.escalation.reason == "evidence_exhausted"


def test_agent_escalates_on_budget_exhaustion(adversarial_dataset: Path, spec_path: Path):
    _store, proj, spec = _snapshot(adversarial_dataset, spec_path)
    exc = _first_unexplained(proj)
    snap = RunSnapshot.from_projection(proj)
    # every turn just calls a tool, never concludes
    loop = _Client([Turn(tool_calls=[ToolCall("t", "query_evidence", {})], stop_reason="tool_use")])
    inv = investigate(exc, Tools(snap), loop, spec, turn_budget=3)
    assert inv.outcome == "escalate"
    assert inv.escalation is not None
    assert inv.escalation.reason == "budget"


def test_malformed_output_becomes_escalation(adversarial_dataset: Path, spec_path: Path):
    _store, proj, spec = _snapshot(adversarial_dataset, spec_path)
    exc = _first_unexplained(proj)
    snap = RunSnapshot.from_projection(proj)
    client = _Client(
        [Turn(text="here is my answer: it is a duplicate", stop_reason="end_turn")] * 4
    )
    inv = investigate(exc, Tools(snap), client, spec, turn_budget=3)
    assert inv.outcome == "escalate"  # never guessed a category


def test_security_review_is_never_investigated(adversarial_dataset: Path, spec_path: Path):
    store = EventStore("sqlite://")
    proj = execute(store, RunInputs(spec_path=spec_path, dataset_dir=adversarial_dataset))
    started = {
        p["exception_id"]
        for t, p in store.iter_payloads(proj.run_id)
        if t == EventType.AGENT_INVESTIGATION_STARTED
    }
    sec = {e.id for e in proj.exceptions if e.category == "SECURITY_REVIEW"}
    assert sec  # the demo data has an injected note
    assert not (started & sec), "a SECURITY_REVIEW exception was sent to the agent"


def test_injection_note_is_fenced_in_the_task_message(adversarial_dataset: Path, spec_path: Path):
    from arbiter_engine.agent.tools import build_task_message

    _store, proj, spec = _snapshot(adversarial_dataset, spec_path)
    snap = RunSnapshot.from_projection(proj)
    # find any record carrying untrusted content and build a task around it
    exc = next(
        (
            e
            for e in proj.exceptions
            if any(snap.records[r].untrusted for r in e.record_ids if r in snap.records)
        ),
        proj.exceptions[0],
    )
    msg = build_task_message(exc, snap, spec, {"theta_conclude": 0.8, "theta_escalate": 0.55})
    # raw injection strings never appear un-fenced
    if "IGNORE ALL PREVIOUS INSTRUCTIONS" in msg:
        assert "<untrusted-record-data" in msg
        assert "‹untrusted-record-data" not in msg  # only the wrapper's own '<' survives
