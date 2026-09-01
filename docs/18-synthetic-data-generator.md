# 18 — Synthetic Data Generator (`datagen`)

_You cannot claim measured accuracy without labeled data. `datagen` produces realistic, adversarial, fully-labeled reconciliation batches. It is as much a deliverable as the engine._

---

## 1. Goals

1. **Realistic** — the distributions (order values, method mix, fee tiers, refund/chargeback rates, settlement timing) match a real Indian D2C / marketplace merchant closely enough that the match rate on it is informative.
2. **Adversarial** — it injects the hard exceptions on purpose, at controllable rates, from a documented catalog derived from real-world reconciliation failure modes ([doc 15 §3](15-domain-model-reconciliation.md)).
3. **Labeled** — every record's true match group and every injected anomaly's true category + resolution are in `ground_truth.json`. Every agent-relevant exception also gets a labeled ideal trajectory.
4. **Reproducible** — `(scenario, records, seed)` fully determines the output.
5. **Honest** — a `--difficulty` dial and scenario presets let a judge see where accuracy degrades, and the README discloses the synthetic-vs-production gap ([doc 08 R7](08-why-it-might-not-sell.md)).

---

## 2. Output

```
datasets/<name>/
├── razorpay_recon.csv        # processor line items (real fetch-recon schema — doc 11 §5)
├── bank.csv                  # bank statement credits (+ noise lines)
├── ledger.csv                # order records (+ refunds)
├── ground_truth.json         # the answer key (§5)
├── trajectories.json         # labeled ideal investigation paths for agent eval (doc 12 §6)
└── manifest.json             # scenario, seed, generator_version, param values, injected-anomaly counts
```

---

## 3. The generative model

### 3.1 Scenario presets

| Preset | Shape | Order value (₹, lognormal) | Method mix | Refund rate | Chargeback rate | Processors |
|---|---|---|---|---|---|---|
| `d2c` | D2C brand on Shopify | μ≈ln(1400), σ≈0.7 | UPI 55% / card 30% / netbanking 10% / wallet 5% | 6% | 0.3% | Razorpay (+ optional 2nd) |
| `marketplace` | multi-seller marketplace | μ≈ln(900), σ≈0.9 | UPI 65% / card 25% / rest 10% | 9% | 0.5% | Razorpay + COD remittance file |
| `saas` | B2B SaaS subscriptions | μ≈ln(6000), σ≈0.5 | card 70% / netbanking 25% / UPI 5% | 2% | 0.2% | Razorpay, intl card 15% |

### 3.2 Temporal model

- Orders arrive via a non-homogeneous Poisson process over the period (weekday/weekend and time-of-day intensity; a payday bump).
- Payment capture: same day for UPI/card, 0–1 day lag for netbanking.
- **Settlement batching:** processor batches captured payments daily at a cutoff; settlement `settled_at` = capture date + T+2 **working days** (a committed 2026 India bank-holiday calendar; weekends skipped).
- **Bank credit** `value_date` = `settled_at` + {0 with p=0.9, 1 with p=0.1} (bank posting lag).
- Period boundary is deliberately placed so ~T+2 worth of settlements straddle it → natural `TIMING` exceptions even before injection.

### 3.3 Fee model

Per item: `fee = round(gross × mdr_rate(method, network))`, `tax = round(fee × 0.18)`.
`mdr_rate`: UPI 0% (below threshold) or a flat platform fee; card 1.6–2.0% by network; netbanking flat ₹15–20; wallet ~1.9%; intl card 3.0–3.5% + FX markup. Rates drawn from published Razorpay ranges ([Razorpay: MDR vs platform fees](https://razorpay.com/blog/upi-charges-explained-mdr-vs-platform-fees/), [Razorpay: international charges 2026](https://razorpay.com/blog/international-payment-gateway-charges-india-2026)).

### 3.4 Statistical realism validation

`datagen validate <name>` checks the generated batch against target distributions (KS test on order value, χ² on method mix, settlement-lag histogram) and fails if any drifts beyond tolerance — so "realistic" is enforced, not asserted.

---

## 4. The anomaly injection catalog

Each anomaly: injected at rate `r` (per scenario defaults, overridable), recorded in `ground_truth.json` with the true category and resolution, and tagged by whether it is deterministically resolvable.

| Anomaly | How it's injected | True category | True resolution | Det.-resolvable? |
|---|---|---|---|---|
| `DUP_EXPORT` | duplicate a `payment` line (overlapping export windows) | `DUPLICATE` | `void_duplicate_of(id)` | partial (dedup finds it; void needs human) |
| `PARTIAL_CAPTURE` | capture 60–95% of order total | `PARTIAL_PAYMENT` | `route_to_human` | no |
| `OVER_CHARGE` | second full payment for one order | `OVER_PAYMENT` | `raise_dispute` (refund) | no |
| `SPLIT_BATCH` | move one order's payment to the next settlement batch | `SPLIT_SETTLEMENT` | `accept_variance` (N:1 match) | yes (subset pass) |
| `FEE_DRIFT` | apply `mdr_rate × (1 + δ)`, δ ∈ [3%, 12%] | `FEE_DEDUCTION` + overcharge flag | `flag_overcharge` | yes (fee model) |
| `GST_ROUND` | compute GST per-item then also batch-round → ±₹1–3 residual | `ROUNDING` | `accept_variance` | yes |
| `MISSING_UTR` | blank the bank narration UTR | `MISSING_UTR` | fuzzy match → propose or escalate | partial |
| `TIMING_STRADDLE` | shift a batch's `settled_at` across the period boundary | `TIMING` | `carry_forward` | yes |
| `CHARGEBACK_LATE` | add a `debit` adjustment in a later batch referencing an earlier `payment_id`, + a ₹ fee | `CHARGEBACK` | `raise_dispute` / `route_to_human` | partial |
| `FX_SLIP` | settle an intl payment at order-rate ± 1.5% | `FX_DIFFERENCE` | `attribute_to(FX gain/loss)` | yes |
| `WRONG_ACCT` | mark a batch `settled=true` but omit its bank credit | `WRONG_ACCOUNT` | `route_to_human` | no |
| `ORPHAN_CREDIT` | add a bank credit with no processor batch (e.g. a manual transfer) | `UNEXPLAINED` → escalate | `request_data` / `route_to_human` | no |
| `REFUND_NET` | net a refund against gross in one line instead of a separate `debit` | `REFUND_NETTING` | `attribute_to(Sales Returns)` | yes (identity) |
| `INJECTION_NOTE` | put an injection string in one payment's `notes` | `SECURITY_REVIEW` | `route_to_human` | yes (scanner) |
| `UNMAPPED_ORDER` | reference an `order_id` absent from `ledger.csv` | `UNMAPPED_ORDER` | `request_data` | partial |

The catalog is intentionally broader than what the matcher handles well, so `category_accuracy < 100%` is expected and the honest number is reported ([doc 07 §6](07-evaluation-and-benchmark.md)).

### 4.1 Anti-"teaching to the test"

- The anomaly definitions are derived from the domain model ([doc 15](15-domain-model-reconciliation.md)) and cited real-world sources — **not** reverse-engineered from what the matcher happens to catch.
- The person/prompt writing the matcher rules and the person/prompt writing the anomaly injector are kept as separate modules with separate specs; a code review checklist item is "does this rule exist only to pass a specific anomaly?"
- `--difficulty hard` raises injection rates and adds compound anomalies (a `TIMING` batch that also has `FEE_DRIFT`) — the number drops, and that drop is shown.
- The real-dataset attempt ([doc 09 Q5](09-open-strategic-questions.md)) is the ultimate check.

---

## 5. `ground_truth.json` schema

```json
{
  "generator_version": "0.4.0",
  "scenario": "d2c", "seed": 42, "records": 800, "period": ["2026-08-01","2026-08-31"],
  "true_matches": [
    { "group_id": "gt_001", "settlement_utr": "UTR...", "bank_record_id": "bank_3",
      "processor_record_ids": ["rp_10","rp_11","..."], "ledger_order_ids": ["ord_9","..."],
      "expected_net_minor": 95420000, "clean": true }
  ],
  "anomalies": [
    { "id": "an_07", "kind": "FEE_DRIFT", "record_ids": ["rp_233"],
      "true_category": "FEE_DEDUCTION", "true_resolution": {"action": "flag_overcharge", "amount_minor": 4120},
      "deterministically_resolvable": true, "dollar_impact_minor": 4120 }
  ],
  "distribution_report": { "order_value_ks_p": 0.62, "method_mix_chi2_p": 0.44, "settlement_lag_ok": true }
}
```

---

## 6. `trajectories.json` (agent eval labels)

For each anomaly that requires investigation, an **ideal trajectory**:

```json
{ "exception_kind": "WRONG_ACCT",
  "ideal_path": [
    {"step": "plan", "expect_goal_mentions": ["settled true", "no bank credit"]},
    {"step": "tool", "tool": "decomposition_detail", "why": "confirm the batch is internally consistent"},
    {"step": "tool", "tool": "counterparty_history", "why": "check if this settlement account differs historically"},
    {"step": "decide", "terminal": "escalate", "reason": "evidence_exhausted",
     "question_should_mention": ["another bank account"]}
  ],
  "acceptable_alternatives": [ "... " ],
  "anti_patterns": ["concluding DUPLICATE", "proposing a match without a bank record"] }
```

`arbiter bench` scores real trajectories against these for tool-use accuracy and trajectory efficiency ([doc 12 §6](12-agent-design.md)).

---

## 7. CLI

```bash
arbiter gen --scenario d2c --records 800 --seed 42 --out datasets/d2c-aug
arbiter gen --scenario marketplace --records 2000 --difficulty hard --seed 7
arbiter gen --cycles 3 --scenario d2c --seed 42        # 3 consecutive monthly batches for the learning-loop demo
datagen validate datasets/d2c-aug                       # distribution checks
```

The committed `datasets/seed/` is a small (`--records 120`) `d2c` batch with a fixed seed, including exactly one of each anomaly — small enough to read, complete enough to exercise every path, and the default for `make demo`'s fast mode.
