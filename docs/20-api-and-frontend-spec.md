# 20 — API & Frontend Specification

_The HTTP surface and the cockpit, specified to build-ready detail._

---

## 1. API (FastAPI, `/v1`)

JSON in/out, Pydantic models, auto OpenAPI at `/docs`. Single-tenant in v1 (`org_id = "local"`), but every route already takes it so multi-tenant is a middleware change.

### 1.1 Routes

| Method | Path | Purpose | Notes |
|---|---|---|---|
| `POST` | `/v1/datasets` | register a dataset (upload the 3 files or point at a path) | returns `dataset_hash` |
| `GET` | `/v1/specs` · `/v1/specs/{name}` | list / fetch recon specs + version history | |
| `POST` | `/v1/runs` | start a run `{spec, dataset, no_ai?, config?}` | returns `run_id`, `202` |
| `GET` | `/v1/runs` · `/v1/runs/{id}` | list / run detail (status, counts, timings) | |
| `GET` | `/v1/runs/{id}/stream` | **SSE** live progress (§1.3) | |
| `GET` | `/v1/runs/{id}/scorecard` | matching + agent scorecard JSON | |
| `GET` | `/v1/runs/{id}/matches` | paginated, filterable (`status`, `pass`) | |
| `GET` | `/v1/runs/{id}/exceptions` | paginated; sort by `amount_impact` desc default; filter `category`,`status` | |
| `GET` | `/v1/exceptions/{id}` | full exception + records + decomposition + candidates + proposal/escalation + agent trajectory | the evidence-drawer payload |
| `POST` | `/v1/exceptions/{id}/resolve` | `{action, detail, draft_rule_decision?}` → `RESOLUTION_APPLIED` | |
| `POST` | `/v1/exceptions/{id}/reject-proposal` | `{reason}` | |
| `GET` | `/v1/runs/{id}/rules/pending` · `POST /v1/rules/{id}/merge` | learning-loop rule review | spec-diff in the response |
| `POST` | `/v1/runs/{id}/replay` | reproduce from event log → new `run_id`, assert hash match | |
| `GET` | `/v1/runs/{id}/verify` | recompute the hash chain | `{intact: bool, events: n, terminal_hash}` |
| `GET` | `/v1/runs/{id}/memo?format=html\|pdf\|json` | the Close Memo | |
| `GET` | `/v1/runs/{id}/audit-pack` | zip: records + events + scorecard + memo | |
| `GET` | `/v1/runs/{id}/trace` | OTLP file | |
| `GET` | `/healthz` · `/readyz` | liveness / readiness (DB + migrations) | |

### 1.2 Error model

RFC 9457 problem+json: `{type, title, status, detail, instance}`. Codes: `400` validation, `404`, `409` (idempotency conflict — returns the existing run), `422` (bad spec), `429`, `503` (not ready / provider down). Never a bare 500 without a `type`.

### 1.3 SSE event stream (`/runs/{id}/stream`)

```
event: state         data: {"state":"MATCHING","pass":"tolerant","progress":0.4}
event: counts        data: {"records":800,"matched":611,"exceptions":9}
event: investigation data: {"exception_id":"exc_0a1b","phase":"plan","goal":"..."}
event: investigation data: {"exception_id":"exc_0a1b","phase":"tool","tool":"decomposition_detail"}
event: investigation data: {"exception_id":"exc_0a1b","phase":"decide","terminal":"proposal","category":"TIMING"}
event: scorecard     data: { ...full scorecard... }
event: done          data: {"status":"completed","run_id":"..."}
```

Backed by the event log: the stream is a tail of new events mapped to these frames, so a reconnect replays from `Last-Event-ID`.

---

## 2. Frontend (Next.js 15, App Router, TypeScript strict)

### 2.1 Stack

| Concern | Choice |
|---|---|
| Framework | Next.js 15 App Router; the run view is a Server Component that SSRs the scorecard, the queue hydrates client-side |
| Styling | Tailwind + CSS variables for the design tokens ([doc 05 §3](05-design-doctrine.md)); `shadcn/ui` (Radix) primitives |
| Data | TanStack Query (server state, retries, SWR); the SSE stream feeds a query cache updater |
| Table | TanStack Table (the exception queue — sorting, grouping, keyboard nav, column sizing) |
| Charts | visx (scorecard bars, coverage bar, cycle sparkline, reliability diagram) — `dataviz` skill palette |
| Forms | React Hook Form + Zod (resolution controls, rule review) |
| PDF | the Close Memo view is print-CSS; `arbiter memo --pdf` renders the same route headless |
| Test | Vitest + Testing Library; Playwright for the triage flow; `axe-core` in CI |

### 2.2 Routes

```
/                         → run list (recent runs, status, headline match rate, spec)
/runs/[id]                → the cockpit (scorecard + queue + drawer), the main screen
/runs/[id]/memo           → Close Memo (print-styled)
/runs/[id]/rules          → pending learned-rule review (spec diff, approve/reject)
/runs/[id]/trace          → link out / embedded span viewer (P2)
/specs                    → spec list + version history + the m/u table
```

### 2.3 Component tree (the cockpit)

```
<RunLayout>
  <RunHeader>                     spec · period · record count · "97.2% auto-tied · ₹41,900 / 6 open" · re-run · export
  <div class="cockpit-grid">      CSS grid: scorecard (left, ~360px) | queue (center, flex) | drawer (right, ~440px, toggles)
    <Scorecard>
      <HeadlineNumber/>           auto-tied %, $ tied / $ open, count-up on improvement
      <CoverageBar/>              stacked ₹: auto | low-confidence | exception
      <AccuracyPanel/>            precision · recall · false-match rate (bench/demo only)
      <AgentPanel/>               task-completion · hallucination · escalation recall · ECE
      <ExceptionsByType/>         horizontal bars, ₹-sorted
      <CycleTrend/>               sparkline of auto-tied % across runs of this spec
    <ExceptionQueue>              <DataGrid> — see doc 05 §2.2; rows: ▸ Type Impact Confidence Hypothesis Source Status Action
      <QueueToolbar/>             filter (/) · group-by-type (g) · bulk-select
      <QueueRow/> ×N              j/k nav, e expand, a accept, r reject, w won't-fix
    <EvidenceDrawer>              opens beside the selected row (not a modal)
      <RecordCards/>              3 aligned cards; matching fields on shared rows; diffs get an accent left-border
      <IdentityEquation/>         the decomposition with real numbers, residual called out (mono)
      <RuleTrail/>                which passes ran, which rule fired, why no auto-match — plain sentences
      <AgentProposal/>            "proposed by Arbiter · <model>" badge; explanation with clickable evidence refs
                                  (click → highlights the field in RecordCards); hypotheses_tested list; draft rule as a diff
      <DecisionControls/>         Accept · Edit & accept · Reject · Won't fix — with the consequence preview
    <RunProgress>                 shown while state != completed: pass ticker + investigations streaming (from SSE)
```

### 2.4 State coverage (every view)

`loading` (skeleton, not shimmer-heavy) · `empty` ("no exceptions — everything tied" is a real, celebrated state) · `error` (per-surface boundary; a failed scorecard doesn't blank the queue) · `partial` (run still going: show what's ready, mark the rest pending) · `stale` (SWR revalidating indicator).

### 2.5 Interaction spec (keyboard)

| Key | Action |
|---|---|
| `j` / `k` | next / previous exception |
| `e` / `Enter` | expand/collapse the evidence drawer |
| `a` | accept the agent proposal (or, on a group, accept all) |
| `r` | reject proposal (prompts one-word reason) |
| `w` | mark won't-fix |
| `x` | toggle-select for bulk |
| `/` | focus filter |
| `g` | toggle group-by-type |
| `?` | shortcut cheatsheet |

`prefers-reduced-motion` disables the 120ms transitions and the count-up. Focus ring (2px accent) always visible. 44px min hit targets.

### 2.6 The Close Memo (`/runs/[id]/memo`)

One flowing document, print-styled (A4), sections:
1. **Header** — entity, period, spec + version, generated-at, `terminal_event_hash` (so `arbiter verify` can confirm it).
2. **Result** — X% auto-tied, ₹ tied vs ₹ open, N exceptions (M resolved, K carried forward, J escalated).
3. **Coverage** — the ₹ coverage table + the exceptions-by-type table.
4. **Decomposition summary** — total gross, MDR, GST-on-MDR, refunds, chargebacks, net — tied to the bank.
5. **Exception register** — every exception: category, ₹, records, resolution/decision, who decided, the proposed journal entry ([doc 15 §5](15-domain-model-reconciliation.md)).
6. **Sign-off** — a line for the preparer and reviewer.
Account numbers masked by default (`--full` for internal use).
