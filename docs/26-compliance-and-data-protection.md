# 26 — Compliance & Data Protection

_Arbiter handles settlement data, bank statements, and counterparty information for Indian businesses. That puts it inside two regulatory perimeters — RBI's payment ecosystem rules and India's data-protection law — plus card-data security standards. This document scopes what applies, what Arbiter does about it, and what is explicitly deferred._

> **Scope note:** Arbiter is **not** a payment aggregator, does not touch the money flow, and does not store card numbers. Most of the heaviest obligations (escrow, RBI authorisation, PCI-DSS as an acquirer) do **not** apply. What applies is the *data-handling* subset — and that Arbiter takes seriously because a finance-data tool that leaks is dead.

---

## 1. RBI Payment Aggregator / Payment Gateway Directions (2025)

Sources: [Trilegal](https://trilegal.com/knowledge_repository/rbis-guidelines-on-regulation-of-payment-aggregators-and-payment-gateways/), [AuthBridge](https://authbridge.com/blog/rbi-payment-aggregator-master-direction-2025/), [PhonePe for Business](https://business.phonepe.com/articles/rbi-approved-payment-gateway-compliance-rules-every-merchant-must-know).

| RBI requirement | Applies to Arbiter? | What Arbiter does |
|---|---|---|
| PA authorisation, net-worth, escrow account, T+1 settlement | **No** — Arbiter never holds or moves merchant funds; it reconciles records after the fact | n/a; documented so a reviewer sees we know the boundary |
| **Card data storage** — only issuer/network may store PAN; others may keep at most **last 4 digits + issuer name** for reconciliation/tracking | **Yes, as a constraint** | The canonical `Record` model has **no PAN field**. Only `card_network`, `card_type`, `card_issuer` (bank code), and (if present in the source) last-4. The parser **drops** any full card number it encounters and logs a `PII_DROPPED` event |
| PCI-DSS 4.0.1 by 2026 (MFA for payment-env access, DB-level encryption of personal data, disk-level no longer sufficient) | **Partially** — Arbiter is not in a cardholder-data environment, but the spirit (DB-level encryption, access control) is adopted for the hosted product | Hosted: Postgres column-level encryption for `records.untrusted` + `records.raw` + counterparty fields; app-level auth with MFA on the roadmap ([doc 13 §8](13-production-readiness.md)). Self-host/demo: the operator's responsibility, documented in the runbook |
| Merchant onboarding due diligence / KYC | **No** | Arbiter's user is the merchant's own finance team; no onboarding of third parties |
| Data localisation — payment data stored in India | **Yes, for the hosted product** | Hosted deployment pins Postgres + object storage to an India region; the LLM call is the only cross-border flow and carries only the minimised, fenced evidence bundle (§3), disclosed in the DPA |

**Net:** Arbiter sits *outside* the PA-PG authorisation perimeter but *inside* the card-data-minimisation and (for hosted) data-localisation expectations. The architecture already reflects this — no PAN storage, minimised LLM payloads, India-region hosting.

---

## 2. Digital Personal Data Protection Act, 2023 (+ DPDP Rules 2025)

Sources: [Seclore compliance guide](https://www.seclore.com/fundamentals/dpdp-rules-2025-compliance-guide/), [Levo DPDP handbook](https://www.levo.ai/resources/blogs/the-dpdp-india-2026-handbook---the-complete-guide-to-indias-new-data-protection-era), [dpdpa.com §8](https://www.dpdpa.com/dpdpa2023/chapter-2/section8.html), [myITmanager: DPDP for SaaS](https://myitmanager.in/dpdp-act-saas-companies-india/).

Arbiter processes **personal data** wherever a counterparty is an individual (a customer name on an order, a payer name in a bank narration). Under DPDP that makes the deployment a **Data Fiduciary** (or Data Processor, when hosted on behalf of a customer). Full operational compliance is phased through 2026–2027; penalties reach ₹250 Cr for a security failure causing a breach.

| DPDP obligation | Arbiter's position |
|---|---|
| **Lawful basis / purpose limitation** | Data is processed for one stated purpose — reconciliation of the customer's own financial records. No secondary use, no profiling, no sale. Stated in the privacy notice and the DPA |
| **Data minimisation** | The event store keeps the source rows the customer already has; the *LLM* receives only the minimised evidence bundle (§3). `--no-ai` processes everything locally with zero external transfer |
| **Notice & consent** | For the hosted product: a privacy notice + a Data Processing Agreement where Arbiter is the processor and the customer (the merchant) is the fiduciary; the merchant carries the consent relationship with its own customers |
| **Security safeguards** | Encryption at rest (§1), hash-chained tamper-evident log ([doc 14 C6](14-security-and-trust.md)), access control, secret hygiene ([doc 14 C5](14-security-and-trust.md)), redaction in logs/traces |
| **Breach notification** | Runbook includes a breach-response procedure; the immutable event log makes scope-of-impact assessment precise |
| **Grievance Officer / DPO** | Named contact for the hosted product (post-hackathon; a company obligation) |
| **Data principal rights** (access, correction, erasure) | `arbiter purge --run <id>` hard-deletes a run + projections with an auditable `RUN_PURGED` meta-event ([doc 17 §9](17-data-model-and-schema.md)); correction is re-ingest + re-run |
| **Cross-border transfer** | Only the fenced evidence bundle leaves India, only to the Anthropic API, only when AI is enabled; disclosed; the customer can run `--no-ai` for zero transfer |
| **Retention** | The customer controls lifecycle; Arbiter sets no default retention beyond the run's usefulness; documented |

**Deferred (company obligations, not architecture):** registering as a Significant Data Fiduciary if thresholds are met, appointing a DPO, a formal DPIA, consent-manager integration. Named in [doc 13 §8](13-production-readiness.md).

---

## 3. What actually leaves the machine (the minimised LLM payload)

The single most important compliance fact, restated from [doc 14 §3](14-security-and-trust.md):

- **Raw files never leave.** Not the settlement CSV, not the bank statement, not the ledger.
- **Per ambiguous exception**, the agent receives: the 1–5 records in/adjacent to that exception, the candidate-match summaries, the decomposition residual, the relevant spec rules. Account numbers are **masked** unless the spec marks them a match key.
- **`--no-ai` sends nothing** — the full pipeline runs locally.
- Anthropic API inputs are **not used for training** under the standard commercial terms; stated in the README and the DPA so a finance buyer can verify.
- Every LLM request/response is recorded (`AGENT_INTERACTION` events) so the customer has a complete record of exactly what was transmitted.

---

## 4. Security certifications — honest status

| Standard | Status | Note |
|---|---|---|
| SOC 2 Type I / II | **Not started** — needs a company | Roadmap Q2 ([doc 21 §8](21-go-to-market-and-business-model.md)); no architectural blocker |
| ISO 27001 | Not started | Post-traction |
| PCI-DSS SAQ | **Likely out of scope** (no cardholder data) — to be confirmed with a QSA | Card-data minimisation (§1) is designed to keep it out of scope |
| VAPT / pen test | Planned pre-first-paid-customer | The proposal-only tool architecture ([doc 14 C3](14-security-and-trust.md)) limits blast radius regardless |

Arbiter v1 (the Buildathon build) is **local-first and single-tenant**; the compliance surface that matters for the demo is card-data minimisation (done, in the data model) and the minimised LLM payload (done, in the agent design). Everything in §2–§4 that's marked deferred is a *company* build-out, and none of it is blocked by a decision made now — which is the point of documenting it.

---

## 5. Compliance-relevant design decisions already made

| Decision | Doc | Compliance payoff |
|---|---|---|
| No PAN in the data model; drop-and-log full card numbers | [17 §3](17-data-model-and-schema.md) | RBI card-data storage rule |
| `untrusted` fields stored separately, never in logic, fenced for the LLM | [14 C1](14-security-and-trust.md), [17 §3](17-data-model-and-schema.md) | minimisation + injection defense |
| Minimised per-exception evidence bundle; raw files never transmitted | [14 §3](14-security-and-trust.md), [19 §1](19-agent-contracts.md) | DPDP cross-border + minimisation |
| `--no-ai` mode with zero external transfer | [ADR-0001](adr/0001-deterministic-core-ai-at-the-boundary.md) | data-sovereignty option for strict customers |
| Hash-chained tamper-evident event log + `arbiter verify` | [ADR-0002](adr/0002-event-sourced-store.md), [14 C6](14-security-and-trust.md) | breach-scope assessment, audit integrity |
| `arbiter purge` with auditable deletion meta-event | [17 §9](17-data-model-and-schema.md) | DPDP erasure right |
| Redaction filter on log/trace handlers; `gitleaks` pre-commit | [14 C5](14-security-and-trust.md) | secret + PII hygiene |
| India-region pinning for hosted Postgres + object storage | [13](13-production-readiness.md) | RBI data localisation |
