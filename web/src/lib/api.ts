// Thin typed client for the Arbiter API (docs/20 §1).
// On the client the Next rewrite proxies /api/* to the FastAPI backend; on the
// server we call the backend directly (relative URLs don't resolve in RSC fetch).
// Computed per call so the runtime environment (not the bundle-time one) decides.
function base(): string {
  if (typeof window !== "undefined") return "/api";
  // Server components can't use a relative URL. Prefer a configured API, else
  // hit this same deployment's route handlers (Vercel sets VERCEL_URL), else
  // localhost for `make up`.
  if (process.env.ARBITER_API_URL) return process.env.ARBITER_API_URL;
  // the stable production alias isn't behind deployment protection; VERCEL_URL is
  const v = process.env.VERCEL_PROJECT_PRODUCTION_URL;
  if (v) return `https://${v}/api`;
  return "http://127.0.0.1:8000";
}

// The cockpit's API key (prod). Dev (`ARBITER_ENV=dev`) needs none. Set it via
// the ⌘K palette → "Set API key"; it lives only in this browser.
export function apiKey(): string | null {
  if (typeof window === "undefined") return process.env.ARBITER_API_KEY ?? null;
  try {
    return localStorage.getItem("arbiter-key");
  } catch {
    return null;
  }
}
export function setApiKey(key: string | null): void {
  try {
    if (key) localStorage.setItem("arbiter-key", key);
    else localStorage.removeItem("arbiter-key");
  } catch {
    /* private mode */
  }
}

function authHeaders(): Record<string, string> {
  const k = apiKey();
  return k ? { authorization: `Bearer ${k}` } : {};
}

// Bring-your-own LLM key: provider + key + model, stored only in this browser and
// sent as headers on POST /v1/runs — used for that one run, never persisted.
export interface LlmConfig {
  provider: "openai" | "anthropic";
  key: string;
  model?: string;
}
export function llmConfig(): LlmConfig | null {
  try {
    const raw = localStorage.getItem("arbiter-llm");
    return raw ? (JSON.parse(raw) as LlmConfig) : null;
  } catch {
    return null;
  }
}
export function setLlmConfig(c: LlmConfig | null): void {
  try {
    if (c && c.key) localStorage.setItem("arbiter-llm", JSON.stringify(c));
    else localStorage.removeItem("arbiter-llm");
  } catch {
    /* private mode */
  }
}
function llmHeaders(): Record<string, string> {
  const c = llmConfig();
  if (!c || !c.key) return {};
  const h: Record<string, string> = {
    "x-llm-provider": c.provider,
    "x-llm-key": c.key,
  };
  if (c.model) h["x-llm-model"] = c.model;
  return h;
}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${base()}${path}`, {
    cache: "no-store",
    headers: authHeaders(),
  });
  if (!r.ok) throw new Error(`${r.status} ${path}`);
  return (await r.json()) as T;
}

async function post<T>(
  path: string,
  body: unknown,
  extra: Record<string, string> = {},
): Promise<T> {
  const r = await fetch(`${base()}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json", ...authHeaders(), ...extra },
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
  safety?: {
    replay_divergence: boolean;
    unsafe_auto_resolutions: number;
    items_needing_human: number;
    unsafe_resolution_rate: number;
    rupees_protected_minor: number;
    rupees_at_risk_minor: number;
    rupees_protected_rate: number;
    fabricated_citations: number;
    injection_quarantined: number;
  };
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
    calibration_model?: string | null;
    prompt_hash?: string | null;
    insufficient_eval_data?: boolean;
    est_cost_usd: number | null;
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
  /** total records behind this exception; `records` may be a capped sample */
  _record_total?: number;
  records: Array<
    Record<string, unknown> & {
      id: string;
      source: string;
      kind: string;
      amount_display: string;
    }
  >;
  decompositions: Array<{
    settlement_utr: string | null;
    expected_minor: number;
    actual_minor: number;
    residual_minor: number;
    ledger_crosscheck_ok: boolean;
    components: Record<string, number>;
  }>;
  candidates: Array<{
    hypothesis: string;
    score_bits: number;
    record_ids: string[];
  }>;
  agent_proposal: Record<string, unknown> | null;
  agent_escalation: Record<string, unknown> | null;
  agent_trace?: Array<{
    turn: number | null;
    text: string;
    tool_calls: string[];
    stop_reason: string | null;
    role?: string | null;
  }>;
  agent_investigation?: AgentInvestigation | null;
}

export interface SafetyDecision {
  action: "SAFE" | "PROPOSE" | "ESCALATE" | "QUARANTINE";
  risk: string;
  risk_label?: string;
  reasons: string[];
  grounded_confidence?: number;
  detail?: string;
  escalation_reason?: string | null;
  policy_version?: string;
}

export interface InvestigationStep {
  kind:
    | "plan"
    | "evidence"
    | "reason"
    | "proposal"
    | "escalation"
    | "safety";
  title: string;
  body?: string | null;
  model?: string | null;
  tools?: Array<{ name: string; args: Record<string, unknown> }>;
  category?: string | null;
  hypotheses_tested?: string[];
  suggested_action?: string | null;
  stated_confidence?: number | null;
  grounded_confidence?: number | null;
  citations_resolved?: string;
  fabricated?: string[];
  reason?: string | null;
  what_i_know?: string | null;
  what_is_missing?: string | null;
  action?: string;
  risk?: string;
  risk_label?: string;
  reasons?: string[];
  policy_version?: string;
}

export interface AgentInvestigation {
  steps: InvestigationStep[];
  outcome: "proposal" | "escalate";
  decision: SafetyDecision | null;
  tokens_in: number;
  tokens_out: number;
  tool_calls: number;
}

export interface StreamFrame {
  seq: number;
  type: string;
  ts?: string;
  exception_id?: string | null;
  category?: string | null;
  turn?: number | null;
  text?: string;
  tool_calls?: string[];
  stop_reason?: string | null;
  explanation?: string;
  grounded_confidence?: number | null;
  question?: string;
  reason?: string | null;
  impact_minor?: number | null;
  counts?: Record<string, number>;
  decision?: SafetyDecision | null;
}

// The cockpit runs in the browser, where the Next rewrite proxies /api/* to the
// backend; EventSource/WebSocket can't set headers, so the key rides the query.
export function streamUrl(runId: string): string {
  const k = apiKey();
  return `/api/v1/runs/${runId}/stream${k ? `?key=${encodeURIComponent(k)}` : ""}`;
}

export const api = {
  listRuns: () => get<{ runs: RunSummary[] }>("/v1/runs"),
  listSpecs: () =>
    get<{ specs: { name: string; path: string }[] }>("/v1/specs"),
  listDatasets: () =>
    get<{ datasets: { name: string; path: string }[] }>("/v1/datasets"),
  startRun: (spec: string, dataset: string, no_ai = false) =>
    post<RunSummary>("/v1/runs", { spec, dataset, no_ai }, llmHeaders()),
  run: (id: string) => get<RunSummary>(`/v1/runs/${id}`),
  scorecard: (id: string) => get<Scorecard>(`/v1/runs/${id}/scorecard`),
  exceptions: (id: string) =>
    get<{ total: number; exceptions: ReconException[] }>(
      `/v1/runs/${id}/exceptions`,
    ),
  drawer: (runId: string, excId: string) =>
    get<EvidenceDrawer>(`/v1/exceptions/${runId}/${excId}`),
  resolve: (runId: string, excId: string, action: string, detail: string) =>
    post<{ ok: boolean; demo?: boolean }>(
      `/v1/exceptions/${runId}/${excId}/resolve`,
      { action, detail },
    ),
  verify: (id: string) =>
    get<{ intact: boolean; events: number; terminal_hash: string }>(
      `/v1/runs/${id}/verify`,
    ),
  clusters: (id: string) => get<ClusterReport>(`/v1/runs/${id}/clusters`),
  attack: (spec: string, dataset: string, scenario?: string) =>
    post<AttackReport>("/v1/attack", { spec, dataset, scenario }),
};

export interface ClusterReport {
  cluster_count: number;
  total_gross_minor: number;
  total_net_minor: number;
  clusters: Array<{
    headline: string;
    count: number;
    gross_impact_minor: number;
    net_impact_minor: number;
    example_id: string;
    exception_ids: string[];
  }>;
}

export interface AttackScenario {
  scenario: string;
  description: string;
  attack_impact_minor: number;
  detected: boolean;
  rupees_unaccounted_minor: number;
  unsafe_auto_resolution: boolean;
  what_arbiter_did: string;
  verdict: "CONTAINED" | "PARTIAL" | "MISSED" | "UNSAFE";
}

export interface AttackReport {
  scenarios: AttackScenario[];
  contained: number;
  unsafe: number;
  rupees_unaccounted_minor: number;
}

export function rupees(minor: number): string {
  const sign = minor < 0 ? "-" : "";
  const n = Math.abs(minor) / 100;
  return `${sign}₹${n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}
