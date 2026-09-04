"use client";

import { useState } from "react";

import { rupees, type ReconException, type Scorecard } from "@/lib/api";
import { categoryLabel, PASS_LABEL } from "@/lib/vocab";
import { cn } from "@/lib/utils";
import { Stat } from "./shared";

// a calm categorical palette for the impact bar — one hue per exception type,
// distinct in both themes, following the dataviz approach (no reused semantics)
const CAT_HUE: Record<string, string> = {
  TIMING: "#5c7cfa",
  WRONG_ACCOUNT: "#e8a33d",
  DUPLICATE: "#9775fa",
  CHARGEBACK: "#e8590c",
  SECURITY_REVIEW: "#e03131",
  FEE_DEDUCTION: "#20a4a0",
  ROUNDING: "#868e96",
  UNEXPLAINED: "#f03e3e",
};
const hue = (cat: string | null | undefined) =>
  (cat && CAT_HUE[cat]) || "#868e96";

/** The verdict, as a readable strip. Answers "is the money right?" before the
 *  controller reads anything else. Deep metrics collapse into a disclosure. */
export function Verdict({
  scorecard,
  exceptions,
  onPick,
}: {
  scorecard: Scorecard;
  exceptions: ReconException[];
  onPick: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const m = scorecard.matching;
  const s = scorecard.safety;
  const open_ = exceptions.filter(
    (e) => e.status !== "resolved" && e.status !== "wont_fix",
  );
  const needsYou = open_.filter(
    (e) => e.status === "escalated" || e.status === "security_review",
  ).length;

  // impact bar — one segment per open exception, width by rupees at stake
  const segs = [...open_]
    .map((e) => ({
      id: e.id,
      minor: Math.abs(e.amount_impact_minor),
      cat: e.category,
    }))
    .sort((a, b) => b.minor - a.minor);
  const total = segs.reduce((sum, x) => sum + x.minor, 0) || 1;

  return (
    <section className="rounded-lg border border-border bg-surface">
      <div className="flex flex-col gap-5 p-5 sm:flex-row sm:flex-wrap sm:gap-x-14 sm:gap-y-6">
        <div>
          <div className="text-lg font-semibold tabular-nums text-positive sm:text-xl">
            {(m.auto_match_rate * 100).toFixed(1)}%
          </div>
          <div className="mt-0.5 text-sm text-text">verified automatically</div>
          <div className="text-xs text-text-muted">
            {m.correct_matches} of {m.true_matches} settlement groups tied
          </div>
        </div>
        <Stat
          value={s ? rupees(s.rupees_at_risk_minor) : "n/a"}
          label="held for a person"
          sub={`${open_.length} open ${open_.length === 1 ? "item" : "items"}`}
          tone="attention"
        />
        <Stat
          value={String(needsYou)}
          label={needsYou === 1 ? "needs you directly" : "need you directly"}
          sub="escalations and security holds"
          tone={needsYou > 0 ? "critical" : undefined}
        />
      </div>

      {segs.length > 0 && (
        <div className="border-t border-border px-5 py-4">
          <div className="mb-2 text-xs text-text-muted">
            <span className="font-medium">Where the money at stake sits</span>
            <span className="ml-2 font-mono">
              {rupees(total)} across {segs.length}
            </span>
          </div>
          <div className="flex h-2.5 gap-0.5 overflow-hidden rounded-full">
            {segs.map((seg) => (
              <button
                key={seg.id}
                onClick={() => onPick(seg.id)}
                title={`${categoryLabel(seg.cat)} · ${rupees(seg.minor)}`}
                style={{
                  flexBasis: `${(seg.minor / total) * 100}%`,
                  background: hue(seg.cat),
                }}
                className="min-w-[3px] transition-opacity [transition-duration:120ms] hover:opacity-70"
              />
            ))}
          </div>
          <div className="mt-2.5 grid grid-cols-2 gap-x-4 gap-y-1.5 sm:grid-cols-4">
            {segs.slice(0, 4).map((seg) => (
              <button
                key={seg.id}
                onClick={() => onPick(seg.id)}
                className="flex min-w-0 items-center gap-1.5 text-xs text-text-muted hover:text-text"
              >
                <span
                  className="size-2 shrink-0 rounded-full"
                  style={{ background: hue(seg.cat) }}
                />
                <span className="truncate">{categoryLabel(seg.cat)}</span>
                <span className="shrink-0 font-mono">{rupees(seg.minor)}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between border-t border-border px-5 py-2.5 text-xs text-text-muted transition-colors [transition-duration:120ms] hover:text-text"
      >
        <span>
          {open ? "Hide" : "Show"} the assurance numbers
        </span>
        <span aria-hidden>{open ? "–" : "+"}</span>
      </button>

      {open && (
        <div className="grid gap-x-8 gap-y-3 border-t border-border p-5 text-sm sm:grid-cols-2">
          <Metric
            label="False matches"
            value={`${(m.false_match_rate * 100).toFixed(1)}%`}
            good={m.false_match_rate <= 0.015}
            note="Matches ground truth says are wrong."
          />
          <Metric
            label="Rupees accounted for"
            value={`${(m.dollar_coverage * 100).toFixed(1)}%`}
            good={m.dollar_coverage >= 0.98}
            note="Share of settlement value Arbiter can explain."
          />
          {s && (
            <>
              <Metric
                label="Unsafe auto-resolutions"
                value={`${s.unsafe_auto_resolutions}`}
                good={s.unsafe_auto_resolutions === 0}
                note="Arbiter never closes an item a person should see. This should be zero."
              />
              <Metric
                label="Replay"
                value={s.replay_divergence ? "diverged" : "identical"}
                good={!s.replay_divergence}
                note="Re-running the same inputs produced the same result."
              />
              <Metric
                label="Fabricated citations"
                value={`${s.fabricated_citations}`}
                good={s.fabricated_citations === 0}
                note="AI claims that didn't resolve to a real record."
              />
              <Metric
                label="Injection attempts quarantined"
                value={`${s.injection_quarantined}`}
                note="Prompt-injection in the data, caught and isolated."
              />
            </>
          )}
          {m.by_pass && (
            <div className="sm:col-span-2">
              <div className="text-xs font-medium text-text-muted">
                How the automatic matches were made
              </div>
              <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs">
                {Object.entries(m.by_pass).map(([k, v]) => (
                  <span key={k}>
                    <span className="font-mono">{v}</span>{" "}
                    {PASS_LABEL[k] ?? k.replace(/_/g, " ")}
                  </span>
                ))}
              </div>
            </div>
          )}
          {scorecard.agent.enabled && (
            <div className="sm:col-span-2 border-t border-border pt-3">
              <div className="text-xs font-medium text-text-muted">
                AI investigator ({scorecard.agent.model})
              </div>
              <div className="mt-1 text-xs text-text-muted">
                {scorecard.agent.investigations} investigation
                {scorecard.agent.investigations === 1 ? "" : "s"} ·{" "}
                {scorecard.agent.escalations} escalated to a person ·{" "}
                {typeof scorecard.agent.est_cost_usd === "number"
                  ? `$${scorecard.agent.est_cost_usd.toFixed(3)}`
                  : "cost n/a"}
                {scorecard.agent.insufficient_eval_data && (
                  <>
                    {" · "}
                    <span className="text-attention">
                      too few labelled runs to score its accuracy yet
                    </span>
                  </>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function Metric({
  label,
  value,
  note,
  good,
}: {
  label: string;
  value: string;
  note: string;
  good?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <div>
        <div className="text-sm">{label}</div>
        <div className="text-xs text-text-muted">{note}</div>
      </div>
      <div
        className={cn(
          "shrink-0 font-mono text-sm tabular-nums",
          good === true && "text-positive",
          good === false && "text-critical",
        )}
      >
        {value}
      </div>
    </div>
  );
}
