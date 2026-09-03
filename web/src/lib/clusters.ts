// Client-side mirror of arbiter_engine.exceptions.cluster (spec §24).
// Deterministic root-cause grouping of a run's open exceptions so the cockpit
// shows "5 causes, ₹X each" instead of one long list. Kept in lock-step with
// the Python module — same key, same ordering.
import type { ReconException } from "./api";

const OPEN = new Set([
  "open",
  "proposed",
  "escalated",
  "security_review",
  "budget_exceeded",
]);

const BANDS: [number, string][] = [
  [1_000_00, "<₹1k"],
  [10_000_00, "₹1k–₹10k"],
  [1_00_000_00, "₹10k–₹1L"],
  [10_00_000_00, "₹1L–₹10L"],
];

function band(minor: number): string {
  const a = Math.abs(minor);
  for (const [ceil, label] of BANDS) if (a < ceil) return label;
  return "₹10L+";
}

function direction(minor: number): string {
  return minor < 0 ? "short" : minor > 0 ? "over" : "flat";
}

function ruleId(by: string): string {
  if (by.startsWith("rule:")) return by.slice(5);
  if (by.startsWith("human:")) return "human-corrected";
  return by || "unclassified";
}

export interface Cluster {
  headline: string;
  category: string;
  count: number;
  grossMinor: number;
  netMinor: number;
  exampleId: string;
}

export function clusterExceptions(exceptions: ReconException[]): Cluster[] {
  const buckets = new Map<string, ReconException[]>();
  for (const e of exceptions) {
    if (!OPEN.has(e.status)) continue;
    const cat = e.category ?? "UNCLASSIFIED";
    const key = `${cat} · ${ruleId(e.classified_by)} · ${direction(
      e.amount_impact_minor,
    )} · ${band(e.amount_impact_minor)}`;
    const bucket = buckets.get(key);
    if (bucket) bucket.push(e);
    else buckets.set(key, [e]);
  }
  const out: Cluster[] = [];
  for (const [headline, members] of buckets) {
    const sorted = [...members].sort(
      (a, b) =>
        Math.abs(b.amount_impact_minor) - Math.abs(a.amount_impact_minor) ||
        a.id.localeCompare(b.id),
    );
    const lead = sorted[0]!;
    out.push({
      headline,
      category: lead.category ?? "UNCLASSIFIED",
      count: members.length,
      grossMinor: members.reduce(
        (s, m) => s + Math.abs(m.amount_impact_minor),
        0,
      ),
      netMinor: members.reduce((s, m) => s + m.amount_impact_minor, 0),
      exampleId: lead.id,
    });
  }
  return out.sort(
    (a, b) =>
      b.grossMinor - a.grossMinor || a.headline.localeCompare(b.headline),
  );
}
