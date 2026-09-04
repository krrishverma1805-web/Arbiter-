"use client";

import { useState } from "react";

import { rupees, type EvidenceDrawer, type AgentInvestigation } from "@/lib/api";
import {
  ACTIONS,
  actionLabel,
  categoryLabel,
  componentLabel,
  componentSign,
  ESCALATION_REASON,
  plainSummary,
  sourceLabel,
  STEP_LABEL,
} from "@/lib/vocab";
import { cn } from "@/lib/utils";
import { CategoryChip, StatusChip } from "./shared";

export function Evidence({
  drawer,
  onResolve,
  busy,
}: {
  drawer: EvidenceDrawer | null;
  onResolve: (action: string) => void;
  busy: boolean;
}) {
  if (!drawer) {
    return (
      <div className="grid flex-1 place-items-center p-8 text-center">
        <p className="max-w-xs text-sm text-text-muted">
          Pick an exception to see the records behind it, the settlement maths,
          and what to do about it.
        </p>
      </div>
    );
  }

  const e = drawer.exception;
  const dc = drawer.decompositions[0];
  const resolved = e.resolution;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex-none border-b border-border p-5">
        <div className="flex flex-wrap items-center gap-2">
          <CategoryChip category={e.category} />
          <StatusChip status={e.status} />
        </div>
        <div className="mt-2 font-mono text-lg tabular-nums">
          {e.impact_display ?? rupees(e.amount_impact_minor)}
        </div>
        <p className="mt-1.5 text-sm leading-snug text-text-muted">
          {plainSummary(e, dc?.residual_minor ?? null)}
        </p>
      </div>

      <div className="min-h-0 flex-1 space-y-6 overflow-y-auto p-5 [scrollbar-gutter:stable]">
        {dc && <Identity dc={dc} />}

        <Records records={drawer.records} total={drawer._record_total} />

        {drawer.agent_investigation &&
        drawer.agent_investigation.steps.length > 0 ? (
          <Investigation inv={drawer.agent_investigation} />
        ) : (
          drawer.agent_escalation && (
            <Callout tone="attention" title="Arbiter escalated this to you">
              <p>
                <span className="text-text-muted">It knows: </span>
                {String(drawer.agent_escalation.what_i_know)}
              </p>
              <p>
                <span className="text-text-muted">It&apos;s missing: </span>
                {String(drawer.agent_escalation.what_is_missing)}
              </p>
              <p className="mt-1.5 font-medium text-text">
                {String(drawer.agent_escalation.question)}
              </p>
            </Callout>
          )
        )}
      </div>

      {/* actions */}
      <div className="flex-none border-t border-border p-5">
        {resolved ? (
          <div className="rounded-md border border-positive/30 bg-positive/5 px-3 py-2 text-sm text-positive">
            Resolved · {actionLabel(resolved.action ?? "")}
          </div>
        ) : (
          <ActionList busy={busy} onResolve={onResolve} />
        )}
      </div>
    </div>
  );
}

/* ── resolution actions ─────────────────────────────────────────────────── */

function ActionList({
  busy,
  onResolve,
}: {
  busy: boolean;
  onResolve: (a: string) => void;
}) {
  const [showAll, setShowAll] = useState(false);
  const primary = ACTIONS.slice(0, 2);
  const rest = ACTIONS.slice(2);

  const Row = (a: (typeof ACTIONS)[number]) => (
    <button
      key={a.key}
      disabled={busy}
      onClick={() => onResolve(a.key)}
      className={cn(
        "flex w-full flex-col gap-0.5 rounded-md border px-3 py-2 text-left transition-colors [transition-duration:120ms] disabled:opacity-50",
        a.tone === "primary"
          ? "border-accent bg-accent/5 hover:bg-accent/10"
          : "border-border hover:bg-surface-2",
      )}
    >
      <span
        className={cn(
          "text-sm font-medium",
          a.tone === "primary" && "text-accent",
        )}
      >
        {a.label}
      </span>
      <span className="text-xs text-text-muted">{a.hint}</span>
    </button>
  );

  return (
    <>
      <div className="mb-2 text-xs font-medium text-text-muted">
        What do you want to do?
      </div>
      <div className="grid gap-1.5">
        {primary.map(Row)}
        {showAll && rest.map(Row)}
      </div>
      <button
        onClick={() => setShowAll((s) => !s)}
        className="mt-2 text-xs text-accent hover:underline"
      >
        {showAll ? "Fewer options" : `${rest.length} more ways to resolve`}
      </button>
    </>
  );
}

/* ── the settlement identity, as a real equation ─────────────────────────── */

function Identity({
  dc,
}: {
  dc: EvidenceDrawer["decompositions"][number];
}) {
  const parts = Object.entries(dc.components).filter(([, v]) => v !== 0);
  const diff = dc.actual_minor - dc.expected_minor;
  return (
    <section>
      <h3 className="text-sm font-semibold">The settlement maths</h3>
      <p className="mt-0.5 text-xs text-text-muted">
        What the payout should have been, line by line.
      </p>
      <div className="mt-2.5 overflow-hidden rounded-md border border-border">
        <table className="w-full text-sm">
          <tbody className="divide-y divide-border">
            {parts.map(([k, v]) => (
              <tr key={k}>
                <td className="px-3 py-1.5 text-text-muted">
                  {componentSign(k) < 0 ? "less " : ""}
                  {componentLabel(k)}
                </td>
                <td className="px-3 py-1.5 text-right font-mono tabular-nums">
                  {componentSign(k) < 0 ? "−" : ""}
                  {rupees(Math.abs(v))}
                </td>
              </tr>
            ))}
            <tr className="bg-surface-2/60 font-medium">
              <td className="px-3 py-1.5">Expected payout</td>
              <td className="px-3 py-1.5 text-right font-mono tabular-nums">
                {rupees(dc.expected_minor)}
              </td>
            </tr>
            <tr>
              <td className="px-3 py-1.5 text-text-muted">Bank actually paid</td>
              <td className="px-3 py-1.5 text-right font-mono tabular-nums">
                {rupees(dc.actual_minor)}
              </td>
            </tr>
            <tr
              className={cn(
                "font-semibold",
                diff === 0 ? "text-positive" : "text-attention",
              )}
            >
              <td className="px-3 py-1.5">Difference</td>
              <td className="px-3 py-1.5 text-right font-mono tabular-nums">
                {diff > 0 ? "+" : ""}
                {rupees(diff)}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-xs text-text-muted">
        Cross-checked against your ledger:{" "}
        {dc.ledger_crosscheck_ok ? (
          <span className="text-positive">matches</span>
        ) : (
          <span className="text-attention">doesn&apos;t match</span>
        )}
        {dc.settlement_utr && (
          <>
            {" · "}
            <span className="font-mono">{dc.settlement_utr}</span>
          </>
        )}
      </p>
    </section>
  );
}

/* ── the records ─────────────────────────────────────────────────────────── */

function Records({
  records,
  total,
}: {
  records: EvidenceDrawer["records"];
  total?: number;
}) {
  const [expanded, setExpanded] = useState(false);
  const groups = new Map<string, EvidenceDrawer["records"]>();
  for (const r of records) {
    const g = groups.get(r.source) ?? [];
    g.push(r);
    groups.set(r.source, g);
  }
  const shownTotal = total ?? records.length;

  return (
    <section>
      <h3 className="text-sm font-semibold">
        The records{" "}
        <span className="font-normal text-text-muted">
          {shownTotal > records.length
            ? `(${shownTotal} behind this, ${records.length} loaded)`
            : `(${shownTotal})`}
        </span>
      </h3>
      <div className="mt-2.5 space-y-3">
        {Array.from(groups.entries()).map(([source, rs]) => {
          const show = expanded ? rs : rs.slice(0, 3);
          return (
            <div key={source}>
              <div className="mb-1 text-xs font-medium text-text-muted">
                {sourceLabel(source)}{" "}
                <span className="font-normal">({rs.length})</span>
              </div>
              <ul className="divide-y divide-border overflow-hidden rounded-md border border-border text-sm">
                {show.map((r) => (
                  <li
                    key={r.id}
                    className="flex items-center justify-between gap-3 px-3 py-1.5"
                  >
                    <span className="min-w-0 truncate">
                      <span className="capitalize">{String(r.kind)}</span>
                      {typeof r.external_ids === "object" &&
                        r.external_ids !== null &&
                        "order_id" in r.external_ids && (
                          <span className="ml-1.5 font-mono text-xs text-text-muted">
                            {String(
                              (r.external_ids as Record<string, unknown>)
                                .order_id,
                            )}
                          </span>
                        )}
                    </span>
                    <span className="shrink-0 font-mono tabular-nums">
                      {String(r.amount_display)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
      </div>
      {records.length > 3 && (
        <button
          onClick={() => setExpanded((x) => !x)}
          className="mt-2 text-xs text-accent hover:underline"
        >
          {expanded ? "Show fewer" : `Show all ${records.length}`}
        </button>
      )}
    </section>
  );
}

/* ── the AI investigation ────────────────────────────────────────────────── */

function Investigation({ inv }: { inv: AgentInvestigation }) {
  const [raw, setRaw] = useState(false);
  const esc = inv.steps.find((s) => s.kind === "escalation");
  const reason = esc?.reason ?? inv.decision?.escalation_reason ?? "";

  return (
    <section>
      <div className="flex items-baseline justify-between">
        <h3 className="text-sm font-semibold">What the AI investigator did</h3>
        <span className="font-mono text-[11px] text-text-muted">
          {inv.tool_calls} tool calls
        </span>
      </div>

      {inv.outcome === "escalate" && reason && (
        <Callout tone="attention" title="Why it didn't resolve this itself">
          <p>{ESCALATION_REASON[reason] ?? "The evidence wasn't conclusive."}</p>
          {esc?.what_is_missing && (
            <p className="mt-1 text-text-muted">
              Still open: {esc.what_is_missing}
            </p>
          )}
        </Callout>
      )}

      <ol className="mt-3 space-y-3">
        {inv.steps
          .filter((s) => s.kind !== "escalation")
          .map((s, i) => (
            <li key={i} className="border-l-2 border-border pl-3">
              <div className="text-xs font-medium text-text-muted">
                {STEP_LABEL[s.kind] ?? s.title}
              </div>
              {s.body && <p className="mt-0.5 text-sm">{s.body}</p>}
              {s.kind === "proposal" && (
                <p className="mt-1 text-xs text-text-muted">
                  Proposed: {categoryLabel(s.category)}
                  {typeof s.grounded_confidence === "number" &&
                    ` · confidence ${(s.grounded_confidence * 100).toFixed(0)}%`}
                  {s.suggested_action &&
                    ` · suggested "${actionLabel(s.suggested_action)}"`}
                </p>
              )}
              {s.kind === "safety" && s.action && (
                <p className="mt-1 text-xs">
                  <span className="text-text-muted">Decision: </span>
                  <span
                    className={cn(
                      s.action === "SAFE" ? "text-positive" : "text-attention",
                    )}
                  >
                    {s.action === "SAFE"
                      ? "safe to propose"
                      : s.action === "ESCALATE"
                        ? "send to a person"
                        : s.action.toLowerCase()}
                  </span>
                </p>
              )}
            </li>
          ))}
      </ol>

      <button
        onClick={() => setRaw((r) => !r)}
        className="mt-3 text-xs text-text-muted hover:text-text"
      >
        {raw ? "Hide" : "Show"} the model&apos;s own words
      </button>
      {raw && (
        <pre className="mt-2 max-h-52 overflow-auto rounded-md border border-border bg-surface-2/50 p-2.5 text-[11px] leading-relaxed">
          {JSON.stringify(inv.decision, null, 2)}
        </pre>
      )}
    </section>
  );
}

/* ── shared callout ─────────────────────────────────────────────────────── */

function Callout({
  tone,
  title,
  children,
}: {
  tone: "attention" | "accent";
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "mt-3 rounded-md border p-3 text-sm",
        tone === "attention"
          ? "border-attention/30 bg-attention/5"
          : "border-accent/30 bg-accent/5",
      )}
    >
      <div
        className={cn(
          "text-xs font-semibold",
          tone === "attention" ? "text-attention" : "text-accent",
        )}
      >
        {title}
      </div>
      <div className="mt-1 space-y-1">{children}</div>
    </div>
  );
}
