# 22 — Cost Model

_What Arbiter costs to run, at the Buildathon and at scale. LLM spend is the only variable cost that matters; everything else is negligible at these volumes._

Model prices (per MTok, Anthropic first-party, cached 2026-06): Opus 5 `$5 / $25` (in/out), Sonnet 5 `$2 / $10`, Haiku 4.5 `$1 / $5`. Prompt-cache reads are heavily discounted; Batch API is −50%.

---

## 1. Per-exception cost (the unit)

The deterministic core costs ~nothing. Cost is incurred only when the agent investigates an exception.

**Token profile of one investigation** (tiered policy — [doc 19 §6](19-agent-contracts.md)):

| Component | Tokens | Notes |
|---|---|---|
| System prompt + taxonomy + spec rules | ~2,500 | **cached** after the first exception in a run → ~$0 marginal |
| Per-exception task block (records, candidates, decomposition) | ~1,200 in | fresh each time |
| 2–4 tool calls + returns | ~2,500 in / ~600 out | evidence bundles |
| Reasoning + terminal Proposal/Escalate | ~1,500 out | |
| **Effective fresh tokens** | **~5,200 in / ~2,100 out** | after caching |

| Path | Model | Cost/exception |
|---|---|---|
| Haiku triage only (confident, simple category) | Haiku 4.5 | ~$0.005–0.010 |
| Escalated to Opus (full investigation) | Opus 5 | ~$0.026 + ~$0.053 = **~$0.08** |
| Blended (assume 60% resolved at triage, 40% escalated) | — | **~$0.035/exception** |
| `bench` runs (Batch API, −50%) | — | ~$0.018/exception |

Target ([doc 04 §10](04-technical-architecture.md)): **< $0.05/exception.** Met by the blend + caching + batch.

---

## 2. Per-run cost

Exceptions are a small fraction of records (a good recon has 1–3% exception rate; an adversarial demo batch is higher on purpose).

| Run | Records | Exceptions (agent-investigated) | Cost (with AI) | Cost `--no-ai` |
|---|---|---|---|---|
| `make demo` (seed) | 120 | ~14 (1 of each anomaly) | ~$0.50 | $0 |
| Demo batch | 800 | ~18 | ~$0.65 | $0 |
| `bench` full | 800 | ~18 (batched) | ~$0.32 | $0 |
| `bench --ablate` (4 configs) | 800 ×4 | — | ~$1.10 total | — |
| Realistic monthly close | ~4,300 | ~60 | ~$2.10 | $0 |
| `bench --scale 5000` | 5,000 | ~90 | ~$3.20 | $0 |

Per-run **cost ceiling** (`per_run_cost_ceiling_usd`, default $2.00): once hit, remaining exceptions get Haiku-only or are skipped to `budget` escalations. The scorecard always reports actual spend + how many exceptions hit the ceiling.

---

## 3. Buildathon total budget

| Activity | Runs | Est. cost |
|---|---|---|
| Development (frequent `run` + `bench` during M3–M5) | ~400 | ~$120 |
| CI (`bench` on every push, ~150 pushes) | 150 | ~$48 (batch) |
| Ablation + calibration studies | ~30 | ~$35 |
| Demo rehearsals + recording | ~40 | ~$25 |
| Buffer | — | ~$70 |
| **Total** | | **~$300** |

Mitigations that keep this down: `--no-ai` for anything not testing the agent; the seed dataset (120 records) for fast iteration; Batch API in CI; prompt caching; `claude-haiku-4-5` as the CI default model unless a test specifically needs Opus.

---

## 4. Production cost at scale (per customer/month)

| Customer size | Records/mo | Exceptions/mo | LLM cost/mo | % of ₹29k Team price |
|---|---|---|---|---|
| Solo (₹9k tier) | ~1,500 | ~20 | ~₹80 ($1) | ~1% |
| Team, typical | ~4,300 | ~60 | ~₹250 ($3) | ~1% |
| Team, high-volume | ~15,000 | ~180 | ~₹700 ($8.5) | ~2.5% |

LLM cost is a rounding error against the subscription. The gross-margin risk is support and hosting, not inference — the tiered policy and caching are what keep it that way.

---

## 5. Infra cost (negligible, listed for completeness)

- Demo/OSS: $0 (local, SQLite).
- Hosted: one small app server + managed Postgres + object storage for audit packs ≈ $50–150/mo total early; scales sub-linearly with customers because runs are bursty and short.
- OpenTelemetry: self-hosted collector or a free tier early.
