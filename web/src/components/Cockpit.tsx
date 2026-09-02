"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  api,
  rupees,
  type EvidenceDrawer,
  type ReconException,
  type RunSummary,
  type Scorecard,
} from "@/lib/api";

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

  const current = exceptions[sel];

  const refresh = useCallback(async () => {
    const r = await api.exceptions(runId);
    setExceptions(r.exceptions);
  }, [runId]);

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
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLSelectElement) return;
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
    <div className="min-h-screen">
      <header className="flex items-center justify-between border-b border-border bg-surface px-6 py-3">
        <div className="flex items-baseline gap-3">
          <Link href="/" className="text-sm text-muted hover:text-text">
            ← runs
          </Link>
          <span className="font-mono text-xs text-muted">{runId.slice(0, 8)}</span>
        </div>
        <div className="text-sm">
          {scorecard && (
            <>
              <span className="font-semibold">
                {(scorecard.matching.auto_match_rate * 100).toFixed(1)}% auto-tied
              </span>
              {" · "}
              <span className="text-attention">{run.exceptions} exceptions</span>
            </>
          )}
        </div>
      </header>

      <div className="grid grid-cols-[340px_1fr_minmax(0,440px)]">
        {/* ① scorecard */}
        <aside className="border-r border-border p-5">
          {scorecard ? <ScorecardPanel s={scorecard} /> : <p className="text-sm text-muted">no scorecard</p>}
        </aside>

        {/* ② queue */}
        <section className="min-w-0">
          <div className="border-b border-border px-4 py-2 text-xs text-muted">
            {exceptions.length} exceptions · <kbd className="font-mono">j</kbd>/<kbd className="font-mono">k</kbd> move ·{" "}
            <kbd className="font-mono">e</kbd> drawer · <kbd className="font-mono">a</kbd> accept ·{" "}
            <kbd className="font-mono">w</kbd> won&apos;t-fix
          </div>
          {exceptions.length === 0 ? (
            <p className="p-8 text-center text-sm text-positive">Everything tied. Nothing to review.</p>
          ) : (
            <table className="w-full text-sm">
              <tbody>
                {exceptions.map((e, i) => (
                  <tr
                    key={e.id}
                    onClick={() => setSel(i)}
                    className={`cursor-pointer border-b border-border ${
                      i === sel ? "bg-accent/10" : "hover:bg-accent/5"
                    }`}
                  >
                    <td className="w-40 px-4 py-2">
                      <span className={`font-medium ${CAT_COLOR[e.category ?? ""] ?? ""}`}>
                        {e.category ?? "—"}
                      </span>
                    </td>
                    <td className="px-2 py-2 text-right font-mono">
                      {e.impact_display ?? rupees(e.amount_impact_minor)}
                    </td>
                    <td className="px-2 py-2 text-xs text-muted">{e.classified_by}</td>
                    <td className="px-4 py-2 text-right text-xs">
                      <StatusPill status={e.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        {/* ③ evidence drawer */}
        {open && (
          <aside className="border-l border-border p-5">
            {!current ? (
              <p className="text-sm text-muted">select an exception</p>
            ) : !drawer ? (
              <p className="text-sm text-muted">loading evidence…</p>
            ) : (
              <DrawerPanel d={drawer} onResolve={resolve} />
            )}
          </aside>
        )}
      </div>
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
        <div className="text-3xl font-semibold">{(m.auto_match_rate * 100).toFixed(1)}%</div>
        <div className="text-xs text-muted">auto-tied ({m.correct_matches}/{m.true_matches})</div>
      </div>
      <Row label="precision" v={pct(m.precision)} />
      <Row label="false-match rate" v={pct(m.false_match_rate)} bad={m.false_match_rate > 0.015} />
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
      <div className="text-xs font-semibold uppercase tracking-wide text-muted">exceptions</div>
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
          <Row label="hallucination" v={pct(s.agent.hallucination_rate)} bad={s.agent.hallucination_rate > 0.02} />
          {typeof s.agent.grounded_rate === "number" && (
            <Row label="grounded" v={pct(s.agent.grounded_rate)} />
          )}
          {typeof s.agent.confidence_ece === "number" && s.agent.confidence_n ? (
            <Row label="confidence ECE" v={s.agent.confidence_ece.toFixed(3)} />
          ) : null}
          <Row label="escalation recall" v={pct(s.agent.escalation_recall)} />
          <Row label="cost" v={`$${s.agent.est_cost_usd.toFixed(3)}`} />
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
        <div className={`text-lg font-semibold ${CAT_COLOR[e.category ?? ""] ?? ""}`}>
          {e.category ?? "UNCLASSIFIED"}
        </div>
        <div className="text-xs text-muted">
          {e.impact_display ?? rupees(e.amount_impact_minor)} · {e.classified_by} · {e.status}
        </div>
      </div>

      <div className="space-y-2">
        {d.records.map((r) => (
          <div key={r.id} className="rounded border border-border bg-surface p-2 text-xs">
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
        <div key={dc.settlement_utr} className="rounded border border-border bg-surface p-2 font-mono text-xs">
          expected {rupees(dc.expected_minor)} · actual {rupees(dc.actual_minor)} ·{" "}
          <span className={dc.residual_minor === 0 ? "text-positive" : "text-attention"}>
            residual {rupees(dc.residual_minor)}
          </span>
        </div>
      ))}

      {d.agent_proposal && <ProposalPanel p={d.agent_proposal} />}
      {d.agent_escalation && (
        <div className="rounded border border-accent/40 bg-accent/5 p-3 text-xs">
          <div className="font-semibold text-accent">escalated by Arbiter</div>
          <p className="mt-1">
            <strong>knows:</strong> {String(d.agent_escalation.what_i_know)}
          </p>
          <p>
            <strong>missing:</strong> {String(d.agent_escalation.what_is_missing)}
          </p>
          <p className="mt-1 font-medium">{String(d.agent_escalation.question)}</p>
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
  const grounded = g && typeof g.grounded_confidence === "number" ? g.grounded_confidence : null;
  const fabricated = (g?.fabricated as unknown[] | undefined)?.length ?? 0;
  const catOk = g ? g.category_consistent !== false : true;
  const refs = (p.evidence_refs as { claim: string; record_id: string; field: string }[]) ?? [];
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
              ↳ {r.claim} <span className="font-mono">[{r.record_id}·{r.field}]</span>
            </li>
          ))}
        </ul>
      )}
      {fabricated > 0 && (
        <div className="mt-2 font-medium text-critical">
          ⚠ {fabricated} citation(s) did not resolve to a real record — escalated
        </div>
      )}
      {!catOk && typeof g?.category_note === "string" && g.category_note.length > 0 && (
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
