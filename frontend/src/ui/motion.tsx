/* Nexus UI - animated, data-driven visuals. Every animation reflects real system state;
   with prefers-reduced-motion they render as static diagrams. */
import { ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { BookOpenCheck, Brain, Check, FileSearch, Mail, ShieldAlert, TrendingUp, UserRound, Workflow } from "lucide-react";
import type { AuditEvent, ClauseRisk, Clause, Offer, PricingPlan } from "@lib/api";
import { ago, money } from "@lib/api";

const reduced = () => typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

/* ------------------------------------------------------------------ agent network */
export type AgentKey = "contract_analyst" | "legal_risk" | "memory" | "sales_pricing" | "communication" | "audit" | "human";
const AGENTS: { key: AgentKey; label: string; icon: typeof Brain; angle: number }[] = [
  { key: "contract_analyst", label: "Analyst", icon: FileSearch, angle: -150 },
  { key: "legal_risk", label: "Legal / Risk", icon: ShieldAlert, angle: -90 },
  { key: "memory", label: "Memory", icon: Brain, angle: -30 },
  { key: "sales_pricing", label: "Pricing", icon: TrendingUp, angle: 30 },
  { key: "communication", label: "Communication", icon: Mail, angle: 90 },
  { key: "audit", label: "Audit", icon: BookOpenCheck, angle: 150 },
];
export const agentOf = (e: AuditEvent): AgentKey | "orchestrator" =>
  e.agent.startsWith("human:") ? "human" : (e.agent as AgentKey | "orchestrator");

/** The multi-agent system as a living diagram. `active` agents glow and send packets faster. */
export function AgentNetwork({ active }: { active: Set<string> }) {
  const W = 400, H = 280, cx = W / 2, cy = H / 2 - 4, rx = 150, ry = 100;
  const still = reduced();
  const nodes = AGENTS.map((a) => ({ ...a, x: cx + rx * Math.cos((a.angle * Math.PI) / 180), y: cy + ry * Math.sin((a.angle * Math.PI) / 180) }));
  const anyActive = active.size > 0;
  return (
    <svg className="nx-net" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Agent network. ${anyActive ? "Working: " + [...active].join(", ") : "Idle"}`}>
      <defs>
        <radialGradient id="nx-net-core"><stop offset="0%" stopColor="var(--accent)" stopOpacity=".35" /><stop offset="100%" stopColor="var(--accent)" stopOpacity="0" /></radialGradient>
      </defs>
      <circle cx={cx} cy={cy} r={70} fill="url(#nx-net-core)" className={still ? undefined : "nx-net__breathe"} />
      {nodes.map((n, i) => {
        const on = active.has(n.key) || (n.key === "audit" && anyActive);
        const path = `M${cx},${cy} L${n.x},${n.y}`;
        return (
          <g key={n.key}>
            <path d={path} className={`nx-net__edge ${on ? "on" : ""}`} />
            {!still && (
              <>
                <circle r={on ? 3.6 : 2.4} className={`nx-net__packet ${on ? "on" : ""}`}>
                  <animateMotion dur={on ? "1.1s" : "3.2s"} begin={`${(i * 0.45) % 3}s`} repeatCount="indefinite" path={path} />
                </circle>
                {on && (
                  <circle r={3} className="nx-net__packet on back">
                    <animateMotion dur="1.4s" begin={`${0.5 + i * 0.2}s`} repeatCount="indefinite" path={`M${n.x},${n.y} L${cx},${cy}`} />
                  </circle>
                )}
              </>
            )}
          </g>
        );
      })}
      {nodes.map((n) => {
        const on = active.has(n.key) || (n.key === "audit" && anyActive);
        const Icon = n.icon;
        return (
          <g key={n.key} className={`nx-net__node ${on ? "on" : ""}`}>
            {on && !still && <circle cx={n.x} cy={n.y} r={22} className="nx-net__ring" />}
            <circle cx={n.x} cy={n.y} r={22} className="nx-net__disc" />
            <Icon x={n.x - 10} y={n.y - 10} width={20} height={20} className="nx-net__icon" />
            <text x={n.x} y={n.y + 38} textAnchor="middle" className="nx-net__label">{n.label}</text>
          </g>
        );
      })}
      <g className={`nx-net__core ${active.has("orchestrator") || anyActive ? "on" : ""}`}>
        <circle cx={cx} cy={cy} r={30} className="nx-net__hub" />
        <Workflow x={cx - 13} y={cy - 13} width={26} height={26} className="nx-net__hubicon" />
        <text x={cx} y={cy + 48} textAnchor="middle" className="nx-net__label strong">Orchestrator</text>
      </g>
      {active.has("human") && (
        <g className="nx-net__node on">
          <circle cx={W - 26} cy={26} r={16} className="nx-net__disc" />
          <UserRound x={W - 34} y={18} width={16} height={16} className="nx-net__icon" />
        </g>
      )}
    </svg>
  );
}

const AGENT_LABEL: Record<string, string> = {
  contract_analyst: "Analyst", legal_risk: "Legal/Risk", memory: "Memory", sales_pricing: "Pricing",
  communication: "Comms", orchestrator: "Orchestrator", audit: "Audit", auth: "Auth",
};
export function LiveTicker({ events }: { events: AuditEvent[] }) {
  return (
    <ol className="nx-ticker" aria-live="polite">
      {events.map((e) => (
        <li key={e.seq}>
          <span className="nx-ticker__who">{e.agent.startsWith("human:") ? "Reviewer" : AGENT_LABEL[e.agent] ?? e.agent}</span>
          <span className="nx-ticker__what">{e.action.replace(/_/g, " ").toLowerCase()} · {e.rationale}</span>
          <span className="nx-ticker__when">{ago(e.ts)}</span>
        </li>
      ))}
    </ol>
  );
}

/* ------------------------------------------------------------------ price ruler */
/** Our offer and theirs as two markers converging round by round. */
export function PriceRuler({ history, plan, agreed, maxRounds = 8 }: { history: Offer[]; plan: PricingPlan; agreed?: number | null; maxRounds?: number }) {
  const ours = [...history].reverse().find((h) => h.sender === "us" && h.terms)?.terms?.price;
  const theirs = [...history].reverse().find((h) => h.sender === "them" && h.terms)?.terms?.price;
  const round = Math.max(0, ...history.map((h) => h.round));
  const vals = [plan.floor_price, plan.anchor.price, ours, theirs, agreed].filter((v): v is number => v != null);
  const lo = Math.min(...vals) * 0.94, hi = Math.max(...vals) * 1.04;
  const pos = (v: number) => `${((v - lo) / (hi - lo)) * 100}%`;
  const u = agreed ?? ours, t = agreed ?? theirs;
  const gap = u != null && t != null ? Math.abs(u - t) : null;
  const fmt = (v: number) => (hi >= 100_000 ? money(v, true) : money(v));
  return (
    <div className="nx-ruler" data-agreed={agreed != null}>
      <div className="nx-ruler__head">
        <span><b>Round {round || 0}</b> of {maxRounds}</span>
        <span className="nx-ruler__dots" aria-hidden>{Array.from({ length: maxRounds }, (_, i) => <i key={i} data-on={i < round} />)}</span>
        <span className="nx-ruler__gap">{agreed != null ? <><Check size={14} />Agreed at {money(agreed)}</> : gap != null ? <>Gap {money(gap)}</> : "Waiting for the first offer"}</span>
      </div>
      <div className="nx-ruler__track">
        <div className="nx-ruler__tick" style={{ left: pos(plan.floor_price) }}><span>Floor {fmt(plan.floor_price)}</span></div>
        {plan.concession_limit > plan.floor_price && (
          <div className="nx-ruler__tick soft" style={{ left: pos(plan.concession_limit) }}><span>Limit {fmt(plan.concession_limit)}</span></div>
        )}
        {u != null && t != null && (
          <div className="nx-ruler__span" style={{ left: pos(Math.min(u, t)), width: `calc(${pos(Math.max(u, t))} - ${pos(Math.min(u, t))})` }} />
        )}
        {t != null && <div className="nx-ruler__mark them" style={{ left: pos(t) }}><span>Them {fmt(t)}</span></div>}
        {u != null && <div className="nx-ruler__mark us" style={{ left: pos(u) }}><span>Us {fmt(u)}</span></div>}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ contract fingerprint */
/** One bar per clause, coloured and sized by risk, revealed by a scanning beam. */
export function ContractFingerprint({ clauses, risks, resolved, onPick }: {
  clauses: Clause[]; risks: ClauseRisk[]; resolved: (id: string) => boolean; onPick?: (id: string) => void;
}) {
  const byId = useMemo(() => Object.fromEntries(risks.map((r) => [r.clause_id, r])), [risks]);
  return (
    <div className="nx-print" role="list" aria-label="Contract risk fingerprint">
      {!reduced() && <span className="nx-print__beam" aria-hidden />}
      {clauses.map((c, i) => {
        const r = byId[c.id];
        const tone = !r ? "low" : resolved(c.id) ? "ok" : r.requires_human ? "high" : r.level;
        return (
          <button key={c.id} type="button" role="listitem" className="nx-print__bar" data-tone={tone} style={{ animationDelay: `${i * 45}ms` }}
            title={`§ ${c.id.slice(1)} ${c.heading.replace(/^\d+\s*/, "") || c.type}: ${tone === "ok" ? "resolved" : r?.level ?? "low"}`}
            onClick={() => onPick?.(c.id)} aria-label={`Clause ${c.id.slice(1)}, ${tone}`} />
        );
      })}
    </div>
  );
}

/* ------------------------------------------------------------------ confetti */
/** A short burst on a canvas overlay; calls onDone after ~1.8s. */
export function Confetti({ onDone }: { onDone: () => void }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    if (reduced()) { onDone(); return; }
    const cv = ref.current!, ctx = cv.getContext("2d")!;
    const dpr = window.devicePixelRatio || 1;
    cv.width = innerWidth * dpr; cv.height = innerHeight * dpr; ctx.scale(dpr, dpr);
    const cs = getComputedStyle(document.documentElement);
    const colors = ["--accent", "--series-1", "--series-2", "--good", "--warning"].map((v) => cs.getPropertyValue(v).trim());
    const parts = Array.from({ length: 140 }, () => ({
      x: innerWidth / 2 + (Math.random() - 0.5) * 120, y: innerHeight * 0.35,
      vx: (Math.random() - 0.5) * 14, vy: -Math.random() * 13 - 4, r: Math.random() * 6 + 4,
      rot: Math.random() * 6, vr: (Math.random() - 0.5) * 0.3, c: colors[Math.floor(Math.random() * colors.length)],
    }));
    const start = performance.now();
    let raf = 0;
    const tick = (t: number) => {
      const k = (t - start) / 1800;
      ctx.clearRect(0, 0, innerWidth, innerHeight);
      for (const p of parts) {
        p.vy += 0.35; p.x += p.vx; p.y += p.vy; p.rot += p.vr; p.vx *= 0.99;
        ctx.save(); ctx.globalAlpha = Math.max(0, 1 - k); ctx.translate(p.x, p.y); ctx.rotate(p.rot);
        ctx.fillStyle = p.c; ctx.fillRect(-p.r / 2, -p.r / 4, p.r, p.r / 2); ctx.restore();
      }
      if (k < 1) raf = requestAnimationFrame(tick); else onDone();
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [onDone]);
  return <canvas ref={ref} className="nx-confetti" aria-hidden />;
}

/** Remembers the previous value of something (to detect transitions such as -> signed). */
export function usePrevious<T>(v: T): T | undefined {
  const r = useRef<T>();
  useEffect(() => { r.current = v; }, [v]);
  return r.current;
}

/** A celebratory overlay: stamp slams down while confetti bursts. */
export function SignedCelebration({ children, onDone }: { children: ReactNode; onDone: () => void }) {
  const [show, setShow] = useState(true);
  if (!show) return null;
  // portal to <body>: page transitions leave transforms on ancestors, which would trap position:fixed
  return createPortal(
    <div className="nx-celebrate" role="status" aria-label="Deal signed">
      <Confetti onDone={() => { setShow(false); onDone(); }} />
      <div className="nx-celebrate__stamp">{children}</div>
    </div>,
    document.body,
  );
}
