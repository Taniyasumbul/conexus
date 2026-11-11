"""CoNexus REST API.

    POST /api/contracts                      upload + analyze (Analyst + Risk agents)
    GET  /api/contracts                      list
    GET  /api/contracts/{id}                 full negotiation state
    POST /api/contracts/{id}/negotiate       start (simulated counterparty or e-mail)
    POST /api/contracts/{id}/reply           inbound counterparty reply (e-mail webhook)
    POST /api/contracts/{id}/decision        human reviewer approves / rejects an escalation
    GET  /api/escalations                    human review inbox
    GET  /api/contracts/{id}/audit           decision trail for one contract
    GET  /api/audit/verify                   verify the global hash chain
    GET  /api/metrics                        portfolio KPIs
    GET  /api/samples                        bundled demo contracts + scenarios
    GET  /api/eval                           latest evaluation results

Interactive docs: http://localhost:8000/docs
"""
from __future__ import annotations

import json
import os
import secrets
import tempfile
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Literal

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, Header, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from ..agents.audit import AuditAgent
from ..agents.risk import RiskClassifier
from ..config import DATA, RUNS, EscalationPolicyConfig, PricingPolicyConfig, Settings, get_settings
from ..integrations.channels import Channel, ConsoleChannel, EmailChannel, SlackChannel
from ..integrations import mailer
from ..integrations.redline_docx import build_redline_docx
from ..llm import build_llm
from ..models import DealContext, HumanDecision, NegotiationState, Terms
from ..orchestrator import Orchestrator
from ..parsing import read_document
from ..sim.counterparty import PERSONAS, RuleCounterparty
from ..sim.world import LIST_PER_SEAT
from ..store import Store
from .annotation import AnnotationService
from .auth import (COOKIE, ROLES, SESSION_TTL, check_password_strength, current_user, hash_password, new_session,
                   public_user, require, seed_admin_from_env, token_hash, verify_password)


class NegotiateRequest(BaseModel):
    mode: Literal["simulated", "email"] = "simulated"
    persona: Literal["cooperative", "hardball", "deadline"] = "cooperative"
    wtp: float | None = Field(None, description="Simulated buyer's private max annual price (simulated mode)")
    delay_s: float = Field(1.0, ge=0, le=30, description="Pause between simulated rounds, for live demos")
    counterparty_email: str | None = None


class ReplyRequest(BaseModel):
    message: str


class AnnotationRequest(BaseModel):
    clause_id: str
    requires_human: bool | None = Field(None, description="null = unsure / skip")
    level: Literal["low", "medium", "high"] | None = None
    redlinable: bool | None = None
    note: str = Field("", max_length=1000)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=1, max_length=200)


class SetupRequest(LoginRequest):
    name: str = Field(min_length=1, max_length=80)


class ReadRequest(BaseModel):
    ids: list[int] = []
    all: bool = False


class EmailRequest(BaseModel):
    email: str = Field(min_length=3, max_length=200)


class TokenRequest(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class ResetRequest(TokenRequest):
    password: str = Field(min_length=1, max_length=200)


class UserCreate(SetupRequest):
    role: Literal["sales", "legal", "admin"]


class UserUpdate(BaseModel):
    name: str | None = Field(None, max_length=80)
    role: Literal["sales", "legal", "admin"] | None = None
    active: bool | None = None
    password: str | None = Field(None, max_length=200)


class PolicyUpdate(BaseModel):
    escalation: dict = {}
    pricing: dict = {}


class DecisionRequest(BaseModel):
    approve: bool
    note: str = Field("", max_length=1000)


def apply_policy(s: Settings, escalation: dict, pricing: dict) -> tuple[dict, dict]:
    """Validate the merged policy, then update the live config objects in place (the agents hold
    references to them, so the change takes effect immediately). Returns (before, after) diffs."""
    esc = EscalationPolicyConfig(**{**s.escalation.model_dump(), **escalation})
    pri = PricingPolicyConfig(**{**s.pricing.model_dump(), **pricing})
    before, after = {}, {}
    for section, live, new in (("escalation", s.escalation, esc), ("pricing", s.pricing, pri)):
        for k, v in new.model_dump().items():
            if getattr(live, k) != v:
                before[f"{section}.{k}"], after[f"{section}.{k}"] = getattr(live, k), v
                setattr(live, k, v)
    return before, after


def _policy_schema(model) -> list[dict]:
    out = []
    for name, f in model.model_fields.items():
        meta = {"name": name, "description": f.description, "default": f.default}
        for m in f.metadata:
            for attr in ("ge", "le"):
                if getattr(m, attr, None) is not None:
                    meta[attr] = getattr(m, attr)
        ann = f.annotation
        meta["type"] = "bool" if ann is bool else "int" if ann is int else "float" if ann is float else "choice"
        if meta["type"] == "choice":
            meta["choices"] = list(getattr(ann, "__args__", []))
        out.append(meta)
    return out


class RecordingChannel(Channel):
    """Wraps a channel and records the last message (useful for the UI and tests)."""

    def __init__(self, inner: Channel):
        self.inner = inner
        self.sent: list[dict] = []

    def send(self, to, subject, body):
        self.sent.append({"to": to, "subject": subject, "body": body, "ts": time.time()})
        self.inner.send(to, subject, body)


def _escalation_channel() -> Channel:
    if os.getenv("SLACK_WEBHOOK_URL"):
        return RecordingChannel(SlackChannel())
    return RecordingChannel(ConsoleChannel(quiet=True))


def _email_channel() -> Channel:
    if os.getenv("SMTP_HOST"):
        return RecordingChannel(EmailChannel())
    return RecordingChannel(ConsoleChannel(quiet=True))


def create_app(settings: Settings | None = None, db_path: Path | None = None, audit_path: Path | None = None,
               labels_export: Path | None = None) -> FastAPI:
    s = (settings or get_settings()).model_copy(deep=True)
    # DATABASE_URL (Postgres) keeps data across restarts on hosts with ephemeral disks, e.g. Render free
    database_url = os.getenv("DATABASE_URL") if db_path is None else None
    store = Store(db_path or RUNS / "conexus.db", url=database_url)
    seed_admin_from_env(store)
    saved_policy = store.kv_get("policy")
    if saved_policy:
        p = json.loads(saved_policy)
        apply_policy(s, p.get("escalation", {}), p.get("pricing", {}))
    audit = AuditAgent(sink=store) if store.backend == "postgres" else AuditAgent(audit_path or RUNS / "audit.jsonl")
    llm = build_llm(s)
    escalations = _escalation_channel()
    clf = RiskClassifier.default(s)
    common = dict(audit=audit, escalations=escalations, out_dir=RUNS, learn=True, classifier=clf)
    # one orchestrator per outbound channel; they share audit log and CRM memory
    sim_orch = Orchestrator(s, llm, outbound=RecordingChannel(ConsoleChannel(quiet=True)), **common)
    email_orch = Orchestrator(s, llm, outbound=_email_channel(), crm=sim_orch.crm, **common)
    locks: dict[str, threading.Lock] = defaultdict(threading.Lock)
    annotations = AnnotationService(s, store, sim_orch.risk, **({"export_path": labels_export} if labels_export else {}))

    app = FastAPI(title="CoNexus API", version="0.2.0",
                  description="Risk-aware, memory-augmented multi-agent B2B contract negotiation")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    app.state.store, app.state.audit = store, audit

    def orch_for(cid: str) -> Orchestrator:
        row = store.row(cid)
        return email_orch if row and row["mode"] == "email" else sim_orch

    def load(cid: str) -> NegotiationState:
        st = store.state(cid)
        if st is None:
            raise HTTPException(404, f"contract {cid} not found")
        return st

    def view(st: NegotiationState) -> dict:
        row = store.row(st.contract_id)
        return {"id": st.contract_id, "mode": row["mode"], "filename": row["filename"], "created_at": row["created_at"],
                "updated_at": row["updated_at"], **st.model_dump(mode="json")}

    def drive(cid: str) -> None:
        """Background job: play the simulated counterparty until a human is needed or the deal ends."""
        with locks[cid]:
            st, cp, row = store.state(cid), store.sim(cid), store.row(cid)
            if cp is None:
                return
            while st.status == "awaiting_reply":
                time.sleep(row["sim_delay"] or 0)
                reply = cp.respond(st.round, st.last_our_offer, st.last_sent_redlines)
                st = sim_orch.on_reply(st, reply)
                store.save(st, sim=cp)

    # ------------------------------------------------------------------ routes
    sales, legal, admin = require("sales"), require("legal"), require("admin")

    # ------------------------------------------------------------------ notifications on stage changes
    COVER = {"sales": ("sales",), "legal": ("sales", "legal"), "admin": ("sales", "legal", "admin")}
    _raw_save = store.save

    def _money(v: float) -> str:
        return f"${v:,.0f}"

    def save_and_notify(st: NegotiationState, **kw) -> None:
        prev = store.row(st.contract_id)
        prev_status = prev["status"] if prev else None
        _raw_save(st, **kw)
        if prev_status == st.status:
            return
        who, link = st.context.customer, f"/contracts/{st.contract_id}"
        if st.status == "awaiting_human" and st.escalation:
            store.notify("escalation", f"{who} needs a decision", st.escalation.triggers[0] if st.escalation.triggers else st.escalation.kind,
                         link, role="legal")
        elif st.status == "signed" and st.outcome and st.outcome.final_terms:
            t = st.outcome.final_terms
            store.notify("signed", f"Deal signed with {who}", f"{_money(t.price)}/yr · net {t.payment_days} · {st.outcome.rounds} rounds", link)
        elif st.status == "closed" and st.outcome:
            label = {"rejected_by_human": "rejected by Legal", "walked_away": "customer walked away",
                     "no_agreement": "no agreement", "handed_off": "handed to a person"}.get(st.outcome.status, st.outcome.status)
            store.notify("closed", f"{who}: {label}", f"Closed after {st.outcome.rounds} rounds", link)
        elif prev_status == "awaiting_human" and st.status == "awaiting_reply" and st.human_decisions:
            d = st.human_decisions[-1]
            store.notify("approved", f"{d.reviewer} approved {who}", d.note or "The agents resumed the negotiation", link)

    store.save = save_and_notify  # every state change goes through here
    DEMO_EMAIL = "demo@conexus.local"
    demo_enabled = os.getenv("CONEXUS_DEMO", "0").lower() in ("1", "true", "yes")

    def real_users() -> int:
        return store.user_count() - (1 if store.user_by_email(DEMO_EMAIL) else 0)

    def seed_demo_contracts() -> None:
        """Give an empty workspace something to look at: a few sample deals in different states."""
        if store.all():
            return
        rows = {json.loads(l)["contract_id"]: json.loads(l) for l in (DATA / "labels" / "contracts.jsonl").read_text().splitlines()}
        plan = ["contract_000", "contract_010", "contract_016", "contract_022", "contract_005", "contract_040"]
        for k, sid in enumerate(plan):
            r = rows.get(sid)
            if not r:
                continue
            ctx = DealContext(**r["context"])
            cid = f"CNX-DEMO-{k + 1:02d}"
            st = sim_orch.analyze(cid, (DATA / "contracts" / f"{sid}.txt").read_text(), ctx)
            store.create(st, (DATA / "contracts" / f"{sid}.txt").read_text(), f"{sid}.txt")
            if sid == plan[-1]:
                continue  # leave one contract analyzed, ready to negotiate
            h = r["hidden"]
            cp = RuleCounterparty(h["wtp"], st.opening_terms or Terms(price=ctx.list_price * 0.6), h["persona"], seed=k)
            store.save(st, sim=cp, mode="simulated", sim_delay=0)
            st = sim_orch.drive(sim_orch.start(st), cp)
            store.save(st, sim=cp)

    @app.get("/health")
    def health():
        return {"ok": True, "llm": llm.name if llm else "offline"}

    # ------------------------------------------------------------------ auth
    def _login(response: Response, request: Request, uid: int) -> None:
        response.set_cookie(COOKIE, new_session(store, uid), max_age=SESSION_TTL, httponly=True, samesite="lax",
                            secure=request.url.scheme == "https", path="/")

    @app.get("/api/auth/status")
    def auth_status(request: Request):
        try:
            user = current_user(request)
        except HTTPException:
            user = None
        return {"setup_required": real_users() == 0, "user": user, "demo_enabled": demo_enabled,
                "signup_enabled": signup_enabled and real_users() > 0}

    @app.post("/api/auth/setup")
    def auth_setup(req: SetupRequest, request: Request, response: Response):
        """One-time: create the first admin. Disabled as soon as any user exists."""
        if real_users() > 0:
            raise HTTPException(409, "Setup is already complete. Sign in instead.")
        check_password_strength(req.password)
        uid = store.create_user(req.email, req.name, "admin", hash_password(req.password))
        audit.log("auth", "USER_CREATED", f"first admin {req.email} created via setup", {"role": "admin"})
        _login(response, request, uid)
        return public_user(store.user_by_id(uid))

    # ------------------------------------------------------------------ sign up, verify, reset
    signup_enabled = os.getenv("CONEXUS_SIGNUP", "1").lower() in ("1", "true", "yes")
    VERIFY_TTL, RESET_TTL = 24 * 3600, 30 * 60

    def _public_url(request: Request) -> str:
        return (os.getenv("CONEXUS_PUBLIC_URL") or str(request.base_url)).rstrip("/")

    def _send_link(request: Request, uid: int, email: str, name: str, purpose: str) -> dict:
        token = secrets.token_urlsafe(32)
        store.create_email_token(token_hash(token), uid, purpose, time.time() + (VERIFY_TTL if purpose == "verify" else RESET_TTL))
        page = "verify" if purpose == "verify" else "reset"
        link = f"{_public_url(request)}/{page}?token={token}"
        if purpose == "verify":
            sent = mailer.send(email, "Confirm your CoNexus e-mail", f"Welcome, {name.split(' ')[0]}",
                               "Confirm your e-mail address to finish creating your CoNexus account.",
                               "Confirm e-mail", link, "The link works once and expires in 24 hours. If you did not sign up, ignore this e-mail.")
        else:
            sent = mailer.send(email, "Reset your CoNexus password", "Reset your password",
                               "Someone asked to reset the password for this CoNexus account. Choose a new one with the button below.",
                               "Choose a new password", link, "The link works once and expires in 30 minutes. If it was not you, ignore this e-mail.")
        out: dict = {"ok": True, "email_sent": sent}
        if not sent and mailer.dev_links_enabled():
            out["dev_link"] = link  # local development only: no SMTP configured
        return out

    @app.post("/api/auth/signup", status_code=201)
    def auth_signup(req: SetupRequest, request: Request):
        if not signup_enabled:
            raise HTTPException(404, "Sign-up is turned off on this server. Ask an admin for an account.")
        if real_users() == 0:
            raise HTTPException(409, "This workspace has no admin yet. Use the setup screen first.")
        if "@" not in req.email or "." not in req.email.split("@")[-1]:
            raise HTTPException(422, "Enter a valid e-mail address")
        existing = store.user_by_email(req.email)
        if existing and existing["email_verified"]:
            raise HTTPException(409, "An account with this e-mail already exists. Sign in or reset your password.")
        check_password_strength(req.password)
        if existing:  # signed up before but never verified: refresh details and resend
            store.update_user(existing["id"], name=req.name, password_hash=hash_password(req.password))
            uid = existing["id"]
        else:
            uid = store.create_user(req.email, req.name, "sales", hash_password(req.password), verified=False)
            audit.log("auth", "USER_SIGNUP", f"{req.email} signed up (sales, unverified)", {"role": "sales"})
        return _send_link(request, uid, req.email.strip().lower(), req.name, "verify")

    @app.post("/api/auth/verify")
    def auth_verify(req: TokenRequest, request: Request, response: Response):
        u = store.consume_email_token(token_hash(req.token), "verify")
        if not u:
            raise HTTPException(400, "This link is invalid or has expired. Request a new one from the sign-in page.")
        store.set_verified(u["id"])
        audit.log("auth", "EMAIL_VERIFIED", f"{u['email']} verified their e-mail")
        _login(response, request, u["id"])
        return public_user(store.user_by_id(u["id"]))

    @app.post("/api/auth/resend-verification")
    def auth_resend(req: EmailRequest, request: Request):
        u = store.user_by_email(req.email)
        if u and u["active"] and not u["email_verified"]:
            return _send_link(request, u["id"], u["email"], u["name"], "verify")
        return {"ok": True, "email_sent": False}  # same answer either way: no account enumeration

    @app.post("/api/auth/forgot")
    def auth_forgot(req: EmailRequest, request: Request):
        u = store.user_by_email(req.email)
        if u and u["active"] and u["email"] != DEMO_EMAIL:
            return _send_link(request, u["id"], u["email"], u["name"], "reset")
        return {"ok": True, "email_sent": False}

    @app.post("/api/auth/reset")
    def auth_reset(req: ResetRequest, request: Request, response: Response):
        check_password_strength(req.password)
        u = store.consume_email_token(token_hash(req.token), "reset")
        if not u:
            raise HTTPException(400, "This link is invalid or has expired. Ask for a new one.")
        store.update_user(u["id"], password_hash=hash_password(req.password))  # also ends other sessions
        store.set_verified(u["id"])  # they proved they own the inbox
        audit.log("auth", "PASSWORD_RESET", f"{u['email']} reset their password")
        _login(response, request, u["id"])
        return public_user(store.user_by_id(u["id"]))

    @app.post("/api/auth/demo")
    def auth_demo(request: Request, response: Response):
        """One-click demo: signs in as a Legal-level demo user (no Settings or user admin)."""
        if not demo_enabled:
            raise HTTPException(404, "The demo is not enabled on this server")
        u = store.user_by_email(DEMO_EMAIL)
        if not u:
            store.create_user(DEMO_EMAIL, "Demo Visitor", "legal", hash_password(secrets.token_urlsafe(24)))
            u = store.user_by_email(DEMO_EMAIL)
            audit.log("auth", "USER_CREATED", "demo visitor account created", {"role": "legal"})
        seed_demo_contracts()
        _login(response, request, u["id"])
        return public_user(u)

    @app.post("/api/auth/login")
    def auth_login(req: LoginRequest, request: Request, response: Response):
        u = store.user_by_email(req.email)
        if not u or not u["active"] or not verify_password(req.password, u["password_hash"]):
            raise HTTPException(401, "Email or password is incorrect")
        if not u["email_verified"]:
            raise HTTPException(403, "Confirm your e-mail first. Use the link we sent when you signed up.")
        _login(response, request, u["id"])
        return public_user(u)

    @app.post("/api/auth/logout")
    def auth_logout(request: Request, response: Response):
        tok = request.cookies.get(COOKIE)
        if tok:
            store.delete_session(token_hash(tok))
        response.delete_cookie(COOKIE, path="/")
        return {"ok": True}

    # ------------------------------------------------------------------ users (admin)
    @app.get("/api/users")
    def list_users(user=Depends(admin)):
        return [dict(u) | {"active": bool(u["active"])} for u in store.users()]

    @app.post("/api/users", status_code=201)
    def create_user(req: UserCreate, user=Depends(admin)):
        if store.user_by_email(req.email):
            raise HTTPException(409, f"{req.email} already has an account")
        check_password_strength(req.password)
        uid = store.create_user(req.email, req.name, req.role, hash_password(req.password))
        audit.log(f"human:{user['email']}", "USER_CREATED", f"{req.email} added as {req.role}", {"role": req.role})
        return public_user(store.user_by_id(uid))

    @app.patch("/api/users/{uid}")
    def update_user(uid: int, req: UserUpdate, user=Depends(admin)):
        target = store.user_by_id(uid)
        if not target:
            raise HTTPException(404, "user not found")
        if uid == user["id"] and (req.role not in (None, "admin") or req.active is False):
            raise HTTPException(409, "You cannot remove your own admin access")
        if req.password:
            check_password_strength(req.password)
        store.update_user(uid, name=req.name, role=req.role, active=None if req.active is None else int(req.active),
                          password_hash=hash_password(req.password) if req.password else None)
        changes = {k: v for k, v in req.model_dump().items() if v is not None and k != "password"} | ({"password": "reset"} if req.password else {})
        audit.log(f"human:{user['email']}", "USER_UPDATED", f"{target['email']}: {changes}", changes)
        return public_user(store.user_by_id(uid)) | {"active": bool(store.user_by_id(uid)["active"])}

    # ------------------------------------------------------------------ policy
    @app.get("/api/policy")
    def get_policy(user=Depends(sales)):
        return {"escalation": s.escalation.model_dump(), "pricing": s.pricing.model_dump(),
                "schema": {"escalation": _policy_schema(EscalationPolicyConfig), "pricing": _policy_schema(PricingPolicyConfig)}}

    @app.put("/api/policy")
    def put_policy(req: PolicyUpdate, user=Depends(admin)):
        try:
            before, after = apply_policy(s, req.escalation, req.pricing)
        except ValueError as e:
            raise HTTPException(422, str(e))
        if after:
            store.kv_set("policy", json.dumps({"escalation": s.escalation.model_dump(), "pricing": s.pricing.model_dump()}))
            audit.log(f"human:{user['email']}", "POLICY_CHANGE",
                      "; ".join(f"{k}: {before[k]} -> {after[k]}" for k in after), {"before": before, "after": after})
        return {"changed": after, **get_policy(user)}

    @app.get("/api/policy/history")
    def policy_history(user=Depends(sales)):
        return [e for e in reversed(audit.events) if e["action"] == "POLICY_CHANGE"][:50]

    @app.post("/api/contracts", status_code=201)
    def create_contract(user=Depends(sales), customer: str = Form(...), segment: str = Form("smb"), region: str = Form("india"),
                        product: str = Form("pro"), seats: int = Form(50), list_price: float | None = Form(None),
                        sample_id: str | None = Form(None), file: UploadFile | None = File(None)):
        if file is None and not sample_id:
            raise HTTPException(400, "upload a file or choose a sample_id")
        if sample_id:
            path = DATA / "contracts" / f"{Path(sample_id).name}.txt"
            if not path.exists():
                raise HTTPException(404, "unknown sample")
            text, filename = path.read_text(), path.name
        else:
            suffix = Path(file.filename or "x.txt").suffix.lower()
            if suffix not in (".pdf", ".docx", ".txt", ".md"):
                raise HTTPException(415, "supported: .pdf .docx .txt .md")
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(file.file.read())
            try:
                text = read_document(tmp.name)
            finally:
                os.unlink(tmp.name)
            filename = file.filename
        try:
            ctx = DealContext(customer=customer, segment=segment, region=region, product=product, seats=seats,
                              list_price=list_price or LIST_PER_SEAT[product] * seats)
        except Exception as e:
            raise HTTPException(422, str(e))
        cid = f"CNX-{time.strftime('%y%m%d')}-{secrets.token_hex(3).upper()}"
        st = sim_orch.analyze(cid, text, ctx)
        store.create(st, text, filename)
        return view(st)

    @app.get("/api/contracts")
    def list_contracts(user=Depends(sales)):
        out = []
        for r in store.all():
            st = NegotiationState.model_validate_json(r["state_json"])
            terms = (st.outcome.final_terms if st.outcome else None) or st.agreed_terms
            out.append({
                "id": r["id"], "customer": r["customer"], "status": r["status"], "mode": r["mode"],
                "segment": st.context.segment, "list_price": st.context.list_price, "round": st.round,
                "outcome": st.outcome.status if st.outcome else None,
                "price": terms.price if terms else None,
                "risky_clauses": sum(x.requires_human and x.clause_id not in st.reviewed_clauses
                                     and not st.redline_results.get(x.clause_id) for x in st.risks),
                "escalation": st.escalation.kind if st.escalation else None,
                "updated_at": r["updated_at"],
            })
        return out

    @app.get("/api/contracts/{cid}")
    def get_contract(cid: str, user=Depends(sales)):
        return view(load(cid))

    @app.post("/api/contracts/{cid}/negotiate")
    def negotiate(cid: str, req: NegotiateRequest, bg: BackgroundTasks, user=Depends(sales)):
        with locks[cid]:
            st = load(cid)
            if st.status != "analyzed":
                raise HTTPException(409, f"already started (status={st.status})")
            opening = st.opening_terms or Terms(price=st.context.list_price * 0.6)
            if req.mode == "simulated":
                cp = RuleCounterparty(req.wtp or st.context.list_price * 0.8, opening, req.persona,
                                      seed=int.from_bytes(cid.encode(), "little") % 10_000)
                store.save(st, sim=cp, mode="simulated", sim_delay=req.delay_s)
                st = sim_orch.start(st)
                store.save(st, sim=cp)
                bg.add_task(drive, cid)
            else:
                store.save(st, mode="email")
                st = email_orch.start(st)
                store.save(st)
        return view(st)

    @app.post("/api/contracts/{cid}/reply")
    def reply(cid: str, req: ReplyRequest, request: Request, x_conexus_webhook_token: str | None = Header(None)):
        """Inbound e-mail webhook (e.g. SendGrid / Mailgun inbound parse, authenticated with the
        X-Conexus-Webhook-Token header = CONEXUS_WEBHOOK_TOKEN) or manual paste from the UI (session)."""
        expected = os.getenv("CONEXUS_WEBHOOK_TOKEN")
        if not (expected and x_conexus_webhook_token and secrets.compare_digest(expected, x_conexus_webhook_token)):
            sales(request)
        with locks[cid]:
            st = load(cid)
            if store.row(cid)["mode"] != "email":
                raise HTTPException(409, "replies are only accepted for e-mail mode negotiations")
            try:
                st = email_orch.on_reply(st, req.message)
            except ValueError as e:
                raise HTTPException(409, str(e))
            store.save(st)
        return view(st)

    @app.post("/api/contracts/{cid}/decision")
    def decision(cid: str, req: DecisionRequest, bg: BackgroundTasks, user=Depends(legal)):
        d = HumanDecision(approve=req.approve, reviewer=user["email"], note=req.note)
        with locks[cid]:
            st = load(cid)
            try:
                st = orch_for(cid).resolve(st, d)
            except ValueError as e:
                raise HTTPException(409, str(e))
            store.save(st)
        if st.status == "awaiting_reply" and store.row(cid)["mode"] == "simulated":
            bg.add_task(drive, cid)
        return view(st)

    @app.get("/api/contracts/{cid}/document")
    def contract_document(cid: str, user=Depends(sales)):
        """The original text with character offsets for every clause, for the marked-up document view."""
        st = load(cid)
        text = store.row(cid)["text"]
        segments, pos = [], 0
        for c in st.clauses:
            head_at = text.find(c.heading.split(" ", 1)[-1], pos) if c.heading else -1
            body_at = text.find(c.text[:60], max(pos, head_at if head_at >= 0 else pos))
            if body_at < 0:
                continue
            start = head_at if 0 <= head_at < body_at else body_at
            # the heading line starts at the beginning of its line (include the clause number)
            line_start = text.rfind("\n", 0, start) + 1
            end = body_at + len(c.text)
            segments.append({"clause_id": c.id, "start": line_start, "body_start": body_at, "end": end})
            pos = end
        return {"text": text, "segments": segments}

    @app.get("/api/contracts/{cid}/redline.docx")
    def redline_docx(cid: str, user=Depends(sales)):
        st = load(cid)
        blob = build_redline_docx(st, user["name"], audit.head)
        audit.log(f"human:{user['email']}", "REDLINE_EXPORT", "redlined Word document exported", contract_id=cid)
        safe = "".join(ch for ch in st.context.customer if ch.isalnum() or ch in " -_").strip().replace(" ", "_") or "contract"
        return Response(blob, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        headers={"Content-Disposition": f'attachment; filename="{safe}_{cid}_redline.docx"'})

    @app.get("/api/escalations")
    def escalations_inbox(user=Depends(sales)):
        out = []
        for r in store.all():
            if r["status"] != "awaiting_human":
                continue
            st = NegotiationState.model_validate_json(r["state_json"])
            out.append({"id": r["id"], "customer": r["customer"], "escalation": st.escalation.model_dump() if st.escalation else None,
                        "terms": (st.agreed_terms or st.last_our_offer).model_dump() if (st.agreed_terms or st.last_our_offer) else None,
                        "flagged": [x.model_dump(mode="json") for x in st.risks if x.requires_human and x.clause_id not in st.reviewed_clauses],
                        "clauses": {c.id: c.text for c in st.clauses}, "updated_at": r["updated_at"]})
        return out

    @app.get("/api/contracts/{cid}/audit")
    def contract_audit(cid: str, user=Depends(sales)):
        load(cid)
        return [e for e in audit.events if e["contract_id"] == cid]

    @app.get("/api/audit")
    def audit_events(limit: int = 200, user=Depends(sales)):
        """Most recent events across all contracts, newest first."""
        return list(reversed(audit.events[-limit:]))

    @app.get("/api/audit/verify")
    def verify(user=Depends(sales)):
        ok, msg = audit.verify_stored()
        return {"ok": ok, "message": msg, "events": len(audit.events), "head": audit.head}

    @app.get("/api/metrics")
    def metrics(user=Depends(sales)):
        rows = [NegotiationState.model_validate_json(r["state_json"]) for r in store.all()]
        signed = [x for x in rows if x.status == "signed"]
        by_status: dict[str, int] = defaultdict(int)
        for x in rows:
            by_status[x.status] += 1
        escalated_ever = sum(1 for x in rows if any(e for e in x.human_decisions) or x.status == "awaiting_human")
        return {
            "contracts": len(rows), "by_status": by_status,
            "signed": len(signed), "awaiting_human": by_status.get("awaiting_human", 0),
            "signed_value": round(sum(x.outcome.final_terms.price for x in signed), 2),
            "avg_rounds_signed": round(sum(x.round for x in signed) / len(signed), 2) if signed else None,
            "avg_discount_signed": round(sum(1 - x.outcome.final_terms.price / x.context.list_price for x in signed) / len(signed), 3) if signed else None,
            "escalation_rate": round(escalated_ever / len(rows), 3) if rows else None,
            "unreviewed_risky_signed": sum(x.outcome.signed_unreviewed_risky_clauses for x in signed),
            "crm_memory_size": len(sim_orch.crm.deals),
        }

    @app.get("/api/samples")
    def samples(limit: int = 40, user=Depends(sales)):
        rows = [json.loads(l) for l in (DATA / "labels" / "contracts.jsonl").read_text().splitlines()[:limit]]
        return [{"id": r["contract_id"], **r["context"], "expert_should_escalate": r["should_escalate"],
                 "scenario": {"wtp": r["hidden"]["wtp"], "persona": r["hidden"]["persona"]}} for r in rows]

    @app.get("/api/personas")
    def personas(user=Depends(sales)):
        return PERSONAS

    @app.get("/api/eval")
    def eval_results(user=Depends(sales)):
        out = {}
        for name in ("eval_escalation", "eval_negotiation", "eval_cuad", "eval_llm"):
            # fresh local runs win; otherwise fall back to the committed snapshot in results/
            p = next((d / f"{name}.json" for d in (RUNS, RUNS.parent / "results") if (d / f"{name}.json").exists()), None)
            out[name] = json.loads(p.read_text()) if p else None
        return out

    # ------------------------------------------------------------------ expert annotation (RO2 ground truth)
    def _need_cuad():
        if not annotations.available:
            raise HTTPException(503, "CUAD clauses not found. Run `conexus fetch-cuad` (or `make cuad`) first.")

    @app.get("/api/annotate/next")
    def annotate_next(user=Depends(legal)):
        _need_cuad()
        return annotations.next(user["email"]) or {"done": True}

    @app.post("/api/annotate")
    def annotate(req: AnnotationRequest, user=Depends(legal)):
        _need_cuad()
        try:
            return annotations.submit(req.clause_id, user["email"], req.requires_human, req.level, req.redlinable, req.note)
        except KeyError:
            raise HTTPException(404, f"unknown clause {req.clause_id}")

    @app.get("/api/annotate/stats")
    def annotate_stats(user=Depends(legal)):
        _need_cuad()
        return annotations.stats()

    # ------------------------------------------------------------------ notifications
    @app.get("/api/notifications")
    def notifications(user=Depends(sales)):
        rows = store.notifications_for(user["id"], COVER[user["role"]])
        items = [{"id": r["id"], "kind": r["kind"], "title": r["title"], "body": r["body"], "link": r["link"],
                  "created_at": r["created_at"], "read": bool(r["is_read"])} for r in rows]
        return {"unread": sum(not i["read"] for i in items), "items": items}

    @app.post("/api/notifications/read")
    def notifications_read(req: ReadRequest, user=Depends(sales)):
        ids = req.ids
        if req.all:
            ids = [r["id"] for r in store.notifications_for(user["id"], COVER[user["role"]], limit=500)]
        store.mark_read(user["id"], ids)
        return {"ok": True}

    # ------------------------------------------------------------------ analytics
    @app.get("/api/analytics")
    def analytics(days: int = 14, user=Depends(sales)):
        rows = store.all()
        states = [(r, NegotiationState.model_validate_json(r["state_json"])) for r in rows]
        now = time.time()
        day0 = int(now // 86400) - (days - 1)
        series = [{"day": time.strftime("%d %b", time.gmtime((day0 + i) * 86400)), "analyzed": 0, "signed": 0, "value": 0.0, "escalated": 0}
                  for i in range(days)]

        def bucket(ts: float):
            i = int(ts // 86400) - day0
            return series[i] if 0 <= i < days else None

        signed = []
        for r, st in states:
            if (b := bucket(r["created_at"])):
                b["analyzed"] += 1
            if st.status == "signed" and st.outcome and st.outcome.final_terms:
                signed.append((r, st))
                if (b := bucket(r["updated_at"])):
                    b["signed"] += 1
                    b["value"] += st.outcome.final_terms.price
        by_kind: dict[str, int] = defaultdict(int)
        for e in audit.events:
            if e["action"] == "ESCALATE":
                by_kind[(e.get("data") or {}).get("kind", "other")] += 1
                if (b := bucket(e["ts"])):
                    b["escalated"] += 1
        decisions = {"approved": 0, "rejected": 0}
        for _, st in states:
            for d in st.human_decisions:
                decisions["approved" if d.approve else "rejected"] += 1
        close_minutes = sorted((r["updated_at"] - r["created_at"]) / 60 for r, _ in signed)
        rounds: dict[int, int] = defaultdict(int)
        segment: dict[str, dict] = defaultdict(lambda: {"deals": 0, "value": 0.0})
        for _, st in signed:
            rounds[st.outcome.rounds] += 1
            seg = segment[st.context.segment]
            seg["deals"] += 1
            seg["value"] += st.outcome.final_terms.price
        discounts = [{"customer": st.context.customer, "discount": round(1 - st.outcome.final_terms.price / st.context.list_price, 3),
                      "price": st.outcome.final_terms.price} for _, st in signed]
        return {
            "days": series,
            "escalations_by_kind": [{"kind": k, "count": v} for k, v in sorted(by_kind.items(), key=lambda kv: -kv[1])],
            "decisions": decisions,
            "time_to_close_minutes": {"median": round(close_minutes[len(close_minutes) // 2], 1) if close_minutes else None,
                                      "fastest": round(close_minutes[0], 1) if close_minutes else None,
                                      "slowest": round(close_minutes[-1], 1) if close_minutes else None},
            "rounds": [{"rounds": k, "deals": rounds[k]} for k in range(1, 9)],
            "by_segment": [{"segment": k, **v} for k, v in sorted(segment.items(), key=lambda kv: -kv[1]["value"])],
            "discounts": sorted(discounts, key=lambda d: -d["discount"]),
            "totals": {"contracts": len(states), "signed": len(signed), "value": round(sum(st.outcome.final_terms.price for _, st in signed), 2),
                       "escalations": sum(by_kind.values())},
        }

    @app.get("/api/outbox")
    def outbox(limit: int = 20, user=Depends(sales)):
        """Escalation messages sent to reviewers (Slack / console)."""
        return escalations.sent[-limit:] if isinstance(escalations, RecordingChannel) else []

    # ---------------------------------------------------------------- web app (built React UI)
    dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if dist.exists():
        from fastapi.responses import FileResponse
        from fastapi.staticfiles import StaticFiles

        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path.startswith(("api/", "docs", "openapi.json", "health")):
                raise HTTPException(404)
            f = (dist / path).resolve()
            if path and f.is_file() and dist in f.parents:
                return FileResponse(f)
            return FileResponse(dist / "index.html")

    return app


def main():
    import uvicorn

    uvicorn.run("conexus.api.server:create_app", factory=True,
                host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "8000")))
