# Capability Status — the single source of truth

Every other document (README, cockpit copy, `docs/`, the demo, the pitch) must
agree with this table. If something here says `LIMITED` or `NOT BUILT`, no other
doc may imply otherwise.

_Last verified: 2026-09-04, HEAD `aae0e34`._

## Core engine

| Capability | Status | Proof |
|---|---|---|
| Deterministic reconciliation (matching + money math, zero LLM) | **DONE** | `arbiter run --no-ai`; `test_matching.py`, `test_determinism.py` |
| 8-pass matcher + Fellegi–Sunter scoring | **DONE** | `match/`, `test_fellegi_sunter.py` |
| Settlement decomposition (gross − MDR − GST − refunds ± rounding) | **DONE** | `decompose/identity.py`, `test_matching.py` |
| Multi-format ingest (CSV / XLSX / MT940 / CAMT.053 / PDF text-layer) | **DONE** | `ingest/`, `test_ingest*.py` |
| Multi-currency + FX (unrated currency → quarantine) | **DONE** | `ingest/normalize.py`, `test_fx.py` |
| Exception taxonomy + deterministic classifier | **DONE** | `exceptions/classify.py` |
| Root-cause clustering (`arbiter clusters`) | **DONE** | `exceptions/cluster.py`, `test_cluster.py` |
| Validated exception state machine (terminal states) | **DONE** | `exceptions/state.py`; API 409 on illegal transition |
| Event-sourced store, hash-chained, `arbiter verify` | **DONE** | `events/store.py`, `test_events.py` |
| Deterministic replay (`arbiter replay` → identical terminal hash) | **DONE** | `replay.py`, `test_control_invariants.py` |
| `--no-ai` full-determinism mode | **DONE** | `run.py`; `test_no_ai_preserves_a_complete_reconciliation` |

## AI investigation

| Capability | Status | Proof |
|---|---|---|
| Bounded investigation loop (plan → tools → hypothesise → decide) | **DONE** | `agent/investigator.py`, `test_agent.py` |
| Read-only / proposal-only tool surface | **DONE** | `agent/tools.py`; `test_agent_tools_are_all_read_only` |
| `get_record(id)` citation inspection | **DONE** | `agent/tools.py::get_record`; `test_get_record_tool_is_read_only_and_pii_safe` |
| Evidence grounding (every citation must resolve) | **DONE** | `agent/grounding.py`; `test_a_fabricated_citation_escalates` |
| Independent 2nd-model verifier (fail-closed) | **DONE** | `agent/investigator.py::_verify`; `test_a_broken_verifier_response_escalates` |
| Deterministic counterfactual arithmetic (positive confirmation) | **DONE** | `safety/counterfactual.py`, `test_safety_kernel.py` |
| Structured output contract (schema-validated Proposal / Escalate) | **DONE** | `agent/schemas.py` |
| Prompt-injection quarantine (routed to SECURITY_REVIEW, bypasses the agent) | **DONE** | `exceptions/injection.py`; `test_injection_content_is_quarantined_and_fenced` |
| Provider-pluggable (`AnthropicClient` / `OpenAIClient` / recorded / scripted) | **DONE** | `agent/client.py` |
| Cost honesty (`est_cost_usd = None` for unpriced models, never `$0.000`) | **DONE** | `agent/pricing.py`; `test_pricing.py` |
| Model-keyed calibration (a Claude ECE is never shown as GPT's) | **DONE** | `bench/calibration.py::model_key` |

## Safety

| Capability | Status | Proof |
|---|---|---|
| Deterministic Safety Kernel — the single proposal-decision gate | **DONE** | `safety/kernel.py`; `test_every_proposal_passes_through_the_kernel` |
| R0–R5 risk tiers | **DONE** | `safety/risk.py`, `test_safety_kernel.py` |
| R5 / money-movement categories never return SAFE | **DONE** | `test_r5_control_category_never_returns_safe`, `test_never_safe_categories_never_return_safe` |
| `SAFE` requires a *positive* arithmetic confirmation (earned, not "no red flag") | **DONE** | `safety/kernel.py` step 7 |
| Fail-closed everywhere (verifier / provider / budget / fabrication → escalate) | **DONE** | `test_control_invariants.py` |
| **Arbiter never auto-resolves** — a human confirms every proposal | **DONE** | `test_nothing_in_the_codebase_auto_applies_a_safe_decision` (greps the tree) |
| Headline safety metrics in the scorecard, CI-gated at tolerance 0 | **DONE** | `bench/scorecard.py::SafetyScore`, `bench/gate.py` |
| Attack Arbiter (12 deterministic tamperings) | **DONE** | `arbiter attack`; `test_attacks.py` — 12 contained · 0 unsafe · ₹0 unaccounted |
| 14 named control-invariant tests | **DONE** | `docs/CONTROL_INVARIANTS.md`, `test_control_invariants.py` |

## Evaluation

| Capability | Status | Proof |
|---|---|---|
| Deterministic matching benchmark + regression gate | **DONE** | `arbiter bench --gate`; CI `bench` job |
| Adversarial synthetic distribution + graceful-degradation invariants | **DONE** | `arbiter-datagen --difficulty adversarial`; CI `bench` job |
| **Agent trajectory benchmark** — 99 labelled cases, real loop, usefulness vs safety scored apart | **DONE** | `arbiter agent-bench`; `test_agent_bench.py`; CI `bench` job |
| Meaningful **live-model** agent benchmark (Claude / GPT over the full corpus) | **LIMITED** | one live gpt-4o investigation captured (the verifier caught a bad proposal); no full run — needs an API key in CI |
| Confidence calibration study | **DONE** (structure) · **LIMITED** (live) | `arbiter bench --calibration`; the agent ECE needs a live-model run |

## Product / UX

| Capability | Status | Proof |
|---|---|---|
| Cockpit — scorecard, keyboard exception queue, evidence drawer | **DONE** | `web/`, `test_api.py` |
| Structured investigation chain (PLAN → EVIDENCE → PROPOSAL → SAFETY → OUTCOME) | **DONE** | `Cockpit.tsx::InvestigationChain`; `_fold_agent_investigation` |
| Safety Kernel decision visible in the cockpit + the streaming view | **DONE** | `Cockpit.tsx`, `LiveRun.tsx` |
| "Why didn't Arbiter resolve this?" | **DONE** | `Cockpit.tsx::WhyNotResolved` |
| "Explain this number" (decomposition popover) | **DONE** | `Cockpit.tsx` |
| No raw JSON in the primary UI (behind a "Technical detail" disclosure) | **DONE** | `Cockpit.tsx`, `_strip_json` |
| Hosted-demo overview ("are my numbers right?" in 5 seconds) | **DONE** | `web/src/app/page.tsx::DemoOverview` |
| Attack Arbiter panel in the cockpit | **DONE** | `Cockpit.tsx::AttackPanel`; `POST /v1/attack` |
| Close Memo + audit-pack | **DONE** | `arbiter memo`, `arbiter audit-pack` |
| Cash-position readout | **DONE** | `arbiter cash-position` |

## Platform (out of scope for the submission, present and tested)

| Capability | Status |
|---|---|
| API-key auth, RBAC, org-scoping, Postgres RLS | **DONE** |
| Async job queue, idempotency, rate limiting, S3 storage | **DONE** |
| Alembic migrations, Docker, Helm, OTel/Sentry hooks, MCP server | **DONE** |

## NOT BUILT / NOT DONE (stated deliberately)

| Item | Status | Why |
|---|---|---|
| OCR for scanned (no text-layer) PDFs | **NOT BUILT** | raises a clear error; fail closed rather than guess at image-only financial data |
| Live processor / bank / ERP connectors | **NOT BUILT** | stated v1 non-goal; batch-file ingestion only |
| Real customer validation | **NOT DONE** | zero customers, zero design partners; no real bank statement has been reconciled |
| Production target-load validation (500 orgs, 10k runs/day) | **NOT DONE** | the queue/worker/HPA architecture exists; the evidence it holds does not |
| ERP journal posting, fraud detection, cash forecasting, consolidation, mobile, SOC 2 | **NOT BUILT** | out of scope for v1 |
