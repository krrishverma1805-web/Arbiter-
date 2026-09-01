# ADR-0002 — Event-sourced, append-only store with hash chaining

- **Status:** Accepted
- **Date:** 2026-09-02

## Context

Reconciliation results must be auditable ("who decided what, on what evidence") and reproducible ("prove this number"). The Buildathon bar warns against cherry-picked results. We need a storage model that makes the run's history tamper-evident and the results reconstructable by a third party.

## Decision

All state changes are **immutable events** appended to an `events` table. Each event carries `prev_hash` and `hash = sha256(prev_hash + canonical_json(payload))`, forming a chain per run. Query-side projections (`records`, `matches`, `exceptions`, `decompositions`) are **derived** by folding events and are never written directly by business logic. `arbiter replay <run-id>` drops and rebuilds projections from the event log and asserts the resulting hashes match.

Same schema on SQLite (demo / default) and Postgres (deployment). Events need only `INSERT` + ordered range scans, which SQLite handles well at demo scale.

## Consequences

**Positive:** deterministic replay; tamper-evidence; trivial audit export; debugging by replaying to any `seq`; no hidden mutable state; natural fit for a future queue/worker split.

**Negative:** more ceremony than CRUD; projections must be kept in sync with event schema (mitigated: projections are code, rebuilt on demand, versioned with the engine); storage grows with history (acceptable — finance data is small and history is the point).

## Alternatives considered

- **Plain CRUD tables + an audit-log side table:** rejected — the audit log becomes a second source of truth that can disagree with the primary; replay is not guaranteed.
- **Full CQRS with a message bus:** rejected — over-engineered for demo scale; the fold-on-read model gives the same guarantees with far less infrastructure.
