/* Nexus UI - upload drop zone, analysis reveal and the marked-up contract document. */
import { DragEvent, ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { CheckCheck, FileText, ShieldAlert, ShieldCheck, TriangleAlert, UploadCloud, UserCheck, X } from "lucide-react";
import type { Clause, ClauseRisk, ContractDocument } from "@lib/api";
import { titleCase } from "@lib/api";
import { Badge } from "./primitives";
import { CountUp } from "./primitives";
import { RedlineDiff, ScoreMeter } from "./domain";

/* ------------------------------------------------------------------ drop zone */
const ACCEPT = [".pdf", ".docx", ".txt", ".md"];
export function Dropzone({ file, onFile, id = "dropzone" }: { file: File | null; onFile: (f: File | null) => void; id?: string }) {
  const [over, setOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const take = (f: File | undefined) => {
    if (!f) return;
    const ok = ACCEPT.some((ext) => f.name.toLowerCase().endsWith(ext));
    setError(ok ? null : `${f.name} is not a PDF, Word or text file`);
    onFile(ok ? f : null);
  };
  const onDrop = (e: DragEvent) => { e.preventDefault(); setOver(false); take(e.dataTransfer.files?.[0]); };
  return (
    <div className="nx-drop" data-over={over} data-has={!!file}
      onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)} onDrop={onDrop}
      onClick={() => input.current?.click()} role="button" tabIndex={0}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && input.current?.click()} aria-describedby={`${id}-hint`}>
      <input ref={input} id={id} type="file" accept={ACCEPT.join(",")} hidden onChange={(e) => take(e.target.files?.[0])} />
      {file ? (
        <div className="nx-drop__file">
          <span className="nx-drop__icon"><FileText size={22} /></span>
          <div style={{ minWidth: 0 }}><b>{file.name}</b><small>{(file.size / 1024).toFixed(0)} KB · ready to analyze</small></div>
          <button type="button" className="nx-iconbtn" aria-label="Remove file" onClick={(e) => { e.stopPropagation(); onFile(null); }}><X size={16} /></button>
        </div>
      ) : (
        <>
          <span className="nx-drop__icon big"><UploadCloud size={28} /></span>
          <b>Drop the customer's contract here</b>
          <small id={`${id}-hint`}>or click to browse · PDF, Word or text</small>
        </>
      )}
      {error && <span className="nx-drop__error">{error}</span>}
    </div>
  );
}

/* ------------------------------------------------------------------ analysis reveal */
type Tone = "human" | "off" | "ok";
const toneOf = (r?: ClauseRisk): Tone => (!r ? "ok" : r.requires_human ? "human" : r.level !== "low" ? "off" : "ok");

/** The analyst's result, revealed clause by clause like a scan. */
export function AnalysisReveal({ clauses, risks, onOpen }: { clauses: Clause[]; risks: ClauseRisk[]; onOpen?: (id: string) => void }) {
  const byId = useMemo(() => Object.fromEntries(risks.map((r) => [r.clause_id, r])), [risks]);
  const human = risks.filter((r) => r.requires_human).length;
  const off = risks.filter((r) => !r.requires_human && r.level !== "low").length;
  return (
    <div className="nx-reveal">
      <div className="nx-reveal__counts">
        <div><b><CountUp value={clauses.length} /></b><span>clauses read</span></div>
        <div data-tone="human"><b><CountUp value={human} /></b><span>need Legal</span></div>
        <div data-tone="off"><b><CountUp value={off} /></b><span>off-market, auto-redline</span></div>
        <div data-tone="ok"><b><CountUp value={clauses.length - human - off} /></b><span>standard</span></div>
      </div>
      <ol className="nx-reveal__list">
        {clauses.map((c, i) => {
          const t = toneOf(byId[c.id]);
          return (
            <li key={c.id} data-tone={t} style={{ animationDelay: `${120 + i * 70}ms` }}>
              <button type="button" onClick={() => onOpen?.(c.id)}>
                <span className="nx-reveal__ref">§ {c.id.slice(1)}</span>
                <span className="nx-reveal__name">{c.heading.replace(/^\d+\s*/, "") || titleCase(c.type)}</span>
                <span className="nx-reveal__tag">
                  {t === "human" ? <><ShieldAlert size={14} />Needs Legal</> : t === "off" ? <><TriangleAlert size={14} />Redline</> : <><ShieldCheck size={14} />Standard</>}
                </span>
              </button>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

/* ------------------------------------------------------------------ marked-up document */
export function DocumentView({ doc, clauses, risks, reviewed, redlineResults, threshold = 0.5, initial }: {
  doc: ContractDocument; clauses: Clause[]; risks: ClauseRisk[]; reviewed: string[]; redlineResults: Record<string, boolean>; threshold?: number; initial?: string | null;
}) {
  const byId = useMemo(() => Object.fromEntries(risks.map((r) => [r.clause_id, r])), [risks]);
  const clauseById = useMemo(() => Object.fromEntries(clauses.map((c) => [c.id, c])), [clauses]);
  const first = risks.find((r) => r.requires_human) ?? risks.find((r) => r.level !== "low");
  const [sel, setSel] = useState<string | null>(initial ?? first?.clause_id ?? null);
  const paper = useRef<HTMLElement>(null);
  // bring the selected clause into view inside the document (not the whole page)
  useEffect(() => {
    const box = paper.current;
    const el = box?.querySelector<HTMLElement>(`[data-clause="${sel}"]`);
    if (box && el) box.scrollTo({ top: Math.max(0, el.offsetTop - 60), behavior: "smooth" });
  }, [sel]);

  const parts: ReactNode[] = [];
  let pos = 0;
  doc.segments.forEach((s, k) => {
    if (s.start > pos) parts.push(<span key={`t${k}`} className="nx-doc__plain">{doc.text.slice(pos, s.start)}</span>);
    const r = byId[s.clause_id];
    const resolved = reviewed.includes(s.clause_id) || redlineResults[s.clause_id] === true;
    const tone = resolved ? "resolved" : toneOf(r);
    const marked = tone !== "ok";
    parts.push(
      <span key={s.clause_id} className="nx-doc__clause" data-tone={tone} data-sel={sel === s.clause_id} data-clause={s.clause_id}>
        <span className="nx-doc__head">{doc.text.slice(s.start, s.body_start)}</span>
        {marked ? (
          <mark role="button" tabIndex={0} onClick={() => setSel(s.clause_id)} onKeyDown={(e) => e.key === "Enter" && setSel(s.clause_id)}
            aria-label={`Clause ${s.clause_id.slice(1)}: ${tone}`}>{doc.text.slice(s.body_start, s.end)}</mark>
        ) : <span onClick={() => setSel(s.clause_id)}>{doc.text.slice(s.body_start, s.end)}</span>}
      </span>,
    );
    pos = s.end;
  });
  if (pos < doc.text.length) parts.push(<span key="tail" className="nx-doc__plain">{doc.text.slice(pos)}</span>);

  const r = sel ? byId[sel] : undefined;
  const c = sel ? clauseById[sel] : undefined;
  const resolved = sel ? reviewed.includes(sel) || redlineResults[sel] === true : false;

  return (
    <div className="nx-docwrap">
      <div className="nx-doc__legend">
        <span data-tone="human">Needs Legal</span><span data-tone="off">Off-market, redlined</span><span data-tone="resolved">Resolved</span>
      </div>
      <div className="nx-docgrid">
        <article ref={paper} className="nx-doc" aria-label="Contract with risky clauses highlighted">{parts}</article>
        <aside className="nx-doc__side" aria-live="polite">
          {r && c ? (
            <div className="nx-doc__note" key={sel}>
              <div className="nx-row" style={{ justifyContent: "space-between" }}>
                <b>§ {c.id.slice(1)} {c.heading.replace(/^\d+\s*/, "") || titleCase(c.type)}</b>
                {resolved ? <Badge tone="good" icon={reviewed.includes(c.id) ? <UserCheck /> : <CheckCheck />}>{reviewed.includes(c.id) ? "Reviewed" : "Redline accepted"}</Badge>
                  : r.requires_human ? <Badge tone="critical" icon={<ShieldAlert />}>Needs Legal</Badge>
                  : r.level !== "low" ? <Badge tone="warning">Off-market</Badge> : <Badge tone="good">Standard</Badge>}
              </div>
              <ScoreMeter score={r.score} threshold={threshold} />
              {r.reasons.length > 0 ? (
                <ul className="nx-reasons">{r.reasons.map((x) => <li key={x}>{x}</li>)}</ul>
              ) : <p className="nx-secondary">Matches the standard playbook.</p>}
              {r.redline && r.level !== "low" && <RedlineDiff original={c.text} proposed={r.redline} label={r.redlinable ? "Our redline" : "Fallback for the reviewer"} />}
            </div>
          ) : <p className="nx-secondary">Click a highlighted clause to see why it was flagged.</p>}
        </aside>
      </div>
    </div>
  );
}
