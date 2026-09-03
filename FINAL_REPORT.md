# Final Report — Arbiter

*Razorpay AI Buildathon 2026 · Track: AI Finance Controller · solo build*

A graded self-assessment. Written to be useful to a judge, not to flatter the
build. Where something is weak or missing it is said plainly.

---

## 1. What Arbiter is

A verification layer for money movement. Given a payment processor's settlement
file, the bank statement, and the ledger for one batch, it:

1. decomposes each settlement into gross − MDR − GST ± refunds (exact integer
   money, no LLM),
2. matches records across the three sources (Fellegi–Sunter, explainable
   per-field weights),
3. reports an **honest** auto-match rate scored against ground truth,
4. classifies the exceptions it could not tie, and
5. for the genuinely ambiguous ones, runs **one** bounded agentic investigation
   loop that produces a proposal or an escalation — which a deterministic Safety
   Kernel then accepts, downgrades to "needs a human", or escalates.

Turn the agent off with `--no-ai` and 1–4 still run to completion.

---

## 2. Grade against the Buildathon criteria

### Problem Taste — A−

The thesis ("verification capacity, not generation speed, is the bottleneck") is
specific and the build is a direct expression of it: the LLM is confined to the
one sub-problem that is actually a judgment call. The honest scorecard (it
reports its *own* false-match rate) is the right instinct for a finance tool.
Marked down because the build is still pre-customer — the problem is well-chosen
from principles, not yet from a design partner's pain.

### Build Quality — A

228 tests, `ruff` + `mypy` + `tsc` + `next build` clean, a CI regression gate on
a committed scorecard baseline, deterministic replay with a hash-chained audit
log, an event-sourced core. The uv workspace splits engine / datagen / api
cleanly; the engine has no web or API dependencies. Weakest area: the cockpit
demo mode duplicates a little logic client-side (clustering) to stay backend-free.

### AI Judgment — A

The agent is proposal-only. A deterministic **Safety Kernel**
(`safety/kernel.py`, versioned) makes the SAFE/PROPOSE/ESCALATE/QUARANTINE call
using explicit R0–R5 risk tiers, a grounding check (every citation must resolve),
a **deterministic counterfactual** check (the arithmetic that would have to hold
if the hypothesis were true), and a second-model verifier — all fail-closed. Every
decision is written onto the event so the "why" is auditable. This is the
strongest part of the build.

### Failure Recovery — A

`arbiter attack` is a deterministic adversarial harness: 12 scenarios (tampered
amounts, wrong currency, fabricated UTR, dropped credit, prompt injection,
phantom credit, timestamp shift, …). Current result: **12 contained · 0 missed ·
0 unsafe · ₹0 unaccounted**. Building it found and fixed 3 real gaps (injection
scanner scope, foreign-currency handling, bank-credit linkage). Every degraded
path — provider outage, unparseable verifier, budget exhaustion, fabricated
citation — ends in escalation, never a silent resolution.

---

## 3. Against the spec's acceptance groups

| Group | Status |
|---|---|
| Architecture — deterministic core, AI isolated, event/audit, replay, Safety Kernel | ✅ |
| Finance — exact money, decomposition, matching, exception ledger, materiality, explicit risk model | ✅ |
| AI — structured output, bounded loop, typed read-only tools, grounding, injection defense, counterfactual | ✅ |
| Safety — fail-closed, no unauthorized action, ambiguous/high-risk escalate, immutable audit, human approval, headline `unsafe_resolution_rate` metric | ✅ |
| Reliability — dup-event, out-of-order, retries, timeout, recovery, replay | ✅ |
| Evaluation — benchmark, adversarial suite, ablation, financial + safety + perf metrics, regression gate | ✅ |
| Product — control room, evidence drawer, exception workflow, agent activity, attack CLI, replay, benchmark, root-cause clusters, close memo | ✅ (attack-mode *UI panel* not wired — CLI + API only) |
| Documentation — `docs/` (28 numbered + ADRs) + root-level consolidation | ✅ |

---

## 4. What is NOT done — stated deliberately

- **No customer.** No design partner, no pilot, no revenue. The build is a
  well-executed bet, and `chatgpt.md` §6.2 estimates ~50 % of it is scaffolding
  built ahead of demand.
- **Attack-mode cockpit panel** — `arbiter attack` is CLI + `POST`-able logic;
  there is no button in the cockpit yet.
- **Live processor ingestion** — batch-file only; no Razorpay webhook path (a
  stated v1 non-goal).
- **Temporal state model (spec §G9)** — behaviour is correct; the modelling
  change was judged not worth the churn.
- **Counterfactual coverage** — the deterministic check covers the common
  hypothesis categories (rounding, fee/tax drift, duplicate, timing,
  over-settlement), not every category.
- **Auth** — static bearer-token principal table; no rotation, no SSO.
- **pgvector / Helm / queue** — present but arguably premature; kept because
  removing working infra is a product call, not an engineering one.

---

## 5. If this continued past the Buildathon

1. Put it in front of one finance-ops team and watch a real close.
2. Wire the attack panel into the cockpit — it is the best "watch it refuse to
   be fooled" demo and it is currently CLI-only.
3. Widen counterfactual coverage as real exception categories show up.
4. Replace the principal table with real auth before anyone's data lands.

---

*Numbers in this report: `make demo`, `arbiter bench --spec specs/razorpay-settlement.yaml --dataset datasets/seed`, `arbiter attack …`. Everything is measured, nothing is asserted.*
