# 10 — Implementation Plan

_How Arbiter gets built, in what order, mapped to how it's judged, with a realistic schedule and a definition of done._

---

## 1. Build philosophy

- **Vertical slices, deterministic-first.** Every milestone ends with `arbiter run` working end-to-end on real synthetic data and producing a scorecard. The scope of the slice grows; there is never a "big bang integration" week.
- **The benchmark is built in M1, not M5.** You cannot tune what you cannot measure. `arbiter bench` exists before the matcher is good.
- **The AI step is added late and behind a flag.** The deterministic core must be excellent and measured _first_. The AI is layered on and its lift is measured against that baseline.
- **Docs and code move together.** Every ADR-worthy decision gets an ADR. The `docs/` folder is part of the deliverable.

---

## 2. Mapping to the judging criteria

The four stated criteria (from [01](01-market-and-thesis.md) §7), and exactly how the build addresses each:

### Problem Taste — "a meaningful, real-world financial problem"
- Multi-rail settlement reconciliation is a universal, recurring, money-denominated finance-ops pain ([01](01-market-and-thesis.md) §2, §3).
- The framing — _the exception list is the product, not the leftover_ ([09](09-open-strategic-questions.md) Q10) — shows we understand where the actual pain is (the residual 10%, not the easy 90%).
- Choosing settlement decomposition (`net = gross − MDR − GST − refunds − chargebacks`) over a generic bank-to-book join shows domain depth.

### Build Quality — "clean repo, execution reliability, code trust"
- Monorepo with clear package boundaries ([04](04-technical-architecture.md) §9); `make demo` runs the whole thing in one command.
- `pytest` + `hypothesis` property tests; ≥ 85% engine coverage; a determinism test that fails CI if two runs diverge.
- Typed throughout (Pydantic v2 / TypeScript strict).
- CI runs tests + `arbiter bench` on every commit and publishes the scorecard artifact.
- Every architectural decision has an ADR in `docs/adr/`.

### AI Judgment — "use AI where appropriate, deterministic where AI is unnecessary"
- ADR-0001 states the doctrine: deterministic core, AI at exactly one bounded step, every AI output a gated proposal, `--no-ai` mode always works ([04](04-technical-architecture.md) §3).
- The scorecard **measures the AI's lift** — category accuracy with vs. without the LLM. If the AI doesn't earn its place, the number will say so and we cut it.
- Money math, matching, scoring, and replay contain zero LLM calls, by design and by test.

### Failure Recovery — "show what broke and how you resolved it"
- The exception ledger _is_ a failure-recovery system: every unresolved item is categorized, quantified, explained, and given a proposed fix + a rule that prevents recurrence.
- `docs/BUILD-LOG.md` — a running, honest log of what broke during development and how it was fixed (kept from day one, not reconstructed at the end).
- Deterministic replay + the regression gate = the engineering answer to "how do you recover when accuracy regresses."
- The demo script deliberately shows an `UNEXPLAINED` exception Arbiter could not resolve, and narrates what it's missing.

---

## 3. Milestones

Assumes a solo builder, ~3 focused weeks. Adjust week lengths to your actual runway; the _order_ is the important part.

### M0 — Skeleton & data (days 1–3)
- Monorepo scaffold (uv workspace, pnpm, Makefile, docker-compose, CI stub).
- `datagen`: generate `razorpay_settlement.csv` + `bank.csv` + `ledger.csv` + `ground_truth.json` for a clean batch (no anomalies yet), seeded.
- Event store: append-only table, hash chain, fold, `arbiter replay` stub.
- Canonical `Record` model + CSV ingest with declared column mapping.
- `arbiter run` runs, ingests, emits `RECORD_INGESTED` events, prints record counts.
- **Exit:** `make demo` ingests a 200-record batch deterministically; `arbiter replay` reproduces it.

### M1 — Deterministic matcher + benchmark (days 4–8)
- Recon spec loader + validator + safe rule-expression AST.
- Matching pass 1 (exact) + pass 2 (tolerant) + confidence formula.
- Settlement decomposition + residual computation.
- Exception taxonomy + deterministic classifier (spec rules).
- `datagen`: add the 12 labeled anomaly types with a difficulty dial.
- `arbiter bench`: full scorecard (matching metrics, $ coverage, throughput, exception histogram) vs `ground_truth.json`.
- CI: run bench, upload `scorecard.json` + HTML, comment metrics on PR.
- **Exit:** honest scorecard on an adversarial batch; `--no-ai` is the only mode so far; determinism test green.

### M2 — Hard matching + exception ranking (days 9–12)
- Pass 3 (set/subset with bounded subset-sum) — the differentiating pass.
- Pass 4 (fuzzy candidate scoring) + candidate attachment to exceptions.
- $-impact ranking; exception grouping/dedup.
- Decomposition D5 (over/undercharge detection).
- Tune the deterministic core; record the `--no-ai` baseline numbers.
- **Exit:** deterministic core hits its target auto-match rate on the adversarial batch; baseline scorecard committed.

### M3 — The one AI step (days 13–16)
- Adjudication agent: Anthropic SDK, `claude-opus-5`, adaptive thinking, the 4-tool read-only surface, strict `Proposal` structured output, frozen+hashed prompt.
- Wire it to `AMBIGUOUS` / `UNEXPLAINED` exceptions only; per-exception budget + accounting.
- Batch-API path for `bench`.
- Scorecard: add category accuracy, resolution usefulness, **AI lift** (vs the M2 baseline), cost/tokens.
- **Exit:** measured AI lift number exists; `arbiter run` (with AI) and `--no-ai` both green; cost < $0.05/exception.

### M4 — Cockpit (days 14–19, overlaps M3)
- Next.js app, three surfaces: scorecard, exception queue (keyboard-first grid), evidence drawer.
- Evidence drawer is the polished piece: 3 record cards, the identity equation, rule trail, AI proposal with clickable evidence refs, decision controls.
- FastAPI endpoints behind it.
- Light/dark parity, WCAG AA, reduced-motion.
- **Exit:** a judge can triage the demo batch entirely in the cockpit.

### M5 — Learning loop, polish, submission (days 19–21)
- Resolution → rule synthesis → spec-diff review → re-run shows the number move.
- Cycle demo: 3 monthly batches, rules carried forward, 85→93→97 curve on screen.
- Starter rule packs.
- `arbiter explain` (evidence drawer as text).
- README, `BUILD-LOG.md` finalized, 5-min pitch video, architecture doc pass.
- Audit-pack export.
- **Exit:** all 7 success criteria from [02](02-product-spec.md) §7 pass from a clean checkout.

---

## 4. What ships in each priority band (from [06](06-feature-inventory.md))

- **P0 (must):** A1–A5, A7, B1–B4, B6, C1–C8, D1–D3, E1–E6, F1–F5, F7–F9, G1, G5, H1–H4, I1–I6, J1–J4, K1–K3, K6, L1–L4.
- **P1 (if time):** A6, B5, D4–D5, F6, F10, G2–G4, H5, I7, J5–J6, K4–K5, K7, L5.
- **P2 (post):** all of section M.

If time runs short, cut P1 features before compromising any P0 — especially do not compromise `arbiter bench`, the determinism test, or the evidence drawer.

---

## 5. Scope discipline (what we are NOT building, and saying so)

Stated in [02](02-product-spec.md) §6 and [06](06-feature-inventory.md) §M. The README will contain an explicit "Non-goals for this version" section. Reviewers read deliberate, defended scope boundaries as a maturity signal; they read silent gaps as oversights.

---

## 6. Risks to the plan itself

| Risk | Mitigation |
|---|---|
| Subset-sum pass eats a week | Timebox to 2 days; ship meet-in-the-middle ≤40 + greedy fallback; ILP is P2 |
| Cockpit scope creep | The three surfaces only; evidence drawer polished, rest competent; it's 40% of effort ([09](09-open-strategic-questions.md) Q9) |
| AI lift turns out small | That's a _finding_, not a failure — report it, ship the deterministic core as the headline, keep AI as opt-in |
| Synthetic data feels fake to judges | Difficulty dial + realistic scenario presets + disclose the asterisk + attempt one real dataset ([09](09-open-strategic-questions.md) Q5) |
| Time overrun | M1 (deterministic core + bench) alone is a legitimate submission. Everything after is upside. Protect M1. |

---

## 7. Definition of done (the submission checklist)

- [ ] `git clone && make demo` → cockpit open with a real scorecard in < 3 min
- [ ] `arbiter bench` → precision / recall / **false-match rate** / $ coverage / throughput / cost, reproducibly
- [ ] `arbiter run --no-ai` → works; scorecard shows the deterministic baseline
- [ ] AI lift is measured and stated (a real number, whatever it is)
- [ ] `arbiter replay <id>` → byte-identical
- [ ] CI green: tests, coverage gate, determinism test, regression gate, scorecard artifact
- [ ] Cycle demo shows the auto-match rate rising across 3 batches
- [ ] Evidence drawer: every number traceable to source in ≤ 2 clicks
- [ ] `docs/` complete; every non-trivial decision has an ADR
- [ ] `BUILD-LOG.md` — honest account of what broke and how it was fixed
- [ ] README: what it is, why, quickstart, non-goals, the honest limitations
- [ ] 5-minute pitch video: problem → demo (including one unresolved exception) → the benchmark → the architecture doctrine
- [ ] Public repo, clean history, LICENSE (Apache-2.0 for the open-core engine)
