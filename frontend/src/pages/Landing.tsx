import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  ArrowRight, BookOpenCheck, Brain, Check, FileDown, FileSearch, FileSignature, Hand, Link2, Mail, MessageSquare,
  ShieldAlert, ShieldCheck, SlidersHorizontal, Sparkles, TrendingUp, Workflow,
} from "lucide-react";
import { AgentNetwork, Badge, Logo, PriceRuler, RedlineDiff } from "@ui";
import type { AuthStatus, Offer, PricingPlan, User } from "@lib/api";
import { api } from "@lib/api";

/* ------------------------------------------------------------------ shared animation clock */
function useTicker(len: number, ms: number) {
  const [i, setI] = useState(0);
  useEffect(() => {
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) { setI(len - 1); return; }
    const t = setInterval(() => setI((x) => (x + 1) % len), ms);
    return () => clearInterval(t);
  }, [len, ms]);
  return i;
}

/* ------------------------------------------------------------------ live demo (illustrative data) */
const PLAN: PricingPlan = {
  anchor: { price: 58300, payment_days: 30, term_months: 12 }, target: { price: 54000, payment_days: 30, term_months: 12 },
  floor_price: 37000, concession_limit: 45200, max_payment_days: 60, wtp_estimate: 53000, evidence: [],
};
const US = [58300, 57500, 56000, 54300, 52600];
const THEM = [46200, 47900, 49400, 50600, 52600];
const STEPS: { active: string[]; caption: string; round: number; agreed?: boolean }[] = [
  { active: ["contract_analyst"], caption: "Reading 14 clauses from the customer's paper", round: 0 },
  { active: ["legal_risk"], caption: "Uncapped liability found. Redline drafted", round: 0 },
  { active: ["memory", "sales_pricing"], caption: "25 similar deals found. Anchor set", round: 0 },
  { active: ["communication", "sales_pricing"], caption: "Round 1 offer sent", round: 1 },
  { active: ["communication"], caption: "Customer counters", round: 2 },
  { active: ["communication", "sales_pricing"], caption: "Conceding on the policy curve", round: 3 },
  { active: ["communication", "sales_pricing"], caption: "Redline accepted", round: 4 },
  { active: ["orchestrator", "audit"], caption: "Agreed and sent for signature", round: 5, agreed: true },
];
function history(round: number): Offer[] {
  const h: Offer[] = [];
  for (let r = 1; r <= round; r++) {
    h.push({ round: r, sender: "us", terms: { price: US[r - 1], payment_days: 30, term_months: 12 }, message: "", accept: false, walk_away: false, redline_responses: {}, new_legal_terms: false });
    h.push({ round: r, sender: "them", terms: { price: THEM[r - 1], payment_days: 30, term_months: 12 }, message: "", accept: false, walk_away: false, redline_responses: {}, new_legal_terms: false });
  }
  return h;
}

function HeroStage() {
  const i = useTicker(STEPS.length, 1900);
  const step = STEPS[i];
  return (
    <div className="lp-stage" aria-label="Animated product demo with example data">
      <div className="lp-window">
        <div className="lp-window__bar"><i /><i /><i /><span>Negotiation · Helix Health · example</span></div>
        <div className="lp-window__body">
          <AgentNetwork active={new Set(step.active)} />
          <div className="lp-window__side">
            <div className="lp-caption" key={i}><span>{i + 1}/{STEPS.length}</span>{step.caption}</div>
            <PriceRuler history={history(step.round)} plan={PLAN} agreed={step.agreed ? 52600 : null} maxRounds={8} />
          </div>
        </div>
      </div>
      <div className="lp-float lp-float--a" data-on={i >= 1 && i < 6}>
        <span className="lp-float__icon rose"><ShieldAlert size={16} /></span>
        <div><b>§ 6 Liability</b><small>Uncapped. Redline proposed</small></div>
      </div>
      <div className="lp-float lp-float--b" data-on={step.agreed === true}>
        <span className="lp-float__icon mint"><FileSignature size={16} /></span>
        <div><b>Signed · $52,600/yr</b><small>Sealed in the audit ledger</small></div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ bento visuals */
function MiniChain() {
  const i = useTicker(1000, 2200);
  const h = (n: number) => ((n * 2654435761) >>> 0).toString(16).padStart(8, "0").slice(0, 6);
  const acts = ["FLAG_CLAUSE", "SEND_OFFER", "ESCALATE", "APPROVE", "EXECUTE"];
  return (
    <div className="lp-chain">
      {[0, 1, 2].map((k) => (
        <div key={i + k} className="lp-chain__b" data-new={k === 2}>
          <b>{acts[(i + k) % acts.length]}</b><code>{h(i + k)}…</code>
          {k < 2 && <Link2 size={14} className="lp-chain__l" />}
        </div>
      ))}
    </div>
  );
}

function MiniPolicy() {
  return (
    <div className="lp-policy">
      {[["Risk threshold", 50], ["Autonomy limit", 70], ["Max discount", 45]].map(([l, v]) => (
        <div key={l}><span>{l}</span><div><i style={{ width: `${v}%` }} /></div></div>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ pricing */
const PLANS = [
  { name: "Starter", price: "$0", per: "forever", blurb: "Try autonomous negotiation on your own contracts.", cta: "Start free",
    features: ["25 contracts a month", "All six agents, offline models", "Risk review and redlines", "Word export with tracked changes"] },
  { name: "Growth", price: "$49", per: "per user / month", blurb: "For sales teams that close deals every week.", cta: "Start 14-day trial", popular: true,
    features: ["Unlimited contracts", "Claude or a private local model", "Escalation inbox and roles", "Slack and e-mail alerts", "CRM memory from past deals"] },
  { name: "Enterprise", price: "Custom", per: "annual contract", blurb: "For legal-heavy teams with compliance needs.", cta: "Talk to us",
    features: ["Custom escalation policy", "Expert-labelled risk model", "Tamper-evident audit exports", "Single sign-on", "Dedicated support"] },
];

/* ------------------------------------------------------------------ page */
function useDemo(onSignedIn?: (u: User) => void) {
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  return {
    busy,
    start: async () => {
      setBusy(true);
      try { const u = await api.demo(); navigate("/", { replace: true }); onSignedIn?.(u); }
      catch { navigate("/signin"); }
      finally { setBusy(false); }
    },
  };
}

export default function Landing({ status, onSignedIn }: { status?: AuthStatus | null; onSignedIn?: (u: User) => void }) {
  const demo = useDemo(onSignedIn);
  const canDemo = !!status?.demo_enabled;
  return (
    <div className="lp">
      <div className="lp-gradient" aria-hidden><span /><span /><span /><span /></div>

      <header className="lp-nav">
        <div className="lp-wrap lp-nav__in">
          <Link to="/" className="lp-brand"><Logo /><b>CoNexus</b></Link>
          <nav className="lp-nav__links" aria-label="Sections">
            <a href="#product">Product</a><a href="#proof">Results</a><a href="#how">How it works</a><a href="#pricing">Pricing</a>
          </nav>
          <div className="lp-nav__end">
            <Link to="/signin" className="lp-link">Sign in</Link>
            <Link to={status?.signup_enabled ? "/signup" : "/signin"} className="lp-btn lp-btn--dark lp-btn--sm">Start free<ArrowRight size={15} /></Link>
          </div>
        </div>
      </header>

      <section className="lp-hero">
        <div className="lp-wrap lp-hero__grid">
          <div className="lp-hero__copy">
            <span className="lp-pill"><Sparkles size={14} />AI agents for B2B contracts</span>
            <h1>Contract negotiation on autopilot</h1>
            <p>CoNexus reads your customer's contract, fixes the risky clauses, negotiates the price from your past deals and asks a human only when it really matters.</p>
            <div className="lp-hero__ctas">
              <Link to={status?.signup_enabled ? "/signup" : "/signin"} className="lp-btn lp-btn--dark lp-btn--lg">Start free<ArrowRight size={18} /></Link>
              {canDemo
                ? <button type="button" className="lp-btn lp-btn--ghost lp-btn--lg" onClick={demo.start} disabled={demo.busy}>{demo.busy ? "Opening demo…" : "Try the demo"}<Sparkles size={16} /></button>
                : <a href="#product" className="lp-btn lp-btn--ghost lp-btn--lg">See it work</a>}
            </div>
            <div className="lp-hero__chips">
              <span><MessageSquare size={14} />Slack alerts</span><span><Mail size={14} />E-mail negotiation</span>
              <span><FileDown size={14} />Word redlines</span><span><Workflow size={14} />Claude or local AI</span>
            </div>
          </div>
          <HeroStage />
        </div>
      </section>

      <section className="lp-section" id="product">
        <div className="lp-wrap">
          <div className="lp-head">
            <span className="lp-kicker">Product</span>
            <h2>Six agents that do the work your team keeps postponing</h2>
          </div>
          <div className="lp-bento">
            <article className="lp-card lp-card--wide">
              <div className="lp-card__text"><span className="lp-ico teal"><TrendingUp size={18} /></span><h3>Negotiates price like your best rep</h3>
                <p>Anchors from what similar customers actually paid, concedes on a policy curve and never drops below your floor.</p></div>
              <div className="lp-card__viz"><PriceRuler history={history(4)} plan={PLAN} maxRounds={8} /></div>
            </article>
            <article className="lp-card">
              <span className="lp-ico rose"><ShieldAlert size={18} /></span><h3>Catches the clauses that hurt</h3>
              <p>Uncapped liability, IP grabs and exclusivity are flagged and redlined automatically.</p>
              <RedlineDiff original="Payable within ninety (90) days." proposed="Payable within thirty (30) days." label="Redline" />
            </article>
            <article className="lp-card">
              <span className="lp-ico amber"><Hand size={18} /></span><h3>Stops for a person when it matters</h3>
              <p>Deal-breakers, rejected redlines and big deals wait in Legal's inbox. Approve and the agents carry on.</p>
              <div className="lp-mini-inbox"><b>Saffron Works</b><Badge tone="critical">Needs Legal</Badge><span className="lp-mini-approve"><Check size={12} />Approve</span></div>
            </article>
            <article className="lp-card">
              <span className="lp-ico blue"><BookOpenCheck size={18} /></span><h3>Every decision on the record</h3>
              <p>Each step is chained with SHA-256. Change one entry and verification fails.</p>
              <MiniChain />
            </article>
            <article className="lp-card">
              <span className="lp-ico violet"><SlidersHorizontal size={18} /></span><h3>Your rules, not ours</h3>
              <p>Set the risk threshold, autonomy limit, discount and payment terms. Every change is audited.</p>
              <MiniPolicy />
            </article>
            <article className="lp-card">
              <span className="lp-ico mint"><Brain size={18} /></span><h3>Learns from every deal</h3>
              <p>Closed deals flow back into memory, so the next offer starts smarter.</p>
              <div className="lp-agents">
                {[FileSearch, ShieldAlert, Brain, TrendingUp, Mail, BookOpenCheck].map((I, k) => <span key={k}><I size={15} /></span>)}
              </div>
            </article>
            <article className="lp-card">
              <span className="lp-ico blue"><FileDown size={18} /></span><h3>Redlines your lawyer can open</h3>
              <p>Export any contract to Word with every change as a real tracked change and a comment explaining why.</p>
              <div className="lp-docx"><span>contract_redline.docx</span><b>4 tracked changes · 4 comments</b></div>
            </article>
            <article className="lp-card">
              <span className="lp-ico teal"><Workflow size={18} /></span><h3>Your data stays yours</h3>
              <p>Run fully offline, on a private local model, or with Claude. Switch with one setting.</p>
              <div className="lp-models"><span data-on="true">Offline</span><span>Local model</span><span>Claude</span></div>
            </article>
          </div>
        </div>
      </section>

      <section className="lp-proof" id="proof">
        <div className="lp-wrap">
          <div className="lp-head lp-head--light">
            <span className="lp-kicker">Proven on real contracts</span>
            <h2>Tested on 7,084 clauses from 475 real commercial contracts</h2>
          </div>
          <div className="lp-stats">
            <div><b>86%</b><span>of deal-breaker clauses caught in contracts the model never saw</span></div>
            <div><b>0</b><span>risky clauses signed without review in 200 simulated deals</span></div>
            <div><b>5.7×</b><span>better at spotting risky clauses than hand-written rules (F1 0.74 vs 0.13)</span></div>
            <div><b>+8 pts</b><span>more of the deal value captured when pricing uses past deals</span></div>
          </div>
          <p className="lp-proof__note">Measured on the public CUAD v1 dataset with a locked test set of 99 unseen contracts.</p>
        </div>
      </section>

      <section className="lp-section" id="how">
        <div className="lp-wrap">
          <div className="lp-head"><span className="lp-kicker">How it works</span><h2>Upload in the morning, signed by the afternoon</h2></div>
          <ol className="lp-steps">
            {[
              [FileSearch, "Upload", "Drop in a PDF or Word contract and pick the customer."],
              [ShieldCheck, "Review", "Risky clauses are flagged, safe fixes are redlined for you."],
              [TrendingUp, "Negotiate", "Agents trade offers by e-mail until the numbers meet."],
              [FileSignature, "Sign", "Approved terms go out for signature with a sealed audit trail."],
            ].map(([I, t, d], k) => {
              const Icon = I as typeof FileSearch;
              return <li key={k}><span className="lp-steps__n"><Icon size={18} /></span><b>{t as string}</b><p>{d as string}</p></li>;
            })}
          </ol>
        </div>
      </section>

      <section className="lp-section lp-section--tint" id="pricing">
        <div className="lp-wrap">
          <div className="lp-head lp-head--center"><span className="lp-kicker">Pricing</span><h2>Start free, upgrade when your team does</h2></div>
          <div className="lp-plans">
            {PLANS.map((p) => (
              <div key={p.name} className="lp-plan" data-popular={!!p.popular}>
                {p.popular && <span className="lp-plan__tag">Most popular</span>}
                <b className="lp-plan__name">{p.name}</b>
                <div className="lp-plan__price"><span>{p.price}</span><small>{p.per}</small></div>
                <p>{p.blurb}</p>
                <Link to={status?.signup_enabled ? "/signup" : "/signin"} className={`lp-btn ${p.popular ? "lp-btn--grad" : "lp-btn--outline"}`}>{p.cta}</Link>
                <ul>{p.features.map((f) => <li key={f}><Check size={15} />{f}</li>)}</ul>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="lp-final">
        <div className="lp-gradient lp-gradient--final" aria-hidden><span /><span /><span /><span /></div>
        <div className="lp-wrap lp-final__in">
          <h2>Stop losing weeks to contract back-and-forth</h2>
          <p>Watch an agent negotiate a real contract in under a minute.</p>
          {canDemo
            ? <button type="button" className="lp-btn lp-btn--dark lp-btn--lg" onClick={demo.start} disabled={demo.busy}>Try the demo, no sign-up<ArrowRight size={18} /></button>
            : <Link to={status?.signup_enabled ? "/signup" : "/signin"} className="lp-btn lp-btn--dark lp-btn--lg">Start free<ArrowRight size={18} /></Link>}
        </div>
      </section>

      <footer className="lp-foot">
        <div className="lp-wrap lp-foot__in">
          <Link to="/" className="lp-brand"><Logo size={24} /><b>CoNexus</b></Link>
          <nav aria-label="Footer"><a href="#product">Product</a><a href="#pricing">Pricing</a><Link to="/signin">Sign in</Link></nav>
          <span>© 2026 CoNexus. Risk results measured on CUAD v1 (CC BY 4.0).</span>
        </div>
      </footer>
    </div>
  );
}
