# 05 — Design Doctrine

_The principles, the interface model, the visual system, and the interaction rules for Arbiter's cockpit. Every screen is derived from this document._

---

## 1. Design thesis

Reconciliation software is almost universally ugly, dense in the wrong places, and built for viewing rather than working. BlackLine looks like 2008. GST tools look like tax forms. Spreadsheets have no state.

**Arbiter's cockpit is designed as a triage instrument, not a report.** The controller arrives with a question — _"is the money right, and if not, what do I do?"_ — and leaves with an answer and a shrunk to-do list. The interface's only job is to move them through that as fast as trust allows.

Three words govern every decision: **Calm. Legible. Fast.**

- **Calm** — finance work happens under deadline stress. The UI never adds urgency it doesn't have. Muted ground, one accent, generous spacing, no notification confetti, no dark patterns.
- **Legible** — every number traceable to its source in ≤ 2 clicks; every status word from a fixed vocabulary; nothing hidden behind hover.
- **Fast** — the exception queue is keyboard-first. A power user clears 40 exceptions without touching the mouse.

---

## 2. The interface model — "one run, three surfaces"

A reconciliation **run** is the atomic unit. Everything is scoped to a run. Three surfaces, in workflow order:

```
┌───────────────────────────────────────────────────────────────────────┐
│  RUN HEADER   razorpay-settlement · Aug 2026 · 214 records · 2m ago    │
│  ● 97.2% auto-tied   ₹41,900 across 6 exceptions   ⟳ re-run   ⤓ export │
└───────────────────────────────────────────────────────────────────────┘

  ①  SCORECARD            ②  EXCEPTION QUEUE            ③  EVIDENCE DRAWER
  the verdict             the work                      the proof
  ───────────             ─────────────                 ─────────────
  match rate + trend      ranked list of the 6          for the selected item:
  $ tied / $ open         each: type · ₹ · confidence   3 source records side-by-side
  precision/recall        one-line AI hypothesis        the identity math
  exceptions by type      [resolve ▸] inline            the rule trail
  cycle-over-cycle        keyboard j/k to move          the AI proposal + evidence refs
                                                        [accept] [edit] [reject]
```

### 2.1 Surface ① — Scorecard (the verdict)

Answers "is the money right?" in one glance. Contents, in priority order:

1. **The headline number** — auto-tied %, big, with the $ tied vs $ open beneath it. Color is _informational_, never alarmist: a neutral slate for the number, a single amber dot if open exceptions exist.
2. **Coverage bar** — a single horizontal stacked bar: `auto-tied | low-confidence | exception`, by _rupees_ not count (₹ is what the controller is accountable for).
3. **Accuracy panel** (when ground truth is present, i.e. bench/demo) — precision, recall, false-match rate, as a small labeled trio. Honest by construction.
4. **Exceptions by type** — a horizontal bar list, sorted by ₹ impact.
5. **Cycle trend** — a sparkline of auto-tied % over the last N runs of this spec. This is the "it gets better" story; it earns the most vertical space after the headline.

Charts follow the `dataviz` skill: one categorical palette, same in light/dark, direct labels over legends, no chartjunk.

### 2.2 Surface ② — Exception Queue (the work)

The core screen. A dense, keyboard-driven grid. One row per exception.

| Column | Content | Notes |
|---|---|---|
| ▸ | expand to evidence drawer inline | `Enter` / click |
| Type | `TIMING`, `DUPLICATE`, … | colored chip, fixed vocabulary, colorblind-safe |
| Impact | ₹ at stake, right-aligned, signed | primary sort |
| Confidence | Arbiter's confidence in its own hypothesis | bar, not number-noise |
| Hypothesis | one line: _"Bank credit ₹8,240 has no settlement — likely T+2 into September; matches 3 Aug orders"_ | from rule or AI |
| Source | which records (razorpay / bank / ledger badges) | |
| Status | `open` · `proposed` · `resolved` · `won't-fix` · `budget-exceeded` | |
| Action | `resolve ▸` | opens the resolution control |

**Interactions:**
- `j` / `k` move; `x` select; `e` expand; `a` accept AI proposal; `r` reject; `w` won't-fix; `/` filter; `g` group-by-type.
- Bulk: select several `ROUNDING` exceptions → `a` → accept all → one "draft a rule for this?" prompt.
- Every resolution shows, immediately and inline, the consequence: _"Rule `r_timing_sept` drafted · re-run to apply · projected auto-tied 97.2% → 98.6%"_.

### 2.3 Surface ③ — Evidence Drawer (the proof)

Opens beside a selected exception (never a modal — you keep the queue in view). Top to bottom:

1. **Three record cards, side by side** — Razorpay settlement line, bank credit, ledger order(s). Matching fields aligned on the same rows; differing fields highlighted with a thin left border in the accent. The raw row is one click away.
2. **The identity** — the decomposition rendered as an equation with real numbers, the residual called out: `₹8,240 (ledger) − ₹165 (MDR) − ₹29.70 (GST) = ₹8,045.30 expected · ₹8,240 received · Δ ₹194.70`.
3. **Rule trail** — which passes ran, which rule fired, why it didn't auto-match. Plain sentences.
4. **AI proposal** (if any) — clearly badged _"proposed by Arbiter · claude-opus-5"_. The explanation, each factual claim linked to an evidence id (click → highlights that field in the record cards above). The suggested action. The draft rule, as a diff.
5. **Decision controls** — `Accept` · `Edit & accept` · `Reject` · `Won't fix`. Reject asks for a one-word reason (feeds a future eval).

**The drawer is the trust surface.** If a skeptical controller or auditor is going to be won over, it happens here: everything the machine believes, why, and the ability to overrule it in one keystroke.

---

## 3. Visual system

### 3.1 Foundations

| Token | Light | Dark | Use |
|---|---|---|---|
| `--bg` | `#FAFAF9` (warm off-white) | `#0E0F11` | page ground |
| `--surface` | `#FFFFFF` | `#17181B` | cards, drawer |
| `--border` | `#E7E5E4` | `#2A2C30` | hairlines only, 1px |
| `--text` | `#1C1917` | `#EDEDED` | |
| `--text-muted` | `#78716C` | `#9BA1A6` | secondary |
| `--accent` | `#3B5BDB` (a serious indigo-blue) | `#5C7CFA` | one accent, used sparingly: focus, links, selected row |
| `--positive` | `#2F9E44` | `#51CF66` | tied / resolved |
| `--attention` | `#E8A33D` | `#F0B849` | open exception (never red — nothing here is an error, it's just unfinished) |
| `--critical` | `#E03131` | `#FF6B6B` | reserved for false-match / identity broken only |

Rationale: warm neutral ground (less clinical than pure gray), exactly one accent so the eye always knows where "the action" is, amber-not-red for exceptions because framing matters — an unreconciled item is _work_, not a _failure_.

### 3.2 Type

- **UI:** Inter (or the system stack as fallback). 14px base, 13px in the grid.
- **Numbers:** a tabular-figures font feature everywhere money appears — columns of rupees must align on the decimal. `font-variant-numeric: tabular-nums`.
- **Mono:** JetBrains Mono / ui-monospace for ids, hashes, the identity equation, rule expressions.
- Scale is tight: 12 / 13 / 14 / 16 / 20 / 28. One display size (28) for the scorecard headline; nothing bigger.

### 3.3 Density & rhythm

- 8px base spacing grid. Grid rows 32px. Drawer padding 20px.
- The queue shows ~20 rows without scrolling on a laptop. Density is a feature — the controller wants to see the whole problem at once.
- Whitespace is spent on the scorecard and drawer (where thinking happens), conserved in the queue (where scanning happens).

### 3.4 Motion

- Almost none. 120ms ease for drawer open, row select, filter. No spring, no bounce, no skeleton shimmer theatrics.
- The _only_ celebratory moment: when a re-run pushes auto-tied % up, the headline number counts up over 400ms and the trend sparkline extends. Earned, once per run.

### 3.5 Theme

Full light/dark parity per the Artifacts theming rules — tokens on `:root`, dark under both `@media (prefers-color-scheme: dark)` and `[data-theme="dark"]`. Finance folks work early and late; both themes are first-class.

---

## 4. Content & voice

- **Status vocabulary is closed.** Exactly: `auto-tied`, `low-confidence`, `exception`, `open`, `proposed`, `resolved`, `won't-fix`, `budget-exceeded`. Never synonyms.
- **Numbers always carry units and sign.** `₹8,240.00`, `−₹194.70`. Never bare `8240`.
- **AI text is always attributed and always hedged appropriately.** "Likely…", "Consistent with…", "No evidence for…". Never "This is a duplicate." — always "This matches payment_id `pay_X` on amount, date and counterparty — likely a duplicate."
- **Errors are plain.** "Bank file has 3 rows with no date — fix the file and re-ingest." with the row numbers. No codes.
- **No dark patterns.** No fake urgency, no "12 people are looking at this", no pre-checked "share my data".

---

## 5. Accessibility (non-negotiable)

- WCAG 2.2 AA contrast on every token pair above.
- Every action keyboard-reachable; visible focus ring (2px accent) always.
- Exception type conveyed by **chip label + shape/icon**, never color alone.
- Screen-reader labels on every chart data point; charts have an adjacent data table toggle.
- Respects `prefers-reduced-motion` (kills even the 120ms transitions).
- Minimum 44px hit targets for pointer; grid rows expand hit area to full width.

---

## 6. The CLI is part of the design

Judges and engineers meet Arbiter through the terminal first. The CLI output is designed with the same care:

- `arbiter run` prints a live progress line per pass, then a compact scorecard table (same numbers as surface ①), then the exception list as a clean table, then the one-line "open the cockpit: …".
- Color: same palette, degradeable to no-color (`NO_COLOR`).
- `arbiter explain <exception-id>` prints the evidence drawer as text — the three records, the identity, the rule trail, the AI proposal.
- Every command supports `--json` for machine consumption.

---

## 7. What "next-gen" actually means here

Not 3D, not glassmorphism, not an AI chat bubble bolted onto a table. Next-gen for this product is:

1. **The exception queue feels like a fast email client, not a BI dashboard.** Keyboard triage, inline resolution, visible consequence.
2. **Provenance is always one keystroke away** — the "why" is never a support ticket.
3. **The interface shows its own accuracy** — the scorecard doesn't hide the false-match rate; trust is built by exposure, not concealment.
4. **The learning loop is visible** — you _watch_ the number improve as you work. Software that visibly gets better is rare and memorable.
5. **It's genuinely calm** — in a category defined by stress and ugliness, restraint is the differentiator.
