<h1 align="center">Arbiter</h1>

<p align="center"><strong>A verification layer for money movement.</strong></p>

<p align="center">
Arbiter closes one finance-ops loop end to end — reconciling a payment processor's settlements
against the bank and the ledger across a batch — reports an <em>honest</em> match rate, and hands
back a categorized, evidence-backed list of the exceptions it could not resolve, each with a
proposed fix.
</p>

<p align="center"><em>Submission — Razorpay AI Buildathon 2026 · Track: AI Finance Controller</em></p>

---

## The one sentence

> Arbiter turns _"here are three files, tell me if the money is right"_ into
> _"97.2% tied automatically, ₹41,900 across 6 exceptions still need you — here's each one,
> the evidence, and what I think it is."_

## Why this exists

The 2026 engineering consensus: **verification capacity, not generation speed, is the bottleneck.**
Reconciliation, settlement and forecasting are still done by hand — not because the data entry is
hard, but because someone has to _trust_ the result, and trust doesn't parallelize.

Arbiter is built as a direct expression of that idea. It's a **hybrid-orchestration agent**: a
deterministic state-machine skeleton does the matching and the money math (reproducibly, no LLM in
the path), and an **agentic investigation loop** — plan → gather evidence → test a hypothesis →
conclude or escalate — handles the one sub-problem that is genuinely a judgment call: the ambiguous
exceptions a human would otherwise dig into by hand. The agent only ever *investigates and proposes*;
a human confirms. Turn it off entirely with `--no-ai` and the deterministic core still stands.

Full reasoning: [`docs/01`](docs/01-market-and-thesis.md) · the agent: [`docs/12`](docs/12-agent-design.md) · why it's built this way: [`docs/11`](docs/11-plan-evaluation-and-gaps.md), [`ADR-0004`](docs/adr/0004-hybrid-orchestration.md).

## What it does

| | |
|---|---|
| **Ingests** | Razorpay settlement report + bank statement + order ledger → one immutable, normalized event log |
| **Matches** | 8 deterministic passes: exact → tolerant → subset-sum (1 credit ↔ N orders) → fuzzy candidates → blocked → aggregate N:1 → aggregate 1:N → cross-period carry-forward |
| **Decomposes** | Verifies `net = gross − MDR − GST-on-MDR − refunds − chargebacks ± rounding` line by line |
| **Classifies** | Every non-match → a typed exception (`TIMING`, `DUPLICATE`, `FEE_DRIFT`, …), ranked by ₹ at stake, then grouped into root causes (`arbiter clusters`) |
| **Investigates** | The ambiguous residue → a bounded agent loop calls read-only tools, tests a hypothesis, and either proposes a category + explanation + fix + rule, or escalates with one sharpened question. **Arbiter never auto-resolves — a human confirms every proposal.** |
| **Gates** | A deterministic **Safety Kernel** rules every proposal: SAFE / present-for-review / escalate / quarantine — from the risk tier (R0–R5), grounding, a counterfactual *arithmetic confirmation*, a 2nd-model verifier, and a never-safe list for money-movement categories. All fail-closed. `unsafe_resolution_rate` is CI-gated at tolerance 0 |
| **Benchmarks the agent** | `arbiter agent-bench` → 99 labelled trajectory cases, the real investigation loop. Usefulness and safety scored **separately**. A competent agent: 100% task, 100% escalation recall, 0 unsafe, +44% lift. A confidently-wrong agent: **0 material unsafe** |
| **Stress-tests** | `arbiter attack` → 12 deterministic tamperings (altered amount, wrong currency, fabricated UTR, prompt injection, phantom credit, …); asserts a tampered file never produces a confident clean tie. Current: 12 contained · 0 unsafe · ₹0 unaccounted |
| **Learns** | You accept a resolution → Arbiter drafts a durable rule → next cycle's auto-match rate rises |
| **Reports** | `arbiter bench` → matching metrics (auto-match, precision, recall, **false-match rate**, ₹ coverage) **and** headline safety metrics (`unsafe_resolution_rate`, `rupees_protected`, `replay_divergence`) — reproducibly, in CI |
| **Places the cash** | `arbiter cash-position` → every settled rupee partitioned: confirmed in bank · in transit · held (disputes / wrong account) · unexplained. Pure arithmetic off the reconciled ledger — it always sums back to the processor-side net |
| **Attests** | `arbiter memo` → an auditor-ready Close Memo (totals tied, coverage, every exception + its resolution, the audit-trail hash); `arbiter audit-pack` → the memo + the full hash-chained event log + a re-check manifest, as one zip |

## Status

**Milestones M0–M5 are built** (see [`docs/10`](docs/10-implementation-plan.md)):

- **M0** — uv workspace, hash-chained event store with `verify`, deterministic CSV ingestion,
  synthetic data generator with ground truth, the `arbiter` CLI.
- **M1–M2** — the 4-pass deterministic matcher (exact → tolerant → subset-sum → fuzzy),
  Fellegi–Sunter scoring with calibrated `P(match)`, the settlement decomposition, the
  safe-AST rule engine, typed exception classification, and `arbiter bench` scoring matching
  **and** agent metrics against ground truth (gated in CI: false-match ≤ 1.5%, auto-match ≥ 80%
  at 800 records).
- **M3** — the hybrid-orchestration investigation agent ([ADR-0004](docs/adr/0004-hybrid-orchestration.md)):
  a deterministic skeleton FSM + one bounded agentic loop (plan → investigate with read-only
  tools → hypothesize → conclude or escalate), frozen+hashed prompt, untrusted-record fencing,
  strict `Proposal`/`Escalate` output. Runs offline deterministically when no API key is set.
- **M4** — the FastAPI backend and the Next.js cockpit (scorecard · keyboard-first exception
  queue · evidence drawer), verified end to end.
- **M5** — the learning loop (resolution → drafted safe rule → reviewed spec merge → the rule
  classifies the next run, no model in the loop), the 3-close **cycle demo** (`make cycle`),
  the deterministic **cash-position** readout, the auditor-ready **Close Memo**, and the
  `audit-pack` export.
- **Beyond M5** — the full [`docs/28`](docs/28-production-hardening.md) production-hardening
  roadmap (multi-tenant platform, Postgres RLS, async job queue, Helm, OTel/Sentry/Grafana,
  MCP server, continuous learning), then a 93-section hardening spec audited
  ([`ENGINEERING_AUDIT.md`](ENGINEERING_AUDIT.md)) and its gaps closed: the **Safety Kernel**
  ([`AI_SAFETY.md`](AI_SAFETY.md)), the **Attack Arbiter** harness
  ([`FAILURE_RECOVERY.md`](FAILURE_RECOVERY.md)), headline safety metrics
  ([`BENCHMARK.md`](BENCHMARK.md)), root-cause clustering, a validated exception state
  machine, and the graded [`FINAL_REPORT.md`](FINAL_REPORT.md).

229 tests, strict `mypy`/`ruff`, CI with an isolated determinism gate, the bench scorecard
gate (matching **and** safety metrics), a `gitleaks` + `pip-audit` security job, a Postgres
restore-drill job, and a web typecheck/lint/build job.

## Quickstart

```bash
git clone https://github.com/krrishverma1805-web/Arbiter- && cd Arbiter-
make demo          # generate a batch, reconcile it, score it against ground truth
make up            # the API + the cockpit on localhost
```

```bash
uv sync --all-packages
uv run arbiter gen --scenario d2c --records 800 --seed 42 --out datasets/seed
uv run arbiter run   --spec specs/razorpay-settlement.yaml --dataset datasets/seed [--no-ai]
uv run arbiter bench --spec specs/razorpay-settlement.yaml --dataset datasets/seed --json
uv run arbiter explain <run-id>            # the evidence for each exception, as text
uv run arbiter resolve <run-id> <exc-id> --action <a> [--category <C>]   # → drafts a learned rule
uv run arbiter rules pending <run-id> --spec specs/razorpay-settlement.yaml
uv run arbiter rules merge   <run-id> --spec specs/razorpay-settlement.yaml   # bumps version:
uv run arbiter cycle-demo --out data/cycle   # 3 closes: resolve once, learn, carry forward
uv run arbiter cash-position <run-id>     # where the money is: confirmed / in-transit / held / unexplained
uv run arbiter memo       <run-id> --out close-memo.html     # Close Memo (print-styled → PDF)
uv run arbiter audit-pack <run-id> --out pack.zip            # event log + memo + verify manifest
uv run arbiter replay  <run-id>            # reproduce a completed run from its event log
uv run arbiter verify  <run-id>            # recompute the audit hash chain
uv run arbiter events  <run-id>            # dump the raw event log
```

The investigation agent needs `ANTHROPIC_API_KEY`; without it, runs still complete —
ambiguous exceptions escalate deterministically and the run stays reproducible.
It can also run against OpenAI instead — `pip install 'arbiter-engine[openai]'`, then
`ARBITER_LLM_PROVIDER=openai OPENAI_API_KEY=… ARBITER_OPENAI_MODEL=gpt-4o`. Same
`Turn` contract, so grounding, the verifier pass, replay and the scorecard are
unchanged; a non-Anthropic model that free-forms the output contract is coerced
back onto it and still vetted by the deterministic grounding layer.

## What's in here

| Path | |
|---|---|
| [`docs/`](docs/) | The full research, spec, architecture, design doctrine, competitive analysis, and honest red-team (28 docs + 5 ADRs), plus root-level summaries: [`ARCHITECTURE`](ARCHITECTURE.md) · [`AI_SAFETY`](AI_SAFETY.md) · [`SECURITY`](SECURITY.md) · [`THREAT_MODEL`](THREAT_MODEL.md) · [`BENCHMARK`](BENCHMARK.md) · [`FAILURE_RECOVERY`](FAILURE_RECOVERY.md) · [`REPLAY`](REPLAY.md) · [`FINAL_REPORT`](FINAL_REPORT.md) |
| `packages/engine/` | The reconciliation engine — money, hashing, event store, spec loader, ingestion, the 8-pass matcher, Fellegi–Sunter scoring, decomposition, the safe-AST rule engine, the investigation agent, the deterministic **Safety Kernel** (`safety/`), the **Attack Arbiter** harness (`attack.py`), root-cause clustering, the learning loop, `bench`, `memo`, the CLI |
| `packages/datagen/` | Synthetic batch generator — clean batches + ground truth + the labeled adversarial anomaly catalog |
| `packages/api/` | FastAPI backend — runs, scorecard, exceptions, resolve, learned-rule review |
| `web/` | Next.js cockpit — scorecard · keyboard-first exception queue · evidence drawer |
| `specs/` | `razorpay-settlement.yaml` (flagship) · `gst-2b.yaml` (proof the engine is loop-agnostic) |

## Documentation

**For a judge — the 3-minute path:**
[`docs/buildathon/DEMO.md`](docs/buildathon/DEMO.md) (the script) ·
[`docs/buildathon/SAFETY_RESULTS.md`](docs/buildathon/SAFETY_RESULTS.md) ·
[`docs/buildathon/AGENT_EVALUATION.md`](docs/buildathon/AGENT_EVALUATION.md) ·
[`docs/buildathon/ATTACK_RESULTS.md`](docs/buildathon/ATTACK_RESULTS.md) ·
[`docs/buildathon/LIMITATIONS.md`](docs/buildathon/LIMITATIONS.md) ·
[`docs/CLAIMS.md`](docs/CLAIMS.md) (claim → proof → command) ·
[`docs/CONTROL_INVARIANTS.md`](docs/CONTROL_INVARIANTS.md)

**Repo-root summaries, each points into `docs/`:**
[`ARCHITECTURE.md`](ARCHITECTURE.md) · [`AI_SAFETY.md`](AI_SAFETY.md) · [`SECURITY.md`](SECURITY.md) · [`THREAT_MODEL.md`](THREAT_MODEL.md) · [`BENCHMARK.md`](BENCHMARK.md) · [`FAILURE_RECOVERY.md`](FAILURE_RECOVERY.md) · [`REPLAY.md`](REPLAY.md) · [`FINAL_REPORT.md`](FINAL_REPORT.md) (graded self-assessment) · [`ENGINEERING_AUDIT.md`](ENGINEERING_AUDIT.md)

**Full research and spec — read in order:**

1. [`01-market-and-thesis.md`](docs/01-market-and-thesis.md) — why this, why now, which loop, sourced
2. [`02-product-spec.md`](docs/02-product-spec.md) — what it is, what's in the box and why, how it works end to end
3. [`03-competitive-landscape.md`](docs/03-competitive-landscape.md) — BlackLine, HighRadius, Numeric, Nominal, Ledge, PG-native, OSS — and the wedge
4. [`04-technical-architecture.md`](docs/04-technical-architecture.md) — the system, data model, algorithms, the AI boundary, tech choices
5. [`05-design-doctrine.md`](docs/05-design-doctrine.md) — the cockpit: principles, interface model, visual system, interaction rules
6. [`06-feature-inventory.md`](docs/06-feature-inventory.md) — every feature, its job, its priority
7. [`07-evaluation-and-benchmark.md`](docs/07-evaluation-and-benchmark.md) — how the matcher is measured, honestly
8. [`08-why-it-might-not-sell.md`](docs/08-why-it-might-not-sell.md) — the internal red-team, and how to make it sellable
9. [`09-open-strategic-questions.md`](docs/09-open-strategic-questions.md) — the decisions that are yours to make
10. [`10-implementation-plan.md`](docs/10-implementation-plan.md) — build order, judging-criteria map, schedule, definition of done
11. [`11-plan-evaluation-and-gaps.md`](docs/11-plan-evaluation-and-gaps.md) — adversarial review of the plan: the grade, the structural weakness, 14 gaps + fixes
12. [`12-agent-design.md`](docs/12-agent-design.md) — the agent: skeleton, investigation loop, replay, model ablation, the full agent scorecard + calibration
13. [`13-production-readiness.md`](docs/13-production-readiness.md) — deploy, secrets, migrations, tracing, resilience, SLOs, the runbook
14. [`14-security-and-trust.md`](docs/14-security-and-trust.md) — threat model (prompt injection via record fields, tampering, secret leakage) + the controls

**Deep dives (build-ready detail):** [`15` domain model & exception taxonomy](docs/15-domain-model-reconciliation.md) · [`16` matching engine (Fellegi–Sunter, subset-sum)](docs/16-matching-engine-deep-dive.md) · [`17` data model & full schema](docs/17-data-model-and-schema.md) · [`18` synthetic data generator](docs/18-synthetic-data-generator.md) · [`19` agent prompts & schemas](docs/19-agent-contracts.md) · [`20` API & frontend spec](docs/20-api-and-frontend-spec.md) · [`21` go-to-market & business model](docs/21-go-to-market-and-business-model.md) · [`22` cost model](docs/22-cost-model.md) · [`23` risk register](docs/23-risk-register.md) · [`24` demo & pitch script](docs/24-demo-and-pitch.md) · [`25` testing & CI](docs/25-testing-and-ci-strategy.md) · [`26` compliance (RBI PA-PG, DPDP)](docs/26-compliance-and-data-protection.md) · [`27` completeness audit](docs/27-completeness-audit.md)

- [`adr/`](docs/adr/) — architecture decision records (0001–0005)
- [`KNOWN-FAILURE-MODES.md`](docs/KNOWN-FAILURE-MODES.md) — where the agent is weak, and the containment
- [`RUNBOOK.md`](docs/RUNBOOK.md) — deploy, rollback, resume a stuck run, rotate the key, restore the event store

## Non-goals for this version (stated deliberately)

Arbiter v1 does **not**: post journal entries into an ERP · run live bank/ERP connectors ·
do multi-entity consolidation · detect fraud · produce a full cash forecast. Each is a
deliberate scope boundary with a reason — see [`docs/02 §6`](docs/02-product-spec.md) and
[`docs/06 §M`](docs/06-feature-inventory.md). (Auth, multi-tenancy and billing *are* built
now — [`SECURITY.md`](SECURITY.md) — but there is no hosted instance and no customer.)

## The numbers (800-record adversarial batch, seed 42, `--no-ai`)

| metric | value | | metric | value |
|---|---|---|---|---|
| auto-match rate | **93.8%** | | false-match rate | **0.0%** |
| precision | 100.0% | | ₹ coverage | 100.0% |
| recall | 93.8% | | ₹ unexplained | 0.7% |
| anomalies caught | 8 / 10 | | category accuracy | 75.0% |

**Safety** (`SafetyScore` block, CI-gated at tolerance 0) — unsafe auto-resolutions **0 / 2**
human-only items · ₹ protected **₹53,245 (100%)** · replay divergence **none** · fabricated
citations **0** · Attack Arbiter **12 / 12 contained, 0 unsafe, ₹0 unaccounted**
(`arbiter attack`).

**Agent** (`arbiter agent-bench` — 99 labelled trajectory cases, the real investigation
loop, usefulness and safety scored separately):

| client | task | category | escalation recall | unsafe | notes |
|---|---|---|---|---|---|
| oracle (competent) | **100%** | **100%** | **100%** | **0** | +44% lift vs. "escalate everything" |
| reckless (confidently wrong) | — | — | — | **0 material** | 48% escalated by the harness · 5 immaterial SAFE-gate slips (₹4.5k) · a human still confirms |
| fabricator (cites a ghost) | — | — | **100%** | **0** | every fabrication escalates |

> **Arbiter never auto-resolves.** `unsafe_resolution_rate` measures how often the
> kernel's `SAFE` gate *would* have been wrong — a trust check on the gate, not a
> description of an auto-apply that doesn't exist.

**Ablation** (`arbiter bench --ablate`) — the deterministic core is the whole
table below until an `ANTHROPIC_API_KEY` is set; the model tiers (haiku triage →
opus investigate) then slot in as extra rows and the **AI lift** on category
accuracy is reported against the `--no-ai` baseline. The nightly `live` CI job
runs that path; there is no key in the dev/CI environment.

| config | category acc. | task compl. | escalation recall | $/run |
|---|---|---|---|---|
| `--no-ai` | 75.0% | — | — | 0.00 |
| haiku / sonnet / opus | *nightly-live only* | | | |

**Calibration** (`arbiter bench --calibration`) — ECE **0.12**, isotonic-recalibrated
and disclosed. At demo scale the deterministic matcher's confidence is effectively
binary (1.0 for a clean tie), so every prediction lands in one reliability bin
(conf 1.00, acc 0.88) — a 12-point over-confidence, not a spread. Calibration
becomes meaningful for the Fellegi–Sunter fuzzy pass and the agent's `P(match)`,
which need live runs and more data ([`docs/12 §6`](docs/12-agent-design.md)).

## Honest limitations

- The benchmark runs on **synthetic data**, which is cleaner than production. Real-world match
  rates will be lower. The generator injects realistic messiness and the difficulty dial shows
  where accuracy degrades — but the asterisk is real and stays visible.
- Small batch sizes (50–500) mean wide confidence intervals on the rates. `bench --seeds N` aggregates.
- Every agent proposal is **grounded** before a human sees it — each cited `record_id` must
  resolve to a real record in the run, and a deterministic check confirms the category fits
  the evidence shape. A fabricated citation voids the proposal and escalates it. The
  confidence shown is re-derived from how the citations hold up, never the model's raw
  self-assessment ([docs/28 §1.3](docs/28-production-hardening.md)).
- The investigation agent's own scorecard (task-completion, hallucination, grounded rate,
  confidence ECE, escalation P/R) and
  the model ablation only have real numbers from the nightly `live` job — there is no API key
  in the dev/CI environment. Offline, the agent path is exercised with recorded/scripted turns.
- See [`docs/07 §6`](docs/07-evaluation-and-benchmark.md) for the full list.

## License

Apache-2.0 (engine, benchmark, CLI, specs). See [`LICENSE`](LICENSE).
