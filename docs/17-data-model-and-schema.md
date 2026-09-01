# 17 — Data Model & Schema

_Full physical schema. SQLite (demo) and Postgres (deploy) run identical DDL via Alembic. Events are the source of truth; everything else is a projection._

---

## 1. Schema overview

```
   ┌──────────────┐        ┌───────────────┐
   │  spec_versions│        │     runs      │
   └──────┬───────┘        └───────┬───────┘
          │ 1:N                    │ 1:N
          ▼                        ▼
   (referenced by runs)     ┌─────────────┐        append-only, hash-chained
                            │   events    │◀──────  THE SOURCE OF TRUTH
                            └──────┬──────┘
                                   │  fold()
             ┌─────────────┬───────┼────────┬──────────────┐
             ▼             ▼       ▼        ▼              ▼
        ┌─────────┐  ┌─────────┐ ┌──────┐ ┌────────────┐ ┌───────────┐
        │ records │  │ matches │ │decomp│ │ exceptions │ │ scorecards│    ← PROJECTIONS
        └─────────┘  └─────────┘ └──────┘ └────────────┘ └───────────┘      (rebuildable)
```

**Rule:** business logic only ever writes to `events`. A projection is `DELETE FROM projection WHERE run_id=? ; replay events`. `arbiter db rebuild-projections` does this globally after a projection-schema migration.

---

## 2. `events` — append-only, hash-chained

```sql
CREATE TABLE events (
  id            INTEGER PRIMARY KEY,          -- global monotonic
  run_id        TEXT    NOT NULL,
  seq           INTEGER NOT NULL,             -- per-run 0..N
  ts            TEXT    NOT NULL,             -- ISO8601, informational only (never used in logic)
  type          TEXT    NOT NULL,
  payload       TEXT    NOT NULL,             -- canonical JSON (sorted keys, no whitespace)
  payload_schema INTEGER NOT NULL DEFAULT 1,  -- payload schema version for this type
  actor         TEXT    NOT NULL,             -- 'engine' | 'agent:<model>@<prompt_hash>' | 'human:<id>'
  prev_hash     TEXT    NOT NULL,             -- sha256 of previous event's hash ('' for seq 0)
  hash          TEXT    NOT NULL,             -- sha256(prev_hash || canonical(payload) || type || actor)
  UNIQUE(run_id, seq)
);
CREATE INDEX ix_events_run ON events(run_id, seq);
CREATE INDEX ix_events_type ON events(run_id, type);
```

### 2.1 Event types & payloads

| `type` | payload (v1) |
|---|---|
| `RUN_STARTED` | `{spec_name, spec_version, spec_hash, dataset_hash, seed, config_hash, no_ai: bool}` |
| `SOURCE_INGESTED` | `{source, format, profile, rows_in, rows_ok, rows_quarantined, file_hash}` |
| `ROW_QUARANTINED` | `{source, source_row_id, reason, raw}` |
| `RECORD_INGESTED` | full `Record` (§3) |
| `BLOCK_BUILT` | `{block_key, kind, record_ids[]}` |
| `MATCH_PROPOSED` | `{match_id, pass, left[], right[], weight, per_field_weights, confidence_raw}` |
| `MATCH_CONFIRMED` | `{match_id, left[], right[], pass, confidence, rule_id, status}` |
| `MATCH_REJECTED` | `{match_id, reason}` (lost to a higher-confidence conflicting match) |
| `DECOMPOSITION_COMPUTED` | `{group_id, settlement_utr, identity_lhs, identity_rhs, residual_minor, ledger_crosscheck_ok}` |
| `EXCEPTION_OPENED` | `{exception_id, record_ids[], amount_impact_minor, candidates[]}` |
| `EXCEPTION_CLASSIFIED` | `{exception_id, category, classified_by, confidence}` |
| `AGENT_INVESTIGATION_STARTED` | `{exception_id, goal, planned_evidence[]}` |
| `AGENT_INTERACTION` | `{exception_id, turn, model, prompt_hash, request, response, tokens_in, tokens_out, cache_read, latency_ms, tool_calls[]}` |
| `AGENT_PROPOSAL_CREATED` | full `Proposal` (§6) |
| `AGENT_ESCALATED` | `{exception_id, what_i_know, what_is_missing, question, reason}` |
| `RESOLUTION_APPLIED` | `{exception_id, action, detail, actor, prior_status}` |
| `RULE_DRAFTED` | `{rule_id, when, classify, resolve, provenance_exception_id}` |
| `RULE_MERGED` | `{rule_id, spec_version_before, spec_version_after, approved_by}` |
| `SCORECARD_COMPUTED` | full scorecard JSON ([doc 07 §4](07-evaluation-and-benchmark.md), [doc 12 §6](12-agent-design.md)) |
| `MEMO_GENERATED` | `{memo_hash, terminal_event_hash, format}` |
| `RUN_COMPLETED` | `{status, counts, wallclock_ms, wallclock_with_ai_ms}` |
| `RUN_PURGED` | `{reason, by}` (meta-event; the only event that may follow deletion) |

Payloads are Pydantic models under `events/payloads/`, versioned; a bump adds `payload_schema` handling in the fold, never rewrites history.

---

## 3. `records` (projection)

```sql
CREATE TABLE records (
  id             TEXT PRIMARY KEY,      -- sha256(source, source_row_id, run_id)[:16]
  run_id         TEXT NOT NULL,
  source         TEXT NOT NULL,         -- 'razorpay_recon' | 'bank' | 'ledger'
  kind           TEXT NOT NULL,         -- 'payment'|'refund'|'adjustment'|'chargeback'|'credit'|'order'
  amount_minor   INTEGER NOT NULL,      -- paise, signed (credit +, debit −)
  fee_minor      INTEGER NOT NULL DEFAULT 0,
  tax_minor      INTEGER NOT NULL DEFAULT 0,
  currency       TEXT NOT NULL DEFAULT 'INR',
  value_date     TEXT,                  -- ISO date
  posted_date    TEXT,
  settled_at     TEXT,
  counterparty   TEXT,
  reference      TEXT,                  -- normalized ref string used in matching
  external_ids   TEXT NOT NULL,         -- JSON: {settlement_utr, settlement_id, payment_id, order_id, utr, dispute_id, ...}
  untrusted      TEXT NOT NULL DEFAULT '{}',  -- JSON: {description, notes, narration} — NEVER used in logic, only shown fenced
  raw            TEXT NOT NULL,         -- original row verbatim
  ingest_file_hash TEXT NOT NULL,
  org_id         TEXT NOT NULL DEFAULT 'local'   -- reserved for multi-tenant
);
CREATE INDEX ix_records_run_source ON records(run_id, source);
CREATE INDEX ix_records_extids ON records(run_id, reference);
```

`untrusted` is stored separately from `raw` and from the matching fields precisely so the code path that builds an LLM prompt can grab it and fence it ([doc 14 C1](14-security-and-trust.md)) while the matching code never touches it.

---

## 4. `matches` (projection)

```sql
CREATE TABLE matches (
  id             TEXT PRIMARY KEY,
  run_id         TEXT NOT NULL,
  left_ids       TEXT NOT NULL,         -- JSON array
  right_ids      TEXT NOT NULL,
  group_ids      TEXT NOT NULL,         -- ledger side (JSON array)
  pass           TEXT NOT NULL,         -- 'exact'|'tolerant'|'subset'|'subset_heuristic'|'transitive'
  weight_bits    REAL,                  -- FS match weight
  per_field_weights TEXT,               -- JSON {amount: +6.2, date: -1.1, ...}
  confidence     REAL NOT NULL,         -- CALIBRATED P(match)
  rule_id        TEXT,
  residual_minor INTEGER NOT NULL DEFAULT 0,
  status         TEXT NOT NULL          -- 'auto'|'low_confidence'|'human_confirmed'
);
CREATE INDEX ix_matches_run ON matches(run_id, status);
```

---

## 5. `decompositions` & `exceptions` (projections)

```sql
CREATE TABLE decompositions (
  group_id       TEXT PRIMARY KEY,
  run_id         TEXT NOT NULL,
  settlement_utr TEXT,
  identity_expected_minor INTEGER NOT NULL,
  identity_actual_minor   INTEGER NOT NULL,
  residual_minor          INTEGER NOT NULL,
  ledger_crosscheck_ok    INTEGER NOT NULL,   -- 0/1
  components     TEXT NOT NULL               -- JSON: {gross, mdr, gst, refunds, chargebacks, adjustments, rounding}
);

CREATE TABLE exceptions (
  id              TEXT PRIMARY KEY,
  run_id          TEXT NOT NULL,
  record_ids      TEXT NOT NULL,             -- JSON array
  category        TEXT,                      -- from spec taxonomy; NULL until classified
  classified_by   TEXT NOT NULL DEFAULT 'unclassified',  -- 'rule:<id>'|'agent'|'unclassified'
  amount_impact_minor INTEGER NOT NULL,      -- signed ₹ at stake — ranking key
  confidence      REAL,                      -- confidence in the classification/hypothesis
  candidates      TEXT NOT NULL DEFAULT '[]',-- JSON: [{hypothesis, score, per_field_weights}]
  agent_proposal  TEXT,                      -- JSON Proposal (§6) or NULL
  agent_trajectory_id TEXT,                  -- links to AGENT_INTERACTION events
  resolution      TEXT,                      -- JSON Resolution or NULL
  status          TEXT NOT NULL DEFAULT 'open'
                  -- 'open'|'proposed'|'escalated'|'resolved'|'wont_fix'|'budget_exceeded'|'security_review'
);
CREATE INDEX ix_exc_run_status ON exceptions(run_id, status);
CREATE INDEX ix_exc_rank ON exceptions(run_id, amount_impact_minor);
```

---

## 6. Embedded JSON contracts

### `Proposal` (agent output, `AGENT_PROPOSAL_CREATED`)
```json
{
  "exception_id": "exc_0a1b",
  "category": "TIMING",                       // enum: spec taxonomy — strict
  "confidence": 0.86,                          // calibrated
  "explanation": "Bank credit ₹8,240 on 2 Sep has no settlement in the August processor report. A settlement batch setl_9f2 for ₹8,240 net appears in the 31 Aug processor data with settled_at 2026-09-02T05:14Z (T+2). The amounts and the 3 order ids match.",
  "evidence_refs": [
    {"claim": "no settlement in August report", "record_id": "bank_41", "field": "settlement_utr"},
    {"claim": "setl_9f2 settled_at is 2 Sep", "record_id": "rp_318", "field": "settled_at"}
  ],
  "suggested_action": {"action": "carry_forward", "detail": "Reconciling item; clears in the September run."},
  "draft_rule": {
    "when": "unmatched('bank') and ts_day(record.value_date) <= 3 and exists_match_in_prior_period(record)",
    "classify": "TIMING", "resolve": "carry_forward"
  }
}
```

### `Escalate` (agent output, `AGENT_ESCALATED`)
```json
{
  "exception_id": "exc_3c4d",
  "what_i_know": "Orphan bank credit ₹5,000 on 14 Aug, UTR present but no matching settlement_utr. No processor batch nets to ₹5,000 within ±₹50. No counterparty in the narration.",
  "what_is_missing": "Whether a second bank account or a second processor feeds this account.",
  "question": "Is there another payment processor or bank account not included in this reconciliation?",
  "reason": "evidence_exhausted"                // 'evidence_exhausted'|'contradictory'|'budget'|'provider_unavailable'
}
```

### `Resolution` (`RESOLUTION_APPLIED`)
```json
{ "action": "carry_forward", "detail": "...", "actor": "human:krrish", "source": "accepted_proposal", "at": "2026-09-02T11:00:00Z" }
```

---

## 7. `runs` & `spec_versions`

```sql
CREATE TABLE runs (
  id          TEXT PRIMARY KEY,
  spec_name   TEXT NOT NULL,
  spec_version INTEGER NOT NULL,
  spec_hash   TEXT NOT NULL,
  dataset_hash TEXT NOT NULL,
  seed        INTEGER,
  no_ai       INTEGER NOT NULL DEFAULT 0,
  status      TEXT NOT NULL,              -- 'running'|'completed'|'failed'|'purged'
  started_at  TEXT NOT NULL,
  completed_at TEXT,
  org_id      TEXT NOT NULL DEFAULT 'local'
);

CREATE TABLE spec_versions (
  spec_name   TEXT NOT NULL,
  version     INTEGER NOT NULL,
  yaml        TEXT NOT NULL,              -- the full spec at this version
  hash        TEXT NOT NULL,
  mu_table    TEXT,                       -- estimated m/u probabilities (doc 16 §5.2) frozen for reproducibility
  created_at  TEXT NOT NULL,
  parent_version INTEGER,                 -- the version this was derived from (learning loop)
  PRIMARY KEY (spec_name, version)
);
```

Idempotency: `arbiter run` computes `(spec_hash, dataset_hash, config_hash, no_ai)` — an identical tuple returns the existing completed run unless `--rerun`.

---

## 8. Migrations discipline

- Alembic; every migration has an `upgrade` and a real `downgrade`.
- Migrations may: add tables, add nullable columns, add indexes, add new projection tables.
- Migrations may **not**: alter or delete rows in `events`, change an existing event payload's meaning (bump `payload_schema` and handle both in the fold instead).
- After any projection-table migration, CI runs `arbiter db rebuild-projections` on the seed data and asserts the scorecard is unchanged.

---

## 9. Retention & privacy

- The event store is the customer's system of record; they own its lifecycle.
- `arbiter purge --run <id>`: hard-deletes `events` + projections for the run, writes one `RUN_PURGED` meta-event to a separate `purge_log` table (so the deletion itself is auditable).
- Logs/traces never contain full `raw` or `untrusted` content ([doc 14 C5](14-security-and-trust.md)).
