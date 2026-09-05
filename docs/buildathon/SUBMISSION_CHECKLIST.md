# Submission Checklist

Status at the close of the master-plan hardening pass (Stages A–D).

## Financial correctness

- [x] deterministic matching benchmark green (`arbiter bench`, CI `bench` job)
- [x] false-match rate measured and published (0.0% on seed)
- [x] settlement decomposition tested (`test_matching.py`, `decompose/`)
- [x] ₹ coverage measured (100% on seed)
- [x] exact integer minor-unit arithmetic (`test_control_invariants.py::test_money_math_is_integer_only`)

## Agent — usefulness

- [x] 99 labelled trajectory cases (`arbiter agent-bench`, ≥ 40 required)
- [x] task completion measured (oracle 100%)
- [x] category accuracy measured (oracle 100%)
- [x] evidence grounded rate measured (100%)
- [x] escalation precision / recall measured (100% / 100%)
- [x] AI lift measured (+44% vs. "escalate everything")
- [x] trajectory efficiency measured (avg turns / tokens)

## Agent — safety

- [x] `unsafe_resolution_rate` = 0 on the oracle client (CI-gated)
- [x] `material_unsafe_resolutions` = 0 on the reckless adversary (CI-gated)
- [x] fabricated citations always escalate (`fabricated_escalated_rate` = 1.0)
- [x] R5 / money-movement categories never return SAFE (`test_control_invariants.py`)
- [x] verifier failure escalates (fail-closed)
- [x] provider failure escalates (not a crash)
- [x] prompt-injection suite green (quarantined at ingest, never reaches the model)
- [x] Attack Arbiter green (12 contained · 0 unsafe · ₹0 unaccounted)

## Auditability

- [x] every proposal carries ≥ 1 evidence reference (schema-enforced)
- [x] every citation resolves or the proposal escalates
- [x] prompt hash + model recorded on every agent event
- [x] event chain verified (`arbiter verify`)
- [x] replay reproduces the terminal hash byte-for-byte
- [x] audit pack works (`arbiter audit-pack`)

## UX

- [x] no raw JSON in the normal investigation UI — moved behind "Technical detail"
- [x] the structured chain renders (PLAN → EVIDENCE → PROPOSAL → SAFETY DECISION → OUTCOME)
- [x] the Safety Kernel decision is one glance in the cockpit + the streaming view
- [x] "Why didn't Arbiter resolve this?" panel on escalations
- [x] "explain this number" decomposition popover on the impact figure
- [x] hosted-demo home page leads with the "are my numbers right?" overview
- [x] keyboard-first exception queue · light/dark parity · reduced motion
- [x] cost never shows a fake `$0.000` — "unavailable for this provider" instead

## Demo

- [x] a varied flagship dataset (`datasets/seed` — 11 anomaly types)
- [x] one **real** AI investigation captured (gpt-4o, the verifier rejection)
- [x] Attack Arbiter demo beat
- [x] benchmark demo beat
- [x] `--no-ai` demo beat
- [x] replay demo beat
- [x] Close Memo
- [x] 3-minute script with current numbers (`docs/buildathon/DEMO.md`)
- [ ] recorded 4–6-investigation flagship run — *declined*: the benchmark tells
      that story with 99 cases; padding the demo with scripted investigations
      would be less honest than one real run

## Honesty

- [x] synthetic data labelled as synthetic, everywhere
- [x] real-data limitation explicit (`docs/buildathon/LIMITATIONS.md`, `docs/CLAIMS.md`)
- [x] scale limitation explicit
- [x] "Arbiter never auto-resolves" stated in the README, the UI, and `AI_SAFETY.md`
- [x] no fake cost, no cross-model calibration
- [x] `docs/CLAIMS.md` — the anti-overclaim mechanism; the UI states nothing stronger

## Build

- [x] 255 tests, `-m "not live"`
- [x] `ruff check` + `ruff format --check` clean
- [x] `mypy` clean (102 source files)
- [x] `tsc --noEmit` + `next build` clean
- [x] `datasets/seed` regenerates byte-identically (`dataset_hash` match)
- [x] every CLI command runs from a fresh clone
- [x] commits authored `krrishverma1805-web`

## Not done (deliberately)

- Live processor / bank / ERP connectors (v1 non-goal)
- OCR for scanned PDFs
- SSO, key rotation, SOC 2
- A full live-model agent-bench run against **Claude or GPT** specifically
  (needs a funded key) — a full 99-case run against **Gemini** is done
  (`docs/STATUS.md`; 46/99 completed, the rest escalated on a free-tier rate
  limit, not crashed)
- The 5-minute pitch **video** — the builder's task
