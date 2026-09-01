# 07 — Evaluation & Benchmark Methodology

_How Arbiter measures itself, honestly. This document is the direct answer to the Buildathon bar: "Throughput plus measured accuracy plus an honest exception list. One cherry-picked match proves nothing."_

> **Scope:** this document covers the **matching engine**. The **agent** is evaluated separately and just as rigorously — task-completion rate, tool-use accuracy, grounding/faithfulness, hallucination rate, escalation precision/recall, trajectory efficiency, and a confidence-calibration study — in **[doc 12 §6](12-agent-design.md)**. `arbiter bench` emits both scorecards.

---

## 1. Principle: the benchmark is a product feature, not a slide

Every reconciliation vendor claims a number ("90%+", "99%"). None publishes:
- the **false-match rate** (matches that are wrong),
- the **methodology** (what counts as a match, what data),
- a way for a stranger to **reproduce** it.

Arbiter ships all three. `arbiter bench` is a first-class command; `scorecard.json` is emitted on every run; CI publishes it on every commit. The claim and the means to check the claim travel together.

---

## 2. The ground-truth dataset

Measured accuracy requires known answers. Arbiter's `datagen` package generates synthetic batches **with a labeled answer key**.

### 2.1 What a batch contains

```
datasets/<name>/
├── razorpay_settlement.csv    # e.g. 40 settlement lines across 6 payout batches
├── bank.csv                   # e.g. 8 credits (6 settlements + 2 noise) 
├── ledger.csv                 # e.g. 210 orders + 12 refunds
├── ground_truth.json          # the answer key
└── manifest.json              # seed, generator version, params, anomaly counts
```

### 2.2 `ground_truth.json` schema

```json
{
  "matches": [
    { "settlement_id": "setl_001", "bank_utr": "UTR2026...", "ledger_order_ids": ["ord_1","ord_2", "..."],
      "expected_net_minor": 80453000, "clean": true }
  ],
  "anomalies": [
    { "id": "anom_01", "type": "DUPLICATE",
      "records": ["rp_line_88"], "correct_category": "DUPLICATE",
      "correct_resolution": "void_duplicate_of:pay_00042",
      "dollar_impact_minor": 129900,
      "resolvable_deterministically": false }
  ]
}
```

### 2.3 The anomaly catalog (labeled failure modes)

Each is injected at a configurable rate; each has a known correct category and resolution.

| Anomaly | Description | Deterministically resolvable? | Tests |
|---|---|---|---|
| `DUPLICATE` | Same payment appears twice in the settlement file | No (needs cross-check) | dedup + AI hypothesis |
| `PARTIAL_PAYMENT` | Customer paid less than order total | Sometimes | tolerance + classifier |
| `SPLIT_SETTLEMENT` | One order's payout split across two settlement cycles | No | subset pass |
| `FEE_DRIFT` | MDR charged ≠ contracted rate | Yes (fee schedule) | decomposition D5 |
| `GST_ROUNDING` | GST-on-MDR rounded differently than books | Yes (tolerance) | rule `r_rounding` |
| `MISSING_UTR` | Bank credit with no reference | No | fuzzy pass + AI |
| `TIMING_STRADDLE` | T+2 settlement lands in the next period | Yes (date rule) | rule `r_timing` |
| `CHARGEBACK` | Chargeback deducted from a later settlement | Partially | decomposition + AI |
| `FX_DIFFERENCE` | Intl payment settled at a different rate | Yes (tolerance) | tolerant pass |
| `WRONG_ACCOUNT` | Credit to a secondary bank account | No | AI hypothesis |
| `OVER_PAYMENT` | Duplicate customer payment for one order | No | AI + dedup |
| `REFUND_NETTING` | Refund netted against gross vs shown separately | Yes (identity) | decomposition |

The mix of "deterministically resolvable" vs "needs judgment" is the whole point: it lets the scorecard report **how much the deterministic core handles alone** vs **how much the AI step adds** vs **what neither can do** (the honest residue).

---

## 3. Metrics — exact definitions

Let the universe be all "true reconciliation units" (a true match, or a true anomaly) from `ground_truth.json`.

### 3.1 Matching metrics

| Metric | Definition | Target (demo dataset) |
|---|---|---|
| **Auto-match rate** | (records auto-tied at confidence ≥ θ_auto) / (records that are part of a true clean match) | 90–97% |
| **Match precision** | correct auto-matches / all auto-matches | ≥ 99.0% |
| **Match recall** | correct auto-matches / all true clean matches | ≥ 92% |
| **False-match rate** | auto-matches that contradict ground truth / all auto-matches | ≤ 1.0% — _reported prominently, never hidden_ |
| **Low-confidence tier size** | records matched at θ_review ≤ c < θ_auto | reported, not targeted |
| **$ coverage** | ₹ in correct auto-matches / total ₹ | ≥ 98% |
| **$ unexplained** | ₹ in `UNEXPLAINED` exceptions / total ₹ | ≤ 1% |

### 3.2 Exception-handling metrics

| Metric | Definition | Target |
|---|---|---|
| **Category accuracy** | exceptions whose assigned category == `correct_category` / all classified exceptions | ≥ 85% |
| **Resolution-proposal usefulness** | proposals whose `suggested_action` matches `correct_resolution` (exact or human-judged equivalent) / all proposals | ≥ 70% |
| **AI lift** | (category accuracy with AI) − (category accuracy, `--no-ai`) | report the delta — this is the AI's measured value |
| **Budget-exceeded rate** | exceptions marked `budget-exceeded` / all AI-adjudicated | ≤ 5% |
| **Human-touch count** | exceptions requiring a human decision | the headline "work remaining" number |

### 3.3 Throughput & cost

| Metric | Definition |
|---|---|
| **Records/sec** | total records / wall-clock (deterministic phase) |
| **End-to-end wall-clock** | ingest → scorecard, with and without AI |
| **LLM cost/run** | Σ token cost across adjudications (from `usage`) |
| **LLM cost/exception** | above / exceptions adjudicated |

### 3.4 Cycle metrics (the learning-loop evidence)

Run the same spec across 3 generated "monthly" batches, applying accepted rules between cycles:

| Cycle | Auto-match rate | Human-touch count | Rules in spec |
|---|---|---|---|
| 1 | ~85% | ~30 | 6 (baseline) |
| 2 | ~93% | ~12 | 11 |
| 3 | ~97% | ~5 | 15 |

The exact numbers come from the real run; the _shape_ (monotonic up) is the claim and is enforced by a test.

---

## 4. The scorecard artifact

`scorecard.json` (also rendered as an HTML page and a CLI table):

```json
{
  "run_id": "…", "spec": "razorpay-settlement@3", "generated_at": "…",
  "dataset": { "name": "d2c-aug", "seed": 42, "records": 214, "true_matches": 6, "anomalies": 11 },
  "matching": { "auto_match_rate": 0.972, "precision": 0.994, "recall": 0.951,
                "false_match_rate": 0.006, "low_confidence": 4,
                "dollar_coverage": 0.991, "dollar_unexplained": 0.004 },
  "exceptions": { "total": 6, "by_type": {"TIMING":2,"DUPLICATE":1,"FEE_DRIFT":1,"WRONG_ACCOUNT":1,"UNEXPLAINED":1},
                  "category_accuracy": 0.86, "resolution_usefulness": 0.72,
                  "ai_lift": 0.19, "budget_exceeded": 0 },
  "throughput": { "records_per_sec": 640, "wallclock_s": 0.33, "wallclock_with_ai_s": 14.1 },
  "cost": { "llm_usd": 0.21, "llm_usd_per_exception": 0.05, "tokens_in": 38200, "tokens_out": 4100 },
  "determinism": { "replay_hash_match": true }
}
```

---

## 5. Anti-cherry-pick guarantees

1. **One command reproduces everything:** `make bench` → generates the dataset from a committed seed, runs, scores, prints the scorecard. A judge runs the exact same thing.
2. **CI runs it on every commit** and uploads the scorecard + HTML report as a build artifact; a bot comments the headline metrics on the PR. The number has a history, visible in the repo.
3. **Determinism test:** `arbiter run` twice → identical event hash chain, or CI fails.
4. **Regression gate:** if `auto_match_rate` drops more than 2 points or `false_match_rate` rises above 1.5%, CI fails.
5. **The dataset is adversarial by construction** — it contains anomalies specifically designed to be hard. We report the number _on that_, not on an easy batch.
6. **`--no-ai` numbers are always reported alongside** — you can see exactly what the deterministic core does without the LLM, so the AI's contribution is measured, not assumed.
7. **Failure cases are shown, not buried:** the demo script deliberately opens the `UNEXPLAINED` exception and says "Arbiter could not resolve this one — here's what it knows and what it's missing."

---

## 6. Honest limitations of this methodology (stated up front)

| Limitation | Impact | Mitigation / disclosure |
|---|---|---|
| Synthetic data is cleaner than production | Real-world match rate will be lower | Disclosed in the README; difficulty dial (J5) shows degradation; roadmap includes a real anonymized dataset |
| We wrote both the generator and the matcher | Risk of "teaching to the test" | Anomaly catalog is derived from documented real-world reconciliation exceptions (sources in [01](01-market-and-thesis.md)), not from what the matcher happens to handle; `--no-ai` baseline and category accuracy < 100% show it's not gamed |
| `resolution_usefulness` needs human judgment for equivalence | Slightly subjective | Validated LLM-as-judge protocol ([doc 12 §6.1a](12-agent-design.md)): binary reference-based rubric, cited evidence, judge ensemble, human-validated to Cohen's κ ≥ 0.6, κ reported; borderline calls logged |
| Small N (50–500) | Wide confidence intervals on rates | Report N and run multiple seeds; `bench --seeds 10` aggregates |
| One processor (Razorpay) shape | Generality unproven at scale | `gst-2b.yaml` spec + a second processor shape as evidence of the engine's spec-driven design |
