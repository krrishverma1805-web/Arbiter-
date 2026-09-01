# 15 — Domain Model: Reconciliation

_The finance content Arbiter must get right. Written so an engineer with no accounting background can implement it correctly, and so a controller reading it trusts that we understand their job._

---

## 1. The three views of one rupee

A single customer payment produces **three independent records**, created by three parties at three times:

| # | View | Created by | When | Says |
|---|---|---|---|---|
| 1 | **Order / ledger record** | the merchant's commerce system (Shopify, custom, ERP) | at checkout | "Customer X owes / paid ₹1,000 for order #123" |
| 2 | **Processor record** | Razorpay | at payment capture, then again at settlement | "We captured ₹1,000 on payment `pay_abc`; we will settle ₹1,000 − ₹20 MDR − ₹3.60 GST = ₹976.40 in settlement `setl_xyz` / UTR `UTR789`" |
| 3 | **Bank record** | the merchant's bank | at settlement credit (T+2) | "₹9,54,200 credited on 12 Aug, ref UTR789" (one line for a whole batch of payments) |

**Reconciliation = proving these three agree, and explaining every place they don't.** The hard part is that they are at different **grains** (per-order, per-payment, per-payout-batch), different **times** (checkout, capture, T+2), and different **completeness** (the bank line is a net lump; the processor record itemizes; the ledger may be missing refunds).

---

## 2. The settlement identity (the equation Arbiter verifies)

For every group of processor line items sharing a `settlement_utr`:

```
bank_credit(UTR)  ==  Σ credit(items)          # gross payments settled
                    − Σ debit(items)           # refunds, chargebacks, negative adjustments
                    − Σ fee(items)             # MDR
                    − Σ tax(items)             # GST on MDR (18%, SAC 998433)
                    ± rounding                 # within a ₹1 tolerance
```

And the cross-check against the ledger, for the `payment`-type items only:

```
Σ amount(items where type == payment)  ==  Σ order_total(ledger orders in this batch)
```

If the first equation holds → the payout is **arithmetically explained**. If the second also holds → the payout is **fully reconciled to the business**. A break in either is an exception, and _which_ equation broke tells you _what kind_ of exception.

Sources for the fee/GST model: [Razorpay: UPI/MDR charges](https://razorpay.com/blog/upi-charges-explained-mdr-vs-platform-fees/), [Razorpay: settlement transparency playbook](https://razorpay.com/blog/settlement-transparency-the-complete-merchant-playbook-for-questioning-your-payment-gateway-in-2026), [incorpx: RBI & GST requirements](https://www.incorpx.io/blog/payment-gateway-compliance-rbi-gst-requirements), [Zoho: GST reconciliation for gateway fees](https://www.zoho.com/payments/academy/regulatory-compliance/gst-reconciliation-and-gst-invoice-records.html).

---

## 3. The exhaustive exception taxonomy

Each type below has: **what it is**, **root cause**, **how Arbiter detects it deterministically** (or why it can't), **the resolution playbook**, and **the accounting treatment**. This is the reference the spec's `taxonomy` and `rules` implement, and what the agent's prompt teaches.

### 3.1 Arithmetic-explained, business-benign (auto-resolvable)

| Type | What / root cause | Deterministic detection | Resolution | Accounting |
|---|---|---|---|---|
| **ROUNDING** | Sub-rupee differences from GST rounding, per-item vs batch rounding | `abs(residual) ≤ rounding_tolerance` (₹1) | Accept variance; post to a "rounding differences" GL account | Immaterial; expensed |
| **FEE_DEDUCTION** | The residual is exactly the expected MDR and it just wasn't auto-attributed to line items | `abs(residual − expected_MDR) ≤ ε` where `expected_MDR` from the rate card by `method` | Attribute to payment processing fees | Dr Payment Gateway Charges, Cr Bank |
| **TAX_DEDUCTION** | Same, for GST-on-MDR | residual matches `0.18 × MDR` | Attribute to GST input credit (if separately invoiced) | Dr GST Input Credit (ITC), Cr Bank — **only if** the processor's tax invoice lists GST separately ([Zoho](https://www.zoho.com/payments/academy/regulatory-compliance/gst-reconciliation-and-gst-invoice-records.html)) |
| **FX_DIFFERENCE** | International payment settled in INR at a rate different from the order-date rate | `method`/currency indicates intl AND residual within an FX tolerance band | Book FX gain/loss | Dr/Cr Foreign Exchange Gain/Loss |

### 3.2 Timing (auto-classifiable, resolves by carry-forward)

| Type | What / root cause | Deterministic detection | Resolution | Accounting |
|---|---|---|---|---|
| **TIMING** | T+2 settlement lands in the next period; payment is in this month's processor report, credit is in next month's bank statement (or vice versa) | Unmatched bank credit with `value_date` in first ~3 days of period AND a matching processor batch in the prior period; OR unmatched processor batch near period-end | Carry the reconciling item forward; it clears next cycle | Recognize the receivable ("Settlement Receivable" / "Funds in Transit") at period-end; clear on credit |
| **ON_HOLD / IN_FLIGHT** | Processor is holding the settlement (`on_hold=true`) — reserve, risk review, KYC | `on_hold == true` on the line items | No action; track as in-transit | "Funds in Transit — held"; disclose if material |

### 3.3 Value / completeness mismatches (needs judgment → agent or human)

| Type | What / root cause | Detection | Resolution playbook | Accounting |
|---|---|---|---|---|
| **PARTIAL_PAYMENT** | Customer paid less than order total (partial capture, discount applied post-order, wallet + card split not fully captured) | `payment.amount < order.order_total` beyond tolerance, single payment | Confirm with the order system whether the balance is expected; if written off → bad debt | Dr Bank (received) + Dr Discount/Bad Debt, Cr AR |
| **OVER_PAYMENT** | Customer charged twice for one order; or a manual re-charge | Two `payment` items, same `order_id`, both captured | Refund the duplicate; until then it's a liability | Cr Customer Refunds Payable |
| **SPLIT_SETTLEMENT** | One order's payment split across two settlement batches (processor-side batching) | `order_id` appears in two `settlement_utr` groups, amounts sum to the order | Match as N:1; no action | Normal |
| **SHORT_SETTLEMENT** | Processor settled less than `gross − fees` with no explained deduction | Residual is negative and unexplained by the fee model | **Raise a processor dispute** — this is money owed to the merchant | Dr Settlement Receivable — Disputed, Cr Revenue/Bank |
| **MISSING_PAYOUT** | A processor settlement batch has no corresponding bank credit at all | `settlement_utr` group with no bank line within the window | Escalate: chase the processor / check the bank account on file | "Settlement Receivable — Overdue" |

### 3.4 Adjustments & disputes (needs judgment)

| Type | What / root cause | Detection | Resolution | Accounting |
|---|---|---|---|---|
| **CHARGEBACK** | Customer disputed a payment; processor claws back the amount (+ often a fee) from a later settlement | `dispute_id` present, OR a `debit` adjustment referencing a prior `payment_id` | Match the clawback to the original payment; decide whether to contest | Dr Chargeback Losses (+ Dr Chargeback Fees), Cr Bank; reverse recognized revenue |
| **ADJUSTMENT** | Processor credit/debit for a correction, promo, refund of fees, GST credit note | `type == adjustment`, `description` gives the reason (untrusted — [doc 14](14-security-and-trust.md)) | Read the description; categorize to the right GL account; keep the processor's credit note | Depends on reason |
| **REFUND_TIMING** | Refund issued this period but netted against a settlement in a different period | Refund `debit` item in a batch whose payments were in a prior period | Carry-forward; ensure the original sale's revenue is reversed in the right period | Dr Sales Returns, Cr Bank (in the refund period) |

### 3.5 Data-quality & identity (needs judgment / data fix)

| Type | Root cause | Detection | Resolution |
|---|---|---|---|
| **MISSING_UTR** | Bank narration doesn't contain a parseable UTR | `extract_utr(narration)` returns empty | Fuzzy-match on amount + date + counterparty; if unique, propose; else escalate |
| **WRONG_ACCOUNT** | Settlement credited to a secondary/old bank account not in the recon set | Processor batch settled (`settled=true`) but no credit in the provided bank file | Escalate: check other bank accounts; update the account on file with the processor |
| **DUPLICATE** | Same payment appears twice in the processor export (export bug, overlapping date ranges) | `count(payment_id, type=payment) > 1` with identical amounts | Deduplicate the export; never auto-void — route to human |
| **UNMAPPED_ORDER** | Processor `order_id` has no row in the ledger export (ledger export incomplete, or order in a different system) | `order_id` not found in ledger | Escalate: widen the ledger export window / check other order sources |
| **SECURITY_REVIEW** | Injection-shaped content in `description` / `notes` / `narration` | deterministic scanner ([doc 14 C2](14-security-and-trust.md)) | Route to human; never send to the agent |
| **UNEXPLAINED** | None of the above; residual is real and unattributed | fallthrough | Agent investigates; if it can't, escalates with "what's missing" |

---

## 4. The resolution actions (closed vocabulary)

Every exception resolves to exactly one of these. The agent's `suggested_action` and the spec's `resolve:` use this vocabulary.

| Action | Meaning | Produces |
|---|---|---|
| `accept_variance` | The difference is real, immaterial, expected | A GL posting suggestion to a variance account |
| `attribute_to(account)` | The difference is an explained fee/tax/FX | A GL posting suggestion |
| `carry_forward` | It's a timing item; it will clear next period | A "reconciling item" on the period-end recon, auto-cleared next run |
| `flag_overcharge` | The processor deducted more than contracted | A dispute packet: payment ids, expected vs actual, ₹ owed |
| `raise_dispute` | Chargeback to contest, or missing/short payout | A dispute packet |
| `void_duplicate_of(id)` | This is a duplicate export row | A note to fix the export; no ledger impact |
| `request_data(source, detail)` | Can't resolve without more data | A precise data request |
| `route_to_human(question)` | Genuine judgment call | The one question a human must answer |
| `wont_fix(reason)` | Human decides it's not worth pursuing (e.g. ₹4 short payout) | Closed with reason, logged |

---

## 5. Accounting treatment — the mapping to journal entries

Arbiter **does not post** journal entries in v1 ([doc 02 §6](02-product-spec.md)). But it **proposes** them in the Close Memo, because that's what makes the output actionable. The model, per [Razorpay's own guidance](https://razorpay.com/blog/settlement-transparency-the-complete-merchant-playbook-for-questioning-your-payment-gateway-in-2026) and standard practice:

| Event | Date | Journal entry (proposed) |
|---|---|---|
| Order paid (payment captured) | transaction date | Dr **Settlement Receivable** (gross) · Cr **Revenue** (+ Cr GST Output if applicable) |
| Settlement confirmed | `settled_at` | Dr **Payment Gateway Charges** (MDR) · Dr **GST Input Credit** (GST on MDR) · Cr **Settlement Receivable** (fee portion) |
| Bank credit received | bank `value_date` | Dr **Bank** (net) · Cr **Settlement Receivable** (net) |
| Refund | refund date | Dr **Sales Returns** · Cr **Settlement Receivable** |
| Chargeback | clawback date | Dr **Chargeback Loss** · Dr **Chargeback Fees** · Cr **Settlement Receivable** |

The three "layers" (revenue on transaction date, fees + GST at settlement, bank receipt on credit date) are linked by `order_id` → `settlement_utr` → bank UTR. Arbiter's whole job is to make that linkage explicit and prove it nets to zero.

---

## 6. Why the "50+ records" framing understates the problem

50 records sounds small. But a realistic month for a ₹1 Cr/month D2C brand:
- ~2,000 orders → ~2,000 processor `payment` items
- ~120 refunds, ~8 chargebacks, ~15 adjustments
- ~22 settlement batches → 22 bank credits
- Across 2 processors + 1 bank + 1 order ledger = ~4,300 records to tie

The 50-record floor is the _minimum_ to demonstrate the loop. Arbiter's demo runs **800** and `bench --scale 5000` is documented, because throughput at realistic scale is the point ([doc 11 G10](11-plan-evaluation-and-gaps.md)).
