# FINAL VALIDATION

The full validation sequence (`ARBITER_FINAL_BUILDATHON_SHIP_SPEC.md` Phase 29),
run 2026-09-04 on HEAD after the final ship pass. **No stage is red.**

| Stage | Command | Result |
|---|---|---|
| Lint | `ruff check .` · `ruff format --check .` | **clean** (209 files formatted) |
| Typecheck (Python) | `mypy packages/{engine,datagen,api}` | **clean** (102 source files) |
| Typecheck (web) | `pnpm typecheck` (`tsc --noEmit`) | **clean** |
| Unit + integration | `pytest -m "not live"` | **255 passed**, 2 skipped (pdf extra, live), exit 0 |
| Determinism / replay | `arbiter replay <run>` · `test_determinism.py` · `test_control_invariants.py` | **chain intact**, terminal hash byte-identical |
| Deterministic benchmark | `arbiter bench --dataset datasets/seed --gate bench/baseline-800.json` | auto-match **93.8%** · false-match **0.0%** · ₹ coverage **100%** · **regression gate passed** |
| Agent benchmark | `arbiter agent-bench --client all --seeds 8 --gate` | oracle: 100% task · 0 unsafe · gate OK. reckless: 0 material unsafe · ₹0.07 slip · gate OK. fabricator: 100% escalated · gate OK. |
| Attack Arbiter | `arbiter attack --spec … --dataset datasets/seed` | **12 contained · 0 partial · 0 missed · 0 UNSAFE · ₹0 unaccounted** |
| Security | `gitleaks` · `pip-audit` (CI `security` job) | **pass** |
| Web build | `pnpm build` | **✓ compiled · 7/7 static pages** |
| Docker | image build + `/healthz` (CI `docker` job) | **pass** |
| Helm | `helm lint` + `kubeconform -strict` (CI `helm` job) | **pass** |
| Postgres restore drill | pg_dump → drop schema → pg_restore → verify + replay (CI `recovery` job) | **pass** (byte-identical after round trip) |
| `datasets/seed` reproducibility | `arbiter-datagen gen --scenario d2c --records 800 --seed 42` → `dataset_hash` | **byte-identical** to the committed dataset |
| Every CLI command | `run` · `run --no-ai` · `bench` · `agent-bench` · `attack` · `verify` · `replay` · `clusters` · `cash-position` · `memo` · `cycle-demo` | **all run from a clean clone** |
| Claims audit | [`CLAIMS_AUDIT.md`](CLAIMS_AUDIT.md) | every number maps to a command; synthetic/live labelled |
| Manual hostile review | [`FINAL_RED_TEAM.md`](FINAL_RED_TEAM.md) | 12 input attacks + 9 agent attacks + 7 infra attacks → **0 unsafe resolutions, 0 crashes** |

## CI

The `bench` job runs `arbiter bench --gate` **and** `arbiter agent-bench --client all --gate`
on every push. The main `test` job runs the full non-live suite (coverage moved
to the nightly job — it gates nothing and doubled the runtime). The nightly job
additionally runs `agent-bench --client anthropic` against a real model when the
`ANTHROPIC_API_KEY` secret is configured.

## The one LIMITED item

A full **live-model** agent-bench run over the 99-case corpus. The infrastructure
is wired (nightly CI step); it needs the repo's `ANTHROPIC_API_KEY` secret set.
Until then the scripted `oracle`/`reckless`/`fabricator` clients bound the harness
and one live gpt-4o investigation is captured in the demo. This is disclosed in
`docs/STATUS.md`, `LIMITATIONS.md`, `CLAIMS_AUDIT.md`, and `FINAL_REPORT.md`.
