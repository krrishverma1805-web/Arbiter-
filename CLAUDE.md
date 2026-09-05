# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Arbiter is a verification layer for money movement — a Razorpay AI Buildathon
2026 submission (track: AI Finance Controller). Given a payment processor's
settlement report, a bank statement, and an order ledger for one batch, it
reconciles them, reports an honest match rate (including its own false-match
rate), and returns a categorized, evidence-backed list of exceptions it could
not resolve.

The core design doctrine (`docs/adr/0004-hybrid-orchestration.md`): a
**deterministic state-machine skeleton** does all matching and money math —
reproducible, no LLM in that path — and exactly **one bounded agentic
investigation loop** (plan → gather evidence via read-only tools → test a
hypothesis → conclude or escalate) handles the residue that's genuinely a
judgment call. The agent only ever investigates and proposes; a deterministic
**Safety Kernel** (`safety/kernel.py`) is the single gate that decides
SAFE / PROPOSE / ESCALATE / QUARANTINE, and **a human confirms every
proposal** — nothing in the codebase auto-applies a resolution (this is a
grepped test invariant, see `test_control_invariants.py`). `--no-ai` disables
the agent entirely and the deterministic core still produces a complete
reconciliation.

`docs/STATUS.md` is the single source of truth for what's actually built vs.
limited vs. not built. Every other doc (README, this file, the cockpit copy)
must agree with it — if you're unsure whether something exists, check there
first. `docs/CLAIMS.md` maps every claim to the exact command that reproduces
it.

## Commands

### Setup
```
uv sync --all-packages              # Python workspace (engine + datagen + api)
cd web && pnpm install              # frontend
```
The `openai` extra (`uv sync --all-packages --extra openai`) is required for
`OpenAIClient`, `GroqClient` and `GeminiClient` — they share one wire format.
`ANTHROPIC_API_KEY` (or `GROQ_API_KEY` / `GEMINI_API_KEY` / `OPENAI_API_KEY`)
is only needed to run the agent live; everything else works with no key.

### Run the engine
```
make demo                                    # generate datasets/seed, reconcile, print scorecard
arbiter run --spec specs/razorpay-settlement.yaml --dataset datasets/seed [--no-ai]
arbiter bench --spec <spec> --dataset <dataset> [--gate bench/baseline-800.json]
arbiter attack --spec <spec> --dataset <dataset>        # 12-scenario adversarial harness
arbiter agent-bench --client oracle|reckless|fabricator|all|anthropic|openai|groq|gemini --seeds N [--gate]
arbiter replay <run-id>                      # byte-identical re-run, proves determinism
arbiter verify                                # checks the hash-chained event log
arbiter clusters | arbiter memo | arbiter audit-pack | arbiter cash-position
```
`arbiter-datagen gen --scenario d2c --records 800 --seed 42 --out <dir>`
regenerates a dataset with `ground_truth.json` alongside it — everything in
`bench`/`agent-bench` is scored against that file.

### Backend + frontend
```
make api                 # FastAPI on :8000
make web                  # Next.js cockpit on :3000 (needs api running)
make up                   # both together
```

### Tests
```
uv run pytest -q                                   # full suite
uv run pytest -q -m "not live"                     # CI mode — skips real-API tests
uv run pytest packages/engine/tests/test_agent.py::test_name -q   # single test
```
The `live` marker (`pyproject.toml`) is for tests that hit a real provider API
— nightly only, excluded from the normal/CI run.

### Lint / format / type-check
```
uv run ruff check .                  # add --fix to auto-fix
uv run ruff format --check .
uv run mypy packages/engine/arbiter_engine packages/datagen/arbiter_datagen packages/api/arbiter_api
cd web && npx tsc --noEmit && pnpm build
```
`make lint` / `make typecheck` run both the Python and web sides together.
mypy is `strict = true`; scope is source only (`arbiter_engine`,
`arbiter_datagen`, `arbiter_api`) — it does not check `tests/`.

## Architecture

**uv workspace**, three independent packages plus a Next.js frontend:

- `packages/engine` (`arbiter_engine`) — the CLI (`arbiter`) and all
  deterministic + agent logic. Has no web/API dependency.
- `packages/datagen` (`arbiter_datagen`) — synthetic dataset generator
  (`arbiter-datagen`), emits `ground_truth.json` alongside the data it makes.
- `packages/api` (`arbiter_api`) — FastAPI backend (`arbiter-api`) serving the
  cockpit; auth, job queue, Postgres/SQLite storage live here, not in the
  engine.
- `web/` — the Next.js cockpit (scorecard, keyboard exception queue, evidence
  drawer, streaming investigation view).

### Inside `arbiter_engine`

| Module | Responsibility |
|---|---|
| `ingest/` | Multi-format parsing (CSV/XLSX/MT940/CAMT.053/PDF text-layer) → normalized records |
| `match/` | The 8-pass matcher (exact → tolerant → subset-sum → fuzzy → blocked → aggregate N:1/1:N → carry-forward), Fellegi–Sunter scoring |
| `decompose/` | Settlement identity check: `net = gross − MDR − GST − refunds ± rounding` |
| `exceptions/` | Classification, root-cause clustering, the validated exception state machine, prompt-injection quarantine |
| `events/` | The event-sourced, hash-chained store everything is built on (`arbiter verify` checks the chain) |
| `agent/` | The investigation loop (`investigator.py`), the LLM client abstraction (`client.py`), tools, grounding, structured-output schemas |
| `safety/` | The Safety Kernel (`kernel.py`), risk tiers R0–R5, deterministic counterfactual arithmetic, policy |
| `bench/` | `arbiter bench` (matching scorecard + regression gate) and `arbiter agent-bench` (99-case agent trajectory benchmark, scores usefulness and safety separately) |
| `run.py` / `replay.py` | Orchestrates one reconciliation run; replay reproduces a prior run's terminal hash byte-for-byte |
| `attack.py` | The adversarial harness (12 deterministic tamperings) |
| `cli.py` | The `arbiter` Typer app — thin, delegates everything above |

### The agent client abstraction (`agent/client.py`)

Every provider implements one `LLMClient` protocol and returns a provider-
agnostic `Turn` (text, tool calls, stop reason, token usage), so the
investigator, grounding, replay and scorecard never know which model ran.
`AnthropicClient` is the native implementation; `OpenAIClient`, `GroqClient`
and `GeminiClient` all subclass `_OpenAICompatibleClient` because Groq and
Gemini both expose OpenAI-wire-compatible endpoints — only base URL, API key
source and default model differ per subclass. `RecordedClient` replays
captured `AGENT_INTERACTION` events (what `arbiter replay` uses — no network
call). `ScriptedClient` returns canned turns for the offline test suite and
for `agent-bench`'s `oracle`/`reckless`/`fabricator` scripted personas.

All live clients share `_with_retry` — bounded exponential backoff on a rate
limit, with a per-attempt delay cap so a provider that reports a very long
wait doesn't stall for tens of minutes. `bench/agent_bench.py::evaluate`
catches any exception `investigate()` still raises and escalates that one
case (mirroring `agent/orchestrate.py`, which does the same for the real
`arbiter run --ai` path) — a live provider hiccup degrades one exception to
"needs a human," it never crashes the run.

### Safety flow

Every agent proposal passes through exactly one gate — `safety/kernel.py`.
It checks, in order: risk tier (R5 / money-movement categories can never
return SAFE), evidence grounding (every citation must resolve to a real
record), a deterministic counterfactual arithmetic check (SAFE requires a
*positive* confirmation, not just "no red flag"), and an independent
second-model verifier for high-impact exceptions. Any failure, timeout, or
unparseable response anywhere in that chain fails closed to ESCALATE. The
headline safety metric across all benchmarks is `unsafe_resolution_rate`,
which CI gates at tolerance 0.

### Specs and datasets

A reconciliation problem is declared once as a YAML spec (`specs/*.yaml` —
e.g. `razorpay-settlement.yaml`) covering field mappings, matching
tolerances, and risk/materiality thresholds; `arbiter run`/`bench`/`attack`
all take `--spec` + `--dataset`. `datasets/seed` is the canonical fixture
dataset with a committed `ground_truth.json`; `bench/baseline-800.json` is
the committed regression baseline that `arbiter bench --gate` checks new runs
against (each metric has a direction and a tolerance — safety metrics carry
tolerance 0.0, i.e. they may never regress).
