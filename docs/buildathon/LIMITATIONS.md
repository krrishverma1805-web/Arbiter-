# Limitations — stated deliberately

If a judge asks "what are you hiding?", this is the answer. Nothing here is a
secret; it's all in the README, the code comments, and `docs/CLAIMS.md`.

## Not validated

| # | Limitation | Why it matters | What would fix it |
|---|---|---|---|
| 1 | **No customer.** Zero design partners, zero pilots, zero revenue. No real bank statement has ever been reconciled. | Every accuracy number is on synthetic data Arbiter's own generator produced. | 10 controller conversations; 3 anonymised real reconciliations. |
| 2 | **Agent accuracy on a live frontier model is not benchmarked** over the full corpus. One live gpt-4o investigation is captured (the verifier caught a bad proposal). | The scripted `agent-bench` clients bound the *harness*, not a real model's judgment. | `ANTHROPIC_API_KEY` in CI + `agent-bench --client anthropic --seeds 16`. |
| 3 | **Production scale is not load-tested** (stated target: 500 concurrent orgs, 10k runs/day). | The queue / worker / HPA architecture exists; the evidence it holds does not. | A load test at that target. |
| 4 | **Real-world match rates will be lower** than the synthetic 93.8%. Real bank data is messier than any generator. | The headline number is an upper bound. | Point 1. |

## Scope boundaries (v1 non-goals, on purpose)

* No journal-entry posting into an ERP — Arbiter proposes, a human posts.
* No live processor / bank / ERP connectors — batch-file ingestion only.
* No multi-entity consolidation, no fraud detection, no cash forecasting.
* OCR for scanned PDFs (no text layer) raises a clear error — not built.
* Auth is a static bearer-token principal table — no SSO, no key rotation.
* No SOC 2 — that needs a company.

## Known behavioural constraints

* Dates outside **2015–2035** are quarantined at ingest as corrupt/manipulated —
  this would reject legitimately old historical data.
* A foreign-currency row with **no configured FX rate** is quarantined, never
  guessed.
* The deterministic **counterfactual check** covers the common hypothesis
  categories (rounding, fee/tax drift, timing straddle, duplicate,
  over/short settlement); a category it doesn't model gets `PROPOSE`, never
  `SAFE`.
* A confidently-wrong agent whose wrong category is residual-compatible reaches a
  green `PROPOSE` ~half the time in the adversarial benchmark — a human rejects
  it (Arbiter never auto-resolves), and the 2nd-model verifier (not in the
  scripted run) catches more of these live.

## What is genuinely strong

The deterministic core, the honest benchmark, the Safety Kernel, the Attack
Arbiter harness, the replayable audit trail, and the fact that **the AI has no
authority over financial truth** — it investigates, deterministic code decides
how its output is presented, and a human confirms.
