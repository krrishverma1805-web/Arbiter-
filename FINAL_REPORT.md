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

255 tests, `ruff` + `mypy` + `tsc` + `next build` clean, a CI regression gate on
a committed scorecard baseline, deterministic replay with a hash-chained audit
log, an event-sourced core. The uv workspace splits engine / datagen / api
cleanly; the engine has no web or API dependencies. Weakest area: the cockpit
demo mode duplicates a little logic client-side (clustering) to stay backend-free.

### AI Judgment — A

The agent is proposal-only and **Arbiter never auto-resolves** — a human confirms
every proposal. A deterministic **Safety Kernel** (`safety/kernel.py`, versioned)
rules SAFE/PROPOSE/ESCALATE/QUARANTINE using explicit R0–R5 risk tiers, a
grounding check, a **deterministic counterfactual** check (which now returns
*positive confirmation*, not just contradiction — SAFE is earned), a second-model
verifier, and a never-safe list for money-movement categories. All fail-closed.
Every decision is written onto the event.

The `arbiter agent-bench` trajectory benchmark (99 labelled cases, the real
investigation loop) scores usefulness and safety **separately**: a competent
agent gets 100% task completion, 100% escalation recall, 0 unsafe resolutions,
+44% lift over "escalate everything"; a deliberately confidently-wrong agent
reaches **0 material unsafe resolutions** (its SAFE-gate slips are sub-rupee
category ambiguities, ₹1.14 total across the corpus, and a human still confirms);
a fabricated citation escalates 100% of the time. The benchmark also *found* a
real harness gap — the kernel used to mark wrong proposals SAFE when the narrow
checks didn't fire — which is now fixed. This is the strongest part of the build.

### Failure Recovery — A

`arbiter attack` is a deterministic adversarial harness: 12 scenarios (tampered
amounts, wrong currency, fabricated UTR, dropped credit, prompt injection,
phantom credit, timestamp shift, …). Current result: **12 contained · 0 missed ·
0 unsafe · ₹0 unaccounted**. Building it found and fixed 4 real gaps (injection
scanner scope, foreign-currency handling, implausible-date handling,
bank-credit linkage). Every degraded path — provider outage, unparseable
verifier, budget exhaustion, fabricated citation — ends in escalation, never a
silent resolution. 14 named control-invariant tests
(`docs/CONTROL_INVARIANTS.md`), one per property, are the executable proof.

---

## 3. Against the spec's acceptance groups

| Group | Status |
|---|---|
| Architecture — deterministic core, AI isolated, event/audit, replay, Safety Kernel | ✅ |
| Finance — exact money, decomposition, matching, exception ledger, materiality, explicit risk model | ✅ |
| AI — structured output, bounded loop, typed read-only tools, grounding, injection defense, counterfactual | ✅ |
| Safety — fail-closed, no unauthorized action, ambiguous/high-risk escalate, immutable audit, human approval, headline `unsafe_resolution_rate` metric | ✅ |
| Reliability — dup-event, out-of-order, retries, timeout, recovery, replay | ✅ |
| Evaluation — matching benchmark, **agent trajectory benchmark**, adversarial suite, ablation, financial + safety + perf metrics, regression gate | ✅ |
| Product — control room, **structured investigation chain + Safety Kernel card + "why not resolved" + "explain this number"**, exception workflow, attack CLI + panel, replay, benchmark, root-cause clusters, close memo | ✅ |
| Documentation — `docs/` (28 numbered + ADRs) + 7 root summaries + `CLAIMS.md` + `CONTROL_INVARIANTS.md` + `docs/buildathon/` | ✅ |

---

## 4. What is NOT done — stated deliberately

- **No customer.** No design partner, no pilot, no revenue. The build is a
  well-executed bet, and `chatgpt.md` §6.2 estimates ~45 % of it is scaffolding
  built ahead of demand.
- **A full live-model agent benchmark against Claude or GPT specifically.**
  `agent-bench` proves the *harness* (scripted oracle/reckless/fabricator
  clients, 99 cases) and now also a full live run: `--client gemini` against
  `gemini-3.5-flash-lite` completed 46/99 real investigations (100%
  evidence-grounded, 0 material unsafe resolutions), with the other 53
  escalated — not crashed — on the free-tier key's rate limit. That run
  surfaced and fixed two real gaps: the benchmark harness didn't catch a
  provider failure per-case the way the real run pipeline (`orchestrate.py`)
  already did, and the OpenAI-compatible client dropped Gemini's required
  `thought_signature` across multi-turn tool calls. A full Claude/GPT run
  still needs a funded key in CI; one live gpt-4o investigation is separately
  captured (the verifier caught a bad proposal).
- **The demo shows one real investigation.** The frozen snapshot has a single
  gpt-4o run (the verifier rejection — the strongest AI-judgment beat). The
  "4–6 varied exceptions" story is told by the *benchmark* (99 cases), not by
  padding the demo with scripted investigations.
- **Live processor ingestion** — batch-file only; no Razorpay webhook path (a
  stated v1 non-goal).
- **Counterfactual coverage** — the deterministic check positively confirms the
  common hypothesis categories (rounding, fee/tax drift, duplicate, timing
  straddle, over/short settlement); an unmodelled category gets `PROPOSE`, never
  `SAFE`.
- **Auth** — static bearer-token principal table; no rotation, no SSO.
- **pgvector / Helm / queue** — present but arguably premature; kept because
  removing working infra is a product call, not an engineering one.
- **Production scale** — the queue/worker/HPA architecture exists; a load test
  at the stated target (500 orgs, 10k runs/day) does not.

---

## 5. If this continued past the Buildathon

1. Put it in front of one finance-ops team and watch a real close.
2. Put `ANTHROPIC_API_KEY` in CI and run `agent-bench --client anthropic` over
   the whole corpus — the harness is proven; a real model's trajectory on it is
   not.
3. Widen the deterministic counterfactual's *positive-confirmation* coverage as
   real exception categories show up.
4. Replace the principal table with real auth before anyone's data lands.

---

## 6. Reproduce every number in this report

```bash
make demo                                               # matching scorecard
arbiter bench --spec specs/razorpay-settlement.yaml --dataset datasets/seed
arbiter attack --spec … --dataset datasets/seed         # 12 contained · 0 unsafe
arbiter agent-bench --client oracle --seeds 16          # 100% / 0 unsafe / +44%
arbiter agent-bench --client reckless --seeds 16        # 0 material unsafe
pytest packages/engine/tests/test_control_invariants.py # 14 named proofs
arbiter replay <run-id>                                 # byte-identical hash
```

Full claim → proof → command table: [`docs/CLAIMS.md`](docs/CLAIMS.md).
Everything is measured, nothing is asserted.
