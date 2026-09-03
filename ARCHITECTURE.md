# Architecture

> Root-level summary. The full treatment is [`docs/04-technical-architecture.md`](docs/04-technical-architecture.md);
> the decisions behind it are the ADRs in [`docs/adr/`](docs/adr/).

## The shape

```
CLIENTS   arbiter CLI (Typer) · cockpit (Next.js 15 / React 19) · CI · MCP stdio
                                   │ REST/JSON + SSE + WS
API       FastAPI — packages/api/arbiter_api      (auth, rate-limit, idempotency, audit)
                                   │
ENGINE    packages/engine/arbiter_engine
          ingest → normalize → decompose → match → classify → [agent] → safety kernel → events
                                   │
STORE     append-only hash-chained `events` table (SQLite / Postgres) — the only source of truth
```

Deterministic FSM skeleton + **one** bounded agentic investigation loop
([ADR-0004](docs/adr/0004-hybrid-orchestration.md)). Turn the loop off with
`--no-ai` and the deterministic core still produces a full, scored reconciliation.

## Non-negotiables

| Principle | Where it lives | ADR |
|---|---|---|
| Money math / matching / decomposition make **zero** LLM calls | `engine/money.py`, `match/`, `decompose/` | [0001](docs/adr/0001-deterministic-core-ai-at-the-boundary.md) |
| Every state change is an event; nothing is mutated in place | `events/store.py`, `events/fold.py` | [0002](docs/adr/0002-event-sourced-store.md) |
| The recon spec is data, not code | `specs/*.yaml`, `specs/model.py` | [0003](docs/adr/0003-recon-spec-as-data.md) |
| Probabilistic matching is explainable (Fellegi–Sunter, per-field weights) | `match/fs.py` | [0005](docs/adr/0005-fellegi-sunter-matching.md) |
| The agent only *proposes*; a deterministic kernel decides SAFE/PROPOSE/ESCALATE/QUARANTINE | `safety/kernel.py` | see [AI_SAFETY.md](AI_SAFETY.md) |

## The event store

`events` is append-only and hash-chained: each row carries `prev_hash` and
`hash = H(prev_hash ‖ canonical(payload))`. `arbiter verify <run>` recomputes the
chain; `arbiter replay <run>` re-folds the events into a projection and checks the
terminal hash is bit-identical. Cross-run learned state (calibration, drafted
rules, pattern memory) is written to `__learn__<org>` pseudo-runs so it never
enters a reconciliation's hash chain. Full detail: [REPLAY.md](REPLAY.md).

## Packages

- `packages/engine` — the reconciliation engine and the agent. No web, no API deps.
- `packages/datagen` — synthetic dataset generator with labeled ground truth.
- `packages/api` — FastAPI service over the engine.
- `web/` — the cockpit (Next.js). Talks only to the API; has a frozen-snapshot demo mode.
