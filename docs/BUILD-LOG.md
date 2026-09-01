# Build Log

An honest, running account of what broke during development and how it was resolved.
This directly serves the Buildathon's **Failure Recovery** criterion — kept from day one,
not reconstructed at the end.

Format: newest first. Each entry: what broke · how it showed up · root cause · fix · what changed to prevent recurrence.

---

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
