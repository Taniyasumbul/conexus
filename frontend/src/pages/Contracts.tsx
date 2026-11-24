import { useMemo } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Search } from "lucide-react";
import {
  Button, Card, EmptyState, FilterChip, Input, PageHeader, ResultCount, Skeleton, SortSelect, Stack, Table, Tabs, Toolbar,
} from "@ui";
import { api, ContractSummary, Status, titleCase } from "@lib/api";
import { useApi } from "@lib/hooks";
import { useAuth } from "@lib/auth";
import { contractColumns } from "./Overview";
import { ErrorState } from "./shared";

type View = "all" | Status;
type Sort = "updated" | "value" | "customer" | "risk";
const VIEWS: { value: View; label: string }[] = [
  { value: "all", label: "All" },
  { value: "awaiting_human", label: "Needs review" },
  { value: "analyzed", label: "Ready to negotiate" },
  { value: "awaiting_reply", label: "Negotiating" },
  { value: "signed", label: "Sent to sign" },
  { value: "closed", label: "Closed" },
];
const SEGMENTS = ["startup", "smb", "mid_market", "enterprise"];
const SORTS: { value: Sort; label: string }[] = [
  { value: "updated", label: "Recently updated" },
  { value: "value", label: "Highest value" },
  { value: "risk", label: "Most open risks" },
  { value: "customer", label: "Customer A–Z" },
];
const value = (r: ContractSummary) => r.price ?? r.list_price;
const SORT_FN: Record<Sort, (a: ContractSummary, b: ContractSummary) => number> = {
  updated: (a, b) => b.updated_at - a.updated_at,
  value: (a, b) => value(b) - value(a),
  risk: (a, b) => b.risky_clauses - a.risky_clauses || b.updated_at - a.updated_at,
  customer: (a, b) => a.customer.localeCompare(b.customer),
};

export default function Contracts() {
  const nav = useNavigate();
  const { can } = useAuth();
  const list = useApi(api.contracts, [], () => 5000);
  // the view lives in the URL, so a filtered list can be bookmarked or shared
  const [params, setParams] = useSearchParams();
  const view = (params.get("view") as View) || "all";
  const sort = (params.get("sort") as Sort) || "updated";
  const q = params.get("q") ?? "";
  const risky = params.get("risk") === "open";
  const segs = (params.get("segment") ?? "").split(",").filter(Boolean);

  const set = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(params);
    Object.entries(patch).forEach(([k, v]) => (v ? next.set(k, v) : next.delete(k)));
    setParams(next, { replace: true });
  };
  const toggleSeg = (s: string) => set({ segment: (segs.includes(s) ? segs.filter((x) => x !== s) : [...segs, s]).join(",") || null });
  const filtered = Boolean(q || risky || segs.length);

  const all = list.data ?? [];
  const count = (v: View) => (v === "all" ? all.length : all.filter((r) => r.status === v).length);
  const rows = useMemo(() => all
    .filter((r) => view === "all" || r.status === view)
    .filter((r) => !risky || r.risky_clauses > 0)
    .filter((r) => !segs.length || segs.includes(r.segment))
    .filter((r) => (r.customer + " " + r.id).toLowerCase().includes(q.toLowerCase()))
    .sort(SORT_FN[sort] ?? SORT_FN.updated), [all, view, risky, segs.join(), q, sort]);
  const inView = view === "all" ? all.length : count(view);

  if (list.error) return <ErrorState error={list.error} onRetry={list.reload} />;
  return (
    <Stack gap={20}>
      <PageHeader title="Contracts" description="Every contract CoNexus has read, and where each one stands." />
      <Card flush>
        <div className="nx-viewtabs">
          <Tabs<View> value={view} onChange={(v) => set({ view: v === "all" ? null : v })}
            tabs={VIEWS.map((v) => ({ value: v.value, label: v.label, count: list.data ? count(v.value) : undefined }))} />
        </div>
        <Toolbar end={<>
          <ResultCount shown={rows.length} total={inView} onClear={filtered ? () => set({ q: null, risk: null, segment: null }) : undefined} />
          <SortSelect<Sort> id="contract-sort" value={sort} onChange={(v) => set({ sort: v === "updated" ? null : v })} options={SORTS} />
        </>}>
          <div className="nx-search">
            <Search size={15} aria-hidden />
            <Input id="contract-search" aria-label="Search customer or contract ID" placeholder="Search customer or ID" value={q}
              onChange={(e) => set({ q: e.target.value || null })} />
          </div>
          <FilterChip selected={risky} onToggle={() => set({ risk: risky ? null : "open" })}>Open risks</FilterChip>
          {SEGMENTS.map((s) => <FilterChip key={s} selected={segs.includes(s)} onToggle={() => toggleSeg(s)}>{titleCase(s)}</FilterChip>)}
        </Toolbar>
        {list.data ? (
          <Table cards caption="Contracts" rows={rows} rowKey={(r) => r.id} onRowClick={(r) => nav(`/contracts/${r.id}`)} columns={contractColumns(can("legal"))}
            empty={all.length
              ? <EmptyState title="No contracts match" action={filtered ? <Button size="sm" onClick={() => set({ q: null, risk: null, segment: null })}>Clear filters</Button> : undefined}>
                  {filtered ? "Try fewer filters or another search term." : "Nothing is in this stage right now."}
                </EmptyState>
              : <EmptyState title="No contracts yet" action={<Button variant="primary" onClick={() => nav("/new")}>Create contract</Button>}>
                  Upload a customer contract to get a risk review and an opening offer.
                </EmptyState>} />
        ) : <div style={{ padding: 20 }}><Skeleton height={240} /></div>}
      </Card>
    </Stack>
  );
}
