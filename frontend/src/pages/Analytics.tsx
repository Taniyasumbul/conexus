import { BadgeDollarSign, Clock3, FileSignature, Hand } from "lucide-react";
import { ActivityChart, Card, Columns, Company, EmptyState, Grid, MetricBars, PageHeader, Skeleton, Stack, Stat, Table, ValueArea } from "@ui";
import { api, money, pct, titleCase } from "@lib/api";
import { useApi } from "@lib/hooks";
import { ErrorState } from "./shared";

type Analytics = {
  days: { day: string; analyzed: number; signed: number; value: number; escalated: number }[];
  escalations_by_kind: { kind: string; count: number }[];
  decisions: { approved: number; rejected: number };
  time_to_close_minutes: { median: number | null; fastest: number | null; slowest: number | null };
  rounds: { rounds: number; deals: number }[];
  by_segment: { segment: string; deals: number; value: number }[];
  discounts: { customer: string; discount: number; price: number }[];
  totals: { contracts: number; signed: number; value: number; escalations: number };
};

function duration(min: number | null): string {
  if (min == null) return "—";
  if (min < 1) return `${Math.round(min * 60)} s`;
  if (min < 90) return `${Math.round(min)} min`;
  if (min < 60 * 36) return `${(min / 60).toFixed(1)} h`;
  return `${(min / 1440).toFixed(1)} days`;
}

export default function AnalyticsPage() {
  const a = useApi(() => api.analytics() as Promise<Analytics>, [], () => 15000);
  if (a.error) return <ErrorState error={a.error} onRetry={a.reload} />;
  if (!a.data) return <Stack><Skeleton height={140} /><Skeleton height={300} /></Stack>;
  const d = a.data;
  if (d.totals.contracts === 0) {
    return <Stack gap={20}><PageHeader title="Analytics" description="How the agents are performing." />
      <Card><EmptyState title="No data yet">Analyse and negotiate a few contracts and the charts fill in here.</EmptyState></Card></Stack>;
  }
  const decided = d.decisions.approved + d.decisions.rejected;
  return (
    <Stack gap={20}>
      <PageHeader title="Analytics" description="How the agents are performing over the last 14 days." />
      <Grid min={200}>
        <Stat icon={<BadgeDollarSign />} tint="violet" label="Signed per year" value={money(d.totals.value, true)} hint={`${d.totals.signed} deals signed`} />
        <Stat icon={<FileSignature />} tint="mint" label="Close rate" value={pct(d.totals.signed / d.totals.contracts)} hint={`of ${d.totals.contracts} contracts`} />
        <Stat icon={<Clock3 />} tint="sky" label="Median time to close" value={duration(d.time_to_close_minutes.median)}
          hint={`fastest ${duration(d.time_to_close_minutes.fastest)}`} />
        <Stat icon={<Hand />} tint="rose" label="Paused for a person" value={d.totals.escalations}
          hint={decided ? `${d.decisions.approved} approved · ${d.decisions.rejected} rejected` : "No decisions yet"} />
      </Grid>

      <div className="nx-split">
        <Card title="Activity" subtitle="Contracts analysed and deals signed per day"><ActivityChart data={d.days} /></Card>
        <Card title="Signed value" subtitle="Annual contract value signed per day"><ValueArea data={d.days} /></Card>
      </div>

      <Grid min={320}>
        <Card title="Why deals paused" subtitle="Escalations by reason">
          {d.escalations_by_kind.length
            ? <MetricBars data={d.escalations_by_kind.map((e) => ({ name: titleCase(e.kind), value: e.count }))} format={(v) => String(v)} height={Math.max(140, d.escalations_by_kind.length * 44)} />
            : <EmptyState title="No escalations">Every deal stayed within policy.</EmptyState>}
        </Card>
        <Card title="Rounds to agreement" subtitle="Signed deals by number of rounds">
          <Columns data={d.rounds} x="rounds" y="deals" label="Deals" />
        </Card>
      </Grid>

      <Grid min={320}>
        <Card title="By segment" subtitle="Signed deals and value" flush>
          <Table rows={d.by_segment} rowKey={(r) => r.segment} empty={<EmptyState title="Nothing signed yet" />} columns={[
            { key: "s", header: "Segment", render: (r) => <b>{titleCase(r.segment)}</b> },
            { key: "d", header: "Deals", num: true, render: (r) => r.deals },
            { key: "v", header: "Value / yr", num: true, render: (r) => money(r.value) },
          ]} />
        </Card>
        <Card title="Biggest discounts" subtitle="Off list price, signed deals" flush>
          <Table rows={d.discounts.slice(0, 6)} rowKey={(r) => r.customer + r.price} empty={<EmptyState title="Nothing signed yet" />} columns={[
            { key: "c", header: "Customer", render: (r) => <Company name={r.customer} /> },
            { key: "p", header: "Price / yr", num: true, render: (r) => money(r.price) },
            { key: "d", header: "Discount", num: true, render: (r) => <b>{pct(r.discount)}</b> },
          ]} />
        </Card>
      </Grid>
    </Stack>
  );
}
