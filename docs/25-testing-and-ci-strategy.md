# 25 — Testing & CI Strategy

_How Arbiter earns "code trust" (a stated judging criterion). The test suite is itself a demo artifact — a judge can read it and see the guarantees are enforced, not claimed._

---

## 1. Test layers

| Layer | Tool | What it covers |
|---|---|---|
| Unit | pytest | pure functions: `money` (paise arithmetic), `extract_utr`, FS weight, date-window logic, the rule-expression AST evaluator |
| Property | hypothesis | invariants that must hold for *any* generated batch (§2) |
| Golden / snapshot | pytest + committed fixtures | full runs on committed batches → expected match groups + scorecard; diff on change |
| Contract | pytest | the agent's output always validates the `Proposal`/`Escalate` schema; every `explanation` claim has a real `evidence_ref` ([doc 19 §7](19-agent-contracts.md)) |
| Determinism | pytest | `run` twice → identical event hash chain; `--resume` from every state boundary → identical terminal hash |
| Calibration | `arbiter bench --calibration` in CI | matcher ECE ≤ 0.05; agent ECE ≤ 0.05 (or recalibrated) |
| Security | pytest | injection strings in untrusted fields → `SECURITY_REVIEW`, never reach the agent; CSV formula neutralization; file size/row caps |
| Integration | pytest + httpx | API routes, SSE stream framing, idempotency (409 returns existing run) |
| E2E | Playwright | the triage flow: open run → expand exception → click evidence-ref → accept → see consequence |
| A11y | axe-core (Playwright) | WCAG 2.2 AA on the cockpit routes |
| Supply chain | pip-audit, npm audit, gitleaks | high-severity deps fail CI; no secrets in commits |

---

## 2. Property tests (the invariants)

For any `datagen` batch + spec:

1. **Conservation:** `matched_records + exception_records + low_confidence_records == total_records`. Nothing is silently dropped.
2. **No double-claim:** no record id appears in two accepted matches.
3. **Identity holds for subset matches:** every `subset`/`subset_heuristic` match's decomposition residual ≤ `rounding_tolerance`.
4. **Monotonic thresholds:** a match at confidence `c` implies all its per-field weights are consistent with `c` via the calibrated map.
5. **Determinism:** `hash(run(batch)) == hash(run(batch))`.
6. **Blocking recall:** every true match (from `ground_truth`) has its members sharing ≥1 block. Target ≥ 99.5%.
7. **Replay fidelity:** projections rebuilt from the event log == projections from the live run.
8. **`--no-ai` completeness:** the pipeline completes and produces a full matching scorecard with zero LLM calls.

---

## 3. Agent testing (without burning money on every CI run)

- **Recorded fixtures:** a set of `AGENT_INTERACTION` recordings from real Opus/Haiku runs, committed. Most agent tests replay these — deterministic, free, fast.
- **Live agent tests:** a small, tagged suite (`@pytest.mark.live`) that actually calls the API on the seed dataset — run nightly and on release, not per-push, using Haiku + Batch API (~$0.30/run).
- **`bench` in CI:** per-push CI runs `arbiter bench --no-ai` (free) + a cached/recorded agent scorecard. The full live `bench` runs nightly and its scorecard history is committed to `bench-history/`.

---

## 4. CI pipeline (`.github/workflows/ci.yml`)

```
on: [push, pull_request]

jobs:
  lint-type:        ruff + mypy (engine, strict) ; tsc --noEmit + eslint (web)
  test-engine:      pytest -m "not live" --cov ; fail if engine cov < 85% or matcher/decompose < 95%
  determinism:      the determinism + resume property tests (isolated job so a failure is unmistakable)
  bench:            arbiter gen (committed seed) ; arbiter bench --no-ai ;
                    arbiter bench (recorded agent) ;
                    upload scorecard.json + scorecard.html ; comment headline metrics on the PR ;
                    FAIL if auto_match_rate drops > 2 pts vs bench-history/baseline.json
                    FAIL if false_match_rate > 1.5%
  security:         pip-audit ; npm audit --audit-level=high ; gitleaks
  web-test:         vitest ; playwright (triage flow + axe) against a seeded run
  build:            docker build (multi-stage) ; docker compose up + smoke test /healthz

nightly:
  live-agent:       pytest -m live ; arbiter bench (live, Haiku) ; append to bench-history/
```

PR comment (the bot) — **schematic; the shape, not the numbers** (the CI `bench` job
already asserts an absolute floor and a regression gate against `bench/baseline-800.json`):
```
Arbiter bench — seed dataset (800 records, seed 42, --no-ai)
  auto-match rate   93.8%   vs baseline gate ✓
  false-match rate  0.0%    ✓ under the 1.5% gate
  ₹ coverage        100%
  agent-bench: oracle 100% task · 0 unsafe · +44% lift · reckless 0 material unsafe
  replay            deterministic ✓
```

---

## 5. Coverage targets

| Module | Line coverage |
|---|---|
| `match/`, `decompose/` | ≥ 95% |
| `events/`, `specs/`, `exceptions/` | ≥ 90% |
| `agent/` (harness, not model output) | ≥ 85% |
| `ingest/`, `bench/`, `learn/`, `memo/` | ≥ 85% |
| engine overall | ≥ 85% (hard gate) |
| `datagen/` | ≥ 80% |

---

## 6. What a failing test *becomes*

Every real CI failure during the build gets an entry in [`BUILD-LOG.md`](BUILD-LOG.md): symptom → root cause → fix → the test/gate that now prevents recurrence. That log is the Failure-Recovery criterion, written continuously rather than reconstructed.
