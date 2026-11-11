import { ReactNode, useState } from "react";
import { Check, Download, Play, Trash2 } from "lucide-react";
import {
  Alert, AuditTimeline, Badge, Button, Card, ChoiceGroup, ClauseCard, DealStepper, Dialog, EmptyState, Field, Grid, HashChip,
  Input, KeyValue, NegotiationThread, PageHeader, PriceChart, Range, RedlineDiff, RiskBadge, Row, ScoreMeter, Segmented, Select,
  SignatureStamp, Skeleton, Spinner, Stack, Stat, StatusBadge, Table, Tabs, Textarea, useToast,
} from "@ui";
import type { AuditEvent, Clause, ClauseRisk, Offer, PricingPlan } from "@lib/api";

/* Example data for the gallery only - not real contracts. */
const EX_CLAUSE: Clause = { id: "c6", type: "liability_cap", heading: "6 Limitation of Liability", type_confidence: 0.9,
  text: "Vendor's aggregate liability shall not exceed ten (10) times the total contract value, and the exclusion of consequential damages shall apply only to Customer." };
const EX_RISK: ClauseRisk = { clause_id: "c6", clause_type: "liability_cap", level: "high", score: 0.91, requires_human: true, redlinable: true, source: "hybrid",
  redline: "Each party's aggregate liability shall not exceed the fees paid in the twelve (12) months preceding the claim; neither party is liable for indirect or consequential damages.",
  reasons: ["Liability cap far above market (>2x fees)", "One-sided exclusion of consequential damages"] };
const EX_HISTORY: Offer[] = [
  { round: 0, sender: "them", terms: { price: 12450, payment_days: 60, term_months: 12 }, message: "", accept: false, walk_away: false, redline_responses: {}, new_legal_terms: false },
  { round: 1, sender: "us", terms: { price: 17360, payment_days: 30, term_months: 12 }, message: "Our proposal: $17,360 per year, payment net 30 days, 12-month term.", accept: false, walk_away: false, redline_responses: {}, new_legal_terms: false },
  { round: 1, sender: "them", terms: { price: 13100, payment_days: 55, term_months: 12 }, message: "Our counter-proposal is $13,100 per year with payment net 55 days.", accept: false, walk_away: false, redline_responses: {}, new_legal_terms: false },
  { round: 2, sender: "us", terms: { price: 16200, payment_days: 35, term_months: 12 }, message: "Our proposal: $16,200 per year, payment net 35 days.", accept: false, walk_away: false, redline_responses: {}, new_legal_terms: false },
  { round: 2, sender: "them", terms: { price: 14300, payment_days: 45, term_months: 12 }, message: "We can do $14,300 per year, net 45.", accept: false, walk_away: false, redline_responses: {}, new_legal_terms: false },
  { round: 3, sender: "us", terms: { price: 15100, payment_days: 40, term_months: 12 }, message: "Our proposal: $15,100 per year, payment net 40 days.", accept: false, walk_away: false, redline_responses: {}, new_legal_terms: false },
  { round: 3, sender: "them", terms: { price: 15100, payment_days: 40, term_months: 12 }, message: "We accept your proposal of $15,100 per year, net 40. Deal.", accept: true, walk_away: false, redline_responses: {}, new_legal_terms: false },
];
const EX_PLAN: PricingPlan = { anchor: { price: 17444, payment_days: 30, term_months: 12 }, target: { price: 15400, payment_days: 30, term_months: 12 },
  floor_price: 12408, concession_limit: 13480, max_payment_days: 60, wtp_estimate: 15860, evidence: [] };
const EX_EVENTS: AuditEvent[] = [
  { seq: 0, ts: 1762800000, contract_id: "EX", agent: "contract_analyst", action: "EXTRACT_CLAUSES", rationale: "14 clauses; opening terms $12,450 / net 60", data: null, prev_hash: "0", hash: "8e297dde6f5162b2c41e" },
  { seq: 1, ts: 1762800001, contract_id: "EX", agent: "legal_risk", action: "FLAG_CLAUSE", rationale: "c6 liability_cap: level=high score=0.91 human=True", data: null, prev_hash: "8e29", hash: "a0c1fe3392b7d6e01aa2" },
  { seq: 2, ts: 1762800003, contract_id: "EX", agent: "orchestrator", action: "ESCALATE", rationale: "redline on risk-critical clause c6 rejected", data: null, prev_hash: "a0c1", hash: "37f9b2e8c6d1a0e4f5b2" },
  { seq: 3, ts: 1762803600, contract_id: "EX", agent: "human:dr.arya", action: "APPROVE", rationale: "redline_rejected: acceptable for this customer", data: null, prev_hash: "37f9", hash: "d4c415d43b4d736a9e10" },
  { seq: 4, ts: 1762803700, contract_id: "EX", agent: "orchestrator", action: "EXECUTE", rationale: "agreed $15,100/net40 in 3 rounds; envelope env-d83ab4717c", data: null, prev_hash: "d4c4", hash: "01266d87269b36f9d336" },
];

function Section({ id, title, note, children }: { id: string; title: string; note?: string; children: ReactNode }) {
  return (
    <Card title={<span id={id}>{title}</span>} subtitle={note}>
      <Stack gap={16}>{children}</Stack>
    </Card>
  );
}
const SWATCHES = ["bg", "surface", "surface-2", "border", "fg", "fg-2", "fg-3", "accent", "accent-soft", "good", "warning", "serious", "critical", "series-1", "series-2", "nav-bg"];

export default function Gallery() {
  const toast = useToast();
  const [seg, setSeg] = useState("week");
  const [choice, setChoice] = useState("hardball");
  const [tab, setTab] = useState("one");
  const [range, setRange] = useState(0.5);
  const [dialog, setDialog] = useState(false);

  return (
    <Stack gap={20}>
      <PageHeader eyebrow="Nexus UI" title="Component library"
        description="The design system every CoNexus screen is built from: tokens, primitives and contract-negotiation components. Import from @ui. All data on this page is example data." />

      <Section id="tokens" title="Tokens" note="Defined once in tokens.css; light and dark themes redefine the same names">
        <Grid min={110} gap={12}>{SWATCHES.map((s) => <div key={s} className="nx-swatch"><i style={{ background: `var(--${s})` }} /><code>--{s}</code></div>)}</Grid>
        <Stack gap={6}>
          <h1>Display 26 · Space Grotesk</h1>
          <h2>Heading 20 · contract portfolio</h2>
          <p>Body 14 · Inter. Customer shall pay undisputed invoices within thirty (30) days of the invoice date.</p>
          <code>Mono · JetBrains Mono · § c6 · sha256 8e297dde6f51 · $15,100 net 40</code>
        </Stack>
      </Section>

      <Section id="buttons" title="Button">
        <Row>
          <Button variant="primary" icon={<Play size={16} />}>Start negotiation</Button>
          <Button>Secondary</Button>
          <Button variant="ghost">Ghost</Button>
          <Button variant="success" icon={<Check size={16} />}>Approve</Button>
          <Button variant="danger" icon={<Trash2 size={16} />}>Reject deal</Button>
          <Button loading>Saving</Button>
          <Button disabled>Disabled</Button>
        </Row>
        <Row><Button size="sm">Small</Button><Button>Medium</Button><Button size="lg" icon={<Download size={18} />}>Large</Button></Row>
      </Section>

      <Section id="badges" title="Badge · StatusBadge · RiskBadge" note="State is always icon or text plus colour, never colour alone">
        <Row><Badge>Neutral</Badge><Badge tone="info">Info</Badge><Badge tone="good">Good</Badge><Badge tone="warning">Warning</Badge><Badge tone="serious">Serious</Badge><Badge tone="critical">Critical</Badge><Badge outline>Outline</Badge><Badge tone="good" dot>With dot</Badge></Row>
        <Row><StatusBadge status="analyzed" /><StatusBadge status="awaiting_reply" /><StatusBadge status="awaiting_human" /><StatusBadge status="signed" /><StatusBadge status="closed" /></Row>
        <Row><RiskBadge level="low" /><RiskBadge level="medium" /><RiskBadge level="high" needsHuman /></Row>
      </Section>

      <Section id="data" title="Stat · ScoreMeter · KeyValue · HashChip">
        <Grid min={180}><Stat label="Signed value / yr" value="$412K" hint="23 signed" /><Stat label="Needs a human" value={3} tone="critical" hint="In the inbox" /><Stat label="Unreviewed risky" value={0} tone="good" hint="Risk gate holding" /></Grid>
        <Grid min={220}>
          <Stack gap={8}><ScoreMeter score={0.12} /><ScoreMeter score={0.38} /><ScoreMeter score={0.91} /></Stack>
          <KeyValue items={[["Their opening", "$12,450 · net 60"], ["Our last offer", "$15,100 · net 40"], ["Round", 3]]} />
          <Row><HashChip hash="8e297dde6f5162b2c41e93aa" /><HashChip hash="01266d87269b36f9d3369ca51f434d8f" chars={20} /></Row>
        </Grid>
      </Section>

      <Section id="forms" title="Form controls">
        <Grid min={220}>
          <Field label="Customer" htmlFor="g-in" hint="As it appears on the contract"><Input id="g-in" placeholder="Helix Health" /></Field>
          <Field label="Segment" htmlFor="g-sel"><Select id="g-sel" options={[{ value: "smb", label: "SMB" }, { value: "ent", label: "Enterprise" }]} /></Field>
          <Field label="Threshold" htmlFor="g-range" hint="Clause escalation threshold"><Range id="g-range" value={range} onChange={setRange} min={0} max={1} step={0.05} format={(v) => v.toFixed(2)} /></Field>
          <Field label="Seats" htmlFor="g-err" error="Seats must be at least 1"><Input id="g-err" type="number" defaultValue={0} /></Field>
        </Grid>
        <Field label="Customer reply" htmlFor="g-ta"><Textarea id="g-ta" placeholder="We cannot accept the change to clause c6." /></Field>
        <Segmented label="Example" value={seg} onChange={setSeg} options={[{ value: "day", label: "Day" }, { value: "week", label: "Week" }, { value: "month", label: "Month" }]} />
        <ChoiceGroup label="Persona" value={choice} onChange={setChoice} options={[
          { value: "cooperative", title: "Cooperative", detail: "Concedes quickly" }, { value: "hardball", title: "Hardball", detail: "Rejects redlines" }, { value: "deadline", title: "Deadline", detail: "Late concessions" }]} />
      </Section>

      <Section id="nav" title="Tabs · DealStepper">
        <Tabs value={tab} onChange={setTab} tabs={[{ value: "one", label: "Negotiation", count: 6 }, { value: "two", label: "Clauses", count: 14 }, { value: "three", label: "Audit trail" }]} />
        <DealStepper status="awaiting_human" everEscalated />
        <DealStepper status="signed" everEscalated={false} />
      </Section>

      <Section id="feedback" title="Alert · Toast · Dialog · Empty · Loading">
        <Alert tone="info" title="Memory evidence">25 similar deals (18 won / 7 lost) → buyer budget ≈ 0.70× list</Alert>
        <Alert tone="good" title="Chain intact">2,980 events verified</Alert>
        <Alert tone="warning" title="Off-market payment terms">Net 90 is above the 30-day policy. An autonomous redline will be proposed.</Alert>
        <Alert tone="critical" title="Redline rejected · in negotiation">Redline on risk-critical clause c6 rejected</Alert>
        <Row>
          <Button onClick={() => toast("Approved. The agents have resumed.", "good")}>Show toast</Button>
          <Button onClick={() => toast("Couldn't reach the API.", "critical")}>Error toast</Button>
          <Button onClick={() => setDialog(true)}>Open dialog</Button>
          <Spinner />
        </Row>
        <Dialog open={dialog} onClose={() => setDialog(false)} title="Reject and close this deal?" footer={<><Button variant="ghost" onClick={() => setDialog(false)}>Keep it open</Button><Button variant="danger" onClick={() => setDialog(false)}>Reject deal</Button></>}>
          The agents stop negotiating and the decision is written to the audit ledger.
        </Dialog>
        <Grid min={240}><Skeleton height={80} /><Card flat><EmptyState title="Nothing needs you right now">Escalations land here.</EmptyState></Card></Grid>
      </Section>

      <Section id="table" title="Table" note="Numbers right-aligned with tabular figures; rows clickable with keyboard support">
        <Card flush flat>
          <Table rows={[{ id: "D00022", seg: "SMB · INDIA", list: 22560, fin: 15790, won: true }, { id: "D01377", seg: "SMB · INDIA", list: 19200, fin: 16900, won: false }]} rowKey={(r) => r.id} onRowClick={() => toast("Row clicked")} columns={[
            { key: "id", header: "Deal", render: (r) => <span className="nx-mono">{r.id}</span> },
            { key: "s", header: "Segment", render: (r) => r.seg },
            { key: "l", header: "List", num: true, render: (r) => `$${r.list.toLocaleString()}` },
            { key: "f", header: "Final", num: true, render: (r) => `$${r.fin.toLocaleString()}` },
            { key: "w", header: "Result", render: (r) => <Badge tone={r.won ? "good" : "critical"}>{r.won ? "Won" : "Lost"}</Badge> },
          ]} />
        </Card>
      </Section>

      <Section id="contract" title="ClauseCard · RedlineDiff" note="Word-level legal redline: deletions struck, insertions underlined">
        <ClauseCard clause={EX_CLAUSE} risk={EX_RISK} defaultOpen />
        <RedlineDiff original="Customer shall pay undisputed invoices within ninety (90) days of receipt." proposed="Customer shall pay undisputed invoices within thirty (30) days of the invoice date." />
      </Section>

      <Section id="negotiation" title="PriceChart · NegotiationThread · SignatureStamp">
        <PriceChart history={EX_HISTORY} plan={EX_PLAN} height={240} />
        <NegotiationThread history={EX_HISTORY.slice(0, 5)} customer="Lumen Mobility" />
        <Row><SignatureStamp envelope="env-d83ab4717c" terms={{ price: 15100, payment_days: 40, term_months: 12 }} /></Row>
      </Section>

      <Section id="audit" title="AuditTimeline">
        <AuditTimeline events={EX_EVENTS} />
      </Section>
    </Stack>
  );
}
