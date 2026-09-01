# 23 — Risk Register

_Build and delivery risks for the Buildathon (distinct from [doc 08](08-why-it-might-not-sell.md), which is commercial risk). Each has an owner-action, a trigger to watch, and a contingency._

Likelihood / Impact: L / M / H. **Exposure** = L×I.

---

## Technical

| ID | Risk | L | I | Exp | Mitigation (do now) | Trigger (watch for) | Contingency |
|---|---|---|---|---|---|---|---|
| T1 | Subset-sum pass is slow / hangs on a pathological batch | M | H | H | Op-count budget not wall-clock ([doc 16 §9](16-matching-engine-deep-dive.md)); block by `settlement_utr` first; cap candidate set | a `bench` run > 30s | Ship meet-in-the-middle ≤25 + greedy only; mark heuristic matches; ILP is post-hackathon |
| T2 | m/u estimation (Fellegi-Sunter) is fiddly / unstable | M | M | M | Seed from domain priors; estimate from labeled `ground_truth` (not EM guesswork); freeze the table per run | matcher ECE > 0.1 or wild weights | Fall back to a hand-weighted linear score; FS is an enhancement, not load-bearing |
| T3 | Agent lift turns out small (< 5 pts) | M | M | M | Measure early (M3); the deterministic core is the headline anyway | `bench` AI-lift < 5 pts after tuning | Report it honestly as a finding; ship agent as opt-in; lean the pitch on the deterministic core + benchmark |
| T4 | Agent is miscalibrated / over-confident | M | M | M | Calibration study built into `bench`; isotonic recalibration | ECE > 0.05 | Recalibrate + disclose; if still bad, hide numeric confidence, show coarse bands |
| T5 | Determinism breaks (flaky hashes) | L | H | M | Sorted iteration everywhere; integer paise; determinism + resume tests in CI from day one | CI determinism test fails | Bisect via the event log; the test catching it *is* the recovery story for the BUILD-LOG |
| T6 | Prompt injection defense has a hole | L | H | M | Proposal-only tools make money-safety independent of it ([doc 14 C3](14-security-and-trust.md)); scanner + fencing + one injected note in the demo | red-team finds a bypass | Document it in KNOWN-FAILURE-MODES; the backstop (C3) still holds |
| T7 | Anthropic API rate limits / outage during the demo | L | H | M | Recorded `AGENT_INTERACTION`s → `arbiter replay` runs the demo offline; `--no-ai` always works | 429s in rehearsal | Demo from a replayed run; show a live `--no-ai` run + a pre-recorded agent run |
| T8 | Real Razorpay/bank formats differ from assumptions | M | M | M | Build against the documented `fetch-recon` schema; three parser profiles; get one real export early | a real file won't parse | The declared column-map design means it's a YAML fix, not code; show that as a feature |

## Scope & schedule

| ID | Risk | L | I | Exp | Mitigation | Trigger | Contingency |
|---|---|---|---|---|---|---|---|
| S1 | Cockpit scope creep eats engine time | H | M | H | 60/40 split is a hard rule ([doc 09 Q9](09-open-strategic-questions.md)); 3 surfaces only; evidence drawer is the one polished piece | > 40% of days on UI | Ship the queue + drawer read-mostly; the CLI + `bench` carry the demo |
| S2 | Too many docs, not enough code | M | M | M | Docs are done; from here it's M0→M5 code | day X with no runnable `arbiter run` | Freeze docs; the doc set is already a differentiator, stop polishing it |
| S3 | Time overrun; incomplete at submission | M | H | H | M1 (deterministic core + matching bench) alone is a legitimate submission; everything after is upside | behind at the M2/M3 boundary | Submit at the last green milestone; a working M2 + great docs beats a half-broken M5 |
| S4 | The learning-loop cycle demo doesn't show a clean rising curve | M | M | M | `datagen --cycles 3` designed so rules meaningfully help; tune the anomaly persistence | curve is flat/noisy | Show 2 cycles; or show it as "projected" with the mechanism, honestly labeled |
| S5 | 5-min pitch video runs long / buries the lede | M | M | M | Script it ([doc 24](24-demo-and-pitch.md)); rehearse to 4:30; lead with the benchmark | first cut > 6 min | Cut to: problem (30s) → run + rising curve (2m) → one escalation (45s) → the benchmark (1m) → doctrine (30s) |

## External / judging

| ID | Risk | L | I | Exp | Mitigation | Contingency |
|---|---|---|---|---|---|---|
| E1 | Judges read "one LLM call" as "not really an agent" | L (post doc 11/12) | H | M | The hybrid-orchestration reframe + the visible investigation loop + agent scorecard ([ADR-0004](adr/0004-hybrid-orchestration.md)) | The pitch explicitly narrates the loop: plan → evidence → hypothesis → conclude/escalate |
| E2 | Judges see synthetic data and discount the numbers | M | M | M | Adversarial catalog from cited real failure modes; `--difficulty` shows degradation; disclose the asterisk; attempt a real dataset | Show the `--no-ai` baseline + the honest false-match rate; offer to run their data |
| E3 | A competitor's demo is flashier | M | L | L | Arbiter's separation is rigor + honesty, not flash; the calm UI is deliberate ([doc 05](05-design-doctrine.md)) | Let the reproducible benchmark + the audit trail do the talking |
| E4 | Panel asks a deep accounting question | L | M | L | [doc 15](15-domain-model-reconciliation.md) covers the treatment; know the settlement identity cold | "Here's the journal-entry mapping in the Close Memo" |

---

## Top 5 by exposure (where attention goes)

1. **S1 / S3** — scope & schedule. Protect the engine; M1 is a valid submission; branch to "submit at last green milestone" early if behind.
2. **T1** — subset-sum. Timebox hard; heuristic is acceptable and flagged.
3. **T3** — agent lift. Measure in M3, not M5; a small number is a finding to report, not a crisis.
4. **T7** — API availability at demo time. The replay path makes the demo outage-proof.
5. **E1** — the "is it an agent" perception. Already structurally addressed; the pitch must narrate the loop.
