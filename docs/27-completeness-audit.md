# 27 — Completeness Audit

_A final, honest check: has every dimension of this product and this build been researched and specified, or are there gaps? Written to be the last document a skeptic reads before concluding the plan is real._

**Verdict:** the plan is **complete enough to build**. Every dimension below is either specified to build-ready detail or explicitly deferred with a reason. The three items still marked "thin" are thin because they can only be resolved by writing code and measuring — not by more planning.

---

## 1. Coverage matrix

Legend: ✅ specified to build-ready detail · 🟡 specified, will firm up during the build · ⏸ deliberately deferred (reason given) · ❌ gap

### Product & strategy
| Dimension | Status | Where |
|---|---|---|
| Problem definition & "why now" | ✅ | [01](01-market-and-thesis.md) |
| Which finance-ops loop, and why | ✅ | [01 §3](01-market-and-thesis.md), [09 Q1](09-open-strategic-questions.md) |
| Product definition, scope, non-goals | ✅ | [02](02-product-spec.md) |
| Target user / persona | ✅ | [02 §3](02-product-spec.md), [21 §2](21-go-to-market-and-business-model.md) |
| Competitive landscape (incumbents, startups, PG-native, OSS engines, **OSS AI agents**) | ✅ | [03](03-competitive-landscape.md) |
| Differentiation / defensible wedge | ✅ | [03 §4](03-competitive-landscape.md), [21 §1](21-go-to-market-and-business-model.md) |
| Why it might NOT sell (red-team) | ✅ | [08](08-why-it-might-not-sell.md) |
| Go-to-market, pricing, unit economics | ✅ | [21](21-go-to-market-and-business-model.md) |
| Open strategic questions | ✅ | [09](09-open-strategic-questions.md) |

### Architecture & engineering
| Dimension | Status | Where |
|---|---|---|
| Architectural principles / the AI boundary | ✅ | [04 §1–3](04-technical-architecture.md), [ADR-0001](adr/0001-deterministic-core-ai-at-the-boundary.md), [ADR-0004](adr/0004-hybrid-orchestration.md) |
| The agent: loop, tools, stopping, replay | ✅ | [12](12-agent-design.md), [19](19-agent-contracts.md) |
| Matching algorithm (blocking, Fellegi–Sunter, subset-sum, assignment) | ✅ | [16](16-matching-engine-deep-dive.md), [ADR-0005](adr/0005-fellegi-sunter-matching.md) |
| Settlement decomposition / the identity | ✅ | [15 §2](15-domain-model-reconciliation.md), spec |
| Exception taxonomy (root cause, detection, resolution, accounting) | ✅ | [15 §3–5](15-domain-model-reconciliation.md) |
| Data model & full schema (DDL, events, projections) | ✅ | [17](17-data-model-and-schema.md), [ADR-0002](adr/0002-event-sourced-store.md) |
| Recon spec DSL | ✅ | [04 §5](04-technical-architecture.md), [ADR-0003](adr/0003-recon-spec-as-data.md), `specs/` |
| Synthetic data generator | ✅ | [18](18-synthetic-data-generator.md) |
| Ingestion / real-format parsers | ✅ (3 profiles specified) | [11 G5](11-plan-evaluation-and-gaps.md), [15](15-domain-model-reconciliation.md) |
| API surface | ✅ | [20 §1](20-api-and-frontend-spec.md) |
| Frontend architecture & screens | ✅ | [05](05-design-doctrine.md), [20 §2](20-api-and-frontend-spec.md) |
| Design system (tokens, type, motion, a11y) | ✅ | [05 §3–5](05-design-doctrine.md) |
| Tech stack + rationale for each choice | ✅ | [04 §8](04-technical-architecture.md) |
| Repo structure | ✅ | [04 §9](04-technical-architecture.md) |

### Evaluation & quality
| Dimension | Status | Where |
|---|---|---|
| Matching benchmark (metrics, ground truth, anti-cherry-pick) | ✅ | [07](07-evaluation-and-benchmark.md) |
| Agent benchmark (task-completion, tool-use, grounding, hallucination, escalation) | ✅ | [12 §6](12-agent-design.md) |
| LLM-as-judge protocol for subjective metrics | ✅ | [12 §6.1a](12-agent-design.md) |
| Confidence calibration (matcher + agent) | ✅ | [16 §5.5](16-matching-engine-deep-dive.md), [12 §6.2](12-agent-design.md) |
| Model ablation (`--no-ai` / haiku / sonnet / opus) | ✅ | [12 §5](12-agent-design.md) |
| Testing strategy & CI pipeline | ✅ | [25](25-testing-and-ci-strategy.md) |
| Known failure modes (the agent's own) | ✅ structure; 🟡 fills from real runs | [KNOWN-FAILURE-MODES.md](KNOWN-FAILURE-MODES.md) |

### Operations, security, compliance
| Dimension | Status | Where |
|---|---|---|
| Production readiness (migrations, tracing, resilience, SLOs, runbook) | ✅ | [13](13-production-readiness.md) |
| Security threat model + controls (prompt injection, tampering, secrets) | ✅ | [14](14-security-and-trust.md) |
| Cost model (per-exception → at-scale) | ✅ | [22](22-cost-model.md) |
| Regulatory: RBI PA-PG, DPDP Act, PCI-DSS scope | ✅ | [26](26-compliance-and-data-protection.md) |
| Risk register (build/scope/judging) | ✅ | [23](23-risk-register.md) |

### Delivery
| Dimension | Status | Where |
|---|---|---|
| Implementation plan / milestones / judging-criteria map | ✅ | [10](10-implementation-plan.md) |
| Definition of done / submission checklist | ✅ | [10 §7](10-implementation-plan.md), [11 §7](11-plan-evaluation-and-gaps.md) |
| Demo & pitch script + judge walkthrough + Q&A | ✅ | [24](24-demo-and-pitch.md) |
| Build log / failure-recovery narrative | ✅ ongoing | [BUILD-LOG.md](BUILD-LOG.md) |
| Licensing | ✅ open-core, Apache-2.0 | [09 Q2](09-open-strategic-questions.md), `LICENSE` |

---

## 2. The three items still "thin" — and why more planning won't help

| # | Item | Why it's thin | How it gets resolved |
|---|---|---|---|
| A | **Real-world match rate** vs the synthetic number | We have no real Razorpay export + bank statement yet | Build M1–M2, run it, report the honest synthetic number with the asterisk; attempt one real dataset ([09 Q5](09-open-strategic-questions.md)) |
| B | **Actual AI lift** (agent vs `--no-ai`) | Can't know until the agent and the deterministic baseline both exist and are measured | M3 measures it; a small number is a *finding to report*, not a failure ([23 T3](23-risk-register.md)) |
| C | **Subset-sum heuristic behaviour** on pathological batches | Depends on real block-size distributions | M2 stress-tests it; heuristic is bounded and flagged; ILP is the documented fallback ([16 §6.3](16-matching-engine-deep-dive.md)) |

None of these is a *specification* gap. They are *empirical* questions that the build answers.

---

## 3. What is deliberately excluded (and the reason)

| Excluded | Reason | If it continues |
|---|---|---|
| Posting journal entries to the ERP | "Act on money" is a trust/liability leap ([08 R8](08-why-it-might-not-sell.md)) | Proposed JEs → one-click post, behind a flag, Q3 ([21 §8](21-go-to-market-and-business-model.md)) |
| Live bank/ERP API connectors | Connector sprawl is a deliberate v1 non-goal; 3 real *file* parsers ship instead | Connector SDK, post-hackathon |
| Multi-tenant auth / RBAC / SSO / billing | Not judged; local-first demo; `org_id` reserved in the schema | Middleware + row-level security |
| Full cash forecasting | Only credible on a reconciled ledger; a deterministic *position* readout is the P2 stretch | Forecasting module, Q4 |
| Multi-currency consolidation, intercompany elimination | Enterprise-close scope; different product | — |
| Multi-agent architecture | 2–10× cost, no accuracy gain at this scale ([12 §8](12-agent-design.md)) | Revisit only if trajectory eval demands it |
| SOC 2 / ISO 27001 / formal DPIA / DPO | Company obligations, not architecture; none blocked by a current decision | [21 §8](21-go-to-market-and-business-model.md), [26 §4](26-compliance-and-data-protection.md) |
| Mobile app | The cockpit is responsive to tablet; a native app is unwarranted | — |
| i18n / non-INR-non-USD | India + a Stripe-shaped scenario cover the demo; the money layer is currency-generic | Add locales when a customer needs one |

Every exclusion is *named* and *reasoned*. A reviewer reading this section sees scope discipline, not oversight — which is the intended signal.

---

## 4. Research provenance

Every non-obvious claim in the docs is sourced. Primary research threads:

- **The buildathon itself** — the track brief, judging criteria (Problem Taste / Build Quality / AI Judgment / Failure Recovery), the bar.
- **The market** — BlackLine, HighRadius, Numeric, Nominal, Ledge (funding, positioning, claims); the verification-bottleneck thesis.
- **Razorpay domain** — the `fetch-recon` field schema, settlement mechanics, the `net = gross − MDR − GST − refunds − chargebacks` identity, Smart Collect 2.0.
- **India regulatory** — RBI PA-PG Directions 2025 (card-data storage, T+1, localisation), DPDP Act 2023 + Rules 2025, GST on MDR (SAC 998433, 18%, ITC).
- **Technical** — Fellegi–Sunter record linkage (m/u, match weights, blocking); entity resolution; hybrid deterministic/agentic orchestration for high-stakes workflows; 2026 agent-evaluation practice (trajectory, tool-use accuracy, grounding); LLM-as-judge reliability (position bias, κ validation); prompt-injection defense (CaMeL / PARSE, untrusted-data fencing); OSS reconciliation engines (Blnk, Lerian Matcher) and OSS AI recon agents.
- **Commercial** — finance-close software pricing (FloQast benchmarks), fintech GTM patterns.

Sources are linked inline throughout docs 01, 03, 08, 11, 15, 16, 21, 26.

---

## 5. Conclusion

The plan spans **27 documents + 5 ADRs + 2 working recon specs**. It covers the product, the market, the competition (including the OSS agents that share Arbiter's core principle), the architecture, the agent, the matching mathematics, the full schema, the data generator, the evaluation of both the matcher and the agent, security, compliance, cost, risk, GTM, testing, the build plan, and the pitch.

There is no remaining *specification* work that would materially de-risk the build. The next dollar of effort belongs in **code** — milestone M0 in [doc 10](10-implementation-plan.md). What the build will teach us (real match rate, real AI lift, heuristic behaviour) is written down as open empirical questions, not pretended away.

**The plan is done. Build.**
