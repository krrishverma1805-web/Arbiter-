# ADR-0005 — Fellegi–Sunter probabilistic matching with domain-seeded m/u

- **Status:** Accepted
- **Date:** 2026-09-02

## Context

The tolerant matching pass ([doc 16](../16-matching-engine-deep-dive.md)) needs to score record pairs that don't match on an exact key. Options: hand-tuned weighted scores, a trained classifier, or the classical Fellegi–Sunter (FS) probabilistic record-linkage model. The confidence the pass emits must be **calibrated** (the low-confidence tier and the human's trust depend on it) and **explainable** (an auditor asks "how sure, and why").

## Decision

Use the **Fellegi–Sunter model**: per-field agreement *levels*, each with an m-probability (agreement rate among true matches) and u-probability (agreement rate among non-matches); match weight = Σ log2(m/u); decision thresholds derived from the block's prior P(match) and the spec's `θ_auto`/`θ_review`.

m/u values are:
1. **seeded** from domain priors (e.g. u for "amount exact" ≈ 1/|distinct amounts in block|),
2. **estimated** from the labeled synthetic data (direct counting against `ground_truth.json`, or EM), and
3. **frozen** into the spec version's artifact (`spec_versions.mu_table`) so a run is reproducible.

Reported `confidence` is the **calibrated** posterior P(match), not the raw weight; calibration (ECE, isotonic recalibration) is verified in `arbiter bench` exactly as for the agent.

## Consequences

**Positive:**
- Principled, well-documented method (Fellegi & Sunter 1969; Linacre's expositions) — easy to defend to a panel.
- Per-field weight contributions are naturally explainable ("amount within ₹1: +6.2 bits") and shown in the evidence drawer.
- Having a *labeled* synthetic dataset means we estimate real m/u instead of guessing — a genuine advantage of shipping `datagen`.
- Thresholds fall out of probability, not vibes.

**Negative:**
- FS assumes conditional independence of fields given match status — not strictly true (amount and reference correlate). Mitigation: keep the field set small and roughly independent; the calibration step catches systematic over/under-confidence.
- m/u estimation adds a step. Mitigation: it's bounded, seeded, and frozen per run; if it misbehaves (T2 in [doc 23](../23-risk-register.md)) we fall back to a hand-weighted linear score — FS is an enhancement, not load-bearing.

## Alternatives considered

- **Hand-tuned weights:** simplest, but not calibrated, hard to defend, brittle across datasets.
- **Trained classifier (e.g. gradient-boosted):** better raw accuracy potentially, but a black box, needs more training data than a hackathon has, and undermines the "explainable, deterministic" story.
- **An off-the-shelf ER library (Splink, dedupe, Zingg):** viable, but pulling a heavy dependency for the core matching logic reduces inspectability and the "we built the engine" signal; the FS math is ~200 lines and worth owning.
