import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { LogIn, ShieldAlert, ShieldCheck } from "lucide-react";
import { Alert, Button, Field, Input, Logo, RedlineDiff, Skeleton } from "@ui";
import { api, ApiError, AuthStatus, User } from "@lib/api";

export default function SignIn({ status, onSignedIn, error }: { status: AuthStatus | null; onSignedIn: (u: User) => void; error: string | null }) {
  const setup = status?.setup_required ?? false;
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const navigate = useNavigate();

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    try {
      const u = setup ? await api.setup({ email, name, password }) : await api.login(email, password);
      navigate("/", { replace: true });
      onSignedIn(u);
    } catch (err) {
      setMsg((err as ApiError).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="nx-auth">
      <div className="nx-grad" aria-hidden><span /><span /><span /><span /></div>
      <section className="nx-auth__brand" aria-label="About CoNexus">
        <Link to="/" className="nx-brand" title="Back to the website"><Logo size={36} /><b>CoNexus</b></Link>
        <div className="nx-auth__pitch">
          <h1>Agents negotiate<br />People decide the risk</h1>
          <p>Upload a customer contract. CoNexus redlines it, negotiates the price from your deal history, and hands anything risky to Legal.</p>
        </div>
        <div className="nx-auth__preview" aria-hidden>
          <div className="nx-auth__float nx-card">
            <div className="nx-row" style={{ justifyContent: "space-between" }}>
              <span className="nx-mono nx-muted">§ 6 Limitation of Liability</span>
              <span className="nx-badge nx-badge--critical"><ShieldAlert size={13} />Escalated to Legal</span>
            </div>
            <RedlineDiff original="Vendor's liability shall be unlimited." proposed="Each party's liability is capped at 12 months' fees." label="Proposed redline" />
          </div>
          <div className="nx-auth__chips">
            <span className="nx-card"><b>0</b> risky clauses signed unreviewed</span>
            <span className="nx-card"><b>86%</b> deal-breakers caught in unseen contracts</span>
          </div>
        </div>
      </section>

      <section className="nx-auth__form">
        {!status && !error ? <div className="nx-auth__card"><Skeleton height={280} /></div> : (
          <form className="nx-auth__card" onSubmit={submit}>
            <div>
              <h2>{setup ? "Create the first admin" : "Sign in"}</h2>
              <p className="nx-secondary" style={{ marginTop: 6 }}>
                {setup ? "No accounts exist yet. This one gets full access; add your team from Settings afterwards." : "Use the account your administrator created for you."}
              </p>
            </div>
            {error && <Alert tone="critical" title="Can't reach CoNexus">{error}</Alert>}
            {msg && <Alert tone="critical">{msg}</Alert>}
            {setup && (
              <Field label="Full name" htmlFor="name"><Input id="name" required autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} /></Field>
            )}
            <Field label="Work e-mail" htmlFor="email"><Input id="email" type="email" required autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" /></Field>
            <Field label="Password" htmlFor="password" hint={setup ? "At least 10 characters" : undefined}>
              <Input id="password" type="password" required autoComplete={setup ? "new-password" : "current-password"} minLength={setup ? 10 : undefined}
                value={password} onChange={(e) => setPassword(e.target.value)} />
            </Field>
            <Button type="submit" variant="primary" size="lg" block loading={busy} icon={setup ? <ShieldCheck size={18} /> : <LogIn size={18} />}>
              {setup ? "Create admin and continue" : "Sign in"}
            </Button>
            {!setup && status?.demo_enabled && (
              <Button type="button" variant="secondary" size="lg" block disabled={busy} onClick={async () => {
                setBusy(true);
                try { const u = await api.demo(); navigate("/", { replace: true }); onSignedIn(u); }
                catch (err) { setMsg((err as ApiError).message); } finally { setBusy(false); }
              }}>Explore the demo, no account needed</Button>
            )}
            <p className="nx-muted" style={{ fontSize: "var(--text-xs)" }}>
              Roles: <b>Sales</b> creates and negotiates contracts · <b>Legal</b> also approves escalations and labels clauses · <b>Admin</b> also sets policy and manages users.
            </p>
          </form>
        )}
      </section>
    </div>
  );
}
