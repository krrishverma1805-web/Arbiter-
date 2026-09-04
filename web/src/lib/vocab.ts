// Plain-language layer. Every raw enum the engine emits gets a human phrase and,
// where it helps, a one-line "what this means". The cockpit never shows a bare
// code — it shows the phrase, and keeps the code as a hover / technical detail.
import { rupees, type ReconException } from "./api";

/* ── exception categories ─────────────────────────────────────────────────── */

export const CATEGORY_LABEL: Record<string, string> = {
  TIMING: "Settlement timing",
  WRONG_ACCOUNT: "Wrong account",
  DUPLICATE: "Duplicate payment",
  CHARGEBACK: "Chargeback",
  SECURITY_REVIEW: "Security review",
  FEE_DEDUCTION: "Fee deduction",
  ROUNDING: "Rounding",
  UNEXPLAINED: "Unexplained",
};

export const CATEGORY_BLURB: Record<string, string> = {
  TIMING: "Money that landed in a different period than the books expected.",
  WRONG_ACCOUNT: "A payout that reached an account the ledger doesn't recognise.",
  DUPLICATE: "The same payment looks to have been credited more than once.",
  CHARGEBACK: "A customer reversal the bank took back out of the settlement.",
  SECURITY_REVIEW: "Held while a security check runs. Not a money problem yet.",
  FEE_DEDUCTION: "The processor kept a different fee than the schedule says.",
  ROUNDING: "A sub-rupee difference from rounding. Usually safe to accept.",
  UNEXPLAINED: "The automated checks and the AI could not account for this gap.",
};

export function categoryLabel(cat: string | null | undefined): string {
  if (!cat) return "Unclassified";
  return CATEGORY_LABEL[cat] ?? cat.replace(/_/g, " ").toLowerCase();
}

/** Tone for a category chip — maps to Badge variants. */
export function categoryTone(
  cat: string | null | undefined,
): "neutral" | "accent" | "attention" | "critical" {
  switch (cat) {
    case "SECURITY_REVIEW":
    case "UNEXPLAINED":
      return "critical";
    case "CHARGEBACK":
    case "WRONG_ACCOUNT":
      return "attention";
    case "TIMING":
      return "accent";
    default:
      return "neutral";
  }
}

/* ── status ──────────────────────────────────────────────────────────────── */

export const STATUS_LABEL: Record<string, string> = {
  open: "Needs review",
  proposed: "Proposal ready",
  escalated: "Escalated to you",
  security_review: "Security hold",
  budget_exceeded: "Ran out of budget",
  resolved: "Resolved",
  wont_fix: "Won't fix",
};

export function statusLabel(s: string): string {
  return STATUS_LABEL[s] ?? s.replace(/_/g, " ");
}

export function statusTone(
  s: string,
): "neutral" | "accent" | "positive" | "attention" | "critical" {
  switch (s) {
    case "resolved":
      return "positive";
    case "proposed":
      return "accent";
    case "escalated":
    case "budget_exceeded":
      return "attention";
    case "security_review":
      return "critical";
    default:
      return "neutral";
  }
}

/* ── resolution actions ──────────────────────────────────────────────────── */

export interface ActionSpec {
  key: string;
  label: string;
  hint: string;
  tone: "primary" | "secondary" | "ghost" | "danger";
}

export const ACTIONS: ActionSpec[] = [
  {
    key: "accept_variance",
    label: "Accept the difference",
    hint: "Book the gap as expected and close this.",
    tone: "primary",
  },
  {
    key: "carry_forward",
    label: "Carry forward",
    hint: "Expect this to settle in the next cycle.",
    tone: "secondary",
  },
  {
    key: "flag_overcharge",
    label: "Flag as overcharge",
    hint: "The processor kept more than agreed. Raise it with them.",
    tone: "secondary",
  },
  {
    key: "raise_dispute",
    label: "Raise a dispute",
    hint: "Open a formal dispute with the counterparty.",
    tone: "secondary",
  },
  {
    key: "request_data",
    label: "Request more data",
    hint: "Ask for the missing file or reference before deciding.",
    tone: "secondary",
  },
  {
    key: "route_to_human",
    label: "Send to a colleague",
    hint: "Hand this to someone with more context.",
    tone: "ghost",
  },
  {
    key: "wont_fix",
    label: "Won't fix",
    hint: "Acknowledge and leave it. Feeds a future rule.",
    tone: "ghost",
  },
];

export function actionLabel(key: string): string {
  return ACTIONS.find((a) => a.key === key)?.label ?? key.replace(/_/g, " ");
}

/* ── who flagged it ──────────────────────────────────────────────────────── */

export function classifiedByLabel(by: string): string {
  if (!by || by === "unclassified") return "Not yet classified";
  if (by.startsWith("human:")) return "Set by a person";
  if (by.startsWith("rule:")) return "Auto-flagged by a rule";
  if (by === "agent") return "Classified by the AI";
  return by;
}

/* ── matching passes ─────────────────────────────────────────────────────── */

export const PASS_LABEL: Record<string, string> = {
  exact: "exact match",
  tolerant: "within tolerance",
  subset_heuristic: "grouped settlement",
  blocked: "needed review",
};

/* ── a synthesized plain-English summary of an exception ──────────────────── */

/** One sentence a controller can act on, built from what we know without the
 *  full evidence drawer. `residualMinor` (from the decomposition) sharpens it
 *  when available. */
export function plainSummary(
  e: ReconException,
  residualMinor?: number | null,
): string {
  const n = e.record_ids?.length ?? 0;
  const amt = e.impact_display ?? rupees(e.amount_impact_minor);
  const many = n > 1 ? `${n} payments` : "One payment";

  switch (e.category) {
    case "TIMING":
      return `${many} settled in a later period than the books expected. ${amt} lands next cycle.`;
    case "WRONG_ACCOUNT":
      return `${many} paid out to an account the ledger doesn't recognise. ${amt} at stake.`;
    case "DUPLICATE":
      return `${many} where the settlement is short ${
        residualMinor != null ? rupees(Math.abs(residualMinor)) : amt
      } against what was expected. Looks like a double credit.`;
    case "FEE_DEDUCTION":
      return `The processor kept ${amt} ${
        e.amount_impact_minor >= 0 ? "more" : "less"
      } in fees than the schedule says.`;
    case "CHARGEBACK":
      return `${amt} pulled back out of the settlement as a customer reversal.`;
    case "SECURITY_REVIEW":
      return `Held while a security check runs. ${amt} on hold, no money problem confirmed.`;
    case "ROUNDING":
      return `A ${amt} rounding difference. Usually safe to accept.`;
    case "UNEXPLAINED":
      return `Settlement is off by ${amt} and neither the checks nor the AI could explain it. Needs you.`;
    default:
      return `${amt} difference to review across ${n} record${n === 1 ? "" : "s"}.`;
  }
}

/* ── settlement decomposition components ──────────────────────────────────── */

export const COMPONENT_LABEL: Record<string, string> = {
  gross: "Gross payments",
  mdr: "Processor fee",
  gst_on_mdr: "GST on the fee",
  refunds: "Refunds",
  adjustment_credits: "Adjustments (credit)",
  adjustment_debits: "Adjustments (debit)",
  chargebacks: "Chargebacks",
  reserves: "Reserve held back",
};

export function componentLabel(k: string): string {
  return COMPONENT_LABEL[k] ?? k.replace(/_/g, " ");
}

/** Components that add to the payout vs. those that subtract. */
export function componentSign(k: string): 1 | -1 {
  return k === "gross" || k === "adjustment_credits" ? 1 : -1;
}

/* ── agent investigation steps ───────────────────────────────────────────── */

export const STEP_LABEL: Record<string, string> = {
  plan: "What the AI set out to check",
  evidence: "Evidence it pulled",
  reason: "What it found",
  proposal: "What it proposed",
  safety: "Safety check",
  escalation: "Why it stopped and asked you",
};

export const ESCALATION_REASON: Record<string, string> = {
  verifier_rejected:
    "A second, independent model disagreed that the evidence supports the conclusion.",
  contradictory: "A cited record doesn't exist in this run.",
  evidence_exhausted: "The evidence wasn't strong enough to be sure.",
  counterfactual_contradicted:
    "The arithmetic check refuted the proposed cause.",
  material_risk:
    "The amount is large and the conclusion was plausible, not certain.",
  inconsistent: "Repeated investigations didn't agree on a cause.",
  budget: "The investigation ran out of steps before reaching a confident answer.",
  confidence_in_uncertain_band: "Confidence landed in the band that requires a person.",
  provider_unavailable: "The model was unavailable.",
};

/* ── source names ────────────────────────────────────────────────────────── */

export const SOURCE_LABEL: Record<string, string> = {
  ledger: "Your ledger",
  razorpay_recon: "Razorpay",
  bank: "Bank statement",
};

export function sourceLabel(s: string): string {
  return SOURCE_LABEL[s] ?? s.replace(/_/g, " ");
}
