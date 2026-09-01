# ADR-0004 — Hybrid orchestration: deterministic skeleton, agentic investigation loop

- **Status:** Accepted
- **Date:** 2026-09-02
- **Supersedes:** nothing · **Refines:** [ADR-0001](0001-deterministic-core-ai-at-the-boundary.md)

## Context

The track asks for "an agent." [ADR-0001](0001-deterministic-core-ai-at-the-boundary.md) confined the LLM to one step. The plan evaluation ([docs/11](../11-plan-evaluation-and-gaps.md) §2) found that as written, the LLM step was a single classify-and-explain call — a pipeline stage, not an agent. We need the "agent" claim to be true without weakening the determinism and auditability that ADR-0001 buys.

The 2026 standard for high-stakes financial workflows is **hybrid orchestration / state-machine-guided agents**: a deterministic skeleton with hardcoded flow and rules, and an AI "brain" that decides tactics *within* bounded sub-problems, with control always returning to the skeleton ([liviaerxin](https://liviaerxin.github.io/blog/agentic-vs-deterministic-orchestration), [Praetorian](https://www.praetorian.com/blog/deterministic-ai-orchestration-a-platform-architecture-for-autonomous-development/)).

## Decision

Arbiter is a **hybrid-orchestration agent**:

1. **Deterministic skeleton** — a finite state machine (`INGESTING → MATCHING → DECOMPOSING → CLASSIFYING → INVESTIGATING → SCORING → REPORTING`). Flow and order are fixed and replayable. No LLM calls.

2. **Agentic brain** — invoked once per ambiguous/unexplained exception, runs a bounded **investigation loop**: `PLAN → INVESTIGATE (iterative read-only tool calls) → HYPOTHESIZE & TEST (seek disconfirming evidence) → DECIDE (optimal stopping: conclude with a Proposal, or escalate with a sharpened question)`. Turn- and token-budgeted. Proposal-only tools. Human gate before any state change.

3. **Replay** — the skeleton is bit-reproducible; the brain's LLM interactions are recorded as events and *replayed* (not re-called) by `arbiter replay`. A completed run is always reproducible from its log.

4. **Evaluation** — the brain is measured as an agent: task-completion rate, tool-use accuracy, grounding, hallucination rate, escalation precision/recall, trajectory efficiency, cost/latency, and a confidence-calibration study ([docs/12](../12-agent-design.md) §6).

## Consequences

**Positive:**
- The "agent" claim is now substantive and demonstrable — planning, iterative investigation, hypothesis testing, autonomous stopping.
- The optimal-stopping decision directly embodies the verification-bottleneck thesis the whole product is built on.
- Determinism, auditability, and money-safety from ADR-0001 are fully preserved — the brain still only investigates and proposes.
- Agent-level evaluation gives judges the metrics they actually score on.

**Negative:**
- More complex than a single call: a real loop, tool definitions, trajectory logging, an agent eval set. ~3–4 extra build days (milestone M3 in [docs/10](../10-implementation-plan.md)).
- The investigation loop costs more per exception than one call — mitigated by the tiered model policy (Haiku triage → Opus for hard cases) and prompt caching.
- Non-determinism of fresh agent runs must be explained precisely (done: [docs/12](../12-agent-design.md) §4).

## Alternatives considered

- **Keep the single call** (v1): rejected — not credibly "an agent," weak on the AI-track evaluation.
- **Fully autonomous agent orchestrating the whole run**: rejected — non-deterministic money math, unauditable, violates ADR-0001, and pure AI orchestration is the wrong pattern for high-stakes finance.
- **Multi-agent (matcher / investigator / reviewer)**: rejected for v1 — 2–10× cost for no accuracy gain at this scale; revisit only if trajectory eval shows one agent can't hold context.
