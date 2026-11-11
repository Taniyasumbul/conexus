import { Alert, Badge, Card, EmptyState, Grid, KeyValue, MetricBars, PageHeader, Skeleton, Stack, Stat, Table, ThresholdChart } from "@ui";
import { api, money, pct } from "@lib/api";
import { useApi } from "@lib/hooks";
import { ErrorState } from "./shared";

type Row = Record<string, any> & { system: string };
const f3 = (v: number | null | undefined) => (v == null ? "—" : v.toFixed(3));

export default function Evaluation() {
  const ev = useApi(api.evals, []);
  if (ev.error) return <ErrorState error={ev.error} onRetry={ev.reload} />;
  if (!ev.data) return <Skeleton height={300} />;
  const { eval_escalation: esc, eval_negotiation: neg } = ev.data;
  const cuad = (ev.data as any).eval_cuad;
  const llmEv = (ev.data as any).eval_llm;
  const parsing = llmEv ? (llmEv.parsing_hybrid ?? llmEv.parsing) : null;
  if (!esc && !neg && !(ev.data as any).eval_cuad) return <EmptyState title="No evaluation results yet">Run <code>make eval</code> to produce them.</EmptyState>;

  const tA: Row[] = neg?.table_a_end_to_end ?? [];
  const tB: Row[] = neg?.table_b_negotiation_only ?? [];
  const full = tA.find((r) => r.system.startsWith("conexus"));
  const noGate = tA.find((r) => r.system.includes("no risk gate"));
  const mem = tB.find((r) => r.system.startsWith("memory"));
  const cold = tB.find((r) => r.system.startsWith("no memory"));

  return (
    <Stack gap={24}>
      <PageHeader title="Evaluation" description="Real-contract results first, then the synthetic benchmarks." />
      <Alert tone="warning" title="Synthetic rule scores are an upper bound">The rule playbook and the synthetic labels come from the same guideline. On real CUAD text the rules alone catch only a small share of deal-breakers.</Alert>

      {neg && full && noGate && mem && cold && (
        <Grid min={200}>
          <Stat label="Risky clauses signed unreviewed" value={full.unreviewed_risky_clauses_signed} tone="good" hint={`vs ${noGate.unreviewed_risky_clauses_signed} without the risk gate`} />
          <Stat label="Surplus captured · memory" value={pct(mem.surplus_share)} hint={`vs ${pct(cold.surplus_share)} cold start`} />
          <Stat label="Revenue per contract · memory" value={money(mem.revenue_per_contract, true)} hint={`vs ${money(cold.revenue_per_contract, true)} cold start`} />
          <Stat label="Audit chain" value={neg.audit_events.toLocaleString()} hint={neg.audit_verification.startsWith("OK") ? "events, chain intact" : neg.audit_verification} />
        </Grid>
      )}

      {cuad && (
        <>
          <h2>RO2 · Real contracts (CUAD)</h2>
          <Alert tone="info" title={`${cuad.n_clauses.toLocaleString()} lawyer-highlighted clauses from ${cuad.n_contracts} real contracts`}>
            Ground truth: {cuad.expert_labelled ? `${cuad.expert_labelled} expert labels, the rest` : "all"} CUAD proxy labels (deal-breaker categories). Proxy labels ignore which party a clause binds, so expect noise. Add expert labels on the Annotate page.
          </Alert>
          <Card title="F1 by approach" subtitle="Needs-a-human detection, 5-fold grouped by contract (no contract in both train and test)">
            <MetricBars data={Object.entries(cuad.results).map(([k, v]: [string, any]) => ({ name: k.replace("ablation: ", ""), value: v.f1 }))}
              format={(v) => v.toFixed(2)} height={230} highlight="hybrid (CUAD, CV)" />
          </Card>
          <Card title="Precision and recall per approach" flush><PRTable data={cuad.results} /></Card>
          <Grid min={360}>
          <Card title="Recall on each deal-breaker category" flush>
            <Table rows={cuad.recall_by_category} rowKey={(r: any) => r.category} columns={[
              { key: "c", header: "CUAD category", render: (r: any) => r.category },
              { key: "n", header: "Clauses", num: true, render: (r: any) => r.n },
              { key: "r", header: "Rules", num: true, render: (r: any) => pct(r.rules_recall) },
              { key: "h", header: "Hybrid (CUAD-trained)", num: true, render: (r: any) => <b>{pct(r.hybrid_cuad_recall)}</b> },
            ]} />
          </Card>
          <Card title="Contract Analyst clause-type accuracy" subtitle="Real text, no headings">
            <KeyValue items={[["Keyword rules", pct(cuad.analyst_type_accuracy.keywords)], ["Learned classifier (CV)", pct(cuad.analyst_type_accuracy["learned (CV)"])]]} />
          </Card>
          </Grid>
        </>
      )}

      {cuad?.held_out_test && Object.keys(cuad.held_out_test).length > 0 && (
        <Card title={`Held-out test contracts (n=${cuad.n_test_clauses?.toLocaleString()} clauses, ${cuad.n_test_contracts} contracts)`}
          subtitle="Locked 20% of CUAD contracts, never used for training or tuning. Report these once." flush>
          <PRTable data={cuad.held_out_test} />
        </Card>
      )}

      {llmEv && (
        <>
          <h2>Language model experiments · {llmEv.model}</h2>
          <Card title="Can the Communication Agent read real customer replies?"
            subtitle={`Share of ${parsing.n_messages} messages parsed fully correctly (price, payment days, acceptance, clause responses), by writing style${llmEv.parsing_hybrid ? ". LLM column = regex-first hybrid (post-hoc revision, same messages)" : ""}`} flush>
            <Table rows={Object.keys(Object.values(parsing.results as Record<string, any>)[0].by_style).map((style) => ({ style }))}
              rowKey={(r) => r.style} columns={[
                { key: "s", header: "Writing style", render: (r) => <Stack gap={2}><b>{titleCaseLocal(r.style)}</b><span className="nx-muted" style={{ fontSize: "var(--text-xs)" }}>{String(parsing.examples[r.style]).slice(0, 110)}…</span></Stack> },
                ...Object.keys(parsing.results).map((parser) => ({
                  key: parser, header: parser, num: true,
                  render: (r: { style: string }) => pct(parsing.results[parser].by_style[r.style]),
                })),
              ]} />
          </Card>
          {llmEv.risk_held_out && Object.keys(llmEv.risk_held_out).length > 0 && (
            <Card title="Risk scoring with the language model" subtitle="Stratified sample of held-out CUAD test clauses" flush>
              <PRTable data={llmEv.risk_held_out} />
            </Card>
          )}
          {llmEv.negotiation && (
            <Card title="Single monolithic LLM vs CoNexus" subtitle="Same contracts and simulated buyers" flush>
              <Table rows={llmEv.negotiation as Row[]} rowKey={(r) => r.system} columns={[
                { key: "s", header: "System", render: (r) => r.system },
                { key: "a", header: "Agree", num: true, render: (r) => pct(r.agreement_rate) },
                { key: "e", header: "Escalate", num: true, render: (r) => pct(r.escalation_rate) },
                { key: "sh", header: "Surplus", num: true, render: (r) => f3(r.surplus_share) },
                { key: "x", header: "Unreviewed risky", num: true, render: (r) => r.unreviewed_risky_clauses_signed ? <Badge tone="critical">{r.unreviewed_risky_clauses_signed}</Badge> : <Badge tone="good">0</Badge> },
                { key: "ms", header: "Seconds / contract", num: true, render: (r) => (r.runtime_ms_per_contract / 1000).toFixed(1) },
              ]} />
            </Card>
          )}
        </>
      )}

      {esc && (
        <>
          <h2>RO2 · Escalation policy (synthetic)</h2>
          <div className="nx-split">
            <Card title="Precision and recall by threshold" subtitle="Hybrid risk score before hard rules; dashed line = configured threshold 0.5">
              <ThresholdChart sweep={esc.hybrid_threshold_sweep_scores_only} threshold={0.5} />
            </Card>
            <Stack gap={16}>
              <Card title="Clause level" subtitle={`Grouped CV over wording families · n=${esc.n_clauses}`} flush>
                <PRTable data={esc.clause_level} />
              </Card>
              <Card title="Contract level" subtitle={`Cross-fitted · n=${esc.n_contracts}, ${esc.positives} should escalate`} flush>
                <PRTable data={esc.contract_level} />
              </Card>
            </Stack>
          </div>
        </>
      )}

      {neg && (
        <>
          <h2>RO3 · Memory-grounded pricing</h2>
          <Grid min={320}>
            <Card title="Share of the deal zone captured" subtitle={`Negotiation only, n=${neg.n_zopa} contracts with a deal zone`}>
              <MetricBars data={tB.map((r) => ({ name: r.system, value: r.surplus_share }))} format={(v) => v.toFixed(2)} height={170} highlight={mem?.system} />
            </Card>
            <Card title="Agreement rate" subtitle="Same contracts and buyers">
              <MetricBars data={tB.map((r) => ({ name: r.system, value: r.agreement_rate }))} format={(v) => pct(v)} height={170} highlight={mem?.system} />
            </Card>
          </Grid>
          <h2>RO5 · End to end, baselines and ablations</h2>
          <Card title="Table A" subtitle={`All ${neg.n_contracts} contracts. Human-only is modelled, not measured.`} flush>
            <Table rows={tA} rowKey={(r) => r.system} columns={[
              { key: "s", header: "System", render: (r) => r.system.startsWith("conexus") ? <b>{r.system}</b> : r.system },
              { key: "a", header: "Agree", num: true, render: (r) => pct(r.agreement_rate) },
              { key: "e", header: "Escalate", num: true, render: (r) => pct(r.escalation_rate) },
              { key: "r", header: "Rounds", num: true, render: (r) => r.avg_rounds_to_agree ?? "—" },
              { key: "w", header: "Price / WTP", num: true, render: (r) => f3(r.price_over_wtp) },
              { key: "sh", header: "Surplus", num: true, render: (r) => f3(r.surplus_share) },
              { key: "x", header: "Unreviewed risky", num: true, render: (r) => r.unreviewed_risky_clauses_signed ? <Badge tone="critical">{r.unreviewed_risky_clauses_signed}</Badge> : <Badge tone="good">0</Badge> },
              { key: "d", header: "Days", num: true, render: (r) => r.est_days_to_outcome },
              { key: "ms", header: "ms / contract", num: true, render: (r) => r.runtime_ms_per_contract ?? "—" },
            ]} />
          </Card>
          <p className="nx-muted" style={{ fontSize: "var(--text-xs)" }}>Time model assumptions: {Object.entries(neg.time_model).map(([k, v]) => `${k.replace(/_/g, " ")} = ${v}`).join(" · ")}</p>
        </>
      )}
    </Stack>
  );
}

const titleCaseLocal = (s: string) => s.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());

function PRTable({ data }: { data: Record<string, { precision: number; recall: number; f1: number; tp: number; fp: number; fn: number }> }) {
  const rows = Object.entries(data).map(([mode, m]) => ({ mode, ...m }));
  return <Table rows={rows} rowKey={(r) => r.mode} columns={[
    { key: "m", header: "Mode", render: (r) => r.mode },
    { key: "p", header: "Precision", num: true, render: (r) => f3(r.precision) },
    { key: "r", header: "Recall", num: true, render: (r) => f3(r.recall) },
    { key: "f", header: "F1", num: true, render: (r) => <b>{f3(r.f1)}</b> },
    { key: "c", header: "TP / FP / FN", num: true, render: (r) => `${r.tp} / ${r.fp} / ${r.fn}` },
  ]} />;
}
