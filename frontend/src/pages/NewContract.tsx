import { FormEvent, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { FileUp, ScanSearch } from "lucide-react";
import { Badge, Button, Card, ChoiceGroup, Dropzone, Field, Grid, Input, PageHeader, Select, Stack, useToast } from "@ui";
import { api, ApiError, money, Sample, titleCase } from "@lib/api";
import { useApi } from "@lib/hooks";

const PRICE = { core: 120, pro: 240, suite: 480 } as const;
type Source = "sample" | "upload";

export default function NewContract() {
  const nav = useNavigate();
  const toast = useToast();
  const samples = useApi(api.samples, []);
  const [source, setSource] = useState<Source>("upload");
  const [sampleId, setSampleId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [form, setForm] = useState({ customer: "", segment: "smb", region: "india", product: "pro" as keyof typeof PRICE, seats: 50 });
  const [busy, setBusy] = useState(false);

  const sample: Sample | undefined = samples.data?.find((s) => s.id === sampleId);
  useEffect(() => {
    if (!sampleId && samples.data?.length) setSampleId(samples.data.find((s) => s.expert_should_escalate)?.id ?? samples.data[0].id);
  }, [samples.data, sampleId]);
  useEffect(() => {
    if (source === "sample" && sample) setForm({ customer: sample.customer, segment: sample.segment, region: sample.region, product: sample.product as keyof typeof PRICE, seats: sample.seats });
  }, [sample, source]);

  const set = <K extends keyof typeof form>(k: K, v: (typeof form)[K]) => setForm((f) => ({ ...f, [k]: v }));

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (source === "upload" && !file) return toast("Choose a contract file first.", "critical");
    const fd = new FormData();
    Object.entries(form).forEach(([k, v]) => fd.append(k, String(v)));
    if (source === "sample") fd.append("sample_id", sampleId); else fd.append("file", file!);
    setBusy(true);
    try {
      const s = await api.createContract(fd);
      try { sessionStorage.setItem(`nx-scenario-${s.id}`, JSON.stringify(sample?.scenario ?? null)); } catch { /* ignore */ }
      toast(`Analyzed ${s.clauses.length} clauses`, "good");
      nav(`/contracts/${s.id}`);
    } catch (err) {
      toast((err as ApiError).message, "critical");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit}>
      <Stack gap={20}>
        <PageHeader title="New contract" description="Nothing is sent to the customer until you start negotiating." />

        <Card title="1 · Contract" subtitle="PDF, DOCX or plain text">
          <Stack gap={16}>
            <ChoiceGroup<Source> label="Contract source" value={source} onChange={setSource} options={[
              { value: "sample", title: "Bundled sample", detail: "200 generated MSAs with expert labels" },
              { value: "upload", title: "Upload a file", detail: "Your own customer contract" },
            ]} />
            {source === "sample" ? (
              <Field label="Sample contract" htmlFor="sample" hint={sample && <>List {money(sample.list_price)}/yr · {sample.expert_should_escalate ? <Badge tone="critical" dot>expert says escalate</Badge> : <Badge tone="good" dot>expert says clean</Badge>}</>}>
                <Select id="sample" value={sampleId} onChange={(e) => setSampleId(e.target.value)}
                  options={(samples.data ?? []).map((s) => ({ value: s.id, label: `${s.id} · ${s.customer} · ${titleCase(s.segment)} ${s.region.toUpperCase()} · ${s.product} ×${s.seats}${s.expert_should_escalate ? "  [risky]" : ""}` }))} />
              </Field>
            ) : (
              <Dropzone file={file} onFile={setFile} />
            )}
          </Stack>
        </Card>

        <Card title="2 · Deal context" subtitle="Used by the Memory and Pricing agents to find similar past deals">
          <Grid min={180}>
            <Field label="Customer" htmlFor="customer"><Input id="customer" required value={form.customer} onChange={(e) => set("customer", e.target.value)} placeholder="Company name" /></Field>
            <Field label="Segment" htmlFor="segment"><Select id="segment" value={form.segment} onChange={(e) => set("segment", e.target.value)} options={["startup", "smb", "mid_market", "enterprise"].map((v) => ({ value: v, label: titleCase(v) }))} /></Field>
            <Field label="Region" htmlFor="region"><Select id="region" value={form.region} onChange={(e) => set("region", e.target.value)} options={["india", "us", "eu", "apac"].map((v) => ({ value: v, label: v.toUpperCase() }))} /></Field>
            <Field label="Product" htmlFor="product"><Select id="product" value={form.product} onChange={(e) => set("product", e.target.value as keyof typeof PRICE)} options={Object.entries(PRICE).map(([v, p]) => ({ value: v, label: `${titleCase(v)} · $${p}/seat` }))} /></Field>
            <Field label="Seats" htmlFor="seats" hint={`List price ${money(PRICE[form.product] * form.seats)}/yr`}><Input id="seats" type="number" min={1} value={form.seats} onChange={(e) => set("seats", Number(e.target.value))} /></Field>
          </Grid>
        </Card>

        <div className="nx-row nx-row--end">
          <Button type="submit" variant="primary" size="lg" loading={busy} icon={source === "upload" ? <FileUp size={18} /> : <ScanSearch size={18} />}>Analyze contract</Button>
        </div>
      </Stack>
    </form>
  );
}
