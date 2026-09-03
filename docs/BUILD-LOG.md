# Build Log

An honest, running account of what broke during development and how it was resolved.
This directly serves the Buildathon's **Failure Recovery** criterion — kept from day one,
not reconstructed at the end.

Format: newest first. Each entry: what broke · how it showed up · root cause · fix · what changed to prevent recurrence.

---

## 2026-09-03 — Phase 3/5: Alertmanager + cockpit motion

`deploy/monitoring/alertmanager.yml` — a `page`/default route split, an inhibit
rule, `send_resolved`; `prometheus.yml` gained the `alerting:` block; an
`alertmanager` service joins the `monitoring` compose profile. The webhook
receivers are inert placeholders — set a real Slack/PagerDuty target per env.

Cockpit motion (`Cockpit.tsx`, `framer-motion`): the evidence drawer slides +
fades on open/close via `AnimatePresence`, its body cross-fades when you change
selection (`key={current.id}`), and a `layoutId` accent bar springs between
exception rows. `useReducedMotion` zeroes every transition.

## 2026-09-03 — Phase 1: multi-currency / FX

`SourceSpec.fx = {"base": "INR", "rates": {"USD": 83.2, …}}`. In `normalize_row`,
a row whose `currency` differs from the base is converted (amount + fee + tax)
before matching; the pre-conversion amount and currency go into
`external_ids.fx_orig_amount_minor` / `fx_orig_currency`. An unrated currency is
quarantined ("no FX rate for JPY->INR") rather than silently mis-matched.
`_classify_residual` gained an `FX_DIFFERENCE` branch — a batch residual within
2% of expected, on a batch that has FX-converted line items, is the conversion
spread, not an unexplained gap. 4 tests, 175 total, gate green.

## 2026-09-03 — Phase 1: counterparty entity resolution

`match/entity.py`: `canonical_entity(name)` folds a counterparty to a stable key
— lowercases, strips bank-narration prefixes (`NEFT CR `, `RTGS DR `, …),
drops legal-form / honorific noise (`PVT`, `LTD`, `PRIVATE`, `M/S`, `GMBH`, …)
and punctuation, so "ACME SOFTWARE PVT LTD" / "Acme Software Private Limited" /
"M/S Acme Software" all become `acme software`. `same_entity` additionally
matches an abbreviation against its longer legal name (token-subset).

Wired in three places: the fuzzy matcher (a +1-bit tiebreak when a bank
narration's party resolves to the settlement batch's party), the resolution
memory's feature bag (`cp:` tokens are canonical), and `counterparty_history` —
which `orchestrate` now actually populates from the tenant's earlier completed
runs, keyed on the canonical entity. 4 tests, 171 total, gate green.

## 2026-09-03 — Phase 1: 2nd-model verifier + tiered triage + self-consistency

Three agent-accuracy layers, all gated so `--no-ai` / no-key / the offline
tests are untouched:

- **Verifier pass** (`investigator._verify`) — after a proposal clears the
  deterministic grounding check, if a `verifier` client is supplied and the
  exception is ≥ `verify_above_minor`, an independent model sees the proposal +
  the *resolved* cited records and returns `{supported, reason}`; `false` →
  `verifier_rejected` escalation. The verifier turn is appended to
  `inv.interactions` (`role: "verifier"`) so it lands in the audit trace.
- **Tiered triage** (`orchestrate.make_client(..., exc=)`) — `model_policy:
  tiered` + `triage_below_minor`: a low-$ non-UNEXPLAINED exception goes to the
  small model, everything else to opus; per-category `effort`.
- **Self-consistency** (`orchestrate._self_consistent`) — an exception ≥
  `self_consistency_above_minor` runs `self_consistency_samples` full
  investigations; the majority category wins, no majority → `inconsistent`
  escalation. Only the winning run's interactions are persisted, so `replay`
  still reproduces it in one pass; the combined token cost is kept.

`Escalate.reason` gained `verifier_rejected` / `inconsistent`. Spec
`adjudication` gained `verify` model + the four threshold knobs. 5 offline tests
+ 1 live. 167 tests, gate green.

## 2026-09-03 — Phase 1: cross-period carry-forward

`match/cross_period.py`. `prior_open_batches(store, spec_hash, exclude_run_id)`
folds the tenant's earlier *completed* runs for the same spec and returns the
settlement batches (`settlement_utr`, net, from-run, period) that ended a run
still open (`TIMING` / `MISSING_UTR` / `SPLIT_SETTLEMENT` / `UNEXPLAINED` /
`PARTIAL_PAYMENT`). `build_exceptions` gained a `prior_batches` arg: a
would-be-orphan bank credit that `match_carry_forward` ties to one (by UTR, then
by net amount) is classified `TIMING` / `rule:r_cross_period` with a
`note="carried forward — settles batch … left open by run … (period …)"` — the
new `Exception_.note` field.

Deliberately not an auto-match: the batch lives in another run's ledger, so a
human still confirms. Replay-safe because classification only runs when
`EXCEPTION_OPENED` isn't already on the log — a replay in a fresh store (no
priors) never re-classifies. `run.py` wires it via `prior_open_batches` before
`build_exceptions`. 4 tests, 162 total, gate green.

## 2026-09-03 — Phase 1: MT940 + CAMT.053 bank-statement ingestion

Two real bank-statement formats, both **dependency-free**:
`ingest/mt940_source.py` (a tolerant `:61:`/`:86:` SWIFT tag parser — a
malformed `:61:` is quarantined, not fatal) and `ingest/camt_source.py`
(ISO 20022 XML via stdlib `xml.etree`, namespace-agnostic). Each `:61:` / each
`<Ntry>` becomes a row with the **same canonical keys a `bank_csv` source
produces** (`amount` magnitude + `debit` for the sign, `value_date`,
`posted_date`, `narration`, `account_no`), so the spec column map,
`extract_utr(reference)` derive and card-number scrub all apply unchanged.
`ingest_source` routes on extension first (`.sta/.mt940/.940` → MT940,
`.xml` → CAMT), `spec.format:` only disambiguates a bare `.txt`. `run.py`
`_SOURCE_EXTS` / `_dataset_hash` widened to match.

Snags while writing the tests: the MT940 debit row set only `debit`, so
`normalize_row` raised "missing amount" before it checked the sign — now both
readers put the magnitude on `amount` and add `debit` for outflows; and the
`.xml` file was routing to the MT940 reader because the spec's `format: mt940`
string matched first. 6 tests, 158 total, gate green.

## 2026-09-03 — Phase 3: Redis cache + deploy pipeline

`arbiter_api/cache.py` — `get_or_set(key, ttl, fn)`. The scorecard endpoint
(folds the whole run, re-verifies the chain, re-scores) is memoised per
`(org, run, terminal-hash)` once the run is complete and therefore immutable —
no invalidation problem, entries just expire. Redis when `REDIS_URL` is set
(shared across API replicas), an in-process TTL dict otherwise. `redis` service
in `docker-compose`, a Deployment + Service in the chart (`redis.enabled`,
`allkeys-lru`). New `arbiter-api[redis]` extra. 1 test (second scorecard hit is
served from cache).

`.github/workflows/deploy.yml` — fires on a green `ci` run on `main`; dormant
until `KUBE_CONFIG` is set, then `helm upgrade --install --atomic --wait`
(the new revision auto-rolls-back if its pods don't go healthy; the pre-upgrade
hook Job migrates first) and a live `/healthz` smoke.

Chart now renders 18 resources, all kubeconform-clean. 153 tests.

## 2026-09-03 — Phase 4: pgvector resolution memory

`agent/vector_memory.py`: `ResolutionMemory` re-folds every run of the tenant on
every construction. `VectorResolutionMemory` signed-feature-hashes each resolved
exception's shape into a 256-dim unit vector (deterministic — no embedding
model, the core stays LLM-free), persists it to a `resolution_vectors` table on
the store's DB (tenant-scoped, raw DDL so it's out of Alembic), and only embeds
resolutions it hasn't seen. `recall` is a `pgvector <=>` ANN query when the
extension loads, an in-Python cosine scan otherwise — same
`recall(exc, records, k, floor)` signature so `similar_exceptions` can't tell.
`orchestrate` prefers it (`ARBITER_VECTOR_MEMORY`, default on) and falls back to
the old memory on any error.

3 tests. 152 total, gate green.

## 2026-09-03 — Phase 4: opt-in global pattern library

`arbiter_engine/learn/global_patterns.py` — the network effect, done carefully.
On a resolve (CLI + API) the exception's *shape* — `anon_shape`: category,
residual band, record-count band, sorted source/kind types, and three
has-a-reference / -counterparty / -dispute-id booleans — plus the action goes to
a **separate** library DB (`ARBITER_GLOBAL_DB_URL`). No amounts, names, ids,
free text, or org id ever cross; the contributor is `sha256(org_id + salt)` so
"3 other teams resolved this as accept_variance" works without knowing who.

`similar_exceptions` gains a `from_the_network` section. `ARBITER_GLOBAL_PATTERNS`
= `off` (default) / `consume` / `contribute` is the per-tenant kill-switch and
`org_id == "local"` never contributes.

The library table uses its own `MetaData` (not `SQLModel.metadata`) — the
migration-drift test caught the first cut trying to add `global_patterns` to the
tenant schema. 5 tests incl. an identifier-leak assertion. 149 total.

## 2026-09-03 — Phase 4: input-drift detection + model registry

`arbiter_engine/learn/drift.py`: after ingest, each run gets a numeric profile
(source/kind mix, reference/counterparty/value-date coverage, amount log-median
+ CV, counterparty cardinality). It's compared by population-stability index
against the mean of the tenant's recent runs for the same spec; past
`_PSI_ALERT` we record which features moved. The `INPUT_DRIFT_DETECTED` event
lives on `__learn__<org>` — **not** the reconciliation chain — because the
baseline depends on other runs, so putting it inline would make a replay in a
fresh store diverge. `run.py` calls it in a `try/except` that can never fail a
run.

`arbiter models --spec` folds the learned-artifact registry from the log:
promoted/rejected FS models, fitted calibration maps, the drift timeline. (The
agent prompt is already hashed onto every interaction event.)

4 drift tests incl. "stays off the reconciliation chain / run still verifies".
144 tests, gate green.

## 2026-09-03 — Phase 5: realtime presence over WebSocket

`WS /v1/runs/{id}/ws` + `arbiter_api/presence.py` — an in-process room hub keyed
`(org_id, run_id)`. On join/leave the whole room gets a `{type:"presence",
viewers:[…]}` roster; a resolve on the run fans out `{type:"exception_resolved",
…}` (from the sync handler via `hub.broadcast_soon`, which hops to the event
loop with `call_soon_threadsafe`). The cockpit header shows viewer initials +
"N viewing"; `usePresence` degrades to solo if the socket won't open. Multi-
replica note in the module: swap `_Hub` for Redis pub/sub.

Snags: (1) `resolve("Bearer ")` — an empty query `key` still matched the
`bearer ` prefix, looked up an empty hash and closed 1008; pass `None` when no
key. (2) the SSE stream only stopped when RUN_COMPLETED was the *last* event —
a resolve on the same run left it spinning 120s; now it stops as soon as
RUN_COMPLETED is anywhere on the log. 1 WS test (roster of two + resolve
fan-out). 140 tests.

Trivy (now working) flagged two fixable CRITICALs: Next.js
CVE-2025-29927 (middleware auth bypass) → bumped `next` 15.1.6 → 15.5.25;
`libgnutls30` on the web base → `node:20-slim` → `node:22-slim` (trixie) plus
`apt-get upgrade` in both runtime stages. One residual — CVE-2026-59873 in the
`tar` vendored inside `next/dist/compiled` (unbumpable without Next; no runtime
path extracts a tarball) — is in a documented `.trivyignore`.

## 2026-09-02 — Phase 5: ⌘K command palette + Apple-minimal pass

`CommandPalette.tsx` (`cmdk`) mounted in the root layout — ⌘K / Ctrl-K opens it
anywhere; navigate, jump to a recent run, or switch theme (light / dark /
system, persisted to `localStorage`, restored by a tiny pre-paint script so
there's no flash). `globals.css`: tighter letter-spacing on headings,
antialiasing, `color-mix` selection colour, thin scrollbars, and
`prefers-reduced-motion` hardened to ~0ms on every element/pseudo-element.

## 2026-09-02 — Phase 5: streaming investigation view + motion system

`GET /v1/runs/{id}/stream` now emits UI-shaped frames (`_stream_frame`): agent
turn text + tool-call names, proposal (with `grounded_confidence`) and
escalation payloads, `EXCEPTION_OPENED` impact, `RUN_COMPLETED` counts — plus
`id:` lines + `Last-Event-ID` honouring for reconnection, `: ping` heartbeats
and `X-Accel-Buffering: no`.

`web/src/components/LiveRun.tsx` + `/runs/[id]/live`: opens the stream, folds it
into a per-exception timeline, and choreographs it with Framer Motion — cards
spring in, each agent turn slides in under its investigation, the proposal /
escalation fades in as the verdict. A phase rail tracks ingest → match →
classify → investigate → done. `useReducedMotion` collapses every transition to
0s. `NewRun` sends an AI run here; `--no-ai` still goes straight to the cockpit.
`framer-motion` + `cmdk` added (cmdk is for the next slice). 139 tests + a
stream-shape API test.

Regression (three tries): `trivy-action` pinned a non-existent
`setup-trivy@v0.2.2`; the raw `install.sh` and `setup-trivy@v0.2.6` both exit 1
right after resolving the version on the runner. Settled on running
`aquasec/trivy:0.58.1` as a container with the docker socket mounted — no
installer, scans the loaded local images directly.

## 2026-09-02 — Phase 4: feedback → FS retraining behind an eval gate

`arbiter_engine/learn/retrain.py` + `arbiter retrain --spec`. Every confirmed
match a tenant accumulates is a labelled positive; a matched bank credit paired
with a *different* run's batch is a negative. `FSModel.from_labeled` re-estimates
the m/u table from those — the matcher literally learns this tenant's data.

The gate: the labelled pairs are split (spec-hash-seeded, so the decision is
reproducible); the candidate must beat the incumbent on held-out ROC-AUC by
`margin` (0.01) or it is **rejected**. Both outcomes are events —
`FS_MODEL_PROMOTED` (carries the full mu table) / `FS_MODEL_REJECTED` — parked on
a `__learn__<org>` pseudo-run (hidden from `store.runs()` by a new
`include_internal` flag). `run.py` now loads a promoted table via
`fs_store.load_fs_model` ahead of the domain prior + calibration map.

Bug found writing the AUC: had the Mann–Whitney tie term as `- 0.5·ties`
instead of `+`, so a signal-blind model scored −0.5. 5 tests (incl. the gate
rejecting a worse candidate, and a promoted run still verifying). 138 total.

## 2026-09-02 — Phase 4: MCP server (read-only reconciliation as a capability)

`arbiter_api/mcp_server.py` — a FastMCP stdio server (`arbiter-api mcp`, behind
the `arbiter-api[mcp]` extra) exposing 7 read-only tools: `list_runs`,
`run_summary`, `verify_run`, `cash_position_for`, `query_evidence`,
`decomposition_detail`, `list_exceptions`. Each is a projection read reusing the
engine's own `agent.tools` — no tool can mutate a match, a record, money, or the
event log, and a test asserts no registered tool name contains a mutating verb.
Tenant scope from `ARBITER_MCP_ORG`. So a CFO copilot or a controller's
assistant can call reconciliation as a capability.

Snag: `mcp>=1.2` resolved to `mcp 2.x`, which renamed `FastMCP` → `MCPServer`
and moved the module. Pinned `mcp>=1.2,<2` to keep the widely-supported v1
API. The CI `test` job now `uv sync --extra mcp` so the suite really exercises
it. 134 tests.

Also fixed `4834930`'s successor: `aquasecurity/trivy-action@0.28.0` doesn't
exist — the tags are `v`-prefixed. Pinned `@v0.29.0`.

## 2026-09-02 — Phase 3: pgbouncer + Grafana/Prometheus alerting

`deploy/monitoring/` — a Prometheus scrape config, SLO alert rules
(`alerts.yml`: 5xx-rate > 2%, API p95 > 750ms, API-down, run-failure-rate > 5%,
queue-depth > 50), and a Grafana dashboard JSON (request rate, latency
quantiles, run outcomes, queue depth, error-ratio stat). `docker compose
--profile monitoring up` brings up Prometheus + Grafana against the compose API.

pgbouncer (transaction pooling): a `pgbouncer` service in `docker-compose`
(`edoburu/pgbouncer`) that `api` + `worker` now connect through
(`ARBITER_DB_URL` → `pgbouncer:6432`); `migrate` still talks to Postgres
directly because DDL wants a session. Mirrored in the Helm chart as a
Deployment + Service (`pgbouncer.enabled`, default on). Chart now renders 16
resources, all kubeconform-clean.

## 2026-09-02 — Phase 3: image scan + SBOM + GHCR push

The `docker` CI job now, after the smoke tests: Trivy-scans both images
(`ignore-unfixed`, fails only on a fixable CRITICAL so base-image noise can't
red main), uploads a CycloneDX SBOM as an artifact, and — only on a push to
`main` — logs in to GHCR with the workflow token and pushes
`ghcr.io/<owner>/arbiter-{api,web}` at `:<sha>` and `:latest`. The job gained
`permissions: packages: write`.

## 2026-09-02 — Phase 3: restore drill + worker chaos recovery

**Restore drill.** New CI `recovery` job: a real `postgres:16` service,
`arbiter-api db upgrade` (so the RLS migration runs against real Postgres for
the first time), a deterministic `--no-ai` run, then `pg_dump -Fc` → `DROP
SCHEMA public CASCADE` → `pg_restore`. Afterwards `arbiter verify --json` (new
`--json` flag on the CLI) and `replay` must show the same `terminal_hash`, the
same event count, and `intact: true` — proving the hash chain is exactly
recoverable from a backup.

**Chaos.** Found a real gap: a job stuck in `running` because its worker was
killed was never reclaimed. Added `jobs.reclaim_stale()` — run at the top of
every `claim()` — which requeues any `running` job whose lease
(`ARBITER_JOB_LEASE_SECONDS`, default 300s) has expired, or dead-letters it if
it is out of attempts. Two tests: a dead worker's job is picked up and
completed by the next worker; a lease-expired job out of attempts is
dead-lettered with `"worker lease expired"`.

Regression on `4834930`: the `web` CI job failed — `pnpm/action-setup@v4` reads
`packageManager` from the *repo-root* `package.json` (the job's
`working-directory: web` only affects `run:` steps), so it saw no version.
Fixed with `package_json_file: web/package.json` and moved the action before
`setup-node` so `cache: pnpm` works. 131 tests.

## 2026-09-02 — Phase 3: OpenTelemetry span export + Sentry (opt-in)

`arbiter_engine/tracing.py` — a zero-dependency shim: `span("match", …)` is a
transparent context manager unless a tracer provider is configured, so the
engine keeps no hard OTel dependency (`make demo`, the tests, the docker image
stay lean). `run.py` now opens `run → ingest → match → classify → investigate`
spans.

`arbiter_api.obs` gains `configure_sentry()` (on iff `SENTRY_DSN` set) and
`configure_tracing(app)` (on iff `OTEL_EXPORTER_OTLP_ENDPOINT` set) — the latter
stands up a `TracerProvider` with an OTLP/HTTP exporter, instruments FastAPI +
SQLAlchemy, and points the engine shim at the same provider so a request and its
run are one trace tree. Deps live in a new `arbiter-api[observability]` extra;
mypy ignores the missing modules when it isn't installed.

Regression: the web `docker` job failed on `dece47f` — `corepack` in
`node:20-slim` pulled `pnpm@11` (needs Node 22) because nothing pinned the
version. Fixed by pinning `packageManager: pnpm@10.28.2` in `web/package.json`,
refreshing corepack in the Dockerfile, and dropping the hard-coded `version` in
the CI `web` job so it reads the pin. 129 tests, gate green.

## 2026-09-02 — Phase 3: web image + Helm chart

`web/Dockerfile` (Next.js `output: "standalone"`, `node:20-slim`, non-root
`nextjs` uid 10001, `HEALTHCHECK`) and a `web` service in `docker-compose.yml`.
A `.dockerignore` keeps the build contexts small.

`deploy/helm/arbiter/` — a real chart for the three workloads: `api`
(Deployment + Service + HPA + PDB), `worker` (Deployment + HPA,
`terminationGracePeriodSeconds: 120` so an in-flight run is re-claimed not
lost), `web` (Deployment + Service). Schema migrations run as a
`pre-install,pre-upgrade` hook Job (`arbiter-api db upgrade`). ConfigMap +
Secret (or `existingSecret`), a shared uploads PVC, optional Ingress,
`readOnlyRootFilesystem` + dropped caps + `seccompProfile: RuntimeDefault`
everywhere.

CI gains a `helm` job — `helm lint` + `helm template` piped through
`kubeconform -strict` against the k8s 1.28 schema (14 resources, all valid) —
and the `docker` job now also builds the `web` image and curls the cockpit.

## 2026-09-02 — Phase 2: Postgres row-level security

Migration `28f8eb3b` (Postgres-only — a no-op on SQLite): `ENABLE` +
`FORCE ROW LEVEL SECURITY` on `events`, `jobs`, `idempotency_keys`, with a
policy restricting every row to `current_setting('arbiter.org_id')`. The store
now runs each transaction through `EventStore._session()`, which on Postgres
sets that GUC per transaction (`set_config(..., is_local=true)`) — so even a
query that forgot its `WHERE org_id =` filter cannot cross a tenant. Defense in
depth behind the application-level scoping.

`test_migrations.py` asserts the RLS revision applies cleanly on SQLite and the
store still works. 127 tests.

## 2026-09-02 — Phase 2: idempotency keys on the mutating routes

`arbiter_api/idempotency.py` + an `idempotency_keys` table (migration
`5c450dd7`). `POST /v1/runs` and `.../resolve` honour an `Idempotency-Key`
header: the first `(org, key)` response is stored (24 h TTL) and every later
request with the same key gets it back verbatim — so a retried run doesn't
enqueue twice and a retried resolve doesn't append a second event. Same key +
a *different* body → **409** (a client bug worth surfacing).

The drift test caught the new table immediately — the migration was written and
`env.py` now imports `arbiter_api.idempotency`. `test_api.py`: run-replay,
resolve-replay, key-conflict. 126 tests.

## 2026-09-02 — Phase 2: tenant-scoped upload storage

`POST /v1/uploads` (multipart) writes a customer's CSV/XLSX under
`{ARBITER_UPLOADS_DIR}/{org_id}/{upload_id}/`; `POST /v1/runs` then takes
`dataset: "upload:<id>"`. `arbiter_api/storage.py` — a `Storage` class
(filesystem-backed; an S3/R2 impl slots behind `save` / `path` / `list_ids`),
filename sanitised, `.csv/.xlsx/.xlsm` only, 50 MB / 12-files caps.
`arbiter_api/resolve.py` centralises spec + dataset resolution (path · name ·
`upload:` ) for both the route and the worker.

`test_api.py`: upload the three source files → run against `upload:<id>` →
completed run; a `.txt` is rejected 422; uploads are tenant-scoped. 124 tests.
`python-multipart` added. Still open: S3/R2 backend, a virus scan, a retention
policy.

## 2026-09-02 — Phase 2/3: Alembic migrations + `arbiter-api db upgrade`

`packages/api/arbiter_api/migrations/` — Alembic configured in Python (no
`alembic.ini`), `env.py` pulls the union of every `table=True` model (`events`,
`api_keys`, `jobs`) from `SQLModel.metadata`. One initial migration.
`arbiter-api db upgrade` runs `alembic upgrade head`; `db current` shows the
version. `docker-compose` gets a `migrate` one-shot service that `api` and
`worker` wait on (`service_completed_successfully`).

`test_migrations.py`: **`alembic upgrade head` on an empty DB produces exactly
the schema `SQLModel.metadata.create_all` would** — so a migration can never
silently drift from the models — and `upgrade` is idempotent. 121 tests. The
engine still `create_all`s for the SQLite dev/test path (matches the initial
migration byte-for-byte); prod runs migrations.

## 2026-09-02 — Phase 3: structured logs, request correlation, Prometheus metrics

`arbiter_api/obs.py`: structlog JSON logging (one line per request —
`request_id`, method, path, status, `duration_ms`), a middleware that binds a
`request_id` (from the client's `X-Request-Id` or fresh) and echoes it on the
response, and `GET /metrics` in Prometheus text format —
`arbiter_http_requests_total{method,path,status}`,
`arbiter_http_request_seconds`, `arbiter_runs_total{outcome}`,
`arbiter_job_queue_depth` (path labels have ids collapsed to `{id}` so
cardinality stays bounded). `/metrics` is public and never 500s.

`test_api.py` asserts the `X-Request-Id` header and the metric names. 119 tests.
Still open: OpenTelemetry span export (`--trace`), Grafana dashboards, Sentry,
SLO alerting.

## 2026-09-02 — Phase 3: the API / worker Docker image + a CI build job

`packages/api/Dockerfile` — multi-stage (uv, cache-mounted dep layer), `python:
3.12-slim` runtime, non-root uid 10001, `HEALTHCHECK`, `ENTRYPOINT ["arbiter-
api"]` so `command: ["worker"]` runs the queue consumer from the same image.
`arbiter-engine[postgres]` / `arbiter-api[postgres]` extras add `psycopg[binary]`;
the image installs them and defaults `ARBITER_DB_URL` to Postgres.

`docker-compose.yml` rewritten: `db` (postgres:16) always up; `api` + `worker`
(×2 replicas, `ARBITER_ASYNC=1`) behind the `app` profile —
`docker compose --profile app up --build`.

New CI `docker` job: builds the image with the GHA cache and asserts a container
starts and answers `/healthz`. 118 tests.

## 2026-09-02 — Phase 2: per-tenant rate limiting

`arbiter_api/ratelimit.py` — a token-bucket limiter keyed on
`(org, subject)` with two buckets: a generous one for reads (600/min, burst 120)
and a tight one for writes (60/min, burst 20), all env-tunable. The `_gate`
middleware checks it after auth; over the limit → **429** with `Retry-After`.
In-memory (correct for one API instance; a Redis bucket is the multi-node swap,
same interface). `test_api.py` trips a tiny bucket and asserts the 429 + header;
an autouse fixture resets the limiter between tests. 118 tests.

## 2026-09-02 — Phase 2: async runs — a DB-backed job queue

`arbiter_api/jobs.py`: a single `jobs` table with an atomic claim (`UPDATE …
WHERE status='queued' … RETURNING`, honoured by both SQLite and Postgres), so it
survives a restart and needs no Redis. `POST /v1/runs` records a `Job` for the
caller's org; with `ARBITER_ASYNC=1` it returns `202 {job_id, status:"queued"}`
and `arbiter-api worker` (`make worker`) picks it up; otherwise it runs inline
(the default — demo + tests unchanged). Up to `MAX_ATTEMPTS` retries, then
`failed`. `GET /v1/jobs` and `GET /v1/jobs/{id}` are tenant-scoped.

`test_api.py`: queued → worker drains → done + a completed run; a job failure is
recorded on the row, not raised; the jobs list is tenant-scoped. 117 tests. Still
open: WebSocket progress (the SSE stream exists), a proper worker Dockerfile
(Phase 3).

## 2026-09-02 — Phase 2: API auth — principal, API keys, RBAC

`arbiter_api/auth.py`: every request carries `Authorization: Bearer <key>`; the
key is sha256-hashed and looked up in an `api_keys` table (org, subject, role).
A middleware resolves the `Principal` into a `ContextVar` so handlers reach a
**tenant-scoped store** (`current_store()` → `get_store(principal.org_id)`)
without threading it through every signature — `get_store()` is shadowed in
`app.py` to return it.

- `ARBITER_ENV=dev` + no key → the `local` org, `admin` role (demo + tests need
  no setup). `prod` + no/invalid key → **401**.
- RBAC: `analyst` to start a run or resolve; `admin` to merge learned rules.
  Wrong role → **403**.
- `GET /v1/me` returns the principal. `arbiter-api issue-key --org --subject
  --role` mints a key.

`test_api.py`: dev principal, prod 401, viewer 403 on run/merge, and **two API
tenants do not see each other's runs**. 114 tests. Still open: an access audit
log, and the cockpit sending its key in prod.

## 2026-09-02 — Phase 2: tenant isolation in the event store

`EventStore(url, org_id=...)` — one instance is scoped to one tenant. Every
read and write (`append`, `events`, `runs`, `verify`, `purge`) filters
`Event.org_id`, so two stores over the same database with different `org_id`
cannot see each other's runs. `Event` gets an indexed `org_id` column
(default `"local"` — every existing path is byte-unchanged in behaviour).

`run.py` folds the store's `org_id` into the config hash when it isn't
`"local"`, so the same spec + dataset run by two tenants gets **different**
`run_id`s (they would otherwise collide — the hash never included the tenant).
`RUN_STARTED` records `org_id` in the tamper-evident payload. `get_store(org_id)`
on the API is now cached per-org.

`test_events.py`: two tenants over one DB file are isolated for reads, verify,
and purge; `execute()` partitions run ids by tenant; the default path is
unchanged. 110 tests. **Still open in Phase 2:** the API principal / auth that
picks the org (right now it's always `"local"`), RLS policies for Postgres,
async workers.

## 2026-09-02 — Phase 5.1: the investigation trace in the cockpit

`GET /v1/exceptions/{run}/{id}` now returns `agent_trace` — the agent's turn-by-
turn steps for that exception, folded from the `AGENT_INTERACTION` events (turn
text + which tools it called + stop reason). The evidence drawer renders it as a
collapsible "investigation trace · N turns" list above the proposal, so a judge
watches the agent reason: plan → each tool call → hypothesis → conclusion.
`test_api.py` asserts the field is present; `pnpm typecheck + lint + build`
clean. 108 tests.

## 2026-09-02 — Phase 1.3: agent verifier — action must fit the category

Extends the deterministic category check: the proposal's `suggested_action` must
be coherent with its `category` (`DUPLICATE` → `void_duplicate_of` /
`route_to_human`; `TIMING` → `carry_forward` / `accept_variance`; …). A proposal
with the right category but the wrong fix is internally inconsistent — it caps
`grounded_confidence` at 0.4 and escalates. `test_agent.py`: `TIMING` +
`void_duplicate_of` → escalate. 107 tests.

## 2026-09-02 — Phase 1.2: the matcher's calibration persists per spec

`arbiter bench --calibration --db <store>` now emits an `FS_CALIBRATION_FITTED`
event (`match/fs_store.py`), keyed to the spec hash, carrying the isotonic
recalibration map. `run.py` loads the latest map for the spec before matching, so
the next run's `P(match)` is already calibrated to that customer's data — the
matcher improves with use, deterministically (it folds from the event log;
`replay` never re-runs matching so it's untouched, and a fresh store has no map
so CI is unaffected).

Only adopted from ≥ 12 predictions and ≥ 2 map points. **For the flagship
`razorpay-settlement` spec the FS confidence is effectively single-valued (1.0
for a clean settlement tie), so the map is degenerate and nothing is persisted —
the calibration study already flagged this.** The mechanism matters for
fuzzy-heavy specs where confidence has a real spread. `test_calibration.py`
covers the persist → load → `FSModel` round-trip. 106 tests, gate unchanged.

## 2026-09-02 — Cockpit: surface grounding + the matcher's pass mix

The Phase 1.2 / 1.3 accuracy work was invisible in the UI. The evidence drawer's
proposal panel now shows **grounded confidence** (and, when it differs, what the
model *said*), lists every `evidence_ref` inline, and flags a fabricated citation
or a failed category check in red. The scorecard panel adds the `by_pass`
breakdown (exact / tolerant / blocked / aggregate …) and the agent's grounded
rate + confidence ECE. `pnpm typecheck && lint && build` clean.

## 2026-09-02 — Phase 1.4: mangled-UTR robustness stressor in the generator

The new matcher passes (2b–2d) were only exercised by hand-built fixtures. On
`hard` difficulty the generator now garbles the settlement UTR in a deterministic
~15% of otherwise-clean bank narrations (`... REF <utr with the last 4 chars
reversed>`). Those batches stay in `true_matches` — the correct outcome is still
a clean auto-tie — so if the amount+date blocking pass fails to recover them the
scorecard's recall drops and the gate fires. `test_matching.py` asserts
`by_pass["blocked"] ≥ 1` and recall ≥ 0.85 on a hard batch. `normal` (the CI
gate's difficulty) is untouched. 105 tests.

## 2026-09-02 — Scorecard: `matching.by_pass` breakdown

The scorecard now reports how many matches each pass tied
(`{"exact": 15, "tolerant": 2, "blocked": 1, ...}`), so the robustness passes
are visible in `arbiter bench` and the regression gate can see if the mix
shifts. On the standard 800-record seed the new `blocked` pass already recovers
one batch whose UTR did not cleanly key — auto-match and false-match unchanged.
Baseline regenerated.

## 2026-09-02 — Phase 1.2: aggregated- and split-payout matching (N:1 and 1:N)

Indian PGs roll several small settlements into one bank credit, and banks split
one large payout into tranches. Two new passes, after pass 2b:

- **pass 2c (N:1):** a free bank credit vs the *sum* of 2–4 still-unresolved
  settlement blocks (`_blocks_summing_to`, bounded subset over ≤ 14 blocks).
- **pass 2d (1:N):** the mirror — 2–3 free bank credits summing to one block
  (`_credits_summing_to`, ≤ 10 credits).

Both emit a single `aggregate` match covering every record on both sides; more
than one candidate subset → skip (never guess). Confidence 0.85 (0.78 if the
residual exceeds the rounding band).

Only fire on blocks the UTR key failed that pass 2b did not claim — a no-op on
the clean CI dataset, bench gate unchanged. `test_matching.py`: merge two
credits into one → 2c ties both batches; split one credit into two → 2d ties
both credits. 104 tests.

## 2026-09-02 — Phase 1.4: a CI regression gate on the scorecard

CI had an *absolute floor* (false-match ≤ 1.5%, auto-match ≥ 80%) but nothing
stopped a change from quietly trading, say, match rate for coverage while both
stayed above their floors.

`bench/gate.py` + `arbiter bench --gate <baseline.json>`: nine metrics, each with
a direction (must-not-fall / must-not-rise) and an absolute tolerance. The gate
fails the build if any moves the wrong way past its tolerance. `bench/baseline-
800.json` is the committed reference (regenerated with `make bench-baseline`
when a genuine improvement lands). The absolute floor stays as a second, blunter
check. `test_bench.py` covers the comparison. 102 tests.

## 2026-09-02 — Phase 1.1: XLSX ingestion + a shared messy-tabular core

The engine only read `.csv`, and its CSV reader assumed a clean table (header on
row 0, no junk rows). Real bank / processor exports are `.xlsx` as often as not,
with title lines above the header and a "Grand Total" row at the bottom.

- `ingest/tabular.py` — the shared row loop plus `detect_header` (find the real
  header row by matching the spec's mapped column names) and `is_junk_row` (drop
  a row when every populated cell is a number or an exact totals/balance marker
  and at least one marker is present — so a narration that merely *contains*
  "total" is safe).
- `ingest/csv_source.py` — rewritten to route through the shared core; adds
  delimiter sniffing (`,` `;` `\t` `|`) and an encoding fallback
  (utf-8-sig → utf-8 → cp1252 → latin-1).
- `ingest/xlsx_source.py` — openpyxl, `read_only` + `data_only`, one sheet
  (`spec.sheet` or the first), same core. `SourceSpec` gains `sheet` and
  `header_row`.
- `ingest_source(...)` dispatches on the file extension; `run.py` and
  `_resolve_source_file` / `_dataset_hash` now accept `.xlsx` / `.xlsm`.

**Bug caught in the test:** the "Grand Total" label landed in the *amount*
column (bank.csv's column 0), so the first `is_junk_row` — which special-cased
amount columns — missed it and the row was quarantined as an unparseable amount.
Rewrote the check to be column-agnostic. `test_ingest.py`: an .xlsx with a
2-line preamble + a totals row ingests the exact same records as the CSV.
101 tests, bench gate unchanged.

## 2026-09-02 — Phase 1.2: multi-key blocking (matcher survives a missing UTR)

The matcher blocked **only** on an exact `settlement_utr` join. Real bank
statements routinely drop or reformat the UTR (it lives in free-text narration),
so on real data passes 1–2 would fire on almost nothing and everything fell to
subset/fuzzy.

New **pass 2b** (`match/engine.py`): a settlement block the UTR key could not tie
is retried against every free bank credit whose net is within amount tolerance
and whose date is in-window. Greedy stable assignment by amount closeness; a
runner-up within the rounding band marks the block ambiguous and caps its
confidence below `review`. Confidence comes from amount + date closeness alone
(0.80–0.94) — this pass has no UTR or reference signal by construction and is
never rated above the UTR-keyed passes.

`test_matching.py`: strip every bank UTR from the clean dataset → pass 2b still
ties the batches, and none is mis-tied. Bench gate unchanged at 800 records
(auto 93.75%, false 0.0%, coverage 100%). 100 tests.

## 2026-09-02 — Phase 1.3: resolution memory (semantic `similar_exceptions`)

The `similar_exceptions` tool was an exact-category filter over a
`prior_resolutions` list **that nothing ever populated** — so it always returned
`[]`. Now `agent/memory.py` builds a `ResolutionMemory` from the store's own
`RESOLUTION_APPLIED` history (every prior run's resolved exceptions), turns each
exception into a bag of shape features (category, residual band, record-count
band, source/kind mix, reference + counterparty tokens), and ranks by
IDF-weighted cosine similarity. `Tools` now also carries the exception under
investigation so the tool can query by *its* shape, not just a hint.

Deterministic, dependency-free — the pgvector, cross-tenant version is Phase 4
and the tool interface doesn't change when it lands. `test_agent_memory.py`:
recall across two runs, the tool switches to `method: "semantic"`, features are
stable and shape-aware. 99 tests.

## 2026-09-02 — Phase 1.3: agent grounding + category verification (docs/28)

The agent's `evidence_refs` were self-reported and trusted. Now, before any
proposal reaches a human (`agent/grounding.py`):

- **Grounding.** Every cited `record_id` must resolve to a real record /
  decomposition / match in the run. A citation that points at nothing is a
  fabrication — the proposal is voided and the exception escalates
  (`reason: contradictory`). This is the authoritative `hallucination_rate` now.
- **Category check.** A deterministic test that the proposed category fits the
  evidence shape (DUPLICATE needs a repeated `payment_id`, ROUNDING needs a small
  residual, CHARGEBACK needs a `dispute_id`, …). Zero LLM cost. A mismatch caps
  confidence at 0.4.
- **`grounded_confidence`.** The model's raw self-assessment is never used for
  the escalation decision or shown to the human — it's re-derived from how many
  citations resolved and how well the fields check out. Below `theta_escalate`
  → escalate instead of propose.

The frozen prompt (V1) gained a line telling the model its citations are verified
and its confidence re-derived. `test_agent.py` gains three cases: fabricated ref
→ escalate, weak grounded confidence → escalate, category inconsistent with
evidence → escalate. 95 tests.

## 2026-09-02 — M5 stretch: `arbiter cash-position`

The reconciled ledger answers "is the money right?"; this answers "where is it?" —
every settled rupee partitioned into confirmed-in-bank / in-transit / held /
unexplained, as pure arithmetic (no LLM).

**First cut didn't reconcile.** It summed exception `amount_impact_minor` into the
buckets, but that field is a *severity heuristic* for ranking the queue, not a
balance — it double-counted against `confirmed` and left a ₹30–70k `Δ`.

**Fix: partition the settlement batches, not the exceptions.** Every processor row
belongs to exactly one `settlement_utr`; each batch's net (gross − MDR − GST −
refunds for *its* rows) lands in one bucket, chosen by the highest-severity
exception that touches it, else by whether its decomposition is clean. Now the
four buckets sum back to the processor-side net exactly — `reconciling_delta` is
0 on every seed, and a non-zero value would be surfaced, not hidden.
`test_cash.py` asserts the partition and its determinism.

## 2026-09-02 — M5: the cycle demo, and making the learning loop actually move a number

The learning-loop *mechanism* landed earlier; this is the demo that proves it —
three monthly closes with the learned rule carried forward (`arbiter cycle-demo`,
`make cycle`).

**What didn't work at first.** The pitch (docs/02 §5.3) is "resolve once → the
match rate rises next cycle." But every mechanical anomaly the generator injected
was *already* classified by a base-spec rule, and the one recurring `UNEXPLAINED`
was an orphan bank credit — genuinely undecidable, correctly not generalisable.
There was nothing for a learned rule to catch.

**Root cause.** `datagen`'s `SPLIT_BATCH` injector moved a payment between two
settlement batches but never froze either batch's bank credit, so both re-tied
and the "split" produced no residual at all — a silent no-op anomaly (it was the
one the scorecard's `detected_anomalies` always missed).

**Fix.**
- `_split_batch` now `freeze_bank(dst)`: the destination settlement was paid
  before the order was re-routed into it, so it carries a real, labelled residual
  until someone recognises the two halves net out. The source re-ties cleanly.
- `arbiter resolve --category <C>` (and the API `category` field): a controller
  correcting the classifier — "this UNEXPLAINED residual is a SPLIT_SETTLEMENT" —
  is what seeds the rule. `RESOLUTION_APPLIED` carries the correction; the fold
  applies it to the exception (`classified_by: human:<actor>`).
- `SPLIT_SETTLEMENT` template added to `synthesize.py`:
  `exception.record_count >= {rc} and abs(exception.residual_minor) <= {band}` —
  the `rc` floor (≥ 3, generalised down from the resolved case) keeps it off 1:1
  residuals; the band is 2× the accepted variance, so a larger one still opens an
  exception.

**The demo is an A/B, not a single line.** Each close is a fresh random batch, so
batch-to-batch noise would swamp one metric column. `cycle-demo` scores every
close twice — once on the base spec, once on the carried-forward spec — and
reports the gap. That gap is the rule and nothing else.

**Verified:** the 800-record bench gate is unchanged (auto-match 93.75%,
false-match 0.0%, coverage 100%, replay hash stable); `test_cycle.py` asserts the
later closes never regress and at least one recovers money the base spec left
UNEXPLAINED. Full suite 90 tests, `ruff` + `mypy` clean.

## 2026-09-02 — M5: the learning loop + the Close Memo (docs/02 §5.3, docs/20 §2.6)

When a human resolves an exception, Arbiter drafts a **candidate classification rule**
in the same safe-AST language the spec already uses (`arbiter_engine/learn/synthesize.py`).
The draft is deliberately narrow — it fires only for exceptions that look like the one
just resolved (same category, residual within a widened band, same source) — and only
for mechanical categories. Judgement categories (`UNEXPLAINED`, `AMBIGUOUS`,
`SECURITY_REVIEW`, `WRONG_ACCOUNT`) never generalise: a `draft_rule_from_resolution`
returns `None` and the resolution stays a one-off.

`RULE_DRAFTED` is an event. `arbiter rules pending <run>` diffs a run's drafts against
the live spec; `arbiter rules merge <run>` splices the approved rules into the `rules:`
block as reviewable YAML (provenance comment + `# learned <id>`), bumps `version:`, and
emits `RULE_MERGED`. A merged rule drives classification on the next run — the loop
closes without any model in it. Same three commands on the API
(`/v1/exceptions/.../resolve` now returns `drafted_rule`, `/v1/runs/{id}/rules/pending`,
`/v1/runs/{id}/rules/merge`).

`arbiter memo <run>` renders the **Reconciliation Close Memo** — one self-contained HTML
file, no external resources, opens offline: the result, the settlement decomposition
(gross → MDR → GST → refunds → net), every exception with its category / ₹ impact /
who classified it / status / resolution, and the audit trail with the terminal hash
and the `arbiter verify` command that reproduces it.

**Bugs caught:**
- `merge_rules` first appended rules at EOF, landing a `- id:` list item after the
  `adjudication:` mapping → invalid YAML. Fixed to splice after the last indented line
  of the `rules:` block (a column-0 line or section comment ends the block).
- The spliced `when:` used `yaml.safe_dump(value).strip()`, which emits a trailing
  `...` document-end marker on a scalar — a stray `...` line broke the parse. Switched
  to `json.dumps(value)` (valid YAML double-quoted scalar, handles the `'…'` literals).
- Draft dict / payload key mismatch (`id` vs `rule_id`) surfaced as a pydantic
  `ValidationError` and a CLI `KeyError`; unified on `rule_id` for the draft/pending
  dicts, `id` stays the YAML rule key.

`arbiter audit-pack <run>` zips the three things an auditor needs — the full
hash-chained `event-log.jsonl`, the `close-memo.html`, and a `manifest.json` with
the terminal hash and the `verify` command — so the whole run travels as one file
and the chain can be recomputed offline.

Prevention: `test_learn.py` (draft safety, judgement categories don't generalise,
pending→merge bumps the version and re-parses, a merged rule classifies the next run),
`test_memo.py` (self-contained document, every exception listed), `test_audit_pack.py`
(the zip's manifest matches `verify`, the log line count matches, the chain head is
genesis) — plus an API test for resolve → pending. Full suite + `ruff` + `mypy` green;
the merge writes to a spec copy in tests, never the repo's.

## 2026-09-02 — M4b: the cockpit (`web/`, docs/05 + docs/20 §2)

Next.js 15 (App Router) + React 19 + Tailwind + TypeScript strict. The design tokens
from docs/05 §3.1 are CSS variables with full light/dark parity (`:root`, `@media
prefers-color-scheme`, `[data-theme]`) and `prefers-reduced-motion` honoured.

Three surfaces on one screen (docs/05 §2):
1. **Scorecard** (left) — auto-tied %, precision, false-match rate, ₹ coverage, the
   exception mix, the agent panel (task-completion, hallucination, escalation recall,
   cost), determinism ✓, throughput.
2. **Exception queue** (centre) — ranked by ₹ impact, keyboard-first
   (`j`/`k` move, `e` drawer, `a` accept, `w` won't-fix), typed category chips
   (colour + label), status pills. Empty state is a celebrated "Everything tied."
3. **Evidence drawer** (right) — the records side by side, the identity equation with
   the residual called out, the agent's proposal/escalation clearly badged, and the
   resolution controls (which POST to `/v1/exceptions/.../resolve`).

`/` lists runs + a "reconcile" form (spec × dataset × `--no-ai`).

**Bug caught:** server-side `fetch` in a React Server Component can't use a relative
URL, and a module-level `const BASE = typeof window ...` was resolving to the client
branch in the Next server bundle. Fixed: `base()` is now a function evaluated per call
(server → `ARBITER_API_URL` / `127.0.0.1:8000`, client → `/api` via the Next rewrite).

`tsc --noEmit`, `next lint`, and `next build` all clean; verified end to end against a
live API (`make up`). CI gains a `web` job (typecheck + lint + build). `make up` runs
both; the Makefile gains `api` / `web` / `up` / `bench` targets.

## 2026-09-02 — M4a: the HTTP API (docs/20 §1)

`packages/api` — a FastAPI wrapping the engine, the cockpit backend + the customer
integration surface. Routes: `/healthz` `/readyz`; `/v1/specs` `/v1/datasets`;
`POST /v1/runs`; `/v1/runs` list + detail + `/scorecard` + `/matches` + `/exceptions`
+ `/verify` + `/replay` + `/stream` (SSE); `/v1/exceptions/{run}/{id}` (the
evidence-drawer payload) + `/resolve` (→ `RESOLUTION_APPLIED`). RFC-9457-ish problem
responses. New events: `RESOLUTION_APPLIED` / `RULE_DRAFTED` / `RULE_MERGED`, folded
onto exceptions (a resolved exception carries its resolution + status).

**Bug caught:** the API needs the store to persist across requests — an in-memory
`sqlite://` engine drops its tables between connections. Fixed in `EventStore`: for
`sqlite://` / `:memory:` it now uses a `StaticPool` (one kept-alive connection per
engine, so separate `EventStore()` instances stay isolated — the determinism tests
still pass).

6 API tests (health, spec/dataset listing, full run lifecycle, evidence drawer +
resolve, 404s). 79 tests total. Live smoke: `arbiter-api` serves and a `POST /v1/runs`
completes end to end. ruff + mypy(strict) clean.

## 2026-09-02 — M3: the investigation agent (ADR-0004)

The skeleton FSM gains an `INVESTIGATING` phase. For each `UNEXPLAINED` / `AMBIGUOUS`
exception (never `SECURITY_REVIEW`), a bounded agent loop runs: `PLAN → INVESTIGATE
(read-only tools) → HYPOTHESIZE & TEST → DECIDE → Proposal | Escalate`.

- `agent/schemas.py` — strict `Proposal` / `Escalate` pydantic contracts; category is a
  fixed enum (the agent cannot invent one).
- `agent/prompts.py` — the frozen, hashed system prompt.
- `agent/fencing.py` — every untrusted record field wrapped in `<untrusted-record-data>`;
  the raw `<`/`>` replaced so an injected tag can't close the fence.
- `agent/tools.py` — 5 read-only tools (`query_evidence`, `counterparty_history`,
  `similar_exceptions`, `candidate_matches`, `decomposition_detail`) + the task-message
  builder. **No tool mutates a match, a record, a ledger entry, or money** (docs/14 C3).
- `agent/client.py` — pluggable `LLMClient`: `AnthropicClient` (real, `claude-opus-5`,
  adaptive thinking), `RecordedClient` (replays `AGENT_INTERACTION` events — so
  `arbiter replay` reproduces a run without the API), `ScriptedClient` (offline tests).
- `agent/investigator.py` — the bounded loop (turn + token budgets; forces the decision
  on the last turn; malformed output → escalation, never a guess).
- `agent/orchestrate.py` — drives the phase, emits `AGENT_INVESTIGATION_STARTED`,
  `AGENT_INTERACTION*`, `AGENT_PROPOSAL_CREATED | AGENT_ESCALATED`; per-run cost ceiling;
  with no `ANTHROPIC_API_KEY` it escalates *deterministically* (no LLM call) so the run
  still completes and stays reproducible.
- `bench` gains the **agent scorecard** (task-completion, category accuracy of proposals,
  escalation precision/recall, hallucination rate, tool calls, cost) and `--ablate`
  (`--no-ai` vs haiku/sonnet/opus). `arbiter explain` prints the evidence + the agent's
  proposal/escalation as text.

`--no-ai` skips the phase entirely. `arbiter replay` and `--rerun` reproduce the exact
terminal hash (verified). 74 tests + 1 skipped live test; a nightly CI job runs the
live suite. ruff + mypy(strict) clean.

## 2026-09-02 — Benchmark correctness fix (the CI `bench` gate)

**Symptom:** the `bench` CI job (which runs on an 800-record batch) would fail its
scorecard gate — on 800 records the reported false-match rate was ~57% and auto-match
~21%, while unit tests, the `lint-type`, `test` and `determinism` jobs all passed.

**Root cause — two test-harness bugs, not engine bugs:**
1. **Anomaly density scaled linearly.** `plan()` used `records // 60` per anomaly type,
   so at 800 records ~13 of every type were injected — a *majority* of settlement
   batches were anomalous, which is nothing like real reconciliation (~1–5%).
2. **The scorecard's "false match" definition was too strict.** It counted *any*
   predicted match on a batch not in `ground_truth.true_matches` as a false match —
   even when the matcher correctly tied the identity within tolerance and an exception
   was opened for the residual. A tied identity with a flagged variance is correct
   behaviour, not a false match.

**Fix:**
1. `plan()` now targets a realistic anomalous-batch fraction (normal ≈ 8%, hard ≈ 18%),
   distributed across types by weight, capped — never a majority.
2. The scorer redefines a **false match** as: the matcher auto-tied a batch whose
   identity does *not* close **and** no exception flagged it. A tie whose identity
   closes is correct; a non-closing tie that an exception caught is "flagged", counted
   as neither correct nor false.

**Result:** honest, stable numbers at every scale — 120 rec: auto-match 94%, precision
94%, false-match 0%; 800 rec: 100% / 100% / 0%. New tests
(`test_scorecard_holds_at_scale`, `test_hard_difficulty_degrades_visibly`) lock this in.
CI now also pins Python 3.12.

**Note on earlier commits:** the M1–M2c commits' `bench` job would have failed this
gate for the reasons above. The engine on those commits was always deterministic and
correct — the *benchmark was mis-measuring it*. Every other CI job (lint, types, unit
tests, determinism) passed on those commits; history was not rewritten.

## 2026-09-02 — M2: Fellegi–Sunter, subset/fuzzy passes, resume, calibration

- **M2a — probabilistic matching** (ADR-0005): `match/fellegi_sunter.py` (agreement
  levels, m/u, weight = Σ log2(m/u), posterior from the block prior, a calibration
  hook, and `from_labeled` frequency estimation); `match/compare.py` (comparison
  vectors + Jaro–Winkler); `match/subset.py` (subset-sum matching — exact
  meet-in-the-middle ≤22, greedy above, returns None on ambiguity). `match/engine.py`
  rewritten to 4 passes: exact · tolerant (FS-weighted) · subset · fuzzy (candidates
  attached, never auto-matched).
- **M2b — resilience + calibration**: `arbiter run --resume` (resumes a crashed run
  from its last committed stage — reproduces the exact terminal hash from every stage
  boundary, tested) and `--rerun`; `arbiter bench --calibration` (reliability diagram,
  Expected Calibration Error, Pool-Adjacent-Violators isotonic recalibration when
  ECE > 0.05).

**M2 calibration finding:** the deterministic matcher is *slightly over-confident* —
16 matches all stated at 1.00 confidence, observed accuracy 0.94, ECE 0.062 → an
isotonic map is fitted and disclosed. Exactly the kind of thing the calibration study
exists to catch.

- **M2c — safe-AST rule engine** (ADR-0003): `exceptions/rules.py` parses a spec's
  `rules:` `when:` expressions with Python's `ast` module against a strict node
  whitelist (no `eval`, no imports, no comprehensions/lambdas, no dunder names, no
  private-attribute access, per-object attribute allow-lists). `exceptions/context.py`
  builds the `RuleContext` (safe helper fns: `abs`, `is_empty`, `injection_signal`,
  `count_records`, `unmatched`, `ts_day`, …). The classifier now consults the spec's
  rules first; a broken rule never crashes a run, it just doesn't fire. The reference
  spec's 7 rules all compile and drive the `_classify_residual` path.

66 tests (rule safety: `__import__`/`open`/`lambda`/comprehension/dunder all rejected;
first-match-wins; broken-rule tolerance; the reference spec's rules compile).
ruff + mypy(strict) clean.

## 2026-09-02 — M1: matching engine, decomposition, classifier, `arbiter bench`

The deterministic skeleton FSM now runs end to end:
`INGESTING → MATCHING → DECOMPOSING → CLASSIFYING → RUN_COMPLETED`.

- **match/** — blocking by `settlement_utr`; pass 1 (exact) + pass 2 (tolerant) with an
  explicit confidence formula (`match/confidence.py`; Fellegi–Sunter m/u + calibration is
  M2 per ADR-0005). Deterministic (sorted iteration, integer paise).
- **decompose/** — the settlement identity `net = Σcredit − Σdebit − Σfee − Σtax` per UTR
  group, with the ledger cross-check; residual drives classification.
- **exceptions/** — the taxonomy, the deterministic injection scanner (untrusted fields →
  `SECURITY_REVIEW`, never sent onward — docs/14 C2), and the M1 classifier covering
  ROUNDING / FEE_DEDUCTION / TIMING / WRONG_ACCOUNT / PARTIAL_PAYMENT / DUPLICATE /
  CHARGEBACK / MISSING_UTR / UNEXPLAINED.
- **bench/** — `arbiter bench` scores a run against `ground_truth.json`: auto-match rate,
  precision, recall, **false-match rate**, ₹ coverage, exception mix, category accuracy,
  throughput, and a live determinism check (a second run must reproduce the hash chain).
- datagen: anomalies now create *real* discrepancies — FEE_DRIFT/GST_ROUND/DUP_EXPORT
  "freeze" the bank at the pre-anomaly amount so the processor file is what's wrong;
  TIMING_STRADDLE actually shifts `settled_at` past the period end.

**Honest M1 baseline** (seed batch, 270 records, difficulty=normal, no AI):
auto-match 88.2% · precision 93.8% · false-match 6.2% · ₹ coverage 100% ·
10/11 anomalies detected · 60% category accuracy · deterministic ✓. This is the number
the agent (M3) is measured against.

**Bugs caught during M1 (Failure Recovery):**

| Symptom | Root cause | Fix | Prevention |
|---|---|---|---|
| 0 matches — every batch became an exception | `extract_utr` regex matched the word "RAZORPAY" as the UTR before the real reference | rewrote it: prefer a token after an explicit `UTR`/`REF` label, then a long alphanumeric token that *contains a digit* (English words never do) | direct `extract_utr` unit cases + the clean-batch test asserts full match |
| GST_ROUND / FEE_DRIFT anomalies invisible | datagen recomputed the bank credit *after* the anomaly, so the identity still closed | `freeze_bank()` snapshots each batch's clean net before the anomaly phase | `test_adversarial_scorecard_is_honest` asserts a sub-perfect but strong baseline |
| CHARGEBACK batch classified WRONG_ACCOUNT | a later TIMING_STRADDLE / WRONG_ACCT injector dropped the same batch the chargeback landed in | chargeback marks its batch `protected`; the drop-batch injectors skip protected batches | — |

## 2026-09-02 — M0: scaffold, event store, ingestion, datagen (code begins)

First code. uv workspace + two packages (`arbiter-engine`, `arbiter-datagen`). Shipped:
money (integer paise), canonical hashing, the hash-chained event store + `verify`,
the recon-spec loader, CSV ingestion (→ `RECORD_INGESTED` events), the clean-batch
synthetic data generator with ground truth, the `arbiter` CLI (`run` / `replay` /
`verify` / `events` / `gen`), 27 tests, ruff + mypy(strict) clean, CI (4 jobs incl. an
isolated determinism gate). `arbiter run` ingests the 270-record seed batch
deterministically; `arbiter replay` reproduces it.

**Bugs caught during M0 (Failure Recovery):**

| Symptom | Root cause | Fix | Prevention |
|---|---|---|---|
| `test_two_runs_produce_identical_hash_chains` failed on the first real run | `RUN_COMPLETED.wallclock_ms` (a wall-clock duration) was in the **hashed** payload → every run's terminal hash differed | moved timing to a non-hashed `Event.meta` sidecar; the hash chain now covers semantic content only (matches docs/12 §4) | the determinism test itself — it earned its keep on day one; it runs as an isolated CI job |
| 120 ledger rows + 2 bank rows quarantined as "unparseable / missing amount" | (a) normalize didn't map the ledger's `order_total` to the amount field; (b) the CSV formula-injection neutralizer was prepending `'` to negative numbers **at ingest** | (a) added `order_total` to the amount resolution chain; (b) `neutralize_for_export` is now export-only, never at ingest (docs/14 C4) | `test_ingests_the_clean_dataset` asserts `rows_quarantined == 0`; identity property test on datagen |
| bank amounts double-scaled | datagen wrote bank credits in paise while the bank source spec expects rupees | datagen writes bank statements in rupees (realistic) | `test_settlement_identity_holds_for_every_batch` |

## 2026-09-02 — Compliance, competitive-field, and completeness pass

- **Git history corrected:** the first 3 commits were mis-attributed (author email
  `rajdeepsinghsakarwar@gmail.com` → GitHub account `Rajdeepsingh49`). Rewrote all commits to
  `krrishverma1805-web <krrishverma1805@gmail.com>` and force-pushed. Local git config +
  a memory now enforce the right identity for all future commits.
- **Competitive landscape ([doc 03 §2.8a](03-competitive-landscape.md)):** added the OSS AI
  reconciliation agents — notably `Manu6259/financial-reconciliation-agent`, which independently
  arrived at the same "LLM proposes, deterministic code disposes" principle. Documented exactly
  where Arbiter goes deeper (adversarial scale, settlement decomposition, the investigation-loop
  agent, calibration, multi-rail, honest sub-100 benchmark).
- **Doc 26 — Compliance & Data Protection:** RBI PA-PG Directions 2025 (card-data minimisation —
  the schema already has no PAN field; data localisation for hosted), DPDP Act 2023/Rules 2025
  (data-fiduciary obligations, `arbiter purge` for the erasure right), PCI-DSS scope (likely out,
  by design), the minimised LLM payload.
- **Doc 12 §6.1a:** replaced the hand-wavy "human-judged equivalent" for `resolution_usefulness`
  with a proper LLM-as-judge protocol (binary reference-based rubric, cited evidence, judge
  ensemble, human-validated to Cohen's κ ≥ 0.6).
- **Doc 27 — Completeness Audit:** the full coverage matrix; the 3 items that are thin only
  because they're empirical (real match rate, real AI lift, heuristic behaviour); everything
  deliberately excluded + why. Verdict: the plan is done — build.
- Code begins now at M0.

## 2026-09-02 — Deep-dive specification pass

- Added 11 build-ready deep-dive docs (15–25) + ADR-0005 (Fellegi–Sunter matching) so nothing
  in the build is left to improvisation:
  - 15 domain model: the settlement identity, the exhaustive exception taxonomy with root
    causes / detection / resolution playbooks / accounting treatment (journal entries).
  - 16 matching engine: blocking, Fellegi–Sunter (m/u seeded from the labeled synthetic data),
    the subset-sum pass (meet-in-the-middle + heuristic), assignment, determinism, perf budget.
  - 17 full physical schema (DDL), every event type + payload, projections, JSON contracts.
  - 18 synthetic data generator: generative model, anomaly-injection catalog, ground truth +
    labeled trajectories, anti-"teaching to the test".
  - 19 agent contracts: the frozen system prompt, per-exception task message, tool JSON
    schemas, strict Proposal/Escalate output schema, few-shots, budgets.
  - 20 API (routes, SSE, errors) + frontend (component tree, state coverage, keyboard, memo).
  - 21 GTM: positioning, ICP, wedge, pricing, unit economics, the field at the Buildathon.
  - 22 cost model (per-exception ~$0.035, per demo run ~$0.65, Buildathon total ~$300).
  - 23 risk register (build/scope/judging) with triggers + contingencies.
  - 24 the 5-minute pitch script + judge walkthrough + anticipated Q&A.
  - 25 testing & CI: property-test invariants, testing the agent cheaply, the pipeline.
- Research folded in: Razorpay `fetch-recon` schema, Fellegi–Sunter math, India settlement
  accounting treatment (SAC 998433, 18% GST on MDR, ITC), FloQast pricing benchmarks.

## 2026-09-02 — Plan evaluation pass

- **Adversarial self-review** of docs 01–10 ([doc 11](11-plan-evaluation-and-gaps.md)). Grade: B+. Found one structural weakness and 14 gaps.
- **Structural fix:** v1 described a pipeline with one LLM call, not an agent. Reframed as **hybrid orchestration** — deterministic skeleton + a real agentic investigation loop (plan → investigate → hypothesize/test → conclude/escalate) — [ADR-0004](adr/0004-hybrid-orchestration.md), [doc 12](12-agent-design.md).
- **New docs:** 11 (evaluation/gaps), 12 (agent design + agent scorecard + calibration), 13 (production readiness), 14 (security & trust), `KNOWN-FAILURE-MODES.md`.
- **Spec updated** to Razorpay's real `fetch-recon` field names (`entity_id`, `settlement_utr`, `debit`/`credit`/`fee`/`tax`, `dispute_id`, …).
- **Still no code broken** — code begins at M0.

## 2026-09-02 — Repository & research phase

- **Set up:** monorepo plan, full `docs/` research and specification set, ADRs, reference recon specs.
- **Nothing broken yet** — code begins at milestone M0.
- **Decision captured:** confined the LLM to a single bounded step ([ADR-0001](adr/0001-deterministic-core-ai-at-the-boundary.md)) after weighing an LLM-first matching approach and rejecting it on reproducibility/auditability grounds.

---

<!--
Template for future entries:

## YYYY-MM-DD — <short title>

**Symptom:** what was observed (test failure, wrong number, crash, judge feedback)
**Root cause:** the actual reason
**Fix:** what was changed
**Prevention:** the test / gate / doc added so it can't silently recur
-->
