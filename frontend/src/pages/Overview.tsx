import { useNavigate } from "react-router-dom";
import { ArrowRight, FilePlus2, ShieldCheck } from "lucide-react";
import { Badge, Button, Card, EmptyState, Grid, PageHeader, Skeleton, Stack, Stat, StatusBadge, Table } from "@ui";
import { ago, api, ContractSummary, money, pct, Status, titleCase } from "@lib/api";
import { useApi } from "@lib/hooks";
import { ErrorState } from "./shared";

const PIPE: { status: Status; label: string; color: string }[] = [
  { status: "analyzed", label: "Analyzed", color: "var(--fg-3)" },
  { status: "awaiting_reply", label: "Negotiating", color: "var(--accent)" },
  { status: "awaiting_human", label: "Needs human", color: "var(--critical)" },
  { status: "signed", label: "Signed", color: "var(--good)" },
  { status: "closed", label: "Closed", color: "var(--border-strong)" },
];

export function contractColumns(): import("@ui").Column<ContractSummary>[] {
  return [
    { key: "customer", header: "Customer", render: (r) => <Stack gap={0}><b>{r.customer}</b><span className="nx-muted nx-mono" style={{ fontSize: "var(--text-xs)" }}>{r.id}</span></Stack> },
    { key: "status", header: "Status", render: (r) => <StatusBadge status={r.status} /> },
    { key: "segment", header: "Segment", render: (r) => titleCase(r.segment) },
    { key: "list", header: "List / yr", num: true, render: (r) => money(r.list_price) },
    { key: "price", header: "Agreed / last", num: true, render: (r) => money(r.price) },
    { key: "round", header: "Round", num: true, render: (r) => r.round || "—" },
    { key: "risk", header: "Risk", render: (r) => r.risky_clauses ? <Badge tone="critical" dot>{r.risky_clauses} need human</Badge> : <Badge tone="good" dot>Clean</Badge> },
    { key: "upd", header: "Updated", render: (r) => <span className="nx-muted">{ago(r.updated_at)}</span> },
  ];
}

export default function Overview() {
  const nav = useNavigate();
  const m = useApi(api.metrics, [], () => 5000);
  const list = useApi(api.contracts, [], () => 5000);
  const inbox = useApi(api.inbox, [], () => 5000);

  if (m.error) return <ErrorState error={m.error} onRetry={m.reload} />;
  const d = m.data;
  const total = d?.contracts ?? 0;

  return (
    <Stack gap={24}>
      <PageHeader eyebrow="Control room" title="Contract portfolio"
        description="What the agents are negotiating right now, what they closed, and what is waiting for a person."
        actions={<Button variant="primary" icon={<FilePlus2 size={16} />} onClick={() => nav("/new")}>New contract</Button>} />

      <Grid min={190}>
        {d ? <>
          <Stat label="Contracts" value={d.contracts} hint={`${d.crm_memory_size.toLocaleString()} deals in CRM memory`} />
          <Stat label="Signed value / yr" value={money(d.signed_value, true)} hint={`${d.signed} signed${d.avg_rounds_signed ? ` · ${d.avg_rounds_signed} rounds avg` : ""}`} />
          <Stat label="Needs a human" value={d.awaiting_human} tone={d.awaiting_human ? "critical" : undefined} hint="Waiting in the escalation inbox" />
          <Stat label="Avg discount off list" value={pct(d.avg_discount_signed)} hint="Signed deals" />
          <Stat label="Risky clauses signed unreviewed" value={d.unreviewed_risky_signed} tone={d.unreviewed_risky_signed === 0 ? "good" : "critical"}
            hint={<><ShieldCheck size={14} />Risk gate {d.unreviewed_risky_signed === 0 ? "holding" : "breached"}</>} />
        </> : Array.from({ length: 5 }, (_, i) => <Skeleton key={i} height={104} />)}
      </Grid>

      {total > 0 && d && (
        <Card title="Pipeline" subtitle={`${total} contracts by stage`}>
          <Stack gap={12}>
            <div className="nx-progress" role="img" aria-label="Contracts by stage">
              {PIPE.map((p) => (d.by_status[p.status] ? <span key={p.status} style={{ width: `${(d.by_status[p.status]! / total) * 100}%`, background: p.color }} title={`${p.label}: ${d.by_status[p.status]}`} /> : null))}
            </div>
            <div className="nx-legend">
              {PIPE.map((p) => <span key={p.status}><i style={{ background: p.color, height: 8, width: 8, borderRadius: 2 }} />{p.label} <b className="nx-num">{d.by_status[p.status] ?? 0}</b></span>)}
            </div>
          </Stack>
        </Card>
      )}

      {!!inbox.data?.length && (
        <Card title="Waiting for your decision" tone="critical" subtitle="The agents paused these deals and will resume once someone approves or rejects them."
          actions={<Button size="sm" icon={<ArrowRight size={14} />} onClick={() => nav("/inbox")}>Open inbox</Button>} flush>
          <Table rows={inbox.data.slice(0, 4)} rowKey={(r) => r.id} onRowClick={(r) => nav(`/contracts/${r.id}`)} columns={[
            { key: "c", header: "Customer", render: (r) => <b>{r.customer}</b> },
            { key: "k", header: "Reason", render: (r) => <Badge tone="critical">{titleCase(r.escalation.kind)}</Badge> },
            { key: "t", header: "Trigger", render: (r) => <span className="nx-secondary">{r.escalation.triggers[0]}</span> },
            { key: "p", header: "On the table", num: true, render: (r) => money(r.terms?.price) },
          ]} />
        </Card>
      )}

      <Card title="Recent contracts" flush actions={<Button size="sm" variant="ghost" onClick={() => nav("/contracts")}>View all</Button>}>
        {list.data ? (
          <Table rows={list.data.slice(0, 8)} rowKey={(r) => r.id} onRowClick={(r) => nav(`/contracts/${r.id}`)} columns={contractColumns()}
            empty={<EmptyState title="No contracts yet" action={<Button variant="primary" onClick={() => nav("/new")}>Analyze your first contract</Button>}>
              Upload a customer's MSA or pick a bundled sample. The agents extract clauses, score risk and negotiate.
            </EmptyState>} />
        ) : <div style={{ padding: 20 }}><Skeleton height={160} /></div>}
      </Card>
    </Stack>
  );
}
