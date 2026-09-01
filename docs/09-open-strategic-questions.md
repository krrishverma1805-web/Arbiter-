# 09 — Open Strategic Questions

_The decisions that are genuinely yours to make. Each has a recommendation and the reasoning behind it, but the call is yours and it changes what gets built._

---

## Q1 — Which single loop does the Buildathon demo close?

**Options:**
- **A. Multi-rail settlement reconciliation** (Razorpay + optional 2nd processor ↔ bank ↔ order ledger). _Recommended._
- B. GST-2B tax-line matching (purchase register ↔ GSTR-2B ↔ books).
- C. Bank-to-book reconciliation (bank statement ↔ GL cash account).
- D. Forward cash forecaster.

**Recommendation: A**, with B shipped as a second `spec` file to prove the engine is loop-agnostic.

**Why:** judge legibility (Razorpay _is_ settlements — no domain lecture needed), data standardization (one processor schema), the richest real exception taxonomy, and it's not TAM-capped to India. D is not a reconciliation loop and is only credible _downstream_ of a reconciled ledger — it's the "what's next" slide, not the demo. C is the most commoditized. B is a strong India play but has worse unit economics (see [08](08-why-it-might-not-sell.md) R11) — better as proof-of-generality than as the headline.

**What changes based on your answer:** the reference spec, the synthetic generator's primary scenario, the demo script, and which competitor set you're most directly measured against.

---

## Q2 — Open source, closed, or open-core?

**Options:**
- **A. Open-core:** engine + benchmark + CLI + specs are MIT/Apache; hosted cockpit, connectors, and team features are commercial. _Recommended._
- B. Fully open source, everything.
- C. Closed, standard SaaS.

**Recommendation: A.**

**Why:** the engine being inspectable directly attacks the trust-monopoly and unknown-startup problems ([08](08-why-it-might-not-sell.md) R1). A published, runnable benchmark only has teeth if the thing it benchmarks is open. It earns a small team disproportionate mindshare (the dev-tools playbook). And it keeps a commercial surface (hosting, connectors, collaboration) so it's not purely a donation.

**What changes:** licensing headers, repo hygiene expectations (a fully-open project is judged on contributor experience), and whether the pitch leads with "product" or "project."

**Sub-question Q2a:** For the Buildathon specifically, is the repo public from day one, or public at submission? _Recommendation: public at submission, developed in the open if you're comfortable — "code speaks louder than your resume" rewards visible history._

---

## Q3 — What is the AI's job, exactly — and is it load-bearing or garnish?

The architecture ([04](04-technical-architecture.md) §3) confines the LLM to adjudicating ambiguous exceptions. Two ways to feel about that:

- **A. It's load-bearing and that's the honest amount.** The measured "AI lift" (category accuracy with vs. without) is the proof. If lift is ~15–20 points and resolution proposals are ~70% useful, the AI is doing real work in the one place judgment is actually needed. _Recommended framing._
- B. Push the AI further — let it drive the matching strategy, propose spec changes autonomously, generate the synthetic scenarios. More impressive-sounding, more risk, weaker "AI Judgment" story.

**Recommendation: A.** The Buildathon's "AI Judgment" criterion explicitly rewards _"opt for deterministic solutions where AI is unnecessary."_ A tightly-scoped, measured AI role is the stronger submission than a maximalist one. But you must _measure and show_ the lift — if you can't demonstrate the AI earns its place, cut it and ship the deterministic core proudly.

**Open sub-question Q3a:** Should the agent also be allowed to _draft synthetic anomaly scenarios_ (adversarial self-play against its own matcher)? Interesting, impressive, but risks the "teaching to the test" critique ([07](07-evaluation-and-benchmark.md) §6). _Lean no for v1; mention as future work._

---

## Q4 — Who is the design-partner user for the pitch narrative?

**Options:**
- **A. Controller / finance lead at a 30–100 person multi-rail D2C or marketplace business.** _Recommended._
- B. CA firm / outsourced controller serving many SMBs.
- C. Finance engineer at a fintech/platform building on a ledger.

**Recommendation: A** as the primary persona in the demo and docs; **B** as the "and it also scales this way" note. A is the most relatable in a 5-minute pitch and the pain is visceral and specific (COD remittance + 2 processors + marketplace payouts + GST). B is arguably the better _business_ but a worse _story_.

**What changes:** the demo dataset scenario, the cockpit's default view, the language in the README, the ROI framing.

---

## Q5 — How ambitious is the accuracy claim, and how do you handle the gap to production?

**Options:**
- **A. Report the real synthetic-data number with the false-match rate and a visible "production will differ" asterisk; make the learning-curve (85→97 over cycles) the headline instead of a single number.** _Recommended._
- B. Tune the demo dataset until the number is ~97%+ and lead with that.
- C. Get a real anonymized dataset from someone before submission and benchmark on that.

**Recommendation: A**, and attempt **C** if you can find even one friendly business with a Razorpay export + bank statement. B is the trap — a suspiciously high number on self-generated data invites exactly the "one cherry-picked match proves nothing" critique the bar is warning about.

---

## Q6 — Software vs. managed service vs. infrastructure (the R10 question)

**Recommendation:** open-core (Q2-A) resolves most of this: **infrastructure/trust via the open engine, software via the hosted cockpit sold to the controller.** Explicitly _not_ the managed "we reconcile for you" service — it doesn't scale for a small team and competes with cheap labor.

**Still open:** whether the first dollar comes from the hosted cockpit (controller SaaS) or from paid connectors/support (infra). Probably the cockpit; revisit after the first 5 users.

---

## Q7 — How much to lean into Razorpay's own ecosystem?

For the Buildathon, using the Razorpay settlement report format and an optional Razorpay Settlements API ingest path is clearly right — it's the track's home turf.

**The question:** does the _product_ position as "Razorpay-native" (deep integration, co-marketing potential, acquisition target) or "processor-neutral" (bigger TAM, Razorpay is just one source)?

**Recommendation:** build processor-neutral (the spec design already is), but make the Razorpay path the most polished one for the submission. Neutral architecture, Razorpay-first demo. This keeps both the "Razorpay could acquire this" and the "this is a real independent product" options alive.

---

## Q8 — Post-Buildathon: what is this?

**Options:**
- A. A funded startup attempt.
- **B. An open-source project you maintain + a portfolio centerpiece that gets you the Razorpay role (or similar).** _Recommended given the stated goal._
- C. A prototype to hand off / an acqui-hire conversation starter.

**Recommendation: B.** The stated goal is to win the Buildathon and boost your skills/credibility. Optimize for that: a genuinely excellent, honest, well-engineered artifact that demonstrates senior-level judgment. If it gains OSS traction, A and C stay open. Don't contort the build toward fundability at the cost of the demo.

---

## Q9 — Scope: how much UI vs. how much engine?

**The tension:** the engine + benchmark is where the "senior engineer" signal is; the cockpit is where the "this is a real product" signal is. Limited time forces a split.

**Recommendation:** **60% engine/benchmark, 40% cockpit.** Non-negotiable engine deliverables: deterministic multi-pass matcher, settlement decomposition, exception taxonomy + classifier, the one AI step (measured), event log + replay, `arbiter bench` with the full scorecard, the adversarial generator. Cockpit: the three surfaces from [05](05-design-doctrine.md) done well, even if read-mostly, with the evidence drawer as the one truly polished piece. A beautiful cockpit on a shallow engine loses this track; a deep engine with a competent cockpit wins it.

---

## Q10 — Naming and framing of the exception list

Small but real: the track says "the exceptions it could not resolve." Is Arbiter's list framed as **failures** ("couldn't do these") or as **the deliverable** ("here's your prioritized work, pre-diagnosed")?

**Recommendation:** the deliverable framing, consistently — in the UI (amber, not red), the CLI, the docs, the pitch. "Arbiter resolved 208 of 214 and handed me the 6 that need judgment, each with the evidence and a proposed fix" is a stronger sentence than "Arbiter failed on 6."

---

## Decisions needed before writing code

| # | Question | Blocks | Default if you don't decide |
|---|---|---|---|
| Q1 | Which loop | the reference spec, the generator | A (multi-rail settlement) |
| Q2 | OSS / closed / open-core | licensing, repo hygiene, pitch framing | A (open-core) |
| Q3 | AI scope | the agent package, the eval design | A (bounded, measured) |
| Q9 | Engine vs UI split | the build schedule | 60/40 engine-heavy |

The rest (Q4–Q8, Q10) shape the _narrative_ and can be finalized while building.
