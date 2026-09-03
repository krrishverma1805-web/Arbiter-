# Threat Model

> Root-level summary. Depth: [`docs/14-security-and-trust.md`](docs/14-security-and-trust.md),
> [`docs/23-risk-register.md`](docs/23-risk-register.md),
> [`docs/KNOWN-FAILURE-MODES.md`](docs/KNOWN-FAILURE-MODES.md).

## Assets

1. The **reconciliation verdict** — "this money is right / these ₹ still need you".
   Corrupting it silently is the worst outcome.
2. The **audit trail** — the append-only event chain. It must be tamper-evident.
3. **Tenant data** — settlement, bank and ledger files, per org.
4. **LLM credentials** — env or per-request.

## Actors

| Actor | Capability | Mitigation |
|---|---|---|
| Malicious data supplier | controls the contents of the three input files | deterministic decomposition + matching; the Attack Arbiter suite; ingest quarantine; injection scanner |
| Compromised LLM / prompt-injection payload in a record | can return any text as a "proposal" | proposal-only tool surface; grounding check; deterministic Safety Kernel; counterfactual verification; injection scanner routes the row to a human first |
| Curious / hostile tenant | a valid principal in org A | every row and cache key is org-scoped; learned state keyed `__learn__<org>` |
| Network attacker | sees API traffic | bearer auth; TLS assumed at the edge; idempotency keys stop replay from creating duplicate events |
| Insider with DB write | can edit `events` rows | hash chain — `arbiter verify` detects any edit, insert, delete, or reorder |

## Abuse cases the build explicitly defends (Attack Arbiter — `arbiter attack`)

duplicate settlement row · altered settlement amount · wrong currency ·
fabricated settlement UTR · dropped bank credit · duplicate refund ·
prompt injection in a settlement note · injection in a bank narration ·
₹10,00,000 phantom credit · negative gross · blanked amount ·
timestamp shifted 74 years.

Current result: **12 contained · 0 missed · 0 unsafe · ₹0 unaccounted.**
The invariant checked: the matcher never asserts a confident clean tie over a
tampered record, and every rupee stays either matched or flagged.

## Known residual risk

- The second-model verifier is still an LLM; the counterfactual check is the
  deterministic backstop but does not cover every hypothesis category.
- No defense against a supplier who tampers *consistently across all three files*
  in a way that still balances — that is indistinguishable from correct data
  without an external source of truth (a stated v1 limitation).
- Auth is a static principal table; no key rotation.
