# Failure Recovery

> Root-level summary. Depth: [`docs/13-production-readiness.md`](docs/13-production-readiness.md),
> [`docs/KNOWN-FAILURE-MODES.md`](docs/KNOWN-FAILURE-MODES.md), [`docs/RUNBOOK.md`](docs/RUNBOOK.md).

## Design stance: fail closed

Every ambiguous or degraded path ends in **escalate to a human**, never in a
silent auto-resolution. The deterministic core is the floor: `--no-ai` always
produces a complete, scored reconciliation.

## What happens when …

| Failure | Behaviour |
|---|---|
| LLM provider is down / rate-limited | the investigation escalates with reason `provider_unavailable`; the run completes with that exception open. It does not crash or sink the run. |
| Verifier returns unparseable / verdict-less JSON | treated as a rejection → ESCALATE (`verifier_rejected`). Fail-closed. |
| Agent hits its turn / token budget | escalate with reason `budget_exceeded`; partial evidence is attached. |
| A record cited in a proposal doesn't exist | grounding marks it `fabricated` → ESCALATE (`contradictory`). |
| Counterfactual arithmetic contradicts the hypothesis | ESCALATE (`counterfactual_contradicted`). |
| Duplicate event delivered | idempotency key / event dedup — no second state change. |
| Out-of-order events | the fold is order-independent by construction; `verify` still checks the chain. |
| Malformed input row | quarantined at ingest with a reason; the run continues; quarantined count is reported. |
| DB row tampered | `arbiter verify` fails and names the first broken event. |

## Attack Arbiter — `arbiter attack`

A deterministic adversarial harness. Each scenario copies a clean dataset,
applies one known tampering, reconciles with `--no-ai`, and reports:

```
{ scenario, attack_impact, detected?, rupees_unaccounted, unsafe_auto_resolution?,
  what_arbiter_did, verdict }
```

Verdicts: **CONTAINED** (flagged, ₹0 unaccounted) · **PARTIAL** (flagged, some ₹
still adrift) · **MISSED** (no signal, but no false assertion either) ·
**UNSAFE** (the matcher asserted a confident clean tie over a tampered record —
the one outcome that must never happen). `arbiter attack` exits non-zero on any
UNSAFE; `tests/test_attacks.py` is the CI regression gate.

Current: **12 contained · 0 partial · 0 missed · 0 unsafe**, ₹0 unaccounted.

## Recovery procedure for a bad run

1. `arbiter verify <run>` — confirm whether the chain is intact.
2. If intact: the projection is trustworthy; re-open the escalated exceptions in
   the cockpit and resolve them by hand.
3. If broken: the event log was tampered. Discard the projection, restore the
   `events` rows from backup, re-verify.
4. Re-running ingestion produces a **new** run id; the old run is never mutated.
