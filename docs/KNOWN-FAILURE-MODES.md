# Known Failure Modes

_Where Arbiter's agent is weak, why, and how the system contains it. Honest by policy — this file is populated with **real** cases from `arbiter bench` runs as the build progresses, not hypotheticals._

The Buildathon's Failure Recovery criterion asks to see what broke and how it was handled. [`BUILD-LOG.md`](BUILD-LOG.md) covers build-time failures; this file covers the **agent's own** failures on the task.

---

## Containment model (why a wrong proposal is not a wrong ledger)

1. Every agent proposal is **proposal-only** — it cannot confirm a match or move money ([ADR-0001](adr/0001-deterministic-core-ai-at-the-boundary.md)).
2. Every proposal is **badged AI-generated** and requires a human accept/edit/reject.
3. Confidence is **calibrated** ([doc 12 §6.2](12-agent-design.md)) so a shaky proposal *looks* shaky.
4. The **escalation-recall** metric measures how often the agent correctly says "a human needs this."
5. Everything is **replayable** — a bad proposal can be traced to the exact evidence and prompt.

---

## Catalog

**Why this table is not yet populated with agent cases.** The investigation agent
runs against the Anthropic API, and no `ANTHROPIC_API_KEY` is available in the dev
or CI environment. The offline suite exercises the agent through `ScriptedClient` /
`RecordedClient` (deterministic, no network), which proves the *loop* — budgets,
fencing, schema validation, replay — but cannot surface real reasoning failures.
Those come from the **`nightly-live` CI job** (`pytest -m live`, schedule-only),
which needs the repo secret set. Each real failure it turns up gets an `F-0N`
entry here with the trajectory, the ground truth, and the containment that caught it.

Until then, the containment model above is what bounds a bad proposal, and the
agent scorecard in `arbiter bench` (task-completion, hallucination rate,
escalation precision/recall) is the aggregate measure.

### Observed on the deterministic side (not the agent)

- **`SPLIT_SETTLEMENT` is detected but not auto-categorised.** On a 150-record
  normal batch, `arbiter bench` detects 6 of 7 anomalies but `category_accuracy`
  is 0.50: the split-settlement residual opens as `UNEXPLAINED` (a large residual
  the base spec has no rule for), so it is *found* but not *named*. This is by
  design — a first-occurrence novel shape is a human call — and it is exactly what
  the learning loop closes: resolving one as `SPLIT_SETTLEMENT` drafts a rule that
  names the shape on every later close (`arbiter cycle-demo`). Before 2026-09-02
  the `SPLIT_BATCH` anomaly produced no residual at all (a `datagen` bug, see
  BUILD-LOG) and was the anomaly `detected_anomalies` always missed.
- **Sub-tolerance variances never open an exception.** `GST_ROUND` (±1–2 paise)
  and small `FEE_DRIFT` land inside the ₹1.00 rounding band, so they don't appear
  in the exception list. The matcher's tolerance band is doing its job — but the
  ground-truth anomaly count and the exception count legitimately differ. The
  matching scorecard measures this honestly via `false_match_rate` (0.0 — nothing
  is mis-tied) rather than raw recall.

| # | Case | Symptom | Root cause | Containment that caught it | Fix / mitigation |
|---|---|---|---|---|---|
| F-01 | _awaiting `nightly-live`_ | | | | |

<!--
Template:

### F-0N — <short title>
**Scenario:** <the exception, the data shape>
**What the agent did:** <proposal / escalation, confidence>
**What was correct:** <ground truth>
**Why it failed:** <ambiguous evidence / anchored early / missing history / genuinely undecidable>
**How it was contained:** <calibration kept confidence low / escalation-recall flagged it / human gate>
**Change made:** <prompt loop step / threshold tune / new deterministic rule / accepted as inherent limit>
-->

---

## Inherent limits (cases where no fix is appropriate — the honest answer is "a human decides")

- **Genuinely undecidable exceptions.** A ₹5,000 orphan bank credit with no reference, no matching order amount, no counterparty history. The correct behavior is `ESCALATE` with "what's missing," not a guess. Measured by escalation recall, not category accuracy.
- **First occurrence of a novel pattern.** The learning loop needs one human resolution before it can auto-handle a new exception shape. Month 1 of a new customer has more escalations by design.
- **Upstream data errors.** If the bank statement itself is wrong (bank restated a credit), Arbiter surfaces the discrepancy but cannot know which side is truth.
