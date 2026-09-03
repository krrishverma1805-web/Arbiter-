# Security

> Root-level summary. Depth: [`docs/14-security-and-trust.md`](docs/14-security-and-trust.md),
> [`docs/26-compliance-and-data-protection.md`](docs/26-compliance-and-data-protection.md).
> Attacker model and abuse cases: [THREAT_MODEL.md](THREAT_MODEL.md).

## Controls

| Area | Control |
|---|---|
| API auth | bearer token → principal with an org id and a role; every write is authorised and audited (`arbiter_api/auth.py`, `audit`) |
| Multi-tenancy | every row is org-scoped; learned state is keyed `__learn__<org>`; no cross-org read path |
| Rate limiting + idempotency | per-principal limits; `Idempotency-Key` on every write; replays return the cached response, never a second event |
| Audit trail | append-only hash chain; `arbiter verify` detects any tamper or reordering; writes and 401/403s are logged with principal, method, path, status |
| PII | card numbers are Luhn-detected and masked at ingest (`ingest/normalize.py`); free-text fields are marked untrusted and scrubbed |
| Prompt injection | deterministic scanner (`exceptions/injection.py`) quarantines matching rows to SECURITY_REVIEW before the agent runs |
| Secrets | LLM keys come from env or per-request headers (`X-LLM-Key`); never logged, never written to an event, never persisted |
| Foreign currency | a row in a currency with no configured FX rate is quarantined, never silently treated as base currency |
| Data quality | blank amounts, unparseable dates, dates outside 2015–2035, negative gross where impossible → quarantined at ingest |

## Reporting

This is a Buildathon submission, not a deployed service. There is no bug-bounty
program. For the record: report a vulnerability by opening a GitHub issue marked
`security` on `krrishverma1805-web/Arbiter-`.

## What is deliberately out of scope for v1

- Live payment-processor webhook ingestion (batch-file ingestion only).
- At-rest encryption beyond what the database provides.
- SSO / SCIM. Auth is bearer-token with a static principal table.
