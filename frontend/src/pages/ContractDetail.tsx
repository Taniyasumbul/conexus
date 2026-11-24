import { ReactNode, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { Activity, CheckCircle2, FileDown, FileText, Gavel, Hand, Mail, MessagesSquare, Play, Send, TrendingUp, XCircle } from "lucide-react";
import {
  ActivityFeed, Alert, AnalysisReveal, AuditTimeline, Badge, Breadcrumbs, Button, Card, ChoiceGroup, ClauseCard, ContractFingerprint,
  DealStepper, DocumentView, EmptyState, Field, Grid, Input, KeyValue, NegotiationThread, NextAction, PageHeader, PriceChart, PriceRuler,
  Range, Row, Segmented, SignatureStamp, Skeleton, Stack, Stat, StatusBadge, Table, Tabs, Textarea, usePrevious, useToast,
} from "@ui";
import { api, ApiError, ContractState, money, titleCase } from "@lib/api";
import { useApi } from "@lib/hooks";
import { useAuth } from "@lib/auth";
import { DecisionPanel, ErrorState } from "./shared";

type Tab = "document" | "negotiation" | "review" | "activity";

/** The tab that answers "what do I need to look at now" for each stage. */
function defaultTab(s: ContractState): Tab {
  if (s.status === "awaiting_human") return "review";
  if (s.status === "analyzed" || !s.history.length) return "document";
  return "negotiation";
}

export default function ContractDetail({ onChange }: { onChange: () => void }) {
  const { id = "" } = useParams();
  const toast = useToast();
  const c = useApi(() => api.contract(id), [id], (d) => (d?.status === "awaiting_reply" && d.mode === "simulated" ? 900 : 4000));
  const audit = useApi(() => api.audit(id), [id, c.data?.updated_at]);
  const [picked, setPicked] = useState<Tab | null>(null);
  const [docSel, setDocSel] = useState<string | null>(null);
  const status = c.data?.status;
  const prevStatus = usePrevious(status);
  // show the analysis summary once, right after the contract was created
  const [fresh, setFresh] = useState(() => { try { return sessionStorage.getItem(`nx-fresh-${id}`) === "1"; } catch { return false; } });
  useEffect(() => { try { sessionStorage.removeItem(`nx-fresh-${id}`); } catch { /* ignore */ } }, [id]);
  useEffect(() => {
    if (prevStatus && prevStatus !== status) {
      setPicked(null);  // the stage changed: follow it to the tab that matters now
      if (status === "signed") toast("Deal agreed and sent for signature", "good");
      if (status === "awaiting_human") toast("Paused for a Legal decision", "critical");
    }
  }, [status, prevStatus, toast]);

  if (c.error) return <ErrorState error={c.error} onRetry={c.reload} />;
  if (!c.data) return <Stack><Skeleton height={60} /><Skeleton height={120} /><Skeleton height={300} /></Stack>;
  const s = c.data;
  const ctx = s.context;
  const tab = picked ?? defaultTab(s);
  const update = (n: ContractState) => { c.setData(n); onChange(); };
  const openClause = (cid: string) => { setDocSel(cid); setPicked("document"); };
  const openRisks = s.risks.filter((r) => r.requires_human && !s.reviewed_clauses.includes(r.clause_id) && !s.redline_results[r.clause_id]).length;
  const flagged = s.risks.filter((r) => r.requires_human || r.level !== "low").length;

  return (
    <Stack gap={16}>
      <Breadcrumbs items={[{ label: "Contracts", to: "/contracts" }, { label: s.id }]} />
      <PageHeader title={ctx.customer}
        description={`${titleCase(ctx.segment)} · ${ctx.region.toUpperCase()} · ${titleCase(ctx.product)} × ${ctx.seats} seats · list ${money(ctx.list_price)}/yr${s.filename ? ` · ${s.filename}` : ""}`}
        actions={<>
          <StatusBadge status={s.status} />
          <a className="nx-btn nx-btn--secondary nx-btn--sm" href={api.redlineUrl(s.id)} download
            title="Word document with every redline as a tracked change and a margin comment explaining why">
            <FileDown size={16} />Redlined .docx
          </a>
        </>} />
      <DealStepper status={s.status} everEscalated={s.human_decisions.length > 0 || s.status === "awaiting_human"} />

      <NextStep s={s} onDone={update} />
      {fresh && s.status === "analyzed" && (
        <Card title="What CoNexus found" subtitle="Select a clause to read it in the document"
          actions={<Button size="sm" variant="ghost" onClick={() => setFresh(false)}>Dismiss</Button>}>
          <AnalysisReveal clauses={s.clauses} risks={s.risks} onOpen={openClause} />
        </Card>
      )}
      {s.status === "analyzed" && <StartNegotiation s={s} onStarted={update} />}
      {s.status === "awaiting_reply" && s.mode === "email" && <ReplyBox id={s.id} onDone={update} />}

      <div className="nx-workspace">
        <Card flush>
          <div style={{ padding: "0 var(--s-4)" }}>
            <Tabs<Tab> value={tab} onChange={setPicked} tabs={[
              { value: "document", label: "Document", icon: <FileText size={15} /> },
              { value: "negotiation", label: "Negotiation", icon: <MessagesSquare size={15} />, count: Math.max(0, s.history.length - 1) },
              { value: "review", label: "Review", icon: <Gavel size={15} />, count: flagged },
              { value: "activity", label: "Activity", icon: <Activity size={15} />, count: audit.data?.length },
            ]} />
          </div>
          <div style={{ padding: "var(--s-5)" }} role="tabpanel">
            {tab === "document" && <DocumentTab s={s} initial={docSel} />}
            {tab === "negotiation" && (s.history.length ? (
              <Stack gap={24}>
                {s.plan && <PriceRuler history={s.history} plan={s.plan} agreed={s.status === "signed" ? s.outcome?.final_terms?.price : s.agreed_terms?.price} />}
                <PriceChart history={s.history} plan={s.plan} />
                <NegotiationThread history={s.history} customer={ctx.customer} />
              </Stack>
            ) : <EmptyState icon={<MessagesSquare size={28} />} title="Negotiation hasn't started">
                {s.status === "analyzed" ? "Start it from the panel above. Every offer, counter-offer and the price path appear here." : "This contract closed before any offer was sent."}
              </EmptyState>)}
            {tab === "review" && <ReviewTab s={s} />}
            {tab === "activity" && <ActivityTab s={s} events={audit.data} />}
          </div>
        </Card>

        <aside className="nx-workspace__rail" aria-label="Contract context">
          <Card title="Key terms">
            <KeyValue items={[
              ["Customer opened at", s.opening_terms ? `${money(s.opening_terms.price)} · net ${s.opening_terms.payment_days}` : "Not stated"],
              ["Our last offer", s.last_our_offer ? `${money(s.last_our_offer.price)} · net ${s.last_our_offer.payment_days}` : "—"],
              ["Their last offer", s.their_last ? `${money(s.their_last.price)} · net ${s.their_last.payment_days}` : "—"],
              ["Round", s.round || "—"],
              ["Channel", s.mode === "none" ? "Not started" : s.mode === "email" ? `E-mail${ctx.contact_email ? ` · ${ctx.contact_email}` : ""}` : "Simulated buyer"],
            ]} />
          </Card>
          <Card title="Risk summary" subtitle={openRisks ? `${openRisks} clause${openRisks > 1 ? "s" : ""} need${openRisks > 1 ? "" : "s"} Legal` : "No open Legal items"}>
            <Stack gap={12}>
              <ContractFingerprint clauses={s.clauses} risks={s.risks} onPick={() => setPicked("review")}
                resolved={(cid) => s.reviewed_clauses.includes(cid) || s.redline_results[cid] === true} />
              <Row gap={6}>
                {openRisks > 0 && <Badge tone="critical" dot>{openRisks} need Legal</Badge>}
                <Badge tone="warning" dot>{s.risks.filter((r) => r.level !== "low" && !r.requires_human).length} off-market</Badge>
                <Badge tone="good" dot>{s.risks.filter((r) => r.level === "low").length} standard</Badge>
              </Row>
              <Button size="sm" variant="ghost" onClick={() => setPicked("review")}>Review {flagged} flagged clauses</Button>
            </Stack>
          </Card>
          <Card title="Latest activity" actions={<Button size="sm" variant="ghost" onClick={() => setPicked("activity")}>All</Button>}>
            {audit.data ? <ActivityFeed events={[...audit.data].reverse().slice(0, 4)} /> : <Skeleton height={100} />}
          </Card>
        </aside>
      </div>
    </Stack>
  );
}

/* ------------------------------------------------------------------ next action */
function NextStep({ s, onDone }: { s: ContractState; onDone: (n: ContractState) => void }) {
  const { can } = useAuth();
  const gateBlocks = s.risks.some((r) => r.requires_human && !r.redlinable);
  const lastNote = s.human_decisions.at(-1)?.note;
  let node: ReactNode = null;
  switch (s.status) {
    case "analyzed":
      node = <NextAction tone="info" owner="Sales" icon={<Play size={18} />} title="Start negotiation">
        {gateBlocks ? "A clause needs Legal before the agents may negotiate, so starting sends this contract to the review queue first."
          : `${s.clauses.length} clauses read, ${s.risks.filter((r) => r.level !== "low").length} flagged. Choose who the agents negotiate with below.`}
      </NextAction>;
      break;
    case "awaiting_human":
      node = s.escalation && <NextAction tone="critical" owner="Legal" icon={<Hand size={18} />}
        title={can("legal") ? `Your decision: ${titleCase(s.escalation.kind)}` : `Waiting on Legal: ${titleCase(s.escalation.kind)}`}>
        <Stack gap={12}>
          <ul style={{ margin: 0, paddingLeft: "1.1em" }}>{s.escalation.triggers.map((t) => <li key={t}>{t}</li>)}</ul>
          <DecisionPanel id={s.id} escalation={s.escalation} onDone={onDone} />
        </Stack>
      </NextAction>;
      break;
    case "awaiting_reply":
      node = s.mode === "email"
        ? <NextAction tone="info" owner="Customer" icon={<Mail size={18} />} title="Waiting for the customer's reply">
            Offer for round {s.round} sent{s.context.contact_email ? ` to ${s.context.contact_email}` : ""}. Paste their reply below, or it arrives through the mail webhook.
          </NextAction>
        : <NextAction tone="info" owner="CoNexus" icon={<MessagesSquare size={18} />} title={`Negotiating · round ${s.round}`}>
            The simulated buyer is replying. This page updates on its own.
          </NextAction>;
      break;
    case "signed":
      node = s.outcome?.final_terms && <NextAction tone="good" owner="Customer" icon={<CheckCircle2 size={18} />}
        title={`Agreed in ${s.outcome.rounds} rounds · sent for signature`}
        actions={<SignatureStamp envelope={s.outcome.envelope_id ?? ""} terms={s.outcome.final_terms} />}>
        {s.outcome.accepted_redlines.length} redlines accepted · {s.reviewed_clauses.length} clauses cleared by Legal ·{" "}
        {s.outcome.signed_unreviewed_risky_clauses} risky clauses agreed without review. E-signature is a stub, so nothing is legally signed yet.
      </NextAction>;
      break;
    case "closed":
      node = s.outcome && <NextAction icon={<XCircle size={18} />} title={`Closed: ${titleCase(s.outcome.status)}`}>
        After {s.outcome.rounds} rounds. {lastNote ? `Reviewer note: “${lastNote}”` : "No further action."}
      </NextAction>;
      break;
  }
  return <>{node}</>;
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
  const [emailError, setEmailError] = useState("");
  const [busy, setBusy] = useState(false);

  async function start() {
    if (mode === "email" && !/^[^@\s]+@[^@\s]+\.[a-z]{2,}$/i.test(email.trim())) {
      setEmailError("Enter the customer contact's e-mail address.");
      return;
    }
    setBusy(true);
    try {
      onStarted(await api.negotiate(s.id, mode === "simulated" ? { mode, persona, wtp, delay_s: delay } : { mode, counterparty_email: email.trim() }));
    } catch (e) { toast((e as ApiError).message, "critical"); } finally { setBusy(false); }
  }

  return (
    <Card title="Negotiation setup" subtitle="Who the agents negotiate with">
      <Stack gap={16}>
        <Segmented label="Counterparty channel" value={mode} onChange={setMode} options={[
          { value: "simulated", label: "Simulated buyer (demo)" }, { value: "email", label: "Real customer by e-mail" },
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
              <Field label="Pause between rounds" htmlFor="delay" hint="Slows the simulation so you can follow it">
                <Range id="delay" value={delay} onChange={setDelay} min={0} max={4} step={0.2} format={(v) => `${v.toFixed(1)} s`} />
              </Field>
            </Grid>
          </>
        ) : (
          <Field label="Customer contact e-mail" htmlFor="cp-email" error={emailError}
            hint="Offers are sent here. Their replies arrive through the mail webhook or can be pasted on this page.">
            <Input id="cp-email" type="email" required value={email} aria-invalid={!!emailError}
              onChange={(e) => { setEmail(e.target.value); setEmailError(""); }} placeholder="procurement@customer.com" />
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
    <Card title="Record the customer's reply" subtitle="Paste their e-mail. CoNexus reads the price, payment terms and clause answers.">
      <Stack gap={12}>
        <Textarea id="reply" aria-label="Customer reply" value={msg} onChange={(e) => setMsg(e.target.value)}
          placeholder="e.g. We can do $18,500 per year with payment net 45 days. We cannot accept the change to clause c6." />
        <Row justify="end">
          <Button variant="primary" icon={<Send size={16} />} loading={busy} disabled={!msg.trim()} onClick={async () => {
            setBusy(true);
            try { onDone(await api.reply(id, msg)); setMsg(""); toast("Reply processed", "good"); } catch (e) { toast((e as ApiError).message, "critical"); } finally { setBusy(false); }
          }}>Process reply</Button>
        </Row>
      </Stack>
    </Card>
  );
}

/* ------------------------------------------------------------------ review: clauses + evidence */
function ReviewTab({ s }: { s: ContractState }) {
  const [only, setOnly] = useState<"flagged" | "all">("flagged");
  const risks = Object.fromEntries(s.risks.map((r) => [r.clause_id, r]));
  const flagged = s.clauses.filter((c) => risks[c.id].level !== "low" || risks[c.id].requires_human);
  const shown = only === "flagged" ? flagged : s.clauses;
  return (
    <Stack gap={16}>
      <Segmented label="Clause filter" value={only} onChange={setOnly}
        options={[{ value: "flagged", label: `Flagged ${flagged.length}` }, { value: "all", label: `All ${s.clauses.length}` }]} />
      {shown.length ? shown.map((c) => (
        <ClauseCard key={c.id} clause={c} risk={risks[c.id]} reviewed={s.reviewed_clauses.includes(c.id)} redlineStatus={s.redline_results[c.id]}
          defaultOpen={risks[c.id].requires_human} />
      )) : <EmptyState title="No flagged clauses">Every clause matches the standard playbook.</EmptyState>}
      <details className="nx-evidence">
        <summary>Pricing and deal-memory evidence</summary>
        <div><PricingPanel s={s} /></div>
      </details>
    </Stack>
  );
}

function PricingPanel({ s }: { s: ContractState }) {
  const p = s.plan;
  if (!p) return <EmptyState icon={<TrendingUp size={28} />} title="No pricing plan yet">It is built from similar past deals when negotiation starts.</EmptyState>;
  return (
    <Stack gap={16}>
      <Grid min={150}>
        <Stat label="Opening ask" value={money(p.anchor.price, true)} hint="First offer" />
        <Stat label="Est. buyer budget" value={money(p.wtp_estimate, true)} hint="From similar deals" />
        <Stat label="Concession limit" value={money(p.concession_limit, true)} hint="Until the last round" />
        <Stat label="Policy floor" value={money(p.floor_price, true)} hint="Never below" />
      </Grid>
      <Alert tone="info" title="Why these numbers">{p.evidence.join(" · ")}</Alert>
      {s.similar_deals.length > 0 && (
        <Table caption="Most similar past deals" rows={s.similar_deals} rowKey={(d) => d.deal_id} columns={[
          { key: "id", header: "Deal", render: (d) => <span className="nx-mono">{d.deal_id}</span> },
          { key: "seg", header: "Segment", render: (d) => `${titleCase(d.segment)} · ${d.region.toUpperCase()}` },
          { key: "prod", header: "Product", render: (d) => `${titleCase(d.product)} ×${d.seats}` },
          { key: "final", header: "Final", num: true, render: (d) => money(d.final_price) },
          { key: "ratio", header: "% of list", num: true, render: (d) => `${Math.round((d.final_price / d.list_price) * 100)}%` },
          { key: "won", header: "Result", render: (d) => d.won ? <Badge tone="good">Won</Badge> : <Badge tone="critical">Lost</Badge> },
        ]} />
      )}
    </Stack>
  );
}

/* ------------------------------------------------------------------ activity */
function ActivityTab({ s, events }: { s: ContractState; events?: import("@lib/api").AuditEvent[] }) {
  if (!events) return <Skeleton height={200} />;
  return (
    <Stack gap={16}>
      {s.human_decisions.length > 0 && (
        <Stack gap={8}>
          <h3 style={{ fontSize: "var(--text-md)" }}>Legal decisions</h3>
          {s.human_decisions.map((d, i) => (
            <Row key={i} gap={8}><Badge tone={d.approve ? "good" : "critical"}>{d.approve ? "Approved" : "Rejected"}</Badge><b>{d.reviewer}</b><span className="nx-secondary">{d.note || "No note"}</span></Row>
          ))}
        </Stack>
      )}
      <ActivityFeed events={[...events].reverse()} empty="Nothing has happened on this contract yet." />
      {events.length > 0 && (
        <details className="nx-evidence">
          <summary>Technical audit record (hash chain)</summary>
          <div><AuditTimeline events={events} /></div>
        </details>
      )}
    </Stack>
  );
}

/* ------------------------------------------------------------------ document */
function DocumentTab({ s, initial }: { s: ContractState; initial?: string | null }) {
  const doc = useApi(() => api.document(s.id), [s.id]);
  if (doc.error) return <ErrorState error={doc.error} onRetry={doc.reload} />;
  if (!doc.data) return <Skeleton height={420} />;
  return <DocumentView doc={doc.data} clauses={s.clauses} risks={s.risks} reviewed={s.reviewed_clauses} redlineResults={s.redline_results} initial={initial} />;
}
