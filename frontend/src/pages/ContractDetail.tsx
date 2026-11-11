import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { Activity, BookOpenCheck, Gavel, MessagesSquare, Play, Send, TrendingUp } from "lucide-react";
import {
  Alert, AuditTimeline, Badge, Button, Card, ChoiceGroup, ClauseCard, DealStepper, EmptyState, Field, Grid, KeyValue,
  PageHeader, PriceChart, Range, Row, Segmented, SignatureStamp, Skeleton, Stack, Stat, StatusBadge, Table, Tabs, Textarea,
  useToast, NegotiationThread, Input,
} from "@ui";
import { api, ApiError, ContractState, money, titleCase } from "@lib/api";
import { useApi } from "@lib/hooks";
import { DecisionPanel, ErrorState, EscalationSummary } from "./shared";

type Tab = "negotiation" | "clauses" | "pricing" | "audit";

export default function ContractDetail({ onChange }: { onChange: () => void }) {
  const { id = "" } = useParams();
  const c = useApi(() => api.contract(id), [id], (d) => (d?.status === "awaiting_reply" && d.mode === "simulated" ? 900 : 4000));
  const audit = useApi(() => api.audit(id), [id, c.data?.updated_at]);
  const [tab, setTab] = useState<Tab>("negotiation");

  if (c.error) return <ErrorState error={c.error} onRetry={c.reload} />;
  if (!c.data) return <Stack><Skeleton height={60} /><Skeleton height={300} /></Stack>;
  const s = c.data;
  const ctx = s.context;
  const flagged = s.risks.filter((r) => r.requires_human || r.level !== "low").length;
  const update = (n: ContractState) => { c.setData(n); onChange(); };

  return (
    <Stack gap={20}>
      <PageHeader eyebrow={<span className="nx-mono">{s.id}</span>} title={ctx.customer}
        description={`${titleCase(ctx.segment)} · ${ctx.region.toUpperCase()} · ${titleCase(ctx.product)} × ${ctx.seats} seats · list ${money(ctx.list_price)}/yr${s.filename ? ` · ${s.filename}` : ""}`}
        actions={<StatusBadge status={s.status} />} />
      <DealStepper status={s.status} everEscalated={s.human_decisions.length > 0 || s.status === "awaiting_human"} />

      {s.status === "awaiting_human" && s.escalation && (
        <Card title="The agents need a decision" tone="critical">
          <Stack gap={16}><EscalationSummary escalation={s.escalation} /><DecisionPanel id={s.id} escalation={s.escalation} onDone={update} /></Stack>
        </Card>
      )}
      {s.status === "signed" && s.outcome?.final_terms && (
        <Card flat>
          <Row justify="between" gap={24}>
            <Stack gap={4}>
              <h3>Agreed in {s.outcome.rounds} rounds</h3>
              <span className="nx-secondary">{s.outcome.accepted_redlines.length} redlines accepted · {s.reviewed_clauses.length} clauses cleared by a reviewer · {s.outcome.signed_unreviewed_risky_clauses} risky clauses signed without review</span>
            </Stack>
            <SignatureStamp envelope={s.outcome.envelope_id ?? ""} terms={s.outcome.final_terms} />
          </Row>
        </Card>
      )}
      {s.status === "closed" && s.outcome && (
        <Alert tone="warning" title={`Closed: ${titleCase(s.outcome.status)}`}>After {s.outcome.rounds} rounds. {s.human_decisions.at(-1)?.note && `Reviewer note: “${s.human_decisions.at(-1)!.note}”`}</Alert>
      )}
      {s.status === "analyzed" && <StartNegotiation s={s} onStarted={update} />}
      {s.status === "awaiting_reply" && s.mode === "email" && <ReplyBox id={s.id} onDone={update} />}

      <div className="nx-split">
        <Card flush>
          <div style={{ padding: "0 var(--s-4)" }}>
            <Tabs<Tab> value={tab} onChange={setTab} tabs={[
              { value: "negotiation", label: "Negotiation", icon: <MessagesSquare size={15} />, count: Math.max(0, s.history.length - 1) },
              { value: "clauses", label: "Clauses", icon: <Gavel size={15} />, count: s.clauses.length },
              { value: "pricing", label: "Pricing & memory", icon: <TrendingUp size={15} /> },
              { value: "audit", label: "Audit trail", icon: <BookOpenCheck size={15} />, count: audit.data?.length },
            ]} />
          </div>
          <div style={{ padding: "var(--s-5)" }}>
            {tab === "negotiation" && (s.history.length ? (
              <Stack gap={24}><PriceChart history={s.history} plan={s.plan} /><NegotiationThread history={s.history} customer={ctx.customer} /></Stack>
            ) : <EmptyState icon={<Activity size={28} />} title="Negotiation hasn't started">Start it above. You will see every offer, counter-offer and the price path here.</EmptyState>)}
            {tab === "clauses" && <ClauseList s={s} />}
            {tab === "pricing" && <PricingPanel s={s} />}
            {tab === "audit" && (audit.data?.length ? <AuditTimeline events={audit.data} /> : <EmptyState title="No audit events yet" />)}
          </div>
        </Card>

        <Stack gap={16}>
          <Card title="Deal">
            <KeyValue items={[
              ["Their opening", s.opening_terms ? `${money(s.opening_terms.price)} · net ${s.opening_terms.payment_days}` : "Not found"],
              ["Our last offer", s.last_our_offer ? `${money(s.last_our_offer.price)} · net ${s.last_our_offer.payment_days}` : "—"],
              ["Their last offer", s.their_last ? `${money(s.their_last.price)} · net ${s.their_last.payment_days}` : "—"],
              ["Round", s.round || "—"],
              ["Channel", s.mode === "none" ? "Not started" : titleCase(s.mode)],
            ]} />
          </Card>
          <Card title="Risk summary">
            <Stack gap={12}>
              <Row gap={8}>
                {(() => {
                  const human = s.risks.filter((r) => r.requires_human);
                  const open = human.filter((r) => !s.reviewed_clauses.includes(r.clause_id) && !s.redline_results[r.clause_id]).length;
                  return <>
                    {open > 0 && <Badge tone="critical" dot>{open} need human</Badge>}
                    {human.length - open > 0 && <Badge tone="good" dot>{human.length - open} risky, resolved</Badge>}
                  </>;
                })()}
                <Badge tone="warning" dot>{s.risks.filter((r) => r.level !== "low" && !r.requires_human).length} off-market</Badge>
                <Badge tone="good" dot>{s.risks.filter((r) => r.level === "low").length} standard</Badge>
              </Row>
              {s.pending_redlines.length > 0 && (
                <KeyValue items={s.pending_redlines.map((cid) => [
                  <span className="nx-mono">§ {cid.slice(1)}</span>,
                  s.redline_results[cid] === undefined ? <Badge>Proposed</Badge> : s.redline_results[cid] ? <Badge tone="good">Accepted</Badge> : <Badge tone="serious">Rejected</Badge>,
                ])} />
              )}
              <Button size="sm" variant="ghost" onClick={() => setTab("clauses")}>Review {flagged} flagged clauses</Button>
            </Stack>
          </Card>
          {s.human_decisions.length > 0 && (
            <Card title="Human decisions">
              <Stack gap={8}>{s.human_decisions.map((d, i) => (
                <Row key={i} gap={8}><Badge tone={d.approve ? "good" : "critical"}>{d.approve ? "Approved" : "Rejected"}</Badge><b>{d.reviewer}</b><span className="nx-secondary">{d.note}</span></Row>
              ))}</Stack>
            </Card>
          )}
        </Stack>
      </div>
    </Stack>
  );
}

/* ------------------------------------------------------------------ start */
function StartNegotiation({ s, onStarted }: { s: ContractState; onStarted: (n: ContractState) => void }) {
  const toast = useToast();
  const scenario = useMemo(() => { try { return JSON.parse(sessionStorage.getItem(`nx-scenario-${s.id}`) || "null"); } catch { return null; } }, [s.id]);
  const [mode, setMode] = useState<"simulated" | "email">("simulated");
  const [persona, setPersona] = useState<string>(scenario?.persona ?? "cooperative");
  const [wtp, setWtp] = useState<number>(Math.round(scenario?.wtp ?? s.context.list_price * 0.8));
  const [delay, setDelay] = useState(1.2);
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const gateBlocks = s.risks.some((r) => r.requires_human && !r.redlinable);

  async function start() {
    setBusy(true);
    try {
      onStarted(await api.negotiate(s.id, mode === "simulated" ? { mode, persona, wtp, delay_s: delay } : { mode, counterparty_email: email }));
    } catch (e) { toast((e as ApiError).message, "critical"); } finally { setBusy(false); }
  }

  return (
    <Card title="Start autonomous negotiation" subtitle="Analysis is done. Choose who the agents negotiate with.">
      <Stack gap={16}>
        {gateBlocks && <Alert tone="warning" title="This contract will go straight to a reviewer">It has a clause the agents may not accept on their own. Starting sends it to the escalation inbox first.</Alert>}
        <Segmented label="Counterparty channel" value={mode} onChange={setMode} options={[
          { value: "simulated", label: "Simulated buyer" }, { value: "email", label: "Real e-mail" },
        ]} />
        {mode === "simulated" ? (
          <>
            <ChoiceGroup label="Buyer persona" value={persona} onChange={setPersona} options={[
              { value: "cooperative", title: "Cooperative", detail: "Concedes quickly, accepts most redlines" },
              { value: "hardball", title: "Hardball", detail: "Slow concessions, rejects redlines, may add terms" },
              { value: "deadline", title: "Deadline", detail: "Stalls, then concedes near the end" },
            ]} />
            <Grid min={240}>
              <Field label="Buyer's private budget" htmlFor="wtp" hint={`Hidden from the agents. List is ${money(s.context.list_price)}/yr.`}>
                <Range id="wtp" value={wtp} onChange={setWtp} min={Math.round(s.context.list_price * 0.3)} max={Math.round(s.context.list_price * 1.4)} step={10} format={(v) => money(v, true)} />
              </Field>
              <Field label="Pause between rounds" htmlFor="delay" hint="Slows the simulation so you can watch it live">
                <Range id="delay" value={delay} onChange={setDelay} min={0} max={4} step={0.2} format={(v) => `${v.toFixed(1)} s`} />
              </Field>
            </Grid>
          </>
        ) : (
          <Field label="Counterparty e-mail" htmlFor="cp-email" hint="Offers go out over SMTP when configured. Replies arrive through the webhook or the box that appears below.">
            <Input id="cp-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="procurement@customer.com" />
          </Field>
        )}
        <Row justify="end"><Button variant="primary" icon={<Play size={16} />} loading={busy} onClick={start}>Start negotiation</Button></Row>
      </Stack>
    </Card>
  );
}

/* ------------------------------------------------------------------ reply */
function ReplyBox({ id, onDone }: { id: string; onDone: (n: ContractState) => void }) {
  const toast = useToast();
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <Card title="Waiting for the customer's reply" subtitle="Paste it here, or have your mail provider POST it to the reply webhook.">
      <Stack gap={12}>
        <Textarea id="reply" aria-label="Customer reply" value={msg} onChange={(e) => setMsg(e.target.value)}
          placeholder="e.g. We can do $18,500 per year with payment net 45 days. We cannot accept the change to clause c6." />
        <Row justify="end">
          <Button variant="primary" icon={<Send size={16} />} loading={busy} disabled={!msg.trim()} onClick={async () => {
            setBusy(true);
            try { onDone(await api.reply(id, msg)); setMsg(""); } catch (e) { toast((e as ApiError).message, "critical"); } finally { setBusy(false); }
          }}>Process reply</Button>
        </Row>
      </Stack>
    </Card>
  );
}

/* ------------------------------------------------------------------ clauses */
function ClauseList({ s }: { s: ContractState }) {
  const [only, setOnly] = useState<"flagged" | "all">("flagged");
  const risks = Object.fromEntries(s.risks.map((r) => [r.clause_id, r]));
  const shown = s.clauses.filter((c) => only === "all" || risks[c.id].level !== "low" || risks[c.id].requires_human);
  return (
    <Stack gap={12}>
      <Segmented label="Clause filter" value={only} onChange={setOnly} options={[{ value: "flagged", label: `Flagged ${shown.length && only === "flagged" ? shown.length : ""}` }, { value: "all", label: `All ${s.clauses.length}` }]} />
      {shown.length ? shown.map((c) => (
        <ClauseCard key={c.id} clause={c} risk={risks[c.id]} reviewed={s.reviewed_clauses.includes(c.id)} redlineStatus={s.redline_results[c.id]}
          defaultOpen={risks[c.id].requires_human} />
      )) : <EmptyState title="No flagged clauses">Every clause matches the standard playbook.</EmptyState>}
    </Stack>
  );
}

/* ------------------------------------------------------------------ pricing */
function PricingPanel({ s }: { s: ContractState }) {
  const p = s.plan;
  if (!p) return <EmptyState icon={<TrendingUp size={28} />} title="No pricing plan yet">The Memory and Pricing agents build it when negotiation starts.</EmptyState>;
  return (
    <Stack gap={20}>
      <Grid min={150}>
        <Stat label="Anchor" value={money(p.anchor.price, true)} hint="First ask" />
        <Stat label="Est. buyer budget" value={money(p.wtp_estimate, true)} hint="From similar deals" />
        <Stat label="Concession limit" value={money(p.concession_limit, true)} hint="Until the last round" />
        <Stat label="Policy floor" value={money(p.floor_price, true)} hint="Never below" />
      </Grid>
      <Alert tone="info" title="Memory evidence">{p.evidence.join(" · ")}</Alert>
      {s.similar_deals.length > 0 && (
        <Card title="Most similar past deals" flush flat>
          <Table rows={s.similar_deals} rowKey={(d) => d.deal_id} columns={[
            { key: "id", header: "Deal", render: (d) => <span className="nx-mono">{d.deal_id}</span> },
            { key: "seg", header: "Segment", render: (d) => `${titleCase(d.segment)} · ${d.region.toUpperCase()}` },
            { key: "prod", header: "Product", render: (d) => `${titleCase(d.product)} ×${d.seats}` },
            { key: "list", header: "List", num: true, render: (d) => money(d.list_price) },
            { key: "final", header: "Final", num: true, render: (d) => money(d.final_price) },
            { key: "ratio", header: "% of list", num: true, render: (d) => `${Math.round((d.final_price / d.list_price) * 100)}%` },
            { key: "won", header: "Result", render: (d) => d.won ? <Badge tone="good">Won</Badge> : <Badge tone="critical">Lost</Badge> },
          ]} />
        </Card>
      )}
    </Stack>
  );
}
