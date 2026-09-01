# 06 — Feature Inventory

_Every feature Arbiter ships, the job it does, why it exists, and its priority. Nothing is here without a reason; nothing with a reason is missing._

Priority key: **P0** = required for a credible Buildathon submission · **P1** = strongly differentiating, build if time allows · **P2** = post-hackathon.

---

## A. Ingestion & data integrity

| ID | Feature | Job | Why it exists | Priority |
|---|---|---|---|---|
| A1 | Multi-format parser (CSV, XLSX, MT940/BAI2 stub, JSON) | Turn any export into canonical `Record`s | Real files are heterogeneous; the demo needs ≥ CSV+XLSX | P0 |
| A2 | Declared column mapping (in the spec) | Map arbitrary headers → canonical fields | Every merchant's export differs slightly; mapping must be data, not code | P0 |
| A3 | Currency & scale normalization → integer paise | Exact money math | Floats cause phantom exceptions | P0 |
| A4 | Duplicate-file / duplicate-row guard (content hash) | Refuse re-ingesting the same file; flag dup rows | The #1 real-world cause of fake exceptions | P0 |
| A5 | Ingest validation report | "3 rows missing dates — fix and re-ingest" | Garbage-in caught before it's a fake exception | P0 |
| A6 | Razorpay Settlement API ingest path | Pull settlements directly via API key | Shows a real connector without connector sprawl | P1 |
| A7 | Timezone + value-date vs posted-date handling | Correct T+2 / period-boundary logic | Timing exceptions depend on getting dates right | P0 |

## B. Recon spec & rules

| ID | Feature | Job | Why | Priority |
|---|---|---|---|---|
| B1 | YAML recon spec (sources, keys, tolerances, taxonomy, identity, thresholds) | Declaratively define a reconciliation | Loop-agnostic engine; git-diffable, auditable logic | P0 |
| B2 | Spec validation with helpful errors | Catch a broken spec at load | A misconfigured spec silently corrupts results | P0 |
| B3 | Safe rule expression language (whitelisted AST, no `eval`) | Let humans/AI author `when` predicates safely | Customer- and AI-authored rules must be safe to run and analyze | P0 |
| B4 | Reference spec: `razorpay-settlement.yaml` | The flagship loop | This is the demo | P0 |
| B5 | Proof-of-generality spec: `gst-2b.yaml` | Same engine, different loop | Shows the engine isn't a one-off | P1 |
| B6 | Spec versioning + migration note | Track spec changes over cycles | The learning loop mutates the spec; changes must be reviewable | P0 |

## C. Matching engine

| ID | Feature | Job | Why | Priority |
|---|---|---|---|---|
| C1 | Pass 1 — exact key match | Tie the clean majority | Fast, zero-ambiguity baseline | P0 |
| C2 | Pass 2 — tolerant match (amount band, date window) | Absorb rounding, FX cents, T+2 weekend drift | Without it, every rounding diff is a false exception | P0 |
| C3 | Pass 3 — set/subset match (1 credit ↔ N orders) | Reconcile batched payouts | The hard, differentiating pass; naive tools fail here | P0 |
| C4 | Pass 4 — fuzzy candidate scoring | Rank probable matches for the exception list | Gives the human a starting hypothesis, not a blank | P0 |
| C5 | Explicit per-match confidence formula | Every match has a defensible score | Auditor question: "how sure are you?" | P0 |
| C6 | Low-confidence match tier (θ_review ≤ c < θ_auto) | Surface spot-check candidates separately | Honest: not everything is either "tied" or "broken" | P0 |
| C7 | Deterministic ordering / seeded runs | Identical inputs → identical output | Replay, CI, anti-cherry-pick | P0 |
| C8 | Bounded subset-sum (meet-in-middle ≤40, heuristic above) with wall-clock budget | Keep pass 3 tractable | Real batches are small per settlement_id; must not hang | P0 |

## D. Settlement decomposition

| ID | Feature | Job | Why | Priority |
|---|---|---|---|---|
| D1 | Identity solver: `net = gross − MDR − GST − refunds − chargebacks ± rounding` | Verify a payout's arithmetic, not just its total | A total-only match can still be wrong; this is real finance content | P0 |
| D2 | Per-line fee/tax attribution | Attribute deductions to specific payments | Enables "processor overcharged ₹X on payment Y" | P0 |
| D3 | Residual computation on every match | Quantify what's unexplained | Residual ≠ 0 → the match becomes an exception | P0 |
| D4 | Fee-schedule fallback (when the report lacks per-line fees) | Estimate expected MDR from a rate card | Some exports don't itemize; still want a check | P1 |
| D5 | Overcharge / undercharge detection | Flag processor billing errors | Directly "money found" — a sellable outcome | P1 |

## E. Exception taxonomy & triage

| ID | Feature | Job | Why | Priority |
|---|---|---|---|---|
| E1 | Fixed exception taxonomy (11 types, per spec) | Categorize every non-match | An uncategorized list is a dump, not a deliverable | P0 |
| E2 | Deterministic classifier (spec rules) | Auto-type the clear exceptions | If a rule can decide, a rule should | P0 |
| E3 | $-impact ranking | Sort the queue by rupees at stake | The controller's attention is scarce; spend it on money | P0 |
| E4 | Candidate attachment (from fuzzy pass) | Give each exception a starting hypothesis | Cuts human diagnosis time | P0 |
| E5 | Exception dedup / grouping | Collapse 30 identical rounding diffs into one group | Queue must be workable, not overwhelming | P0 |
| E6 | `budget-exceeded` status | Mark exceptions the AI couldn't finish in budget | Honesty; also a scorecard line | P0 |

## F. AI adjudication (the one AI step)

| ID | Feature | Job | Why | Priority |
|---|---|---|---|---|
| F1 | Claude adjudication agent for `AMBIGUOUS` / `UNEXPLAINED` only | Explain the variance + propose category + fix | Compresses human verification time — the core thesis | P0 |
| F2 | Read-only evidence tool (`query_evidence`) | Agent's only data access | No agent tool touches money | P0 |
| F3 | Structured `Proposal` output (category = spec enum) | Machine-checkable, can't invent categories | Safety + downstream automation | P0 |
| F4 | Evidence-ref citations on every claim | Each sentence links to a record field | Trust surface; verifiable | P0 |
| F5 | Draft-resolution proposal | Suggested action ("raise dispute", "carry forward", "void dup") | Turns "here's a problem" into "here's the fix" | P0 |
| F6 | Draft-rule proposal | A `when → classify/resolve` rule for this pattern | Feeds the learning loop | P1 |
| F7 | `--no-ai` full-determinism mode | Run the whole pipeline with zero LLM calls | Proves the core stands alone; also cost/offline | P0 |
| F8 | Per-exception token/time budget + accounting | Bounded cost; reported on scorecard | "AI Judgment" criterion; no runaway spend | P0 |
| F9 | Prompt versioning + hash on every proposal event | Reproducible AI behavior | Audit: "what prompt produced this?" | P0 |
| F10 | Batch-API path for `bench` runs | 50% cheaper eval | Makes frequent benchmarking affordable | P1 |

## G. Resolution & learning loop

| ID | Feature | Job | Why | Priority |
|---|---|---|---|---|
| G1 | Accept / edit / reject / won't-fix on every exception | Human decision, recorded as an event | The human is always in the loop | P0 |
| G2 | Rule synthesis from an accepted resolution | Draft a durable rule from a one-time fix | Month 3 > month 1 | P1 |
| G3 | Spec-diff review UI for drafted rules | Human approves the rule before it's live | AI-authored logic must be reviewed | P1 |
| G4 | Projected-impact preview ("97.2% → 98.6%") | Show the consequence of a resolution before re-run | Makes the loop tangible | P1 |
| G5 | Cycle-over-cycle metric history | Track auto-tied % across runs of a spec | The "it gets better" evidence | P0 |

## H. Event log, replay & audit

| ID | Feature | Job | Why | Priority |
|---|---|---|---|---|
| H1 | Append-only, hash-chained event store | Immutable record of everything | Audit survival; tamper-evidence | P0 |
| H2 | Projections rebuilt by folding events | State is always derivable | No hidden mutable state | P0 |
| H3 | `arbiter replay <run-id>` → byte-identical projections | Deterministic reconstruction | Anti-cherry-pick; debuggability | P0 |
| H4 | Full provenance on every match/exception | records + pass + rule + confidence + actor | "Why does Arbiter believe this?" always answerable | P0 |
| H5 | Export: audit pack (CSV + JSON + the run log) | Hand an auditor a self-contained package | Real deliverable finance teams need | P1 |

## I. Scorecard & benchmark

| ID | Feature | Job | Why | Priority |
|---|---|---|---|---|
| I1 | `arbiter bench` — score a run vs ground truth | Measured accuracy | The Buildathon bar | P0 |
| I2 | Metrics: auto-match rate, precision, recall, **false-match rate**, $ coverage | Honest, complete picture | Nobody else publishes false-match rate | P0 |
| I3 | Throughput reporting (records/sec, wall-clock) | "Throughput" from the bar | Required | P0 |
| I4 | LLM cost/token reporting | Cost transparency | "AI Judgment" | P0 |
| I5 | Exception histogram by type | Where the residue concentrates | Diagnostic + honest | P0 |
| I6 | `scorecard.json` + HTML report artifact in CI | Reproducible by a stranger in one command | Anti-cherry-pick | P0 |
| I7 | Regression gate (fail CI if match rate drops > X%) | Protect accuracy over time | Engineering maturity signal | P1 |

## J. Adversarial synthetic data generator

| ID | Feature | Job | Why | Priority |
|---|---|---|---|---|
| J1 | Generate N-record settlement + bank + ledger batches | The demo & test data | Track requires 50+ synthetic records | P0 |
| J2 | Injected, **labeled** anomalies: duplicate, partial/split settlement, fee drift, GST rounding, missing UTR, timing straddle, chargeback, FX, wrong-account, over/short payment, refund-netting | A real adjudication problem with known answers | Can't claim measured accuracy without labels | P0 |
| J3 | `ground_truth.json` alongside every batch | The answer key for `bench` | Enables precision/recall | P0 |
| J4 | Seeded / reproducible generation | Same seed → same batch | Determinism end-to-end | P0 |
| J5 | Difficulty dial (anomaly rate, batch complexity) | Stress-test the engine | Shows where accuracy degrades — honest | P1 |
| J6 | Scenario presets (D2C brand, marketplace, SaaS) | Realistic shapes | Relatable demo | P1 |

## K. Cockpit UI

| ID | Feature | Job | Why | Priority |
|---|---|---|---|---|
| K1 | Run header + scorecard surface | The verdict at a glance | See [05](05-design-doctrine.md) §2.1 | P0 |
| K2 | Exception queue (keyboard-first data grid) | The work surface | [05](05-design-doctrine.md) §2.2 | P0 |
| K3 | Evidence drawer (3 records + identity + rule trail + AI proposal) | The proof surface | [05](05-design-doctrine.md) §2.3 | P0 |
| K4 | Inline resolution + consequence preview | Resolve without leaving the queue | Speed | P1 |
| K5 | Cycle-trend sparkline | The "it gets better" story | Memorable | P1 |
| K6 | Light/dark parity, WCAG AA, reduced-motion | Accessibility | Non-negotiable | P0 |
| K7 | Run list / spec switcher | Navigate multiple reconciliations | Multi-loop demo | P1 |

## L. CLI & API

| ID | Feature | Job | Why | Priority |
|---|---|---|---|---|
| L1 | `arbiter gen` · `run` · `bench` · `replay` · `explain` | The proof surface for judges/CI | Judges live in the terminal first | P0 |
| L2 | `--json` on every command | Machine consumption | Scriptability | P0 |
| L3 | `make demo` — one command, full loop, cockpit open | Onboarding in 3 minutes | Evaluation friction = lost points | P0 |
| L4 | FastAPI: ingest / runs / exceptions / resolve / scorecard / replay | Cockpit backend + customer pipelines | Real integration path | P0 |
| L5 | OpenAPI docs auto-generated | Self-documenting API | Build quality signal | P1 |

## M. Post-hackathon (P2 — named so scope is explicit)

| ID | Feature | Why deferred |
|---|---|---|
| M1 | Live connectors (bank aggregators, ERP APIs, more PGs) | Connector sprawl is a deliberate v1 non-goal ([08](08-why-it-might-not-sell.md)) |
| M2 | Journal-entry posting into the ERP | "Act on money" is a trust/liability leap needing real customers first |
| M3 | Multi-tenant, auth, RBAC, billing | Not judged; distracts from the core |
| M4 | Forward cash-forecast module (off the reconciled ledger) | Only credible after recon is trusted; strong "what's next" story |
| M5 | ILP subset-sum solver (OR-Tools) | Heuristic is sufficient at demo scale |
| M6 | Real-time / streaming ingest | Batch is the track's framing |
| M7 | SOC 2 / audit certification | Needs a company, not a hackathon |
