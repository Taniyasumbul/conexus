import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, BadgeDollarSign, FilePlus2, Hand, Percent, ShieldCheck } from "lucide-react";
import { useMemo } from "react";
import { AgentNetwork, agentOf, Badge, Button, Card, Company, CountUp, EmptyState, Grid, LiveTicker, Skeleton, Stack, Stat, StatusBadge, Table } from "@ui";
import type { Column } from "@ui";
import { ago, api, ContractSummary, money, Status, titleCase } from "@lib/api";
import { useApi } from "@lib/hooks";
import { useAuth } from "@lib/auth";
import { ErrorState } from "./shared";

const FLOW: { status: Status; label: string; color: string }[] = [
  { status: "analyzed", label: "Analyzed", color: "var(--fg-3)" },
  { status: "awaiting_reply", label: "Negotiating", color: "var(--accent)" },
  { status: "awaiting_human", label: "Needs a human", color: "var(--critical)" },
  { status: "signed", label: "Signed", color: "var(--good)" },
  { status: "closed", label: "Closed", color: "var(--border-strong)" },
];

export function contractColumns(): Column<ContractSummary>[] {
  return [
    { key: "customer", header: "Customer", render: (r) => <Company name={r.customer} sub={r.id} /> },
    { key: "status", header: "Stage", render: (r) => <StatusBadge status={r.status} /> },
    { key: "segment", header: "Segment", render: (r) => <span className="nx-secondary">{titleCase(r.segment)}</span> },
    { key: "price", header: "Value / yr", num: true, render: (r) => <b>{money(r.price ?? r.list_price)}</b> },
    { key: "risk", header: "Risk", render: (r) => r.risky_clauses ? <Badge tone="critical" dot>{r.risky_clauses} for Legal</Badge> : <Badge tone="good" dot>Clear</Badge> },
    { key: "upd", header: "Updated", render: (r) => <span className="nx-muted">{ago(r.updated_at)}</span> },
  ];
}

export default function Overview() {
  const nav = useNavigate();
  const { user, can } = useAuth();
  const m = useApi(api.metrics, [], () => 5000);
  const list = useApi(api.contracts, [], () => 5000);
  const inbox = useApi(api.inbox, [], () => 5000);
  const events = useApi(() => api.auditAll(12), [], () => 2000);
  const active = useMemo(() => {
    const now = Date.now() / 1000;
    return new Set((events.data ?? []).filter((e) => now - e.ts < 15).map(agentOf));
  }, [events.data]);

  if (m.error) return <ErrorState error={m.error} onRetry={m.reload} />;
  const d = m.data;
  const waiting = inbox.data?.length ?? 0;
  const hour = new Date().getHours();
  const greet = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";

  return (
    <Stack gap={24}>
      <section className="nx-hero">
        <div className="nx-grad" aria-hidden><span /><span /><span /><span /></div>
        <div className="nx-hero__main">
          <div className="nx-stack" style={{ ["--gap" as string]: "18px" }}>
            <span className="nx-eyebrow">{active.size ? "Agents working now" : "Agents standing by"}</span>
            <h1>{greet}, {user.name.split(" ")[0]}</h1>
            <p>{waiting > 0
              ? (can("legal") ? `${waiting} deal${waiting > 1 ? "s" : ""} waiting for your decision.` : `${waiting} deal${waiting > 1 ? "s" : ""} waiting for Legal.`)
              : "Nothing needs a person right now."}</p>
            <div><Button variant="primary" size="lg" icon={<FilePlus2 size={18} />} onClick={() => nav("/new")}>New contract</Button></div>
          </div>
          <div className="nx-hero__viz">
            <AgentNetwork active={active} />
            {!!events.data?.length && <LiveTicker events={events.data.slice(0, 3)} />}
          </div>
        </div>
        <div className="nx-flow" aria-label="Contracts by stage">
          {FLOW.map((f) => {
            const n = d?.by_status[f.status] ?? 0;
            return (
              <Link key={f.status} to={f.status === "awaiting_human" ? "/inbox" : "/contracts"} className="nx-flow__stage"
                data-hot={f.status === "awaiting_human" && n > 0}>
                <span className="nx-flow__n">{d ? <CountUp value={n} /> : "–"}</span>
                <span className="nx-flow__label"><i className="nx-flow__dot" style={{ background: f.color }} />{f.label}</span>
              </Link>
            );
          })}
        </div>
      </section>

      <Grid min={160}>
        {d ? <>
          <Stat icon={<BadgeDollarSign />} tint="violet" label="Signed per year" value={<CountUp value={d.signed_value} format={(v) => money(v, true)} duration={1100} />} hint={`${d.signed} deals · ${d.avg_rounds_signed ?? "–"} rounds avg`} />
          <Stat icon={<Hand />} tint="rose" label="Waiting for a person" value={<CountUp value={d.awaiting_human} />} hint="In the inbox" tone={d.awaiting_human ? "critical" : undefined} />
          <Stat icon={<Percent />} tint="amber" label="Average discount" value={d.avg_discount_signed == null ? "—" : <CountUp value={d.avg_discount_signed * 100} format={(v) => `${Math.round(v)}%`} />} hint="Off list price" />
          <Stat icon={<ShieldCheck />} tint="mint" label="Risky clauses signed unreviewed" value={d.unreviewed_risky_signed}
            tone={d.unreviewed_risky_signed === 0 ? "good" : "critical"} hint={d.unreviewed_risky_signed === 0 ? "Risk gate holding" : "Check the ledger"} />
        </> : Array.from({ length: 4 }, (_, i) => <Skeleton key={i} height={150} />)}
      </Grid>

      {waiting > 0 && (
        <Card title="Waiting for a decision" tone="critical"
          actions={<Button size="sm" icon={<ArrowRight size={14} />} onClick={() => nav("/inbox")}>Open inbox</Button>}>
          <div>
            {inbox.data!.slice(0, 4).map((it) => (
              <Link key={it.id} to={`/contracts/${it.id}`} className="nx-decision">
                <Company name={it.customer} />
                <div className="nx-decision__main">
                  <div className="nx-decision__why">{it.escalation.triggers[0]}</div>
                </div>
                <Badge tone="critical">{titleCase(it.escalation.kind)}</Badge>
                <b className="nx-num" style={{ minWidth: 80, textAlign: "right" }}>{money(it.terms?.price)}</b>
                <ArrowRight size={16} className="nx-muted" />
              </Link>
            ))}
          </div>
        </Card>
      )}

      <Card title="Recent contracts" flush actions={<Button size="sm" variant="ghost" onClick={() => nav("/contracts")}>View all</Button>}>
        {list.data ? (
          <Table rows={list.data.slice(0, 6)} rowKey={(r) => r.id} onRowClick={(r) => nav(`/contracts/${r.id}`)} columns={contractColumns()}
            empty={<EmptyState title="No contracts yet" action={<Button variant="primary" onClick={() => nav("/new")}>Analyze your first contract</Button>}>
              Upload a customer contract or pick a sample to watch the agents work.
            </EmptyState>} />
        ) : <div style={{ padding: 20 }}><Skeleton height={160} /></div>}
      </Card>
    </Stack>
  );
}
