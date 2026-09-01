# 16 — Matching Engine Deep Dive

_The algorithms, the math, and the engineering of the deterministic matcher. This is the ~60% of the build that carries the "senior engineer" signal._

---

## 1. Problem statement

Given record sets `L` (processor), `B` (bank), `G` (ledger), produce a set of **match groups** — each an `(l_subset, b_subset, g_subset)` that represents the same money — with a calibrated confidence, and leave everything else as typed exceptions. Matches can be 1:1, 1:N, N:1, or N:M. The assignment must be **deterministic**, **explainable** (every match cites its evidence), and **fast** (≥ 500 rec/s).

This is a constrained **entity resolution** problem ([Binette & Steorts, "(Almost) All of Entity Resolution"](https://arxiv.org/pdf/2008.04443)) with a domain-specific twist: the "same entity" relation is mediated by the settlement identity (§[15.2](15-domain-model-reconciliation.md)), not just field similarity.

---

## 2. Pipeline

```
        blocking            scoring              assignment           decomposition
records ────────▶ candidate ────────▶ scored ─────────────▶ match ──────────────▶ verified
                  pairs/sets          pairs/sets  (greedy + constraints)  groups   (identity)
                                                        │
                                                        └──▶ unmatched ──▶ classify (doc 15)
```

Four passes (exact → tolerant → subset → fuzzy) are **scoring+assignment strategies** applied in sequence over the not-yet-matched remainder. Blocking and decomposition wrap all of them.

---

## 3. Blocking (making it tractable)

Comparing every `L×B×G` triple is `O(n³)` — impossible. Blocking restricts comparisons to plausible candidates ([Murray, "Blocking in Fellegi-Sunter"](http://www2.stat.duke.edu/~rcs46/linkage_readings/2015-Murray-Blocking-FellegiSunter.pdf)).

**Block keys, in priority order:**
1. `settlement_utr` ↔ `extract_utr(bank.narration)` — exact, the strong key
2. `settlement_id` (groups L items into batches before touching B)
3. `payment_id` / `order_id` (L ↔ G)
4. rounded-amount bucket + date-window bucket (`floor(amount/100)`, ISO week) — the fallback block for fuzzy
5. counterparty soundex (last resort, fuzzy only)

Each record lands in ≥1 block. Passes only compare within a block. Blocking recall (fraction of true matches whose members share ≥1 block) is a measured metric — target ≥ 99.5%; a miss here is an unrecoverable false negative, so the amount+date fallback block is deliberately loose.

---

## 4. Pass 1 — Exact

Within a `settlement_utr` block: if `abs(bank.amount − net_for_utr) == 0` and dates align → match, confidence `1.0`, `rule = exact`. `net_for_utr` is the settlement identity evaluated over the block's L items.

No probabilistic machinery needed; this ties the clean majority (typically 80–92% of batches). Cheap, unambiguous, first.

---

## 5. Pass 2 — Tolerant (the Fellegi–Sunter core)

For candidate pairs that share a block but fail exact, compute a **match weight** using the Fellegi–Sunter model ([Fellegi & Sunter 1969](https://academic.oup.com/ije/article/45/3/954/2572621); [Linacre, "The maths of Fellegi-Sunter"](https://www.robinlinacre.com/maths_of_fellegi_sunter/)).

### 5.1 Per-field agreement levels

Each comparison field `f` is compared at **levels** (not just agree/disagree):

| Field | Levels |
|---|---|
| amount | exact · within ₹1 · within ₹10 · within 0.5% · else |
| value_date | same day · ±1 · within settlement window (±4) · else |
| reference (UTR/ref string) | exact · Jaro-Winkler ≥ 0.9 · ≥ 0.7 · else |
| counterparty | exact (norm) · token-set ratio ≥ 0.8 · else |
| shared external id | any of {payment_id, order_id} shared · none |

### 5.2 m and u probabilities

For field `f` at level `k`:
- **m_fk** = P(records agree at level `k` on `f` | the pair is a true match) — "how often matches look like this"
- **u_fk** = P(records agree at level `k` on `f` | the pair is a non-match) — "how often coincidences look like this"

([Linacre, "m and u values"](https://www.robinlinacre.com/m_and_u_values/).) Sources for our values:
1. **Seed from domain priors** (e.g. `u` for "amount exact" ≈ 1/(distinct amounts in the block) — coincidental exact-amount agreement is rare; `m` for "same day" ≈ 0.6 because T+2 spread).
2. **Estimate from the labeled synthetic data** via EM / direct counting against `ground_truth.json` — `datagen` gives us true labels, so we can compute empirical m/u instead of guessing. This is a real advantage of shipping the generator.
3. **Re-estimate per customer** post-hackathon (their data, their patterns) — the spec stores the m/u table so it's tunable without code.

### 5.3 The weight

```
match_weight(pair) = Σ_f  log2( m_{f,k(f)} / u_{f,k(f)} )        # k(f) = observed level for field f
```

Positive contribution when a level is more common among matches than non-matches; negative when it's a coincidence pattern. The **partial match weight** per field is logged and shown in the evidence drawer ("amount within ₹1: +6.2 bits; date ±3 days: −1.1 bits; ref Jaro 0.72: +0.4 bits").

### 5.4 Decision

```
weight ≥ T_match   → match      (T_match ⇒ posterior P(match) ≥ θ_auto, default 0.90)
T_review ≤ w < T_match → low-confidence match (surfaced for spot-check, counted separately)
weight < T_review  → not a match here → falls through to pass 3/4 or becomes an exception
```

`T_match` and `T_review` are derived from `θ_auto`/`θ_review` in the spec plus the block's prior `P(match)` (≈ 1/block-size), so thresholds are principled, not hand-tuned:
```
posterior_odds = prior_odds × 2^weight ;  P(match) = odds / (1+odds)
```

### 5.5 Reported confidence

The Match's `confidence` = calibrated `P(match)` from §5.4, **not** the raw weight. Calibration is verified the same way as the agent's ([doc 12 §6.2](12-agent-design.md)): bucket matches by predicted `P(match)`, compare to observed accuracy on ground truth, report ECE, apply isotonic recalibration if needed. **A miscalibrated matcher confidence is a bug** — it's the number the low-confidence tier and the human's trust depend on.

---

## 6. Pass 3 — Subset / set matching (the hard, differentiating pass)

**Problem:** a bank credit `C` must equal the settlement identity over *some subset* `S ⊆ L_block` of not-yet-matched processor items (and, via the cross-check, some subset of ledger orders).

Formally: find `S` such that
```
| C − ( Σ_{i∈S} credit_i − Σ_{i∈S} debit_i − Σ_{i∈S} fee_i − Σ_{i∈S} tax_i ) | ≤ tol
```

This is **subset-sum with tolerance** — NP-hard in general, tractable here because blocks are small.

### 6.1 Algorithm

| |S_candidates| | Method | Complexity |
|---|---|---|---|
| ≤ 25 | exact meet-in-the-middle: split candidates, enumerate `2^(n/2)` partial sums each side, sort one, binary-search the complement for each | `O(2^(n/2) · n)` |
| 26–40 | meet-in-the-middle with pruning (branch-and-bound on running sum vs `C`) | practical to ~40 |
| > 40 | **greedy + local search**: sort by amount desc, greedily add while sum ≤ C, then hill-climb (swap pairs) to close the gap; bounded by `wallclock_budget_ms` | anytime |

In practice, `settlement_utr` blocking makes `|S_candidates|` the size of one payout batch (typically 20–150) — but items already tied in passes 1–2 are removed first, so the *residual* to solve is usually < 25. The heuristic path is the safety net, and when it's used the match is flagged (`method = subset_heuristic`) and gets a confidence penalty.

### 6.2 Uniqueness

- **Exactly one** subset within tolerance → `subset` match; confidence from the identity residual (0 residual ⇒ high; near-tolerance ⇒ lower).
- **Multiple** subsets within tolerance → **exception `AMBIGUOUS`**, all candidate subsets attached; the agent or a human picks. (Common with many equal-amount small orders — genuinely ambiguous, correctly surfaced rather than guessed.)
- **No** subset within tolerance → `PARTIAL_PAYMENT` / `SHORT_SETTLEMENT` / `UNEXPLAINED` per §[15.3](15-domain-model-reconciliation.md).

### 6.3 Post-hackathon

Replace §6.1 with an ILP (`net == C` as an equality with slack variables, minimize slack; OR-Tools CP-SAT) behind the same interface. The heuristic is sufficient at demo scale ([doc 04 §11](04-technical-architecture.md)).

---

## 7. Pass 4 — Fuzzy candidates (never an auto-match)

For records still unmatched (orphan bank credits, missing-UTR lines), compute the FS weight against *all* records in the loose amount+date block, rank, and attach the **top 3 candidates with their per-field weight breakdown** to the exception. This is the "starting hypothesis" the human/agent gets instead of a blank. Emitted as `candidates`, never as a `Match`.

---

## 8. Assignment (resolving conflicts)

Passes produce candidate matches; a record must not be in two conflicting matches. Assignment:

1. Take matches in confidence order (desc), then by a deterministic tiebreak (`sorted(record_ids)`).
2. Greedily accept a match if none of its records is already claimed by an accepted match.
3. A rejected higher-level match's records remain available for lower passes.
4. **Transitive closure:** if `l1~b1` and `b1~g1` and `l1~g1` are all accepted and consistent, they merge into one match group. Inconsistent triangles (`l1~b1`, `b1~g1`, but `l1≁g1`) → the weakest edge is dropped and the group flagged for review.

Greedy (not global optimal assignment / Hungarian) is deliberate: it's deterministic, `O(n log n)`, explainable ("we took the highest-confidence match first"), and at these block sizes the optimal-vs-greedy gap is negligible. Global assignment is a documented post-hackathon option if the eval shows greedy losing matches.

---

## 9. Determinism guarantees

| Source of nondeterminism | How it's removed |
|---|---|
| dict / set iteration order | all iteration over `sorted(by Record.id)`; no reliance on insertion order |
| floating point | integer paise throughout; FS weights use `Decimal`-backed `log2` computed once and cached; no float sums in the identity |
| wall-clock in logic | `settled_at`/`value_date` are data; "now" never enters a decision; the subset heuristic's time budget is measured in **operations**, not seconds, when `--deterministic` is set |
| parallelism | passes are sequential; within a pass, per-block work is independent and results are merged in block-id order |
| m/u estimation | EM is seeded and run to a fixed iteration count / tolerance; the resulting table is committed as part of the spec artifact for a run |

CI test: `arbiter run` twice on the same input → identical event hash chain (the deterministic phase).

---

## 10. Complexity & performance budget

| Phase | Complexity | 800 records | 5,000 records |
|---|---|---|---|
| Ingest + normalize | `O(n)` | ~50 ms | ~300 ms |
| Blocking | `O(n log n)` | ~20 ms | ~150 ms |
| Pass 1 exact | `O(Σ block)` | ~10 ms | ~60 ms |
| Pass 2 FS | `O(Σ block² )` bounded by block size cap | ~120 ms | ~900 ms |
| Pass 3 subset | `O(batches · 2^(residual/2))`, residual small | ~200 ms | ~1.5 s |
| Pass 4 fuzzy | `O(exceptions · loose_block)` | ~40 ms | ~250 ms |
| Decompose + classify + score | `O(n)` | ~30 ms | ~200 ms |
| **Total (deterministic phase)** | | **< 0.6 s** | **< 4 s** |

Target: ≥ 500 rec/s. Polars for the vectorizable parts (blocking, exact, amount comparisons); pure Python only for the subset search.

---

## 11. What we test

- **Property (hypothesis):** for any generated batch, every `subset` match's identity residual ≤ tolerance.
- **Property:** no record appears in two accepted matches.
- **Property:** `matched_count + exception_record_count + low_confidence_count == total_records` (nothing lost).
- **Golden files:** committed batches with committed expected match groups; diff on change.
- **Calibration:** matcher ECE ≤ 0.05 on the held-out split.
- **Blocking recall:** ≥ 99.5% on ground truth.
- **Determinism:** identical hashes across two runs; identical across `--resume` from every state boundary.
- **Adversarial:** the 12 anomaly types each produce their expected exception category ≥ 85% of the time.
