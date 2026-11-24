import { Link } from "react-router-dom";
import { ExternalLink, PartyPopper } from "lucide-react";
import { Badge, Card, Company, EmptyState, KeyValue, PageHeader, RedlineDiff, ResultCount, ScoreMeter, Skeleton, Stack } from "@ui";
import { ago, api, InboxItem, money, titleCase } from "@lib/api";
import { useApi } from "@lib/hooks";
import { useAuth } from "@lib/auth";
import { DecisionPanel, ErrorState } from "./shared";

/** Oldest first (it has waited longest), then the bigger deal. */
const byUrgency = (a: InboxItem, b: InboxItem) => a.updated_at - b.updated_at || (b.terms?.price ?? 0) - (a.terms?.price ?? 0);

export default function Inbox({ onChange }: { onChange: () => void }) {
  const { can } = useAuth();
  const inbox = useApi(api.inbox, [], () => 3000);
  const decider = can("legal");
  if (inbox.error) return <ErrorState error={inbox.error} onRetry={inbox.reload} />;
  const items = [...(inbox.data ?? [])].sort(byUrgency);

  return (
    <Stack gap={20}>
      <PageHeader title={decider ? "Review queue" : "Waiting on Legal"}
        description={decider ? "Deals paused until you decide. Oldest first." : "Your deals paused for a Legal decision. You'll be notified when they move."}
        actions={inbox.data && <ResultCount shown={items.length} total={items.length} noun={items.length === 1 ? "deal waiting" : "deals waiting"} />} />
      {!inbox.data ? <Skeleton height={240} /> : items.length === 0 ? (
        <Card><EmptyState icon={<PartyPopper size={28} />} title="Nothing is waiting">
          A deal lands here when it hits a deal-breaker clause, a rejected redline, new legal terms, an unclear reply or the autonomy limit.
        </EmptyState></Card>
      ) : (
        <Card flush>
          <ul className="nx-worklist">
            {items.map((it, i) => (
              <li key={it.id}>
                <details className="nx-queue" open={i === 0}>
                  <summary className="nx-work">
                    <Company name={it.customer} sub={it.id} />
                    <div className="nx-work__why"><b>{titleCase(it.escalation.kind)}</b><span title={it.escalation.triggers[0]}>{it.escalation.triggers[0]}</span></div>
                    <div className="nx-work__end">
                      <span className="nx-num nx-secondary">{money(it.terms?.price)}</span>
                      <Badge tone="critical">Waiting {ago(it.updated_at).replace(" ago", "")}</Badge>
                    </div>
                  </summary>
                  <div className="nx-queue__body">
                    <Stack gap={16}>
                      <KeyValue items={[
                        ["Why it paused", <ul style={{ margin: 0, paddingLeft: "1.1em" }}>{it.escalation.triggers.map((t) => <li key={t}>{t}</li>)}</ul>],
                        ["Terms on the table", it.terms ? `${money(it.terms.price)}/yr · net ${it.terms.payment_days}` : "—"],
                        ["Escalation score", <div style={{ maxWidth: 220 }}><ScoreMeter score={it.escalation.score} /></div>],
                        ["Contract", <Link to={`/contracts/${it.id}`} className="nx-linkbtn"><ExternalLink size={13} />Open the full workspace</Link>],
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
                  </div>
                </details>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </Stack>
  );
}
