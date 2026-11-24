/* Nexus UI - workspace patterns: breadcrumbs, next-action bar, table toolbar, filter chips,
   step indicator and a plain activity feed. Quiet by design: no gradients, no motion. */
import { ReactNode } from "react";
import { Link } from "react-router-dom";
import { ArrowUpDown, Check, ChevronRight, X } from "lucide-react";
import type { AuditEvent, Status } from "@lib/api";
import { ago } from "@lib/api";
import { Tone } from "./primitives";

/* ---------------------------------------------------------------- lifecycle vocabulary
   One set of words for every screen. "Sent to sign" until a real e-sign provider confirms. */
export const STAGE: Record<Status, { label: string; next: string; tone: Tone }> = {
  analyzed: { label: "Ready to negotiate", next: "Start negotiation", tone: "neutral" },
  awaiting_reply: { label: "Negotiating", next: "Wait for the customer", tone: "info" },
  awaiting_human: { label: "Needs review", next: "Legal decision", tone: "critical" },
  signed: { label: "Sent to sign", next: "Track signature", tone: "good" },
  closed: { label: "Closed", next: "No action", tone: "neutral" },
};

/* ---------------------------------------------------------------- breadcrumbs */
export function Breadcrumbs({ items }: { items: { label: ReactNode; to?: string }[] }) {
  return (
    <nav className="nx-crumbs" aria-label="Breadcrumb">
      <ol>
        {items.map((it, i) => (
          <li key={i}>
            {it.to ? <Link to={it.to}>{it.label}</Link> : <span aria-current="page">{it.label}</span>}
            {i < items.length - 1 && <ChevronRight size={14} aria-hidden />}
          </li>
        ))}
      </ol>
    </nav>
  );
}

/* ---------------------------------------------------------------- next action
   The one thing someone has to do on this page, and who owns it. */
export function NextAction({ tone = "neutral", owner, title, children, actions, icon }: {
  tone?: Tone; owner?: ReactNode; title: ReactNode; children?: ReactNode; actions?: ReactNode; icon?: ReactNode;
}) {
  return (
    <section className="nx-next" data-tone={tone} aria-label="Next action">
      {icon && <span className="nx-next__icon" aria-hidden>{icon}</span>}
      <div className="nx-next__main">
        <div className="nx-next__label">Next action{owner && <> · <b>{owner}</b></>}</div>
        <h2 className="nx-next__title">{title}</h2>
        {children && <div className="nx-next__body">{children}</div>}
      </div>
      {actions && <div className="nx-next__actions">{actions}</div>}
    </section>
  );
}

/* ---------------------------------------------------------------- table toolbar */
export function Toolbar({ children, end }: { children: ReactNode; end?: ReactNode }) {
  return (
    <div className="nx-toolbar" role="toolbar">
      <div className="nx-toolbar__start">{children}</div>
      {end && <div className="nx-toolbar__end">{end}</div>}
    </div>
  );
}

export function FilterChip({ selected, onToggle, children }: { selected: boolean; onToggle: () => void; children: ReactNode }) {
  return (
    <button type="button" className="nx-chip" aria-pressed={selected} onClick={onToggle}>
      {selected && <Check size={13} aria-hidden />}{children}
    </button>
  );
}

export function SortSelect<T extends string>({ value, onChange, options, id = "sort" }: {
  value: T; onChange: (v: T) => void; options: { value: T; label: string }[]; id?: string;
}) {
  return (
    <label className="nx-sort" htmlFor={id}>
      <ArrowUpDown size={14} aria-hidden /><span className="nx-visually-hidden">Sort by</span>
      <select id={id} value={value} onChange={(e) => onChange(e.target.value as T)}>
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </label>
  );
}

export function ResultCount({ shown, total, noun = "contracts", onClear }: { shown: number; total: number; noun?: string; onClear?: () => void }) {
  return (
    <span className="nx-result" role="status">
      {shown === total ? `${total} ${noun}` : `${shown} of ${total} ${noun}`}
      {onClear && <button type="button" className="nx-linkbtn" onClick={onClear}><X size={13} aria-hidden />Clear filters</button>}
    </span>
  );
}

/* ---------------------------------------------------------------- step indicator */
export function Steps({ steps, current, onPick }: { steps: string[]; current: number; onPick?: (i: number) => void }) {
  return (
    <ol className="nx-steps nx-steps--form" aria-label="Progress">
      {steps.map((s, i) => {
        const state = i < current ? "done" : i === current ? "current" : "todo";
        const label = <><b>{state === "done" ? "✓" : i + 1}</b>{s}</>;
        return (
          <li key={s} className="nx-step" data-state={state} aria-current={state === "current" ? "step" : undefined}>
            {onPick && i < current ? <button type="button" onClick={() => onPick(i)}>{label}</button> : label}
          </li>
        );
      })}
    </ol>
  );
}

/* ---------------------------------------------------------------- activity feed
   Who did what, in words people use: CoNexus, Legal, Customer, System. */
const ACTION_TEXT: Record<string, string> = {
  EXTRACT_CLAUSES: "read the contract", FLAG_CLAUSE: "flagged a clause", PROPOSE_REDLINES: "proposed redlines",
  PRICING_PLAN: "set the pricing plan", SEND_OFFER: "sent an offer", RECEIVE_REPLY: "replied",
  ESCALATE: "asked for a review", EXECUTE: "agreed the deal and sent it to sign", END_NO_DEAL: "ended without a deal",
  ACCEPT_OFFER: "accepted the customer's offer", WRITE_BACK: "saved the outcome to deal memory",
  APPROVE: "approved", REJECT: "rejected", POLICY_CHANGE: "changed the policy", ACCEPT_MISMATCH: "treated a reply as a counter-offer",
};
export function actorOf(e: AuditEvent): { who: string; kind: "conexus" | "person" | "customer" | "system" } {
  if (e.agent.startsWith("human:")) return { who: e.agent.slice(6), kind: "person" };
  if (e.action === "RECEIVE_REPLY") return { who: "Customer", kind: "customer" };
  if (e.agent === "system" || e.action === "POLICY_CHANGE") return { who: "System", kind: "system" };
  return { who: "CoNexus", kind: "conexus" };
}
export function describe(e: AuditEvent): string {
  if (ACTION_TEXT[e.action]) return ACTION_TEXT[e.action];
  if (e.action.startsWith("REDLINE_")) return `redline ${e.action.slice(8).toLowerCase()}`;
  return e.action.toLowerCase().replace(/_/g, " ");
}

export function ActivityFeed({ events, linkContracts, empty = "No activity yet." }: {
  events: AuditEvent[]; linkContracts?: boolean; empty?: string;
}) {
  if (!events.length) return <p className="nx-muted" style={{ fontSize: "var(--text-sm)" }}>{empty}</p>;
  return (
    <ul className="nx-feed">
      {events.map((e) => {
        const a = actorOf(e);
        return (
          <li key={e.seq} data-kind={a.kind}>
            <span className="nx-feed__dot" aria-hidden />
            <div className="nx-feed__main">
              <span><b>{a.who}</b> {describe(e)}
                {linkContracts && e.contract_id && <> · <Link to={`/contracts/${e.contract_id}`} className="nx-mono">{e.contract_id}</Link></>}
              </span>
              <span className="nx-feed__why" title={e.rationale}>{e.rationale}</span>
            </div>
            <time className="nx-feed__time">{ago(e.ts)}</time>
          </li>
        );
      })}
    </ul>
  );
}
