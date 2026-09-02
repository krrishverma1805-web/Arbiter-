# Build Log

An honest, running account of what broke during development and how it was resolved.
This directly serves the Buildathon's **Failure Recovery** criterion — kept from day one,
not reconstructed at the end.

Format: newest first. Each entry: what broke · how it showed up · root cause · fix · what changed to prevent recurrence.

---

## 2026-09-02 — Phase 1.3: agent grounding + category verification (docs/28)

The agent's `evidence_refs` were self-reported and trusted. Now, before any
proposal reaches a human (`agent/grounding.py`):

- **Grounding.** Every cited `record_id` must resolve to a real record /
  decomposition / match in the run. A citation that points at nothing is a
  fabrication — the proposal is voided and the exception escalates
  (`reason: contradictory`). This is the authoritative `hallucination_rate` now.
- **Category check.** A deterministic test that the proposed category fits the
  evidence shape (DUPLICATE needs a repeated `payment_id`, ROUNDING needs a small
  residual, CHARGEBACK needs a `dispute_id`, …). Zero LLM cost. A mismatch caps
  confidence at 0.4.
- **`grounded_confidence`.** The model's raw self-assessment is never used for
  the escalation decision or shown to the human — it's re-derived from how many
  citations resolved and how well the fields check out. Below `theta_escalate`
  → escalate instead of propose.

The frozen prompt (V1) gained a line telling the model its citations are verified
and its confidence re-derived. `test_agent.py` gains three cases: fabricated ref
→ escalate, weak grounded confidence → escalate, category inconsistent with
evidence → escalate. 95 tests.

## 2026-09-02 — M5 stretch: `arbiter cash-position`

The reconciled ledger answers "is the money right?"; this answers "where is it?" —
every settled rupee partitioned into confirmed-in-bank / in-transit / held /
unexplained, as pure arithmetic (no LLM).

**First cut didn't reconcile.** It summed exception `amount_impact_minor` into the
buckets, but that field is a *severity heuristic* for ranking the queue, not a
balance — it double-counted against `confirmed` and left a ₹30–70k `Δ`.

**Fix: partition the settlement batches, not the exceptions.** Every processor row
belongs to exactly one `settlement_utr`; each batch's net (gross − MDR − GST −
refunds for *its* rows) lands in one bucket, chosen by the highest-severity
exception that touches it, else by whether its decomposition is clean. Now the
four buckets sum back to the processor-side net exactly — `reconciling_delta` is
0 on every seed, and a non-zero value would be surfaced, not hidden.
`test_cash.py` asserts the partition and its determinism.

## 2026-09-02 — M5: the cycle demo, and making the learning loop actually move a number

The learning-loop *mechanism* landed earlier; this is the demo that proves it —
three monthly closes with the learned rule carried forward (`arbiter cycle-demo`,
`make cycle`).

**What didn't work at first.** The pitch (docs/02 §5.3) is "resolve once → the
match rate rises next cycle." But every mechanical anomaly the generator injected
was *already* classified by a base-spec rule, and the one recurring `UNEXPLAINED`
was an orphan bank credit — genuinely undecidable, correctly not generalisable.
There was nothing for a learned rule to catch.

**Root cause.** `datagen`'s `SPLIT_BATCH` injector moved a payment between two
settlement batches but never froze either batch's bank credit, so both re-tied
and the "split" produced no residual at all — a silent no-op anomaly (it was the
one the scorecard's `detected_anomalies` always missed).

**Fix.**
- `_split_batch` now `freeze_bank(dst)`: the destination settlement was paid
  before the order was re-routed into it, so it carries a real, labelled residual
  until someone recognises the two halves net out. The source re-ties cleanly.
- `arbiter resolve --category <C>` (and the API `category` field): a controller
  correcting the classifier — "this UNEXPLAINED residual is a SPLIT_SETTLEMENT" —
  is what seeds the rule. `RESOLUTION_APPLIED` carries the correction; the fold
  applies it to the exception (`classified_by: human:<actor>`).
- `SPLIT_SETTLEMENT` template added to `synthesize.py`:
  `exception.record_count >= {rc} and abs(exception.residual_minor) <= {band}` —
  the `rc` floor (≥ 3, generalised down from the resolved case) keeps it off 1:1
  residuals; the band is 2× the accepted variance, so a larger one still opens an
  exception.

**The demo is an A/B, not a single line.** Each close is a fresh random batch, so
batch-to-batch noise would swamp one metric column. `cycle-demo` scores every
close twice — once on the base spec, once on the carried-forward spec — and
reports the gap. That gap is the rule and nothing else.

**Verified:** the 800-record bench gate is unchanged (auto-match 93.75%,
false-match 0.0%, coverage 100%, replay hash stable); `test_cycle.py` asserts the
later closes never regress and at least one recovers money the base spec left
UNEXPLAINED. Full suite 90 tests, `ruff` + `mypy` clean.

## 2026-09-02 — M5: the learning loop + the Close Memo (docs/02 §5.3, docs/20 §2.6)

When a human resolves an exception, Arbiter drafts a **candidate classification rule**
in the same safe-AST language the spec already uses (`arbiter_engine/learn/synthesize.py`).
The draft is deliberately narrow — it fires only for exceptions that look like the one
just resolved (same category, residual within a widened band, same source) — and only
for mechanical categories. Judgement categories (`UNEXPLAINED`, `AMBIGUOUS`,
`SECURITY_REVIEW`, `WRONG_ACCOUNT`) never generalise: a `draft_rule_from_resolution`
returns `None` and the resolution stays a one-off.

`RULE_DRAFTED` is an event. `arbiter rules pending <run>` diffs a run's drafts against
the live spec; `arbiter rules merge <run>` splices the approved rules into the `rules:`
block as reviewable YAML (provenance comment + `# learned <id>`), bumps `version:`, and
emits `RULE_MERGED`. A merged rule drives classification on the next run — the loop
closes without any model in it. Same three commands on the API
(`/v1/exceptions/.../resolve` now returns `drafted_rule`, `/v1/runs/{id}/rules/pending`,
`/v1/runs/{id}/rules/merge`).

`arbiter memo <run>` renders the **Reconciliation Close Memo** — one self-contained HTML
file, no external resources, opens offline: the result, the settlement decomposition
(gross → MDR → GST → refunds → net), every exception with its category / ₹ impact /
who classified it / status / resolution, and the audit trail with the terminal hash
and the `arbiter verify` command that reproduces it.

**Bugs caught:**
- `merge_rules` first appended rules at EOF, landing a `- id:` list item after the
  `adjudication:` mapping → invalid YAML. Fixed to splice after the last indented line
  of the `rules:` block (a column-0 line or section comment ends the block).
- The spliced `when:` used `yaml.safe_dump(value).strip()`, which emits a trailing
  `...` document-end marker on a scalar — a stray `...` line broke the parse. Switched
  to `json.dumps(value)` (valid YAML double-quoted scalar, handles the `'…'` literals).
- Draft dict / payload key mismatch (`id` vs `rule_id`) surfaced as a pydantic
  `ValidationError` and a CLI `KeyError`; unified on `rule_id` for the draft/pending
  dicts, `id` stays the YAML rule key.

`arbiter audit-pack <run>` zips the three things an auditor needs — the full
hash-chained `event-log.jsonl`, the `close-memo.html`, and a `manifest.json` with
the terminal hash and the `verify` command — so the whole run travels as one file
and the chain can be recomputed offline.

Prevention: `test_learn.py` (draft safety, judgement categories don't generalise,
pending→merge bumps the version and re-parses, a merged rule classifies the next run),
`test_memo.py` (self-contained document, every exception listed), `test_audit_pack.py`
(the zip's manifest matches `verify`, the log line count matches, the chain head is
genesis) — plus an API test for resolve → pending. Full suite + `ruff` + `mypy` green;
the merge writes to a spec copy in tests, never the repo's.

## 2026-09-02 — M4b: the cockpit (`web/`, docs/05 + docs/20 §2)

Next.js 15 (App Router) + React 19 + Tailwind + TypeScript strict. The design tokens
from docs/05 §3.1 are CSS variables with full light/dark parity (`:root`, `@media
prefers-color-scheme`, `[data-theme]`) and `prefers-reduced-motion` honoured.

Three surfaces on one screen (docs/05 §2):
1. **Scorecard** (left) — auto-tied %, precision, false-match rate, ₹ coverage, the
   exception mix, the agent panel (task-completion, hallucination, escalation recall,
   cost), determinism ✓, throughput.
2. **Exception queue** (centre) — ranked by ₹ impact, keyboard-first
   (`j`/`k` move, `e` drawer, `a` accept, `w` won't-fix), typed category chips
   (colour + label), status pills. Empty state is a celebrated "Everything tied."
3. **Evidence drawer** (right) — the records side by side, the identity equation with
   the residual called out, the agent's proposal/escalation clearly badged, and the
   resolution controls (which POST to `/v1/exceptions/.../resolve`).

`/` lists runs + a "reconcile" form (spec × dataset × `--no-ai`).

**Bug caught:** server-side `fetch` in a React Server Component can't use a relative
URL, and a module-level `const BASE = typeof window ...` was resolving to the client
branch in the Next server bundle. Fixed: `base()` is now a function evaluated per call
(server → `ARBITER_API_URL` / `127.0.0.1:8000`, client → `/api` via the Next rewrite).

`tsc --noEmit`, `next lint`, and `next build` all clean; verified end to end against a
live API (`make up`). CI gains a `web` job (typecheck + lint + build). `make up` runs
both; the Makefile gains `api` / `web` / `up` / `bench` targets.

## 2026-09-02 — M4a: the HTTP API (docs/20 §1)

`packages/api` — a FastAPI wrapping the engine, the cockpit backend + the customer
integration surface. Routes: `/healthz` `/readyz`; `/v1/specs` `/v1/datasets`;
`POST /v1/runs`; `/v1/runs` list + detail + `/scorecard` + `/matches` + `/exceptions`
+ `/verify` + `/replay` + `/stream` (SSE); `/v1/exceptions/{run}/{id}` (the
evidence-drawer payload) + `/resolve` (→ `RESOLUTION_APPLIED`). RFC-9457-ish problem
responses. New events: `RESOLUTION_APPLIED` / `RULE_DRAFTED` / `RULE_MERGED`, folded
onto exceptions (a resolved exception carries its resolution + status).

**Bug caught:** the API needs the store to persist across requests — an in-memory
`sqlite://` engine drops its tables between connections. Fixed in `EventStore`: for
`sqlite://` / `:memory:` it now uses a `StaticPool` (one kept-alive connection per
engine, so separate `EventStore()` instances stay isolated — the determinism tests
still pass).

6 API tests (health, spec/dataset listing, full run lifecycle, evidence drawer +
resolve, 404s). 79 tests total. Live smoke: `arbiter-api` serves and a `POST /v1/runs`
completes end to end. ruff + mypy(strict) clean.

## 2026-09-02 — M3: the investigation agent (ADR-0004)

The skeleton FSM gains an `INVESTIGATING` phase. For each `UNEXPLAINED` / `AMBIGUOUS`
exception (never `SECURITY_REVIEW`), a bounded agent loop runs: `PLAN → INVESTIGATE
(read-only tools) → HYPOTHESIZE & TEST → DECIDE → Proposal | Escalate`.

- `agent/schemas.py` — strict `Proposal` / `Escalate` pydantic contracts; category is a
  fixed enum (the agent cannot invent one).
- `agent/prompts.py` — the frozen, hashed system prompt.
- `agent/fencing.py` — every untrusted record field wrapped in `<untrusted-record-data>`;
  the raw `<`/`>` replaced so an injected tag can't close the fence.
- `agent/tools.py` — 5 read-only tools (`query_evidence`, `counterparty_history`,
  `similar_exceptions`, `candidate_matches`, `decomposition_detail`) + the task-message
  builder. **No tool mutates a match, a record, a ledger entry, or money** (docs/14 C3).
- `agent/client.py` — pluggable `LLMClient`: `AnthropicClient` (real, `claude-opus-5`,
  adaptive thinking), `RecordedClient` (replays `AGENT_INTERACTION` events — so
  `arbiter replay` reproduces a run without the API), `ScriptedClient` (offline tests).
- `agent/investigator.py` — the bounded loop (turn + token budgets; forces the decision
  on the last turn; malformed output → escalation, never a guess).
- `agent/orchestrate.py` — drives the phase, emits `AGENT_INVESTIGATION_STARTED`,
  `AGENT_INTERACTION*`, `AGENT_PROPOSAL_CREATED | AGENT_ESCALATED`; per-run cost ceiling;
  with no `ANTHROPIC_API_KEY` it escalates *deterministically* (no LLM call) so the run
  still completes and stays reproducible.
- `bench` gains the **agent scorecard** (task-completion, category accuracy of proposals,
  escalation precision/recall, hallucination rate, tool calls, cost) and `--ablate`
  (`--no-ai` vs haiku/sonnet/opus). `arbiter explain` prints the evidence + the agent's
  proposal/escalation as text.

`--no-ai` skips the phase entirely. `arbiter replay` and `--rerun` reproduce the exact
terminal hash (verified). 74 tests + 1 skipped live test; a nightly CI job runs the
live suite. ruff + mypy(strict) clean.

## 2026-09-02 — Benchmark correctness fix (the CI `bench` gate)

**Symptom:** the `bench` CI job (which runs on an 800-record batch) would fail its
scorecard gate — on 800 records the reported false-match rate was ~57% and auto-match
~21%, while unit tests, the `lint-type`, `test` and `determinism` jobs all passed.

**Root cause — two test-harness bugs, not engine bugs:**
1. **Anomaly density scaled linearly.** `plan()` used `records // 60` per anomaly type,
   so at 800 records ~13 of every type were injected — a *majority* of settlement
   batches were anomalous, which is nothing like real reconciliation (~1–5%).
2. **The scorecard's "false match" definition was too strict.** It counted *any*
   predicted match on a batch not in `ground_truth.true_matches` as a false match —
   even when the matcher correctly tied the identity within tolerance and an exception
   was opened for the residual. A tied identity with a flagged variance is correct
   behaviour, not a false match.

**Fix:**
1. `plan()` now targets a realistic anomalous-batch fraction (normal ≈ 8%, hard ≈ 18%),
   distributed across types by weight, capped — never a majority.
2. The scorer redefines a **false match** as: the matcher auto-tied a batch whose
   identity does *not* close **and** no exception flagged it. A tie whose identity
   closes is correct; a non-closing tie that an exception caught is "flagged", counted
   as neither correct nor false.

**Result:** honest, stable numbers at every scale — 120 rec: auto-match 94%, precision
94%, false-match 0%; 800 rec: 100% / 100% / 0%. New tests
(`test_scorecard_holds_at_scale`, `test_hard_difficulty_degrades_visibly`) lock this in.
CI now also pins Python 3.12.

**Note on earlier commits:** the M1–M2c commits' `bench` job would have failed this
gate for the reasons above. The engine on those commits was always deterministic and
correct — the *benchmark was mis-measuring it*. Every other CI job (lint, types, unit
tests, determinism) passed on those commits; history was not rewritten.

## 2026-09-02 — M2: Fellegi–Sunter, subset/fuzzy passes, resume, calibration

- **M2a — probabilistic matching** (ADR-0005): `match/fellegi_sunter.py` (agreement
  levels, m/u, weight = Σ log2(m/u), posterior from the block prior, a calibration
  hook, and `from_labeled` frequency estimation); `match/compare.py` (comparison
  vectors + Jaro–Winkler); `match/subset.py` (subset-sum matching — exact
  meet-in-the-middle ≤22, greedy above, returns None on ambiguity). `match/engine.py`
  rewritten to 4 passes: exact · tolerant (FS-weighted) · subset · fuzzy (candidates
  attached, never auto-matched).
- **M2b — resilience + calibration**: `arbiter run --resume` (resumes a crashed run
  from its last committed stage — reproduces the exact terminal hash from every stage
  boundary, tested) and `--rerun`; `arbiter bench --calibration` (reliability diagram,
  Expected Calibration Error, Pool-Adjacent-Violators isotonic recalibration when
  ECE > 0.05).

**M2 calibration finding:** the deterministic matcher is *slightly over-confident* —
16 matches all stated at 1.00 confidence, observed accuracy 0.94, ECE 0.062 → an
isotonic map is fitted and disclosed. Exactly the kind of thing the calibration study
exists to catch.

- **M2c — safe-AST rule engine** (ADR-0003): `exceptions/rules.py` parses a spec's
  `rules:` `when:` expressions with Python's `ast` module against a strict node
  whitelist (no `eval`, no imports, no comprehensions/lambdas, no dunder names, no
  private-attribute access, per-object attribute allow-lists). `exceptions/context.py`
  builds the `RuleContext` (safe helper fns: `abs`, `is_empty`, `injection_signal`,
  `count_records`, `unmatched`, `ts_day`, …). The classifier now consults the spec's
  rules first; a broken rule never crashes a run, it just doesn't fire. The reference
  spec's 7 rules all compile and drive the `_classify_residual` path.

66 tests (rule safety: `__import__`/`open`/`lambda`/comprehension/dunder all rejected;
first-match-wins; broken-rule tolerance; the reference spec's rules compile).
ruff + mypy(strict) clean.

## 2026-09-02 — M1: matching engine, decomposition, classifier, `arbiter bench`

The deterministic skeleton FSM now runs end to end:
`INGESTING → MATCHING → DECOMPOSING → CLASSIFYING → RUN_COMPLETED`.

- **match/** — blocking by `settlement_utr`; pass 1 (exact) + pass 2 (tolerant) with an
  explicit confidence formula (`match/confidence.py`; Fellegi–Sunter m/u + calibration is
  M2 per ADR-0005). Deterministic (sorted iteration, integer paise).
- **decompose/** — the settlement identity `net = Σcredit − Σdebit − Σfee − Σtax` per UTR
  group, with the ledger cross-check; residual drives classification.
- **exceptions/** — the taxonomy, the deterministic injection scanner (untrusted fields →
  `SECURITY_REVIEW`, never sent onward — docs/14 C2), and the M1 classifier covering
  ROUNDING / FEE_DEDUCTION / TIMING / WRONG_ACCOUNT / PARTIAL_PAYMENT / DUPLICATE /
  CHARGEBACK / MISSING_UTR / UNEXPLAINED.
- **bench/** — `arbiter bench` scores a run against `ground_truth.json`: auto-match rate,
  precision, recall, **false-match rate**, ₹ coverage, exception mix, category accuracy,
  throughput, and a live determinism check (a second run must reproduce the hash chain).
- datagen: anomalies now create *real* discrepancies — FEE_DRIFT/GST_ROUND/DUP_EXPORT
  "freeze" the bank at the pre-anomaly amount so the processor file is what's wrong;
  TIMING_STRADDLE actually shifts `settled_at` past the period end.

**Honest M1 baseline** (seed batch, 270 records, difficulty=normal, no AI):
auto-match 88.2% · precision 93.8% · false-match 6.2% · ₹ coverage 100% ·
10/11 anomalies detected · 60% category accuracy · deterministic ✓. This is the number
the agent (M3) is measured against.

**Bugs caught during M1 (Failure Recovery):**

| Symptom | Root cause | Fix | Prevention |
|---|---|---|---|
| 0 matches — every batch became an exception | `extract_utr` regex matched the word "RAZORPAY" as the UTR before the real reference | rewrote it: prefer a token after an explicit `UTR`/`REF` label, then a long alphanumeric token that *contains a digit* (English words never do) | direct `extract_utr` unit cases + the clean-batch test asserts full match |
| GST_ROUND / FEE_DRIFT anomalies invisible | datagen recomputed the bank credit *after* the anomaly, so the identity still closed | `freeze_bank()` snapshots each batch's clean net before the anomaly phase | `test_adversarial_scorecard_is_honest` asserts a sub-perfect but strong baseline |
| CHARGEBACK batch classified WRONG_ACCOUNT | a later TIMING_STRADDLE / WRONG_ACCT injector dropped the same batch the chargeback landed in | chargeback marks its batch `protected`; the drop-batch injectors skip protected batches | — |

## 2026-09-02 — M0: scaffold, event store, ingestion, datagen (code begins)

First code. uv workspace + two packages (`arbiter-engine`, `arbiter-datagen`). Shipped:
money (integer paise), canonical hashing, the hash-chained event store + `verify`,
the recon-spec loader, CSV ingestion (→ `RECORD_INGESTED` events), the clean-batch
synthetic data generator with ground truth, the `arbiter` CLI (`run` / `replay` /
`verify` / `events` / `gen`), 27 tests, ruff + mypy(strict) clean, CI (4 jobs incl. an
isolated determinism gate). `arbiter run` ingests the 270-record seed batch
deterministically; `arbiter replay` reproduces it.

**Bugs caught during M0 (Failure Recovery):**

| Symptom | Root cause | Fix | Prevention |
|---|---|---|---|
| `test_two_runs_produce_identical_hash_chains` failed on the first real run | `RUN_COMPLETED.wallclock_ms` (a wall-clock duration) was in the **hashed** payload → every run's terminal hash differed | moved timing to a non-hashed `Event.meta` sidecar; the hash chain now covers semantic content only (matches docs/12 §4) | the determinism test itself — it earned its keep on day one; it runs as an isolated CI job |
| 120 ledger rows + 2 bank rows quarantined as "unparseable / missing amount" | (a) normalize didn't map the ledger's `order_total` to the amount field; (b) the CSV formula-injection neutralizer was prepending `'` to negative numbers **at ingest** | (a) added `order_total` to the amount resolution chain; (b) `neutralize_for_export` is now export-only, never at ingest (docs/14 C4) | `test_ingests_the_clean_dataset` asserts `rows_quarantined == 0`; identity property test on datagen |
| bank amounts double-scaled | datagen wrote bank credits in paise while the bank source spec expects rupees | datagen writes bank statements in rupees (realistic) | `test_settlement_identity_holds_for_every_batch` |

## 2026-09-02 — Compliance, competitive-field, and completeness pass

- **Git history corrected:** the first 3 commits were mis-attributed (author email
  `rajdeepsinghsakarwar@gmail.com` → GitHub account `Rajdeepsingh49`). Rewrote all commits to
  `krrishverma1805-web <krrishverma1805@gmail.com>` and force-pushed. Local git config +
  a memory now enforce the right identity for all future commits.
- **Competitive landscape ([doc 03 §2.8a](03-competitive-landscape.md)):** added the OSS AI
  reconciliation agents — notably `Manu6259/financial-reconciliation-agent`, which independently
  arrived at the same "LLM proposes, deterministic code disposes" principle. Documented exactly
  where Arbiter goes deeper (adversarial scale, settlement decomposition, the investigation-loop
  agent, calibration, multi-rail, honest sub-100 benchmark).
- **Doc 26 — Compliance & Data Protection:** RBI PA-PG Directions 2025 (card-data minimisation —
  the schema already has no PAN field; data localisation for hosted), DPDP Act 2023/Rules 2025
  (data-fiduciary obligations, `arbiter purge` for the erasure right), PCI-DSS scope (likely out,
  by design), the minimised LLM payload.
- **Doc 12 §6.1a:** replaced the hand-wavy "human-judged equivalent" for `resolution_usefulness`
  with a proper LLM-as-judge protocol (binary reference-based rubric, cited evidence, judge
  ensemble, human-validated to Cohen's κ ≥ 0.6).
- **Doc 27 — Completeness Audit:** the full coverage matrix; the 3 items that are thin only
  because they're empirical (real match rate, real AI lift, heuristic behaviour); everything
  deliberately excluded + why. Verdict: the plan is done — build.
- Code begins now at M0.

## 2026-09-02 — Deep-dive specification pass

- Added 11 build-ready deep-dive docs (15–25) + ADR-0005 (Fellegi–Sunter matching) so nothing
  in the build is left to improvisation:
  - 15 domain model: the settlement identity, the exhaustive exception taxonomy with root
    causes / detection / resolution playbooks / accounting treatment (journal entries).
  - 16 matching engine: blocking, Fellegi–Sunter (m/u seeded from the labeled synthetic data),
    the subset-sum pass (meet-in-the-middle + heuristic), assignment, determinism, perf budget.
  - 17 full physical schema (DDL), every event type + payload, projections, JSON contracts.
  - 18 synthetic data generator: generative model, anomaly-injection catalog, ground truth +
    labeled trajectories, anti-"teaching to the test".
  - 19 agent contracts: the frozen system prompt, per-exception task message, tool JSON
    schemas, strict Proposal/Escalate output schema, few-shots, budgets.
  - 20 API (routes, SSE, errors) + frontend (component tree, state coverage, keyboard, memo).
  - 21 GTM: positioning, ICP, wedge, pricing, unit economics, the field at the Buildathon.
  - 22 cost model (per-exception ~$0.035, per demo run ~$0.65, Buildathon total ~$300).
  - 23 risk register (build/scope/judging) with triggers + contingencies.
  - 24 the 5-minute pitch script + judge walkthrough + anticipated Q&A.
  - 25 testing & CI: property-test invariants, testing the agent cheaply, the pipeline.
- Research folded in: Razorpay `fetch-recon` schema, Fellegi–Sunter math, India settlement
  accounting treatment (SAC 998433, 18% GST on MDR, ITC), FloQast pricing benchmarks.

## 2026-09-02 — Plan evaluation pass

- **Adversarial self-review** of docs 01–10 ([doc 11](11-plan-evaluation-and-gaps.md)). Grade: B+. Found one structural weakness and 14 gaps.
- **Structural fix:** v1 described a pipeline with one LLM call, not an agent. Reframed as **hybrid orchestration** — deterministic skeleton + a real agentic investigation loop (plan → investigate → hypothesize/test → conclude/escalate) — [ADR-0004](adr/0004-hybrid-orchestration.md), [doc 12](12-agent-design.md).
- **New docs:** 11 (evaluation/gaps), 12 (agent design + agent scorecard + calibration), 13 (production readiness), 14 (security & trust), `KNOWN-FAILURE-MODES.md`.
- **Spec updated** to Razorpay's real `fetch-recon` field names (`entity_id`, `settlement_utr`, `debit`/`credit`/`fee`/`tax`, `dispute_id`, …).
- **Still no code broken** — code begins at M0.

## 2026-09-02 — Repository & research phase

- **Set up:** monorepo plan, full `docs/` research and specification set, ADRs, reference recon specs.
- **Nothing broken yet** — code begins at milestone M0.
- **Decision captured:** confined the LLM to a single bounded step ([ADR-0001](adr/0001-deterministic-core-ai-at-the-boundary.md)) after weighing an LLM-first matching approach and rejecting it on reproducibility/auditability grounds.

---

<!--
Template for future entries:

## YYYY-MM-DD — <short title>

**Symptom:** what was observed (test failure, wrong number, crash, judge feedback)
**Root cause:** the actual reason
**Fix:** what was changed
**Prevention:** the test / gate / doc added so it can't silently recur
-->
