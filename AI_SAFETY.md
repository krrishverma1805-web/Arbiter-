# AI Safety

> Root-level summary. Depth: [`docs/12-agent-design.md`](docs/12-agent-design.md),
> [`docs/19-agent-contracts.md`](docs/19-agent-contracts.md),
> [`docs/14-security-and-trust.md`](docs/14-security-and-trust.md).

## The claim

**Arbiter never auto-resolves an exception.** A human confirms, edits, or rejects
every proposal. The LLM never moves money and never closes an exception — it
investigates one ambiguous exception at a time inside a bounded loop and emits
**a proposal or an escalation** (a structured, schema-validated object). A
deterministic **Safety Kernel** then decides how that proposal is *presented*:
escalate it, present it for review, or mark it low-risk enough that a human's
confirmation is a formality (`SAFE`) — but the human still confirms.

## The Safety Kernel — `packages/engine/arbiter_engine/safety/`

`evaluate(proposal, exc, snapshot, grounding, policy) -> Decision` where
`Decision.action ∈ {SAFE, PROPOSE, ESCALATE, QUARANTINE}` and
`Decision.risk ∈ R0..R5`. It is pure, deterministic, and versioned
(`policy.POLICY_VERSION`). The rules, in order:

1. **fabricated citation** → ESCALATE (`contradictory`)
2. **grounded confidence < θ_escalate** → ESCALATE (`evidence_exhausted`)
3. **counterfactual arithmetically contradicted** → ESCALATE (`counterfactual_contradicted`)
4. **verifier rejects** → ESCALATE (`verifier_rejected`)
5. **material money (R4+) and confidence < θ_conclude** → ESCALATE (`material_risk`)
6. **control-category risk (R5)** → PROPOSE, never SAFE, with a caveat
7. **money-movement / dispute category** (`policy.never_safe_categories`:
   DUPLICATE, CHARGEBACK, PARTIAL_PAYMENT, WRONG_ACCOUNT, MISSING_UTR,
   UNEXPLAINED) → PROPOSE, never SAFE — these always need a human sign-off
8. **SAFE** iff *all* of: tier ≤ R2, grounded confidence ≥ θ_conclude, category
   consistent with the evidence, **and a category-specific arithmetic check
   actively confirmed the hypothesis** (not merely stayed silent). Otherwise
   **PROPOSE**.

Rule 8 is the important one: `SAFE` is *earned*, not "no red flag was raised." A
confidently-wrong proposal for a category whose narrow checks happen not to fire
still only gets `PROPOSE` — a human confirms it.

The `Decision` is written onto every `AGENT_PROPOSAL_CREATED` / `AGENT_ESCALATED`
event, so an auditor sees exactly why the kernel let something through.

### Risk tiers — `safety/risk.py`

`assess_risk` returns the **max** of every rule that fires: R0 rounding within
tolerance · R1 small and category-consistent · R3 multiple candidates /
evidence–category mismatch / confidence in the uncertain band · R4 material
impact / unexplained with material money · R5 control category (SECURITY_REVIEW,
WRONG_ACCOUNT) / fabricated citation.

### Counterfactual verification — `safety/counterfactual.py`

Not a second LLM. For each hypothesis category it runs the arithmetic that would
have to hold if the hypothesis were true — a ROUNDING residual must be a few
paise per line; a period-straddle TIMING must have the *whole* expected credit
outstanding; a CHARGEBACK/PARTIAL must leave the settlement *short*, not over; a
DUPLICATE needs a repeated payment id whose amount matches the residual. It
returns `contradicted` (kernel escalates), `confirmed:` (a positive signal the
kernel needs before SAFE), or silence (no check applies — not a pass).

### Tool surface — `agent/tools.py`

Six read-only tools: `query_evidence`, `get_record`, `counterparty_history`,
`similar_exceptions`, `candidate_matches`, `decomposition_detail`. None can reach
the event store; `test_agent_tool_surface_is_entirely_read_only` runs every tool
and asserts the run snapshot is byte-identical afterward.

## Defense in depth

| Layer | Mechanism |
|---|---|
| Prompt injection | `exceptions/injection.py` — deterministic scanner over untrusted fields; a hit routes the exception to SECURITY_REVIEW and it never reaches the model |
| Tool surface | the agent's tools are read-only; there is no "resolve" or "write" tool |
| Grounding | every citation in a proposal must resolve to a record in the run; unresolved ⇒ `fabricated` ⇒ ESCALATE |
| Fail-closed | an unparseable / verdict-less verifier response escalates; a provider outage escalates the run, it does not sink it |
| No auto-resolve | the kernel's `SAFE` is advisory — a human still confirms every proposal |

## Measuring it — `arbiter agent-bench`

A labelled trajectory benchmark: ~100 real exceptions from seeded reconciliations,
each with its true category, whether a human was actually required, and the
evidence that supports it. The **real** `investigate()` loop runs for every case
against one of:

* **oracle** — a competent agent. Result: 100% task completion, 100% category
  accuracy, **100% of human-only cases escalated, 0 unsafe resolutions**, +44%
  lift over the trivial "escalate everything" policy.
* **reckless** — a confidently-wrong agent (proposes a tempting wrong category at
  0.97). Result: **0 material unsafe resolutions**; the deterministic harness
  escalates or flags every material one; the residual `SAFE`-gate slips are all
  on immaterial amounts (≈ ₹3k total across the corpus) — and a human still
  confirms.
* **fabricator** — cites a record that doesn't exist. Result: **100% escalated**.

Usefulness and safety are scored on separate scorecards. CI gates on: oracle
`unsafe_resolutions == 0` and `escalation_recall == 1.0`; reckless
`material_unsafe_resolutions == 0`; fabricator `fabricated_escalated_rate == 1.0`.

## Adversarial testing

`arbiter attack` mutates a clean dataset with a known tampering and checks
Arbiter never asserts a confident clean tie over a tampered record. See
[FAILURE_RECOVERY.md](FAILURE_RECOVERY.md).
