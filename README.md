<h1 align="center">Arbiter</h1>

<p align="center"><strong>A verification layer for money movement.</strong></p>

<p align="center">
Arbiter closes one finance-ops loop end to end — reconciling a payment processor's settlements
against the bank and the ledger across a batch — reports an <em>honest</em> match rate, and hands
back a categorized, evidence-backed list of the exceptions it could not resolve, each with a
proposed fix.
</p>

<p align="center"><em>Submission — Razorpay AI Buildathon 2026 · Track: AI Finance Controller</em></p>

---

## The one sentence

> Arbiter turns _"here are three files, tell me if the money is right"_ into
> _"97.2% tied automatically, ₹41,900 across 6 exceptions still need you — here's each one,
> the evidence, and what I think it is."_

## Why this exists

The 2026 engineering consensus: **verification capacity, not generation speed, is the bottleneck.**
Reconciliation, settlement and forecasting are still done by hand — not because the data entry is
hard, but because someone has to _trust_ the result, and trust doesn't parallelize.

Arbiter is built as a direct expression of that idea: a **deterministic core** does the matching and
the money math (reproducibly, no LLM in the path), and an LLM is used at **exactly one bounded step** —
explaining the variances a human would otherwise investigate by hand, as gated proposals a human
confirms. Turn the AI off entirely with `--no-ai` and you still get ~88% of the value.

Full reasoning: [`docs/01-market-and-thesis.md`](docs/01-market-and-thesis.md).

## What it does

| | |
|---|---|
| **Ingests** | Razorpay settlement report + bank statement + order ledger → one immutable, normalized event log |
| **Matches** | 4 deterministic passes: exact → tolerant → set/subset (1 credit ↔ N orders) → fuzzy candidates |
| **Decomposes** | Verifies `net = gross − MDR − GST-on-MDR − refunds − chargebacks ± rounding` line by line |
| **Classifies** | Every non-match → a typed exception (`TIMING`, `DUPLICATE`, `FEE_DRIFT`, …), ranked by ₹ at stake |
| **Adjudicates** | The ambiguous residue → Claude proposes a category + plain-language explanation + a fix + a rule. Proposals only — never auto-applied |
| **Learns** | You accept a resolution → Arbiter drafts a durable rule → next cycle's auto-match rate rises |
| **Reports** | `arbiter bench` → auto-match rate, precision, recall, **false-match rate**, ₹ coverage, throughput, LLM cost — reproducibly, in CI, on every commit |

## Quickstart

```bash
git clone <repo> && cd arbiter
make demo          # generates a 200-record batch, reconciles it, opens the cockpit
```

Then:

```bash
arbiter gen --scenario d2c --records 200 --seed 42     # adversarial synthetic batch + ground truth
arbiter run --spec specs/razorpay-settlement.yaml       # reconcile
arbiter run --spec specs/razorpay-settlement.yaml --no-ai   # deterministic core only
arbiter bench --spec specs/razorpay-settlement.yaml     # score vs ground truth
arbiter replay <run-id>                                 # byte-identical reconstruction
arbiter explain <exception-id>                          # evidence drawer, as text
```

## What's in here

| Path | |
|---|---|
| [`docs/`](docs/) | The full research, spec, architecture, design doctrine, competitive analysis, and honest red-team |
| `packages/engine/` | Deterministic matching engine, decomposition, exception taxonomy, the one AI step, event store, bench harness |
| `packages/datagen/` | Adversarial synthetic batch generator with labeled anomalies + ground truth |
| `packages/api/` | FastAPI backend |
| `web/` | Next.js cockpit — scorecard · exception queue · evidence drawer |
| `specs/` | `razorpay-settlement.yaml` (flagship) · `gst-2b.yaml` (proof the engine is loop-agnostic) |

## Documentation

Read in order:

1. [`01-market-and-thesis.md`](docs/01-market-and-thesis.md) — why this, why now, which loop, sourced
2. [`02-product-spec.md`](docs/02-product-spec.md) — what it is, what's in the box and why, how it works end to end
3. [`03-competitive-landscape.md`](docs/03-competitive-landscape.md) — BlackLine, HighRadius, Numeric, Nominal, Ledge, PG-native, OSS — and the wedge
4. [`04-technical-architecture.md`](docs/04-technical-architecture.md) — the system, data model, algorithms, the AI boundary, tech choices
5. [`05-design-doctrine.md`](docs/05-design-doctrine.md) — the cockpit: principles, interface model, visual system, interaction rules
6. [`06-feature-inventory.md`](docs/06-feature-inventory.md) — every feature, its job, its priority
7. [`07-evaluation-and-benchmark.md`](docs/07-evaluation-and-benchmark.md) — how Arbiter measures itself, honestly
8. [`08-why-it-might-not-sell.md`](docs/08-why-it-might-not-sell.md) — the internal red-team, and how to make it sellable
9. [`09-open-strategic-questions.md`](docs/09-open-strategic-questions.md) — the decisions that are yours to make
10. [`10-implementation-plan.md`](docs/10-implementation-plan.md) — build order, judging-criteria map, schedule, definition of done
- [`adr/`](docs/adr/) — architecture decision records

## Non-goals for this version (stated deliberately)

Arbiter v1 does **not**: post journal entries into an ERP · run live bank/ERP connectors ·
do multi-currency consolidation · detect fraud · produce a full cash forecast · handle
auth / multi-tenancy / billing. Each is a deliberate scope boundary with a reason —
see [`docs/02 §6`](docs/02-product-spec.md) and [`docs/06 §M`](docs/06-feature-inventory.md).

## Honest limitations

- The benchmark runs on **synthetic data**, which is cleaner than production. Real-world match
  rates will be lower. The generator injects realistic messiness and the difficulty dial shows
  where accuracy degrades — but the asterisk is real and stays visible.
- Small batch sizes (50–500) mean wide confidence intervals on the rates. `bench --seeds N` aggregates.
- See [`docs/07 §6`](docs/07-evaluation-and-benchmark.md) for the full list.

## License

Apache-2.0 (engine, benchmark, CLI, specs). See [`LICENSE`](LICENSE).
