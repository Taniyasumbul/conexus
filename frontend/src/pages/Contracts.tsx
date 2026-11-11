import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { FilePlus2, Search } from "lucide-react";
import { Button, Card, EmptyState, Input, PageHeader, Row, Segmented, Skeleton, Stack, Table } from "@ui";
import { api, Status } from "@lib/api";
import { useApi } from "@lib/hooks";
import { contractColumns } from "./Overview";
import { ErrorState } from "./shared";

type Filter = "all" | Status;

export default function Contracts() {
  const nav = useNavigate();
  const list = useApi(api.contracts, [], () => 4000);
  const [q, setQ] = useState("");
  const [f, setF] = useState<Filter>("all");
  const rows = useMemo(() => (list.data ?? []).filter((r) =>
    (f === "all" || r.status === f) && (r.customer + r.id).toLowerCase().includes(q.toLowerCase())), [list.data, q, f]);
  const count = (s: Status) => list.data?.filter((r) => r.status === s).length ?? 0;

  if (list.error) return <ErrorState error={list.error} onRetry={list.reload} />;
  return (
    <Stack gap={20}>
      <PageHeader eyebrow="Workspace" title="Contracts" description="Every contract the agents have read, with its current stage."
        actions={<Button variant="primary" icon={<FilePlus2 size={16} />} onClick={() => nav("/new")}>New contract</Button>} />
      <Row justify="between">
        <Segmented<Filter> label="Filter by stage" value={f} onChange={setF} options={[
          { value: "all", label: `All ${list.data?.length ?? ""}` },
          { value: "awaiting_human", label: `Needs human ${count("awaiting_human")}` },
          { value: "awaiting_reply", label: `Negotiating ${count("awaiting_reply")}` },
          { value: "signed", label: `Signed ${count("signed")}` },
          { value: "closed", label: `Closed ${count("closed")}` },
        ]} />
        <div style={{ position: "relative", width: "min(320px, 100%)" }}>
          <Search size={15} style={{ position: "absolute", left: 10, top: 10, color: "var(--fg-3)" }} />
          <Input id="contract-search" aria-label="Search contracts" placeholder="Search customer or ID" value={q} onChange={(e) => setQ(e.target.value)} style={{ paddingLeft: 32 }} />
        </div>
      </Row>
      <Card flush>
        {list.data ? <Table rows={rows} rowKey={(r) => r.id} onRowClick={(r) => nav(`/contracts/${r.id}`)} columns={contractColumns()}
          empty={<EmptyState title={list.data.length ? "No contracts match" : "No contracts yet"}>{list.data.length ? "Try another stage or search term." : "Create one from New contract."}</EmptyState>} />
          : <div style={{ padding: 20 }}><Skeleton height={240} /></div>}
      </Card>
    </Stack>
  );
}
