# Arbiter — Full Project DNA (strategy consult brief)

_Last updated 2026-09-04 (rev. 4 — folds in the agent trajectory benchmark
(`arbiter agent-bench`), a harness fix it surfaced (SAFE is now *earned*), the `get_record`
tool, cost/calibration honesty, the structured investigation UI, and the buildathon doc
package; rev. 3 added the Safety Kernel, Attack Arbiter, headline safety metrics,
clustering, the exception state machine, and the seven consolidated root docs). This file
is written for an external strategy advisor (ChatGPT). It is the single self-contained
document that explains what Arbiter is, what is actually built, what the research says, and
where the people inside the project already believe the plan is weak._

---

## 0. How to read this — and what I want from you

I am the founder / sole builder. Arbiter started as a submission for the **Razorpay AI
Buildathon 2026** (in-person, Bangalore; ₹75k/month student stipend; "code speaks louder
than your resume"), track **AI Finance Controller**. I want it to become a real product /
company, not just a hackathon entry.

### 0.5 Reality check — team, timeline, traction (read this before §10)

- **Team:** one person. No co-founder, no employees.
- **Timeline:** the entire codebase below — ~14k lines, 100 commits, engine + agent + API +
  cockpit + a full production-hardening roadmap + a fail-closed safety layer built against a
  93-section hardening spec — was built in **roughly 4–5 days** of intense work with heavy
  AI pair-programming. That speed is real and worth weighing both ways: it shows unusual
  execution throughput, *and* it means almost nothing has been pressure-tested by time,
  users, or a second engineer.
- **Funding:** none. **Revenue:** none. **Users:** zero. **Design partners:** zero.
- **Validation to date:** synthetic benchmarks the builder wrote, plus one public demo. No
  customer conversation has happened. No real bank statement has been reconciled.
- **The forcing function:** the Buildathon submission. Everything after that is a choice
  (§11 Q1).

**I am not asking you to validate the current plan.** Several people and processes inside
this project have already tried that and concluded — in specific, evidenced ways — that the
commercial thesis is shaky. Those findings are in §10, stated plainly rather than hidden.

Treat this as a **strategy consult, not a pitch to approve.** The thing this project has
been avoiding is *picking a direction and cutting hard*. I want your help doing that, using
the research below as the evidence base rather than my intuition or my attachment to what
I've built.

Concretely, what I want from you is in §12. Read §10 and §11 most carefully.

---

## 1. One-line pitch

**Arbiter is a verification layer for money movement.** It closes one finance-ops loop end
to end — reconciling a payment processor's settlement report against the bank statement and
the order ledger across a batch — reports an *honest* match rate (including the false-match
rate), and hands back a categorized, evidence-backed list of the exceptions it could not
resolve, each with a proposed fix.

It is deliberately **not** "an AI that does your accounting." It is a machine that shrinks
the set of things a human still has to look at, and proves how much it shrank them.

The demo sentence: _"Here are three files, tell me if the money is right"_ becomes
_"93.8% tied automatically, ₹1.73 lakh across 9 exceptions still need you — here's each one,
the evidence, and what I think it is."_

---

## 2. The core bet

Four linked claims. If any is wrong, the product is wrong.

1. **Verification, not generation, is the 2026 bottleneck.** LLMs made *producing* output
   nearly free; *trusting* output stayed expensive and stayed sequential. Finance-ops is
   the purest enterprise instance: the output ("the books are right") must be *verified*
   because someone signs it, an auditor tests it, a regulator can penalize it. That is why
   finance automation lagged despite decades of software — the bottleneck was never data
   entry, it was assurance.

2. **The right use of an LLM here is to compress human verification time, not to make the
   decision.** So the architecture is: **deterministic core, AI only at the ambiguity
   boundary, every AI output a gated proposal, `--no-ai` always works.** The LLM explains a
   variance and proposes a fix; a human confirms; the arithmetic and the matching stay in
   replayable code.

3. **The buyable thing is the assurance artifact, not the automation.** "Prove, every
   month, that the money ties — with evidence a board or an auditor accepts." Automation is
   *how* it's produced; assurance is *what's sold*.

4. **Neutrality is the wedge.** Every bundled reconciliation tool (Razorpay Smart Collect,
   Stripe, every ERP) reconciles *its own rail*. The real user has 2+ processors + a bank +
   an ERP + a tax register. Arbiter is the only thing that ties *all of them* with *one
   audit trail*.

**The uncomfortable part:** claims 1 and 2 are on solid ground and are also what the
Buildathon rewards. Claims 3 and 4 are the *commercial* bet, and they are where the
internal red-team keeps finding problems (§10).

---

## 3. Target user

### Primary persona — "the multi-rail controller"

| Attribute | Value |
|---|---|
| Company | D2C brand or marketplace, ₹5 Cr–₹200 Cr annual GMV, 30–200 people |
| Rails | Razorpay + (Cashfree \| PayU \| marketplace payouts \| COD remittance) + 1–2 banks + Tally/Zoho/NetSuite |
| Buyer | Financial Controller / Finance Manager (owns the monthly close) |
| Trigger | a botched close, an audit finding on reconciliations, a discovered processor overcharge, or a finance hire who refuses to work in spreadsheets |
| Pain today | 2–5 person-days/month; no confidence in the auto-matched pile; input-tax-credit leakage; processor overcharges uncaught |
| Willingness to pay | ₹15k–₹60k/month (vs. 0.3–0.7 FTE ≈ ₹40k–₹120k/month loaded) |

### Secondary persona — "the outsourced controller / CA firm"

Buys tools to serve more clients per accountant; no internal org-change needed; values the
per-client recon spec and the billable Close Memo. Lower ACV, higher volume, faster sale.
B2B2C. **Arguably the better business, a worse pitch narrative.**

### Explicitly NOT the target (first 18 months)

- Single-processor, single-bank micro-businesses — the bundled tool is genuinely good enough.
- Enterprises with an existing BlackLine / audit relationship — trust-monopoly wall.
- Pure GST-2B-only buyers — bad unit economics; GST is a proof-of-generality spec, not the wedge.

---

## 4. Business model

**Open-core.** Engine, CLI, benchmark, and recon specs are Apache-2.0 and free. Revenue is
the hosted cockpit + connectors + team collaboration.

| Tier | Price | For | Includes |
|---|---|---|---|
| OSS / self-host | ₹0 | engineers, CA firms who'll run the CLI | engine, `bench`, specs, file ingest, CLI, Close Memo |
| Solo | ₹9,000/mo | founder-led finance, 1 seat | hosted cockpit, 2 rails, monthly cycle, email support |
| Team | ₹29,000/mo | the primary ICP | 5 seats, unlimited rails, the learning loop + rule review, streaming cockpit, audit-pack export |
| Firm | ₹19,000/mo per client bundle (min 5) | outsourced controllers / CA firms | multi-client workspaces, white-label memo, per-client specs |
| Connectors | usage add-on | anyone wanting live pulls | Razorpay API, bank aggregator, ERP sync — priced per connected source |

**Benchmark:** FloQast runs ~$125–150/user/mo (~$12k–24k/yr typical). Arbiter's Team tier
(~₹3.5L/yr ≈ $4.2k) is deliberately an order of magnitude below the enterprise suites and
roughly at parity with a fractional analyst.

**Unit-economics hypotheses (unvalidated):** ACV ₹3.5L, gross margin ~80% (LLM + hosting is
the variable line), CAC ₹40k–80k (content + founder-led sales + CA-firm partnerships, no
paid acquisition), payback 4–8 months, target logo churn < 2%/mo, NRR 115–130% via
rails + seats + connectors. First real cost data point (§6.1): one agent investigation ≈
20k tokens ≈ $0.05–0.10; a close with 5–10 hard exceptions is well under $1 in LLM spend,
so the LLM line is small — *if* the exception count stays bounded, which cold-start (R9)
works against.

**Sales motion:** OSS top-of-funnel → self-serve Solo → founder-led Team (run their real
month's export live, hand them the memo + the found-money number) → CA-firm partnerships.
No enterprise motion, no SDRs, no RFPs in year one.

**Retention mechanic:** the accumulated rule set + audit history. Switching cost that
compounds monthly, built the honest way (their data, their rules, exportable).

---

## 5. Design doctrine

### 5.1 Product doctrine (non-negotiables)

| # | Principle | Consequence |
|---|---|---|
| P1 | Deterministic core, AI at the boundary | ingestion, matching, decomposition, scoring, replay contain **zero** LLM calls; the LLM produces only gated proposals |
| P2 | Event-sourced, append-only, nothing mutated | every ingest / match / classification / proposal / human decision is an immutable hash-chained event; state is a fold; `replay` reconstructs a run byte-for-byte |
| P3 | The recon logic is data, not code | a YAML recon spec defines sources, keys, tolerances, taxonomy, rules; the engine is generic and loop-agnostic; learned rules are just spec appends |
| P4 | Every match and exception carries its provenance | which records, which pass, which rule, which confidence, which human, which model + prompt hash |
| P5 | Local-first, zero-config demo | `make demo` runs the whole system on SQLite with seeded data; a judge evaluates it in 3 minutes |
| P6 | Money math is exact | integer minor units (paise) everywhere; `Decimal` only at IO edges; no floats in matching or decomposition |

### 5.2 Interface doctrine — "one run, three surfaces"

A reconciliation **run** is the atomic unit. Three surfaces, in workflow order:

1. **Scorecard (the verdict)** — auto-tied %, ₹ tied vs ₹ open, a coverage bar by *rupees*
   not count, precision/recall/false-match when ground truth exists, exceptions by type, a
   cycle-over-cycle sparkline (the "it gets better" story).
2. **Exception queue (the work)** — a dense, keyboard-first data grid. One row per
   exception: type chip, ₹ impact (primary sort), confidence bar, one-line hypothesis,
   source badges, status, inline resolve. `j/k` move, `a` accept, `r` reject, `w` won't-fix,
   `/` filter, `g` group. A power user clears 40 exceptions without a mouse.
3. **Evidence drawer (the proof)** — the trust surface. Three record cards side by side with
   matching fields aligned; the decomposition rendered as an equation with real numbers and
   the residual called out; the rule trail in plain sentences; the AI proposal badged
   "proposed by Arbiter · &lt;model&gt;" (claude-opus-5 or gpt-4o) with every factual claim
   linked to an evidence id; Accept / Edit & accept / Reject / Won't fix.

Three words govern every screen: **Calm. Legible. Fast.** Muted warm ground, exactly one
accent, amber-not-red for exceptions (an unreconciled item is *work*, not a *failure*).
Full light/dark parity, WCAG 2.2 AA, `prefers-reduced-motion` honored. The CLI is designed
with the same care — judges and engineers meet Arbiter through the terminal first.

### 5.3 Voice

Status vocabulary is closed (`auto-tied`, `low-confidence`, `exception`, `open`, `proposed`,
`resolved`, `won't-fix`, `budget-exceeded` — never synonyms). Numbers always carry unit and
sign. AI text is always attributed and always hedged ("Likely…", "Consistent with…", "No
evidence for…"). No dark patterns.

---

## 6. Feature inventory (what is actually built)

Status legend: **✅ built + tested + in CI** · ◑ partial · ○ roadmap.

### Ingestion & data integrity
- ✅ Multi-format parsers: **CSV** (delimiter sniff, encoding fallback, header auto-detect,
  totals-row stripping), **XLSX/XLSM** (openpyxl), **MT940** (`:61:`/`:86:` tag parser,
  dependency-free), **ISO 20022 CAMT.053** (stdlib XML), **PDF text-layer** (pypdf, pure
  Python). All emit the same canonical row keys as a CSV source.
- ✅ Declared column mapping in the spec; currency & scale normalization → integer paise.
- ✅ **Multi-currency + FX**: a row whose currency ≠ base is converted at ingest, original
  kept; an unrated currency is quarantined; an FX-line settlement residual within ~2% is
  classified `FX_DIFFERENCE`.
- ✅ Duplicate-file / duplicate-row guard (content hash); ingest validation report ("3 rows
  missing dates — fix and re-ingest"); CSV formula-injection neutralization (export-only);
  PII / card-number scrub at ingest.
- ○ **OCR for scanned PDFs** (no text layer) — raises a clear error today; needs tesseract +
  real scanned fixtures.
- ○ Live API connectors (Razorpay Settlements API, bank aggregators, ERP APIs) — none built.

### Recon spec & rules
- ✅ YAML recon spec (sources, keys, tolerances, identity formula, taxonomy, thresholds,
  rules); Pydantic validation with helpful errors; spec versioning.
- ✅ **Safe rule expression language** — `when:` predicates parsed to a small whitelisted AST
  (no `eval`, no imports, no dunder); customer- and AI-authored rules are safe to run and
  analyze.
- ✅ Reference spec `razorpay-settlement.yaml`; proof-of-generality spec `gst-2b.yaml`.

### Matching engine
- ✅ **8 passes**: exact key → tolerant (amount band, date window) → subset-sum (1 credit ↔
  N orders, meet-in-the-middle ≤ ~40 candidates, heuristic + wall-clock budget above) →
  fuzzy candidate scoring → blocked (amount+date greedy when the UTR key fails) → aggregate
  N:1 → aggregate 1:N → **cross-period carry-forward** (a late credit that ties a *prior
  run's* still-open batch → `TIMING`, replay-safe).
- ✅ **Fellegi–Sunter** probabilistic scoring with domain-prior m/u probabilities;
  Jaro-Winkler on normalized references; explicit weighted confidence formula per match;
  low-confidence tier surfaced separately.
- ✅ **FS m/u table persists per spec hash** and **retrains from confirmed matches behind a
  ROC-AUC eval gate** — a candidate model must beat the incumbent on a held-out split by a
  margin or it is rejected; both outcomes are logged events.
- ✅ **Counterparty entity resolution** — `canonical_entity` folds legal forms, honorifics,
  bank prefixes, punctuation to one key; wired into the fuzzy matcher, the resolution
  memory, and counterparty history.
- ✅ Deterministic ordering — all passes sort by record id; no wall-clock in logic; same
  inputs + spec + seed → identical event hash chain.

### Settlement decomposition
- ✅ Identity solver `net = Σ gross − Σ MDR − Σ GST-on-MDR − Σ refunds − Σ chargebacks ±
  rounding`, verified per settlement-UTR group; residual computed on every match; a
  total-match that doesn't decompose becomes an exception.
- ✅ Per-line fee/tax attribution; fee-schedule fallback; overcharge / undercharge
  detection (the "money found" line).

### Exception taxonomy & triage
- ✅ Fixed 11-type taxonomy per spec; deterministic classifier (spec rules + built-in
  heuristics); ₹-impact ranking; candidate attachment from the fuzzy pass; dedup/grouping;
  `budget-exceeded` status.
- ✅ **Root-cause clustering** (`exceptions/cluster.py`, `arbiter clusters`, `GET
  /v1/runs/{id}/clusters`, cockpit panel) — groups a run's open exceptions by a
  deterministic key `(category, rule_id, residual direction, magnitude band)` and sums the ₹
  per group, largest first. A controller sees "5 root causes, ₹X each" instead of 80 rows;
  an LLM may only label a cluster, never set the numbers.
- ✅ **Validated status state machine** (`exceptions/state.py`) — `open → proposed /
  escalated / security_review / budget_exceeded → resolved / wont_fix`; `resolved` and
  `wont_fix` are terminal. Wired into both resolve paths; the API returns **409** on an
  illegal transition instead of silently appending a second resolution to a closed exception.

### The AI investigation agent (the one AI step)
- ✅ **Hybrid-orchestration agent**: a deterministic FSM skeleton (`INGESTING → MATCHING →
  DECOMPOSING → CLASSIFYING → INVESTIGATING → SCORING → REPORTING`) + **one bounded agentic
  loop** per `AMBIGUOUS` / `UNEXPLAINED` exception: PLAN → INVESTIGATE (iterative read-only
  tool calls) → HYPOTHESIZE & TEST (actively seek disconfirming evidence) → DECIDE (optimal
  stopping: conclude with a `Proposal`, or `Escalate` with the one sharpened question).
- ✅ 5–8 read-only / proposal-only tools (`query_evidence`, `counterparty_history`,
  `similar_exceptions`, `candidate_matches`, `decomposition_detail`, …). **No tool mutates a
  match, a record, a ledger, or money.**
- ✅ Strict structured output — `Proposal.category` is an enum of the spec taxonomy; the
  model cannot invent a category. Turn budget (6) + per-exception token budget (12k) +
  per-run cost ceiling.
- ✅ Frozen, hashed, versioned system prompt; model id + prompt hash + fenced evidence-bundle
  hash on every proposal event. Untrusted record content (`description`, `notes`, bank
  narration) is `<untrusted-data>`-fenced.
- ✅ **Grounding enforcement** — every `evidence_ref` must resolve to a real record/field or
  the proposal is voided and escalated; a deterministic category ↔ action check;
  `grounded_confidence` is re-derived from how the citations hold up, never the model's raw
  self-assessment.
- ✅ **2nd-model verifier pass** — a grounded proposal above a ₹ threshold is shown to an
  independent model with the *resolved* cited records; `{supported: false}` → escalation.
- ✅ **Tiered triage** — a small model handles low-₹ non-`UNEXPLAINED` exceptions, the large
  model the rest; per-category reasoning effort.
- ✅ **Self-consistency** — exceptions above a ₹ threshold run N samples and majority-vote the
  category; no majority → `inconsistent` escalation. Only the winning run persists so replay
  is a single pass.
- ✅ `--no-ai` full-determinism mode; deterministic escalation when no API key is set.
- ✅ Every LLM request/response recorded as an `AGENT_INTERACTION` event → `replay` replays
  recorded turns instead of re-calling the API.
- ✅ **Provider-pluggable** — an `OpenAIClient` adapter (same `Turn` contract as the
  Anthropic client) so the loop can run on GPT models; a per-run **bring-your-own-key**
  path (the cockpit sends provider + key + model as request headers, used for that one run,
  never persisted).

### Safety layer — the deterministic gate on the AI

- ✅ **Safety Kernel** (`arbiter_engine/safety/`) — a single **pure, deterministic,
  versioned** function `evaluate(proposal, exception, snapshot, grounding, policy) →
  Decision{action ∈ SAFE | PROPOSE | ESCALATE | QUARANTINE, risk ∈ R0..R5, reasons}`. Every
  agent proposal passes through it; the `Decision` is written onto the proposal/escalation
  event so an auditor sees exactly why something was let through. The LLM never decides what
  happens to its own output.
- ✅ **Explicit R0–R5 risk tiers** (`safety/risk.py`) — `assess_risk` returns the max of
  every rule that fires: R0 rounding-within-tolerance · R1 small + category-consistent · R3
  multiple candidates / evidence–category mismatch / confidence in the uncertain band · R4
  material ₹ impact / unexplained-with-material-money · R5 control category
  (`SECURITY_REVIEW`, `WRONG_ACCOUNT`) / fabricated citation.
- ✅ **Deterministic counterfactual verification** (`safety/counterfactual.py`) — *not* a
  second LLM. For each hypothesis category it runs the arithmetic that would have to hold if
  the hypothesis were true ("if this ₹X gap is an unrecorded refund, `refunds += X` closes
  the residual to 0 — does it?") and contradicts the proposal if it doesn't. Independent of,
  and additional to, the 2nd-model verifier.
- ✅ **Fail-closed everywhere** — an unparseable / verdict-less verifier response escalates;
  grounded-confidence below θ_escalate escalates; a provider outage escalates that exception,
  it does not sink the run; material money (R4+) with sub-conclude confidence escalates; R5
  never returns SAFE.
- ✅ **Attack Arbiter** (`arbiter attack`, `POST /v1/attack`, cockpit panel) — a
  deterministic adversarial harness. 12 scenarios, each copies a clean dataset, applies one
  known tampering, reconciles with `--no-ai`, and reports `{detected? rupees_unaccounted?
  unsafe_auto_resolution? what_arbiter_did? verdict}`. Verdicts: CONTAINED / PARTIAL /
  MISSED / **UNSAFE** (the matcher asserted a confident clean tie over a tampered record —
  the one outcome that must never happen). Scenarios: duplicate settlement row · altered
  amount · wrong currency · fabricated UTR · dropped bank credit · duplicate refund · prompt
  injection in a note · injection in a bank narration · ₹10,00,000 phantom credit · negative
  gross · blanked amount · 74-year timestamp shift. **Building it found and fixed 4 real
  gaps** (injection-scanner scope, foreign-currency handling, implausible-date handling,
  bank-credit↔settlement linkage). Current result: **12 contained · 0 missed · 0 unsafe ·
  ₹0 unaccounted.** `arbiter attack` exits non-zero on any UNSAFE; a CI test is the
  regression gate.
- ✅ **Agent trajectory benchmark** (`arbiter agent-bench`, rev. 4) — 99 labelled cases
  built from real seeded reconciliations (true category, `must_escalate`, required evidence,
  materiality, injection flag). The **real** `investigate()` loop runs per case against an
  `oracle` (competent), `reckless` (confidently wrong), `fabricator` (cites a ghost), or a
  live `openai`/`anthropic` client. Usefulness and safety scored on separate cards, gated in
  CI. Results: oracle **100% task · 100% category · 100% escalation recall · 0 unsafe · +44%
  lift**; reckless **0 material unsafe** (14 sub-rupee SAFE-gate slips, ₹1.14 total across 99
  cases; a human still confirms); fabricator **100% escalated**. This closes the "no
  benchmarked agent number" gap for the *harness*; a full live-model trajectory run still
  needs an API key in CI. Also fixed a real harness gap the benchmark surfaced: the kernel
  used to mark confident-wrong proposals SAFE whenever the narrow category checks happened
  not to fire — SAFE now requires a *positive* arithmetic confirmation and excludes
  money-movement categories.
- ✅ **`get_record(id)` tool** — the agent inspects a record before it cites it. **Cost
  honesty** — a shared price table; `est_cost_usd` is `None` (→ "unavailable for this
  provider") for an unpriced model, never a fake `$0.000`. **Model-keyed calibration** — a
  Claude ECE is never shown as GPT's. **Structured investigation UI** — the cockpit renders
  PLAN → EVIDENCE → PROPOSAL → SAFETY DECISION → OUTCOME as cards with a "why didn't Arbiter
  resolve this?" panel and an "explain this number" decomposition popover; raw JSON moved
  behind a "Technical detail" disclosure. **`docs/CONTROL_INVARIANTS.md`** + a 14-test file,
  one named proof per invariant. **`docs/CLAIMS.md`** claim→proof→command matrix.
  **`docs/buildathon/`** — DEMO, AGENT_EVALUATION, SAFETY_RESULTS, ATTACK_RESULTS,
  LIMITATIONS.
- ✅ **Headline safety metrics in the scorecard** (`bench` `SafetyScore`) —
  `unsafe_resolution_rate` (of the items ground truth says needed a human, the fraction the
  agent auto-resolved — **gate tolerance 0**), `rupees_protected` / `rupees_at_risk`,
  `replay_divergence`, `fabricated_citations`, `injection_quarantined`. Surfaced in `arbiter
  bench`, the cockpit scorecard panel, and the streaming view. The safety story is now a
  *number*, gated in CI, not a claim.

### 6.1 What actually happened the first time the agent ran against a live model

Until recently the agent path had only ever been exercised offline with scripted/recorded
turns. It has now been run for real against **`gpt-4o`** (via the adapter, no Anthropic key
available). One representative investigation, verbatim, is the centrepiece of the public
demo. What that surfaced — this is real evidence, not speculation:

- **The loop works end to end on a non-Anthropic model.** Plan → two real read-only tool
  calls (`decomposition_detail`, `similar_exceptions`) → hypothesis → proposal → verifier →
  decision. Tool-call translation, multi-turn history, token accounting, prompt hashing all
  intact.
- **The verifier caught a bad proposal, live.** gpt-4o proposed `TIMING` at a
  self-reported **0.9 confidence**; the independent verifier model checked the cited records
  and returned `{"supported": false}` — the citation pointed at a `settled_at` value that
  didn't actually prove a late settlement. The exception escalated to a human instead of
  being applied. This is the "AI at the boundary, every output gated" thesis working in
  real time.
- **gpt-4o is over-confident and messy.** It self-scored 0.9 on a claim its own verifier
  rejected. The first (pre-fix) run wrapped proposals in ```` ```json ```` fences with
  invalid enum values and extra keys, failed the strict schema for four turns, and hit the
  turn budget — a coercion layer + a `json_schema` response format now clean up after it.
  Claude's constrained structured-output mode holds this down; GPT needs the guardrails more.
- **The agent scorecard reads 0.0%** for task-completion / grounded-rate / escalation-recall
  on a live single-exception run — those metrics need a labelled trajectory set that only
  the synthetic bench has. `arbiter agent-bench` (rev. 4) now benchmarks the *harness*
  properly — 99 labelled cases, oracle/reckless/fabricator clients, usefulness vs safety
  scored apart — but a full **live-model** trajectory run still needs an API key in CI.
- **Observed cost:** one investigation ≈ **18,932 input / 1,075 output tokens** (≈ $0.05–0.10
  on gpt-4o, more on Opus). The cockpit currently shows `$0.000` because the cost estimate
  isn't wired for the OpenAI path.

### 6.2 Moat vs. scaffolding (raw material for §11 Q5 / §12.5)

Rough self-assessment of where the defensible value sits:

- **The moat (≈25%):** settlement decomposition as a first-class model · the deterministic
  matcher + Fellegi–Sunter scoring · the bounded investigation loop with grounding + the
  verifier · **the deterministic Safety Kernel + counterfactual check + the Attack-Arbiter
  harness** (the fail-closed "AI proposes, arithmetic decides" gate is the part a finance
  buyer's risk team would actually care about) · the honest adversarial benchmark with
  gated safety metrics · the event-sourced replayable audit trail.
- **Table stakes (≈30%):** file ingestion, the exception taxonomy, the cockpit UI,
  root-cause clustering, `--no-ai`. Necessary, not differentiating.
- **Premature scaffolding (≈45%):** the multi-tenant platform, Postgres RLS, the async job
  queue, Helm chart, OpenTelemetry/Sentry/Grafana, the MCP server, the continuous-learning
  platform (retraining, drift, global patterns, pgvector). All built to spec, all CI-green,
  **none with a user** — built because a roadmap said to, not because demand pulled it.
  That this happened is itself a data point about how decisions are being made. (The
  Safety-Kernel/Attack-Arbiter work this round was also spec-driven, not demand-driven —
  but it directly serves the Buildathon's "AI Judgment" and "Failure Recovery" criteria,
  which is a narrower and more defensible reason than "the roadmap said so.")

### Resolution & learning loop
- ✅ Accept / edit / reject / won't-fix on every exception, recorded as an event.
- ✅ **Rule synthesis** — an accepted resolution drafts a durable safe-AST `when → classify/
  resolve` rule from a per-category template; judgment categories return no rule.
- ✅ Spec-diff review — a human approves the drafted rule (reviewable YAML, version bump)
  before it's live.
- ✅ **3-close cycle demo** (`arbiter cycle-demo`) — each close scored twice (base spec vs
  carried-forward learned spec) so batch noise ≠ rule effect.
- ✅ **Agent escalation-threshold tuning** — folds `(grounded_confidence, human-kept-the-
  action?)` pairs → picks the θ that best separates accepted from overridden → logged event;
  `arbiter retrain` runs FS retrain + this.
- ✅ **RAG resolution memory** — each resolved exception's feature bag → a 256-dim unit
  vector (deterministic signed-feature-hashing, *not* a trained encoder); `pgvector` ANN
  query on Postgres, in-Python cosine on SQLite; `similar_exceptions` is semantic recall.
- ✅ **Opt-in global pattern library** — on a resolve, the exception's *shape*
  (category, residual band, record-count band, sorted source/kind types, 3 has-a-X booleans
  — no amounts, names, ids, free text, or org id) + the action is contributed to a separate
  DB; contributor = `sha256(org_id + salt)`; `off` / `consume` / `contribute` kill-switch.
- ✅ **Input-drift detection** — a numeric per-run feature profile compared by PSI against the
  tenant's recent runs; a drift event names the moved features (written to a learn
  pseudo-run, never the reconciliation hash chain).
- ✅ **Model registry** — the append-only log versions every learned artifact; `arbiter
  models` folds the timeline.

### Event log, replay, audit, assurance
- ✅ Append-only hash-chained event store; projections rebuilt by folding events;
  `arbiter replay` → byte-identical projections; `arbiter verify` → recompute the chain.
- ✅ **Close Memo** (`arbiter memo`) — self-contained HTML (print-styled → PDF) with totals
  tied, coverage, every exception + resolution, the audit-trail hash + the verify command.
- ✅ **Audit pack** (`arbiter audit-pack`) — the memo + the full hash-chained event log + a
  re-check manifest, as one zip.
- ✅ **Cash-position readout** (`arbiter cash-position`) — every settled rupee partitioned:
  confirmed in bank / in transit / held (disputes, wrong account) / unexplained. Pure
  arithmetic off the reconciled ledger; always sums back to the processor-side net.

### Scorecard & benchmark
- ✅ `arbiter bench` — matching metrics (auto-match rate, precision, recall, **false-match
  rate**, ₹ coverage, ₹ unexplained) **and** agent metrics (task-completion, tool-use
  accuracy, grounding, hallucination rate, escalation P/R, trajectory efficiency,
  confidence ECE). `scorecard.json` + HTML report.
- ✅ **CI regression gate** — `arbiter bench --gate bench/baseline-800.json` fails the build
  if any tracked metric moves the wrong way past its tolerance; an absolute floor as a
  second check.
- ✅ **Adversarial synthetic distribution** (`--difficulty adversarial`) — ~35% of clean
  batches get a mangled UTR, ~25% lose the UTR label entirely, a "Closing Balance" totals
  row is appended, anomaly density ~22%. CI asserts graceful-degradation invariants:
  false-match ≤ 1%, ₹ coverage ≥ 99%, auto-match ≥ 55%.
- ✅ Confidence calibration study (reliability diagram, ECE, isotonic recalibration).

### Adversarial synthetic data generator
- ✅ Generates N-record settlement + bank + ledger batches with a **labeled** `ground_truth.
  json`; 11-anomaly labeled catalog (duplicate, partial/split settlement, fee drift, GST
  rounding, missing UTR, timing straddle, chargeback, FX, wrong-account, over/short payment,
  refund-netting); seeded/reproducible; difficulty dial; scenario presets.

### Platform (multi-tenant)
- ✅ `org_id` on the event store; `EventStore(url, org_id=...)` tenant scoping; run-id
  partitioning; a **cross-tenant isolation test** (P0).
- ✅ **Postgres + Alembic migrations** (`arbiter-api db upgrade`); a "migrations never drift
  from the models" test; **Postgres row-level security** (`ENABLE` + `FORCE`, per-transaction
  `set_config` GUC).
- ✅ **API-key auth** (`Authorization: Bearer`), per-request `Principal` in a ContextVar,
  RBAC (viewer / analyst / admin) on mutating routes, `arbiter-api issue-key`.
- ✅ **Access audit log** — every mutating request and every 401/403 recorded with the
  resolved principal; `GET /v1/audit` (admin, tenant-scoped).
- ✅ **DB-backed async job queue** — atomic claim, `arbiter-api worker`, `202` + run id,
  retries + dead-letter, **self-healing** (stale-lease reclaim on every claim).
- ✅ Per-tenant rate limiting; idempotency keys (`Idempotency-Key`, 409 on reuse); tenant-
  scoped upload storage behind a swappable interface; **S3/R2 backend**.
- ✅ Pinned OpenAPI-surface snapshot test; the cockpit sends its key (SSE/WS carry it as
  `?key=`).

### Infra / deploy / observability
- ✅ `api` / `worker` Dockerfile (multi-stage, non-root, healthcheck) + `web` Dockerfile
  (Next standalone, non-root); `docker-compose` (`db` + `api` + 2× `worker` + `web` +
  `pgbouncer` + `redis` + Prometheus/Grafana/Alertmanager profiles).
- ✅ **Helm chart** — api/worker/web/pgbouncer/redis Deployments, HPAs (`autoscaling/v2`),
  PDB, a `pre-upgrade` migration-hook Job, ConfigMap/Secret, PVC, Ingress (SSE-safe nginx
  annotations); `helm lint` + `kubeconform -strict` in CI.
- ✅ CI: builds api + web images, smoke-tests, **Trivy-scans** (fails on fixable CRITICAL),
  writes a **CycloneDX SBOM**, pushes to GHCR on `main`.
- ✅ `deploy.yml` (dormant until `KUBE_CONFIG`, then `helm upgrade --install --atomic --wait`
  = auto-rollback) + `preview.yml` (per-PR Helm release, dormant until `KUBE_CONFIG` +
  `ARBITER_PREVIEW_DOMAIN`).
- ✅ **structlog** JSON logs + `X-Request-Id` correlation + `GET /metrics` (Prometheus);
  **OpenTelemetry** span export (opt-in via `OTEL_EXPORTER_OTLP_ENDPOINT`); **Sentry**
  (opt-in via `SENTRY_DSN`); Grafana dashboard + Prometheus SLO alert rules + Alertmanager.
- ✅ **CI restore drill** — real Postgres, `db upgrade`, deterministic run, `pg_dump -Fc` →
  `DROP SCHEMA` → `pg_restore`, then `verify` + `replay` assert the terminal hash, event
  count and chain integrity are byte-identical after the round trip.
- ✅ **Redis read-through cache** — the scorecard is memoized per `(run, terminal-hash)` once
  the run is immutable.

### Continuous-learning platform & integrations
- ✅ **MCP server** (`arbiter-api mcp`, stdio) — 7 read-only tools (`list_runs`,
  `run_summary`, `verify_run`, `cash_position_for`, `query_evidence`, `decomposition_detail`,
  `list_exceptions`), tenant-scoped; a test asserts no tool can mutate. Other agents (a
  CFO copilot, a controller's assistant) can call reconciliation as a capability.

### Flagship UX
- ✅ **Streaming investigation view** — opens the SSE stream (enriched: agent turn text, tool
  calls, proposal + escalation payloads, `Last-Event-ID` resume, heartbeats), folds it into
  a per-exception timeline that animates in with Framer Motion springs, a phase rail.
- ✅ **⌘K command palette** (cmdk) — navigate, jump to recent runs, flip the theme.
- ✅ **Realtime presence over WebSocket** — every open cockpit on a run sees the others'
  initials; a resolve is fanned out so two analysts stay in sync.
- ✅ **Live scorecard** — the streaming view fetches the scorecard the moment the run seals.
- ✅ Apple-minimal pass; cockpit motion (drawer slide/fade, shared-layout row cursor),
  `useReducedMotion` throughout.

### Deliberate non-goals (v1)
Journal-entry posting into an ERP · live connectors · multi-entity consolidation · fraud
detection · a full cash forecast · billing. Each is a stated scope boundary with a reason.

---

## 7. Technical architecture

### 7.1 Shape

```
CLIENTS         arbiter CLI (Typer)   ·   Cockpit (Next.js 15 / React 19 / TS)   ·   CI (GitHub Actions)   ·   MCP clients
                          │                         │  REST/JSON + SSE + WS                   │                    │ stdio
                          └───────────────┬─────────┴────────────────────────────────────────┴────────────────────┘
                                          ▼
API LAYER       FastAPI + Pydantic v2 — /v1/ingest /runs /runs/{id}/exceptions /exceptions/{id}/resolve
                /runs/{id}/scorecard /runs/{id}/stream (SSE) /runs/{id}/ws (presence) /audit /jobs /uploads /me
                auth (API key → Principal), RBAC, rate limit, idempotency, audit log, structlog, /metrics
                          ▼
ENGINE          arbiter_engine (pure Python, no web deps)
                ingest/  specs/  match/  decompose/  exceptions/  agent/  learn/  events/  bench/  memo/  cash/  tracing
                          ▼
STORE           SQLModel — SQLite (demo)  |  Postgres (real, + Alembic + RLS + pgbouncer + pgvector)
                events (append-only, hash-chained)  ·  projections (rebuilt by folding)  ·  specs  ·  runs  ·  jobs  ·  api_keys  ·  access_log

datagen/        adversarial synthetic batch generator (separate package) → sources/*.csv + ground_truth.json
```

Monorepo: **uv workspace** with `packages/engine`, `packages/datagen`, `packages/api`, plus
`web/` (pnpm). `make demo` / `make up` / `make bench` / `make cycle` / `make worker`.

### 7.2 The deterministic / AI boundary (the most-judged decision)

**Deterministic (zero LLM calls):** parse & normalize, dedupe, all matching passes,
settlement decomposition, confidence scoring, rule-decidable classification, the scorecard,
replay. These have *correct answers*; non-determinism here is a bug.

**LLM (exactly one step):** investigation of exceptions the deterministic classifier tagged
`AMBIGUOUS` or `UNEXPLAINED` (never `SECURITY_REVIEW` — those bypass the agent). The agent
plans, gathers evidence with read-only tools, tests a hypothesis, and either proposes a
category + explanation + fix + draft rule, or escalates with one question. Output is a
strict schema; malformed → discarded, exception stays `UNEXPLAINED`, logged.

**The gate:** every proposal the agent emits passes through the **deterministic Safety
Kernel** (§6 "Safety layer") before it can be marked SAFE — a pure, versioned function over
the risk tier, the grounding result, a deterministic counterfactual arithmetic check, and
the 2nd-model verifier. The LLM proposes; deterministic code decides SAFE / needs-a-human /
escalate / quarantine, and records why.

**Hard guarantees:** no agent tool mutates money; every proposal is an event with an "AI
proposed" badge; a human accept/edit/reject is required before a proposal affects anything;
the agent is time- and token-budgeted; `arbiter run --no-ai` skips the step entirely and
the scorecard still computes; `unsafe_resolution_rate` (auto-resolutions ground truth says
needed a human) is a CI-gated metric with tolerance 0.

### 7.3 Data model

- **`events`** — `id`, `run_id`, `seq`, `ts` (informational, never in logic), `type`,
  `payload` (json, schema-versioned), `actor` (`engine` / `agent:<model>@<prompthash>` /
  `human:<id>`), `prev_hash`, `hash` = `sha256(prev_hash + canonical(payload))`, `org_id`.
- **`Record`** (canonical, post-normalization) — deterministic id `sha256(source,
  source_row_id, run_id)[:16]`, `source`, `kind`, `amount_minor` (signed paise), `currency`,
  `value_date`, `posted_date`, `counterparty`, `reference`, `external_ids`, `raw` (untouched).
- **`Match`** — `left`/`right` as *sets* of record ids (supports N:M), `pass`, `confidence`,
  `rule_id`, `residual_minor` (0 = clean), `status`.
- **`Exception`** — `records`, `category`, `classified_by`, `amount_impact_minor` (drives
  ranking), `confidence`, `candidates`, `ai_proposal`, `ai_trajectory_id`, `resolution`,
  `status`, `note`.
- Projections (`records`, `matches`, `exceptions`, `decompositions`) are **derived** —
  dropped and rebuilt by folding events, never written directly by business logic.

### 7.4 The recon spec (logic as data)

One YAML file fully describes a reconciliation: `sources` (format + column map + id fields +
scale), `identity` (the decomposition formula + rounding tolerance), `passes` (exact /
tolerant / subset / fuzzy weights), `thresholds`, `taxonomy` (the exception enum), `rules`
(safe-AST `when → classify/resolve`, learned rules appended here with provenance comments).

### 7.5 SDK boundary (the client / engine / model split)

- **Engine ↔ model:** a pluggable `LLMClient` interface (one method, `complete() -> Turn`).
  Implementations: `AnthropicClient` (`claude-opus-5` investigate / `claude-haiku-4-5`
  triage / a `verify` model) · `OpenAIClient` (a real adapter that translates Arbiter's
  Anthropic-shaped messages, tools and structured-output instruction to OpenAI Chat
  Completions and normalises the reply back) · `RecordedClient` (replay) · `ScriptedClient`
  (tests). Structured output via a strict schema (`category` = spec taxonomy enum). Frozen
  prompt as a `cache_control` prefix. `bench` uses the Anthropic Batch API (−50%).
  Provider chosen by `ARBITER_LLM_PROVIDER`, or per-run via `X-LLM-Provider` / `X-LLM-Key` /
  `X-LLM-Model` request headers (applied to the process env for that one inline run under a
  lock, restored after, never written to the job payload or the event log).
- **Cockpit ↔ API:** REST/JSON for reads and mutations; **SSE** (`/runs/{id}/stream`) for
  the streaming investigation view; **WebSocket** (`/runs/{id}/ws`) for presence. The
  cockpit stores its API key in `localStorage` and sends `Authorization: Bearer`; SSE/WS
  carry it as `?key=` (EventSource can't set headers).
- **Other agents ↔ Arbiter:** the MCP server exposes the read-only tool surface over stdio.
- **CLI ↔ engine:** Typer, in-process, same Pydantic types as the API; `--json` on every
  command. The CLI is the primary proof surface for judges and CI.

### 7.6 Determinism & replay (precise statement)

| Component | Guarantee |
|---|---|
| Skeleton (ingest → classify, score, memo) | **bit-reproducible** — same inputs + spec + seed → identical event hash chain |
| Brain (investigation loop) | **not** reproducible on a fresh call; made **replayable** by recording every request/response as an `AGENT_INTERACTION` event |
| `arbiter replay <run-id>` | re-runs the skeleton deterministically; replays recorded agent turns instead of calling the API |
| cross-run learned state (FS retrain, drift, threshold tuning) | written to a `__learn__<org>` pseudo-run, **never** the reconciliation hash chain, so a replay in a fresh store does not diverge |
| `replay_divergence` | a first-class scorecard metric — the reconciliation is run twice and the terminal hashes compared; CI gate tolerance is 0 |

### 7.7 Accuracy — measured, honest, and synthetic

**Current headline numbers** — 800-record *adversarial* batch, seed 42, `--no-ai`
(deterministic core only, no LLM):

| metric | value | | metric | value |
|---|---|---|---|---|
| auto-match rate | **93.8%** | | false-match rate | **0.0%** |
| precision | 100.0% | | ₹ coverage | 100.0% |
| recall | 93.8% | | ₹ unexplained | 0.7% |
| anomalies caught | 8 / 10 | | category accuracy | 75.0% |
| determinism (replay hash match) | ✅ | | confidence ECE | 0.12 (recalibrated, disclosed) |

**Headline safety numbers** — same seed dataset, `SafetyScore` block, CI-gated at tolerance 0:

| metric | value | | metric | value |
|---|---|---|---|---|
| unsafe auto-resolutions | **0 / 2** human-only items | | replay divergence | **none** |
| ₹ protected | **₹53,245 (100%)** | | fabricated citations | **0** |
| Attack Arbiter (12 scenarios) | **12 contained · 0 unsafe** | | ₹ unaccounted after attack | **₹0** |

**What these numbers are and are not:**
- They are on **synthetic data** generated by a generator I also wrote. The anomaly catalog
  is derived from documented real-world reconciliation exceptions, not from what the matcher
  happens to handle, and `--no-ai` + sub-100 category accuracy show it isn't gamed — but the
  "I wrote both the generator and the matcher" risk is real and stated.
- The **agent has now run live** (against `gpt-4o` — see §6.1), so there is a verbatim trace
  showing the loop, the tool calls and the verifier working. But there is still **no
  benchmarked agent accuracy number on any model**: task-completion, hallucination rate,
  grounded rate, escalation P/R, AI lift and calibration all need a labelled trajectory set
  that only the synthetic bench has, and the bench needs an API key that isn't in CI. A
  single live investigation scores 0.0% on those metrics by construction.
- The learning-curve claim (month 3 auto-match > month 1) is demonstrated on **synthetic
  cycles**, and its *shape* (monotonic up) is enforced by a test — but it has never run on a
  real customer's three real closes.
- Real-world match rates **will be lower**. This asterisk is in the README and stays visible.

### 7.8 Scale / limits (stated)

- Subset-sum matcher: exact (meet-in-the-middle) to ~40 candidates per settlement group,
  bounded heuristic above. Not an ILP solver.
- Never load-tested at the stated target (500 concurrent orgs, 10k runs/day). The queue +
  worker + HPA architecture is built for it; the evidence that it holds is not.
- Provider errors (bad key, 429/529, network) → capped backoff → the exception escalates
  with `reason: provider_unavailable`; the run does not fail.
- Known unbuilt agent gaps (from §6.1): structured rendering of every turn in the live view
  (raw JSON still leaks through); a graceful agent scorecard that hides label-dependent
  metrics when there's no eval set; an OpenAI price table; a `get_record(id)` tool so the
  agent can verify its own citations; per-model calibration (the reliability diagram
  assumes Claude); token-level streaming; a messier demo dataset that gives the agent
  3–4 varied exceptions.

### 7.9 Security & compliance posture

- **Deterministic Safety Kernel** as the single gate on every agent proposal (R0–R5 tiers,
  grounding, counterfactual arithmetic, 2nd-model verifier — all fail-closed); the
  `Decision` is on the event log. Money-safety is independent of model-safety.
- **Attack Arbiter** — a 12-scenario deterministic adversarial suite run in CI; current
  result 12 contained / 0 unsafe / ₹0 unaccounted. It found and closed 4 real gaps.
- Prompt-injection defense: untrusted-field fencing + system-prompt data declaration + a
  deterministic injection scanner (broadened this round beyond "ignore previous
  instructions" to role-reassignment, "mark as reconciled/approved", authorization claims,
  leading `system:`/`assistant:` lines) that quarantines to `SECURITY_REVIEW` (bypasses the
  agent) + proposal-only tools as the backstop.
- File intake hardening (size/row caps, CSV formula neutralization, safe XLSX,
  foreign-currency-without-a-rate → quarantine, dates outside 2015–2035 → quarantine).
- Secret + PII redaction in logs/traces/memo; `gitleaks` + `pip-audit` + Trivy in CI.
- `arbiter verify` for tamper-evidence; Postgres RLS for tenant isolation.
- Compliance analysis done (RBI PA-PG Directions 2025 — the schema has no PAN field by
  design; DPDP Act 2023/Rules 2025 — `arbiter purge` for the erasure right; PCI-DSS likely
  out of scope by design). **No SOC 2** — that needs a company.

### 7.10 Build status

M0–M5 milestones complete + the entire `docs/28` production-hardening roadmap (5 phases)
executed + a 93-section external hardening spec (`ARBITER_MASTER_IMPLEMENTATION_SPEC`)
audited (`ENGINEERING_AUDIT.md`: ~85% of it was already built) and its real gaps closed —
the Safety Kernel, the Attack-Arbiter harness, the headline safety metrics, root-cause
clustering, the exception state machine, seven consolidated root docs, and a graded
`FINAL_REPORT.md`. 100 commits over ~4–5 days, every one CI-green. ~222 test functions
(229 cases), ~11 CI jobs (lint-type, test, security, determinism, bench + regression gate,
docker, helm, web, recovery, deploy, nightly-live [schedule-only]). ~14k lines, engine is
the substance.

### 7.11 What's live right now

- **Public demo: `https://arbiter-cockpit.vercel.app`** — the *real* Next.js cockpit,
  hosted, no login. It serves a **frozen snapshot** of one real run (`f7e810ba`: 1,672
  records, agent on `gpt-4o`): the scorecard (now including the headline safety block), the
  keyboard exception queue, the evidence drawer with the 4-turn investigation trace, the
  **root-cause cluster panel**, the **"Run the attack suite" panel** (serving the frozen
  `arbiter attack --json` output — 12 contained), and a `/live` view that replays the real
  event log as SSE so the gpt-4o investigation animates the way it happened
  (plan → tool calls → proposal → verifier rejects the citations → escalated). Backed by
  Next.js route handlers reading captured JSON — no Python backend running. Set
  `ARBITER_API_URL` and it becomes fully live against a real API.
- **The repo** (Apache-2.0, engine/CLI/bench): `make demo` reproduces every number;
  `make up` runs the full stack locally.
- Nothing else. No hosted multi-tenant instance, no customers, no data.

---

## 8. Competitive landscape

Four bands. Arbiter sits deliberately between bands 3 and 4.

| Band | Who | Model | Price | Buyer |
|---|---|---|---|---|
| 1. Enterprise close suites | BlackLine, HighRadius, Trintech, FloQast | seat license + implementation | $50k–$1M+/yr | enterprise controller, via procurement + audit sign-off |
| 2. AI-native close challengers | Numeric ($89M raised), Nominal ($20M), Ledge ($9M), Campfire | SaaS, faster deploy | $15k–$100k/yr | mid-market / high-growth startup controller |
| 3. Payment/ledger infra with recon | Razorpay Smart Collect 2.0, Stripe, Blnk, Openledger, M2P Recon360 | bundled / API / usage | bundled or usage | engineer / ops already on that rail |
| 4. Point tools & DIY | ClearTax / Zoho (GST), Tally add-ons, OSS pipelines, spreadsheets, CA firms | license / services / free | ₹0–₹5k/mo or labor | SMB owner, accountant, CA |

**Key teardowns:**
- **BlackLine** — auditor trust, SOX depth, 20-year track record; but 6–18 month
  implementation, dated UX, AI bolted onto a legacy core, inaccessible to a 50-person
  company. Arbiter is what a company uses for the 5 years before it can afford BlackLine.
- **Numeric** — genuinely modern, 90%+ auto-match at Brex/Wealthfront/Public, deep NetSuite
  integration, well-funded; but US-first, NetSuite-centric, priced for VC-backed startups,
  not focused on settlement decomposition, closed source, "90%+" stated without a published
  false-match rate. Arbiter's angle: publish the number honestly + own the
  gross/MDR/GST/refund decomposition + India/payment-rail wedge.
- **Razorpay Smart Collect 2.0 (and every PG's native recon)** — zero integration, free-ish,
  authoritative on that PG's own data; **but single-source by construction.** It cannot
  reconcile Razorpay + a 2nd PG + the bank + the ledger + the tax register. This is the most
  important competitive point — the real problem is multi-source, and no native tool ties
  all of it.
- **`Manu6259/financial-reconciliation-agent`** (OSS) — independently arrived at the same
  "LLM proposes, deterministic code disposes" principle (validation, not a threat). Real
  ablation study (no-RAG 53.6% → RAG 100%). But tested on **69 transactions**, same-
  distribution, claims 100% — exactly what the Buildathon bar ("one cherry-picked match
  proves nothing") warns against. Arbiter goes further: 800+ adversarial records with a
  labeled catalog and a *sub-100* number with a false-match rate; settlement decomposition;
  a real investigation loop not a single call; calibration; prompt-injection defense;
  deterministic replay.
- **OSS engines (Blnk, Lerian Matcher)** — free, inspectable, real architecture; but they
  are *engines* not products — no exception-triage UX, no LLM adjudication, no scorecard, no
  learning loop, no settlement-decomposition model.

**Arbiter's defensible wedge (6 things, any one a talking point, together a position):**
1. The honest scorecard — nobody publishes precision + recall + false-match rate on
   reproducible *adversarial* labeled data, checkable by a stranger in one command — now
   also with gated safety metrics (`unsafe_resolution_rate`, `replay_divergence`).
2. Settlement decomposition as a first-class model — flags a total-match that doesn't
   decompose as a false match.
3. The exception ledger is the deliverable, not the leftover — typed, ranked by rupees,
   clustered into root causes, each with evidence + hypothesis + one-click-to-rule.
4. Deterministic-core doctrine, written as an ADR — better engineering *and* exactly what
   the "AI Judgment" criterion rewards.
5. Demonstrable improvement over cycles — a rising curve, not a static claim.
6. Fail-closed safety — a deterministic Safety Kernel gates every AI proposal, and an
   Attack-Arbiter harness proves in CI that a tampered file never produces a confident
   clean tie (12/12 contained). This is the "Failure Recovery" criterion, made a number.

---

## 9. Where the internal team keeps landing

Every completeness/strategy pass through this project converges on the same repositioning,
and it is worth stating because it is *not* the same as "build more features":

> **Arbiter is not a reconciliation system. It is the verification and exception layer that
> sits above whatever rails and ledgers a business already uses — processor-neutral,
> auditor-legible, open where it matters — and its output is a checkable assurance artifact,
> not a replacement for anyone's system of record.**

Concretely: sell the scorecard not the automation; wedge = multi-rail D2C/marketplace
settlement recon (not GST-SMB, not enterprise close); augment don't replace; open-source the
engine + the benchmark; deterministic-first, AI-optional, always disclosed; two GTM doors
(CA firms + founder-led finance); never hide a limitation.

**And the uncomfortable conclusion that keeps surviving every review:** as a fundable
standalone company Arbiter faces real headwinds. As (a) a Buildathon-winning demonstration
of engineering + product + market judgment, (b) an open-source project that could earn
genuine adoption, and (c) a wedge a payments company or an ERP could acquire — it is
well-positioned. The strategic question is which of those to optimize for, and the project
has not actually chosen.

---

## 10. Why the product might not sell — internal research findings

_This is the section I most want your help with. Written adversarially on purpose. Rated on
Severity (Low/Med/High/Fatal) and Likelihood (Low/Med/High). Each is paired with the most
honest mitigation available, including "no good mitigation."_

### R1 — Reconciliation is a "trust monopoly" market; buyers don't switch core financial controls to a startup
**Severity: High · Likelihood: High · Thesis-level.**
Reconciliation output feeds the audited financial statements. The buyer's real question is
not "is this tool good?" but "will my auditor accept work produced by this tool, and will I
still have a job if it's wrong?" Incumbents spent 20 years building auditor familiarity. A
finance leader has near-zero upside for championing an unknown tool and career-ending
downside if it misfires.
*Mitigation:* position as an exception co-pilot on top of the existing process, not a
replacement for the system of record; the immutable audit log + deterministic replay is
built to be auditor-legible; open-source the engine. **Honest residual: none of this fully
solves it. This is a slow-trust market and no framing changes that. It argues for starting
where the stakes are lower — a company without an audit relationship yet, or a CA firm that
owns its own methodology.**

### R2 — It's a feature, not a company: everyone is bundling reconciliation
**Severity: High · Likelihood: High · Thesis-level.**
Razorpay ships Smart Collect 2.0. Stripe has reconciliation reports. Every ERP has or is
adding a recon module. A standalone tool competes with "good enough and already included."
*Mitigation:* neutrality is the wedge — every bundled tool reconciles its own rail; Arbiter
ties all of them with one audit trail. Depth on settlement decomposition + the adjudication
workflow. **Honest residual: if a merchant uses one processor and one bank, the bundled
tool IS good enough and Arbiter has no room. The addressable user is specifically the
multi-rail business. That shrinks the market.**

### R3 — The moat is data integration, and that work is unglamorous, endless, and not AI
**Severity: High · Likelihood: High · Thesis-level.**
80% of production reconciliation effort is connectors: every bank's statement format, every
ERP's API quirks, every processor's schema changes. A synthetic-data demo hides all of it.
The AI is the easy 20%.
*Mitigation:* v1 scopes to file ingest + one processor; the recon spec's declared
column-mapping makes a new format a YAML file not a code change; partner with account
aggregators. **Honest residual: this is genuinely the hardest part of the business and
there is no clever way around it. A well-funded competitor with an integration team
out-executes a solo builder here.**

### R4 — "90% auto-match" is already table stakes; the last 10% is where trust is earned and it's slow
**Severity: Medium · Likelihood: High.**
Numeric claims 90%+, HighRadius 99%. Arbiter showing 92% on synthetic data impresses nobody
who's seen the category. The residual exceptions — the actual value — resolve well only
after months of real-usage learning.
*Mitigation:* don't compete on the auto-match %; compete on what happens to the 10% (typed,
ranked, explained, one-click-to-rule); the learning curve is the differentiator; publish the
false-match rate. **Honest residual: cold-start is real. A new customer's month 1 looks
mediocre. The product needs a "here's month 3" story and the patience to get customers
there.** New evidence (§6.1): the one live agent run *escalated* rather than resolving — the
verifier correctly rejected a weak proposal. That's the safety story working, but it also
means "the agent handles the last 10%" is not yet demonstrated; so far it demonstrably knows
when it *can't*.

### R5 — Finance buyers may want less AI, not more; non-determinism is a liability in audited workflows
**Severity: Medium · Likelihood: Medium — architecture already addresses it.**
BlackLine's entire 2026 message is "AI's governance and trust gap." A CFO who hears "an LLM
categorized your reconciliation exceptions" may hear "audit risk." Hallucinated
categorizations, prompt-injection via a vendor's narration field, model drift between
closes — all real.
*Mitigation:* deterministic core, AI only at the boundary, every AI output a gated proposal,
`--no-ai` always available, prompt + model + evidence hashed, provider-pluggable (not locked
to one AI vendor). **Honest residual: some buyers will say no to any LLM in the close.
That's a segmentation reality. It also means the deterministic core must be genuinely
excellent on its own.** New evidence (§6.1): running the agent on `gpt-4o` showed a
non-Anthropic model being over-confident and schema-sloppy, with the deterministic verifier
+ grounding layer catching it. Reads two ways to a skeptical CFO — "see, the guardrails
work" or "see, you can't trust the model" — and which they hear is a sales problem, not an
engineering one.

### R6 — The GTM is an org-change sale (displacing analyst hours), not PLG; cycles are 6–12 months
**Severity: Medium · Likelihood: High.**
The ROI is "0.5–1 fewer reconciliation FTEs." Realizing it means a champion, a pilot,
procurement, security review, a budget cycle.
*Mitigation:* two lower-friction doors (CA firms who adopt tools to raise their own margin;
founder-led finance at 20–80 person companies where buyer = user); land as a monthly
assurance artifact rather than a workflow replacement; OSS bottom-up. **Honest residual: the
big-contract revenue is still an enterprise motion; the bottom-up path may cap at small
ACVs.**

### R7 — Synthetic-data accuracy ≠ production accuracy
**Severity: Medium · Likelihood: High.**
Real bank data has garbled encodings, truncated references, banks that restate, timezone
chaos, partial files, humans who edited the CSV in Excel. The match rate on real data will
be lower, possibly a lot lower.
*Mitigation:* say so in the README and the pitch; the difficulty dial and messy-data
anomalies attempt to close the gap; roadmap includes a real anonymized dataset from a design
partner. **Honest residual: until Arbiter runs on real data at real customers, every number
has an asterisk.**

### R8 — Liability: if Arbiter mis-reconciles and the books are wrong, who's responsible?
**Severity: High · Likelihood: Low near-term / Medium at scale.**
A tool that influences the financial statements inherits some liability exposure,
contractually and reputationally.
*Mitigation:* v1 never posts anything — proposed matches and resolutions only, human
accepts, the ERP stays the system of record; the audit log shows who accepted what; standard
SaaS liability caps. **Honest residual: the moment the product moves toward auto-posting
(the natural expansion), this risk escalates sharply and needs real legal/insurance work.**

### R9 — Cold-start on the learning loop: the product is mediocre until it has cycles of real use
**Severity: Medium · Likelihood: High.**
The rule-learning loop is a core differentiator but needs several real closes before the
auto-match rate climbs.
*Mitigation:* ship starter rule packs per scenario; onboarding runs the last 3 months of
historical data first. **Honest residual: starter packs only go so far; every business's
tail of weird exceptions is its own.**

### R10 — Buyer confusion: is Arbiter software, a service, or infrastructure?
**Severity: Medium · Likelihood: Medium.**
Software (controller buys a seat) competes with FloQast/Numeric. Managed service competes
with outsourced controllers. Infrastructure (API) competes with Blnk. Each has a different
buyer, price, motion. Being all three = clarity of none.
*Mitigation:* pick one for 18 months — the recommendation is open-source engine (infra/
trust) + hosted cockpit (software, controller-bought), explicitly not the managed service.
**But this is a genuine open question and getting it wrong is expensive.**

### R11 — India-specific: severe price sensitivity, cheap manual labor, ecosystem lock-in
**Severity: Medium · Likelihood: High if India-first.**
An Indian SMB can hire a CA firm to do monthly recon for ₹5,000–15,000. Tally/Zoho lock-in
is deep. Willingness to pay for software is low.
*Mitigation:* sell to the CA firm not the SMB; the multi-processor D2C/marketplace segment
has real budgets; go global on the settlement-recon use case (Stripe shape, not just
Razorpay). **Honest residual: if the wedge is India SMB GST, the unit economics are hard —
a strong argument for the D2C/marketplace settlement wedge over the GST wedge.**

### R12 — A solo/small-team builder cannot sustain this against funded competitors
**Severity: High · Likelihood: Medium.**
Numeric has $89M. BlackLine has a sales army. Reconciliation-as-a-company needs integrations,
SOC 2, a sales team, support SLAs — all capital-intensive.
*Mitigation:* reframe the goal — for the Buildathon, Arbiter is a proof of engineering and
product judgment, not a funding-ready company; OSS + a sharp benchmark earns mindshare
disproportionate to headcount. **Honest residual: as a venture it likely needs a team and
capital. As a portfolio artifact, an OSS project, or an acqui-hire conversation, it stands
alone.**

### Risk summary

| ID | Risk | Sev | Lik | Net |
|---|---|---|---|---|
| R1 | Trust-monopoly market | High | High | **Thesis-level** |
| R2 | Feature-not-a-company / bundling | High | High | **Thesis-level** |
| R3 | Integration moat is unglamorous & endless | High | High | **Thesis-level** |
| R4 | 90% is table stakes | Med | High | Serious |
| R5 | Buyers want less AI | Med | Med | Manageable (architecture addresses) |
| R6 | Slow org-change GTM | Med | High | Serious |
| R7 | Synthetic ≠ production accuracy | Med | High | Manageable (disclose) |
| R8 | Liability | High | Low→Med | Watch as scope grows |
| R9 | Learning-loop cold start | Med | High | Manageable (starter packs) |
| R10 | Software vs service vs infra | Med | Med | Decide early |
| R11 | India unit economics | Med | High if India-first | Argues for D2C wedge |
| R12 | Solo builder vs funded field | High | Med | Reframe goal |

### The three thesis-level risks (R1, R2, R3) all point the same way

They are not solved by more engineering. They are addressed, imperfectly, by the
repositioning in §9 (sell assurance not automation; multi-rail wedge; augment not replace;
open-core; disclose everything). Whether that repositioning is *enough* is the question I
can't answer from inside.

---

## 11. Open strategic questions (what I need help thinking through)

Each changes what gets built and how it's pitched. The project has *default* answers but has
not truly committed.

**Q1 — What is Arbiter optimizing for, honestly?**
(a) A Buildathon win + a credential that gets me a role. (b) An OSS project I maintain that
earns adoption. (c) A funded startup attempt. (d) An acqui-hire / acquisition target for a
payments co or ERP. The build so far serves (a) and (b) well. Pursuing (c) would mean
different choices *now* (connectors over polish, design partners over the demo). **I have
been avoiding this choice. Which one — and what would you cut and add if the answer were
(c) specifically?**

**Q2 — Is the multi-rail wedge real, or a rationalization?**
The whole commercial case rests on "the real user has 2+ processors + a bank + an ERP and
nobody ties all of them." Is that a large enough, painful enough, reachable enough segment
to build a company on? Or is it a narrow band that feels defensible precisely because it's
small? How would I falsify this cheaply?

**Q3 — Software vs. managed service vs. infrastructure (the R10 question).**
Default: open-core (open engine + hosted cockpit sold to the controller), explicitly not the
"we reconcile for you" service. But the CA-firm / outsourced-controller channel keeps
looking like the better *business* even though it's a worse *story*. Is the managed/BPO
angle actually the right one for a solo builder in India, and I'm dismissing it for
aesthetic reasons?

**Q4 — Is "sell the assurance artifact, not the automation" a real buyer behavior or a
clever internal framing?**
Do finance teams actually buy a "monthly proof your close is clean" deliverable? Is there
evidence of budget for that, distinct from budget for close-automation software?

**Q5 — How much does the deterministic-core / honest-benchmark story matter to a *buyer*
(vs. a hackathon judge)?**
It's clearly the right engineering and clearly what the Buildathon rewards. But does a
controller choosing a tool care that the false-match rate is published and the engine is
open-source, or is that a builder's value that doesn't move a purchase decision?

**Q6 — India-first or global-from-day-one?**
The settlement-recon loop generalizes to the Stripe shape. India has the acute pain and the
Razorpay relationship; India also has R11's unit economics. Where do I actually start?

**Q7 — What's the cheapest experiment that would tell me this is or isn't a business?**
Not "build more." What's the one test — a landing page, 10 customer conversations, one
design partner running real data — that gives the most signal for the least effort, and
what specifically am I listening for?

**Q8 — If the honest answer is "this is a great portfolio piece and a marginal company,"
what's the highest-value thing to do with 3 more months?**

---

## 12. What I'd like from you

I don't want validation of the current plan — several people/processes inside this project
already tried that and concluded it's shaky in specific, evidenced ways (§10). I want help
doing the thing this project has been avoiding: **picking a direction and cutting hard**,
using the research above as the evidence base rather than intuition.

Specifically:

1. **Force the Q1 choice.** Given everything above, which of the four goals should I
   optimize for? Argue it, don't hedge. Then tell me the 3 things to stop doing and the 3
   things to start.
2. **Pressure-test the multi-rail wedge (Q2).** Is it a real segment or a comfortable story?
   If real, size it roughly and name who I should talk to. If not, what's the actual wedge
   hiding in this build?
3. **Adjudicate R1–R3.** Are the three thesis-level risks survivable for *this* builder in
   *this* market, or do they mean "excellent project, not a company"? Say which.
4. **Design the cheapest falsification experiment (Q7).** One test, what it costs, what
   result kills the idea vs. greenlights it.
5. **Tell me what to cut.** §6.2 is my own rough cut at moat (~25%) vs. table stakes
   (~30%) vs. premature scaffolding (~45%). Pressure-test it. What should not have been
   built yet, and — the part I actually need — what does the fact that I built a full
   production platform *and then a 93-section safety-hardening spec*, all before talking to
   one customer, tell you about how I'm making decisions, and how do I fix that pattern?
6. **If the verdict is "portfolio piece, marginal company" — tell me plainly**, and then
   answer Q8.

Be direct. I would rather hear "this specific thing is wrong" than "there are interesting
opportunities here."

---

## Appendix — pointers into the repo

- `docs/01` market & thesis (sourced) · `docs/03` competitive landscape · `docs/04` technical
  architecture · `docs/05` design doctrine · `docs/06` feature inventory · `docs/07` eval &
  benchmark methodology · `docs/08` why it might not sell (the red-team) · `docs/09` open
  strategic questions · `docs/12` agent design · `docs/21` go-to-market & business model ·
  `docs/22` cost model · `docs/26` compliance (RBI PA-PG, DPDP) · `docs/28` production-
  hardening roadmap (executed).
- `docs/adr/` — 0001 deterministic core / AI at the boundary · 0002 event-sourced store ·
  0003 safe-AST rules · 0004 hybrid orchestration · 0005 Fellegi–Sunter matching.
- `docs/BUILD-LOG.md` — every bug found and fixed, chronologically.
- **Root-level summaries (each points into `docs/`):** `ARCHITECTURE.md` · `AI_SAFETY.md`
  (the Safety Kernel, R0–R5, counterfactual, defense-in-depth table) · `SECURITY.md` ·
  `THREAT_MODEL.md` (assets, actors, the Attack-Arbiter abuse cases, residual risk) ·
  `BENCHMARK.md` · `FAILURE_RECOVERY.md` (fail-closed behaviour table + the attack harness) ·
  `REPLAY.md`.
- `ENGINEERING_AUDIT.md` — the 93-section hardening spec mapped against the code (done /
  partial / gap) + the prioritized plan that was then executed.
- `FINAL_REPORT.md` — a graded self-assessment against the four Buildathon criteria and the
  spec's acceptance groups, with an explicit "what is NOT done" section.
- `packages/engine/arbiter_engine/safety/` — `kernel.py` / `risk.py` / `counterfactual.py`
  / `policy.py`. `packages/engine/arbiter_engine/attack.py` — the adversarial harness.
  `packages/engine/arbiter_engine/exceptions/cluster.py` + `state.py`.
- `README.md` — the numbers, the quickstart, the honest-limitations section.
- `web/DEPLOY.md` — how the public demo is hosted and refreshed.
- **See it: `https://arbiter-cockpit.vercel.app`** (the cockpit + the verbatim gpt-4o
  investigation replay). Run it: `make demo` → `make bench` → `make up`.
