import { useNavigate } from "react-router-dom";
import { ExternalLink, PartyPopper } from "lucide-react";
import { Badge, Button, Card, EmptyState, KeyValue, PageHeader, RedlineDiff, Row, ScoreMeter, Skeleton, Stack } from "@ui";
import { ago, api, money, titleCase } from "@lib/api";
import { useApi } from "@lib/hooks";
import { DecisionPanel, ErrorState, EscalationSummary } from "./shared";

export default function Inbox({ onChange }: { onChange: () => void }) {
  const nav = useNavigate();
  const inbox = useApi(api.inbox, [], () => 3000);
  if (inbox.error) return <ErrorState error={inbox.error} onRetry={inbox.reload} />;
  return (
    <Stack gap={20}>
      <PageHeader eyebrow="Human in the loop" title="Escalation inbox"
        description="Decisions the agents are not allowed to take alone. Each one is paused until you approve or reject it, and your decision is written to the audit ledger." />
      {!inbox.data ? <Skeleton height={240} /> : inbox.data.length === 0 ? (
        <Card><EmptyState icon={<PartyPopper size={28} />} title="Nothing needs you right now">When a contract hits a deal-breaker clause, a rejected redline, new legal terms or the autonomy limit, it lands here.</EmptyState></Card>
      ) : inbox.data.map((it) => (
        <Card key={it.id} tone="critical" title={<Row gap={10}>{it.customer}<span className="nx-mono nx-muted" style={{ fontSize: "var(--text-xs)" }}>{it.id}</span></Row>}
          subtitle={`Escalated ${ago(it.updated_at)}`}
          actions={<Button size="sm" variant="ghost" icon={<ExternalLink size={14} />} onClick={() => nav(`/contracts/${it.id}`)}>Open contract</Button>}>
          <Stack gap={16}>
            <EscalationSummary escalation={it.escalation} />
            <KeyValue items={[
              ["Terms on the table", it.terms ? `${money(it.terms.price)}/yr · net ${it.terms.payment_days}` : "—"],
              ["Escalation score", <div style={{ maxWidth: 220 }}><ScoreMeter score={it.escalation.score} /></div>],
            ]} />
            {it.flagged.map((f) => (
              <div key={f.clause_id} className="nx-clause" data-level={f.level}>
                <div className="nx-clause__head" style={{ cursor: "default" }}>
                  <span className="nx-clause__ref">§ {f.clause_id.slice(1)}</span>
                  <span className="nx-clause__title">{titleCase(f.clause_type)}</span>
                  <Badge tone="critical" dot>{f.reasons[0] ?? "High risk"}</Badge>
                </div>
                <div className="nx-clause__body">
                  <p className="nx-clause__text">{it.clauses[f.clause_id]}</p>
                  {f.redline && <RedlineDiff original={it.clauses[f.clause_id] ?? ""} proposed={f.redline} label="Fallback position you could insist on" />}
                </div>
              </div>
            ))}
            <DecisionPanel id={it.id} escalation={it.escalation} onDone={() => { inbox.reload(); onChange(); }} />
          </Stack>
        </Card>
      ))}
    </Stack>
  );
}
