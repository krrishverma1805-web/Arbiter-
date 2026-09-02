# Runbook

Operational procedures for a running Arbiter deployment. Scoped to what the
Buildathon build actually ships — where a step is a v1 boundary, it says so.

See also: [`13-production-readiness.md`](13-production-readiness.md) (the target
state), [`14-security-and-trust.md`](14-security-and-trust.md) (threat model),
[`BUILD-LOG.md`](BUILD-LOG.md) (build-time failures), [`KNOWN-FAILURE-MODES.md`](KNOWN-FAILURE-MODES.md)
(agent failures on the task).

---

## Configuration

All config is environment variables. Nothing is read from a file except the
recon spec (passed explicitly) and the dataset CSVs.

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | The investigation agent. **Absent → runs still complete**: ambiguous exceptions escalate deterministically and the run stays reproducible. |
| `ARBITER_DB_URL` | `sqlite:///./data/arbiter.db` (API) / in-memory (CLI unless `--db`) | The event store. Any SQLAlchemy URL. |
| `ARBITER_SPECS_DIR` | `specs` | Where the API looks up specs by name. |
| `ARBITER_DATASETS_DIR` | `datasets` | Where the API resolves relative dataset paths. |
| `ARBITER_ENV` | `dev` | `dev` / `demo` / `prod`. |
| `ARBITER_API_URL` | `http://127.0.0.1:8000` | The cockpit's server-side base URL (client-side uses the `/api` rewrite). |

The API key is never logged. It is read only by `AnthropicClient` in
`packages/engine/arbiter_engine/agent/client.py`.

---

## Deploy

```bash
uv sync --all-packages
cd web && pnpm install && pnpm build && cd ..
make up          # API on :8000, cockpit on :3000
```

`make demo` is the zero-dependency path: SQLite, no web, generates a batch,
reconciles it, prints the scorecard and the audit hash.

Before any deploy, the gate is green CI: `lint-type`, `test`, `determinism`,
`bench`, `web`. The `bench` job fails the build if false-match rate > 1.5% or
auto-match rate < 80% on an 800-record adversarial batch.

---

## Rollback

The engine is stateless; the event store is append-only. To roll back a bad
release, redeploy the previous image/commit — no data migration to reverse
because **schema is create-only and additive** (new `EventType` values are
ignored by an older fold, not fatal).

A learned rule that was merged in error is rolled back in git: the merge is a
plain edit to the spec YAML (`# learned <id>` block + a `version:` bump). Revert
that commit and the rule is gone; the `RULE_MERGED` event stays in the log as
the record that it happened.

---

## Resume a stuck or crashed run

Every phase folds from the event log, so a run that died mid-flight resumes from
its last committed event:

```bash
uv run arbiter run --spec <spec> --dataset <dir> --db <url> --resume
```

`--resume` continues from the last phase that emitted an event. `--rerun`
discards a completed run and starts over (same inputs → same terminal hash).

If a run is wedged (e.g. the agent loop is retrying a transient API error past
its budget): it will hit `turn_budget` / `per_run_cost_ceiling_usd` and escalate
the remaining exceptions rather than hang. There is no unbounded wait.

---

## Verify an audit trail

```bash
uv run arbiter verify <run-id> --db <url>     # recompute the hash chain
uv run arbiter replay <run-id> --db <url>     # re-fold every projection, compare terminal hash
```

`verify` walking the chain and `replay` reproducing the terminal hash are the
two independent checks that the log has not been tampered with. The Close Memo
(`arbiter memo`) embeds the terminal hash and the `verify` command so an auditor
can confirm the memo against the log.

If `verify` reports a break: the event at the named sequence number has been
altered or deleted. The event store is the system of record — restore it from
backup (below) and re-run `verify`.

---

## Rotate the API key

1. Issue a new `ANTHROPIC_API_KEY`.
2. Update the environment / secret store.
3. Restart the API (`make up` or the container).
4. No run state depends on the key — in-flight runs that were mid-investigation
   will resume against the new key on `--resume`.

The old key appears in no log, no event, and no projection, so nothing needs
scrubbing.

---

## Back up / restore the event store

The event store is one SQLite file (or one Postgres database). It is the only
durable state — projections and scorecards are always recomputed.

```bash
# SQLite
cp data/arbiter.db data/arbiter.db.$(date +%F)

# any backend — dump the raw log for one run
uv run arbiter events <run-id> --db <url> > run-<run-id>.jsonl
```

Restore = put the file back / reload the database, then `arbiter verify <run-id>`
on a known run to confirm the chain is intact.

---

## v1 boundaries (documented, not yet built)

- No Alembic migrations (`arbiter db upgrade`) — schema is create-only.
- No OpenTelemetry export (`--trace`) — the event log is the trace substrate.
- No `/metrics` endpoint, no rate limiter on the API.
- No auth / multi-tenancy — see [`docs/02 §6`](02-product-spec.md).

Each is scoped in [`13-production-readiness.md`](13-production-readiness.md).
