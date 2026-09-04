# Arbiter Cockpit — UI/UX Audit

_Audit of the current Next.js app (`web/src`) against `docs/05-design-doctrine.md`. Written before the rebuild._

The app has all the right **information** but is a prototype in every other respect: no design system, no loaded typeface, three different page shells, hand-rolled controls, data dumped as text instead of visualized, demo/dev scaffolding leaking into the operator surface, and motion that directly contradicts the doctrine.

---

## 0. Foundations

| # | Flaw | Evidence | Doctrine |
|---|---|---|---|
| F1 | **Inter / JetBrains Mono are never loaded.** Declared in `tailwind.config.ts` but there is no `next/font`, no `<link>`, no `@font-face`. The app renders in the system sans fallback. The marketing `arbiter-walkthrough.html` *does* load them — the real app doesn't. | `layout.tsx` has no font import; `grep next/font` → nothing | §3.2 |
| F2 | **Type scale is off-doctrine.** Doctrine scale is 12/13/14/16/20/28. Code uses `text-[10px]` ×5, `text-[11px]` ×16, plus `xs/sm/lg/xl/2xl/3xl` (10,11,12,14,18,20,24,30). Sub-12px text fails the accessibility floor. | tally in `src/` | §3.2, §5 |
| F3 | **Border radius has no system.** `rounded` (4px) ×67, plus `rounded-md`, `rounded-lg`, `rounded-xl`, `rounded-full`. Cards are 4px in the cockpit, 12px in LiveRun. | tally | §3 |
| F4 | **Spacing is not on the 8px grid.** `py-2.5`, `py-1.5`, `gap-1.5`, `pt-5`, `p-3`, `p-5` everywhere. Doctrine: 8px base, 32px grid rows, 20px drawer padding. | all components | §3.3 |
| F5 | **`globals.css` is missing half the token set** the design intends: no `--surface-2`, no `--shadow`, no on-accent ink token. Buttons hardcode `text-white` on `--accent` (F35). | `globals.css` vs walkthrough `<style>` | §3.1 |
| F6 | **Theme toggle is buried in ⌘K only.** No visible control. "Both themes first-class" but discoverability is zero. `<html>` also lacks `suppressHydrationWarning` despite the pre-paint `data-theme` script. | `CommandPalette.tsx` L39, `layout.tsx` | §3.5 |
| F7 | **No component primitives.** Every button/input/select/card/pill/kbd is inline Tailwind, copy-pasted and slightly different each time. `disabled:opacity-50` on some buttons, not others. Hover language is inconsistent: `hover:border-accent` vs `hover:bg-accent/5` vs `hover:bg-accent/20` vs `hover:text-accent`. | all components | §7 |

---

## 1. Landing page (`app/page.tsx`)

| # | Flaw | Doctrine |
|---|---|---|
| L1 | **Runs list is three `<span>`s in `flex justify-between`.** The middle span ("1,672 records · 900 matches · 40 exceptions") wraps unpredictably and collides with the run id and status. No table, no column headers, no amount alignment across rows, no timestamp, no spec/dataset. Status shown as raw lowercase enum. | §2 (run header wants "razorpay-settlement · Aug 2026 · 214 records · 2m ago") |
| L2 | **`DemoOverview` "assurance" box is a wall of runny text** — 6+ metrics as inline `font-mono` spans inside sentences ("false-match rate 0.0% · ₹ coverage 98% … unsafe auto-resolutions 0 · ₹ protected ₹X · replay identical"). Everything 11–12px. This is the "dense in the wrong places" the doctrine opens by condemning. | §1, §2.1 |
| L3 | **Vocabulary drift.** Landing says "auto-verified", cockpit says "auto-tied", scorecard says "auto-match rate". Doctrine mandates a *closed* status vocabulary. "held for a human" / "auto-verified" / "open exceptions" also mix verb tense. | §4 |
| L4 | **`NewRun` form** is `flex flex-wrap items-end gap-3` of two bare `<select>`s, a checkbox literally labelled `--no-ai`, and a button — CLI implementation leaking into the UI. No card title, no field grouping. | §7 |
| L5 | **"Bring your own API key" is a hand-rolled `▸`/`▾` ASCII disclosure** wrapping another `flex flex-wrap items-end gap-3` of raw inputs. | §7 |
| L6 | **Raw errors shown to users.** `{err && <span>{String(e)}</span>}` renders `Error: 500 /v1/runs`. The API-down notice shows the shell command `uv run arbiter-api`. Doctrine: "Errors are plain. No codes." | §4 |
| L7 | **Three `Stat` cards** with no icon, no weight hierarchy, `text-[11px]` labels. No coverage bar, no visual. | §2.1 |

---

## 2. Cockpit (`components/Cockpit.tsx`) — the core screen

| # | Flaw | Doctrine |
|---|---|---|
| C1 | **The scorecard is a data dump, not a scorecard.** `ScorecardPanel` renders ~25 `label ……… value` text rows (precision, false-match, ₹ coverage, ₹ unexplained, by-pass, exceptions-by-type×N, anomalies, category accuracy, 7 agent rows, 5 safety rows, determinism, throughput). **None of the doctrine's visualizations exist**: no headline+coverage stacked bar (by ₹), no accuracy trio, no exceptions-by-type bar list, no cycle sparkline ("it gets better" story). It's a 320px column of monospace text. | §2.1 |
| C2 | **Left aside stacks three unrelated dense panels** in one scrolling 320px column: Scorecard + Clusters + **AttackPanel**. | §2.1, §3.3 |
| C3 | **"Attack Arbiter / Run the attack suite" lives permanently in the production triage sidebar.** A red-team demo tool in the operator's cockpit. Pure prototype leakage — belongs in a separate demo route. | §1 |
| C4 | **The queue is a headerless borderless `<table>`.** Columns: category, impact, `classified_by`, status. **No `<thead>`** so "rule:timing" / "razorpay-settlement" in column 3 is unexplained. **No confidence column** (doctrine wants a confidence *bar*). **No hypothesis one-liner** — the doctrine's single most important queue element ("Bank credit ₹8,240 has no settlement — likely T+2…") is absent, so every row must be clicked to learn what the problem is. | §2.2, §7.1 |
| C5 | **No filter, search, sort, grouping, or multi-select in the queue.** Rows render in whatever order the API returns. Doctrine wants `/` filter, `g` group-by-type, `x` multi-select, bulk-accept → "draft a rule?". The only navigation aid is the Clusters panel in the sidebar. | §2.2 |
| C6 | **Keyboard model is half-built.** `j/k/e/a/w` only. `Enter` and `e` both toggle the drawer, fighting row activation. No `x`, `r`, `/`, `g`. Hint bar lists 5 keys. Rows are `<tr onClick>` — not individually focusable, no `role`, no `tabindex`. | §2.2, §5 |
| C7 | **Status is colored text, not a chip.** `StatusPill` renders a bare `<span>` with a text color — no background, border, shape, or icon. Category color falls through to `""` for several categories. Doctrine §5: "conveyed by chip label + shape/icon, never colour alone." | §5 |
| C8 | **Evidence drawer is a vertical stack of tinted bordered boxes.** Record cards are `space-y-2` full-width, **not side-by-side** as §2.3 mandates. The decomposition renders **twice** (inside the `<details>` and again at L642). The identity equation ("₹8,240 − ₹165 − ₹29.70 = … Δ ₹194.70") is instead a cramped `flex justify-between` list + a one-line mono string. | §2.3 |
| C9 | **Resolution = 7 bare buttons with raw API enum labels**: `accept_variance`, `carry_forward`, `flag_overcharge`, `raise_dispute`, `request_data`, `route_to_human`, `wont_fix`, wrapped `flex flex-wrap`. No primary action, no "Accept / Edit & accept / Reject / Won't fix", reject asks for no reason, no inline consequence after resolving ("rule drafted · projected 93.8% → higher"). Resolve just silently refreshes the list. | §2.2, §2.3 |
| C10 | **Four stacked agent-reasoning panels** in the 420px column — `WhyNotResolved` (amber tint), `ProposalPanel` (accent tint), `InvestigationChain` (bordered), `agent_trace` `<details>` — each with its own bg tint and lots of `text-[10px]`/`text-[11px]`. Heavy visual noise on the surface the doctrine calls "the trust surface". | §2.3 |
| C11 | **`Presence` / "3 viewing" avatar stack.** Borderline the "12 people are looking at this" dark pattern the doctrine explicitly bans, and a collaboration flourish on a single-operator tool. | §4 |
| C12 | **Header is thin and wrong.** `← runs` + truncated id + presence + "93.8% auto-tied · 40 exceptions". No spec name, no cycle/date, no record count, no re-run, no export — the doctrine's run header (§2) is unmet. | §2 |
| C13 | **Fixed `[320px_1fr_minmax(0,420px)]` grid.** On a 1280px laptop the queue — where scanning happens and density is the feature — gets ~540px squeezed between two heavy panels. Whitespace should be spent on scorecard/drawer and *conserved* in the queue; it's inverted. | §3.3 |
| C14 | **Row click hard-couples three state changes** (`setSel`, `setOpen(true)`, `setTab("evidence")`), so selection and drawer visibility can't move independently. | — |

---

## 3. LiveRun (`components/LiveRun.tsx`)

| # | Flaw | Doctrine |
|---|---|---|
| R1 | **Motion directly violates the doctrine.** §3.4: "Almost none. 120ms ease… No spring, no bounce, no skeleton shimmer theatrics." LiveRun is spring-animated end to end: `stiffness: 380/420`, `layout` animations on every card, `AnimatePresence` + x:−8 slide on every turn `<li>`, opacity fades on every sub-panel. Cockpit has a spring `layoutId="row-cursor"` too. | §3.4 |
| R2 | **A third page shell.** `max-w-3xl` centered column — different from the landing (also `max-w-3xl` but different header) and the cockpit (full-bleed grid). No shared `AppShell`/header/nav anywhere in the app. | §7 |
| R3 | **`PhaseRail` shows raw lowercase phase strings** — `ingesting matching classifying investigating done` — with "done" as a visible step label. | §4 |
| R4 | **The UI parses raw LLM JSON client-side** (`readJsonTurn`, `stripFences` strips ` ```json ` fences). Fragile; on parse failure it dumps blobs. | — |
| R5 | **Investigation cards** stack proposal/verifier/decision/escalation as `border-t` tinted sections — same noise as C10. `rounded-xl` here vs `rounded` elsewhere (F3). | §2.3, §3 |
| R6 | **Jargon:** "Run complete — chain sealed." | §4 |
| R7 | **`text-white` hardcoded on the accent button** (L385). No `--accent-ink` token; dark-mode accent `#5C7CFA` + white is below the intended contrast. | §3.1, §5 |

---

## 4. Systemic

- **No shared layout.** Three shells, three headers, no persistent nav, no breadcrumb, no "which run am I in" affordance beyond a truncated hash.
- **No feedback system.** No toasts, no optimistic UI, no confirmation, no undo on resolve.
- **Empty/loading states are bare strings** — "loading evidence…", "select an exception", "no scorecard".
- **Accessibility gaps:** non-focusable table rows, snake_case button text, missing `aria-label`s, sub-12px text, no reduced-motion path for the springs (only `useReducedMotion` swaps to `duration:0` — the `layout` reflows still fire).
- **Demo & dev leakage in the product surface:** AttackPanel, presence, `uv run arbiter-api`, raw error strings, `--no-ai` checkbox, BYO-key raw form.

---

## 5. What the rebuild must deliver (from the doctrine)

1. **A design system** — tokens (full set incl. `--surface-2`, `--shadow`, `--accent-ink`), loaded Inter + JetBrains Mono, an 8px spacing scale, one radius scale, a primitive kit (Button, Input, Select, Card, Chip/Badge, Kbd, Table, Sheet/Drawer, Toast, Tooltip).
2. **One `AppShell`** — persistent header with the real run context (spec · cycle · records · timestamp · re-run · export), theme toggle, ⌘K.
3. **Scorecard as visualization** — 28px headline %, a single ₹-weighted stacked coverage bar, an accuracy trio, an exceptions-by-type bar list, a cycle sparkline. (Follow the `dataviz` skill.)
4. **Queue as a fast email client** — real column headers, a confidence bar, the AI hypothesis one-liner per row, `/` filter, `g` group, `x` multi-select, bulk resolve, full keyboard model, focusable rows, chip statuses with shape+label.
5. **Evidence drawer** — three record cards *side by side* with aligned/highlighted fields, the identity as a real equation, a plain rule trail, one attributed AI proposal with clickable evidence refs, and `Accept / Edit & accept / Reject / Won't fix` with an inline consequence line.
6. **Motion budget** — 120ms ease on drawer/select/filter only. One earned count-up when auto-tied % rises. Delete the springs.
7. **Move AttackPanel + presence** out of the operator cockpit into a separate `/demo` surface.
