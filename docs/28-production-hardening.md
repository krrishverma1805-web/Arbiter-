# 28 — Production Hardening: from Buildathon submission to flagship product

_Written 2026-09-02, after M0–M5. This is the plan of record for taking Arbiter
from "a rigorous, well-tested reconciliation core with a bounded agent" to "a
multi-tenant product that survives real-world messy data and scales." It is
honest about what exists, what does not, and the order to build it in._

---

## 1. Where the code actually is today (no varnish)

**~9,700 lines.** `packages/engine` (7.1k) is the substance; `datagen` (0.9k),
`api` (0.5k), `web` (1.0k).

| Layer | State | Honest read |
|---|---|---|
| Event store + hash chain + replay | Solid | ADR-0002 done properly. `verify` walks the chain; `replay` reproduces the terminal hash. Deterministic. |
| Money math / decomposition | Solid | Integer paise, settlement identity, ledger cross-check. |
| Matching engine | **Competent, narrow** | 4 passes, Fellegi–Sunter with domain-prior m/u, subset-sum. **Blocks only on `settlement_utr`.** If the UTR isn't cleanly present on both sides, passes 1–2 don't fire and everything falls to subset/fuzzy. No N:M, no cross-period, no per-customer trained model persisted. |
| Ingestion | **CSV only** | Good hygiene (size/row caps, formula-injection guard, PII scrub, quarantine, UTR-from-narration regex). No XLSX, no PDF, no MT940/BAI2/CAMT.053, no API pull, no multi-row headers, no encoding fallback, no multi-currency. |
| Exception classification | Solid, hybrid | Safe-AST spec rules + built-in heuristics. Typed taxonomy. |
| Investigation agent | **Sound loop, thin intelligence** | Bounded PLAN→INVESTIGATE→DECIDE, frozen+hashed prompt, fencing, strict Proposal/Escalate, budgets. **No RAG/vector memory, no verifier pass, no grounding validation of `evidence_refs`, no self-consistency, tiered triage speced but not wired, no agent-confidence calibration, no learning from human accept/reject of proposals.** Never run against the real API here (no key) — only scripted/recorded. |
| Learning loop | Real, minimal | Resolution → drafted safe rule → reviewed spec merge → classifies next run. Per-spec, file-based, single-tenant. No global pattern library, no eval gate before a rule promotes, no FS-model retraining. |
| Cash position | Solid | Deterministic 4-bucket partition that always reconciles. |
| Bench / calibration | Solid | Matching + agent scorecards, ablation, ECE. All synthetic. |
| API | **Thin, unguarded** | FastAPI, `/v1/*`. **No auth. No multi-tenancy. Runs execute synchronously in the request. No job queue. No rate limiting. No idempotency keys. `get_store()` is one process-wide SQLite handle.** SSE stream tails the event log. |
| Web cockpit | Competent | Next.js 15, 3 surfaces, keyboard-first, design tokens, light/dark. No motion system, no command palette, no realtime collab, no streaming investigation view. |
| Persistence | **SQLite, create-only** | `SQLModel.metadata.create_all` on init. No Alembic, no Postgres wiring (the URL is accepted but `psycopg` isn't a dep), no RLS, no connection pool tuning. |
| Deploy | **Compose skeleton** | `docker-compose.yml` references `packages/api/Dockerfile` **which does not exist**. No k8s, no Helm, no image build in CI, no deploy pipeline, no infra-as-code. |
| Observability | **Speced, not built** | docs/13 describes OTEL spans, structured logs, Prometheus counters, `/metrics`. None implemented. `/healthz` + `/readyz` exist. |
| Security | Partial | Prompt-injection defense (fencing + `r_security_scan`), PII scrub, `gitleaks` + `pip-audit` in CI. No authn/authz, no secrets manager, no RLS, no audit-of-access, no encryption-at-rest config. |

**Verdict:** the *hard, differentiating* part — a deterministic, auditable,
replayable reconciliation core with an agent confined to the boundary — is real
and good. Everything that makes it a *product* (multi-tenant, async, observable,
deployable, continuously learning) and everything that makes it *survive real
data* (ingestion breadth, matching robustness, agent accuracy under ambiguity) is
either thin or absent. That is the work.

---

## 2. What "flagship / production-grade" means here, by dimension

Each row is a target state. §3 sequences them.

### Accuracy on real-world data — _the product_
- **Ingestion breadth:** XLSX, PDF bank statements (text + OCR fallback), MT940 / BAI2 / CAMT.053, Razorpay/PG API pull, Tally/Zoho/QuickBooks ledger exports. Multi-row headers, trailing totals, mixed encodings, thousands separators, DR/CR columns, multi-currency with FX.
- **Matching robustness:** multi-key blocking (UTR **or** amount-band+date **or** counterparty **or** order-id set), N:M settlement matching (many bank credits ↔ many batches), cross-period carry-forward (a credit this month for last month's batch), split/merged settlements, per-customer FS model trained from confirmed matches and **persisted per spec version**, counterparty entity resolution.
- **Agent accuracy:** RAG over a resolution memory (vector index of past exceptions + how humans resolved them, per tenant + opt-in global); a **verifier pass** (second model checks the proposal's `evidence_refs` actually support the claim, against the real records); **grounding enforcement** (every `evidence_ref` must resolve to a real record/field or the proposal is rejected); **self-consistency** (N samples, vote) for high-$ exceptions; **tiered triage** wired (cheap model filters, expensive model investigates only the genuinely hard); agent-confidence **calibration** with its own reliability diagram; **active learning** — every human accept/edit/reject is a labeled example that tunes few-shots and the escalation threshold.
- **Evaluation:** real anonymized datasets alongside synthetic; a harder synthetic distribution (adversarial against the current matcher); per-loop scorecards; a regression gate that blocks a merge if any scorecard drops.

### Platform
- Postgres + **Alembic** migrations (`arbiter db upgrade`), connection pooling, read replicas later.
- **Auth**: OIDC (Auth.js / Clerk / WorkOS), organizations, RBAC (viewer / analyst / admin), personal + service API keys, per-request principal.
- **Multi-tenancy + RLS**: every row carries `org_id`; Postgres row-level security policies; the event store, projections, specs, datasets, and learned rules are all tenant-scoped. Cross-tenant leakage is a P0 test.
- **Async execution**: runs are minutes-long — move to a job queue (Arq / Celery / Temporal). API returns `202` + a run id immediately; workers execute; SSE/WebSocket streams progress from the event log.
- **Object storage**: uploads to S3/R2 with signed URLs, virus/type scan, size limits, retention policy.
- **API hardening**: rate limiting (per key + per org), idempotency keys on `POST /runs` and `/resolve`, request-size limits, pagination everywhere, RFC-9457 problem+json (partially there), OpenAPI published, versioning policy.

### Infra / deploy / scale
- **Containers**: `api`, `worker`, `web` Dockerfiles (multi-stage, distroless/slim, non-root, `HEALTHCHECK`); full `docker-compose` for local; a Helm chart for k8s.
- **CI/CD**: build + push images (GHCR), SBOM + image scan (trivy), migration-safety check, deploy pipeline with preview environments per PR, blue/green or rolling with automatic rollback on failed health.
- **Observability**: OpenTelemetry traces (span tree per run, per pass, per tool, per LLM call — the tree is already designed in docs/13 §3.1), structured JSON logs with `run_id` + `org_id` correlation (structlog), Prometheus metrics + Grafana dashboards, **Sentry** for errors, SLOs (run-completion latency, agent p95 cost, API availability) with alerting.
- **Scale**: Redis for caching (spec parse, scorecard, projection folds) + as the queue broker; CDN for the cockpit static assets; horizontal API + worker autoscaling (HPA on queue depth); Postgres connection pooler (pgbouncer); load test to a target (e.g. 500 concurrent orgs, 10k runs/day).
- **Availability / recovery**: Postgres PITR + nightly logical backup + **restore drill in CI**; the event log is the source of truth, so projection loss is always recoverable; documented RTO/RPO; chaos test (kill a worker mid-run → `--resume` completes it).

### Continuous learning
- **Resolution memory**: per-tenant vector store (pgvector) of `(exception embedding → category, resolution, human edits)`; the agent's `similar_exceptions` tool becomes semantic retrieval, not exact-category filter.
- **Global pattern library** (opt-in): anonymized, aggregated exception shapes and their canonical resolutions, shared across tenants — the network effect. Strict anonymization + a tenant kill-switch.
- **Feedback → training**: every accept/edit/reject writes a labeled example. Nightly job: retrain the per-spec FS m/u table from confirmed matches, refresh the agent's per-tenant few-shots, re-tune the escalation threshold against the tenant's own accept rate. **Every promotion goes through an eval gate** — the new artifact must beat the old one on that tenant's held-out set or it is not shipped.
- **Model registry + drift**: version every FS table, prompt, few-shot set; detect input drift (new bank format, new counterparty distribution) and alert.
- **MCP server**: expose Arbiter's read-only tools (`query_evidence`, `decomposition_detail`, `cash_position`, `similar_exceptions`) as an MCP server so other agents (a controller's own assistant, a CFO copilot) can call reconciliation as a capability.

### UX (flagship feel)
- A real motion system (Framer Motion): choreographed transitions, the investigation loop streaming in as the agent works (plan → each tool call → hypothesis → conclusion), optimistic resolution with spring physics, `prefers-reduced-motion` fully honored.
- Command palette (⌘K), keyboard-first everything, an Apple-minimal design system (type scale, one accent, generous whitespace, restrained color — status through shape/weight not hue-noise).
- Realtime: presence (who else is looking at this run), live scorecard as a run streams, WebSocket not just SSE.
- The evidence drawer as the centerpiece — every number two clicks from its source, the agent's trace inline and inspectable.

---

## 3. Sequenced roadmap

Ordering principle: **make it correct on real data before making it big.** A
scalable system that mis-reconciles is worthless; a single-node system that
reconciles a messy real statement correctly is fundable. Infra follows demand.

### Phase 1 — Real-world accuracy _(the moat; do this first)_
1. **Ingestion breadth.** ✅ XLSX (`ingest/xlsx_source.py`, openpyxl), a shared tabular core (`ingest/tabular.py`) with header auto-detection, totals/balance-row stripping, delimiter sniffing and encoding fallback for CSV, `format`-dispatch in `ingest_source`. Still open: PDF (pdfplumber + OCR fallback), a real bank format (MT940 / CAMT.053), multi-currency field + FX, a fixture corpus of real-shaped anonymized statements.
2. **Matching robustness.** ✅ Multi-key blocking (pass 2b). ✅ N:1 (2c) and 1:N (2d) payout matching. ✅ FS calibration persists per spec hash (`FS_CALIBRATION_FITTED` → loaded on the next run; degenerate for the flagship spec, matters for fuzzy-heavy ones). Still open: cross-period carry-forward (needs a cross-run match model); train the FS m/u table itself from confirmed matches (not just the calibration map); counterparty entity resolution.
3. **Agent accuracy.** ✅ Grounding enforcement (`agent/grounding.py` — reject proposals whose `evidence_refs` don't resolve; deterministic category **and action↔category** check; `grounded_confidence` replaces the model's self-assessment). ✅ Agent-confidence calibration (`bench` agent ECE). ✅ RAG resolution memory (`agent/memory.py` — IDF-cosine over exception-shape features, cross-run; pgvector + cross-tenant is Phase 4). Still open: a 2nd-model verifier, tiered triage wiring (needs the live API), self-consistency for high-$ exceptions.
4. **Evaluation upgrade.** ✅ CI regression gate — `arbiter bench --gate bench/baseline-800.json` fails the build if any tracked metric moves the wrong way past its tolerance (`bench/gate.py`); the absolute floor stays as a second check. Still open: a harder synthetic distribution, real anonymized datasets, per-loop scorecards.

**Exit:** on a corpus of real (anonymized) messy statements, auto-match ≥ 90%,
false-match ≤ 1%, agent category-accuracy ≥ 85% with calibrated confidence, and
the regression gate is live.

### Phase 2 — Multi-tenant platform
5. Postgres + Alembic; `org_id` on every table; RLS policies; cross-tenant leakage test. — ✅ **`org_id` on the event store + `EventStore(url, org_id=...)` tenant scoping + run-id partitioning by tenant + the cross-tenant isolation test** (`test_events.py`). Still open: Postgres wiring + Alembic, Postgres RLS policies.
6. Auth (orgs, RBAC, API keys); every route takes a principal; access audit log. — ✅ **API-key auth (`arbiter_api/auth.py`), a per-request `Principal` in a ContextVar, tenant-scoped store, RBAC (`viewer`/`analyst`/`admin`) on the mutating routes, `GET /v1/me`, `arbiter-api issue-key`, and the "two API tenants can't see each other" test.** Still open: an access audit log; the cockpit sending its key.
7. Async runs: job queue + workers; `POST /runs` → 202; progress over WebSocket. — ✅ **DB-backed job queue (`arbiter_api/jobs.py`), atomic claim, `arbiter-api worker` / `make worker`, `ARBITER_ASYNC=1` toggle (inline default), retries + dead-letter, tenant-scoped `GET /v1/jobs`.** Still open: WebSocket progress (SSE stream already exists).
8. Object storage for uploads; rate limiting; idempotency keys; published OpenAPI. — ✅ **per-tenant token-bucket rate limiting (`ratelimit.py`, 429 + `Retry-After`)**. Still open: object storage for uploads, idempotency keys, a published/pinned OpenAPI.

**Exit:** two orgs cannot see each other's data (proven by test); a run is
queued and executed by a worker; the API survives a load test at target RPS.

### Phase 3 — Infra, deploy, observability
9. Dockerfiles (api/worker/web) + full compose + Helm chart. — ✅ **the `api`/`worker` image (`packages/api/Dockerfile`, multi-stage, non-root, healthcheck) + a real `docker-compose` (`db` + `api` + 2× `worker` behind the `app` profile).** Still open: a `web` image, a Helm chart.
10. CI/CD: image build+scan+push, migration gate, preview envs, rolling deploy + auto-rollback. — ✅ **CI `docker` job: builds the image (GHA cache) and asserts a container answers `/healthz`.** Still open: image scan + push to a registry, migration gate, preview envs, deploy pipeline.
11. OpenTelemetry + structlog + Prometheus/Grafana + Sentry + SLOs + alerting.
12. Redis cache + CDN + autoscaling + pgbouncer; backup + **restore drill in CI**; chaos test.

**Exit:** `helm install` brings up the stack; a PR gets a preview URL; a killed
worker's run self-heals; a backup restores in CI; dashboards show the span tree.

### Phase 4 — Continuous learning platform
13. Per-tenant resolution memory (semantic `similar_exceptions`).
14. Feedback → nightly retraining (FS table, few-shots, threshold) **behind an eval gate**.
15. Opt-in global pattern library with hard anonymization + kill-switch.
16. Model registry + drift detection; MCP server.

**Exit:** a tenant's month-3 auto-match rate is measurably higher than month-1 on
their *own* data, with every model promotion gated by an eval.

### Phase 5 — Flagship UX
_Started: ✅ the investigation trace renders in the evidence drawer (turn text +
tool calls, from the `AGENT_INTERACTION` events)._

17. Framer Motion system; streaming investigation view; ⌘K palette.
18. Apple-minimal design system pass; realtime presence + live scorecard over WebSocket.

**Exit:** a judge (or a prospect) watches an agent investigate in real time and
can triage the whole queue without a mouse.

---

## 4. For the Buildathon specifically

The submission is judged on **Problem Taste, Build Quality, AI Judgment, Failure
Recovery** — not on whether it has Kubernetes. What moves those needles before the
deadline, in order:

1. **Phase 1.3 (agent accuracy) + 1.4 (harder eval)** — directly lifts "AI
   Judgment" and gives real, defensible numbers. Highest judging leverage.
2. **Phase 1.1 (ingestion) + one real anonymized dataset** — kills the "synthetic
   data" asterisk, the single biggest credibility gap (docs/08, docs/11).
3. **Phase 5.1 (streaming investigation view)** — makes "watch the agent think"
   real in the demo; strong "Build Quality" + "Problem Taste" signal.
4. Everything in Phases 2–4 is the *startup* roadmap, not the *submission*. Build
   it after, in the open, and the BUILD-LOG becomes the fundraising story.

The pitch is honest: "the hard part — a deterministic, auditable core an auditor
can re-verify, with AI confined to the boundary — is done and tested. Here is the
roadmap to a platform, and here is why this sequence." Judges reward a team that
knows the difference.
