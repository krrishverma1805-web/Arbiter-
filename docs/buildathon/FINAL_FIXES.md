# FINAL FIXES

Every change in the final ship pass (`ARBITER_FINAL_BUILDATHON_SHIP_SPEC.md`).
Format: CHANGE · WHY · FILES · TESTS · RESULT · REGRESSION RISK.

The bulk of the ship spec was already satisfied by the four-stage hardening pass
(`be84bbf` → `aae0e34`; see [`../ENGINEERING_AUDIT.md`](../ENGINEERING_AUDIT.md) §11).
This document covers only the final pass.

---

## F1 · One authoritative capability matrix

- **Why:** spec P0.3 — no README/report/demo may contradict a single status source.
- **Files:** `docs/STATUS.md` (new), `README.md` (link).
- **Tests:** n/a (documentation).
- **Result:** every capability is DONE / LIMITED / NOT BUILT with its proof command.
- **Regression risk:** none.

## F2 · Reconcile the pitch one-liner to the reproducible number

- **Why:** spec P0.4 — every number must map to a command. "97.2% / ₹41,900 / 6
  exceptions" was illustrative; `arbiter bench --dataset datasets/seed` gives
  **93.8% / ₹1.73 lakh / 9 exceptions**.
- **Files:** `README.md`, `chatgpt.md`, `docs/02-product-spec.md`,
  `docs/05-design-doctrine.md`, `docs/06-feature-inventory.md`,
  `docs/20-api-and-frontend-spec.md`.
- **Tests:** `make bench` output cross-checked.
- **Result:** the pitch sentence is now the literal output shape.
- **Regression risk:** none.

## F3 · Fix stale cycle-learning numbers

- **Why:** `docs/07` §3.4 claimed a "~85% → 93% → 97%" auto-match climb "from the
  real run" — `arbiter cycle-demo` actually reports ₹ recovered (₹1,498 across
  two later closes). Same class of drift already fixed in docs/02/08/24.
- **Files:** `docs/07-evaluation-and-benchmark.md`, `docs/25-testing-and-ci-strategy.md`.
- **Tests:** `arbiter cycle-demo` output cross-checked; `test_cycle.py` enforces
  the shape (rules only ever help).
- **Result:** docs match code.
- **Regression risk:** none.

## F4 · agent-bench corpus sharing + CI runtime

- **Why:** `test_agent_bench.py` built the corpus three times (18 reconciliations);
  the CI `test` job ran ~20–30 min with `--cov` instrumentation, which gates
  nothing.
- **Files:** `packages/engine/tests/test_agent_bench.py` (uses `evaluate_all()` —
  one corpus, all three clients), `.github/workflows/ci.yml` (main `test` job
  drops `--cov`; the nightly job picks up coverage **and** a live-model
  `agent-bench --client anthropic` run when the `ANTHROPIC_API_KEY` secret is set).
- **Tests:** `test_agent_bench.py` — 6 tests, ~25 s (was ~60 s).
- **Result:** faster CI; a real-model agent benchmark now runs nightly if the
  secret is configured — closes the one LIMITED row in `docs/STATUS.md` on the
  user's side.
- **Regression risk:** low — `evaluate_all()` was already used by
  `arbiter agent-bench --client all` and CI; the test just consumes it.

## F5 · README test count

- **Why:** said "229 tests"; the suite is 259.
- **Files:** `README.md`.
- **Regression risk:** none.

## F6 · The six deliverable docs

- **Files:** `docs/buildathon/FINAL_AUDIT.md`, `FINAL_FIXES.md`,
  `FINAL_VALIDATION.md`, `CLAIMS_AUDIT.md` (→ `docs/CLAIMS_AUDIT.md`),
  `FINAL_RED_TEAM.md`, `BUILDATHON_READINESS.md`.
- **Regression risk:** none.
