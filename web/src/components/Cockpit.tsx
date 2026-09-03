"use client";

import Link from "next/link";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useCallback, useEffect, useState } from "react";
import {
  api,
  rupees,
  type AttackReport,
  type EvidenceDrawer,
  type ReconException,
  type RunSummary,
  type Scorecard,
} from "@/lib/api";
import { usePresence } from "@/lib/presence";
import { clusterExceptions } from "@/lib/clusters";

const CAT_COLOR: Record<string, string> = {
  TIMING: "text-accent",
  DUPLICATE: "text-attention",
  CHARGEBACK: "text-critical",
  SECURITY_REVIEW: "text-critical",
  FEE_DEDUCTION: "text-attention",
  ROUNDING: "text-muted",
  UNEXPLAINED: "text-critical",
};

const ACTIONS = [
  "accept_variance",
  "carry_forward",
  "flag_overcharge",
  "raise_dispute",
  "request_data",
  "route_to_human",
  "wont_fix",
];

export function Cockpit({
  runId,
  run,
  scorecard,
  initialExceptions,
}: {
  runId: string;
  run: RunSummary;
  scorecard: Scorecard | null;
  initialExceptions: ReconException[];
}) {
  const [exceptions, setExceptions] = useState(initialExceptions);
  const [sel, setSel] = useState(0);
  const [drawer, setDrawer] = useState<EvidenceDrawer | null>(null);
  const [open, setOpen] = useState(true);
  // mobile: one surface at a time via the bottom tab bar; ignored at lg+
  const [tab, setTab] = useState<"score" | "queue" | "evidence">("queue");
  const reduce = useReducedMotion();
  const t = reduce
    ? { duration: 0 }
    : { type: "spring" as const, stiffness: 420, damping: 34 };

  const current = exceptions[sel];

  const refresh = useCallback(async () => {
    const r = await api.exceptions(runId);
    setExceptions(r.exceptions);
  }, [runId]);

  const { viewers } = usePresence(
    runId,
    useCallback(
      (m: Record<string, unknown>) => {
        if (m.type === "exception_resolved") refresh();
      },
      [refresh],
    ),
  );

  useEffect(() => {
    if (!current) {
      setDrawer(null);
      return;
    }
    let live = true;
    api.drawer(runId, current.id).then((d) => live && setDrawer(d));
    return () => {
      live = false;
    };
  }, [runId, current]);

  const resolve = useCallback(
    async (action: string) => {
      if (!current) return;
      await api.resolve(runId, current.id, action, "");
      await refresh();
    },
    [runId, current, refresh],
  );

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLSelectElement
      )
        return;
      if (e.key === "j") setSel((s) => Math.min(s + 1, exceptions.length - 1));
      else if (e.key === "k") setSel((s) => Math.max(s - 1, 0));
      else if (e.key === "e" || e.key === "Enter") setOpen((o) => !o);
      else if (e.key === "a") resolve("accept_variance");
      else if (e.key === "w") resolve("wont_fix");
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [exceptions.length, resolve]);

  return (
    <div className="min-h-screen pb-12 lg:pb-0">
      <header className="flex items-center justify-between border-b border-border bg-surface px-4 py-3 sm:px-6">
        <div className="flex items-baseline gap-3">
          <Link href="/" className="text-sm text-muted hover:text-text">
            ← runs
          </Link>
          <span className="font-mono text-xs text-muted">
            {runId.slice(0, 8)}
          </span>
        </div>
        <div className="flex items-center gap-4 text-sm">
          <Presence viewers={viewers} />
          {scorecard && (
            <span className="whitespace-nowrap">
              <span className="font-semibold">
                {(scorecard.matching.auto_match_rate * 100).toFixed(1)}%
                <span className="hidden sm:inline"> auto-tied</span>
              </span>
              {" · "}
              <span className="text-attention">
                {run.exceptions}
                <span className="hidden sm:inline"> exceptions</span>
              </span>
            </span>
          )}
        </div>
      </header>

      <div className="lg:grid lg:grid-cols-[320px_1fr_minmax(0,420px)]">
        {/* ① scorecard */}
        <aside
          className={`${tab === "score" ? "block" : "hidden"} border-b border-border p-5 lg:block lg:border-b-0 lg:border-r`}
        >
          {scorecard ? (
            <ScorecardPanel s={scorecard} />
          ) : (
            <p className="text-sm text-muted">no scorecard</p>
          )}
          <ClustersPanel exceptions={exceptions} onPick={(id) => {
            const i = exceptions.findIndex((e) => e.id === id);
            if (i >= 0) {
              setSel(i);
              setOpen(true);
              setTab("evidence");
            }
          }} />
          <AttackPanel />
        </aside>

        {/* ② queue */}
        <section
          className={`${tab === "queue" ? "block" : "hidden"} min-w-0 lg:block`}
        >
          <div className="border-b border-border px-4 py-2 text-xs text-muted">
            {exceptions.length} exceptions
            <span className="hidden sm:inline">
              {" · "}
              <kbd className="font-mono">j</kbd>/
              <kbd className="font-mono">k</kbd> move ·{" "}
              <kbd className="font-mono">e</kbd> drawer ·{" "}
              <kbd className="font-mono">a</kbd> accept ·{" "}
              <kbd className="font-mono">w</kbd> won&apos;t-fix
            </span>
          </div>
          {exceptions.length === 0 ? (
            <p className="p-8 text-center text-sm text-positive">
              Everything tied. Nothing to review.
            </p>
          ) : (
            <table className="w-full text-sm">
              <tbody>
                {exceptions.map((e, i) => (
                  <tr
                    key={e.id}
                    onClick={() => {
                      setSel(i);
                      setOpen(true);
                      setTab("evidence");
                    }}
                    className={`relative cursor-pointer border-b border-border ${
                      i === sel ? "bg-accent/10" : "hover:bg-accent/5"
                    }`}
                  >
                    <td className="px-4 py-2.5">
                      {i === sel && (
                        <motion.span
                          layoutId="row-cursor"
                          transition={t}
                          className="absolute inset-y-0 left-0 w-0.5 bg-accent"
                        />
                      )}
                      <span
                        className={`font-medium ${CAT_COLOR[e.category ?? ""] ?? ""}`}
                      >
                        {e.category ?? "—"}
                      </span>
                    </td>
                    <td className="px-2 py-2.5 text-right font-mono">
                      {e.impact_display ?? rupees(e.amount_impact_minor)}
                    </td>
                    <td className="hidden px-2 py-2.5 text-xs text-muted sm:table-cell">
                      {e.classified_by}
                    </td>
                    <td className="px-4 py-2.5 text-right text-xs">
                      <StatusPill status={e.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        {/* ③ evidence drawer */}
        <AnimatePresence initial={false}>
          {open && (
            <motion.aside
              initial={{ opacity: 0, x: reduce ? 0 : 24 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: reduce ? 0 : 24 }}
              transition={t}
              className={`${tab === "evidence" ? "block" : "hidden"} border-t border-border p-5 lg:block lg:border-l lg:border-t-0`}
            >
              {!current ? (
                <p className="text-sm text-muted">select an exception</p>
              ) : !drawer ? (
                <p className="text-sm text-muted">loading evidence…</p>
              ) : (
                <motion.div
                  key={current.id}
                  initial={{ opacity: 0, y: reduce ? 0 : 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={t}
                >
                  <DrawerPanel d={drawer} onResolve={resolve} />
                </motion.div>
              )}
            </motion.aside>
          )}
        </AnimatePresence>
      </div>

      {/* mobile surface switcher */}
      <nav className="fixed inset-x-0 bottom-0 z-30 flex border-t border-border bg-surface lg:hidden">
        {(["score", "queue", "evidence"] as const).map((v) => (
          <button
            key={v}
            onClick={() => setTab(v)}
            className={`flex-1 py-3 text-xs font-medium capitalize ${
              tab === v ? "text-accent" : "text-muted"
            }`}
          >
            {v === "queue" ? `queue · ${exceptions.length}` : v}
          </button>
        ))}
      </nav>
    </div>
  );
}

function Presence({
  viewers,
}: {
  viewers: { viewer_id: string; name: string }[];
}) {
  if (viewers.length <= 1) return null;
  const initials = (n: string) => n.slice(0, 2).toUpperCase();
  return (
    <div
      className="flex items-center gap-1.5"
      title={viewers.map((v) => v.name).join(", ")}
    >
      <div className="flex -space-x-1.5">
        {viewers.slice(0, 4).map((v) => (
          <span
            key={v.viewer_id}
            className="grid h-6 w-6 place-items-center rounded-full border border-surface bg-accent/15 text-[10px] font-medium text-accent"
          >
            {initials(v.name)}
          </span>
        ))}
      </div>
      <span className="text-xs text-muted">{viewers.length} viewing</span>
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  const c =
    status === "resolved"
      ? "text-positive"
      : status === "escalated"
        ? "text-accent"
        : status === "security_review"
          ? "text-critical"
          : "text-muted";
  return <span className={c}>{status}</span>;
}

function ScorecardPanel({ s }: { s: Scorecard }) {
  const m = s.matching;
  return (
    <div className="space-y-5">
      <div>
        <div className="text-3xl font-semibold">
          {(m.auto_match_rate * 100).toFixed(1)}%
        </div>
        <div className="text-xs text-muted">
          auto-tied ({m.correct_matches}/{m.true_matches})
        </div>
      </div>
      <Row label="precision" v={pct(m.precision)} />
      <Row
        label="false-match rate"
        v={pct(m.false_match_rate)}
        bad={m.false_match_rate > 0.015}
      />
      <Row label="₹ coverage" v={pct(m.dollar_coverage)} />
      <Row label="₹ unexplained" v={pct(m.dollar_unexplained)} />
      {m.by_pass && (
        <Row
          label="by pass"
          v={Object.entries(m.by_pass)
            .map(([k, v]) => `${k} ${v}`)
            .join("  ")}
        />
      )}
      <hr className="border-border" />
      <div className="text-xs font-semibold uppercase tracking-wide text-muted">
        exceptions
      </div>
      {Object.entries(s.exceptions.by_type).map(([k, v]) => (
        <Row key={k} label={k} v={String(v)} />
      ))}
      <Row
        label="anomalies caught"
        v={`${s.exceptions.detected_anomalies}/${s.exceptions.total_anomalies}`}
      />
      <Row label="category accuracy" v={pct(s.exceptions.category_accuracy)} />
      <hr className="border-border" />
      <div className="text-xs font-semibold uppercase tracking-wide text-muted">
        agent {s.agent.enabled ? `· ${s.agent.model}` : "· disabled"}
      </div>
      {s.agent.enabled && (
        <>
          <Row label="task-completion" v={pct(s.agent.task_completion_rate)} />
          <Row
            label="hallucination"
            v={pct(s.agent.hallucination_rate)}
            bad={s.agent.hallucination_rate > 0.02}
          />
          {typeof s.agent.grounded_rate === "number" && (
            <Row label="grounded" v={pct(s.agent.grounded_rate)} />
          )}
          {typeof s.agent.confidence_ece === "number" &&
          s.agent.confidence_n ? (
            <Row label="confidence ECE" v={s.agent.confidence_ece.toFixed(3)} />
          ) : null}
          <Row label="escalation recall" v={pct(s.agent.escalation_recall)} />
          <Row label="cost" v={`$${s.agent.est_cost_usd.toFixed(3)}`} />
        </>
      )}
      {s.safety && (
        <>
          <hr className="border-border" />
          <div className="text-xs font-semibold uppercase tracking-wide text-muted">
            safety (headline)
          </div>
          <Row
            label="unsafe auto-resolutions"
            v={`${s.safety.unsafe_auto_resolutions} / ${s.safety.items_needing_human}`}
            bad={s.safety.unsafe_auto_resolutions > 0}
          />
          <Row
            label="₹ protected"
            v={`${rupees(s.safety.rupees_protected_minor)} (${pct(
              s.safety.rupees_protected_rate,
            )})`}
          />
          <Row
            label="replay divergence"
            v={s.safety.replay_divergence ? "✗ DIVERGED" : "none"}
            bad={s.safety.replay_divergence}
          />
          <Row
            label="fabricated citations"
            v={String(s.safety.fabricated_citations)}
            bad={s.safety.fabricated_citations > 0}
          />
          <Row
            label="injection quarantined"
            v={String(s.safety.injection_quarantined)}
          />
        </>
      )}
      <hr className="border-border" />
      <Row
        label="deterministic"
        v={s.determinism.replay_hash_match ? "✓" : "✗"}
        bad={!s.determinism.replay_hash_match}
      />
      <Row label="throughput" v={`${s.throughput.records_per_sec} rec/s`} />
    </div>
  );
}

function ClustersPanel({
  exceptions,
  onPick,
}: {
  exceptions: ReconException[];
  onPick: (id: string) => void;
}) {
  const clusters = clusterExceptions(exceptions);
  if (clusters.length === 0) return null;
  const total = clusters.reduce((s, c) => s + c.grossMinor, 0);
  return (
    <div className="mt-6 border-t border-border pt-5">
      <div className="text-xs font-semibold uppercase tracking-wide text-muted">
        root causes · {clusters.length}
      </div>
      <p className="mt-1 text-xs text-muted">
        {rupees(total)} across {exceptions.length} exceptions
      </p>
      <ul className="mt-3 space-y-2">
        {clusters.map((c) => (
          <li key={c.headline}>
            <button
              onClick={() => onPick(c.exampleId)}
              className="w-full rounded border border-border bg-surface p-2 text-left hover:border-accent"
            >
              <div className="flex items-baseline justify-between gap-2">
                <span
                  className={`text-xs font-medium ${CAT_COLOR[c.category] ?? ""}`}
                >
                  {c.category}
                </span>
                <span className="font-mono text-xs">{rupees(c.grossMinor)}</span>
              </div>
              <div className="mt-0.5 text-[11px] text-muted">
                {c.count}× · {c.headline.split(" · ").slice(1).join(" · ")}
              </div>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function AttackPanel() {
  const [report, setReport] = useState<AttackReport | null>(null);
  const [busy, setBusy] = useState(false);
  const run = async () => {
    setBusy(true);
    try {
      setReport(await api.attack("razorpay-settlement", "seed"));
    } catch {
      setReport(null);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="mt-6 border-t border-border pt-5">
      <div className="text-xs font-semibold uppercase tracking-wide text-muted">
        attack arbiter
      </div>
      <p className="mt-1 text-xs text-muted">
        Tamper with a clean dataset and watch Arbiter refuse to be fooled.
      </p>
      <button
        onClick={run}
        disabled={busy}
        className="mt-2 rounded border border-border bg-surface px-3 py-1.5 text-xs font-medium hover:border-accent disabled:opacity-50"
      >
        {busy ? "running…" : "Run the attack suite"}
      </button>
      {report && (
        <div className="mt-3">
          <div className="text-xs">
            <span className="font-semibold text-positive">
              {report.contained} contained
            </span>
            {" · "}
            <span
              className={
                report.unsafe > 0 ? "font-semibold text-critical" : "text-muted"
              }
            >
              {report.unsafe} unsafe
            </span>
            {" · "}
            <span className="text-muted">
              {rupees(report.rupees_unaccounted_minor)} unaccounted
            </span>
          </div>
          <ul className="mt-2 space-y-1">
            {report.scenarios.map((s) => (
              <li
                key={s.scenario}
                className="flex items-baseline justify-between gap-2 text-[11px]"
              >
                <span className="truncate text-muted">{s.scenario}</span>
                <span
                  className={
                    s.verdict === "CONTAINED"
                      ? "text-positive"
                      : s.verdict === "UNSAFE"
                        ? "text-critical"
                        : "text-attention"
                  }
                >
                  {s.verdict}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function DrawerPanel({
  d,
  onResolve,
}: {
  d: EvidenceDrawer;
  onResolve: (a: string) => void;
}) {
  const e = d.exception;
  return (
    <div className="space-y-4">
      <div>
        <div
          className={`text-lg font-semibold ${CAT_COLOR[e.category ?? ""] ?? ""}`}
        >
          {e.category ?? "UNCLASSIFIED"}
        </div>
        <div className="text-xs text-muted">
          {e.impact_display ?? rupees(e.amount_impact_minor)} ·{" "}
          {e.classified_by} · {e.status}
        </div>
      </div>

      <div className="space-y-2">
        {d.records.map((r) => (
          <div
            key={r.id}
            className="rounded border border-border bg-surface p-2 text-xs"
          >
            <div className="flex justify-between">
              <span className="font-medium">
                {r.source} · {r.kind}
              </span>
              <span className="font-mono">{r.amount_display}</span>
            </div>
            <div className="text-muted">{String(r.reference ?? "")}</div>
          </div>
        ))}
      </div>

      {d.decompositions.map((dc) => (
        <div
          key={dc.settlement_utr}
          className="rounded border border-border bg-surface p-2 font-mono text-xs"
        >
          expected {rupees(dc.expected_minor)} · actual{" "}
          {rupees(dc.actual_minor)} ·{" "}
          <span
            className={
              dc.residual_minor === 0 ? "text-positive" : "text-attention"
            }
          >
            residual {rupees(dc.residual_minor)}
          </span>
        </div>
      ))}

      {d.agent_trace && d.agent_trace.length > 0 && (
        <details className="rounded border border-border bg-surface p-2 text-xs">
          <summary className="cursor-pointer font-medium text-muted">
            investigation trace · {d.agent_trace.length} turns
          </summary>
          <ol className="mt-2 space-y-1.5">
            {d.agent_trace.map((t, i) => (
              <li key={i} className="border-l-2 border-accent/40 pl-2">
                {t.text && <p>{t.text}</p>}
                {t.tool_calls.length > 0 && (
                  <p className="font-mono text-muted">
                    → {t.tool_calls.join(", ")}
                  </p>
                )}
              </li>
            ))}
          </ol>
        </details>
      )}
      {d.agent_proposal && <ProposalPanel p={d.agent_proposal} />}
      {d.agent_escalation && (
        <div className="rounded border border-accent/40 bg-accent/5 p-3 text-xs">
          <div className="font-semibold text-accent">escalated by Arbiter</div>
          <p className="mt-1">
            <strong>knows:</strong> {String(d.agent_escalation.what_i_know)}
          </p>
          <p>
            <strong>missing:</strong>{" "}
            {String(d.agent_escalation.what_is_missing)}
          </p>
          <p className="mt-1 font-medium">
            {String(d.agent_escalation.question)}
          </p>
        </div>
      )}

      {e.resolution ? (
        <div className="rounded border border-positive/40 bg-positive/10 p-2 text-xs">
          resolved · {e.resolution.action}
        </div>
      ) : (
        <div className="flex flex-wrap gap-2 pt-2">
          {ACTIONS.map((a) => (
            <button
              key={a}
              onClick={() => onResolve(a)}
              className="rounded border border-border px-2 py-1 text-xs hover:border-accent hover:text-accent"
            >
              {a}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function ProposalPanel({ p }: { p: Record<string, unknown> }) {
  const g = (p.grounding ?? null) as Record<string, unknown> | null;
  const raw = typeof p.confidence === "number" ? p.confidence : null;
  const grounded =
    g && typeof g.grounded_confidence === "number"
      ? g.grounded_confidence
      : null;
  const fabricated = (g?.fabricated as unknown[] | undefined)?.length ?? 0;
  const catOk = g ? g.category_consistent !== false : true;
  const refs =
    (p.evidence_refs as {
      claim: string;
      record_id: string;
      field: string;
    }[]) ?? [];
  return (
    <div className="rounded border border-accent/40 bg-accent/5 p-3 text-xs">
      <div className="flex items-center justify-between">
        <span className="font-semibold text-accent">proposed by Arbiter</span>
        {grounded !== null && (
          <span
            className={`font-mono ${grounded >= 0.8 ? "text-positive" : grounded >= 0.55 ? "text-attention" : "text-critical"}`}
          >
            {pct(grounded)} grounded
            {raw !== null && raw !== grounded ? ` (said ${pct(raw)})` : ""}
          </span>
        )}
      </div>
      <div className="mt-1 font-medium">{String(p.category)}</div>
      <p className="mt-1">{String(p.explanation ?? "")}</p>
      {refs.length > 0 && (
        <ul className="mt-2 space-y-0.5 text-muted">
          {refs.map((r, i) => (
            <li key={i}>
              ↳ {r.claim}{" "}
              <span className="font-mono">
                [{r.record_id}·{r.field}]
              </span>
            </li>
          ))}
        </ul>
      )}
      {fabricated > 0 && (
        <div className="mt-2 font-medium text-critical">
          ⚠ {fabricated} citation(s) did not resolve to a real record —
          escalated
        </div>
      )}
      {!catOk &&
        typeof g?.category_note === "string" &&
        g.category_note.length > 0 && (
          <div className="mt-2 text-attention">⚠ {g.category_note}</div>
        )}
    </div>
  );
}

function Row({ label, v, bad }: { label: string; v: string; bad?: boolean }) {
  return (
    <div className="flex justify-between text-sm">
      <span className="text-muted">{label}</span>
      <span className={`font-mono ${bad ? "text-critical" : ""}`}>{v}</span>
    </div>
  );
}

const pct = (x: number) => `${(x * 100).toFixed(1)}%`;
