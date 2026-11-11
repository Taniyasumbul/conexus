import { useState } from "react";
import { Link } from "react-router-dom";
import { RefreshCw, ShieldCheck, ShieldX } from "lucide-react";
import { Alert, AuditTimeline, Button, Card, EmptyState, HashChip, PageHeader, Row, Segmented, Skeleton, Stack } from "@ui";
import { api, when } from "@lib/api";
import { useApi } from "@lib/hooks";
import { ErrorState } from "./shared";

export default function Ledger() {
  const verify = useApi(api.verify, []);
  const events = useApi(() => api.auditAll(300), [], () => 5000);
  const outbox = useApi(api.outbox, []);
  const [view, setView] = useState<"events" | "notifications">("events");

  if (verify.error) return <ErrorState error={verify.error} onRetry={verify.reload} />;
  const v = verify.data;
  return (
    <Stack gap={20}>
      <PageHeader eyebrow="RO4 · Audit & explainability" title="Audit ledger"
        description="Every agent and reviewer decision is chained to the one before it with SHA-256. Editing, deleting or reordering any entry breaks the chain, and verification finds it."
        actions={<Button icon={<RefreshCw size={15} />} onClick={() => { verify.reload(); events.reload(); }}>Verify again</Button>} />
      {!v ? <Skeleton height={80} /> : (
        <Alert tone={v.ok ? "good" : "critical"} title={v.ok ? "Chain intact" : "Chain broken"}>
          <Stack gap={8}>
            <span>{v.message} · {v.events.toLocaleString()} events</span>
            <Row gap={8}>{v.ok ? <ShieldCheck size={16} /> : <ShieldX size={16} />}<span>Head hash</span><HashChip hash={v.head} chars={20} /></Row>
            <span className="nx-muted" style={{ fontSize: "var(--text-xs)" }}>Anchor the head hash outside this system (e-mail it to compliance daily, commit it to git) to make the whole history tamper-evident.</span>
          </Stack>
        </Alert>
      )}
      <Segmented label="Ledger view" value={view} onChange={setView} options={[
        { value: "events", label: "Decision events" }, { value: "notifications", label: `Reviewer notifications ${outbox.data?.length ?? ""}` },
      ]} />
      {view === "events" ? (
        <Card title="Latest events" subtitle="Newest first, across all contracts">
          {events.data?.length ? (
            <Stack gap={0}>
              {groupByContract(events.data).map(([cid, evs]) => (
                <div key={`${cid}-${evs[0].seq}`} style={{ paddingBottom: 8 }}>
                  <div className="nx-eyebrow" style={{ marginBottom: 8 }}>{cid ? <Link to={`/contracts/${cid}`}>{cid}</Link> : "system"}</div>
                  <AuditTimeline events={evs} />
                </div>
              ))}
            </Stack>
          ) : <EmptyState title="The ledger is empty">Analyze a contract to see the first entries.</EmptyState>}
        </Card>
      ) : (
        <Card title="Messages sent to reviewers" subtitle="Slack when SLACK_WEBHOOK_URL is set; recorded here either way">
          {outbox.data?.length ? (
            <Stack gap={12}>{[...outbox.data].reverse().map((m, i) => (
              <details key={i} className="nx-clause">
                <summary className="nx-clause__head"><span className="nx-clause__title">{m.subject}</span><span className="nx-muted">{when(m.ts)}</span></summary>
                <div className="nx-clause__body"><pre className="nx-mono" style={{ whiteSpace: "pre-wrap", margin: 0, fontSize: "var(--text-sm)" }}>{m.body}</pre></div>
              </details>
            ))}</Stack>
          ) : <EmptyState title="No escalations sent yet" />}
        </Card>
      )}
    </Stack>
  );
}

function groupByContract<T extends { contract_id: string | null }>(evs: T[]): [string | null, T[]][] {
  const out: [string | null, T[]][] = [];
  for (const e of evs) {
    const last = out[out.length - 1];
    if (last && last[0] === e.contract_id) last[1].push(e); else out.push([e.contract_id, [e]]);
  }
  return out;
}
