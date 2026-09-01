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

## Catalog (to be filled from real runs)

| # | Case | Symptom | Root cause | Containment that caught it | Fix / mitigation |
|---|---|---|---|---|---|
| F-01 | _pending M3_ | | | | |

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
