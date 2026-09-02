// Thin typed client for the Arbiter API (docs/20 §1).
// On the client the Next rewrite proxies /api/* to the FastAPI backend; on the
// server we call the backend directly (relative URLs don't resolve in RSC fetch).
// Computed per call so the runtime environment (not the bundle-time one) decides.
function base(): string {
  if (typeof window !== "undefined") return "/api";
  return process.env.ARBITER_API_URL ?? "http://127.0.0.1:8000";
}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${base()}${path}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`${r.status} ${path}`);
  return (await r.json()) as T;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${base()}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${r.status} ${path}`);
  return (await r.json()) as T;
}

export interface RunSummary {
  run_id: string;
  status: string | null;
  records: number;
  matches: number;
  exceptions: number;
  matched_records?: number;
  terminal_hash?: string;
  by_source?: Record<string, number>;
}

export interface Scorecard {
  matching: {
    auto_match_rate: number;
    precision: number;
    recall: number;
    false_match_rate: number;
    dollar_coverage: number;
    dollar_unexplained: number;
    true_matches: number;
    correct_matches: number;
    by_pass?: Record<string, number>;
  };
  exceptions: {
    total: number;
    by_type: Record<string, number>;
    category_accuracy: number;
    detected_anomalies: number;
    total_anomalies: number;
  };
  throughput: { records_per_sec: number };
  determinism: { replay_hash_match: boolean };
  agent: {
    enabled: boolean;
    model: string;
    investigations: number;
    proposals: number;
    escalations: number;
    task_completion_rate: number;
    category_accuracy: number;
    escalation_precision: number;
    escalation_recall: number;
    hallucination_rate: number;
    grounded_rate?: number;
    confidence_ece?: number;
    confidence_n?: number;
    est_cost_usd: number;
  };
}

export interface ReconException {
  id: string;
  category: string | null;
  classified_by: string;
  amount_impact_minor: number;
  impact_display?: string;
  confidence: number | null;
  record_ids: string[];
  status: string;
  candidates: unknown[];
  agent_proposal: Record<string, unknown> | null;
  agent_escalation: Record<string, unknown> | null;
  resolution: Record<string, string> | null;
}

export interface EvidenceDrawer {
  exception: ReconException;
  records: Array<Record<string, unknown> & { id: string; source: string; kind: string; amount_display: string }>;
  decompositions: Array<{
    settlement_utr: string | null;
    expected_minor: number;
    actual_minor: number;
    residual_minor: number;
    ledger_crosscheck_ok: boolean;
    components: Record<string, number>;
  }>;
  candidates: Array<{ hypothesis: string; score_bits: number; record_ids: string[] }>;
  agent_proposal: Record<string, unknown> | null;
  agent_escalation: Record<string, unknown> | null;
  agent_trace?: Array<{
    turn: number | null;
    text: string;
    tool_calls: string[];
    stop_reason: string | null;
  }>;
}

export const api = {
  listRuns: () => get<{ runs: RunSummary[] }>("/v1/runs"),
  listSpecs: () => get<{ specs: { name: string; path: string }[] }>("/v1/specs"),
  listDatasets: () => get<{ datasets: { name: string; path: string }[] }>("/v1/datasets"),
  startRun: (spec: string, dataset: string, no_ai = false) =>
    post<RunSummary>("/v1/runs", { spec, dataset, no_ai }),
  run: (id: string) => get<RunSummary>(`/v1/runs/${id}`),
  scorecard: (id: string) => get<Scorecard>(`/v1/runs/${id}/scorecard`),
  exceptions: (id: string) => get<{ total: number; exceptions: ReconException[] }>(`/v1/runs/${id}/exceptions`),
  drawer: (runId: string, excId: string) => get<EvidenceDrawer>(`/v1/exceptions/${runId}/${excId}`),
  resolve: (runId: string, excId: string, action: string, detail: string) =>
    post<{ ok: boolean }>(`/v1/exceptions/${runId}/${excId}/resolve`, { action, detail }),
  verify: (id: string) => get<{ intact: boolean; events: number; terminal_hash: string }>(`/v1/runs/${id}/verify`),
};

export function rupees(minor: number): string {
  const sign = minor < 0 ? "-" : "";
  const n = Math.abs(minor) / 100;
  return `${sign}₹${n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}
