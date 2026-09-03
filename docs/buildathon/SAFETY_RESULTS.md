# Safety Results

One page. Every number is reproducible with the command next to it.

## The one claim

**Arbiter never auto-resolves an exception. A human confirms, edits, or rejects
every proposal.** Everything below is about making the AI's mistakes *observable,
bounded, and recoverable* before that human decides.

## Headline metrics — `arbiter bench --dataset datasets/seed`

| metric | value | meaning |
|---|---|---|
| `unsafe_resolution_rate` | **0.0%** | of the 2 items ground truth says needed a human, none were auto-resolved |
| `rupees_protected` | **₹53,245 / ₹53,245 (100%)** | every ₹ of human-only impact was escalated or held for review |
| `replay_divergence` | **none** | a byte-identical re-run produced the same terminal hash |
| `fabricated_citations` | **0** | no proposal cited a record that doesn't exist |
| `injection_quarantined` | **1** | the injection scanner routed one record to SECURITY_REVIEW |

CI gate tolerance on `unsafe_resolution_rate`, `replay_divergence`,
`fabricated_citations`: **0**.

## The Safety Kernel — `safety/kernel.py`

Every agent proposal passes one deterministic, versioned function.
`Decision.action ∈ {SAFE, PROPOSE, ESCALATE, QUARANTINE}`, written onto the
event log. Order of checks:

1. fabricated citation → ESCALATE
2. grounded confidence < θ_escalate → ESCALATE
3. counterfactual arithmetic **contradicted** → ESCALATE
4. 2nd-model verifier rejects → ESCALATE
5. material money (R4+) and confidence < θ_conclude → ESCALATE
6. control category (R5) or money-movement / dispute category → PROPOSE, never SAFE
7. **SAFE** only if: low risk **and** high grounded confidence **and** category
   consistent **and** a category-specific arithmetic check *positively confirmed*
   the hypothesis. Otherwise PROPOSE.

Rule 7 is the important one: `SAFE` is *earned*, not "nothing flagged it."

## Agent benchmark — `arbiter agent-bench`

99 labelled cases, the real investigation loop:

| client | result |
|---|---|
| **oracle** (competent) | 100% task · 100% category · **100% escalation recall · 0 unsafe** · +44% lift |
| **reckless** (confidently wrong) | **0 material unsafe** · ~40% escalated by the harness · ~46% shown to a human who rejects them · 14 sub-rupee SAFE-gate slips (₹1.14 total across 99 cases; a human still confirms) |
| **fabricator** (cites a ghost record) | **100% escalated** |

See [AGENT_EVALUATION.md](AGENT_EVALUATION.md) for the full breakdown.

## Attack Arbiter — `arbiter attack`

12 deterministic tamperings. **12 contained · 0 unsafe · ₹0 unaccounted.**
See [ATTACK_RESULTS.md](ATTACK_RESULTS.md).

## Control invariants — `pytest packages/engine/tests/test_control_invariants.py`

14 named tests, one per property. See
[../CONTROL_INVARIANTS.md](../CONTROL_INVARIANTS.md).

## Fail-closed behaviour

| Failure | Result |
|---|---|
| LLM provider down / rate-limited | that exception escalates (`provider_unavailable`); the run completes |
| verifier returns unparseable JSON | treated as a rejection → escalate |
| agent hits its turn / token budget | escalate with partial evidence |
| a cited record doesn't exist | grounding → `fabricated` → escalate |
| counterfactual contradicts the hypothesis | escalate |
| a tampered DB row | `arbiter verify` fails and names the first broken event |

## What is NOT proven

* Agent accuracy on a **live frontier model** over the whole corpus (one live
  gpt-4o investigation captured; no full run — no key in CI).
* Real-world safety on a **real customer's data**. Zero customers.
