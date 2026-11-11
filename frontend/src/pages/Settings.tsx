import { FormEvent, useEffect, useMemo, useState } from "react";
import { History, KeyRound, ShieldAlert, SlidersHorizontal, UserPlus, Users } from "lucide-react";
import {
  Alert, Avatar, Button, Card, Dialog, EmptyState, Field, Grid, Input, PageHeader, Range, Row, SaveBar, Segmented,
  Select, Skeleton, Stack, Switch, Table, Tabs, ThresholdChart, useToast,
} from "@ui";
import { ago, api, ApiError, money, Policy, PolicyField, Role, User, when } from "@lib/api";
import { useApi } from "@lib/hooks";
import { useAuth } from "@lib/auth";
import { ErrorState } from "./shared";

type Tab = "escalation" | "pricing" | "team" | "history";
type Section = "escalation" | "pricing";
type Draft = Record<Section, Record<string, unknown>>;

const LABELS: Record<string, string> = {
  clause_threshold: "Clause risk threshold", combine: "How rules and the model combine", ml_weight: "Model weight (weighted mode)",
  max_rounds: "Maximum negotiation rounds", autonomy_value_limit: "Autonomy limit (annual value)",
  escalate_on_new_legal_terms: "Pause on new legal terms", escalate_on_rejected_redline: "Pause on rejected critical redline",
  escalate_failed_high_value: "Hand failed deals to a person above",
  max_discount: "Maximum discount", target_payment_days: "Opening payment terms", max_payment_days: "Longest payment terms",
  cost_of_capital: "Cost of capital", boulware_beta: "Concession curve", anchor_markup_over_wtp: "Opening ask above budget estimate",
  concession_limit_of_wtp: "Concession limit", memory_k: "Similar deals retrieved",
};
const PERCENT = new Set(["clause_threshold", "ml_weight", "max_discount", "cost_of_capital", "anchor_markup_over_wtp", "concession_limit_of_wtp"]);
const MONEY = new Set(["autonomy_value_limit", "escalate_failed_high_value"]);
const DAYS = new Set(["target_payment_days", "max_payment_days"]);

function fmt(f: PolicyField, v: unknown): string {
  if (typeof v === "boolean") return v ? "On" : "Off";
  if (MONEY.has(f.name)) return money(v as number);
  if (f.name === "clause_threshold") return (v as number).toFixed(2);
  if (PERCENT.has(f.name)) return `${Math.round((v as number) * 100)}%`;
  if (DAYS.has(f.name)) return `net ${v}`;
  return String(v);
}

export default function Settings() {
  const { can } = useAuth();
  const [tab, setTab] = useState<Tab>("escalation");
  return (
    <Stack gap={20}>
      <PageHeader title="Settings" description="The agents' rules and the people who can change them." />
      <Tabs<Tab> value={tab} onChange={setTab} tabs={[
        { value: "escalation", label: "Escalation policy", icon: <ShieldAlert size={15} /> },
        { value: "pricing", label: "Pricing policy", icon: <SlidersHorizontal size={15} /> },
        ...(can("admin") ? [{ value: "team" as Tab, label: "Team", icon: <Users size={15} /> }] : []),
        { value: "history", label: "Change history", icon: <History size={15} /> },
      ]} />
      {(tab === "escalation" || tab === "pricing") && <PolicyEditor section={tab} />}
      {tab === "team" && can("admin") && <Team />}
      {tab === "history" && <PolicyHistory />}
    </Stack>
  );
}

/* ------------------------------------------------------------------ policy */
function PolicyEditor({ section }: { section: Section }) {
  const { can } = useAuth();
  const toast = useToast();
  const pol = useApi(api.policy, []);
  const evals = useApi(api.evals, []);
  const [draft, setDraft] = useState<Draft>({ escalation: {}, pricing: {} });
  const [saving, setSaving] = useState(false);
  const editable = can("admin");

  const dirty = useMemo(() => {
    if (!pol.data) return [] as string[];
    return (["escalation", "pricing"] as Section[]).flatMap((sec) =>
      Object.entries(draft[sec]).filter(([k, v]) => pol.data![sec][k] !== v).map(([k]) => `${sec}.${k}`));
  }, [draft, pol.data]);

  if (pol.error) return <ErrorState error={pol.error} onRetry={pol.reload} />;
  if (!pol.data) return <Skeleton height={420} />;
  const p: Policy = pol.data;
  const value = (sec: Section, k: string) => (k in draft[sec] ? draft[sec][k] : p[sec][k]);
  const set = (sec: Section, k: string, v: unknown) => setDraft((d) => ({ ...d, [sec]: { ...d[sec], [k]: v } }));

  async function save() {
    setSaving(true);
    try {
      const pick = (sec: Section) => Object.fromEntries(Object.entries(draft[sec]).filter(([k, v]) => p[sec][k] !== v));
      const res = await api.savePolicy({ escalation: pick("escalation"), pricing: pick("pricing") });
      pol.setData(res);
      setDraft({ escalation: {}, pricing: {} });
      toast(`Saved ${Object.keys(res.changed ?? {}).length} change(s). The agents use them from now on.`, "good");
    } catch (e) { toast((e as ApiError).message, "critical"); } finally { setSaving(false); }
  }

  const sweep = evals.data?.eval_escalation?.hybrid_threshold_sweep_scores_only;
  const fields = p.schema[section];

  return (
    <Stack gap={16}>
      {!editable && <Alert tone="info" title="Read only">Only admins can change the policy. You can see exactly what the agents are allowed to do.</Alert>}
      <div className={section === "escalation" && sweep ? "nx-split" : undefined}>
        <Card title={section === "escalation" ? "When must a person step in?" : "How the agents negotiate price"}
          subtitle={section === "escalation" ? "Applies to new analyses and to every negotiation step from now on" : "Applies to negotiations started after you save"}>
          <div>
            {fields.map((f) => <SettingRow key={f.name} f={f} v={value(section, f.name)} dirty={dirty.includes(`${section}.${f.name}`)}
              disabled={!editable || (f.name === "ml_weight" && value("escalation", "combine") !== "weighted")}
              onChange={(v) => set(section, f.name, v)} />)}
          </div>
        </Card>
        {section === "escalation" && sweep && (
          <Stack gap={16}>
            <Card title="What the threshold trades off" subtitle="Precision and recall of the risk score on held-out clause wording (synthetic benchmark)">
              <ThresholdChart sweep={sweep} threshold={Number(value("escalation", "clause_threshold"))} height={220} />
            </Card>
            <Alert tone="info" title="Reading the chart">Lower the threshold and more clauses reach a person (higher recall, more reviews). Raise it and the agents act alone more often (higher precision, more missed risk). Deal-breaker rules escalate regardless of the threshold.</Alert>
          </Stack>
        )}
      </div>
      {dirty.length > 0 && (
        <SaveBar actions={<>
          <Button variant="ghost" onClick={() => setDraft({ escalation: {}, pricing: {} })}>Discard</Button>
          <Button variant="primary" loading={saving} onClick={save}>Save {dirty.length} change{dirty.length > 1 ? "s" : ""}</Button>
        </>}>{dirty.length} unsaved change{dirty.length > 1 ? "s" : ""} to the agents' policy</SaveBar>
      )}
    </Stack>
  );
}

function SettingRow({ f, v, dirty, disabled, onChange }: { f: PolicyField; v: unknown; dirty: boolean; disabled: boolean; onChange: (v: unknown) => void }) {
  const id = `pol-${f.name}`;
  let control;
  if (f.type === "bool") control = <Switch id={id} checked={Boolean(v)} disabled={disabled} onChange={onChange} label={v ? "On" : "Off"} />;
  else if (f.type === "choice") control = (
    <Segmented label={LABELS[f.name] ?? f.name} value={String(v)} onChange={(x) => !disabled && onChange(x)}
      options={(f.choices ?? []).map((c) => ({ value: c, label: c === "max" ? "Either signal" : c === "weighted" ? "Weighted" : c }))} />
  );
  else if (MONEY.has(f.name)) control = (
    <Row gap={8}><span className="nx-muted">$</span>
      <Input id={id} type="number" min={f.ge ?? 0} step={1000} disabled={disabled} value={Number(v)} style={{ maxWidth: 200 }}
        onChange={(e) => onChange(Number(e.target.value))} /></Row>
  );
  else control = (
    <Range id={id} value={Number(v)} min={f.ge ?? 0} max={f.le ?? 100} step={f.type === "int" ? 1 : ((f.le ?? 1) - (f.ge ?? 0)) / 100}
      format={(x) => fmt(f, f.type === "int" ? Math.round(x) : Math.round(x * 100) / 100)}
      onChange={(x) => !disabled && onChange(f.type === "int" ? Math.round(x) : Math.round(x * 100) / 100)} />
  );
  return (
    <div className="nx-setting" data-dirty={dirty}>
      <div>
        <label className="nx-setting__label" htmlFor={id}>{LABELS[f.name] ?? f.name}</label>
        <div className="nx-setting__desc">{f.description}</div>
        <div className="nx-setting__meta">{f.name} · default {fmt(f, f.default)}</div>
      </div>
      <div style={{ opacity: disabled ? 0.6 : 1, pointerEvents: disabled ? "none" : undefined }}>{control}</div>
    </div>
  );
}

/* ------------------------------------------------------------------ history */
function PolicyHistory() {
  const h = useApi(api.policyHistory, []);
  if (h.error) return <ErrorState error={h.error} onRetry={h.reload} />;
  if (!h.data) return <Skeleton height={200} />;
  if (!h.data.length) return <Card><EmptyState icon={<History size={28} />} title="No policy changes yet">The agents are running on the defaults. Changes appear here with who made them.</EmptyState></Card>;
  return (
    <Card title="Policy changes" subtitle="From the audit ledger, newest first" flush>
      <Table rows={h.data} rowKey={(e) => String(e.seq)} columns={[
        { key: "w", header: "When", render: (e) => <span title={when(e.ts)}>{ago(e.ts)}</span> },
        { key: "by", header: "Changed by", render: (e) => <Row gap={8}><Avatar name={e.agent.replace("human:", "")} />{e.agent.replace("human:", "")}</Row> },
        { key: "what", header: "Change", render: (e) => {
          const d = e.data as { before: Record<string, unknown>; after: Record<string, unknown> };
          return <Stack gap={4}>{Object.keys(d.after).map((k) => (
            <span key={k}><code>{k.split(".")[1]}</code> <span className="nx-muted">{String(d.before[k])}</span> → <b>{String(d.after[k])}</b></span>
          ))}</Stack>;
        } },
      ]} />
    </Card>
  );
}

/* ------------------------------------------------------------------ team */
const ROLE_INFO: Record<Role, string> = { sales: "Creates and negotiates contracts", legal: "Also approves escalations and labels clauses", admin: "Also sets policy and manages the team" };

function Team() {
  const { user: me } = useAuth();
  const toast = useToast();
  const users = useApi(api.users, []);
  const [form, setForm] = useState({ name: "", email: "", role: "sales" as Role, password: "" });
  const [busy, setBusy] = useState(false);
  const [resetFor, setResetFor] = useState<User | null>(null);
  const [newPw, setNewPw] = useState("");
  useEffect(() => { if (!resetFor) setNewPw(""); }, [resetFor]);

  async function add(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await api.createUser(form);
      toast(`${form.email} can now sign in as ${form.role}`, "good");
      setForm({ name: "", email: "", role: "sales", password: "" });
      users.reload();
    } catch (err) { toast((err as ApiError).message, "critical"); } finally { setBusy(false); }
  }
  async function patch(u: User, b: Partial<{ role: Role; active: boolean; password: string }>, ok: string) {
    try { await api.updateUser(u.id, b); toast(ok, "good"); users.reload(); } catch (err) { toast((err as ApiError).message, "critical"); }
  }

  if (users.error) return <ErrorState error={users.error} onRetry={users.reload} />;
  return (
    <Stack gap={16}>
      <Card title="People" subtitle="Who can sign in, and what they may do" flush>
        {!users.data ? <div style={{ padding: 20 }}><Skeleton height={140} /></div> : (
          <Table rows={users.data} rowKey={(u) => String(u.id)} columns={[
            { key: "u", header: "Person", render: (u) => <Row gap={10}><Avatar name={u.name} /><Stack gap={0}><b>{u.name}{u.id === me.id && <span className="nx-muted"> (you)</span>}</b><span className="nx-muted" style={{ fontSize: "var(--text-xs)" }}>{u.email}</span></Stack></Row> },
            { key: "r", header: "Role", render: (u) => (
              <Select aria-label={`Role for ${u.email}`} value={u.role} disabled={u.id === me.id} style={{ width: 130 }}
                onChange={(e) => patch(u, { role: e.target.value as Role }, `${u.email} is now ${e.target.value}`)}
                options={(["sales", "legal", "admin"] as Role[]).map((r) => ({ value: r, label: r[0].toUpperCase() + r.slice(1) }))} />
            ) },
            { key: "a", header: "Access", render: (u) => (
              <Switch checked={!!u.active} disabled={u.id === me.id} label={u.active ? "Active" : "Disabled"}
                onChange={(v) => patch(u, { active: v }, v ? `${u.email} re-enabled` : `${u.email} signed out and disabled`)} />
            ) },
            { key: "c", header: "Added", render: (u) => <span className="nx-muted">{u.created_at ? ago(u.created_at) : "—"}</span> },
            { key: "p", header: "", render: (u) => <Button size="sm" variant="ghost" icon={<KeyRound size={14} />} onClick={() => setResetFor(u)}>Set password</Button> },
          ]} />
        )}
      </Card>

      <Card title="Add a person" subtitle="Share the temporary password privately; they can be given a new one any time">
        <form onSubmit={add}>
          <Stack gap={16}>
            <Grid min={200}>
              <Field label="Full name" htmlFor="nu-name"><Input id="nu-name" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
              <Field label="Work e-mail" htmlFor="nu-email"><Input id="nu-email" type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></Field>
              <Field label="Temporary password" htmlFor="nu-pw" hint="At least 10 characters"><Input id="nu-pw" type="text" required minLength={10} autoComplete="off" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></Field>
            </Grid>
            <Field label="Role" htmlFor="nu-role" hint={ROLE_INFO[form.role]}>
              <Segmented<Role> label="Role" value={form.role} onChange={(r) => setForm({ ...form, role: r })}
                options={[{ value: "sales", label: "Sales" }, { value: "legal", label: "Legal" }, { value: "admin", label: "Admin" }]} />
            </Field>
            <Row justify="end"><Button type="submit" variant="primary" icon={<UserPlus size={16} />} loading={busy}>Add person</Button></Row>
          </Stack>
        </form>
      </Card>

      <Dialog open={!!resetFor} onClose={() => setResetFor(null)} title={`New password for ${resetFor?.name ?? ""}`}
        footer={<>
          <Button variant="ghost" onClick={() => setResetFor(null)}>Cancel</Button>
          <Button variant="primary" disabled={newPw.length < 10} onClick={async () => { if (resetFor) { await patch(resetFor, { password: newPw }, "Password changed; their other sessions were signed out"); setResetFor(null); } }}>Set password</Button>
        </>}>
        <Field label="New password" htmlFor="reset-pw" hint="At least 10 characters. Their existing sessions end."><Input id="reset-pw" type="text" autoComplete="off" value={newPw} onChange={(e) => setNewPw(e.target.value)} /></Field>
      </Dialog>
    </Stack>
  );
}
