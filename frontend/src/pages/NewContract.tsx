import { FormEvent, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, ArrowRight, ScanSearch } from "lucide-react";
import {
  Alert, Badge, Breadcrumbs, Button, Card, ChoiceGroup, Dropzone, Field, Grid, Input, KeyValue, PageHeader, Row, Select, Stack, Steps, useToast,
} from "@ui";
import { api, ApiError, money, Sample, titleCase } from "@lib/api";
import { useApi } from "@lib/hooks";

const PRICE = { core: 120, pro: 240, suite: 480 } as const;
const STEPS = ["Contract", "Business context", "Review & analyze"];
type Source = "upload" | "sample";

export default function NewContract() {
  const nav = useNavigate();
  const toast = useToast();
  const samples = useApi(api.samples, []);
  const [step, setStep] = useState(0);
  const [source, setSource] = useState<Source>("upload");
  const [sampleId, setSampleId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [form, setForm] = useState({ customer: "", segment: "smb", region: "india", product: "pro" as keyof typeof PRICE, seats: 50 });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  const sample: Sample | undefined = samples.data?.find((s) => s.id === sampleId);
  useEffect(() => {
    if (!sampleId && samples.data?.length) setSampleId(samples.data.find((s) => s.expert_should_escalate)?.id ?? samples.data[0].id);
  }, [samples.data, sampleId]);
  useEffect(() => {
    if (source === "sample" && sample) setForm({ customer: sample.customer, segment: sample.segment, region: sample.region, product: sample.product as keyof typeof PRICE, seats: sample.seats });
  }, [sample, source]);

  const set = <K extends keyof typeof form>(k: K, v: (typeof form)[K]) => { setForm((f) => ({ ...f, [k]: v })); setErrors((e) => ({ ...e, [k]: "" })); };
  const listPrice = PRICE[form.product] * form.seats;

  function validate(i: number): boolean {
    const e: Record<string, string> = {};
    if (i === 0 && source === "upload" && !file) e.file = "Choose the customer's contract file.";
    if (i === 0 && source === "sample" && !sampleId) e.file = "Choose a sample contract.";
    if (i === 1 && !form.customer.trim()) e.customer = "Enter the customer's company name.";
    if (i === 1 && (!Number.isFinite(form.seats) || form.seats < 1)) e.seats = "Seats must be at least 1.";
    setErrors(e);
    return Object.keys(e).length === 0;
  }
  const next = () => { if (validate(step)) setStep(step + 1); };

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (step < 2) return next();
    if (!validate(0) || !validate(1)) return;
    const fd = new FormData();
    Object.entries(form).forEach(([k, v]) => fd.append(k, String(v)));
    if (source === "sample") fd.append("sample_id", sampleId); else fd.append("file", file!);
    setBusy(true);
    setFailure(null);
    try {
      const s = await api.createContract(fd);
      try {
        sessionStorage.setItem(`nx-scenario-${s.id}`, JSON.stringify(source === "sample" ? sample?.scenario ?? null : null));
        sessionStorage.setItem(`nx-fresh-${s.id}`, "1");  // the contract page shows the analysis summary once
      } catch { /* storage unavailable: the page still works */ }
      toast(`Analyzed ${s.clauses.length} clauses`, "good");
      nav(`/contracts/${s.id}`);
    } catch (err) {
      // keep everything the user entered; say what went wrong and where to fix it
      setFailure((err as ApiError).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} noValidate>
      <Stack gap={20}>
        <Breadcrumbs items={[{ label: "Contracts", to: "/contracts" }, { label: "Create contract" }]} />
        <PageHeader title="Create contract" description="CoNexus reads the contract, flags clauses for Legal and prepares an opening offer. Nothing is sent to the customer until you start negotiating." />
        <Steps steps={STEPS} current={step} onPick={setStep} />

        {step === 0 && (
          <Card title="Contract" subtitle="The customer's paper: PDF, Word (.docx) or plain text, up to 10 MB">
            <Stack gap={16}>
              <ChoiceGroup<Source> label="Contract source" value={source} onChange={(v) => { setSource(v); setErrors({}); }} options={[
                { value: "upload", title: "Upload the customer's contract", detail: "Stored in your workspace only; never sent to the customer" },
                { value: "sample", title: <>Use a sample <Badge tone="warning">Demo</Badge></>, detail: "Generated contracts for training and demos, not real customers" },
              ]} />
              {source === "upload" ? (
                <Field label="Contract file" htmlFor="dropzone" error={errors.file}>
                  <Dropzone file={file} onFile={(f) => { setFile(f); setErrors({}); }} />
                </Field>
              ) : (
                <Field label="Sample contract" htmlFor="sample" error={errors.file}
                  hint={sample && <>List {money(sample.list_price)}/yr · {sample.expert_should_escalate ? <Badge tone="critical" dot>Expert label: needs Legal</Badge> : <Badge tone="good" dot>Expert label: clean</Badge>}</>}>
                  <Select id="sample" value={sampleId} onChange={(e) => setSampleId(e.target.value)}
                    options={(samples.data ?? []).map((s) => ({ value: s.id, label: `${s.id} · ${s.customer} · ${titleCase(s.segment)} · ${s.product} ×${s.seats}${s.expert_should_escalate ? " · needs Legal" : ""}` }))} />
                </Field>
              )}
            </Stack>
          </Card>
        )}

        {step === 1 && (
          <Card title="Business context" subtitle="Used to find similar past deals and to set the price range">
            <Grid min={200}>
              <Field label="Customer" htmlFor="customer" error={errors.customer}>
                <Input id="customer" value={form.customer} onChange={(e) => set("customer", e.target.value)} placeholder="Company name" aria-invalid={!!errors.customer} autoFocus />
              </Field>
              <Field label="Segment" htmlFor="segment"><Select id="segment" value={form.segment} onChange={(e) => set("segment", e.target.value)} options={["startup", "smb", "mid_market", "enterprise"].map((v) => ({ value: v, label: titleCase(v) }))} /></Field>
              <Field label="Region" htmlFor="region"><Select id="region" value={form.region} onChange={(e) => set("region", e.target.value)} options={["india", "us", "eu", "apac"].map((v) => ({ value: v, label: v.toUpperCase() }))} /></Field>
              <Field label="Product" htmlFor="product"><Select id="product" value={form.product} onChange={(e) => set("product", e.target.value as keyof typeof PRICE)} options={Object.entries(PRICE).map(([v, p]) => ({ value: v, label: `${titleCase(v)} · $${p} per seat` }))} /></Field>
              <Field label="Seats" htmlFor="seats" error={errors.seats} hint={`List price ${money(listPrice)} per year`}>
                <Input id="seats" type="number" min={1} value={form.seats} onChange={(e) => set("seats", Number(e.target.value))} aria-invalid={!!errors.seats} />
              </Field>
            </Grid>
          </Card>
        )}

        {step === 2 && (
          <Card title="Review & analyze" subtitle="Check the details. Analysis takes a few seconds.">
            <Stack gap={16}>
              <KeyValue items={[
                ["Contract", source === "upload" ? (file?.name ?? "—") : <>{sampleId} <Badge tone="warning">Demo</Badge></>],
                ["Customer", form.customer || "—"],
                ["Deal", `${titleCase(form.segment)} · ${form.region.toUpperCase()} · ${titleCase(form.product)} × ${form.seats} seats`],
                ["List price", `${money(listPrice)} per year`],
              ]} />
              <Alert tone="info" title="What happens next">
                CoNexus splits the contract into clauses, scores each one for legal risk and proposes redlines. You then review the
                findings and choose when to start negotiating. Contracts with a deal-breaker clause go to Legal first.
              </Alert>
              {failure && <Alert tone="critical" title="Couldn't analyze this contract">{failure} Your details are kept; fix the file or try again.</Alert>}
            </Stack>
          </Card>
        )}

        <Row justify="between">
          {step > 0 ? <Button type="button" variant="ghost" icon={<ArrowLeft size={16} />} onClick={() => setStep(step - 1)}>Back</Button> : <span />}
          {step < 2
            ? <Button type="submit" variant="primary" icon={<ArrowRight size={16} />}>Continue</Button>
            : <Button type="submit" variant="primary" loading={busy} icon={<ScanSearch size={16} />}>Analyze contract</Button>}
        </Row>
      </Stack>
    </form>
  );
}
