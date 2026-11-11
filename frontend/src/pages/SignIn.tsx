/* Account screens: sign in, create account, confirm e-mail, forgot / reset password.
   All share one gradient layout so the flow feels like one product. */
import { FormEvent, ReactNode, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ArrowLeft, KeyRound, LogIn, MailCheck, ShieldAlert, ShieldCheck, UserPlus } from "lucide-react";
import { Alert, Button, Field, Input, Logo, RedlineDiff, Skeleton, Spinner } from "@ui";
import { api, ApiError, AuthStatus, User } from "@lib/api";

type Props = { status: AuthStatus | null; onSignedIn: (u: User) => void; error?: string | null };
type LinkResult = { ok: boolean; email_sent: boolean; dev_link?: string };

/* ------------------------------------------------------------------ shared layout */
function AuthLayout({ children }: { children: ReactNode }) {
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
      <section className="nx-auth__form">{children}</section>
    </div>
  );
}

function Heading({ title, sub }: { title: string; sub?: ReactNode }) {
  return <div><h2>{title}</h2>{sub && <p className="nx-secondary" style={{ marginTop: 6 }}>{sub}</p>}</div>;
}

/** "Check your inbox" panel. In local development without SMTP it shows the link itself. */
function Sent({ email, result, what }: { email: string; result: LinkResult; what: string }) {
  return (
    <div className="nx-auth__card">
      <span className="nx-auth__mailicon"><MailCheck size={26} /></span>
      <Heading title="Check your inbox" sub={<>We sent {what} to <b>{email}</b>. It can take a minute; check spam too.</>} />
      {result.dev_link && (
        <Alert tone="warning" title="Developer mode: e-mail is not set up on this server">
          No message was sent. <a href={result.dev_link}>Open the link directly</a>.
        </Alert>
      )}
      <Link to="/signin" className="nx-auth__back"><ArrowLeft size={15} />Back to sign in</Link>
    </div>
  );
}

/* ------------------------------------------------------------------ sign in */
export default function SignIn({ status, onSignedIn, error }: Props) {
  const setup = status?.setup_required ?? false;
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [unverified, setUnverified] = useState(false);
  const [resent, setResent] = useState<LinkResult | null>(null);
  const navigate = useNavigate();

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setMsg(null); setUnverified(false);
    try {
      const u = setup ? await api.setup({ email, name, password }) : await api.login(email, password);
      navigate("/", { replace: true });
      onSignedIn(u);
    } catch (err) {
      const ae = err as ApiError;
      setMsg(ae.message);
      setUnverified(ae.status === 403);
    } finally {
      setBusy(false);
    }
  }

  if (resent) return <AuthLayout><Sent email={email} result={resent} what="a new confirmation link" /></AuthLayout>;

  return (
    <AuthLayout>
      {!status && !error ? <div className="nx-auth__card"><Skeleton height={280} /></div> : (
        <form className="nx-auth__card" onSubmit={submit}>
          <Heading title={setup ? "Create the first admin" : "Welcome back"}
            sub={setup ? "No accounts exist yet. This one gets full access; add your team from Settings afterwards." : "Sign in to your CoNexus workspace."} />
          {error && <Alert tone="critical" title="Can't reach CoNexus">{error}</Alert>}
          {msg && (
            <Alert tone={unverified ? "warning" : "critical"} actions={unverified && (
              <Button size="sm" onClick={async () => setResent(await api.resendVerification(email))}>Send a new link</Button>
            )}>{msg}</Alert>
          )}
          {setup && <Field label="Full name" htmlFor="name"><Input id="name" required autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} /></Field>}
          <Field label="Work e-mail" htmlFor="email"><Input id="email" type="email" required autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" /></Field>
          <Field label="Password" htmlFor="password" hint={setup ? "At least 10 characters" : undefined}>
            <Input id="password" type="password" required autoComplete={setup ? "new-password" : "current-password"} minLength={setup ? 10 : undefined}
              value={password} onChange={(e) => setPassword(e.target.value)} />
          </Field>
          {!setup && <Link to="/forgot" className="nx-auth__forgot">Forgot password?</Link>}
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
          {!setup && status?.signup_enabled && (
            <p className="nx-auth__switch">New to CoNexus? <Link to="/signup">Create an account</Link></p>
          )}
        </form>
      )}
    </AuthLayout>
  );
}

/* ------------------------------------------------------------------ create account */
export function SignUp({ status }: Props) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [done, setDone] = useState<LinkResult | null>(null);
  const strength = password.length === 0 ? 0 : password.length < 10 ? 1 : password.length < 14 ? 2 : 3;

  if (status && !status.signup_enabled) {
    return <AuthLayout><div className="nx-auth__card"><Heading title="Sign-up is closed" sub="Ask your administrator to add you to the workspace." />
      <Link to="/signin" className="nx-auth__back"><ArrowLeft size={15} />Back to sign in</Link></div></AuthLayout>;
  }
  if (done) return <AuthLayout><Sent email={email} result={done} what="a confirmation link" /></AuthLayout>;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setMsg(null);
    try { setDone(await api.signup({ name, email, password })); }
    catch (err) { setMsg((err as ApiError).message); }
    finally { setBusy(false); }
  }

  return (
    <AuthLayout>
      <form className="nx-auth__card" onSubmit={submit}>
        <Heading title="Create your account" sub="Start negotiating contracts with AI agents. Free while you try it." />
        {msg && <Alert tone="critical">{msg}</Alert>}
        <Field label="Full name" htmlFor="su-name"><Input id="su-name" required autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Taniya Sumbul" /></Field>
        <Field label="Work e-mail" htmlFor="su-email"><Input id="su-email" type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" /></Field>
        <Field label="Password" htmlFor="su-pw" hint="At least 10 characters">
          <Input id="su-pw" type="password" required minLength={10} autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
        <div className="nx-auth__strength" data-level={strength} aria-hidden><i /><i /><i /></div>
        <Button type="submit" variant="primary" size="lg" block loading={busy} icon={<UserPlus size={18} />}>Create account</Button>
        <p className="nx-auth__switch">Already have an account? <Link to="/signin">Sign in</Link></p>
        <p className="nx-muted" style={{ fontSize: "var(--text-xs)" }}>New accounts start with the Sales role. An admin can give you Legal or Admin access.</p>
      </form>
    </AuthLayout>
  );
}

/* ------------------------------------------------------------------ confirm e-mail (from the link) */
export function VerifyEmail({ onSignedIn }: Props) {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [err, setErr] = useState<string | null>(null);
  const once = useRef(false);
  useEffect(() => {
    if (once.current) return;  // tokens are single-use; StrictMode would call this twice
    once.current = true;
    const token = params.get("token") ?? "";
    api.verifyEmail(token).then((u) => { navigate("/", { replace: true }); onSignedIn(u); }).catch((e) => setErr((e as ApiError).message));
  }, [params, navigate, onSignedIn]);
  return (
    <AuthLayout>
      <div className="nx-auth__card">
        {err ? (
          <>
            <Heading title="That link didn't work" />
            <Alert tone="critical">{err}</Alert>
            <Link to="/signin" className="nx-auth__back"><ArrowLeft size={15} />Back to sign in</Link>
          </>
        ) : <div className="nx-row" style={{ gap: 12 }}><Spinner /><b>Confirming your e-mail…</b></div>}
      </div>
    </AuthLayout>
  );
}

/* ------------------------------------------------------------------ forgot password */
export function ForgotPassword(_: Props) {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<LinkResult | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  if (done) return <AuthLayout><Sent email={email} result={done} what="a password reset link, if an account exists for that address," /></AuthLayout>;
  return (
    <AuthLayout>
      <form className="nx-auth__card" onSubmit={async (e) => {
        e.preventDefault(); setBusy(true); setMsg(null);
        try { setDone(await api.forgot(email)); } catch (err) { setMsg((err as ApiError).message); } finally { setBusy(false); }
      }}>
        <Heading title="Reset your password" sub="Enter the e-mail you sign in with and we'll send you a link." />
        {msg && <Alert tone="critical">{msg}</Alert>}
        <Field label="Work e-mail" htmlFor="fp-email"><Input id="fp-email" type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
        <Button type="submit" variant="primary" size="lg" block loading={busy} icon={<KeyRound size={18} />}>Send reset link</Button>
        <Link to="/signin" className="nx-auth__back"><ArrowLeft size={15} />Back to sign in</Link>
      </form>
    </AuthLayout>
  );
}

/* ------------------------------------------------------------------ choose a new password (from the link) */
export function ResetPassword({ onSignedIn }: Props) {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  return (
    <AuthLayout>
      <form className="nx-auth__card" onSubmit={async (e) => {
        e.preventDefault();
        if (password !== confirm) { setMsg("The two passwords don't match"); return; }
        setBusy(true); setMsg(null);
        try { const u = await api.reset(params.get("token") ?? "", password); navigate("/", { replace: true }); onSignedIn(u); }
        catch (err) { setMsg((err as ApiError).message); } finally { setBusy(false); }
      }}>
        <Heading title="Choose a new password" sub="You'll be signed in straight away. Other devices are signed out." />
        {msg && <Alert tone="critical">{msg}</Alert>}
        <Field label="New password" htmlFor="rp-pw" hint="At least 10 characters"><Input id="rp-pw" type="password" required minLength={10} autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} /></Field>
        <Field label="Repeat it" htmlFor="rp-pw2"><Input id="rp-pw2" type="password" required minLength={10} autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} /></Field>
        <Button type="submit" variant="primary" size="lg" block loading={busy} icon={<KeyRound size={18} />}>Save and sign in</Button>
      </form>
    </AuthLayout>
  );
}
