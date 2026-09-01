# 24 — Demo & Pitch Script

_The 5-minute pitch video and the judge walkthrough. The bar says "one cherry-picked match proves nothing" — the demo is built to be the opposite of a cherry-pick._

---

## 1. The 5-minute pitch video (script, ~4:45)

### [0:00–0:30] The problem, concretely
> "This is a real Razorpay settlement report, a real bank statement, and an order ledger for one month of a D2C brand. Three files, same money, three different shapes. Somebody on the finance team has to prove they agree — and explain every place they don't — before the books close. Today that's days of spreadsheet work, and they still don't fully trust the result. The 2026 consensus is that verification, not generation, is the bottleneck. Reconciliation is exhibit A."

### [0:30–1:15] What Arbiter does — one command
> `arbiter run --spec razorpay-settlement.yaml`
- Screen: the SSE run view. Passes tick by (exact → tolerant → subset → fuzzy). Matched count climbs. Then: "18 exceptions" — and the agent investigations start streaming their plan → conclusion.
- Land on the scorecard: **"96.4% auto-tied, ₹1,90,000 across 18 exceptions still need a human."**
> "Deterministic engine did the matching and the money math — no LLM in that path, fully reproducible. Then an agent investigated only the ambiguous residue."

### [1:15–2:15] The honest benchmark
> `arbiter bench`
- Screen: the full scorecard. **Point at the false-match rate: 0.6%.**
> "Every vendor claims 90 or 99 percent. Nobody publishes their false-match rate on data you can check. This dataset is adversarial — it has duplicates, split settlements, fee drift, chargebacks, a timing straddle, even a prompt-injection attempt in a payment note. The answer key ships with it. Run `make bench` yourself and you get this exact number."
- `arbiter bench --ablate` → the table: `--no-ai` 88.1% · Haiku 92.4% · Opus 96.4%, with cost and latency.
> "That's the AI-judgment call, shown with data: the deterministic core alone gets 88%. The agent is worth 8 points — measured, not assumed. Turn it off and the system still works."

### [2:15–3:00] One exception, end to end
- Open a `TIMING` exception in the evidence drawer. Three record cards. The identity equation with the residual. The agent's explanation with clickable evidence refs. The `carry_forward` proposal and the draft rule.
> "Every number traces to its source in one click. The agent proposes — it never decides. I accept."
- Then open the **escalated** one: an orphan bank credit.
> "This one it couldn't resolve — and it didn't guess. It escalated with exactly one question: 'is there a second bank account feeding this?' That's the product — it collapses a 20-minute investigation into a yes/no."

### [3:00–3:45] It gets better
- `arbiter run` cycle 2, then cycle 3 (rules carried forward).
- Screen: the cycle-trend sparkline: **85% → 93% → 97%**, human-touch count 30 → 12 → 5.
> "When I resolve an exception, Arbiter drafts a durable rule. Month three is measurably better than month one. No competitor shows you a rising curve — they show you a static claim."

### [3:45–4:15] Trust & audit
- `arbiter verify <run-id>` → "event chain intact, 1,214 events."
- `arbiter memo <run-id>` → the Close Memo PDF: totals tied, every exception + resolution, the proposed journal entries, the hash.
> "This is what a controller sends their auditor. Tamper-evident. Replayable. The whole run reconstructs from its log."

### [4:15–4:45] Why this architecture
> "Arbiter is a hybrid-orchestration agent: a deterministic skeleton for anything touching money, one bounded agentic investigation loop for the judgment calls, every AI output gated. That's not timidity — it's the only responsible way to put an LLM near the books, and it's exactly what this track asked for: the right tool in the right place, and the honesty to measure whether it earned its place. The repo's open. The benchmark's reproducible. Thanks."

---

## 2. Judge walkthrough (hands-on, ~10 min)

```bash
git clone <repo> && cd arbiter && make demo
```
1. **Cockpit opens** (< 3 min). Scorecard: real number, not 100%.
2. **Queue:** sorted by ₹ impact. `j`/`k` through it. `e` to expand one.
3. **Evidence drawer:** click an evidence-ref → watch it highlight the field in the record card. Read the identity equation.
4. **Accept a resolution** → see the consequence preview ("97.2% → 98.6%") → `arbiter run` again → watch it move.
5. **The injected note:** filter `category = SECURITY_REVIEW` → show it was quarantined and never sent to the agent.
6. **Terminal:**
   - `arbiter bench` — the full scorecard, both halves (matching + agent).
   - `arbiter bench --calibration` — the reliability diagram, ECE.
   - `arbiter run --no-ai` — same pipeline, deterministic baseline.
   - `arbiter replay <id>` — byte-identical.
   - `arbiter verify <id>` — hash chain intact.
   - `arbiter explain <exception-id>` — the drawer, as text.
7. **`docs/`:** open `11` (the self-review), `12` (the agent), `08` (why it might not sell). Point: every decision is written down and defended.

---

## 3. Anticipated questions & answers

| Q | A |
|---|---|
| "Is this really an agent or just a pipeline with an LLM call?" | "Hybrid orchestration — [ADR-0004](adr/0004-hybrid-orchestration.md). The skeleton is deterministic; the agent runs a real loop: plans an investigation, gathers evidence with tools, tests its hypothesis, and decides on its own whether to conclude or escalate. You saw it stream. It's evaluated as an agent — task-completion, tool-use accuracy, grounding, escalation recall." |
| "Your data is synthetic — why should I believe the number?" | "The generator injects failure modes from documented real-world reconciliation exceptions, with a labeled answer key, and a difficulty dial that shows where accuracy drops. The `--no-ai` baseline and a sub-100% category accuracy show it isn't gamed. And I'll run your real export right now if you have one." |
| "What happens when the LLM hallucinates?" | "Three layers: every claim needs an evidence-ref or it can't be made; confidence is calibrated so a weak proposal looks weak; and the tools are proposal-only, so even a fully hijacked agent can't move money or confirm a match. Hallucination rate is a tracked metric — target ≤ 2%." |
| "Why not just use BlackLine / Numeric?" | "Those are single-rail or six-figure-and-six-months. Arbiter is processor-neutral, ties every rail with one audit trail, and its accuracy is reproducible by a stranger in one command. Different buyer, different trust model." |
| "Can it post the journal entries?" | "It proposes them in the Close Memo. Posting is deferred on purpose — moving from 'decide' to 'act' on money is a trust and liability leap that needs real customer trust first. [doc 08 R8](08-why-it-might-not-sell.md)." |
| "What broke while building it?" | "It's in `BUILD-LOG.md` and `KNOWN-FAILURE-MODES.md` — including cases the agent still gets wrong and how the system contains them. The determinism test caught a sort-order bug on day 6; the escalation threshold was over-cautious until I tuned it against the escalation-precision metric." |

---

## 4. What NOT to do in the demo

- Don't hide the exceptions or the false-match rate. They're the point.
- Don't run a tiny cherry-picked batch. Run 800.
- Don't claim production-readiness beyond what [doc 13 §8](13-production-readiness.md) says is done.
- Don't oversell the AI. "Measured 8-point lift, opt-in, off by a flag" is more credible than "AI-powered everything."
- Don't skip the escalated exception. "It knew what it didn't know" is the most memorable 20 seconds.
