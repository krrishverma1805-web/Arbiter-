# FINAL AUDIT

Audit against `ARBITER_FINAL_BUILDATHON_SHIP_SPEC.md` v1.0.
HEAD `aae0e34` → this pass. Prior work: the four-stage hardening pass
(`be84bbf` → `aae0e34`) closed the bulk of the ship spec's asks; this audit
re-verifies against its exact acceptance criteria and finds what remained.

## Verdict

**Everything the spec rates P0 for safety, correctness, or "unsafe financial
resolution" is DONE and test-verified.** What remained was: the six mandated
deliverable docs, a single authoritative capability matrix, and a handful of
stale illustrative numbers in deep docs.

## Component classification

See [`docs/STATUS.md`](../STATUS.md) — the single source of truth. Summary:

| Layer | DONE | LIMITED | NOT BUILT |
|---|---|---|---|
| Core engine (recon, match, decompose, ingest, replay, `--no-ai`) | all | — | — |
| AI investigation (loop, tools, `get_record`, grounding, verifier, counterfactual, cost, calibration) | all | — | — |
| Safety (Kernel, R0–R5, never-safe, fail-closed, never-auto-resolve, Attack Arbiter, 14 invariants) | all | — | — |
| Evaluation (matching bench + gate, adversarial dist, **agent trajectory bench**) | all | live-model agent bench over the full corpus | — |
| Product / UX (cockpit, structured chain, safety card, why-not-resolved, explain-this-number, demo overview) | all | — | — |
| Out of scope | — | — | OCR, live connectors, real-customer validation, production-load validation |

## Gap matrix (what this pass fixed)

| ID | Finding | Severity | Action taken |
|---|---|---|---|
| G1 | The 6 spec-mandated output docs (`FINAL_AUDIT` … `BUILDATHON_READINESS`) did not exist | P0 | created (this pass) |
| G2 | No single authoritative `Capability \| Status` matrix (`SUBMISSION_CHECKLIST` is a task list) | P0 | `docs/STATUS.md` created, linked from README |
| G3 | Pitch one-liner "97.2% / ₹41,900 / 6 exceptions" ≠ reproducible "93.8% / ₹1.73L / 9 exceptions" | P1 | reconciled in README, chatgpt.md, docs/02/05/06/20 |
| G4 | `docs/07` §3.4 cycle table claimed "exact numbers from the real run" — false (cycle-demo reports ₹ recovered) | P1 | replaced with the real `cycle-demo` output |
| G5 | `docs/25` CI PR-comment mockup used contradicting numbers (`96.7%`, `0.6%`, `$0.31`) | P1 | marked schematic; swapped in real numbers |
| G6 | `test_agent_bench.py` built 3 corpora (18 reconciliations); CI `test` job ~20–30 min with `--cov` | P1 | test uses `evaluate_all()` (one corpus); `--cov` moved to the nightly job; nightly also runs a **live** agent-bench if the API key secret is set |
| G7 | Frozen demo has only 1 investigation | P2 (accepted) | kept — one real investigation + the 99-case benchmark is more honest than scripted padding (spec Phase 6 agrees); documented |
| G8 | HEAD had no completed green CI run | P1 | tracked to green before `BUILDATHON_READINESS` |
| G9 | README test count stale (229) | P1 | → 259 |

## Safety non-negotiables (spec Phase 3) — all verified

Every one of the 14 invariants maps to a named test in
`packages/engine/tests/test_control_invariants.py` (+ `test_safety_kernel.py`,
`test_agent.py`, `test_attacks.py`). See
[`docs/CONTROL_INVARIANTS.md`](../CONTROL_INVARIANTS.md).

## No engine change

This pass touched: `test_agent_bench.py` (corpus sharing), `.github/workflows/ci.yml`
(coverage → nightly + live agent-bench), and documentation. The engine, matcher,
Safety Kernel, and agent are untouched.
