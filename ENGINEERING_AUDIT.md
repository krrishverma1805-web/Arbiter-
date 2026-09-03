# ENGINEERING AUDIT — Arbiter vs. the Master Implementation Spec

_Written 2026-09-03 after a full read of `ARBITER_MASTER_IMPLEMENTATION_SPEC.md` and a
pass over the entire repository. The spec's §0 demands "do not be a yes-man" — so this
document starts with the uncomfortable finding, not a plan._

---

## 0. The headline finding

**~85% of the 93-section spec is already implemented in this repository**, and most of it
is implemented well. A literal top-to-bottom execution of the spec would rebuild working,
tested, CI-green code — which the spec's own §83 ("do not overengineer"), §84 ("respect
existing technology choices unless there is a strong reason to change them"), and §85
("do not remove useful functionality without a justified replacement") explicitly forbid.

So this audit does what §3 actually asks: **map the spec against the code, find the genuine
gaps, and plan only those.**

Second finding, equally uncomfortable and stated because §0 demands it: **this mandate
("harden the submission") is in direct tension with the strategic conclusion the project
reached two days ago** (recorded in `chatgpt.md` §6.2 and §0.5): the build is already
~50% "premature scaffolding built before a single customer touched it," and the
highest-value next move was judged to be a customer conversation, not more engineering.
The spec adds a *new* layer (safety-kernel consolidation, counterfactual verification,
root-cause clustering, an attack harness, six more docs). Some of it genuinely strengthens
the **Buildathon submission specifically** (the judging criteria are Problem Taste, Build
Quality, AI Judgment, Failure Recovery — and a named Safety Kernel + an Attack-Arbiter
demo move directly serve the last two). The rest is polish on a system with no users.
The recommendation in §7 reflects that split.

---

## 1. Current architecture (as built)

```
CLIENTS   arbiter CLI (Typer) · cockpit (Next.js 15 / React 19) · CI · MCP stdio
                                   │ REST/JSON + SSE + WS
API       FastAPI + Pydantic v2 — auth (API key → Principal), RBAC, rate limit,
          idempotency, access-audit log, structlog, /metrics, DB-backed job queue
                                   │
ENGINE    arbiter_engine (pure Python)
          ingest/  → normalize to canonical Record; dedupe; file-hash guard; PII scrub
          specs/   → YAML recon spec (sources, identity, passes, taxonomy, rules); safe-AST rule compiler
          match/   → 8 passes (exact→tolerant→subset-sum→fuzzy→blocked→N:1→1:N→cross-period)
                     Fellegi–Sunter scoring, per-spec calibration + retrain behind ROC-AUC gate
          decompose/ → net = gross − MDR − GST − refunds − chargebacks ± rounding, per settlement UTR
          exceptions/ → 13-type taxonomy, safe-AST rule classifier + built-in heuristics, ₹-impact rank
          agent/   → hybrid-orchestration loop: PLAN→INVESTIGATE(read-only tools)→HYPOTHESIS→DECIDE
                     grounding.py (fabricated-citation reject, category↔evidence check)
                     investigator._verify (2nd-model verifier), _self_consistent (N-sample vote)
                     client.py (AnthropicClient / OpenAIClient / RecordedClient / ScriptedClient)
          learn/   → resolution → safe rule draft → review merge; FS retrain; threshold tune;
                     drift (PSI); global patterns; vector memory (pgvector / cosine)
          events/  → append-only, hash-chained store; fold → projections; verify; replay
          bench/   → matching + agent scorecards; --ablate; --calibration; regression gate
          cash.py  → deterministic 4-bucket partition; memo/ → Close Memo + audit-pack
                                   │
STORE     SQLModel — SQLite (demo) | Postgres (Alembic + RLS + pgbouncer + pgvector)
          events (hash-chained) · projections (rebuilt by folding) · specs · runs · jobs · api_keys · access_log

datagen/  adversarial synthetic generator → sources/*.csv + ground_truth.json (11-anomaly labelled catalog)
```

**Data flow:** files → `ingest_source` → canonical `Record`s (append `RECORD_INGESTED`) →
`match/engine` (append `MATCH_*`) → `decompose` (append `DECOMPOSITION_COMPUTED`) →
`exceptions/build_exceptions` (append `EXCEPTION_OPENED` / `EXCEPTION_CLASSIFIED`) →
`agent/run_investigations` for `AMBIGUOUS`/`UNEXPLAINED` (append `AGENT_*`) → `bench` scores →
`memo` renders. Every transition is an event; `fold_run` rebuilds all projections.

**Control flow:** `run.py::_pipeline` is a linear FSM guarded by `EventType.RUN_COMPLETED
not in seen` and per-stage `EXCEPTION_OPENED not in seen` so replay/resume never re-runs a
completed stage.

**Agent flow:** `investigate(exc, tools, client, spec)` — turn budget 6, token budget 12k,
per-run cost ceiling. Terminal turn forces a strict `Proposal | Escalate` JSON. Every
request/response is an `AGENT_INTERACTION` event → `replay` replays them.

**Persistence:** event-sourced. `Event.hash = sha256(prev_hash + canonical(payload))`.
`arbiter verify` recomputes the chain; `arbiter replay` re-folds + replays agent turns and
asserts byte-identical terminal hash.

**Security boundaries:** API-key auth + RBAC on mutating routes; Postgres RLS per `org_id`;
untrusted record fields (`description`, `notes`, narration) `<untrusted-data>`-fenced in the
prompt; `r_security_scan` quarantines instruction-shaped payloads to `SECURITY_REVIEW`
(which `never_invoke_for` keeps away from the agent entirely).

**AI boundary:** the LLM is invoked in exactly one place (`run_investigations`) and produces
only a strict-schema `Proposal`/`Escalate`. No agent tool mutates a match, record, ledger,
or rupee (asserted by test). `--no-ai` skips the step; the scorecard still computes.

**Testing:** ~190 test functions. pytest + hypothesis. Property tests on the matcher and
datagen identity. A determinism test (`run twice → identical hash chain`) as an isolated CI
job. 11 CI jobs.

**Benchmark:** `arbiter bench` → `scorecard.json` (matching + agent metrics), `--ablate`
(--no-ai vs model tiers), `--calibration` (ECE + isotonic), `--gate` (regression).
`--difficulty adversarial` datagen distribution + a CI stress gate.

**Demo flow:** `make demo` → generate → run → bench. Cockpit: 3 surfaces + `/live` streaming
investigation view. Hosted at `arbiter-cockpit.vercel.app` (frozen real-run snapshot).

---

## 2. Strengths (preserve — do not touch)

| Spec section | Already done, well |
|---|---|
| §4 deterministic core / AI boundary | ADR-0001; the LLM touches one step, produces only proposals |
| §5 AI output as structured object | `agent/schemas.py` — strict `Proposal`/`Escalate` Pydantic, `category` = spec-taxonomy enum |
| §6 confidence not from LLM | `grounding.py::grounded_confidence` re-derived from citation resolution; model self-score discarded |
| §9 forbidden agent capabilities | tools are read-only / proposal-only; a test asserts no tool name can mutate |
| §11 tool-call governance | every turn is an `AGENT_INTERACTION` event with model + prompt hash; no raw CoT exposed |
| §16 event sourcing | `events/store.py` — append-only, `prev_hash`/`hash` chain, schema-versioned payloads |
| §17 deterministic replay | `arbiter replay` + CI test asserting byte-identical terminal hash after pg_dump→restore |
| §18 exact money | integer paise everywhere; `Decimal` only at IO edges; property tests on rounding |
| §19 matching engine | 8 passes; explicit `MATCHED` / `MATCHED_WITH_VARIANCE` (residual) / `AMBIGUOUS` / `UNMATCHED` states; competing candidates surfaced |
| §20 settlement decomposition | `decompose/` — deterministic arithmetic; the LLM never owns it |
| §25 rule-learning loop | `learn/` — resolution → drafted safe-AST rule → human review merge → activation; versioned; the LLM proposes, never activates |
| §27 prompt-injection defense | fencing + `r_security_scan` + `never_invoke_for` + proposal-only backstop; tested in `test_agent.py` |
| §33 AI ablation | `arbiter bench --ablate` — --no-ai vs haiku vs sonnet vs opus |
| §34/§35 bounded agent + stop conditions | turn/token/cost budgets; `provider_unavailable`/`budget`/`inconsistent`/`verifier_rejected` terminal states |
| §43/§44 no-ai / offline | `--no-ai`; `ScriptedClient`/`RecordedClient` for CI; tests never call a live LLM |
| §45 cost controls | per-run cost ceiling; budget exceeded → escalate |
| §50/§51 rules as data + safe DSL | ADR-0003 — whitelisted AST, no `eval`/import/dunder; typed context |
| §52–54 testing pyramid + invariants + property tests | present; determinism, resume, calibration, isolation all covered |
| §56 model/prompt versioning | frozen prompt hash on every interaction; FS model / calibration versioned as events |
| §58 fabricated-citation defense | `grounding.py` — unresolved `record_id` voids the proposal → escalate |
| §73 audit view / §42 live replay | cockpit evidence drawer + `/live` SSE replay |
| §47 multi-tenancy | `org_id` on the event store, RLS, cross-tenant isolation test |

**Verdict:** the deterministic core, the event/audit model, the AI boundary, replay,
prompt-injection defense, and the benchmark are genuinely strong and match or exceed the
spec. Nothing in §1 of the spec's audit-risk list (nondeterminism, float money, mutable
truth, unbounded loops) is present.

---

## 3. Weaknesses / genuine gaps

Ordered by real value, not by spec order.

### G1 — Gating logic is distributed, not a named, separately-testable Safety Kernel (§8)
The spec wants one module every proposed action passes through:
`intent → schema → authz → evidence → deterministic calc → policy → risk → action gating →
human approval → execute/escalate → audit`. Today that logic is spread across
`grounding.py` (citation + category), `orchestrate.py` (`theta_escalate`,
`verify_above_minor`, `self_consistency_above_minor`), the rule engine
(`never_invoke_for`), and `investigator.py` (budgets). It works, but there is no single
`safety/kernel.py` with `evaluate(proposal, evidence, policy) -> Decision` and its own test
suite. **Consolidating it is a real Build-Quality + AI-Judgment win and low risk** (it's a
refactor of existing checks into one seam, not new behavior). **~200 LOC + tests.**

### G2 — No explicit R0–R5 risk tiers (§7)
Risk is implicit today: ₹ thresholds + category (`UNEXPLAINED` gets high effort,
`SECURITY_REVIEW` bypasses the agent). The spec wants an explicit, versioned
`RiskTier` (R0 informational … R5 control/security breach) computed deterministically from
`(category, ₹ impact, evidence coverage, candidate uniqueness, lineage)`, feeding G1.
**~120 LOC + tests + a `risk:` block in the spec's `adjudication:`.**

### G3 — Verification is a 2nd-model check, not a deterministic counterfactual (§13)
`investigator._verify` asks an independent model "do the cited records support this claim?"
— useful (it caught a bad gpt-4o proposal live), but it's still an LLM checking an LLM,
which §13 explicitly says not to rely on alone. There is no module that says: *if the
hypothesis "this ₹X gap is an unrecorded refund" were true, the decomposition would show
`refunds += X` and the residual would be 0 — does it?* The decomposition engine has the
pieces; a `counterfactual/` module that runs the hypothesis-specific arithmetic check for
refund / fee-drift / timing / duplicate hypotheses is genuinely new financial content.
**~200 LOC + tests.** High value for AI Judgment.

### G4 — Exception status is a string, not a validated state machine (§21)
`ExceptionStatus` is a `Literal[...]`. There is no `transition(exc, to) ` that rejects
`rejected → resolved` without a new verified path. In practice the pipeline only ever
advances one way, so no bad transition has occurred — but the spec wants it enforced, and
it's cheap. **~60 LOC + tests.**

### G5 — No root-cause clustering (§24)
`docs/15` describes exception root causes; nothing clusters a run's open exceptions into
"5 root causes, ₹X each" with deterministic aggregation. This is a strong finance-UX moment
(a controller sees 5 buckets, not 87 rows). Cluster key = `(category, rule_id, residual
sign, magnitude band)`; ₹ sum is deterministic; the LLM may only label a cluster.
**~120 LOC + a CLI command + an API endpoint + a small cockpit panel + tests.**

### G6 — No "Attack Arbiter" harness or mode (§29, §70, §88)
The demo has *one* injected note in the seed data. The spec wants a catalog of ~15
deterministic attacks (duplicate row, altered amount, wrong currency, fabricated
settlement id, out-of-order events, timestamp manipulation, prompt injection, fabricated
evidence, ambiguous candidates, schema corruption, high-value anomaly, …), a runner
(`arbiter attack <spec> --scenario X`) that reports `{detected? impact? what Arbiter did?
why?}`, and a cockpit button. **This is the single strongest demo move for the Failure-
Recovery criterion.** ~250 LOC (mostly the attack catalog in datagen) + a CLI + a UI button
+ tests.

### G7 — Headline safety metrics are partial (§32)
The scorecard has `false_match_rate` and `replay_hash_match`. It does not report
`unsafe_resolution_rate` (auto-resolved items ground truth says needed a human),
`rupees_protected` (₹ that would have been unsafely auto-resolved but were escalated), or
`replay_divergence_rate` as first-class outputs. **~80 LOC in `bench/scorecard.py` + gate
entries.**

### G8 — Consolidated root-level docs missing (§75, §90)
The spec wants `ARCHITECTURE.md`, `SECURITY.md`, `THREAT_MODEL.md`, `AI_SAFETY.md`,
`BENCHMARK.md`, `FAILURE_RECOVERY.md`, `REPLAY.md` at the repo root. The *content* exists,
scattered across `docs/04, 12, 13, 14, 07, 23, KNOWN-FAILURE-MODES, RUNBOOK` and the ADRs.
These should be **thin, honest root-level entry points that point into `docs/`** — not
500-line re-derivations. ~1–2h.

### G9 — No temporal finance state model as an explicit object (§14)
Timing is handled functionally (`r_timing_period_boundary`, cross-period carry-forward,
`match_carry_forward`) but there's no `PAYMENT_CAPTURED → SETTLEMENT_SCHEDULED →
BANK_CREDITED` state enum with `PENDING_SETTLEMENT` / `PENDING_BANK_CREDIT` /
`TIMING_DIFFERENCE` as named states. **Lower priority** — the behavior is correct; this is
mostly a modelling/clarity change. ~100 LOC.

### Not gaps (spec asks for it; it exists)
§15 Razorpay event architecture (the recon spec + `ingest_source` + idempotency + event
store already are this abstraction; live webhooks are a stated v1 non-goal) · §26 merchant
memory (`learn/` + vector memory) · §36–39 human-in-the-loop / "why not resolved" /
"explain this number" / Close Memo (the escalation payload carries knows/missing/question;
the drawer shows the identity equation; `arbiter memo` exists) · §40–41 control room /
agent activity (cockpit + `/live`) · §46 security review (`docs/14` threat model + gitleaks
+ pip-audit + Trivy) · §48–49 data quality / schema versioning (`ingest` quarantine +
validation report; `schema_version` on events) · §55 observability (structlog + OTel +
`/metrics`) · §61–63 investigation efficiency / context management / no-vector-DB-without-
need (deterministic filtering before the agent; compact evidence bundle; §63 arguably
*violated* by pgvector — see §5 of this doc) · §78 CI.

---

## 4. Critical risks in the *current* system

Honest list — none are P0-blockers, but they're real:

1. **The agent has never produced a benchmarked accuracy number on any model.** One live
   gpt-4o run exists (it escalated). `bench`'s agent metrics need a labelled trajectory set
   + an API key not in CI. Everything about "the AI adds measured value" (§33) is currently
   a --no-ai baseline plus a promise.
2. **Every accuracy number is on synthetic data the builder wrote.** Stated everywhere,
   still true.
3. **`_verify`'s failure mode is fail-open** — "verifier response unparseable → not
   blocking." For a fail-closed system (§92) this should arguably escalate, not pass.
4. **Subset-sum matcher is bounded at ~40 candidates**; heuristic above, not an ILP solver.
5. **Not load-tested** at the platform's stated scale.
6. **pgvector + Helm + job queue were built before a user** — §83 would say remove them.
   Not a correctness risk; a focus/allocation risk (see `chatgpt.md` §6.2).

---

## 5. Recommended architecture change

**One new layer, cleanly seamed — the Safety Kernel — and everything else stays.**

```
                 AGENT LOOP (unchanged)
                       │  emits a Proposal | Escalate
                       ▼
        ┌──────────────────────────────────────┐
        │           SAFETY KERNEL (new)         │   packages/engine/arbiter_engine/safety/
        │  1. schema        (schemas.py)        │
        │  2. grounding     (grounding.py)  ◄── existing checks, called from here
        │  3. counterfactual (counterfactual/) ◄── G3, new
        │  4. risk tier     (risk.py)      ◄── G2, new
        │  5. policy        (policy.py)    ◄── thresholds, versioned, from spec
        │  → Decision{ action: SAFE|PROPOSE|ESCALATE|QUARANTINE,     │
        │              risk: R0..R5, reasons: [code], evidence_ref } │
        └──────────────────────────────────────┘
                       │  Decision is an event: AGENT_DECISION_GATED
                       ▼
             orchestrate.py applies the Decision (unchanged downstream)
```

The kernel is **pure, deterministic, and separately testable** (`test_safety_kernel.py`) —
no LLM, no DB. `orchestrate.py` shrinks: instead of scattered `if grounded < theta …` it
calls `kernel.evaluate(proposal, snapshot, policy)` once and acts on the `Decision`.

No change to: the event store, the matcher, decomposition, the CLI surface, the API surface,
the cockpit data contract, replay.

---

## 6. Migration plan (incremental, each step green)

1. Extract the current gating constants (`theta_escalate`, `verify_above_minor`, …) into a
   `Policy` dataclass loaded from the spec's `adjudication:` block, versioned. No behavior
   change; add a test pinning the current defaults.
2. Add `safety/risk.py` — `assess_risk(exc, proposal, snapshot) -> RiskTier`. Pure. Tested
   against hand-labelled cases.
3. Add `safety/counterfactual.py` — per-hypothesis arithmetic checks. Pure. Tested.
4. Add `safety/kernel.py` — `evaluate(...) -> Decision` that calls schema → grounding →
   counterfactual → risk → policy in order. Emits `AGENT_DECISION_GATED`.
5. Rewire `orchestrate.py` to call the kernel; delete the now-duplicated inline checks.
   The full agent test suite must stay green (behavior is preserved; the escalation reasons
   get richer).
6. `bench/scorecard.py` — add `unsafe_resolution_rate`, `rupees_protected`,
   `replay_divergence_rate`; add gate entries.
7. Add the state machine (`exceptions/state.py`), clustering (`exceptions/cluster.py` +
   CLI + endpoint + panel), the attack harness (`datagen/attacks.py` + `arbiter attack` +
   UI button).
8. Consolidated root docs.
9. `FINAL_REPORT.md` (§91) — the graded self-assessment.

Run `make test` + `uv run ruff check` + `mypy` + `cd web && npx next build` after every
step. Do not advance past a red state.

---

## 7. Prioritized implementation plan

**Tier A — real Buildathon leverage:**
| # | Item | Why | Status |
|---|---|---|---|
| A1 | G1 + G2 + G3 — Safety Kernel + explicit R0–R5 tiers + deterministic counterfactual | the spec's centrepiece; serves "AI Judgment" + "Build Quality"; a refactor | ✅ **DONE** — `safety/` package (`kernel.py` / `risk.py` / `counterfactual.py` / `policy.py`), 17 tests, wired through `investigator._finalize_proposal`, `Decision` on every proposal/escalation event, `_verify` fail-open closed, `risk:` block in the spec |
| A2 | G6 — Attack Arbiter harness + CLI + UI button | strongest "Failure Recovery" demo move; "watch Arbiter refuse to be fooled" | ✅ **DONE** — `attack.py` (12 deterministic dataset-mutation scenarios), `arbiter attack` CLI (`--scenario`/`--json`, exits 1 on any UNSAFE), `test_attacks.py` regression gate. Hardened 3 real gaps found by the harness: injection scanner scope (`injection.py`), foreign-currency quarantine (`normalize.py`), bank-credit linkage (`classify.py`), implausible-date quarantine (`normalize.py`). Result: **12 contained · 0 partial · 0 missed · 0 UNSAFE**, ₹0 unaccounted. UI button: pending A2-wiring |
| A4 | G7 — headline safety metrics in the scorecard + gate | makes the safety story a *number*, not a claim | next |

**Tier B — worth it if time allows:**
| B1 | G5 — root-cause clustering + panel | strong finance UX; "5 causes not 87 rows" | ~0.5 day |
| B2 | G4 — exception state machine | cheap correctness hardening | ~2h |
| B3 | G8 — consolidated root docs (thin pointers) | spec deliverable; low effort | ~2h |
| B4 | `FINAL_REPORT.md` (§91) | honest graded self-assessment; a deliverable | ~1h |

**Tier C — defer / decline:**
- G9 temporal state model — behavior is already correct; modelling change only.
- Live Razorpay webhook integration (§15) — stated v1 non-goal; needs real API access.
- Removing pgvector / Helm / the queue (§83) — a *product* decision, not an engineering
  one; belongs in the `chatgpt.md` strategy consult, not this pass.

**The `_verify` fail-open bug (§4.3 above)** — fix in A1 (change to escalate on
unparseable verifier response; it's one line and it's the right fail-closed default).

---

## 8. What this audit will NOT do

Per §84/§85 and plain judgement:

- No rewrite of the matcher, the event store, the decomposition engine, the CLI, or the
  cockpit data contract. They are correct and tested.
- No new database, queue, framework, or service.
- No removal of working functionality without a tested replacement.
- No fake metrics, buttons, or benchmarks (§79) — every number stays measured, every
  button stays wired.

---

## 9. Acceptance (from §89) — current status

| Group | Status |
|---|---|
| Architecture (deterministic core, AI isolated, event/audit, replay) | ✅ · **Safety Kernel: A1** |
| Finance (exact money, decomposition, matching, exception ledger, materiality) | ✅ · **explicit risk model: A1** |
| AI (structured output, bounded loop, typed tools, grounding, injection defense, counterfactual) | ✅ except **counterfactual: A3** |
| Safety (fail-closed, no unauthorized action, ambiguous/high-risk escalate, immutable audit, human approval) | ✅ · **tighten `_verify` fail-open: A1** |
| Reliability (dup-event, out-of-order, retries, timeout, recovery, replay) | ✅ |
| Evaluation (benchmark, adversarial, ablation, financial + safety + perf metrics) | ✅ · **attack suite: A2 DONE** · except **safety metrics: A4** |
| Product (control room, evidence, exception workflow, agent activity, attack mode, replay, benchmark dash, close memo, arch viz) | ✅ · **attack CLI: A2 DONE** · except **attack-mode UI panel: A2-wiring**, **root-cause clusters: B1** |
| Documentation | ✅ in `docs/` · **root-level consolidation: B3**, **final report: B4** |

**Overall: the system already meets most of §89. Tier A closes the gaps that matter for
the submission. Tier B is polish. Tier C is out of scope or a product decision.**
