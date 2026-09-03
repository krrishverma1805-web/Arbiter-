# CLAIMS AUDIT

Every number that appears in a submission-facing surface (README, cockpit, the
demo, the benchmark output, the buildathon docs), with its source, the command
that produces it, the dataset/seed, its scope, and a synthetic/live label.

**Rule enforced:** no surface states anything stronger than a row here.
`docs/CLAIMS.md` is the compact claim→proof matrix; this is the exhaustive
number-by-number audit.

Verified 2026-09-04, HEAD `aae0e34`.

## Matching / reconciliation

| Number | Where it appears | Command | Dataset · seed | Scope | Label |
|---|---|---|---|---|---|
| **auto-match 93.8%** | README, BENCHMARK.md, DEMO.md, STATUS.md, pitch one-liner | `arbiter bench --spec specs/razorpay-settlement.yaml --dataset datasets/seed` | seed · 42 · `--no-ai` | one deterministic run | **synthetic** |
| **false-match 0.0%** | README, BENCHMARK.md, DEMO.md, SAFETY_RESULTS.md | same | seed · 42 | same | **synthetic** |
| precision 100% · recall 93.8% | README | same | seed · 42 | same | **synthetic** |
| **₹ coverage 100%** | README, BENCHMARK.md, DEMO.md | same | seed · 42 | same | **synthetic** |
| ₹ unexplained 0.7% | README | same (`dollar_unexplained` = 0.0066) | seed · 42 | same | **synthetic** |
| ~9 open exceptions / ₹1.73 lakh | pitch one-liner, README | `arbiter run --no-ai` + `arbiter clusters` | seed · 42 | same run | **synthetic** |
| ECE 0.12 (recalibrated) | README "Calibration" | `arbiter bench --calibration` | seed · 42 | matcher confidence, degenerate at this scale (single-valued) | **synthetic** |
| adversarial floor: false-match ≤ 1% · ₹ coverage ≥ 99% · auto-match ≥ 55% | CI `bench` job | `arbiter bench` on `--difficulty adversarial` | seed · 7 | CI invariant | **synthetic** |

## Safety (matching scorecard `SafetyScore`)

| Number | Where | Command | Scope | Label |
|---|---|---|---|---|
| **unsafe_resolution_rate 0.0%** | README, SAFETY_RESULTS.md, AI_SAFETY.md | `arbiter bench --dataset datasets/seed` | of the 2 human-only items in the seed run | **synthetic** |
| **₹ protected ₹53,245 (100%)** | README, BENCHMARK.md, SAFETY_RESULTS.md | same | ₹ impact of human-only exceptions, all escalated/held | **synthetic** |
| replay divergence: none | README, SAFETY_RESULTS.md | `arbiter replay` / `arbiter bench` runs twice | terminal-hash comparison | verified, deterministic |
| fabricated citations 0 | README, SAFETY_RESULTS.md | same run | — | **synthetic** |
| injection quarantined 1 | SAFETY_RESULTS.md | same run | the seed dataset's one injection anomaly | **synthetic** |

## Attack Arbiter

| Number | Where | Command | Scope | Label |
|---|---|---|---|---|
| **12 contained · 0 unsafe · ₹0 unaccounted** | README, ATTACK_RESULTS.md, SAFETY_RESULTS.md, DEMO.md, STATUS.md, FINAL_REPORT.md | `arbiter attack --spec … --dataset datasets/seed` | 12 deterministic tampering scenarios | **synthetic (adversarial)** |
| "found and closed 4 real gaps" | ATTACK_RESULTS.md, chatgpt.md | git history + `test_attacks.py` | injection scope, FX handling, implausible dates, bank-credit linkage | verified in code |

## Agent trajectory benchmark (`arbiter agent-bench`)

| Number | Where | Command | Scope | Label |
|---|---|---|---|---|
| **99 labelled cases** | README, AGENT_EVALUATION.md, SAFETY_RESULTS.md | `arbiter agent-bench --client oracle --seeds 16` | 16 seeded reconciliations, exceptions mapped to labelled anomalies, filtered | **synthetic** |
| oracle: **100% task · 100% category · 100% escalation recall · 0 unsafe · +44% lift** | README, AGENT_EVALUATION.md, AI_SAFETY.md, FINAL_REPORT.md | `agent-bench --client oracle` | a **scripted** competent-agent client, not a real model | **synthetic · scripted client** |
| reckless: **0 material unsafe · 14 sub-rupee SAFE-gate slips · ₹1.14 total · ~40% harness-escalated · ~46% shown-and-rejected** | README, AGENT_EVALUATION.md, SAFETY_RESULTS.md, AI_SAFETY.md | `agent-bench --client reckless` | a **scripted** confidently-wrong client | **synthetic · scripted client** |
| fabricator: **100% escalated · 0 unsafe** | README, AGENT_EVALUATION.md | `agent-bench --client fabricator` | a **scripted** ghost-citation client | **synthetic · scripted client** |
| "+44% lift" | multiple | `ai_lift_vs_escalate_all` | lift over the trivial "escalate every exception" policy, NOT over the deterministic classifier | **synthetic · scripted** |

> **These bound the harness/control architecture, not the production accuracy of
> GPT-4o or Claude.** No claim of live-model accuracy is made anywhere. The
> nightly CI job runs `agent-bench --client anthropic` when the API-key secret is
> set — until it does, this row stays scripted-only.

## Live-model evidence

| Claim | Where | Scope | Label |
|---|---|---|---|
| "one live gpt-4o investigation captured — the verifier caught a bad TIMING proposal" | DEMO.md, AGENT_EVALUATION.md, SAFETY_RESULTS.md, LIMITATIONS.md, chatgpt.md §6.1 | a **single** real investigation on run `f7e810ba`, frozen into the hosted demo | **live representative trace — not a benchmark** |
| tokens 18,932 in / 1,075 out · cost ≈ $0.058 | demo scorecard, chatgpt.md | that one investigation | **live** (real token counts; cost is an estimate from the shared price table) |

## Build / test

| Number | Where | Command | Label |
|---|---|---|---|
| **255 tests** | README, FINAL_REPORT.md, SUBMISSION_CHECKLIST.md, FINAL_AUDIT.md | `pytest -m "not live"` | verified locally + CI |
| ruff / mypy / tsc / next build clean | everywhere | the respective commands | verified |
| `datasets/seed` regenerates byte-identically | red-team, LIMITATIONS.md | `arbiter-datagen gen --scenario d2c --records 800 --seed 42` → `dataset_hash` match | verified |

## Numbers that are DELIBERATELY NOT CLAIMED

- production accuracy / real-world match rate
- customer validation / ROI
- 100% safety / universal prompt-injection immunity
- live-model agent accuracy
- audited compliance / SOC 2
- production-scale capacity

These appear only in the "what is NOT claimed" lists in
`docs/buildathon/LIMITATIONS.md`, `docs/CLAIMS.md`, and `README.md`.
