# 01 — Market Research & Thesis

> _"The 2026 builder consensus: verification capacity, not generation speed, is the bottleneck. Reconciliation, settlement and forecasting are still done by hand."_ — Razorpay Buildathon, AI Finance Controller track

This document establishes **why Arbiter exists**, **what problem it attacks**, **who has that problem**, and **why now**. Everything downstream (product spec, architecture, design, features) is derived from the claims here. If a claim here is wrong, the product is wrong — so each is sourced and each is falsifiable.

---

## 1. The one-line thesis

**Arbiter is a verification layer for money movement.** It closes a single finance-ops loop — reconciling a payment processor's settlements against the bank and the ledger — end to end across a batch, reports an honest match rate, and hands back a categorized, evidence-backed list of the exceptions it could not resolve, each with a proposed fix.

It is deliberately **not** "an AI that does your accounting." It is a machine that shrinks the set of things a human still has to look at, and proves how much it shrank them.

---

## 2. Why this loop, and why now

### 2.1 The macro shift: generation is cheap, verification is not

The dominant 2026 engineering realization is that LLMs made _producing_ output nearly free while _trusting_ output stayed expensive and stayed sequential. Industry data backs this:

- AI now writes ~42% of committed code, yet ~96% of developers say they do not fully trust AI output to be correct, and PR review time is up ~91%. Generation parallelizes; verification does not. ([The New Stack](https://thenewstack.io/the-ai-verification-bottleneck-developer-toil-isnt-shrinking/), [srlabs.de](https://srlabs.de/blog/ai-verification-bottleneck))
- The academic framing is optimal-stopping: a reviewer gathers evidence until confidence crosses a threshold; expected verification time _peaks at maximum uncertainty_. ([Lamba, "The Verification Hill", Feb 2026](https://events.bse.eu/live/files/6312-ai-verification-hill-and-hierarchies-lamba-feb2026))
- Design implication, stated directly: _"Successful builders design systems where truth conditions are explicit — every output can be validated and every failure is detectable."_ ([Daniel Keller](https://danielkeller.com/tech/verification-not-generation/))

Finance operations is the purest instance of this problem in the enterprise. The output ("the books are right", "the cash position is X") must be _verified_, not merely _generated_, because someone signs it, an auditor tests it, and a regulator can penalize it. This is why finance-ops automation has lagged despite decades of software: the bottleneck was never data entry, it was **assurance**.

### 2.2 The micro problem: reconciliation is still manual

Reconciliation is the act of proving that two or more independent records of the same money agree, and explaining every place they don't.

- A mid-market finance team reconciles bank statements, payment-processor settlement reports, wallet/ledger events, AP invoices and tax ledgers — mostly in spreadsheets, monthly, under close deadline pressure.
- Mature automated engines auto-match 95–99% of _transactions_; teams then work the residue through exception queues: duplicates, short/over payments, missing payouts, FX differences, inconsistent fees. ([primefinlabs](https://primefinlabs.com/payment-reconciliation-engine/))
- The residue is where the time goes, where the money leaks (unclaimed input tax credit, unrecovered processor overcharges, missed chargebacks), and where trust is won or lost.

### 2.3 Why 2026 specifically

1. **Model capability crossed the "explain a financial variance" line.** Frontier models can now read a settlement report, a bank line and a ledger row and articulate _why_ the three don't tie — in language a controller accepts. That was not reliably true 18 months ago.
2. **The incumbents just validated the category.** BlackLine shipped "Verity" AI agents (Sept 2025) and "Agentic Financial Operations" (Apr 2026) explicitly framed around _"the trust and governance gap"_. HighRadius markets 190+ autonomous finance agents. Numeric raised $89M total ($51M Series B, Nov 2025) with 90%+ auto-match at Brex, Wealthfront, Public. ([GlobeNewswire](https://www.globenewswire.com/news-release/2026/04/14/3273099/0/en/blackline-unveils-agentic-financial-operations-to-close-ai-s-governance-and-trust-gap.html), [HighRadius](https://www.highradius.com/resources/Blog/agentic-ai-in-finance/), [web search: Numeric funding](https://www.numeric.io/blog/reconciliation-automation))
3. **The buyer is now actively piloting.** Per AFP 2026, 52% of US treasurers are piloting AI for cash forecasting; corporate treasury has moved AI agents from pilots into live cash-positioning and board reporting. ([ChatFin](https://chatfin.ai/guide/treasury-ai-cash-flow-forecasting-agents-for-the-cfo-2026/))
4. **The primitives are open.** Double-entry ledgers (Blnk), reconciliation engines (Lerian Matcher), and multi-processor pipelines are now open-source, so a small team can stand on real infrastructure instead of building a ledger from scratch. ([Blnk](https://github.com/blnkfinance/blnk), [Lerian Matcher](https://github.com/LerianStudio/matcher))

The window: the category is proven, the buyer is willing, the incumbents are slow and enterprise-priced, and the tech just became good enough. That is the moment to enter with a sharper, more honest wedge.

---

## 3. The finance-ops loops (and which one Arbiter closes first)

The track names four example directions. We evaluated all four on: pain acuity, judge legibility, data standardisation, defensibility, and demo-ability.

| Loop | What it reconciles | Pain | Data is standardised? | Defensibility | Verdict |
|---|---|---|---|---|---|
| **Multi-source settlement reconciliation** | PG settlement report ↔ bank credits ↔ orders/ledger; explode net payout into gross − MDR − GST − refunds − chargebacks | High, universal, recurring every settlement cycle | **Yes** — one PG's report schema covers thousands of merchants | Medium (engine + exception taxonomy + learning loop) | **PRIMARY** |
| Bank-to-book reconciliation | Bank statement ↔ GL cash account | High, universal | Partial (bank formats vary: MT940, BAI2, CSV) | Low (most crowded) | Secondary module |
| Forward cash forecaster | Not a reconciliation; a projection off AR/AP/bank | High, board-visible | N/A | Medium | **Downstream module** — only trustworthy _after_ the ledger is reconciled |
| Tax-line matcher (GST 2B) | Purchase invoices ↔ GSTR-2B ↔ books; protects input tax credit | Very high in India, money-denominated (lost ITC = real cash) | Yes (GSTN format) | High (India-specific, regulatory) | **Strong secondary** — India wedge |

**Decision: Arbiter's flagship loop is multi-source settlement reconciliation, built on a loop-agnostic engine.** Rationale:

1. **Judge legibility.** Razorpay _is_ the settlement company. A judge sees a net NEFT credit reconciled back to 200 orders, MDR, GST-on-MDR and two refunds, with three unexplained lines surfaced as ranked exceptions — and immediately understands both the problem and the quality of the solution. No domain lecture required.
2. **Data standardisation.** Razorpay's Settlement Reconciliation Report has a fixed schema (settlement_id, order_id, payment_id, amount, fee, tax, type). One synthetic generator produces realistic batches; one parser handles real exports. The "80% of the work is connectors" tax (see [08](08-why-it-might-not-sell.md)) is _lowest_ here.
3. **Rich, real exception taxonomy.** Settlement recon naturally produces FEE_DEDUCTION, TAX_DEDUCTION, ROUNDING, PARTIAL_PAYMENT, TIMING (T+2 straddling month-end), DUPLICATE, CHARGEBACK, FX, MISSING_UTR, WRONG_ACCOUNT, UNEXPLAINED. That is a genuine adjudication problem, not a toy join.
4. **The engine generalises.** A _recon spec_ (YAML: sources, keys, tolerances, exception types, resolution rules) describes settlement recon today and GST-2B or bank-to-book tomorrow with no engine changes. We ship settlement as the reference spec and GST-2B as proof of generality.

The settlement formula Arbiter must reproduce and defend line by line:

```
Net payout (bank credit) = Σ gross(payment) − Σ MDR − Σ GST-on-MDR − Σ refunds − Σ chargebacks − adjustments ± rounding
```

Sources: [terra-insight](https://www.terra-insight.com/insights/razorpay-settlement-reconciliation/), [Razorpay settlement docs](https://razorpay.com/docs/payments/settlements/), [trulyinvoice](https://www.trulyinvoice.com/blog/razorpay-settlement-reconciliation-tally-prime).

---

## 4. Market sizing (directional, not a fundraise)

This is a hackathon build, not a Series A deck, so sizing is scoped to "is there a real market behind this if it continues."

- **Every business that accepts online payments** has settlement reconciliation. Razorpay alone serves millions of businesses; Stripe, PayU, Cashfree, PhonePe add more. Each merchant above ~₹50L/month GMV has a person or a fraction of a person doing this monthly.
- **Adjacent, larger:** the financial close / reconciliation software market that BlackLine ($600M+ revenue), HighRadius, FloQast, Numeric, Ledge and Nominal compete in. Numeric's $89M raised and Nominal's $20M raised on this exact problem is the market signal.
- **India-specific:** GST reconciliation (GSTR-2B ↔ purchase register) is a legally mandated, recurring, money-denominated task for every registered business — served today by ClearTax, Zoho, Tally add-ons and thousands of CA firms doing it by hand.

The point for the buildathon: this is not a niche. It is a large, boring, under-automated market that just became addressable.

---

## 5. What the buyer actually wants (and it is not "more AI")

Synthesised from incumbent positioning and the buyer-research findings in [08](08-why-it-might-not-sell.md):

1. **A smaller pile to check** — fewer exceptions, not zero, and confidence that the auto-matched pile is actually right.
2. **An audit trail that survives an auditor** — who decided what, on what evidence, reproducibly.
3. **Determinism where possible.** Finance buyers are wary of non-deterministic AI touching controls. BlackLine's entire 2026 message is "governance and trust gap." The winning posture is _deterministic core, AI only at the ambiguity boundary, every AI action gated and logged_ — which also happens to be exactly what the Buildathon's "AI Judgment" criterion rewards ("opt for deterministic solutions where AI is unnecessary").
4. **Money found.** Recovered processor overcharges, reclaimed input tax credit, caught duplicate payouts, caught missed chargebacks. A number with a currency sign.
5. **Time back** — measured in analyst-hours per close.

---

## 6. How this maps to the Buildathon bar

The track bar: **"Throughput plus measured accuracy plus an honest exception list. One cherry-picked match proves nothing."**

| Bar element | Arbiter's answer | Where it's specified |
|---|---|---|
| Throughput | `arbiter run` processes a 50–500+ record batch; scorecard reports wall-clock and records/sec | [07](07-evaluation-and-benchmark.md) |
| Measured accuracy | Synthetic batches ship with ground-truth labels; `arbiter bench` reports auto-match rate, precision/recall, **false-match rate**, $ matched vs $ unexplained | [07](07-evaluation-and-benchmark.md) |
| Honest exception list | The exception ledger is a first-class product output: every unresolved item categorized, ranked by $ and confidence, with evidence + hypothesis + proposed action | [06](06-feature-inventory.md), [02](02-product-spec.md) |
| Not cherry-picked | Deterministic replay + CI scorecard on every commit + adversarial data generator with injected labeled anomalies means the numbers are reproducible by a judge in one command | [07](07-evaluation-and-benchmark.md), [10](10-implementation-plan.md) |

The four stated judging criteria — Problem Taste, Build Quality, AI Judgment, Failure Recovery — are mapped explicitly in [10 §2](10-implementation-plan.md).

---

## 7. Sources

- Razorpay AI Buildathon — [razorpay.com/buildathon](https://razorpay.com/buildathon/); track summaries via [velonx.in](https://velonx.in/blog/razorpay-ai-buildathon-2026-tracks-eligibility-stipend-selection-process), [jobseekershub](https://www.jobseekershub.co.in/2026/08/razorpay-ai-buildathon-2026-bangalore.html)
- Verification bottleneck — [The New Stack](https://thenewstack.io/the-ai-verification-bottleneck-developer-toil-isnt-shrinking/), [srlabs.de](https://srlabs.de/blog/ai-verification-bottleneck), [Lamba Feb 2026](https://events.bse.eu/live/files/6312-ai-verification-hill-and-hierarchies-lamba-feb2026), [danielkeller.com](https://danielkeller.com/tech/verification-not-generation/)
- Incumbents & startups — [BlackLine Agentic Financial Operations](https://www.globenewswire.com/news-release/2026/04/14/3273099/0/en/blackline-unveils-agentic-financial-operations-to-close-ai-s-governance-and-trust-gap.html), [HighRadius agentic AI](https://www.highradius.com/resources/Blog/agentic-ai-in-finance/), [Numeric reconciliation automation](https://www.numeric.io/blog/reconciliation-automation), [Ledge](https://www.ledge.co/), [Nominal bank reconciliation](https://nominal.so/blog/bank-reconciliation/), [Kognitos top reconciliation platforms 2026](https://www.kognitos.com/blog/top-ai-platforms-automated-reconciliation-2026/)
- Razorpay settlement mechanics — [terra-insight](https://www.terra-insight.com/insights/razorpay-settlement-reconciliation/), [Razorpay docs: settlements](https://razorpay.com/docs/payments/settlements/), [Razorpay: refunds & MDR](https://razorpay.com/blog/refunds-and-mdr-in-payment-gateways/), [Razorpay Smart Collect 2.0](https://razorpay.com/smart-collect/), [trulyinvoice](https://www.trulyinvoice.com/blog/razorpay-settlement-reconciliation-tally-prime)
- GST / tax-line matching — [aiaccountant: three-way match + GST](https://blog.aiaccountant.com/three-way-match-automation-gst), [ClearTax: GST reconciliation](https://cleartax.in/s/gst-reconciliation), [Taxilla: ITC reconciliation](https://www.taxilla.com/gst-input-tax-credit-reconciliation)
- Cash forecasting — [ChatFin treasury AI 2026](https://chatfin.ai/guide/treasury-ai-cash-flow-forecasting-agents-for-the-cfo-2026/), [Kognitos cash forecasting tools 2026](https://www.kognitos.com/blog/top-ai-cash-flow-forecasting-tools-treasury-2026/)
- Open-source primitives — [Blnk ledger](https://github.com/blnkfinance/blnk), [Lerian Matcher](https://github.com/LerianStudio/matcher), [Etherlabs multi-processor reconciliation](https://github.com/Etherlabs-dev/multi-processor-reconciliation)
