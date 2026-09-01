# Build Log

An honest, running account of what broke during development and how it was resolved.
This directly serves the Buildathon's **Failure Recovery** criterion — kept from day one,
not reconstructed at the end.

Format: newest first. Each entry: what broke · how it showed up · root cause · fix · what changed to prevent recurrence.

---

## 2026-09-02 — Compliance, competitive-field, and completeness pass

- **Git history corrected:** the first 3 commits were mis-attributed (author email
  `rajdeepsinghsakarwar@gmail.com` → GitHub account `Rajdeepsingh49`). Rewrote all commits to
  `krrishverma1805-web <krrishverma1805@gmail.com>` and force-pushed. Local git config +
  a memory now enforce the right identity for all future commits.
- **Competitive landscape ([doc 03 §2.8a](03-competitive-landscape.md)):** added the OSS AI
  reconciliation agents — notably `Manu6259/financial-reconciliation-agent`, which independently
  arrived at the same "LLM proposes, deterministic code disposes" principle. Documented exactly
  where Arbiter goes deeper (adversarial scale, settlement decomposition, the investigation-loop
  agent, calibration, multi-rail, honest sub-100 benchmark).
- **Doc 26 — Compliance & Data Protection:** RBI PA-PG Directions 2025 (card-data minimisation —
  the schema already has no PAN field; data localisation for hosted), DPDP Act 2023/Rules 2025
  (data-fiduciary obligations, `arbiter purge` for the erasure right), PCI-DSS scope (likely out,
  by design), the minimised LLM payload.
- **Doc 12 §6.1a:** replaced the hand-wavy "human-judged equivalent" for `resolution_usefulness`
  with a proper LLM-as-judge protocol (binary reference-based rubric, cited evidence, judge
  ensemble, human-validated to Cohen's κ ≥ 0.6).
- **Doc 27 — Completeness Audit:** the full coverage matrix; the 3 items that are thin only
  because they're empirical (real match rate, real AI lift, heuristic behaviour); everything
  deliberately excluded + why. Verdict: the plan is done — build.
- Code begins now at M0.

## 2026-09-02 — Deep-dive specification pass

- Added 11 build-ready deep-dive docs (15–25) + ADR-0005 (Fellegi–Sunter matching) so nothing
  in the build is left to improvisation:
  - 15 domain model: the settlement identity, the exhaustive exception taxonomy with root
    causes / detection / resolution playbooks / accounting treatment (journal entries).
  - 16 matching engine: blocking, Fellegi–Sunter (m/u seeded from the labeled synthetic data),
    the subset-sum pass (meet-in-the-middle + heuristic), assignment, determinism, perf budget.
  - 17 full physical schema (DDL), every event type + payload, projections, JSON contracts.
  - 18 synthetic data generator: generative model, anomaly-injection catalog, ground truth +
    labeled trajectories, anti-"teaching to the test".
  - 19 agent contracts: the frozen system prompt, per-exception task message, tool JSON
    schemas, strict Proposal/Escalate output schema, few-shots, budgets.
  - 20 API (routes, SSE, errors) + frontend (component tree, state coverage, keyboard, memo).
  - 21 GTM: positioning, ICP, wedge, pricing, unit economics, the field at the Buildathon.
  - 22 cost model (per-exception ~$0.035, per demo run ~$0.65, Buildathon total ~$300).
  - 23 risk register (build/scope/judging) with triggers + contingencies.
  - 24 the 5-minute pitch script + judge walkthrough + anticipated Q&A.
  - 25 testing & CI: property-test invariants, testing the agent cheaply, the pipeline.
- Research folded in: Razorpay `fetch-recon` schema, Fellegi–Sunter math, India settlement
  accounting treatment (SAC 998433, 18% GST on MDR, ITC), FloQast pricing benchmarks.

## 2026-09-02 — Plan evaluation pass

- **Adversarial self-review** of docs 01–10 ([doc 11](11-plan-evaluation-and-gaps.md)). Grade: B+. Found one structural weakness and 14 gaps.
- **Structural fix:** v1 described a pipeline with one LLM call, not an agent. Reframed as **hybrid orchestration** — deterministic skeleton + a real agentic investigation loop (plan → investigate → hypothesize/test → conclude/escalate) — [ADR-0004](adr/0004-hybrid-orchestration.md), [doc 12](12-agent-design.md).
- **New docs:** 11 (evaluation/gaps), 12 (agent design + agent scorecard + calibration), 13 (production readiness), 14 (security & trust), `KNOWN-FAILURE-MODES.md`.
- **Spec updated** to Razorpay's real `fetch-recon` field names (`entity_id`, `settlement_utr`, `debit`/`credit`/`fee`/`tax`, `dispute_id`, …).
- **Still no code broken** — code begins at M0.

## 2026-09-02 — Repository & research phase

- **Set up:** monorepo plan, full `docs/` research and specification set, ADRs, reference recon specs.
- **Nothing broken yet** — code begins at milestone M0.
- **Decision captured:** confined the LLM to a single bounded step ([ADR-0001](adr/0001-deterministic-core-ai-at-the-boundary.md)) after weighing an LLM-first matching approach and rejecting it on reproducibility/auditability grounds.

---

<!--
Template for future entries:

## YYYY-MM-DD — <short title>

**Symptom:** what was observed (test failure, wrong number, crash, judge feedback)
**Root cause:** the actual reason
**Fix:** what was changed
**Prevention:** the test / gate / doc added so it can't silently recur
-->
