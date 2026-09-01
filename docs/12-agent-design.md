# 12 — Agent Design

_The "agent" in "AI Finance Controller." What it is, how its loop works, why it's bounded the way it is, how it's evaluated, and how its judgment is validated rather than asserted._

Read [ADR-0001](adr/0001-deterministic-core-ai-at-the-boundary.md) and [ADR-0004](adr/0004-hybrid-orchestration.md) first.

---

## 1. What kind of agent this is

Arbiter is a **hybrid-orchestration agent**: a deterministic state-machine skeleton with an AI brain for the one sub-problem that is genuinely a judgment task. This is the 2026 standard for high-stakes financial workflows — pure AI orchestration is too risky for anything touching money; pure determinism can't handle the ambiguous tail ([liviaerxin, "Agentic vs Deterministic Orchestration"](https://liviaerxin.github.io/blog/agentic-vs-deterministic-orchestration), [Praetorian](https://www.praetorian.com/blog/deterministic-ai-orchestration-a-platform-architecture-for-autonomous-development/)).

```
        ┌──────────────────────── DETERMINISTIC SKELETON (the "controller") ────────────────────────┐
        │                                                                                           │
  run ─▶│  ingest ─▶ match(pass 1..4) ─▶ decompose ─▶ classify(rules) ─▶ rank ─▶ [residue] ─▶ memo   │
        │                                                        │                           ▲      │
        │                                                        ▼                           │      │
        │                                          ┌──────── AI BRAIN ────────┐               │      │
        │                                          │  investigation loop      │  proposals    │      │
        │                                          │  (per ambiguous          │──────────────▶│      │
        │                                          │   / unexplained          │  (gated,      │      │
        │                                          │   exception)             │   human       │      │
        │                                          └──────────────────────────┘   confirms)   │      │
        └───────────────────────────────────────────────────────────────────────────────────────────┘
```

The skeleton decides **what happens and in what order** — that is fixed, deterministic, and replayable. The brain decides **how to investigate one ambiguous item** — that is where model judgment earns its place. Control always returns to the skeleton when the brain finishes.

**Why this is a real agent, not a pipeline:** the brain plans its own investigation, chooses which evidence to gather and in what order, forms and tests hypotheses, and makes its own decision about when it has enough confidence to conclude versus when to escalate. That is agency, applied to a bounded problem.

---

## 2. The skeleton (deterministic controller)

A finite state machine. Each transition emits an event ([ADR-0002](adr/0002-event-sourced-store.md)). No LLM calls anywhere in here.

| State | Does | Exit condition |
|---|---|---|
| `INGESTING` | parse sources via the spec's format profiles; normalize to `Record`s; dedupe; quarantine bad rows | all sources ingested |
| `MATCHING` | run passes 1–4 in fixed order; emit `MATCH_*` events with confidence + provenance | all records processed |
| `DECOMPOSING` | verify the settlement identity per `settlement_utr` group; compute residuals | all groups checked |
| `CLASSIFYING` | apply spec rules to every non-match / broken-identity; assign taxonomy where a rule decides | all exceptions have a rule verdict or `AMBIGUOUS`/`UNEXPLAINED` |
| `INVESTIGATING` | for each `AMBIGUOUS`/`UNEXPLAINED` exception, invoke the brain (§3); collect `Proposal` or `ESCALATE` | all in-scope exceptions have a terminal agent state or hit budget |
| `SCORING` | compute the scorecard (matching + agent metrics) | — |
| `REPORTING` | render the Close Memo | — |

`--no-ai` skips `INVESTIGATING` entirely; those exceptions stay `UNEXPLAINED` and the memo says so.

---

## 3. The brain (investigation loop)

Invoked once per in-scope exception. A bounded agent loop implemented with the Anthropic SDK tool runner.

### 3.1 The loop

```
1. PLAN
   Input: the exception (records, residual, candidates, rule trail), the spec taxonomy.
   Output: a stated goal ("determine whether bank credit C is a delayed settlement or a
           misdirected payment") + a list of evidence it intends to gather.

2. INVESTIGATE  (repeat, up to N turns / token budget)
   The agent calls read-only tools:
     query_evidence(filters)        → related records, prior matches
     counterparty_history(name|id)  → how this payer/settlement behaved in prior cycles
     similar_exceptions(pattern)    → how humans resolved this shape before + the rules it produced
     candidate_matches(record_id)   → ranked fuzzy candidates with per-signal breakdown
     decomposition_detail(group)    → line-by-line identity math
   Each tool return is appended as an observation. The agent may revise its plan.

3. HYPOTHESIZE & TEST
   The agent commits to a candidate category and then actively seeks disconfirming evidence
   ("if this were a DUPLICATE, I'd expect payment_id to repeat — checking"). This step is
   prompted explicitly; the trajectory eval (§6) rewards it.

4. DECIDE  (optimal stopping)
   - confidence ≥ θ_conclude  → emit Proposal{category, confidence, explanation,
                                 evidence_refs[], suggested_action, draft_rule?}
   - evidence exhausted OR contradictory OR confidence < θ_escalate
                              → emit Escalate{what_i_know, what_is_missing,
                                 the_one_question_a_human_should_answer}
   - budget hit               → emit Escalate{..., reason: "budget"}  (a scorecard line)
```

### 3.2 Why optimal stopping is the point

The verification-bottleneck thesis ([doc 01](01-market-and-thesis.md) §2.1): a reviewer gathers evidence until confidence crosses a threshold; expected verification time peaks at maximum uncertainty. Arbiter's brain **is** that reviewer, automated for the cases where the evidence is sufficient, and it hands the human a _sharpened_ question (not the raw exception) for the cases where it isn't. The product value is the time between "raw exception" and "one specific question" — collapsed from minutes of human digging to seconds.

### 3.3 Hard bounds (unchanged from ADR-0001)

- Every tool is read-only or proposal-only. No tool mutates a match, a record, a ledger, or money.
- `Proposal.category` is an enum of the spec taxonomy (strict structured output) — the model cannot invent a category.
- Turn budget (default 6) + token budget (per spec, default 12k) per exception. Exceed → escalate.
- The frozen system prompt is hashed; model id + prompt hash + fenced evidence-bundle hash are on every proposal event.
- Untrusted record content (`description`, `notes`, bank narration) is `<untrusted-data>`-fenced ([doc 14](14-security-and-trust.md)).
- Human accept/edit/reject required before any proposal affects state.

---

## 4. Determinism & replay (precise statement)

| Component | Guarantee |
|---|---|
| Skeleton (ingest → classify, score, memo) | **Bit-reproducible.** Same inputs + spec + seed → identical event hash chain. |
| Brain (investigation loop) | **Not** reproducible on a fresh call (LLM non-determinism). Made **replayable** by recording every request/response pair in the event log as `AGENT_INTERACTION` events. |
| `arbiter replay <run-id>` | Re-runs the skeleton deterministically; **replays recorded agent interactions** instead of re-calling the API. Full run reproduced from its log. |
| `arbiter run --reinvestigate <run-id>` | Forces fresh agent calls (for testing agent/prompt changes) — produces a new run id. |

So: a completed run is always fully reproducible from its own event log. Fresh agent behavior is tested deliberately, not accidentally.

---

## 5. Model strategy — decided by ablation, not default

We do **not** assert a model. We run [`arbiter bench --ablate`](07-evaluation-and-benchmark.md) across:

| Config | Role tested | Expected use |
|---|---|---|
| `--no-ai` | deterministic baseline | the floor; always reported |
| `claude-haiku-4-5` | cheap bulk triage classification | likely: first-pass category guess on all exceptions |
| `claude-sonnet-5` | mid-tier investigation | candidate default for routine ambiguous cases |
| `claude-opus-5` (adaptive thinking, effort high) | deep investigation | `UNEXPLAINED` and contested cases |

Reported per config: category accuracy, resolution usefulness, escalation precision/recall, **cost/exception**, **latency p50/p95**. The shipped default is a **tiered policy** (Haiku triage → escalate uncertain cases to Opus) if and only if the data shows it beats single-model on the cost/accuracy frontier. The ablation table goes in the README. _This_ is "the right tool in the right place," shown with numbers.

Cost control: the frozen system prompt + spec + taxonomy are a stable prompt-cache prefix, so per-exception marginal cost is the evidence bundle + output only. `bench` runs use the Batch API (50% cheaper).

---

## 6. Agent evaluation

Matching metrics are in [doc 07](07-evaluation-and-benchmark.md). This section adds the **agent scorecard**, computed by `arbiter bench` against a labeled trajectory set that `datagen` emits alongside `ground_truth.json`.

### 6.1 Metrics

| Metric | Definition | Target |
|---|---|---|
| **Task-completion rate** | exceptions reaching a correct terminal state (right `Proposal` OR a justified `ESCALATE`) / all in-scope | ≥ 80% |
| **Category accuracy** | correct category / all `Proposal`s | ≥ 85% |
| **Resolution usefulness** | `suggested_action` matches `correct_resolution` (exact or human-judged equivalent) / all `Proposal`s | ≥ 70% |
| **Tool-use accuracy** | right tool + right args at the right step, scored on a rubric over a labeled trajectory sample | ≥ 90% |
| **Grounding / faithfulness** | on a counterfactual sample, does the proposal change when a tool return is altered? (it should) | ≥ 95% "sensitive" |
| **Hallucination rate** | proposals with an evidence-ref or factual claim not supported by any tool return | ≤ 2% |
| **Escalation precision** | escalations that genuinely needed a human / all escalations | ≥ 85% |
| **Escalation recall** | cases needing a human that were escalated / all cases needing a human | ≥ 90% |
| **Trajectory efficiency** | tool calls per resolved exception vs. the ideal-path count | ≤ 1.5× ideal |
| **Cost / exception**, **latency p50/p95** | from `usage` + timers | < $0.05, < 8s p50 |
| **AI lift** | category accuracy (with brain) − category accuracy (`--no-ai`) | report the delta — this is the measured value of the AI |

### 6.2 Confidence calibration study

An asserted confidence is a liability if it's wrong. `arbiter bench --calibration`:
1. Bucket every `Proposal` by stated confidence (0.5–0.6, 0.6–0.7, …).
2. For each bucket, compute observed accuracy (vs ground truth).
3. Plot the reliability diagram; compute **Expected Calibration Error (ECE)**.
4. If ECE > 0.05, fit a monotonic recalibration map (isotonic) on a held-out split and apply it; the cockpit displays recalibrated confidence and the docs disclose it.

The cockpit's confidence bars are only shown once ECE is acceptable. This is stated in the README.

### 6.3 Observability (traces)

Every run emits OpenTelemetry spans ([doc 13 §3](13-production-readiness.md)): one span per pass, one per exception investigation, nested child spans per tool call and per LLM call (with token counts, latency, cache hits). `arbiter run --trace` writes an OTLP file you can load into any viewer. This is the agent-observability standard — every step a typed, inspectable span with parent/child preserved ([Braintrust](https://www.braintrust.dev/articles/agent-observability-complete-guide-2026), [Arize](https://arize.com/blog/best-ai-observability-tools-for-autonomous-agents-in-2026/)).

---

## 7. Known failure modes (honest)

Maintained in [`docs/KNOWN-FAILURE-MODES.md`](KNOWN-FAILURE-MODES.md) with real cases. Categories we expect and how each is contained:

| Failure | Cause | Containment |
|---|---|---|
| Wrong category on a genuinely undecidable case | evidence truly insufficient | should have escalated — escalation-recall metric catches this; calibration keeps confidence low |
| Over-confident on a plausible-but-wrong hypothesis | model anchored early, didn't seek disconfirmation | the explicit "test your hypothesis" loop step + trajectory eval penalize it; human gate is the backstop |
| Tool-call thrash (many redundant queries) | weak planning | trajectory-efficiency metric; turn budget |
| Escalates too much (low precision) | over-cautious prompt | tune `θ_escalate` against the escalation-precision target |
| Injected instruction in a note | attacker-controlled field | fenced + scanned + quarantined ([doc 14](14-security-and-trust.md)); proposal-only tools mean no money impact even if it slips through |
| Cost spike on a hard batch | many `UNEXPLAINED` → many Opus investigations | per-run cost ceiling; tiered model policy; `budget` escalations reported |

Showing these, with the containment, is the Failure-Recovery criterion answered properly.

---

## 8. Why not more agent

Considered and rejected for v1:
- **Agent picks the matching strategy / passes** — non-deterministic money math; violates ADR-0001.
- **Agent auto-evolves the spec** — AI-authored control logic applied without review is the exact anti-pattern; the learning loop keeps a human diff-review gate.
- **Multi-agent (separate matcher / investigator / reviewer agents)** — 2–10× cost multiplier ([TrueFoundry](https://www.truefoundry.com/blog/multi-agent-orchestration-frameworks)) for no accuracy gain at this scale; one well-instrumented agent loop is the right call. Revisit only if the trajectory eval shows a single agent can't hold the context.
- **Agent posts journal entries** — the "act on money" leap; deferred until real customer trust exists ([doc 08](08-why-it-might-not-sell.md) R8).
