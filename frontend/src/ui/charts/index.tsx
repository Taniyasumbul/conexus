/* Nexus UI charts. Colours come from tokens (validated categorical slots 1-2);
   reference lines use muted ink, never a series colour; one y-axis per chart. */
import {
  Bar, BarChart, CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import type { Offer, PricingPlan } from "@lib/api";
import { money } from "@lib/api";
import { useTokens } from "@lib/hooks";
import { Legend } from "../primitives";

const TOKENS = ["series-1", "series-2", "chart-grid", "fg-2", "fg-3", "border-strong", "surface"] as const;

function ChartTooltip({ active, payload, label, fmt, labelFmt }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="nx-tooltip">
      <div className="nx-muted">{labelFmt ? labelFmt(label) : label}</div>
      {payload.filter((p: any) => p.value != null).map((p: any) => (
        <div key={p.dataKey} style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <i style={{ width: 10, height: 3, borderRadius: 2, background: p.color, display: "inline-block" }} />
          <span>{p.name}</span><b style={{ marginLeft: "auto" }}>{fmt ? fmt(p.value) : p.value}</b>
        </div>
      ))}
    </div>
  );
}

/* ---------------------------------------------------------------- negotiation price path */
export function PriceChart({ history, plan, height = 280 }: { history: Offer[]; plan: PricingPlan | null; height?: number }) {
  const t = useTokens(TOKENS);
  const rounds = new Map<number, { round: number; us?: number; them?: number }>();
  for (const h of history) {
    if (!h.terms) continue;
    const r = rounds.get(h.round) ?? { round: h.round };
    if (h.sender === "us") r.us = h.terms.price; else r.them = h.terms.price;
    rounds.set(h.round, r);
  }
  const data = [...rounds.values()].sort((a, b) => a.round - b.round);
  if (!data.length) return null;
  const axis = { stroke: t["border-strong"], tick: { fill: t["fg-3"], fontSize: 12 }, tickLine: false };
  const vals = data.flatMap((d) => [d.us, d.them]).filter((v): v is number => v != null);
  if (plan) vals.push(plan.floor_price, plan.concession_limit);
  const lo = Math.min(...vals), hi = Math.max(...vals);
  const raw = (hi - lo) / 4 || hi * 0.1;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((x) => x >= raw) ?? raw;
  const domain: [number, number] = [Math.max(0, Math.floor(lo / step) * step), Math.ceil(hi / step) * step];
  const ticks = Array.from({ length: Math.round((domain[1] - domain[0]) / step) + 1 }, (_, i) => domain[0] + i * step);
  return (
    <div className="nx-stack" style={{ ["--gap" as string]: "8px" }}>
      <Legend items={[
        { label: "Our offer", color: t["series-1"] },
        { label: "Their offer", color: t["series-2"] },
        ...(plan ? [{ label: "Concession limit / floor", color: t["fg-3"], dashed: true }] : []),
      ]} />
      <div style={{ width: "100%", height }}>
        <ResponsiveContainer>
          <LineChart data={data} margin={{ top: 8, right: 96, bottom: 4, left: 8 }}>
            <CartesianGrid stroke={t["chart-grid"]} vertical={false} />
            <XAxis dataKey="round" {...axis} tickFormatter={(r) => (r === 0 ? "Open" : `R${r}`)} />
            <YAxis {...axis} width={64} tickFormatter={(v) => money(v, true)} domain={domain} ticks={ticks} allowDataOverflow />
            <Tooltip content={<ChartTooltip fmt={(v: number) => money(v)} labelFmt={(r: number) => (r === 0 ? "Their opening paper" : `Round ${r}`)} />}
              cursor={{ stroke: t["border-strong"], strokeWidth: 1 }} />
            {plan && <ReferenceLine y={plan.floor_price} stroke={t["fg-3"]} strokeDasharray="4 4"
              label={{ value: `Floor ${money(plan.floor_price, true)}`, position: "right", fill: t["fg-2"], fontSize: 11 }} />}
            {plan && plan.concession_limit > plan.floor_price && <ReferenceLine y={plan.concession_limit} stroke={t["fg-3"]} strokeDasharray="2 4"
              label={{ value: `Limit ${money(plan.concession_limit, true)}`, position: "right", fill: t["fg-2"], fontSize: 11 }} />}
            <Line name="Our offer" dataKey="us" stroke={t["series-1"]} strokeWidth={2} connectNulls
              dot={{ r: 4, fill: t["series-1"], stroke: t.surface, strokeWidth: 2 }} activeDot={{ r: 6, stroke: t.surface, strokeWidth: 2 }} isAnimationActive={false} />
            <Line name="Their offer" dataKey="them" stroke={t["series-2"]} strokeWidth={2} connectNulls
              dot={{ r: 4, fill: t["series-2"], stroke: t.surface, strokeWidth: 2 }} activeDot={{ r: 6, stroke: t.surface, strokeWidth: 2 }} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- single-metric bar comparison */
export function MetricBars({ data, format, height = 220, highlight }: {
  data: { name: string; value: number | null }[]; format: (v: number) => string; height?: number; highlight?: string;
}) {
  const t = useTokens(TOKENS);
  const rows = data.filter((d) => d.value != null) as { name: string; value: number }[];
  return (
    <div style={{ width: "100%", height }}>
      <ResponsiveContainer>
        <BarChart data={rows} layout="vertical" margin={{ top: 0, right: 56, bottom: 0, left: 8 }} barCategoryGap={6}>
          <CartesianGrid stroke={t["chart-grid"]} horizontal={false} />
          <XAxis type="number" stroke={t["border-strong"]} tick={{ fill: t["fg-3"], fontSize: 11 }} tickLine={false} tickFormatter={format} />
          <YAxis type="category" dataKey="name" width={170} stroke={t["border-strong"]} tick={{ fill: t["fg-2"], fontSize: 12 }} tickLine={false} />
          <Tooltip content={<ChartTooltip fmt={format} />} cursor={{ fill: t["chart-grid"] }} />
          <Bar dataKey="value" name="Value" radius={[0, 4, 4, 0]} isAnimationActive={false}
            label={{ position: "right", fill: t["fg-2"], fontSize: 11, formatter: format }}
            shape={(p: any) => (
              <rect x={p.x} y={p.y} width={Math.max(0, p.width)} height={p.height} rx={4}
                fill={highlight && p.name !== highlight ? t["border-strong"] : t["series-1"]} />
            )} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

/* ---------------------------------------------------------------- precision / recall vs threshold */
export function ThresholdChart({ sweep, threshold, height = 260 }: { sweep: { threshold: number; precision: number; recall: number }[]; threshold: number; height?: number }) {
  const t = useTokens(TOKENS);
  const axis = { stroke: t["border-strong"], tick: { fill: t["fg-3"], fontSize: 12 }, tickLine: false };
  return (
    <div className="nx-stack" style={{ ["--gap" as string]: "8px" }}>
      <Legend items={[{ label: "Precision", color: t["series-1"] }, { label: "Recall", color: t["series-2"] }, { label: "Configured threshold", color: t["fg-3"], dashed: true }]} />
      <div style={{ width: "100%", height }}>
        <ResponsiveContainer>
          <LineChart data={sweep} margin={{ top: 8, right: 16, bottom: 4, left: 0 }}>
            <CartesianGrid stroke={t["chart-grid"]} vertical={false} />
            <XAxis dataKey="threshold" {...axis} type="number" domain={[0.1, 0.9]} ticks={[0.1, 0.3, 0.5, 0.7, 0.9]} />
            <YAxis {...axis} domain={[0, 1]} ticks={[0, 0.25, 0.5, 0.75, 1]} width={40} />
            <Tooltip content={<ChartTooltip fmt={(v: number) => v.toFixed(2)} labelFmt={(x: number) => `Threshold ${x}`} />} cursor={{ stroke: t["border-strong"] }} />
            <ReferenceLine x={threshold} stroke={t["fg-3"]} strokeDasharray="4 4" />
            <Line name="Precision" dataKey="precision" stroke={t["series-1"]} strokeWidth={2} dot={{ r: 4, fill: t["series-1"], stroke: t.surface, strokeWidth: 2 }} isAnimationActive={false} />
            <Line name="Recall" dataKey="recall" stroke={t["series-2"]} strokeWidth={2} dot={{ r: 4, fill: t["series-2"], stroke: t.surface, strokeWidth: 2 }} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
