import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, FilePlus2 } from "lucide-react";
import {
  ActivityFeed, Badge, Button, Card, Company, EmptyState, PageHeader, Skeleton, Stack, STAGE, StatusBadge, Table,
} from "@ui";
import type { Column } from "@ui";
import { ago, api, ContractSummary, InboxItem, money, titleCase } from "@lib/api";
import { useApi } from "@lib/hooks";
import { useAuth } from "@lib/auth";
import { ErrorState } from "./shared";

const STALE_S = 2 * 86400; // an e-mail negotiation with no reply for two days needs a nudge

/** What should happen next on a contract, in plain words (shared by Home and Contracts). */
export function nextStep(r: ContractSummary, canDecide: boolean): string {
  if (r.status === "awaiting_human") return canDecide ? "Decide" : "Waiting on Legal";
  if (r.status === "awaiting_reply") return r.mode === "email" ? "Waiting for the customer" : "Agents negotiating";
  return STAGE[r.status].next;
}

export function contractColumns(canDecide: boolean): Column<ContractSummary>[] {
  return [
    { key: "customer", header: "Customer", render: (r) => <Company name={r.customer} sub={r.id} /> },
    { key: "status", header: "Stage", render: (r) => <StatusBadge status={r.status} /> },
    { key: "next", header: "Next action", render: (r) => <span className="nx-secondary">{nextStep(r, canDecide)}</span> },
    { key: "price", header: "Value / yr", num: true, render: (r) => <b>{money(r.price ?? r.list_price)}</b> },
    { key: "risk", header: "Risk", render: (r) => r.risky_clauses ? <Badge tone="critical" dot>{r.risky_clauses} open</Badge> : <Badge tone="good" dot>Clear</Badge> },
    { key: "upd", header: "Updated", render: (r) => <span className="nx-muted">{ago(r.updated_at)}</span> },
  ];
}

type Attention = { id: string; customer: string; why: string; detail: string; action: string; tone: "critical" | "warning" | "neutral"; at: number; value?: number | null };

function attentionItems(list: ContractSummary[], inbox: InboxItem[], canDecide: boolean): Attention[] {
  const now = Date.now() / 1000;
  const out: Attention[] = inbox.map((it) => ({
    id: it.id, customer: it.customer, why: titleCase(it.escalation.kind), detail: it.escalation.triggers[0] ?? "",
    action: canDecide ? "Decide" : "Waiting on Legal", tone: "critical", at: it.updated_at, value: it.terms?.price,
  }));
  for (const r of list) {
    if (r.status === "analyzed") {
      out.push({ id: r.id, customer: r.customer, why: "Analyzed, not started", detail: r.risky_clauses ? `${r.risky_clauses} clause${r.risky_clauses > 1 ? "s" : ""} will need Legal` : "No blocking clauses found",
        action: "Start negotiation", tone: "neutral", at: r.updated_at, value: r.list_price });
    } else if (r.status === "awaiting_reply" && r.mode === "email" && now - r.updated_at > STALE_S) {
      out.push({ id: r.id, customer: r.customer, why: "No reply from the customer", detail: `Last activity ${ago(r.updated_at)}`,
        action: "Follow up", tone: "warning", at: r.updated_at, value: r.price ?? r.list_price });
    }
  }
  // Legal decisions first, then stalled, then not started; oldest first inside each group
  const rank = { critical: 0, warning: 1, neutral: 2 } as const;
  return out.sort((a, b) => rank[a.tone] - rank[b.tone] || a.at - b.at);
}

export default function Overview() {
  const nav = useNavigate();
  const { user, can } = useAuth();
  const m = useApi(api.metrics, [], () => 8000);
  const list = useApi(api.contracts, [], () => 5000);
  const inbox = useApi(api.inbox, [], () => 5000);
  const events = useApi(() => api.auditAll(8), [], () => 8000);
  const canDecide = can("legal");

  if (m.error) return <ErrorState error={m.error} onRetry={m.reload} />;
  const d = m.data;
  const loading = !list.data || !inbox.data;
  const attention = loading ? [] : attentionItems(list.data!, inbox.data!, canDecide);
  const active = (list.data ?? []).filter((r) => r.status === "awaiting_reply" || r.status === "awaiting_human" || r.status === "analyzed");
  const firstRun = list.data?.length === 0;

  return (
    <Stack gap={20}>
      <PageHeader title={`Welcome back, ${user.name.split(" ")[0]}`}
        description={loading ? "Loading your work…" : attention.length
          ? `${attention.length} item${attention.length > 1 ? "s" : ""} need${attention.length > 1 ? "" : "s"} attention.`
          : "Nothing needs you right now."} />

      {firstRun ? (
        <Card>
          <EmptyState title="Start with your first contract"
            action={<Button variant="primary" icon={<FilePlus2 size={16} />} onClick={() => nav("/new")}>Create contract</Button>}>
            Upload a customer's contract. CoNexus reads it, flags risky clauses for Legal and prepares an opening offer.
            Nothing is sent to the customer until you start negotiating.
          </EmptyState>
        </Card>
      ) : (
        <Card title="Needs attention" subtitle={canDecide ? "Decisions waiting on you, stalled deals and contracts not started" : "Deals waiting on Legal, stalled deals and contracts not started"} flush
          actions={inbox.data?.length ? <Button size="sm" variant="ghost" icon={<ArrowRight size={14} />} onClick={() => nav("/review")}>{canDecide ? "Review queue" : "Waiting on Legal"}</Button> : undefined}>
          {loading ? <div style={{ padding: 20 }}><Skeleton height={120} /></div> : attention.length === 0 ? (
            <EmptyState title="You're all caught up">New escalations, stalled e-mail negotiations and contracts waiting to start show up here.</EmptyState>
          ) : (
            <ul className="nx-worklist">
              {attention.slice(0, 6).map((a) => (
                <li key={a.id + a.why}>
                  <Link to={`/contracts/${a.id}`} className="nx-work">
                    <Company name={a.customer} sub={a.id} />
                    <div className="nx-work__why"><b>{a.why}</b><span title={a.detail}>{a.detail}</span></div>
                    <div className="nx-work__end">
                      {a.value != null && <span className="nx-num nx-secondary">{money(a.value)}</span>}
                      <Badge tone={a.tone === "neutral" ? "info" : a.tone}>{a.action}</Badge>
                      <ArrowRight size={16} className="nx-muted" aria-hidden />
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}

      {!firstRun && (
        <div className="nx-workspace">
          <Card title="Active contracts" subtitle="Ready to negotiate, negotiating or with Legal" flush
            actions={<Button size="sm" variant="ghost" onClick={() => nav("/contracts")}>All contracts</Button>}>
            {list.data ? (
              <Table cards caption="Active contracts" rows={active.slice(0, 8)} rowKey={(r) => r.id} onRowClick={(r) => nav(`/contracts/${r.id}`)}
                columns={contractColumns(canDecide).filter((c) => c.key !== "upd")}
                empty={<EmptyState title="No active contracts">Everything is either sent to sign or closed.</EmptyState>} />
            ) : <div style={{ padding: 20 }}><Skeleton height={160} /></div>}
          </Card>
          <Card title="Recent activity" actions={<Button size="sm" variant="ghost" onClick={() => nav("/ledger")}>Audit history</Button>}>
            {events.data ? <ActivityFeed events={events.data} linkContracts /> : <Skeleton height={160} />}
          </Card>
        </div>
      )}

      {d && !firstRun && (
        <section aria-label="Portfolio snapshot">
          <div className="nx-metrics">
            <div><span>Agreed value</span><b>{money(d.signed_value, true)}</b><small>{d.signed} deals sent to sign, per year</small></div>
            <div><span>In progress</span><b>{(d.by_status.analyzed ?? 0) + (d.by_status.awaiting_reply ?? 0)}</b><small>Ready or negotiating</small></div>
            <div data-tone={d.awaiting_human ? "critical" : undefined}><span>Needs review</span><b>{d.awaiting_human}</b><small>Paused for Legal</small></div>
            <div data-tone={d.unreviewed_risky_signed ? "critical" : undefined}><span>Risky clauses agreed unreviewed</span><b>{d.unreviewed_risky_signed}</b>
              <small>{d.unreviewed_risky_signed ? "Check the audit history" : "Risk gate holding"}</small></div>
          </div>
        </section>
      )}
    </Stack>
  );
}
