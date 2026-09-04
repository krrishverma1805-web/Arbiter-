"use client";

import Link from "next/link";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  api,
  streamUrl,
  rupees,
  type Scorecard,
  type StreamFrame,
} from "@/lib/api";
import { categoryLabel, ESCALATION_REASON } from "@/lib/vocab";
import { cn } from "@/lib/utils";
import { AppShell } from "@/components/AppShell";
import { Button } from "@/components/ui/button";
import { CategoryChip } from "@/components/cockpit/shared";

type Phase = "ingesting" | "matching" | "classifying" | "investigating" | "done";

const PHASE_LABEL: Record<Phase, string> = {
  ingesting: "Reading the files",
  matching: "Matching",
  classifying: "Classifying exceptions",
  investigating: "Investigating with the AI",
  done: "Done",
};

const PHASE_OF: Record<string, Phase> = {
  RECORD_INGESTED: "ingesting",
  SOURCE_INGESTED: "ingesting",
  MATCH_CONFIRMED: "matching",
  DECOMPOSITION_COMPUTED: "matching",
  EXCEPTION_OPENED: "classifying",
  EXCEPTION_CLASSIFIED: "classifying",
  AGENT_INVESTIGATION_STARTED: "investigating",
  AGENT_INTERACTION: "investigating",
  AGENT_PROPOSAL_CREATED: "investigating",
  AGENT_ESCALATED: "investigating",
  RUN_COMPLETED: "done",
};
const PHASES: Phase[] = [
  "ingesting",
  "matching",
  "classifying",
  "investigating",
  "done",
];

interface Investigation {
  id: string;
  category: string | null;
  impactMinor: number | null;
  turns: { text: string; tools: string[] }[];
  proposal?: {
    category: string | null;
    explanation: string;
    grounded: number | null;
  };
  verifier?: { supported: boolean; reason: string };
  escalation?: { question: string; reason: string | null };
  decision?: {
    action: string;
    risk: string;
    risk_label?: string;
    reasons: string[];
  } | null;
}

// the agent's terminal turns arrive as JSON text; pull them out so they render
// as cards, not raw blobs. Also strips ```json fences from a reasoning turn.
function readJsonTurn(raw: string): Record<string, unknown> | null {
  const s = raw.trim();
  const m = s.match(/\{[\s\S]*\}/);
  if (!m) return null;
  try {
    const o = JSON.parse(m[0]) as Record<string, unknown>;
    return o && typeof o === "object" ? o : null;
  } catch {
    return null;
  }
}
// the streamed reasoning turns arrive as loose markdown; clean it to plain prose
function cleanTurn(t: string): string {
  return t
    .replace(/```json[\s\S]*?```/g, "")
    .replace(/```[\s\S]*?```/g, "")
    .replace(/\*\*/g, "")
    .replace(/^#{1,6}\s*/gm, "")
    .replace(/[ \t]{2,}/g, " ")
    .trim();
}

const KEEP = new Set([
  "EXCEPTION_OPENED",
  "AGENT_INVESTIGATION_STARTED",
  "AGENT_INTERACTION",
  "AGENT_PROPOSAL_CREATED",
  "AGENT_ESCALATED",
  "RUN_COMPLETED",
]);

export function LiveRun({ runId }: { runId: string }) {
  const [frames, setFrames] = useState<StreamFrame[]>([]);
  const [counts, setCounts] = useState({ records: 0, matches: 0, exceptions: 0 });
  const [phase, setPhase] = useState<Phase>("ingesting");
  const [done, setDone] = useState(false);
  const [scorecard, setScorecard] = useState<Scorecard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const reduce = useReducedMotion();
  const seenPhases = useRef<Set<Phase>>(new Set(["ingesting"]));

  useEffect(() => {
    const es = new EventSource(streamUrl(runId));
    const onFrame = (e: MessageEvent) => {
      let f: StreamFrame;
      try {
        f = JSON.parse(e.data);
      } catch {
        return;
      }
      if (!f?.type) return;
      const p = PHASE_OF[f.type];
      if (p) {
        seenPhases.current.add(p);
        setPhase(p);
      }
      if (f.type === "RECORD_INGESTED")
        setCounts((c) => ({ ...c, records: c.records + 1 }));
      else if (f.type === "MATCH_CONFIRMED")
        setCounts((c) => ({ ...c, matches: c.matches + 1 }));
      else if (f.type === "EXCEPTION_OPENED")
        setCounts((c) => ({ ...c, exceptions: c.exceptions + 1 }));
      else if (f.type === "RUN_COMPLETED" && f.counts) {
        const cc = f.counts;
        setCounts((c) => ({
          records: cc.records ?? c.records,
          matches: cc.matches ?? c.matches,
          exceptions: cc.exceptions ?? c.exceptions,
        }));
      }
      if (KEEP.has(f.type))
        setFrames((prev) =>
          prev.some((x) => x.seq === f.seq) ? prev : [...prev, f],
        );
    };
    for (const t of [
      "RECORD_INGESTED",
      "SOURCE_INGESTED",
      "MATCH_CONFIRMED",
      "DECOMPOSITION_COMPUTED",
      "EXCEPTION_OPENED",
      "EXCEPTION_CLASSIFIED",
      "AGENT_INVESTIGATION_STARTED",
      "AGENT_INTERACTION",
      "AGENT_PROPOSAL_CREATED",
      "AGENT_ESCALATED",
      "RUN_STARTED",
      "RUN_COMPLETED",
    ]) {
      es.addEventListener(t, onFrame as EventListener);
    }
    es.addEventListener("message", onFrame as EventListener);
    es.addEventListener("done", () => {
      setDone(true);
      setPhase("done");
      es.close();
      api
        .scorecard(runId)
        .then(setScorecard)
        .catch(() => {});
    });
    es.onerror = () => {
      if (
        es.readyState === EventSource.CLOSED &&
        !seenPhases.current.has("done")
      ) {
        setError("The live feed stopped. Open the cockpit for the finished run.");
        es.close();
      }
    };
    return () => es.close();
  }, [runId]);

  const investigations = useMemo(() => foldInvestigations(frames), [frames]);
  const t = { duration: reduce ? 0 : 0.15 };

  return (
    <AppShell
      width="read"
      context={
        <span className="flex items-center gap-x-2">
          <span className="text-text">
            {done ? "Reconciliation complete" : "Reconciling"}
          </span>
          <span className="hidden font-mono text-text-muted sm:inline">
            {runId.slice(0, 8)}
          </span>
        </span>
      }
      actions={
        <Button asChild variant={done ? "primary" : "secondary"} size="sm">
          <Link href={`/runs/${runId}`}>
            {done ? "Open the cockpit" : "Skip to the cockpit"}
          </Link>
        </Button>
      }
    >
      <PhaseRail phase={phase} seen={seenPhases.current} />

      <div className="mt-6 grid grid-cols-3 gap-3">
        <Stat label="records read" value={counts.records} />
        <Stat label="tied automatically" value={counts.matches} />
        <Stat label="exceptions" value={counts.exceptions} />
      </div>

      {investigations.length > 0 && (
        <h2 className="mb-3 mt-10 text-sm font-semibold">
          What the AI is investigating
        </h2>
      )}

      <div className="space-y-3">
        <AnimatePresence initial={false}>
          {investigations.map((inv) => (
            <motion.div
              key={inv.id}
              initial={{ opacity: 0, y: reduce ? 0 : 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={t}
              className="overflow-hidden rounded-lg border border-border bg-surface"
            >
              <div className="flex items-center justify-between gap-3 px-4 py-3">
                {inv.category ? (
                  <CategoryChip category={inv.category} />
                ) : (
                  <span className="text-sm text-text-muted">investigating…</span>
                )}
                {inv.impactMinor != null && (
                  <span className="font-mono text-xs text-text-muted">
                    {rupees(inv.impactMinor)}
                  </span>
                )}
              </div>

              {inv.turns.length > 0 && (
                <ol className="space-y-2 px-4 pb-3">
                  {inv.turns.map((turn, i) => (
                    <li
                      key={i}
                      className="border-l-2 border-accent/30 pl-3 text-xs leading-relaxed"
                    >
                      {turn.text && <TurnText text={turn.text} />}
                      {turn.tools.length > 0 && (
                        <p className="mt-0.5 font-mono text-[11px] text-text-muted">
                          {turn.tools.map((x) => `→ ${x}`).join("  ")}
                        </p>
                      )}
                    </li>
                  ))}
                </ol>
              )}

              {inv.proposal && (
                <div className="border-t border-accent/20 bg-accent/5 px-4 py-3 text-xs">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-semibold text-accent">
                      Proposed: {categoryLabel(inv.proposal.category)}
                    </span>
                    {inv.proposal.grounded != null && (
                      <span className="font-mono">
                        {Math.round(inv.proposal.grounded * 100)}% grounded
                      </span>
                    )}
                  </div>
                  <p className="mt-1 text-text">{inv.proposal.explanation}</p>
                </div>
              )}

              {inv.verifier && (
                <div
                  className={cn(
                    "border-t px-4 py-3 text-xs",
                    inv.verifier.supported
                      ? "border-positive/20 bg-positive/5"
                      : "border-critical/25 bg-critical/5",
                  )}
                >
                  <span
                    className={cn(
                      "font-semibold",
                      inv.verifier.supported
                        ? "text-positive"
                        : "text-critical",
                    )}
                  >
                    Independent check:{" "}
                    {inv.verifier.supported
                      ? "the citations hold up"
                      : "the citations don't hold up"}
                  </span>
                  <p className="mt-1 text-text">{inv.verifier.reason}</p>
                </div>
              )}

              {inv.decision && (
                <div className="border-t border-border px-4 py-2 text-[11px]">
                  <span className="font-medium uppercase tracking-wide text-text-muted">
                    Safety check
                  </span>{" "}
                  <span className="font-mono">
                    {inv.decision.risk} ·{" "}
                    <span
                      className={cn(
                        inv.decision.action === "SAFE"
                          ? "text-positive"
                          : inv.decision.action === "ESCALATE" ||
                              inv.decision.action === "QUARANTINE"
                            ? "text-attention"
                            : "text-accent",
                      )}
                    >
                      {inv.decision.action === "SAFE"
                        ? "safe to propose"
                        : inv.decision.action === "ESCALATE"
                          ? "send to a person"
                          : inv.decision.action.toLowerCase()}
                    </span>
                  </span>
                </div>
              )}

              {inv.escalation && (
                <div className="border-t border-attention/30 bg-attention/10 px-4 py-3 text-xs">
                  <span className="font-semibold text-attention">
                    Sent to a person
                  </span>
                  <p className="mt-1 text-text-muted">
                    {ESCALATION_REASON[inv.escalation.reason ?? ""] ??
                      "The evidence wasn't conclusive."}
                  </p>
                  {inv.escalation.question && (
                    <p className="mt-1.5 font-medium text-text">
                      {inv.escalation.question}
                    </p>
                  )}
                </div>
              )}
            </motion.div>
          ))}
        </AnimatePresence>
      </div>

      {done && (
        <motion.div
          initial={{ opacity: 0, y: reduce ? 0 : 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={t}
          className="mt-10 rounded-lg border border-positive/30 bg-positive/5 p-5 text-center"
        >
          <p className="text-sm font-medium text-positive">
            Reconciliation complete. The audit trail is sealed.
          </p>
          {scorecard && (
            <div className="mx-auto mt-3 flex max-w-md flex-wrap justify-center gap-x-6 gap-y-1 text-xs text-text-muted">
              <span>
                <span className="font-mono text-text">
                  {(scorecard.matching.auto_match_rate * 100).toFixed(1)}%
                </span>{" "}
                verified automatically
              </span>
              <span>
                <span className="font-mono text-text">
                  {(scorecard.matching.false_match_rate * 100).toFixed(2)}%
                </span>{" "}
                false matches
              </span>
              {scorecard.safety && (
                <span>
                  <span className="font-mono text-text">
                    {scorecard.safety.unsafe_auto_resolutions}
                  </span>{" "}
                  unsafe auto-resolutions
                </span>
              )}
              <span>
                {scorecard.determinism.replay_hash_match
                  ? "reproducible"
                  : "not reproducible"}
              </span>
            </div>
          )}
          <Button asChild variant="primary" className="mt-4">
            <Link href={`/runs/${runId}`}>Open the cockpit</Link>
          </Button>
        </motion.div>
      )}

      {error && !done && (
        <div className="mt-8 rounded-md border border-attention/30 bg-attention/5 p-4 text-center text-sm">
          {error}
        </div>
      )}
    </AppShell>
  );
}

function TurnText({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  const long = text.length > 440;
  const shown = open || !long ? text : text.slice(0, 420).trimEnd() + "…";
  return (
    <p className="text-text">
      {shown}
      {long && (
        <button
          onClick={() => setOpen((o) => !o)}
          className="ml-1 whitespace-nowrap text-accent hover:underline"
        >
          {open ? "less" : "more"}
        </button>
      )}
    </p>
  );
}

function PhaseRail({ phase, seen }: { phase: Phase; seen: Set<Phase> }) {
  return (
    <div className="flex items-center gap-2 overflow-x-auto pb-1">
      {PHASES.map((p, i) => {
        const active = p === phase;
        const past = seen.has(p) && !active;
        return (
          <div key={p} className="flex flex-1 items-center gap-2">
            <div className="flex flex-none items-center gap-1.5">
              <span
                className={cn(
                  "size-2 rounded-full transition-colors [transition-duration:150ms]",
                  active
                    ? "bg-accent"
                    : past
                      ? "bg-positive"
                      : "bg-border",
                )}
              />
              <span
                className={cn(
                  "whitespace-nowrap text-xs",
                  active ? "font-medium text-text" : "text-text-muted",
                )}
              >
                {PHASE_LABEL[p]}
              </span>
            </div>
            {i < PHASES.length - 1 && (
              <div className="h-px min-w-3 flex-1 bg-border" />
            )}
          </div>
        );
      })}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-border bg-surface px-3 py-2.5">
      <div className="text-lg font-semibold tabular-nums">
        {value.toLocaleString("en-IN")}
      </div>
      <div className="mt-0.5 text-xs text-text-muted">{label}</div>
    </div>
  );
}

function foldInvestigations(frames: StreamFrame[]): Investigation[] {
  const byId = new Map<string, Investigation>();
  const order: string[] = [];
  const ensure = (id: string): Investigation => {
    let inv = byId.get(id);
    if (!inv) {
      inv = { id, category: null, impactMinor: null, turns: [] };
      byId.set(id, inv);
      order.push(id);
    }
    return inv;
  };
  for (const f of frames) {
    const id = f.exception_id ?? undefined;
    if (f.type === "EXCEPTION_OPENED" && id) {
      const inv = ensure(id);
      inv.category = f.category ?? inv.category;
      inv.impactMinor = f.impact_minor ?? inv.impactMinor;
    } else if (f.type === "AGENT_INVESTIGATION_STARTED" && id) {
      ensure(id).category = f.category ?? ensure(id).category;
    } else if (f.type === "AGENT_INTERACTION" && id) {
      const inv = ensure(id);
      const j = f.text ? readJsonTurn(f.text) : null;
      if (j && j.kind === "proposal") {
        inv.proposal = {
          category: (j.category as string) ?? null,
          explanation: (j.explanation as string) ?? "",
          grounded:
            typeof j.confidence === "number" ? (j.confidence as number) : null,
        };
      } else if (j && typeof j.supported === "boolean") {
        inv.verifier = {
          supported: j.supported as boolean,
          reason: (j.reason as string) ?? "",
        };
      } else {
        const clean = cleanTurn(f.text ?? "");
        if (clean || (f.tool_calls && f.tool_calls.length))
          inv.turns.push({ text: clean, tools: f.tool_calls ?? [] });
      }
    } else if (f.type === "AGENT_PROPOSAL_CREATED" && id) {
      const inv = ensure(id);
      inv.proposal = {
        category: f.category ?? null,
        explanation: f.explanation ?? "",
        grounded: f.grounded_confidence ?? null,
      };
      if (f.decision) inv.decision = f.decision;
    } else if (f.type === "AGENT_ESCALATED" && id) {
      const inv = ensure(id);
      inv.escalation = { question: f.question ?? "", reason: f.reason ?? null };
      if (f.decision) inv.decision = f.decision;
    }
  }
  return order
    .map((id) => byId.get(id)!)
    .filter(
      (inv) =>
        inv.turns.length > 0 ||
        inv.proposal ||
        inv.verifier ||
        inv.escalation ||
        inv.decision,
    )
    .reverse();
}
