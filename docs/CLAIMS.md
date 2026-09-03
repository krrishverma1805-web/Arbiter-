# Claims → Proof

Every claim Arbiter makes, the command that proves it, and where it is not yet
proven. The rule: **the UI and the README never state anything stronger than a
row in this table.**

| Claim | Proof | Command | Dataset · seed | Expected | Status |
|-------|-------|---------|----------------|----------|--------|
| The deterministic core is bit-reproducible | terminal-hash match on a byte-identical re-run | `arbiter replay <run>` · `arbiter verify <run>` | any | `intact: true`, hashes equal | **verified** (`test_determinism.py`, CI `determinism` job) |
| Honest match quality on adversarial data | matching scorecard vs a shipped answer key | `arbiter bench --spec specs/razorpay-settlement.yaml --dataset datasets/seed` | seed · 42 | auto-match 93.8% · precision 100% · **false-match 0.0%** · ₹ coverage 100% | **verified** (CI `bench` job + gate) |
| Never a wrong confident auto-tie, even under attack | 12 deterministic tamperings, reconcile, check no tampered record gets a clean tie | `arbiter attack --spec … --dataset datasets/seed` | seed · 42 | **12 contained · 0 unsafe · ₹0 unaccounted** | **verified** (`test_attacks.py`, CI) |
| The AI never auto-resolves; a human confirms every proposal | no code path applies a proposal without a human `RESOLUTION_APPLIED` | `pytest packages/engine/tests/test_control_invariants.py::test_nothing_in_the_codebase_auto_applies_a_safe_decision` | — | the only reader of `"SAFE"` is the benchmark metric | **verified** |
| A confident *wrong* agent never reaches a material unsafe resolution | labelled trajectory benchmark, adversarial `reckless` client | `arbiter agent-bench --client reckless --seeds 16` | 16 seeds | `material_unsafe_resolutions == 0`; SAFE-gate slips only on immaterial ₹ | **verified** (CI `bench` job) |
| A competent agent is accepted and its human-only cases all escalate | benchmark, `oracle` client | `arbiter agent-bench --client oracle --seeds 16` | 16 seeds | task ≥ 85% · category 100% · **escalation recall 100%** · 0 unsafe · positive lift | **verified** (CI) |
| A fabricated citation always escalates | benchmark, `fabricator` client + kernel unit test | `arbiter agent-bench --client fabricator` | 16 seeds | `fabricated_escalated_rate == 1.0` | **verified** |
| Settlement decomposition catches a total-match that doesn't balance | identity solver residual on every match | `arbiter bench …` (see `dollar_unexplained`) | seed · 42 | a batch that doesn't decompose becomes an exception | **verified** (`test_matching.py`, `decompose/`) |
| Prompt-injected record content cannot control the agent | injection scanner → SECURITY_REVIEW (bypasses the agent) + fenced input | `pytest -k injection` | — | routed away; never in a proposal | **verified** |
| Tenant isolation | org-scoped reads/writes + Postgres RLS | `pytest packages/api/tests -k "isolation or rls"` · CI `recovery` job | — | no cross-org read | **verified** |
| The learned rules raise the match rate over cycles | 3-close cycle demo, each close scored twice | `arbiter cycle-demo` / `make cycle` | synthetic | month-3 auto-match ≥ month-1 | **verified on synthetic** — never on a real customer's three closes |
| Confidence is calibrated per model | ECE keyed by provider/model/prompt | `arbiter bench … --calibration` | seed · 42 | `model_key` on the report; a Claude ECE is never shown as GPT's | **verified** (structure); the agent ECE needs a live-model run |
| **Real-world accuracy** | a real reconciliation from a real finance team | — | — | — | **NOT VALIDATED** — no customer, no real bank statement has been reconciled |
| **Production scale** (500 concurrent orgs, 10k runs/day) | a load test at that target | — | — | — | **NOT VALIDATED** — the queue/worker/HPA architecture exists; the evidence it holds does not |
| **Agent accuracy on a live frontier model** | `agent-bench --client anthropic` / `openai` with a key | needs `ANTHROPIC_API_KEY` in CI | — | — | **partial** — one live gpt-4o investigation captured (the verifier caught a bad proposal); no full live trajectory run |

## How to read a "verified" row

Clone the repo, run the command, get the number. No login, no key (except the
last three rows). The synthetic-data asterisk is real and stays visible
everywhere: these are reproducible benchmarks on data Arbiter's own generator
produced, not customer production results.
