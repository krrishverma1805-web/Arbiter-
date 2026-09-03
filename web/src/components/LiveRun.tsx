"use client";

import Link from "next/link";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  streamUrl,
  rupees,
  type Scorecard,
  type StreamFrame,
} from "@/lib/api";

type Phase =
  "ingesting" | "matching" | "classifying" | "investigating" | "done";

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
  escalation?: { question: string; reason: string | null };
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
  const [counts, setCounts] = useState({
    records: 0,
    matches: 0,
    exceptions: 0,
  });
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
    // named SSE events + the default message event
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
      // the stream caps itself server-side; only surface a hard failure
      if (
        es.readyState === EventSource.CLOSED &&
        !seenPhases.current.has("done")
      ) {
        setError("stream ended — open the full cockpit");
        es.close();
      }
    };
    return () => es.close();
  }, [runId]);

  const investigations = useMemo(() => foldInvestigations(frames), [frames]);
  const spring = reduce
    ? { duration: 0 }
    : { type: "spring" as const, stiffness: 380, damping: 30 };

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <header className="flex items-baseline justify-between">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Reconciling</h1>
          <p className="mt-0.5 font-mono text-xs text-muted">
            {runId.slice(0, 8)}
          </p>
        </div>
        <Link
          href={`/runs/${runId}`}
          className="text-sm text-accent hover:underline"
        >
          {done ? "open cockpit →" : "skip to cockpit"}
        </Link>
      </header>

      <PhaseRail phase={phase} seen={seenPhases.current} />

      <div className="mt-3 grid grid-cols-3 gap-3">
        <Stat label="records" value={counts.records} />
        <Stat label="auto-tied" value={counts.matches} />
        <Stat label="exceptions" value={counts.exceptions} />
      </div>

      <div className="mt-8 space-y-3">
        <AnimatePresence initial={false}>
          {investigations.map((inv) => (
            <motion.div
              key={inv.id}
              layout
              initial={{ opacity: 0, y: reduce ? 0 : 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={spring}
              className="overflow-hidden rounded-xl border border-border bg-surface"
            >
              <div className="flex items-center justify-between px-4 py-3">
                <span className="text-sm font-medium">
                  {inv.category ?? "investigating…"}
                </span>
                {inv.impactMinor != null && (
                  <span className="font-mono text-xs text-muted">
                    {rupees(inv.impactMinor)}
                  </span>
                )}
              </div>

              <ol className="space-y-2 px-4 pb-3">
                <AnimatePresence initial={false}>
                  {inv.turns.map((t, i) => (
                    <motion.li
                      key={i}
                      initial={{ opacity: 0, x: reduce ? 0 : -8 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={spring}
                      className="border-l-2 border-accent/30 pl-3 text-xs leading-relaxed"
                    >
                      {t.text && <p className="text-text">{t.text}</p>}
                      {t.tools.length > 0 && (
                        <p className="mt-0.5 font-mono text-[11px] text-muted">
                          {t.tools.map((x) => `→ ${x}`).join("  ")}
                        </p>
                      )}
                    </motion.li>
                  ))}
                </AnimatePresence>
              </ol>

              {inv.proposal && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={spring}
                  className="border-t border-accent/20 bg-accent/5 px-4 py-3 text-xs"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-accent">
                      proposal · {inv.proposal.category}
                    </span>
                    {inv.proposal.grounded != null && (
                      <span className="font-mono">
                        {Math.round(inv.proposal.grounded * 100)}% grounded
                      </span>
                    )}
                  </div>
                  <p className="mt-1">{inv.proposal.explanation}</p>
                </motion.div>
              )}
              {inv.escalation && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={spring}
                  className="border-t border-attention/30 bg-attention/10 px-4 py-3 text-xs"
                >
                  <span className="font-semibold text-attention">
                    escalated · {inv.escalation.reason}
                  </span>
                  <p className="mt-1 font-medium">{inv.escalation.question}</p>
                </motion.div>
              )}
            </motion.div>
          ))}
        </AnimatePresence>
      </div>

      {done && (
        <motion.div
          initial={{ opacity: 0, y: reduce ? 0 : 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="mt-10 rounded-xl border border-positive/30 bg-positive/5 p-5 text-center"
        >
          <p className="text-sm font-medium text-positive">
            Run complete — chain sealed.
          </p>
          {scorecard && (
            <div className="mx-auto mt-3 flex max-w-md flex-wrap justify-center gap-x-6 gap-y-1 text-xs text-muted">
              <span>
                <span className="font-mono text-text">
                  {(scorecard.matching.auto_match_rate * 100).toFixed(1)}%
                </span>{" "}
                auto-tied
              </span>
              <span>
                <span className="font-mono text-text">
                  {(scorecard.matching.false_match_rate * 100).toFixed(2)}%
                </span>{" "}
                false-match
              </span>
              <span>
                <span className="font-mono text-text">
                  {(scorecard.matching.dollar_coverage * 100).toFixed(1)}%
                </span>{" "}
                ₹ coverage
              </span>
              <span>
                {scorecard.determinism.replay_hash_match ? "✓" : "✗"}{" "}
                deterministic
              </span>
            </div>
          )}
          <Link
            href={`/runs/${runId}`}
            className="mt-3 inline-block rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white"
          >
            Open the cockpit
          </Link>
        </motion.div>
      )}
      {error && !done && (
        <p className="mt-6 text-center text-sm text-muted">{error}</p>
      )}
    </div>
  );
}

function PhaseRail({ phase, seen }: { phase: Phase; seen: Set<Phase> }) {
  return (
    <div className="mt-6 flex items-center gap-2">
      {PHASES.map((p, i) => {
        const active = p === phase;
        const past = seen.has(p) && !active;
        return (
          <div key={p} className="flex flex-1 items-center gap-2">
            <div className="flex items-center gap-1.5">
              <motion.span
                animate={{ scale: active ? 1.15 : 1 }}
                className={`h-2 w-2 rounded-full ${
                  active ? "bg-accent" : past ? "bg-positive" : "bg-border"
                }`}
              />
              <span
                className={`text-xs ${active ? "text-text" : "text-muted"}`}
              >
                {p}
              </span>
            </div>
            {i < PHASES.length - 1 && <div className="h-px flex-1 bg-border" />}
          </div>
        );
      })}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-border bg-surface px-3 py-2">
      <motion.div
        key={value}
        initial={{ opacity: 0.4 }}
        animate={{ opacity: 1 }}
        className="text-lg font-semibold tabular-nums"
      >
        {value}
      </motion.div>
      <div className="text-[11px] text-muted">{label}</div>
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
      if ((f.text && f.text.trim()) || (f.tool_calls && f.tool_calls.length))
        inv.turns.push({ text: f.text ?? "", tools: f.tool_calls ?? [] });
    } else if (f.type === "AGENT_PROPOSAL_CREATED" && id) {
      ensure(id).proposal = {
        category: f.category ?? null,
        explanation: f.explanation ?? "",
        grounded: f.grounded_confidence ?? null,
      };
    } else if (f.type === "AGENT_ESCALATED" && id) {
      ensure(id).escalation = {
        question: f.question ?? "",
        reason: f.reason ?? null,
      };
    }
  }
  // only show exceptions the agent actually looked at, most recent first
  return order
    .map((id) => byId.get(id)!)
    .filter((inv) => inv.turns.length > 0 || inv.proposal || inv.escalation)
    .reverse();
}
