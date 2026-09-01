# 13 — Production Readiness

_What it takes for Arbiter to be deployed to a real finance team, not just demoed. Each item below is scoped for the Buildathon build unless marked (post)._

---

## 1. Readiness checklist (summary)

| Area | State target for submission |
|---|---|
| Config & secrets | 12-factor; `.env` + env vars; secrets never logged; `ANTHROPIC_API_KEY` the only required secret |
| Database migrations | Alembic; `arbiter db upgrade`; no implicit schema creation in prod mode |
| Observability | OpenTelemetry traces (spans per pass / exception / tool / LLM call); structured JSON logs with `run_id` correlation; Prometheus-style counters |
| Health | `/healthz` (liveness), `/readyz` (DB + migration check); Docker `HEALTHCHECK`; graceful shutdown draining in-flight runs |
| Resilience | every pass resumable from the event log; idempotent runs; typed retries on the agent loop; poisoned-row quarantine |
| Rate limiting | per-token bucket on the API; per-run LLM cost ceiling |
| Security | see [doc 14](14-security-and-trust.md) |
| Packaging | multi-stage Docker; `docker-compose up` = API + Postgres + web; `make demo` = SQLite, no compose |
| CI/CD | GitHub Actions: lint, type-check, test, `arbiter bench`, build images, publish scorecard artifact + PR comment |
| SLOs | defined (§7) and checked in CI against the demo dataset |
| Runbook | `docs/RUNBOOK.md` — deploy, rollback, resume a stuck run, rotate the key, restore the event store |
| Backup | event store dump/restore (`arbiter export --run all`, `arbiter import`) |

---

## 2. Config & secrets

- All config via environment, surfaced through one `Settings` (Pydantic `BaseSettings`) object. No config reads scattered in modules.
- Required: `ANTHROPIC_API_KEY`. Optional: `ARBITER_DB_URL` (default SQLite), `ARBITER_LOG_LEVEL`, `ARBITER_ENV` (`demo`|`dev`|`prod`), `OTEL_EXPORTER_OTLP_ENDPOINT`.
- **Never logged:** the API key; raw financial row content above a redaction threshold (account numbers, full narrations masked in logs — full fidelity only in the event store, which is access-controlled).
- `ARBITER_ENV=prod` disables auto-create-schema, requires migrations, enables auth stubs, tightens CORS.

---

## 3. Observability

### 3.1 Tracing (OpenTelemetry)

Span tree per run:

```
run  (run_id, spec, dataset_hash)
├── ingest            (rows_in, rows_quarantined, per-source)
├── match.pass1..4     (candidates, matches, low_conf)
├── decompose          (groups, identity_ok, residual_total)
├── classify           (rules_fired, ambiguous, unexplained)
├── investigate
│   ├── exception:<id>  (category_in, category_out, confidence, outcome)
│   │   ├── llm.plan        (model, tokens_in/out, cache_read, latency)
│   │   ├── tool.query_evidence  (args, rows_returned, latency)
│   │   ├── llm.investigate ...
│   │   └── llm.decide      (terminal_state)
│   └── ...
├── score
└── report.memo
```

`arbiter run --trace out.otlp` exports it. Load into Jaeger / Arize Phoenix / any OTLP viewer.

### 3.2 Logs

Structured JSON, one event per line, always carrying `run_id` and (where relevant) `exception_id`. Levels used consistently: `INFO` state transitions, `WARNING` quarantines / escalations / retries, `ERROR` run failures. No `print`.

### 3.3 Metrics

Counters/gauges: `runs_total{status}`, `run_duration_seconds`, `records_processed_total`, `exceptions_opened_total{category}`, `agent_investigations_total{outcome}`, `llm_cost_usd_total`, `llm_tokens_total{dir}`, `agent_escalations_total{reason}`.

---

## 4. Resilience & error handling

| Failure | Behavior |
|---|---|
| Malformed / unparseable row | `ROW_QUARANTINED` event with reason + row ref; run continues; memo + scorecard report the count; quarantined rows never silently dropped |
| Duplicate file re-ingested | rejected at ingest (`ingest_file_hash` seen) with a clear message; `--force` to override |
| LLM 429 / 529 | exponential backoff, capped retries; then escalate the exception with `reason: "provider_unavailable"` |
| LLM refusal (`stop_reason: refusal`) | exception → `ESCALATE`, logged; server-side fallback enabled per current SDK guidance |
| Tool timeout | escalate with partial findings recorded |
| Per-run cost ceiling hit | remaining investigations skipped → `budget` escalations; run still completes with a full scorecard |
| Process crash mid-run | `arbiter run --resume <run-id>` folds the event log to the last committed state and continues |
| Idempotency | `arbiter run` on an already-completed `(spec, dataset_hash)` returns the existing run unless `--rerun` |

Property test: kill the process at each state boundary; `--resume` must produce the same final event hash chain as an uninterrupted run.

---

## 5. Database & migrations

- SQLModel schema; Alembic for versioned migrations. `arbiter db upgrade` / `downgrade`.
- SQLite (demo, default) and Postgres (compose / prod) run the **same** migrations.
- Event table is append-only; migrations only ever add columns/indexes or new projection tables — never alter historical event payloads (schema-versioned payloads instead).
- Projections are rebuildable: `arbiter db rebuild-projections` drops and re-folds. Used after a projection-schema change.

---

## 6. Frontend production concerns

| Concern | Approach |
|---|---|
| Live run progress | Server-Sent Events from `/runs/{id}/stream`: pass-by-pass progress, exception count, then agent investigations streaming plan → conclusion |
| State coverage | every view has explicit loading / empty / error / partial states — not just the happy path |
| Optimistic updates | resolving an exception updates the queue immediately; rolls back with a toast on API failure |
| Data fetching | TanStack Query with proper cache keys, retry, and stale-while-revalidate |
| Errors | error boundaries per surface; a failed scorecard doesn't blank the whole page |
| Responsiveness | works down to a 768px tablet; the queue degrades to a card list on narrow screens |
| Accessibility | WCAG 2.2 AA (per [doc 05 §5](05-design-doctrine.md)) — enforced with `axe` in CI |
| Perf | route-level code splitting; the run view SSR's the scorecard for fast first paint |
| The Close Memo view | print-styled; `arbiter memo` and the UI share the same renderer |

---

## 7. SLOs (checked in CI against the demo dataset)

| SLO | Target |
|---|---|
| Run success rate | ≥ 99% (excludes intentional poisoned-data tests) |
| Deterministic phase p95 latency | < 25s for 800 records |
| Full run (with agent) p95 latency | < 5 min for 800 records / ~15 exceptions |
| LLM cost per run | < $1.50 for the demo batch |
| False-match rate | ≤ 1.5% (hard CI gate) |
| Auto-match rate regression | fail CI if it drops > 2 points vs the committed baseline |

---

## 8. What stays (post) — and why it's OK

| Deferred | Why acceptable for submission | Note in |
|---|---|---|
| Multi-tenant auth / RBAC / SSO | single-tenant, local-first is the demo; the data model reserves an `org_id` column so it's not a rewrite | [doc 04 §11](04-technical-architecture.md) |
| Horizontal scaling / worker queue | event-driven engine already supports it; not needed at demo scale | [doc 04 §11](04-technical-architecture.md) |
| SOC 2 / pen test | needs a company | [doc 08 R8](08-why-it-might-not-sell.md) |
| Live connectors (bank/ERP APIs) | three real file parsers ship instead ([doc 11 G5](11-plan-evaluation-and-gaps.md)); API connectors are the first post-hackathon investment | [doc 06 M1](06-feature-inventory.md) |

The point: the deferrals are **named, reasoned, and architecturally anticipated** — not gaps discovered later.
