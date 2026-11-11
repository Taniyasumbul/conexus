import { ReactNode, useCallback, useEffect, useState } from "react";
import { ArrowRight, BookMarked, CircleHelp, ShieldAlert, ShieldCheck } from "lucide-react";
import {
  Alert, Badge, Button, Card, EmptyState, Field, Grid, Input, KeyValue, PageHeader, Row, ScoreMeter, Segmented, Skeleton,
  Stack, Stat, Table, Textarea, useToast,
} from "@ui";
import { AnnotateItem, AnnotateReveal, api, ApiError, pct, RiskLevel, titleCase } from "@lib/api";
import { useApi } from "@lib/hooks";
import { ErrorState } from "./shared";

type Choice = "human" | "standard" | "unsure";

function useAnnotator(): [string, (v: string) => void] {
  const [name, setName] = useState(() => {
    const fromLink = new URLSearchParams(window.location.search).get("annotator");  // personal links: /annotate?annotator=taniya
    if (fromLink) return fromLink.trim();
    try { return localStorage.getItem("nx-annotator") || ""; } catch { return ""; }
  });
  return [name, (v: string) => { setName(v); try { localStorage.setItem("nx-annotator", v); } catch { /* ignore */ } }];
}

export default function Annotate() {
  const toast = useToast();
  const [annotator, setAnnotator] = useAnnotator();
  const [draftName, setDraftName] = useState(annotator);
  const [item, setItem] = useState<AnnotateItem | null>(null);
  const [loadErr, setLoadErr] = useState<ApiError | null>(null);
  const [choice, setChoice] = useState<Choice | null>(null);
  const [level, setLevel] = useState<RiskLevel>("medium");
  const [redlinable, setRedlinable] = useState(false);
  const [note, setNote] = useState("");
  const [reveal, setReveal] = useState<AnnotateReveal | null>(null);
  const [busy, setBusy] = useState(false);
  const stats = useApi(api.annotateStats, [reveal]);

  const loadNext = useCallback(async () => {
    if (!annotator) return;
    setReveal(null); setChoice(null); setNote(""); setRedlinable(false); setLevel("medium");
    try { setItem(await api.annotateNext(annotator)); setLoadErr(null); } catch (e) { setLoadErr(e as ApiError); }
  }, [annotator]);
  useEffect(() => { loadNext(); }, [loadNext]);

  const submit = useCallback(async (c: Choice | null = choice) => {
    if (!item || !c || reveal || busy) return;
    setBusy(true);
    try {
      setReveal(await api.annotate({
        clause_id: item.clause_id, annotator, note,
        requires_human: c === "unsure" ? null : c === "human",
        level: c === "unsure" ? null : level, redlinable: c === "unsure" ? null : redlinable,
      }));
    } catch (e) { toast((e as ApiError).message, "critical"); } finally { setBusy(false); }
  }, [item, choice, reveal, busy, annotator, note, level, redlinable, toast]);

  // keyboard: H / S / U choose, 1-3 level, R redlinable, Enter submit or next
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement).closest("input, textarea, select")) return;
      const k = e.key.toLowerCase();
      if (reveal) { if (k === "enter" || k === "n") { e.preventDefault(); loadNext(); } return; }
      if (k === "h") setChoice("human");
      else if (k === "s") setChoice("standard");
      else if (k === "u") setChoice("unsure");
      else if (k === "1") setLevel("low");
      else if (k === "2") setLevel("medium");
      else if (k === "3") setLevel("high");
      else if (k === "r") setRedlinable((v) => !v);
      else if (k === "enter") { e.preventDefault(); submit(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [reveal, loadNext, submit]);

  if (!annotator) {
    return (
      <Stack gap={20}>
        <Header />
        <Card title="Who is annotating?" subtitle="Each annotator labels independently. Use the same name every session.">
          <form onSubmit={(e) => { e.preventDefault(); if (draftName.trim()) setAnnotator(draftName.trim()); }}>
            <Row gap={12}>
              <div style={{ flex: "1 1 240px" }}><Field label="Your name" htmlFor="ann-name"><Input id="ann-name" value={draftName} onChange={(e) => setDraftName(e.target.value)} placeholder="e.g. taniya" /></Field></div>
              <Button type="submit" variant="primary" style={{ alignSelf: "flex-end" }}>Start annotating</Button>
            </Row>
          </form>
        </Card>
      </Stack>
    );
  }
  if (loadErr) return <Stack gap={20}><Header /><ErrorState error={loadErr} onRetry={loadNext} /></Stack>;

  const st = stats.data;
  const mine = st?.per_annotator[annotator] ?? 0;

  return (
    <Stack gap={20}>
      <Header actions={<Row gap={8}><Badge tone="info" icon={<BookMarked />}>{annotator}</Badge><Button size="sm" variant="ghost" onClick={() => setAnnotator("")}>Switch</Button></Row>} />

      <div className="nx-split">
        <Stack gap={16}>
          {!item ? <Skeleton height={320} /> : item.done ? (
            <Card><EmptyState title="Queue finished">You have labelled every clause in the queue. Thank you.</EmptyState></Card>
          ) : (
            <Card title={<Row gap={10}>Clause {item.position} of {item.queue_size}{item.labelled_by_others > 0 && <Badge tone="info">Agreement check</Badge>}</Row>}
              subtitle={item.contract}>
              <Stack gap={16}>
                <blockquote style={{ margin: 0, padding: "var(--s-4)", borderLeft: "3px solid var(--border-strong)", background: "var(--surface-2)", borderRadius: "var(--r-md)", lineHeight: 1.7, maxWidth: "80ch" }}>
                  {item.text}
                </blockquote>
                <span className="nx-muted" style={{ fontSize: "var(--text-xs)" }}>Clause type (mapped): {titleCase(item.type)} · Perspective: a small software vendor reviewing this clause</span>

                {!reveal ? (
                  <>
                    <div className="nx-choice-grid" role="group" aria-label="Does this clause need a human?">
                      {([
                        ["human", <ShieldAlert size={16} key="i" />, "Needs a human", "H · deal-breaker for the vendor"],
                        ["standard", <ShieldCheck size={16} key="i" />, "Agent may handle", "S · standard or redlinable"],
                        ["unsure", <CircleHelp size={16} key="i" />, "Unsure", "U · excluded from ground truth"],
                      ] as const).map(([v, icon, title, detail]) => (
                        <button key={v} type="button" className="nx-choice" aria-pressed={choice === v} onClick={() => setChoice(v)}>
                          <Row gap={6}>{icon}<strong>{title}</strong></Row><small>{detail}</small>
                        </button>
                      ))}
                    </div>
                    {choice && choice !== "unsure" && (
                      <Grid min={220}>
                        <Field label="Risk level (1 · 2 · 3)" htmlFor="lvl">
                          <Segmented<RiskLevel> label="Risk level" value={level} onChange={setLevel} options={[{ value: "low", label: "Low" }, { value: "medium", label: "Medium" }, { value: "high", label: "High" }]} />
                        </Field>
                        <Field label="Standard fallback exists? (R)" htmlFor="rl">
                          <Segmented label="Redlinable" value={redlinable ? "yes" : "no"} onChange={(v) => setRedlinable(v === "yes")} options={[{ value: "no", label: "No" }, { value: "yes", label: "Yes, redlinable" }]} />
                        </Field>
                      </Grid>
                    )}
                    <Field label="Note (optional)" htmlFor="ann-note"><Textarea id="ann-note" value={note} onChange={(e) => setNote(e.target.value)} style={{ minHeight: 64 }} placeholder="Why, especially if unsure or the party is unclear" /></Field>
                    <Row justify="end"><Button variant="primary" disabled={!choice} loading={busy} onClick={() => submit()}>Save label <kbd style={{ opacity: 0.7, fontSize: 11 }}>Enter</kbd></Button></Row>
                  </>
                ) : (
                  <>
                    <Alert tone="info" title="Saved. Here is what the dataset and the model said">
                      <KeyValue items={[
                        ["CUAD category", reveal.categories.join(", ")],
                        ["Proxy label", reveal.proxy_human === null ? "Ambiguous (no proxy)" : reveal.proxy_human ? "Needs human" : "Agent may handle"],
                        ["Risk model", <Row gap={8}><Badge tone={reveal.model.requires_human ? "critical" : "good"}>{reveal.model.requires_human ? "Needs human" : "Agent may handle"}</Badge><div style={{ width: 160 }}><ScoreMeter score={reveal.model.score} /></div></Row>],
                      ]} />
                    </Alert>
                    <Row justify="end"><Button variant="primary" icon={<ArrowRight size={16} />} onClick={loadNext}>Next clause <kbd style={{ opacity: 0.7, fontSize: 11 }}>Enter</kbd></Button></Row>
                  </>
                )}
              </Stack>
            </Card>
          )}
          <p className="nx-muted" style={{ fontSize: "var(--text-xs)" }}>
            Keys: <code>H</code> needs human · <code>S</code> agent may handle · <code>U</code> unsure · <code>1-3</code> level · <code>R</code> redlinable · <code>Enter</code> save / next.
            The category, proxy label and model opinion appear only after you save, so they cannot anchor your judgement.
          </p>
        </Stack>

        <Stack gap={16}>
          <Grid min={140}>
            <Stat label="Your labels" value={mine} hint={st ? `${pct(mine / st.queue_size)} of queue` : undefined} />
            <Stat label="Adjudicated" value={st?.adjudicated ?? "—"} hint={st ? `${st.positives} need human` : undefined} />
          </Grid>
          <Card title="Agreement" subtitle="Cohen's kappa on clauses both annotators labelled">
            {st?.pairs.length ? (
              <Table rows={st.pairs} rowKey={(p) => p.a + p.b} columns={[
                { key: "p", header: "Pair", render: (p) => `${p.a} · ${p.b}` },
                { key: "o", header: "Overlap", num: true, render: (p) => p.overlap },
                { key: "k", header: "Kappa", num: true, render: (p) => p.kappa == null ? "—" : <Badge tone={p.kappa >= 0.6 ? "good" : p.kappa >= 0.4 ? "warning" : "critical"}>{p.kappa.toFixed(2)}</Badge> },
              ]} />
            ) : <p className="nx-secondary">Needs a second annotator. Clauses already labelled by someone else are offered first.</p>}
          </Card>
          {st && st.adjudicated > 0 && (
            <Card title="Expert labels vs">
              <KeyValue items={[["CUAD proxy labels", pct(st.proxy_agreement)], ["Current risk model", pct(st.model_agreement)]]} />
            </Card>
          )}
          {st && <span className="nx-muted" style={{ fontSize: "var(--text-xs)" }}>Exported to <code>{st.export_path.split("/").slice(-3).join("/")}</code>. Run <code>make eval</code> to score the model against expert labels.</span>}
        </Stack>
      </div>
    </Stack>
  );
}

function Header({ actions }: { actions?: ReactNode }) {
  return <PageHeader eyebrow="RO2 · Ground truth" title="Annotate clauses" actions={actions}
    description="Label real CUAD contract clauses from the vendor's side: does this need a human before signing? Follow docs/ANNOTATION_GUIDELINES.md." />;
}
