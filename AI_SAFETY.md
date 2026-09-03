# AI Safety

> Root-level summary. Depth: [`docs/12-agent-design.md`](docs/12-agent-design.md),
> [`docs/19-agent-contracts.md`](docs/19-agent-contracts.md),
> [`docs/14-security-and-trust.md`](docs/14-security-and-trust.md).

## The claim

The LLM never moves money and never closes an exception. It investigates one
ambiguous exception at a time inside a bounded loop and emits **a proposal or an
escalation** — a structured object, schema-validated. A deterministic **Safety
Kernel** then decides what happens to that proposal.

## The Safety Kernel — `packages/engine/arbiter_engine/safety/`

`evaluate(proposal, exc, snapshot, grounding, policy) -> Decision` where
`Decision.action ∈ {SAFE, PROPOSE, ESCALATE, QUARANTINE}` and
`Decision.risk ∈ R0..R5`. It is pure, deterministic, and versioned
(`policy.POLICY_VERSION`). The rules, in order:

1. **fabricated citation** → ESCALATE (`contradictory`)
2. **grounded confidence < θ_escalate** → ESCALATE (`evidence_exhausted`)
3. **counterfactual check fails** → ESCALATE (`counterfactual_contradicted`)
4. **verifier rejects** → ESCALATE (`verifier_rejected`)
5. **material money (R4+) and confidence < θ_conclude** → ESCALATE (`material_risk`)
6. **control-category risk (R5)** → PROPOSE, never SAFE, with a caveat
7. otherwise **SAFE** iff tier ≤ R2 ∧ confidence ≥ θ_conclude ∧ the category is
   consistent with the evidence; else **PROPOSE**

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
have to hold if the hypothesis were true — e.g. "if this ₹X gap is an unrecorded
refund, `refunds += X` closes the residual to 0" — and contradicts the proposal
if it doesn't. Independent of, and additional to, the second-model verifier.

## Defense in depth

| Layer | Mechanism |
|---|---|
| Prompt injection | `exceptions/injection.py` — deterministic scanner over untrusted fields; a hit routes the exception to SECURITY_REVIEW and it never reaches the model |
| Tool surface | the agent's tools are read-only; there is no "resolve" or "write" tool |
| Grounding | every citation in a proposal must resolve to a record in the run; unresolved ⇒ `fabricated` ⇒ ESCALATE |
| Fail-closed | an unparseable / verdict-less verifier response escalates; a provider outage escalates the run, it does not sink it |
| Headline metric | `bench` reports `unsafe_resolution_rate` — of the items ground truth says needed a human, how many the agent auto-resolved. Gate tolerance: **0**. See [BENCHMARK.md](BENCHMARK.md). |

## Adversarial testing

`arbiter attack` mutates a clean dataset with a known tampering and checks
Arbiter never asserts a confident clean tie over a tampered record. See
[FAILURE_RECOVERY.md](FAILURE_RECOVERY.md).
