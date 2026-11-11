/* Nexus UI - domain components for contract negotiation. */
import { ReactNode, useMemo, useState } from "react";
import {
  AlertOctagon, Bot, CheckCheck, CircleDot, Copy, FileSearch, FileSignature, Gavel, Hand, Mail,
  MessageSquareReply, PenLine, ShieldAlert, ShieldCheck, Sparkles, TrendingUp, UserCheck, UserX, XCircle,
} from "lucide-react";
import type { AuditEvent, Clause, ClauseRisk, Offer, RiskLevel, Status, Terms } from "@lib/api";
import { money, titleCase } from "@lib/api";
import { Badge, Tone } from "./primitives";

/* ---------------------------------------------------------------- status */
const STATUS: Record<Status, { tone: Tone; label: string; icon: ReactNode }> = {
  analyzed: { tone: "neutral", label: "Analyzed", icon: <FileSearch /> },
  awaiting_reply: { tone: "info", label: "Negotiating", icon: <MessageSquareReply /> },
  awaiting_human: { tone: "critical", label: "Needs human", icon: <Hand /> },
  signed: { tone: "good", label: "Signed", icon: <FileSignature /> },
  closed: { tone: "neutral", label: "Closed", icon: <XCircle /> },
};
export function StatusBadge({ status }: { status: Status }) {
  const s = STATUS[status];
  return <Badge tone={s.tone} icon={s.icon}>{s.label}</Badge>;
}

const RISK: Record<RiskLevel, Tone> = { low: "good", medium: "warning", high: "critical" };
export function RiskBadge({ level, needsHuman }: { level: RiskLevel; needsHuman?: boolean }) {
  return (
    <>
      <Badge tone={RISK[level]} dot>{titleCase(level)}</Badge>
      {needsHuman && <Badge tone="critical" icon={<ShieldAlert />}>Needs human</Badge>}
    </>
  );
}

/* ---------------------------------------------------------------- score meter */
export function ScoreMeter({ score, threshold = 0.5, label }: { score: number; threshold?: number; label?: string }) {
  const tone = score >= threshold ? "var(--critical)" : score >= threshold * 0.6 ? "var(--warning)" : "var(--good)";
  return (
    <div className="nx-meter" title={`${label ?? "Risk score"} ${score.toFixed(2)} (threshold ${threshold})`}>
      <div className="nx-meter__track" role="meter" aria-valuemin={0} aria-valuemax={1} aria-valuenow={score} aria-label={label ?? "Risk score"}>
        <div className="nx-meter__fill" style={{ width: `${Math.min(100, score * 100)}%`, background: tone }} />
        <div className="nx-meter__mark" style={{ left: `calc(${threshold * 100}% - 1px)` }} />
      </div>
      <span className="nx-meter__value">{score.toFixed(2)}</span>
    </div>
  );
}

/* ---------------------------------------------------------------- redline diff */
function wordDiff(a: string, b: string) {
  const A = a.split(/(\s+)/), B = b.split(/(\s+)/);
  const n = A.length, m = B.length;
  const dp = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--)
    dp[i][j] = A[i] === B[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
  const out: { t: "same" | "del" | "ins"; s: string }[] = [];
  let i = 0, j = 0;
  const push = (t: "same" | "del" | "ins", s: string) => {
    const last = out[out.length - 1];
    if (last && last.t === t) last.s += s; else out.push({ t, s });
  };
  while (i < n && j < m) {
    if (A[i] === B[j]) { push("same", A[i]); i++; j++; }
    else if (dp[i + 1][j] >= dp[i][j + 1]) push("del", A[i++]);
    else push("ins", B[j++]);
  }
  while (i < n) push("del", A[i++]);
  while (j < m) push("ins", B[j++]);
  // Mostly rewritten? A word-level diff becomes unreadable - show one deletion and one insertion.
  const shared = out.filter((p) => p.t === "same" && p.s.trim()).reduce((k, p) => k + p.s.trim().split(/\s+/).length, 0);
  const words = Math.max(a.split(/\s+/).length, b.split(/\s+/).length);
  if (shared / words < 0.5) return [{ t: "del" as const, s: a }, { t: "same" as const, s: " " }, { t: "ins" as const, s: b }];
  return out;
}
export function RedlineDiff({ original, proposed, label = "Proposed redline" }: { original: string; proposed: string; label?: string }) {
  const parts = useMemo(() => wordDiff(original, proposed), [original, proposed]);
  return (
    <div className="nx-redline">
      <span className="nx-redline__label">{label}</span>
      {parts.map((p, i) => (p.t === "same" ? <span key={i}>{p.s}</span> : p.t === "del" ? <del key={i}>{p.s}</del> : <ins key={i}>{p.s}</ins>))}
    </div>
  );
}

/* ---------------------------------------------------------------- clause card */
export function ClauseCard({ clause, risk, reviewed, redlineStatus, defaultOpen, threshold }: {
  clause: Clause; risk: ClauseRisk; reviewed?: boolean; redlineStatus?: boolean; defaultOpen?: boolean; threshold?: number;
}) {
  const showRedline = risk.redline && risk.level !== "low";
  return (
    <details className="nx-clause" data-level={risk.level} open={defaultOpen}>
      <summary className="nx-clause__head">
        <span className="nx-clause__ref">§ {clause.id.replace("c", "")}</span>
        <span className="nx-clause__title">{clause.heading.replace(/^\d+\s*/, "") || titleCase(clause.type)}</span>
        <RiskBadge level={risk.level} needsHuman={risk.requires_human && !reviewed} />
        {reviewed && <Badge tone="good" icon={<UserCheck />}>Reviewed</Badge>}
        {redlineStatus === true && <Badge tone="good" icon={<CheckCheck />}>Redline accepted</Badge>}
        {redlineStatus === false && <Badge tone="serious" icon={<XCircle />}>Redline rejected</Badge>}
        <div style={{ width: 150 }}><ScoreMeter score={risk.score} threshold={threshold} /></div>
      </summary>
      <div className="nx-clause__body">
        <p className="nx-clause__text">{clause.text}</p>
        {risk.reasons.length > 0 && (
          <div>
            <span className="nx-eyebrow">Why it was flagged</span>
            <ul className="nx-reasons">{risk.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
          </div>
        )}
        {showRedline && <RedlineDiff original={clause.text} proposed={risk.redline!} label={risk.redlinable ? "Autonomous redline" : "Fallback position for reviewer"} />}
        <span className="nx-muted" style={{ fontSize: "var(--text-xs)" }}>
          Type {titleCase(clause.type)} · confidence {clause.type_confidence.toFixed(2)} · scored by {risk.source}
        </span>
      </div>
    </details>
  );
}

/* ---------------------------------------------------------------- terms chip */
export function TermsChips({ terms }: { terms: Terms }) {
  return (
    <div className="nx-msg__terms">
      <Badge tone="info" outline>{money(terms.price)}/yr</Badge>
      <Badge outline>net {terms.payment_days}</Badge>
      <Badge outline>{terms.term_months} mo</Badge>
    </div>
  );
}

/* ---------------------------------------------------------------- negotiation thread */
export function NegotiationThread({ history, customer }: { history: Offer[]; customer: string }) {
  return (
    <div className="nx-thread">
      {history.map((h, i) => {
        if (h.round === 0) return (
          <span key={i} className="nx-system-note"><FileSearch size={13} />Their paper opens at {h.terms ? `${money(h.terms.price)}/yr, net ${h.terms.payment_days}` : "no price"}</span>
        );
        const us = h.sender === "us";
        return (
          <div key={i} className={`nx-msg ${us ? "nx-msg--us" : "nx-msg--them"}`}>
            <span className="nx-msg__meta">
              {us ? <Bot size={13} /> : <Mail size={13} />}
              <b>{us ? "CoNexus" : customer}</b> · round {h.round}
              {h.accept && <Badge tone="good" icon={<CheckCheck />}>Accepts</Badge>}
              {h.walk_away && <Badge tone="critical">Walks away</Badge>}
              {h.new_legal_terms && <Badge tone="critical" icon={<Gavel />}>New legal terms</Badge>}
            </span>
            <div className="nx-msg__bubble">{h.message}</div>
            {h.terms && !h.accept && <TermsChips terms={h.terms} />}
          </div>
        );
      })}
    </div>
  );
}

/* ---------------------------------------------------------------- audit timeline */
const ACTION_STYLE: Record<string, { tone: string; icon: ReactNode }> = {
  EXTRACT_CLAUSES: { tone: "neutral", icon: <FileSearch /> },
  FLAG_CLAUSE: { tone: "warning", icon: <ShieldAlert /> },
  PROPOSE_REDLINES: { tone: "info", icon: <PenLine /> },
  PRICING_PLAN: { tone: "info", icon: <TrendingUp /> },
  SEND_OFFER: { tone: "info", icon: <Mail /> },
  RECEIVE_REPLY: { tone: "neutral", icon: <MessageSquareReply /> },
  REDLINE_ACCEPTED: { tone: "good", icon: <CheckCheck /> },
  REDLINE_REJECTED: { tone: "warning", icon: <XCircle /> },
  ACCEPT_OFFER: { tone: "good", icon: <CheckCheck /> },
  ESCALATE: { tone: "critical", icon: <AlertOctagon /> },
  APPROVE: { tone: "good", icon: <UserCheck /> },
  REJECT: { tone: "critical", icon: <UserX /> },
  EXECUTE: { tone: "good", icon: <FileSignature /> },
  WRITE_BACK: { tone: "info", icon: <Sparkles /> },
  END_NO_DEAL: { tone: "neutral", icon: <XCircle /> },
};
export function AuditTimeline({ events }: { events: AuditEvent[] }) {
  return (
    <ol className="nx-timeline">
      {events.map((e) => {
        const st = ACTION_STYLE[e.action] ?? { tone: "neutral", icon: <CircleDot /> };
        return (
          <li key={e.seq}>
            <span className="nx-timeline__dot" data-tone={st.tone}>{st.icon}</span>
            <div className="nx-stack" style={{ ["--gap" as string]: "2px" }}>
              <div className="nx-timeline__head">
                <span className="nx-timeline__action">{e.action}</span>
                <span className="nx-timeline__agent">{e.agent.startsWith("human:") ? `Reviewer ${e.agent.slice(6)}` : titleCase(e.agent)} · {new Date(e.ts * 1000).toLocaleTimeString()}</span>
                <HashChip hash={e.hash} />
              </div>
              <div className="nx-timeline__text">{e.rationale}</div>
            </div>
          </li>
        );
      })}
    </ol>
  );
}

/* ---------------------------------------------------------------- hash chip */
export function HashChip({ hash, chars = 10 }: { hash: string; chars?: number }) {
  const [copied, setCopied] = useState(false);
  return (
    <button type="button" className="nx-hash" title={`SHA-256 ${hash} — click to copy`}
      onClick={() => {
        navigator.clipboard?.writeText(hash).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1200); }).catch(() => {});
      }}>
      {copied ? <CheckCheck size={12} /> : <Copy size={12} />}{hash.slice(0, chars)}
    </button>
  );
}

/* ---------------------------------------------------------------- lifecycle stepper */
const STEPS = ["Ingest", "Risk review", "Negotiate", "Human gate", "Signed"] as const;
export function DealStepper({ status, everEscalated }: { status: Status; everEscalated: boolean }) {
  const idx = { analyzed: 1, awaiting_reply: 2, awaiting_human: 3, signed: 4, closed: 4 }[status];
  return (
    <div className="nx-steps" aria-label="Deal lifecycle">
      {STEPS.map((s, i) => {
        let state = i < idx ? "done" : i === idx ? "current" : "todo";
        if (s === "Human gate" && !everEscalated && i < idx) state = "done";
        if (s === "Human gate" && status === "awaiting_human") state = "blocked";
        if (status === "signed" && i === 4) state = "done";
        if (status === "closed" && i === 4) state = "current";
        return (
          <span key={s} className="nx-step" data-state={state}>
            <b>{state === "done" ? "✓" : i + 1}</b>{s === "Signed" && status === "closed" ? "Closed" : s}
          </span>
        );
      })}
    </div>
  );
}

/* ---------------------------------------------------------------- signature stamp */
export function SignatureStamp({ envelope, terms }: { envelope: string; terms: Terms }) {
  return (
    <div className="nx-stamp" aria-label="Sent for signature">
      <span><ShieldCheck size={16} style={{ verticalAlign: -3 }} /> Sent for signature</span>
      <small>{envelope} · {money(terms.price)}/yr · net {terms.payment_days}</small>
    </div>
  );
}
