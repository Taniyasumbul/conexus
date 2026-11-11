/* Typed client for the CoNexus FastAPI backend. Types mirror conexus/models.py. */

export type Status = "analyzed" | "awaiting_reply" | "awaiting_human" | "signed" | "closed";
export type RiskLevel = "low" | "medium" | "high";
export type EscalationKind = "risky_clause" | "redline_rejected" | "new_legal_terms" | "no_deal_high_value" | "value_limit" | "none";

export interface Terms { price: number; payment_days: number; term_months: number }
export interface DealContext { customer: string; segment: string; region: string; product: string; seats: number; list_price: number }
export interface Clause { id: string; type: string; heading: string; text: string; type_confidence: number }
export interface ClauseRisk {
  clause_id: string; clause_type: string; level: RiskLevel; score: number; requires_human: boolean;
  redlinable: boolean; redline: string | null; reasons: string[]; source: string;
}
export interface PricingPlan {
  anchor: Terms; target: Terms; floor_price: number; concession_limit: number; max_payment_days: number;
  wtp_estimate: number | null; evidence: string[];
}
export interface DealRecord { deal_id: string; segment: string; region: string; product: string; seats: number; list_price: number; final_price: number; payment_days: number; term_months: number; won: boolean; rounds: number }
export interface Offer { round: number; sender: "us" | "them"; terms: Terms | null; message: string; accept: boolean; walk_away: boolean; redline_responses: Record<string, boolean>; new_legal_terms: boolean }
export interface Escalation { escalate: boolean; stage: string; kind: EscalationKind; triggers: string[]; score: number; clause_ids: string[] }
export interface HumanDecision { approve: boolean; reviewer: string; note: string }
export interface Outcome { status: string; final_terms: Terms | null; rounds: number; escalation: Escalation | null; signed_unreviewed_risky_clauses: number; accepted_redlines: string[]; envelope_id: string | null }

export interface ContractState {
  id: string; contract_id: string; mode: "none" | "simulated" | "email"; filename: string | null; created_at: number; updated_at: number;
  context: DealContext; status: Status; clauses: Clause[]; risks: ClauseRisk[]; opening_terms: Terms | null; plan: PricingPlan | null;
  similar_deals: DealRecord[]; history: Offer[]; pending_redlines: string[]; last_sent_redlines: string[];
  redline_results: Record<string, boolean>; reviewed_clauses: string[]; round: number; their_last: Terms | null;
  last_our_offer: Terms | null; agreed_terms: Terms | null; escalation: Escalation | null; human_decisions: HumanDecision[]; outcome: Outcome | null;
}
export interface ContractSummary {
  id: string; customer: string; status: Status; mode: string; segment: string; list_price: number; round: number;
  outcome: string | null; price: number | null; risky_clauses: number; escalation: EscalationKind | null; updated_at: number;
}
export interface InboxItem {
  id: string; customer: string; escalation: Escalation; terms: Terms | null; flagged: ClauseRisk[]; clauses: Record<string, string>; updated_at: number;
}
export interface AuditEvent { seq: number; ts: number; contract_id: string | null; agent: string; action: string; rationale: string; data: unknown; prev_hash: string; hash: string }
export interface Metrics {
  contracts: number; by_status: Partial<Record<Status, number>>; signed: number; awaiting_human: number; signed_value: number;
  avg_rounds_signed: number | null; avg_discount_signed: number | null; escalation_rate: number | null; unreviewed_risky_signed: number; crm_memory_size: number;
}
export interface Sample { id: string; customer: string; segment: string; region: string; product: string; seats: number; list_price: number; expert_should_escalate: boolean; scenario: { wtp: number; persona: string } }
export interface Verify { ok: boolean; message: string; events: number; head: string }
export interface EvalResults { eval_escalation: any | null; eval_negotiation: any | null }
export interface Health { ok: boolean; llm: string; contracts: number }

export interface AnnotateItem { clause_id: string; text: string; contract: string; type: string; position: number; queue_size: number; labelled_by_others: number; done?: boolean }
export interface AnnotateReveal { categories: string[]; proxy_human: boolean | null; model: { requires_human: boolean; score: number; reasons: string[] } }
export interface AnnotateStats {
  queue_size: number; clauses_labelled: number; labels: number; per_annotator: Record<string, number>;
  pairs: { a: string; b: string; overlap: number; agreement: number | null; kappa: number | null }[];
  adjudicated: number; positives: number; proxy_agreement: number | null; model_agreement: number | null; export_path: string;
}
export interface AnnotationInput { clause_id: string; annotator: string; requires_human: boolean | null; level: RiskLevel | null; redlinable: boolean | null; note: string }

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method };
  if (body instanceof FormData) init.body = body;
  else if (body !== undefined) { init.body = JSON.stringify(body); init.headers = { "content-type": "application/json" }; }
  let res: Response;
  try {
    res = await fetch(path, init);
  } catch {
    throw new ApiError(0, "Can't reach the CoNexus API. Start it with `make api` (port 8000).");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail ?? detail; } catch { /* not json */ }
    throw new ApiError(res.status, typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => req<Health>("GET", "/health"),
  metrics: () => req<Metrics>("GET", "/api/metrics"),
  contracts: () => req<ContractSummary[]>("GET", "/api/contracts"),
  contract: (id: string) => req<ContractState>("GET", `/api/contracts/${id}`),
  createContract: (form: FormData) => req<ContractState>("POST", "/api/contracts", form),
  negotiate: (id: string, body: { mode: "simulated" | "email"; persona?: string; wtp?: number; delay_s?: number; counterparty_email?: string }) =>
    req<ContractState>("POST", `/api/contracts/${id}/negotiate`, body),
  reply: (id: string, message: string) => req<ContractState>("POST", `/api/contracts/${id}/reply`, { message }),
  decide: (id: string, d: HumanDecision) => req<ContractState>("POST", `/api/contracts/${id}/decision`, d),
  inbox: () => req<InboxItem[]>("GET", "/api/escalations"),
  audit: (id: string) => req<AuditEvent[]>("GET", `/api/contracts/${id}/audit`),
  auditAll: (limit = 200) => req<AuditEvent[]>("GET", `/api/audit?limit=${limit}`),
  verify: () => req<Verify>("GET", "/api/audit/verify"),
  samples: () => req<Sample[]>("GET", "/api/samples"),
  evals: () => req<EvalResults>("GET", "/api/eval"),
  annotateNext: (annotator: string) => req<AnnotateItem>("GET", `/api/annotate/next?annotator=${encodeURIComponent(annotator)}`),
  annotate: (a: AnnotationInput) => req<AnnotateReveal>("POST", "/api/annotate", a),
  annotateStats: () => req<AnnotateStats>("GET", "/api/annotate/stats"),
  outbox: () => req<{ to: string; subject: string; body: string; ts: number }[]>("GET", "/api/outbox"),
};

/* ---------------------------------------------------------------- formatting */
export const money = (n: number | null | undefined, compact = false) =>
  n == null ? "—" : new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0, notation: compact ? "compact" : "standard" }).format(n);
export const pct = (n: number | null | undefined, digits = 0) => (n == null ? "—" : `${(n * 100).toFixed(digits)}%`);
export const when = (ts: number) => new Date(ts * 1000).toLocaleString(undefined, { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
export const ago = (ts: number) => {
  const s = Math.max(0, Date.now() / 1000 - ts);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return `${Math.floor(s / 86400)} d ago`;
};
const ACRONYMS: Record<string, string> = { smb: "SMB", ip: "IP", us: "US", eu: "EU", apac: "APAC", llm: "LLM" };
export const titleCase = (s: string) =>
  s.split("_").map((w) => ACRONYMS[w.toLowerCase()] ?? w.charAt(0).toUpperCase() + w.slice(1)).join(" ");
