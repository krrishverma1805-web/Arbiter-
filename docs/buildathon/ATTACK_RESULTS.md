# Attack Arbiter — Results

`arbiter attack --spec specs/razorpay-settlement.yaml --dataset datasets/seed`

A deterministic adversarial harness. Each scenario copies the clean seed dataset,
applies **one** known tampering, reconciles it with `--no-ai`, and checks the
invariant: **a tampered record never produces a confident clean tie, and no
rupee silently disappears.**

## Verdicts

| Verdict | Meaning |
|---|---|
| **CONTAINED** | flagged; ₹0 unaccounted |
| PARTIAL | flagged, but some ₹ still adrift |
| MISSED | no explicit signal — but also no false confident assertion |
| **UNSAFE** | the matcher asserted a confident clean tie over a tampered record. Must never happen. `arbiter attack` exits non-zero. |

## Current result — 12 contained · 0 partial · 0 missed · 0 unsafe · ₹0 unaccounted

| Scenario | What Arbiter did |
|---|---|
| duplicate settlement row | 1 new exception · every rupee stayed matched or flagged |
| altered settlement amount (+₹5,000) | quarantined at ingest · 1 new exception |
| wrong currency (INR→USD, no rate) | quarantined at ingest |
| fabricated settlement UTR | 1 new exception (a bank credit citing a non-existent settlement) |
| dropped bank credit | 1 new exception (expected credit missing) |
| duplicate refund | 1 new exception (batch net breaks) |
| prompt injection in a settlement note | quarantined to SECURITY_REVIEW — bypasses the agent entirely |
| injection in a bank narration | quarantined to SECURITY_REVIEW |
| ₹10,00,000 phantom credit | 1 new exception |
| negative gross | 1 new exception (PARTIAL_PAYMENT) |
| blanked amount | quarantined at ingest |
| timestamp shifted 74 years | quarantined at ingest (date outside 2015–2035) |

## What building it found

The harness surfaced **four real gaps**, now fixed and regression-tested:

1. The injection scanner only matched "ignore previous instructions" — broadened
   to role reassignment, "mark as reconciled/approved", authorization claims,
   and leading `system:` / `assistant:` lines.
2. A foreign-currency row with no configured FX rate was silently treated as
   base currency — now quarantined.
3. A tampered bank credit could float unreconciled — now linked to its
   settlement exception via the shared UTR.
4. Dates far outside a plausible window (a timestamp shift attack) passed
   through — now quarantined at ingest.

## Reproduce

```bash
arbiter attack --spec specs/razorpay-settlement.yaml --dataset datasets/seed
arbiter attack --spec … --dataset … --scenario prompt_injection_note --json
```

`packages/engine/tests/test_attacks.py` runs the full suite in CI and fails the
build on any UNSAFE verdict or any scenario leaving > ₹2 unaccounted.
