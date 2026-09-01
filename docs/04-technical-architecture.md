# 04 — Technical Architecture

_The system, its parts, the data model, the algorithms, the AI boundary, and the decisions behind each._

---

## 1. Architectural principles (the non-negotiables)

| # | Principle | Consequence |
|---|---|---|
| P1 | **Deterministic core, AI at the boundary.** Ingestion, matching, decomposition, scoring and replay contain zero LLM calls. The LLM is invoked for one bounded step and only ever produces gated proposals. | Reproducibility, auditability, testability, cost control, and direct alignment with the Buildathon "AI Judgment" criterion. |
| P2 | **Event-sourced. Append-only. Nothing is mutated.** Every ingest, match, classification, proposal and human decision is an immutable event with a hash chain. Current state is a fold over events. | `arbiter replay <run-id>` reconstructs any run byte-for-byte. Audit survival. Anti-cherry-pick guarantee. |
| P3 | **The recon logic is data, not code.** A YAML _recon spec_ defines sources, keys, tolerances, taxonomy and rules. The engine is generic. | Loop-agnostic (settlement / bank-to-book / GST). Customer-authored, git-diffable logic. Rules learned from human resolutions are just spec appends. |
| P4 | **Every match and every exception carries its provenance.** Which records, which pass, which rule, which confidence, which human, which model+prompt hash. | You can always answer "why does Arbiter believe this?" |
| P5 | **Local-first, zero-config demo.** `make demo` runs the whole system on SQLite with seeded data, no cloud, no keys except one optional `ANTHROPIC_API_KEY`. | A judge evaluates it in 3 minutes. Also the honest scope boundary (no multi-tenant/auth in v1). |
| P6 | **Money math is exact.** All amounts are integer minor units (paise). `Decimal` only at IO edges. No floats in the matching or decomposition path. | No float-drift false exceptions. |

---

## 2. System overview

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│  CLIENTS                                                                          │
│  ┌────────────────┐   ┌──────────────────────────┐   ┌───────────────────────┐    │
│  │ arbiter CLI    │   │ Cockpit (Next.js/React)  │   │ CI (GitHub Actions)   │    │
│  │ (Typer)        │   │ triage · evidence · score│   │ bench → scorecard.json│    │
│  └───────┬────────┘   └────────────┬─────────────┘   └───────────┬───────────┘    │
│          │                         │ REST/JSON                    │               │
│          └──────────────┬──────────┴──────────────────────────────┘               │
│                         ▼                                                          │
│  ┌────────────────────────────────────────────────────────────────────────────┐   │
│  │  API LAYER  — FastAPI + Pydantic v2                                          │   │
│  │  /ingest  /runs  /runs/{id}/exceptions  /exceptions/{id}/resolve            │   │
│  │  /runs/{id}/scorecard   /runs/{id}/replay   /specs                          │   │
│  └───────────────────────────────────┬────────────────────────────────────────┘   │
│                                      ▼                                             │
│  ┌────────────────────────────────────────────────────────────────────────────┐   │
│  │  ENGINE  (arbiter_engine, pure Python, no web deps)                          │   │
│  │                                                                             │   │
│  │  ingest/      normalize → canonical Record; dedupe; file-hash guard          │   │
│  │  specs/       load & validate recon spec (Pydantic); rule compiler           │   │
│  │  match/       pass 1 exact · pass 2 tolerant · pass 3 set/subset · pass 4    │   │
│  │               fuzzy;  confidence model;  candidate ranking                   │   │
│  │  decompose/   settlement identity solver (net = gross−MDR−GST−ref−cb±round)  │   │
│  │  exceptions/  taxonomy · deterministic classifier · $-impact ranking        │   │
│  │  agent/       Claude adjudication (proposals only) · tool surface           │   │
│  │  learn/       resolution → candidate rule synthesis                          │   │
│  │  events/      append-only store · hash chain · fold · replay                 │   │
│  │  bench/       ground-truth scorer · metrics · report                         │   │
│  └───────────────────────────────────┬────────────────────────────────────────┘   │
│                                      ▼                                             │
│  ┌────────────────────────────────────────────────────────────────────────────┐   │
│  │  STORE   SQLite (demo)  |  Postgres (real)   — same SQLModel schema          │   │
│  │  events (append-only, hash-chained) · projections (matches, exceptions,     │   │
│  │  records) rebuilt from events · specs · runs                                 │   │
│  └────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                   │
│  datagen/  adversarial synthetic batch generator (separate package)               │
│            → sources/*.csv  +  ground_truth.json                                   │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. The deterministic / AI boundary (P1 in detail)

This is the most important design decision and the one most directly judged. It is stated as an ADR: [`docs/adr/0001-deterministic-core.md`](adr/0001-deterministic-core.md).

### 3.1 What is deterministic

| Step | Method | Why not AI |
|---|---|---|
| Parse & normalize | Declared column maps, format detection, `Decimal`→paise | An LLM parsing financial CSVs introduces silent transcription errors; formats are finite and declarable |
| Dedupe | Content hash + business-key hash | Exact, cheap, auditable |
| Match pass 1–3 | Set logic, tolerance arithmetic, bounded subset-sum | These have _correct answers_; non-determinism here is a bug |
| Settlement decomposition | Algebra against the identity | It's arithmetic. An LLM doing arithmetic is a liability |
| Confidence scoring | Explicit weighted formula (§6) | Must be reproducible and explainable to an auditor |
| Exception classification (clear cases) | Rule predicates from the spec | If a rule can decide it, a rule should decide it |
| Scorecard | Counting against ground truth | Measurement must not be model-dependent |
| Replay | Event fold | Definitionally deterministic |

### 3.2 What uses the LLM — exactly one step

**Adjudication of exceptions the deterministic classifier tagged `AMBIGUOUS` or `UNEXPLAINED`.**

- **Model:** `claude-opus-5` (adaptive thinking) for adjudication; `claude-haiku-4-5` optional for a cheap first-pass triage on large batches. Model id + prompt hash recorded on every proposal event.
- **Input:** a compact evidence bundle (the unmatched record(s), the top candidate matches with scores, the relevant spec rules, the decomposition residual). Never the raw files.
- **Tools available to the agent (all read-only or proposal-only):**
  - `query_evidence(record_id | filters)` → related records, prior matches, prior exceptions for this counterparty
  - `propose_category(exception_id, category, rationale)` → writes a proposal event (category constrained to the spec taxonomy via structured output)
  - `draft_resolution(exception_id, action, detail)` → proposal event
  - `draft_rule(pattern, action)` → candidate-rule proposal event
- **Output contract:** a `Proposal` object — `{category, confidence, explanation, evidence_refs[], suggested_action, draft_rule?}` — validated against a strict schema. Malformed → discarded, exception stays `UNEXPLAINED`, logged.
- **Hard guarantees:**
  1. No agent tool mutates a match, a record, a ledger, or money.
  2. Every proposal is written as an event and shown in the queue with an "AI proposed" badge.
  3. A human accept/edit/reject is required before a proposal affects anything.
  4. The agent is time- and token-budgeted per exception; on budget exhaustion the exception stays unresolved and is marked so (a scorecard line: "N exceptions exceeded adjudication budget").
  5. Full determinism mode: `arbiter run --no-ai` skips this step entirely; the scorecard still computes. Proves the core stands alone.

### 3.3 Why this is the right call (and not timidity)

The verification-bottleneck thesis ([01](01-market-and-thesis.md) §2.1) says: generation is cheap, _trusting_ generation is the cost. So the correct use of an LLM is not to generate the answer — it's to **compress the human's verification time** by explaining the variance and proposing the fix, while keeping the decision and the arithmetic in deterministic, replayable code. Arbiter is architected as a direct expression of that thesis.

---

## 4. Data model

All tables via SQLModel (SQLAlchemy core); identical DDL on SQLite and Postgres.

### 4.1 `events` — the source of truth (append-only)

| col | type | note |
|---|---|---|
| `id` | int PK | monotonic |
| `run_id` | uuid | groups a reconciliation run |
| `seq` | int | per-run sequence |
| `ts` | datetime | wall clock (informational only; not used in logic) |
| `type` | str | `RECORD_INGESTED` · `MATCH_PROPOSED` · `MATCH_CONFIRMED` · `DECOMPOSITION_COMPUTED` · `EXCEPTION_OPENED` · `AI_PROPOSAL_CREATED` · `RESOLUTION_APPLIED` · `RULE_DRAFTED` · `RULE_MERGED` |
| `payload` | json | type-specific, schema-versioned |
| `actor` | str | `engine` · `agent:claude-opus-5@<prompthash>` · `human:<id>` |
| `prev_hash` | str | sha256 of previous event |
| `hash` | str | sha256(prev_hash + canonical(payload)) |

Projections (`records`, `matches`, `exceptions`, `decompositions`) are **derived** — dropped and rebuilt by folding events. Never written directly by business logic.

### 4.2 `Record` (canonical, post-normalization)

```
Record:
  id: str                     # deterministic: sha256(source, source_row_id, run_id)[:16]
  source: str                 # "razorpay_settlement" | "bank" | "ledger"
  kind: str                   # "payout" | "credit" | "order" | "refund" | "fee" | "chargeback"
  amount_minor: int           # paise, signed (credit +, debit −)
  currency: str
  value_date: date
  posted_date: date | None
  counterparty: str | None
  reference: str | None       # UTR / settlement_id / order_id / free text
  external_ids: dict          # {settlement_id, order_id, payment_id, utr, ...}
  raw: dict                   # original row, untouched
  ingest_file_hash: str
```

### 4.3 `RecordSpec` / `ReconSpec` (the YAML, validated)

See §5.

### 4.4 `Match`

```
Match:
  id: str
  run_id: str
  left: list[str]             # record ids (a set — supports N:M)
  right: list[str]
  pass: str                   # "exact" | "tolerant" | "subset" | "fuzzy"
  confidence: float           # 0..1, from §6 formula
  rule_id: str | None         # which spec rule fired
  residual_minor: int         # unexplained amount after decomposition (0 = clean)
  status: str                 # "auto" | "low_confidence" | "human_confirmed"
```

### 4.5 `Exception`

```
Exception:
  id: str
  run_id: str
  records: list[str]
  category: str | None        # from spec taxonomy; null until classified
  classified_by: str          # "rule:<id>" | "agent" | "unclassified"
  amount_impact_minor: int    # signed $ at stake — drives ranking
  confidence: float
  candidates: list[{match_hypothesis, score}]   # from fuzzy pass
  ai_proposal: Proposal | None
  resolution: Resolution | None
  status: str                 # "open" | "proposed" | "resolved" | "wont_fix" | "budget_exceeded"
```

---

## 5. The recon spec (P3)

A single YAML file fully describes a reconciliation. Example (`specs/razorpay-settlement.yaml`, abridged):

```yaml
name: razorpay-settlement
version: 3
description: Razorpay settlement report ↔ bank credits ↔ order ledger

sources:
  razorpay_settlement:
    format: csv
    columns: { amount: settlement_amount, fee: fee, tax: tax, ... }
    id_fields: [settlement_id, order_id, payment_id]
    amount_scale: rupees_to_paise
  bank:
    format: csv            # or mt940
    columns: { amount: amount, value_date: value_dt, reference: narration }
    id_fields: [utr]
  ledger:
    format: csv
    columns: { amount: order_total, date: order_date }
    id_fields: [order_id]

identity:                  # the decomposition Arbiter must verify
  target: bank.credit
  formula: "sum(ledger.order_total) - sum(razorpay.fee) - sum(razorpay.tax) - sum(razorpay.refund) - sum(razorpay.chargeback)"
  rounding_tolerance_minor: 100     # ₹1

passes:
  exact:
    - key: [razorpay.settlement_id == bank.utr_ref, bank.value_date, net_amount]
  tolerant:
    - amount_tolerance_minor: 200
      date_window_days: 4            # T+2 + weekend
  subset:
    - group_by: razorpay.settlement_id
      solve_for: bank.credit
      apply: identity
  fuzzy:
    - weigh: { reference_jaro: 0.4, amount_prox: 0.3, date_prox: 0.2, counterparty: 0.1 }

thresholds: { auto: 0.90, review: 0.70 }

taxonomy:
  - FEE_DEDUCTION
  - TAX_DEDUCTION
  - ROUNDING
  - PARTIAL_PAYMENT
  - TIMING            # straddles period boundary
  - DUPLICATE
  - CHARGEBACK
  - FX_DIFFERENCE
  - MISSING_UTR
  - WRONG_ACCOUNT
  - UNEXPLAINED

rules:                   # deterministic classifiers + auto-resolutions
  - id: r_rounding
    when: "exception.residual_minor != 0 and abs(exception.residual_minor) <= 100"
    classify: ROUNDING
    resolve: accept_variance
  - id: r_timing_month_end
    when: "unmatched(bank) and record.value_date.day <= 3 and exists(ledger match in prior period)"
    classify: TIMING
    resolve: carry_forward
  # rules appended by the learning loop land here, with provenance comments
```

**Rule compiler:** `when` expressions are parsed into a small safe AST (no `eval`); supported ops are a fixed whitelist (comparisons, `abs`, `exists`, `unmatched`, field access). This keeps customer/AI-authored rules safe and analyzable.

---

## 6. The matching algorithm

### 6.1 Confidence formula (explicit, per Match)

```
confidence = w_key · key_agreement
           + w_amt · amount_score          # 1 − min(1, |Δ| / tolerance)
           + w_date · date_score           # 1 − min(1, |Δdays| / window)
           + w_ref · reference_similarity   # Jaro-Winkler on normalized refs
           + w_id  · shared_external_id      # 1 if any external id matches, else 0
  where weights are declared in the spec and sum to 1;
  pass 1 (exact) forces confidence = 1.0 when all hard keys agree.
```

### 6.2 Set / subset pass (the hard one)

Problem: one bank credit `C` must equal `Σ orders − Σ fees − Σ taxes − Σ refunds` for some subset `S` of currently-unmatched ledger orders sharing a settlement batch.

Approach:
1. Restrict candidates to orders whose `settlement_id` (if present) equals the settlement's, else to orders within the settlement window.
2. Apply the per-order fee/tax model (from the settlement report's per-line fee, or the spec's fee schedule).
3. Solve subset-sum with tolerance via meet-in-the-middle for |candidates| ≤ 40, else a greedy + local-search heuristic, both bounded by a wall-clock budget.
4. Unique solution within tolerance → `subset` match, confidence from §6.1 with a penalty for tolerance consumed. Multiple solutions → exception `AMBIGUOUS` with the candidate subsets attached. No solution → exception `UNEXPLAINED` or `PARTIAL_PAYMENT`.

### 6.3 Determinism

All passes sort inputs by `Record.id` before iterating. No dict-ordering dependence. No wall-clock in logic. Same inputs + same spec + same seed → identical events.

---

## 7. The adjudication agent (implementation)

- **SDK:** `anthropic` Python SDK, `client.messages.create` with `thinking={"type":"adaptive"}`, `output_config={"effort":"medium"}` for routine exceptions, `"high"` for `UNEXPLAINED`.
- **Tool loop:** the SDK beta tool runner (`client.beta.messages.tool_runner`) with the 4 tools in §3.2; `max` ~6 tool turns per exception.
- **Structured output:** the final `Proposal` is produced via `output_config={"format": {...}}` against the strict JSON schema — category is an enum of the spec taxonomy, so the model cannot invent a category.
- **Prompt:** a frozen system prompt (hashed, versioned in `agent/prompts/`) that states: you explain variances and propose fixes; you never assert a match; cite evidence ids for every claim; if evidence is insufficient say so and stop.
- **Batching:** exceptions are adjudicated concurrently (async) with a semaphore; the Message Batches API is used for `arbiter bench` runs to cut cost 50%.
- **Cost control:** per-run token budget; `usage` accumulated and reported on the scorecard (`llm_cost_usd`, `llm_tokens_in/out`, `exceptions_adjudicated`).
- **Caching:** the frozen system prompt + spec + taxonomy are a stable cache prefix (`cache_control`), so per-exception marginal cost is just the evidence bundle + output.
- **Refusal handling:** `stop_reason == "refusal"` → exception stays `UNEXPLAINED`, logged; server-side fallback enabled per the current SDK guidance.

---

## 8. Technology choices & rationale

| Layer | Choice | Why this, not the alternative |
|---|---|---|
| Engine language | **Python 3.12** | The reconciliation/data ecosystem (Polars, pandas, `python-dateutil`, `rapidfuzz`), first-class Anthropic SDK, fast to write and test. Not Go/Rust: the bottleneck is correctness and iteration speed, not raw throughput, at 50–5000 records. |
| Numeric | **integer paise + `Decimal` at edges** | Floats cause phantom exceptions. Non-negotiable in finance code. |
| Data wrangling | **Polars** | Fast, immutable, lazy; expressive joins for the matching passes; smaller memory than pandas. pandas kept only for odd file parsing. |
| Validation | **Pydantic v2** | Spec validation, API models, the `Proposal` schema, structured-output schema — one tool for all. |
| Store | **SQLModel over SQLite (demo) / Postgres (real)** | One schema, zero-config demo, real deployment path. Event-sourced tables need only INSERT + range scans — SQLite is genuinely fine for the demo scale. |
| API | **FastAPI** | Async (for concurrent adjudication), Pydantic-native, auto OpenAPI for the cockpit. |
| CLI | **Typer** | Same types as the API; the CLI is the primary proof surface for judges/CI. |
| Agent | **Anthropic SDK + `claude-opus-5`** | Frontier reasoning for variance explanation; adaptive thinking; strict structured outputs; batch API for cheap bench. `claude-haiku-4-5` for optional bulk triage. |
| Frontend | **Next.js 15 (App Router) + React + TypeScript** | SSR for fast first paint of the run view; mature table/query ecosystem; one language for the whole UI. |
| UI kit | **Tailwind + shadcn/ui + Radix** | Accessible primitives, fast to build a dense, keyboard-driven cockpit, themeable (see [05](05-design-doctrine.md)). |
| Tables | **TanStack Table + TanStack Query** | The exception queue is a serious data grid: sorting, grouping, keyboard nav, server state. |
| Charts | **visx** (or Recharts) | The scorecard and cycle-trend need control; visx composes cleanly. Follows the `dataviz` skill palette. |
| Packaging | **uv** (Python), **pnpm** (JS), **Makefile** + **docker-compose** | `make demo` is the whole onboarding story. |
| CI | **GitHub Actions** | Runs `pytest` + `arbiter bench` on every push; uploads `scorecard.json` + an HTML report as an artifact and comments the key metrics on the PR. |
| Tests | **pytest + hypothesis** | Property tests on the matcher (e.g. "a matched set's decomposition residual is ≤ tolerance"); golden-file tests on full runs; a determinism test (`run twice → identical event hashes`). |

---

## 9. Repo structure

```
arbiter/
├── README.md
├── Makefile                      # make demo / test / bench / up
├── docker-compose.yml
├── pyproject.toml                # uv workspace
├── docs/                         # this folder
│   └── adr/                      # architecture decision records
├── packages/
│   ├── engine/
│   │   ├── arbiter_engine/
│   │   │   ├── ingest/  specs/  match/  decompose/
│   │   │   ├── exceptions/  agent/  learn/  events/  bench/
│   │   │   └── cli.py            # `arbiter` entrypoint (Typer)
│   │   └── tests/
│   ├── datagen/
│   │   └── arbiter_datagen/      # adversarial batch generator
│   └── api/
│       └── arbiter_api/          # FastAPI app
├── web/                          # Next.js cockpit
├── specs/
│   ├── razorpay-settlement.yaml  # reference spec
│   └── gst-2b.yaml               # proof-of-generality spec
├── datasets/
│   └── seed/                     # small committed demo batch + ground truth
└── .github/workflows/ci.yml
```

---

## 10. Non-functional targets

| Property | Target | How verified |
|---|---|---|
| Throughput | ≥ 500 records/run in < 20 s (excl. LLM); ≥ 50 records is the floor per the track | `bench` reports wall-clock |
| Determinism | 100% — two runs, identical event hash chain | CI determinism test |
| LLM cost | < $0.05 per exception adjudicated (with caching + batch) | scorecard `llm_cost_usd` |
| Replay fidelity | byte-identical projections | `arbiter replay` diff test |
| Cold start | `make demo` → cockpit open in < 3 min on a laptop | documented, timed |
| Test coverage | engine ≥ 85% lines; matcher & decompose ≥ 95% | `pytest --cov` in CI |

---

## 11. Known architectural gaps (stated, not hidden)

| Gap | Why acceptable for v1 | Post-hackathon path |
|---|---|---|
| No auth / multi-tenant / RBAC | Not judged; local-first demo | Add org model + row-level security on Postgres |
| No live bank/ERP connectors | Connector sprawl is a deliberate non-goal ([08](08-why-it-might-not-sell.md)) | Connector SDK; start with Razorpay API + one bank aggregator |
| Subset-sum heuristic above 40 candidates | Real settlement batches are usually smaller per `settlement_id`; heuristic is bounded and flagged | ILP solver (OR-Tools) behind the same interface |
| Single-node, in-process | Demo scale | Queue (the engine is already event-driven) + workers |
| No streaming ingest | Batch is the track's framing | The event store already supports incremental folds |
