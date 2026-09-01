# 21 — Go-to-Market & Business Model

_The commercial thinking, at the depth a senior person would bring to a founding decision. Complements [doc 08](08-why-it-might-not-sell.md) (red-team) and [doc 09](09-open-strategic-questions.md) (decisions)._

> **Framing:** for the Buildathon this is a _demonstration of commercial judgment_, not a fundraise. But the judgment has to be real — a vague "we'll figure out GTM" signals the opposite of what's wanted.

---

## 1. Positioning statement

> **For** finance teams at multi-rail businesses (2+ payment processors + a bank + an ERP)
> **who** spend days each month reconciling settlements and never fully trust the result,
> **Arbiter is** a verification layer that ties every rupee across all their rails,
> **that** reports an honest match rate and hands back a pre-diagnosed, ranked exception list with an auditor-ready memo,
> **unlike** their payment processor's native reconciliation (single-rail) or an enterprise close suite (six-figure, six-month implementation),
> **because** money-safety is independent of the AI (deterministic core, gated proposals) and the accuracy number is reproducible by anyone in one command.

---

## 2. Ideal Customer Profile (ICP)

### Primary — "the multi-rail controller"
| Attribute | Value |
|---|---|
| Company | D2C brand or marketplace, ₹5 Cr–₹200 Cr annual GMV, 30–200 people |
| Rails | Razorpay + (Cashfree \| PayU \| marketplace payouts \| COD remittance) + 1–2 bank accounts + Tally/Zoho/NetSuite |
| Buyer | Financial Controller / Finance Manager (owns the close) |
| Trigger | a botched close, an audit finding on reconciliations, a discovered processor overcharge, or a finance hire who refuses to do it in spreadsheets |
| Pain today | 2–5 person-days/month; no confidence in the auto-matched pile; ITC leakage; processor overcharges uncaught |
| Willingness to pay | ₹15k–₹60k/month (vs. 0.3–0.7 FTE ≈ ₹40k–₹120k/month loaded) |

### Secondary — "the outsourced controller / CA firm"
Buys tools to serve more clients per accountant; no internal org-change needed; values the per-client recon spec + the billable Close Memo. Lower ACV, higher volume, faster sales. B2B2C.

### Explicitly **not** ICP (for the first 18 months)
- Single-processor, single-bank micro-businesses (bundled tools are good enough — [doc 08 R2](08-why-it-might-not-sell.md)).
- Enterprises with an existing BlackLine/audit relationship (trust-monopoly wall — [doc 08 R1](08-why-it-might-not-sell.md)).
- Pure GST-2B-only buyers (bad unit economics — [doc 08 R11](08-why-it-might-not-sell.md); GST is a feature, not the wedge).

---

## 3. The wedge and the expansion

```
LAND:  "reconcile your Razorpay + <2nd rail> settlements this month, free, and I'll show you
        what's leaking"  →  a Close Memo with N exceptions and ₹X of found overcharges/ITC
EXPAND: add rails (more processors, more banks) → add GST-2B spec → add the cash-position
        readout → team seats (preparer + reviewer) → the learning loop makes month 3 > month 1
        → they can't easily leave (their rules, their history, their audit trail live here)
```

The retention mechanic is the **accumulated rule set + audit history** — switching cost that compounds monthly, built the honest way (their data, their rules, exportable).

---

## 4. Pricing model

Open-core ([doc 09 Q2](09-open-strategic-questions.md)): the engine, CLI, benchmark and specs are free (Apache-2.0). Revenue is the hosted cockpit + connectors + collaboration.

| Tier | Price | For | Includes |
|---|---|---|---|
| **OSS / self-host** | ₹0 | engineers, tinkerers, CA firms who'll run the CLI | engine, `bench`, specs, file ingest, CLI, Close Memo |
| **Solo** | ₹9,000/mo | founder-led finance, 1 seat | hosted cockpit, 2 rails, monthly cycle, email support |
| **Team** | ₹29,000/mo | the primary ICP | 5 seats, unlimited rails, the learning loop + rule review, SSE cockpit, audit-pack export, priority support |
| **Firm** | ₹19,000/mo per client bundle (min 5) | outsourced controllers / CA firms | multi-client workspaces, white-label memo, per-client specs |
| **Connectors** | usage add-on | anyone wanting live pulls | Razorpay API, bank aggregator, ERP sync — priced per connected source |

Benchmarks: FloQast runs ~$125–150/user/mo, ~$12k–24k/yr typical, six-figure for mid-market ([Vendr](https://www.vendr.com/marketplace/floqast), [SpendHound](https://www.spendhound.com/marketplace/floqast-pricing)). Arbiter's Team tier (~₹3.5L/yr ≈ $4.2k) is deliberately an order of magnitude below the enterprise suites and roughly at parity with a fractional analyst — an easy ROI conversation.

---

## 5. Unit economics (hypotheses, to be validated)

| Metric | Hypothesis | Basis |
|---|---|---|
| ACV (Team) | ₹3.5L (~$4.2k) | pricing above |
| Gross margin | ~80% | hosting + LLM cost (~₹3k–8k/mo/customer at demo-scale volumes — [doc 22](22-cost-model.md)) |
| CAC | ₹40k–₹80k | content + founder-led sales + CA-firm partnerships; no paid acquisition early |
| Payback | 4–8 months | CAC / (ACV × margin / 12) |
| Logo churn | target < 2%/mo | retention mechanic in §3; risk: cold-start (§[08 R9](08-why-it-might-not-sell.md)) |
| Expansion | 115–130% NRR | rails + seats + connectors |

The LLM cost line is the one to watch: the tiered model policy ([doc 19 §6](19-agent-contracts.md)) and prompt caching keep it at single-digit % of revenue; a batch with many `UNEXPLAINED` exceptions is the cost tail, capped per run.

---

## 6. Sales motion

1. **OSS top-of-funnel:** the repo + the benchmark + a "reconcile your Razorpay settlements in 5 minutes" post. Engineers and finance-ops people find it.
2. **Self-serve Solo:** the hosted cockpit, credit-card signup, the first Close Memo as the aha.
3. **Founder-led Team:** for ICP accounts — a 30-min call, run their last month's real export live, hand them the memo + the found-money number. Close on the value shown, not a deck.
4. **CA-firm partnerships:** 3–5 firms as design partners; they bring a portfolio of clients.

No enterprise motion, no SDRs, no RFPs in year one.

---

## 7. The competitive field *at the Buildathon* (what other teams will likely build for this track)

| Likely submission | Why it's weaker than Arbiter |
|---|---|
| "GPT reads two CSVs and lists mismatches" | Non-deterministic, no measured accuracy, no false-match rate, falls over past ~50 rows, no exception taxonomy |
| A bank-to-book matcher with a nice UI | The commodity case; no settlement decomposition; no agent; no benchmark |
| A GST-2B reconciler | Narrow; India-only; rules-only; doesn't touch settlement/bank |
| A cash-flow forecast dashboard | Not a reconciliation loop; forecasts off unreconciled data are untrustworthy — the judges' own framing |
| A multi-agent "finance team" of LLMs | Impressive demo, 2–10× cost, non-deterministic money math, weak on the "deterministic where possible" criterion, hard to show measured accuracy |

**Arbiter's separation:** the honest reproducible benchmark (matching **and** agent), the settlement-decomposition depth, the deterministic-core doctrine written as an ADR, the calibration study, and the "watch the match rate rise over 3 cycles" demo. The bar says "one cherry-picked match proves nothing" — Arbiter is built to be the submission that most directly answers that sentence.

---

## 8. 12-month roadmap (if it continues past the Buildathon)

| Quarter | Focus |
|---|---|
| Q1 | OSS launch; 5 design-partner customers on the hosted cockpit; Razorpay API + one bank-aggregator connector; real-dataset benchmark |
| Q2 | GST-2B spec productized; the learning loop at scale; SOC 2 Type I started; Team tier GA |
| Q3 | ERP write-back (proposed JEs → one-click post to Zoho/Tally) behind a flag; CA-firm program |
| Q4 | The cash-position module → light forecasting off the reconciled ledger; multi-entity |
