# Replay & Determinism

> Root-level summary. Depth: [`docs/17-data-model-and-schema.md`](docs/17-data-model-and-schema.md) §3,
> [`ADR-0002`](docs/adr/0002-event-sourced-store.md), [`docs/RUNBOOK.md`](docs/RUNBOOK.md).

## The guarantee

A reconciliation run is a fold over an append-only list of events. Given the same
events, `arbiter replay <run>` reconstructs a byte-identical projection and the
same terminal hash. The deterministic core makes **zero** LLM calls, so a
`--no-ai` run is fully reproducible; an AI run records the model's turns as
`AGENT_INTERACTION` events and replays them from the log without calling the
provider again.

## The hash chain

```
event.hash = SHA256( prev_hash ‖ canonical_json(payload) )
```

`canonical_json` sorts keys and normalises numbers, so the hash is
platform-independent. `arbiter verify <run>` recomputes the whole chain and
reports the first divergent event if any row was edited, inserted, deleted, or
reordered.

## Commands

| Command | What it does |
|---|---|
| `arbiter verify <run>` | recompute the hash chain; report intact / first break |
| `arbiter replay <run>` | re-fold the events; assert the terminal hash matches |
| `arbiter bench ... ` | runs the reconciliation twice and reports `replay_hash_match` |
| API `GET /v1/runs/{id}/verify` · `/replay` | the same, over HTTP |

## Learned state never touches a run's chain

Calibration fits, drafted rules, and pattern memory are written to
`__learn__<org>` pseudo-runs — a separate chain. A reconciliation's hash depends
only on its own inputs and events, so learning from last month's close cannot
retroactively change this month's terminal hash. Cross-run learning is applied at
the *start* of a run (as spec/config inputs, hashed into `RUN_STARTED`), never
mid-fold.

## What determinism costs

- No wall-clock reads inside the fold; timestamps come from the events.
- No set iteration without a sort; every projection list has an explicit key.
- No dict ordering assumptions across Python versions in hashed payloads.
- Float money is forbidden — all amounts are integer minor units.
