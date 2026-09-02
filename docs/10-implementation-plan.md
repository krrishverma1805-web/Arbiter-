# 10 — Implementation Plan

_How Arbiter gets built, in what order, mapped to how it's judged, with a realistic schedule and a definition of done._

---

## 1. Build philosophy

- **Vertical slices, deterministic-first.** Every milestone ends with `arbiter run` working end-to-end on real synthetic data and producing a scorecard. The scope of the slice grows; there is never a "big bang integration" week.
- **The benchmark is built in M1, not M5.** You cannot tune what you cannot measure. `arbiter bench` exists before the matcher is good.
- **The AI step is added late and behind a flag.** The deterministic core must be excellent and measured _first_. The AI is layered on and its lift is measured against that baseline.
- **Docs and code move together.** Every ADR-worthy decision gets an ADR. The `docs/` folder is part of the deliverable.

---

## 2. Mapping to the judging criteria

The four stated criteria (from [01](01-market-and-thesis.md) §7), and exactly how the build addresses each:

### Problem Taste — "a meaningful, real-world financial problem"
- Multi-rail settlement reconciliation is a universal, recurring, money-denominated finance-ops pain ([01](01-market-and-thesis.md) §2, §3).
- The framing — _the exception list is the product, not the leftover_ ([09](09-open-strategic-questions.md) Q10) — shows we understand where the actual pain is (the residual 10%, not the easy 90%).
- Choosing settlement decomposition (`net = gross − MDR − GST − refunds − chargebacks`) over a generic bank-to-book join shows domain depth.

### Build Quality — "clean repo, execution reliability, code trust"
- Monorepo with clear package boundaries ([04](04-technical-architecture.md) §9); `make demo` runs the whole thing in one command.
- `pytest` + `hypothesis` property tests; ≥ 85% engine coverage; determinism + resume tests that fail CI if a run diverges or a mid-run kill changes the result.
- Typed throughout (Pydantic v2 / TypeScript strict); Alembic migrations; OTEL traces; structured logs; `RUNBOOK.md` ([13](13-production-readiness.md)).
- Three real ingest parsers (Razorpay recon, bank CSV + MT940, Tally/Zoho) — the unglamorous integration work done visibly ([11 G5](11-plan-evaluation-and-gaps.md)).
- CI runs tests + both scorecards + `pip-audit`/`gitleaks` on every commit and publishes the artifacts.
- Every architectural decision has an ADR (0001–0004).

### AI Judgment — "use AI where appropriate, deterministic where AI is unnecessary"
- ADR-0001 + [ADR-0004](adr/0004-hybrid-orchestration.md): deterministic state-machine skeleton, one bounded **agentic investigation loop**, every agent output a gated proposal, `--no-ai` always works ([04 §3](04-technical-architecture.md), [12](12-agent-design.md)).
- The **model ablation** (`--no-ai` / haiku / sonnet / opus, with accuracy × cost × latency) picks the shipped tiered policy from data — "the right tool in the right place," shown not claimed.
- The **agent scorecard** (task-completion, tool-use accuracy, grounding, hallucination rate, escalation P/R) + the **calibration study** substantiate the judgment quantitatively.
- Money math, matching, scoring, and replay contain zero LLM calls, by design and by test. Injection can't move money because tools are proposal-only ([14 C3](14-security-and-trust.md)).

### Failure Recovery — "show what broke and how you resolved it"
- The exception ledger _is_ a failure-recovery system: every unresolved item categorized, quantified, explained, given a proposed fix + a preventing rule.
- The agent's own **optimal-stopping / escalation** behavior — it hands back a sharpened question when it can't resolve something — is failure recovery built into the agent, and it's measured (escalation recall).
- `docs/BUILD-LOG.md` (build failures) **and** `docs/KNOWN-FAILURE-MODES.md` (the agent's own failures, from real runs, with the containment) — both kept from day one.
- Resumable passes + deterministic replay + the regression gate = the engineering answer to "recover when a run crashes or accuracy regresses."
- The demo deliberately shows one exception the agent escalated rather than guessed, and narrates what it's missing.

---

## 3. Milestones

Assumes a solo builder, ~3 focused weeks. Adjust week lengths to your actual runway; the _order_ is the important part.

### M0 — Skeleton & data (days 1–3)
- Monorepo scaffold (uv workspace, pnpm, Makefile, docker-compose, CI stub).
- `datagen`: generate `razorpay_settlement.csv` + `bank.csv` + `ledger.csv` + `ground_truth.json` for a clean batch (no anomalies yet), seeded.
- Event store: append-only table, hash chain, fold, `arbiter replay` stub.
- Canonical `Record` model + CSV ingest with declared column mapping.
- `arbiter run` runs, ingests, emits `RECORD_INGESTED` events, prints record counts.
- **Exit:** `make demo` ingests a 200-record batch deterministically; `arbiter replay` reproduces it.

### M1 — Deterministic matcher + benchmark (days 4–8)
- Recon spec loader + validator + safe rule-expression AST.
- Matching pass 1 (exact) + pass 2 (tolerant) + confidence formula.
- Settlement decomposition + residual computation.
- Exception taxonomy + deterministic classifier (spec rules).
- `datagen`: add the 12 labeled anomaly types with a difficulty dial + a labeled trajectory set + one injected-note record.
- Three real ingest profiles: `razorpay_recon` (exact schema), `bank_csv` (HDFC/ICICI/Axis/generic) + `mt940`, `tally_daybook`/`zoho_books` ([doc 11 G5](11-plan-evaluation-and-gaps.md)).
- Injection scanner → `SECURITY_REVIEW` quarantine ([doc 14 C2](14-security-and-trust.md)); file-intake hardening ([doc 14 C4](14-security-and-trust.md)).
- `arbiter bench`: matching scorecard (metrics, $ coverage, throughput, exception histogram) vs `ground_truth.json`.
- Alembic migrations; structured logging; OTEL scaffolding.
- CI: run bench, upload `scorecard.json` + HTML, comment metrics on PR; `pip-audit`/`gitleaks`.
- **Exit:** honest matching scorecard on an 800-record adversarial batch; `--no-ai` is the only mode so far; determinism + resume tests green.

### M2 — Hard matching + exception ranking (days 9–12)
- Pass 3 (set/subset with bounded subset-sum) — the differentiating pass.
- Pass 4 (fuzzy candidate scoring) + candidate attachment to exceptions.
- $-impact ranking; exception grouping/dedup.
- Decomposition D5 (over/undercharge detection).
- Resumable passes; idempotent runs; `arbiter run --resume`; typed error handling.
- Tune the deterministic core; **commit the `--no-ai` baseline scorecard** (the number the agent is measured against).
- **Exit:** deterministic core hits its target auto-match rate on the adversarial batch; baseline committed; `arbiter verify` works.

### M3 — The investigation agent (days 13–17)
- Skeleton FSM (`INGESTING…REPORTING`) formalized with per-state events.
- Investigation loop: plan → investigate (8 read-only tools) → hypothesize & test → conclude/escalate (optimal stopping). Anthropic SDK tool runner, frozen+hashed prompt, `<untrusted-data>` fencing, strict `Proposal`/`Escalate` structured output, turn/token/cost budgets.
- `AGENT_INTERACTION` events → `arbiter replay` replays them; `--reinvestigate` forces fresh calls.
- **Agent scorecard** in `arbiter bench`: task-completion, tool-use accuracy, grounding, hallucination rate, escalation P/R, trajectory efficiency, cost/latency, **AI lift** vs the M2 baseline.
- `arbiter bench --ablate` (--no-ai / haiku / sonnet / opus) → pick the tiered default from the data.
- `arbiter bench --calibration` → reliability diagram + ECE (+ isotonic recalibration if ECE > 0.05).
- **Exit:** agent scorecard exists with real numbers; ablation table in the README; `run` (with agent) and `--no-ai` both green; cost < $1.50/demo run.

### M4 — Cockpit (days 15–20, overlaps M3)
- Next.js app, three surfaces: scorecard (matching + agent), exception queue (keyboard-first grid), evidence drawer.
- Evidence drawer is the polished piece: 3 record cards, the identity equation, rule trail, the agent's investigation trace + proposal with clickable evidence refs, decision controls.
- Live run progress via SSE (pass-by-pass, then agent investigations streaming plan → conclusion).
- FastAPI behind it; full loading/empty/error state coverage; optimistic resolution with rollback.
- Light/dark parity, WCAG AA (axe in CI), reduced-motion.
- **Exit:** a judge can watch a run and triage the demo batch entirely in the cockpit.

### M5 — Learning loop, assurance artifacts, polish, submission (days 20–23)
- Resolution → rule synthesis → spec-diff review → re-run shows the number move.
- Cycle demo: 3 monthly batches, rules carried forward, the rising-curve on screen.
- Starter rule packs.
- **Close Memo** (`arbiter memo`, HTML + PDF); audit-pack export; `arbiter explain`.
- (stretch — **done**) deterministic cash-position readout off the reconciled ledger (`arbiter cash-position`).
- `KNOWN-FAILURE-MODES.md` populated from real bench runs; `RUNBOOK.md`; `/healthz`+`/readyz`.
- README (with the ablation + calibration numbers), `BUILD-LOG.md` finalized, 5-min pitch video, doc pass.
- **Exit:** all criteria from [02 §7](02-product-spec.md) **and** [doc 11 §7](11-plan-evaluation-and-gaps.md) pass from a clean checkout.

---

## 4. What ships in each priority band (from [06](06-feature-inventory.md))

- **P0 (must):** A1–A5, A7, B1–B4, B6, C1–C8, D1–D3, E1–E6, F1–F1c, F2–F5, F7–F9, G1, G5, H1–H4, I1–I6, J1–J4, K1–K3, K6, L1–L4, **N1–N3, O1–O6, P1–P5, P7**.
- **P1 (if time):** A6, B5, D4–D5, F1d, F6, F10, G2–G4, H5, I7, J5–J6, K4–K5, K7, L5, **N4–N6, O7, P6, P8, Q1–Q2**.
- **P2 (post):** all of section M, **Q3**.

If time runs short, cut P1 before compromising any P0 — and never compromise: `arbiter bench` (both scorecards), the determinism + resume tests, the proposal-only tool guarantee (O3), the injection defense (O1–O2), and the evidence drawer.

---

## 5. Scope discipline (what we are NOT building, and saying so)

Stated in [02](02-product-spec.md) §6 and [06](06-feature-inventory.md) §M. The README will contain an explicit "Non-goals for this version" section. Reviewers read deliberate, defended scope boundaries as a maturity signal; they read silent gaps as oversights.

---

## 6. Risks to the plan itself

| Risk | Mitigation |
|---|---|
| Subset-sum pass eats a week | Timebox to 2 days; ship meet-in-the-middle ≤40 + greedy fallback; ILP is P2 |
| Cockpit scope creep | The three surfaces only; evidence drawer polished, rest competent; it's 40% of effort ([09](09-open-strategic-questions.md) Q9) |
| AI lift turns out small | That's a _finding_, not a failure — report it, ship the deterministic core as the headline, keep AI as opt-in |
| Synthetic data feels fake to judges | Difficulty dial + realistic scenario presets + disclose the asterisk + attempt one real dataset ([09](09-open-strategic-questions.md) Q5) |
| Time overrun | M1 (deterministic core + bench) alone is a legitimate submission. Everything after is upside. Protect M1. |

---

## 7. Definition of done (the submission checklist)

Combines [doc 02 §7](02-product-spec.md) and [doc 11 §7](11-plan-evaluation-and-gaps.md).

_Status as of 2026-09-02 (M0–M5 complete). `[x]` done · `[~]` done within a stated v1 boundary · `[ ]` open._

- [~] `git clone && make demo` → real scorecard on an 800-record batch in ~20s; the cockpit is a separate `make up` (API + web), not folded into `make demo`
- [x] `arbiter bench` → matching scorecard **and** agent scorecard, reproducibly (offline agent path is deterministic via recorded/scripted turns)
- [x] `arbiter bench --ablate` → the `--no-ai` row is in the README; the haiku/sonnet/opus rows + AI lift come from the nightly `live` job (no API key in dev/CI)
- [x] `arbiter bench --calibration` → ECE 0.12, isotonic-recalibrated + disclosed in the README (the deterministic matcher's confidence is effectively binary at this scale)
- [~] `arbiter run --no-ai` works; the deterministic baseline is committed; **AI lift** is disclosed as measurable only from the nightly `live` job
- [x] The agent runs a visible investigation loop (plan → evidence → hypothesis → conclude/escalate), not a one-shot call
- [x] `arbiter replay <id>` reproduces a completed run; `arbiter run --resume` survives a mid-run kill; `arbiter verify` confirms the hash chain
- [x] Prompt-injection defense implemented; the demo data's injected note is caught and routed to `SECURITY_REVIEW`, not the agent
- [~] `/healthz`+`/readyz` and `RUNBOOK.md` exist; OTEL `--trace` and Alembic migrations are documented v1 boundaries ([RUNBOOK](RUNBOOK.md) §v1 boundaries) — the event log is the trace/schema substrate
- [x] CI green: tests + coverage, isolated determinism + resume gate, bench scorecard gate + artifact, `gitleaks` + `pip-audit`, web typecheck/lint/build
- [x] Cycle demo (`arbiter cycle-demo` / `make cycle`): a learned rule carried across 3 closes, scored base-spec vs learned-spec so the gap is the rule alone
- [x] `arbiter memo <id>` → the auditor-ready Close Memo, print-styled so browser "Save as PDF" is the PDF copy, audit hash embedded; `arbiter audit-pack` zips memo + log + manifest
- [x] Evidence drawer: every number traceable to source; full frontend state coverage; live run progress
- [x] `docs/` complete (01–27 + ADRs 0001–0005); `BUILD-LOG.md` populated; `KNOWN-FAILURE-MODES.md` has real deterministic-side observations (agent cases come from the nightly `live` job — reason documented in the file)
- [x] README: what it is, why, quickstart, non-goals, honest limitations, the ablation + calibration numbers
- [ ] 5-minute pitch video: problem → watch a run → one escalated exception → both benchmarks → the hybrid-orchestration doctrine
- [x] Public repo, clean history, LICENSE (Apache-2.0)
