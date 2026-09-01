# 02 — Product Specification

_What Arbiter is, what it contains, why it contains each thing, how it works, and who it is for._

---

## 1. Product definition

**Arbiter** is an agent that closes the settlement-reconciliation loop across a batch of financial records. Given three independent views of the same money — a **payment processor settlement report**, a **bank statement**, and an **internal ledger / order system** — Arbiter:

1. **Ingests** all three into a normalized, immutable event log.
2. **Matches** them using a deterministic, multi-pass matching engine (exact keys → tolerant keys → fuzzy scoring → set/subset matching for batched payouts).
3. **Explodes** each net settlement into its components (gross, MDR, GST-on-MDR, refunds, chargebacks, adjustments, rounding) and verifies the arithmetic.
4. **Classifies** everything it cannot cleanly match into a typed **exception ledger**.
5. **Adjudicates** the hard exceptions with an LLM that produces _proposals only_ — a category, a plain-language explanation of the variance, an evidence trail, and a suggested resolution.
6. **Learns**: when a human accepts a resolution, Arbiter proposes a durable rule so the same exception auto-resolves next cycle.
7. **Reports**: an honest scorecard (match rate, precision/recall, false-match rate, $ reconciled vs $ unexplained, throughput, cost) and the exception list.

**One sentence:** _Arbiter turns "here are three files, tell me if the money is right" into "97.2% tied automatically, ₹41,900 across 6 exceptions still need you — here's each one, the evidence, and what I think it is."_

---

## 2. The name

An **arbiter** adjudicates disputes and renders a decision backed by evidence. That is precisely the product: when the settlement report says one thing and the bank says another, Arbiter examines the evidence, renders a ruling (matched / exception + category), and records its reasoning. The name also signals the posture — Arbiter _decides and explains_, it does not silently _act_ on money.

---

## 3. Who it is for

| User | Their job today | What Arbiter gives them |
|---|---|---|
| **Controller / Finance Manager** (primary, 20–500 person company) | Owns the monthly close; personally works the reconciliation exception queue under deadline | A 10× smaller queue, each item pre-diagnosed with evidence; a scorecard they can show the CFO/auditor |
| **Finance/Ops Analyst** | Builds the recon spreadsheet, chases missing payouts, emails the PG about overcharges | The mechanical matching is done; they spend time on judgment calls and recoveries, not VLOOKUPs |
| **Founder / CFO** (early-stage) | Does recon personally or not at all; discovers problems late | A one-command monthly check with a trustworthy number and a short list of what's wrong |
| **CA firm / outsourced controller** | Reconciles for dozens of clients manually | A repeatable, per-client recon spec + scorecard they can bill against and stand behind |
| **Auditor** (consumer, not buyer) | Tests reconciliations during the audit | An immutable, replayable audit trail: every match, every rule, every human decision, every AI proposal |

**Design target:** the Controller. Every screen, default and message is written for someone who owns the number and is personally accountable for it.

---

## 4. What's in the box (and why)

Each component exists to serve one job. If a component doesn't map to a job below, it doesn't ship.

| # | Component | Job it does | Why it must exist |
|---|---|---|---|
| C1 | **Ingestion & normalization** | Turn heterogeneous exports (Razorpay CSV/API, bank statement CSV/MT940, ledger export) into typed, deduplicated records in an append-only store | Garbage in = untrustworthy out. Normalization is where you catch encoding, date-format, and duplicate-file errors _before_ they become fake exceptions |
| C2 | **Recon spec** (YAML) | Declaratively define a reconciliation: sources, join keys, tolerances, exception taxonomy, resolution rules | Makes the engine loop-agnostic; makes the logic auditable and diffable in git; lets a customer own their rules without touching code |
| C3 | **Deterministic matching engine** | Multi-pass matching: exact → tolerant → fuzzy → set/subset; produces matches with confidence scores and provenance | This does 85–97% of the work. It is deterministic, fast, testable, and replayable. The AI is _not_ in this path |
| C4 | **Settlement decomposition** | Explode net payout into gross − MDR − GST − refunds − chargebacks ± rounding; verify the identity holds | This is the actual finance content. A "match" on the payout total that doesn't decompose is a false match |
| C5 | **Exception taxonomy & classifier** | Assign every non-match a type from a fixed vocabulary; rank by $ impact and confidence | The exception list is the product. It must be _categorized_ and _prioritized_ to be useful, not a raw dump |
| C6 | **Adjudication agent** (Claude) | For ambiguous exceptions only: propose a category, explain the variance in plain language, cite evidence, suggest a resolution | Humans accept fixes faster when the variance is _explained_. This is the verification-capacity multiplier. Strictly proposals — never auto-applied |
| C7 | **Resolution & rule-learning** | Human accepts/edits/rejects a proposal; on accept, Arbiter drafts a durable rule; match rate rises next cycle | Turns one-time human judgment into permanent automation. This is what makes month 3 better than month 1 |
| C8 | **Event log & replay** | Every ing, match, classification, proposal, decision is an immutable event; `arbiter replay` reconstructs any run deterministically | Audit survival + debuggability + "prove the number" + the anti-cherry-pick guarantee |
| C9 | **Scorecard / bench harness** | Run the batch against ground truth; emit auto-match rate, precision, recall, false-match rate, $ coverage, throughput, LLM cost, exception histogram | "Measured accuracy" and "honest exception list" from the bar. Runs in CI on every commit |
| C10 | **Adversarial data generator** | Produce 50–500+ record synthetic batches with realistic, _labeled_ injected anomalies + ground truth | You cannot claim measured accuracy without labeled data. Also the demo dataset |
| C11 | **Cockpit UI** (Next.js) | Run view, exception triage queue, evidence drawer, scorecard, cycle-over-cycle trend | Reconciliation is a human workflow. The queue must be _workable_, not just viewable. See [05](05-design-doctrine.md) |
| C12 | **CLI** (`arbiter`) | `gen`, `run`, `bench`, `replay`, `explain` | Judges, CI, and power users live here. The CLI is the proof surface |
| C13 | **API** (FastAPI) | Programmatic ingest, run, fetch exceptions, post resolutions | The cockpit talks to this; so can a customer's pipeline |

---

## 5. How it works — end to end

```
                    ┌─────────────── arbiter run --spec razorpay-settlement.yaml ───────────────┐
                    │                                                                            │
  settlement.csv ──▶│  C1 Ingest ──▶ normalized events (append-only)                              │
  bank.csv       ──▶│      │                                                                      │
  ledger.csv     ──▶│      ▼                                                                      │
                    │  C3 Match engine (deterministic, multi-pass)                                │
                    │      pass 1: exact (settlement_id ↔ UTR+date+amount)                        │
                    │      pass 2: tolerant (amount ± tolerance, date ± window)                   │
                    │      pass 3: set/subset (one bank credit ↔ N ledger orders)                 │
                    │      pass 4: fuzzy score (reference string, counterparty)                   │
                    │      │                                                                      │
                    │      ├──▶ MATCHED (confidence ≥ θ_auto) ──▶ C4 decompose & verify identity  │
                    │      │                                                                      │
                    │      └──▶ UNMATCHED / identity-fails ──▶ C5 classify into exception type    │
                    │                   │                                                          │
                    │                   ├── deterministic-classifiable ──▶ exception (typed)      │
                    │                   │                                                          │
                    │                   └── ambiguous ──▶ C6 Claude adjudication agent            │
                    │                            (tools: query_evidence, propose_category,         │
                    │                             draft_resolution, draft_rule)                    │
                    │                            → proposal {category, explanation, evidence,      │
                    │                               suggested_action, confidence}                  │
                    │                   ▼                                                          │
                    │  C8 every step emitted as immutable event                                    │
                    │                   ▼                                                          │
                    │  Outputs:  scorecard.json  +  exceptions.json  +  run.log (replayable)       │
                    └────────────────────────────────────────────────────────────────────────────┘
                                        │                         │
                              C11 Cockpit: triage queue     C9 bench: score vs ground truth
                                        │
                              human resolves ──▶ C7 draft rule ──▶ appended to spec (reviewed) ──▶ next cycle
```

### 5.1 The matching passes (why four)

1. **Exact** — join on the strongest available key set. For Razorpay: `settlement_id` against bank `UTR` + credit date + net amount. Catches the clean majority. Zero ambiguity, confidence 1.0.
2. **Tolerant** — same keys, but amounts within a configured tolerance band (rounding, FX cents) and dates within a window (T+2 settlement straddling a weekend/holiday/month-end). Confidence scaled by how much tolerance was consumed.
3. **Set / subset** — one bank credit corresponds to a _batch_ of ledger orders. Solve "which subset of unmatched orders sums (net of fees) to this credit." Bounded subset-sum with the fee model applied. This is the pass that makes settlement recon hard and where naive tools fail.
4. **Fuzzy score** — weak signals: normalized reference strings, counterparty name similarity, amount proximity, temporal proximity. Produces ranked _candidates_, not matches. Feeds the exception as "probable match: X (0.72)".

Anything not matched with confidence ≥ `θ_auto` (default 0.90, per-spec) is an exception. Anything matched between `θ_review` and `θ_auto` is a **low-confidence match** — surfaced for spot-check, counted separately in the scorecard.

### 5.2 Where the LLM is, and is not

**Not in:** ingestion, matching, decomposition arithmetic, scorecard computation, replay. These are deterministic by design (see [04](04-technical-architecture.md) §3, and the "AI Judgment" mapping in [10](10-implementation-plan.md)).

**In:** exactly one place — adjudicating an exception that the deterministic classifier tagged `AMBIGUOUS` or `UNEXPLAINED`. There the agent:
- queries the evidence graph (its only data access is a read-only tool),
- proposes a category from the fixed taxonomy (constrained/structured output),
- writes a 1–3 sentence explanation of the variance,
- suggests a resolution (e.g. "raise processor dispute for ₹X overcharge", "book to timing — will clear next cycle", "duplicate of payment_id Y — void"),
- optionally drafts a rule that would auto-handle this pattern.

Every one of these is a **proposal object** with a confidence and an evidence citation. It is written to the event log and shown in the queue. **Nothing the LLM produces changes a match, posts a journal entry, or moves money.** A human clicks accept.

### 5.3 The learning loop

```
exception ─▶ human accepts resolution "X" ─▶ Arbiter diffs the exception against the spec's rules
          ─▶ drafts candidate rule (e.g. "if source=razorpay and type=fee and |Δ| ≤ ₹2 → auto-classify ROUNDING")
          ─▶ human reviews rule in the cockpit (git-style diff of the spec)
          ─▶ merged into spec ─▶ next run: that pattern never becomes an exception again
```

The scorecard tracks **auto-match rate over cycles**. The demo shows it climbing from ~85% → ~93% → ~97% across three simulated monthly closes. That trajectory _is_ the pitch.

---

## 6. What Arbiter deliberately does NOT do (v1 scope discipline)

| Not in v1 | Why |
|---|---|
| Post journal entries / write to the ERP | Moving from "decide" to "act" on money is a trust and liability leap that needs real customer trust first. Arbiter outputs a proposed JE; the human posts it |
| Live bank / ERP connectors | Connector sprawl is the classic trap ([08](08-why-it-might-not-sell.md)). v1 ingests exports + one Razorpay API path. Connectors are a post-hackathon investment |
| Multi-currency consolidation, intercompany elimination | Enterprise close scope; different product |
| Fraud detection | Different Buildathon track; different precision/recall regime |
| Full cash forecasting | Downstream module (see [06](06-feature-inventory.md) F-future). Only credible _after_ the ledger is reconciled — that's the sequencing story, not v1 |
| Auth, multi-tenant, RBAC, billing | Not what's being judged. Single-tenant, local-first. Noted in architecture as a known gap, not hidden |

Scope discipline is itself a signal of engineering maturity — see [10](10-implementation-plan.md) §5.

---

## 7. Success criteria for the build

Arbiter is "done" for the Buildathon when a judge can, from a clean checkout:

1. `make demo` → generates a 200-record batch, runs reconciliation, opens the cockpit.
2. See a scorecard with a real (not 100%) match rate and a categorized exception list.
3. Open any exception → see the three source records, the rule trail, the AI proposal, the evidence.
4. Accept a resolution → see a rule drafted → re-run → see the match rate rise.
5. `arbiter bench` → see precision/recall/false-match-rate against ground truth, reproducibly.
6. `arbiter replay <run-id>` → get byte-identical results.
7. Read `docs/` and find every decision explained.

If all seven hold, the product matches the bar. See [07](07-evaluation-and-benchmark.md) for exact metric definitions and targets.
