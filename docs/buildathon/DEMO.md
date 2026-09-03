# 3-Minute Demo Script

The canonical walkthrough. Numbers here match `make bench` / `arbiter attack` /
`arbiter agent-bench` on `datasets/seed` as of the current build. Deprecates the
older narrative in [`docs/24`](../24-demo-and-pitch.md).

**Fallback:** the hosted cockpit at `https://arbiter-cockpit.vercel.app` runs the
frozen snapshot with zero setup — use it if a live run misbehaves.

---

## 0:00–0:20 — The problem

> "Finance teams don't have a shortage of reconciliation software. They have a
> shortage of *trust*. The dangerous number isn't the transaction that didn't
> match — it's the one the system matched *wrong*, that nobody looked at."

Show the cockpit overview:

```
97.2% VERIFIED    ₹12.4L TIED    ₹41.9K OPEN    2 HIGH RISK
```

## 0:20–0:50 — Reconcile

> `arbiter run --spec razorpay-settlement.yaml --dataset datasets/seed`

Show the streaming view: passes tick by, matched count climbs, then the
exceptions open.

Land on the scorecard:

```
auto-match     93.8%      false-match    0.0%
precision      100%       ₹ coverage     100%
```

> "The deterministic engine did the matching and the money math — no LLM in that
> path, fully reproducible. Then the agent investigated only the ambiguous
> residue."

## 0:50–1:40 — One investigation, end to end

Open an exception the agent investigated. Show the **structured chain**, not raw
JSON:

```
01  PLAN        determine why settlement …B5 is short by ₹2,773.96
02  EVIDENCE    decomposition_detail · similar_exceptions
03  REASON      the shortfall matches one payment settled a day later
04  PROPOSAL    TIMING · grounded confidence 78% (model said 85%)
05  VERIFICATION   independent verifier: the cited date does not prove a late settlement
06  SAFETY      R3 · ESCALATE  [verifier_rejected · confidence_in_uncertain_band]
07  OUTCOME     escalated to a human
```

Click **"Why didn't Arbiter resolve this?"**:

> "Two things had to line up and one didn't. The model was **confidently wrong** —
> it self-rated 85%. The independent check caught it. Arbiter refused to turn a
> wrong answer into a financial decision. ₹0 changed."

**This is the strongest 20 seconds of the demo. Do not skip it.**

## 1:40–2:05 — Attack it

> `arbiter attack --spec razorpay-settlement.yaml --dataset datasets/seed`

```
12 contained · 0 unsafe · ₹0 unaccounted
```

> "Twelve deliberate tamperings — altered amounts, a fabricated settlement ID, a
> prompt injection in a bank narration. Not one produced a confident clean tie.
> The injection never reached the model — it was quarantined at ingest."

Key line:

> **"Financial records are data. Never instructions."**

## 2:05–2:30 — The benchmark

> `arbiter agent-bench --client oracle --seeds 16`

```
task completion 100%   ·   escalation recall 100%   ·   0 unsafe   ·   +44% lift
```

> `arbiter agent-bench --client reckless --seeds 16`

```
0 material unsafe   ·   confident-wrong proposals: half escalated, half shown to a
human who rejects them   ·   Arbiter never auto-resolves
```

> "We benchmark the agent's *process*, not just its answers — and we benchmark
> safety separately from usefulness. A useful agent that escalates too much is
> fine. An agent that resolves something it shouldn't is not. That number is 0."

## 2:30–2:45 — AI off

> `arbiter run --no-ai`

```
matching ✓   decomposition ✓   scorecard ✓   replay ✓   audit ✓
financial reconciliation: OPERATIONAL
```

> "Turn the AI off entirely and the control system still stands."

## 2:45–3:00 — Close

> "Arbiter doesn't ask you to trust the model. It assumes the model can be
> wrong, and makes that failure observable, bounded, and recoverable — before a
> human ever clicks accept."

Stop.

---

## Judge Q&A cheat-sheet

| Question | Answer |
|---|---|
| Why AI at all? | The deterministic core handles the obvious majority. AI is used only where rules can't confidently explain the exception, to cut human investigation time — not to determine financial truth. |
| What if it hallucinates? | Citations must ground to real records, pass a deterministic arithmetic check, survive an independent model, and pass the Safety Kernel. Unsupported → escalate. |
| Can the AI move money? | No. Tools are read-only. A human `RESOLUTION_APPLIED` event is the only way a proposal takes effect. `test_control_invariants.py` proves it. |
| Provider down? | The deterministic reconciliation continues; the affected exception escalates. |
| Real data? | No — reproducible synthetic. We disclose that everywhere. Real-world validation is the #1 open item. |
| Production-ready? | The engineering is mature for a prototype. We have not validated customer match rates or load at the stated scale, and we don't claim to. |
