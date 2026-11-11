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

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from ..agents.audit import AuditAgent
from ..agents.risk import RiskClassifier
from ..config import DATA, RUNS, Settings, get_settings
from ..integrations.channels import Channel, ConsoleChannel, EmailChannel, SlackChannel
from ..llm import build_llm
from ..models import DealContext, HumanDecision, NegotiationState, Terms
from ..orchestrator import Orchestrator
from ..parsing import read_document
from ..sim.counterparty import PERSONAS, RuleCounterparty
from ..sim.world import LIST_PER_SEAT
from ..store import Store
from .annotation import AnnotationService


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
    annotator: str = Field(min_length=1, max_length=60)
    requires_human: bool | None = Field(None, description="null = unsure / skip")
    level: Literal["low", "medium", "high"] | None = None
    redlinable: bool | None = None
    note: str = Field("", max_length=1000)


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
    s = settings or get_settings()
    store = Store(db_path or RUNS / "conexus.db")
    audit = AuditAgent(audit_path or RUNS / "audit.jsonl")
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
    @app.get("/health")
    def health():
        return {"ok": True, "llm": llm.name if llm else "offline", "contracts": len(store.all())}

    @app.post("/api/contracts", status_code=201)
    def create_contract(customer: str = Form(...), segment: str = Form("smb"), region: str = Form("india"),
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
    def list_contracts():
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
    def get_contract(cid: str):
        return view(load(cid))

    @app.post("/api/contracts/{cid}/negotiate")
    def negotiate(cid: str, req: NegotiateRequest, bg: BackgroundTasks):
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
    def reply(cid: str, req: ReplyRequest):
        """Inbound e-mail webhook (e.g. SendGrid / Mailgun inbound parse) or manual paste from the UI."""
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
    def decision(cid: str, d: HumanDecision, bg: BackgroundTasks):
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

    @app.get("/api/escalations")
    def escalations_inbox():
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
    def contract_audit(cid: str):
        load(cid)
        return [e for e in audit.events if e["contract_id"] == cid]

    @app.get("/api/audit")
    def audit_events(limit: int = 200):
        """Most recent events across all contracts, newest first."""
        return list(reversed(audit.events[-limit:]))

    @app.get("/api/audit/verify")
    def verify():
        ok, msg = AuditAgent.verify(audit.path) if audit.path.exists() else (True, "empty log")
        return {"ok": ok, "message": msg, "events": len(audit.events), "head": audit.head}

    @app.get("/api/metrics")
    def metrics():
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
    def samples(limit: int = 40):
        rows = [json.loads(l) for l in (DATA / "labels" / "contracts.jsonl").read_text().splitlines()[:limit]]
        return [{"id": r["contract_id"], **r["context"], "expert_should_escalate": r["should_escalate"],
                 "scenario": {"wtp": r["hidden"]["wtp"], "persona": r["hidden"]["persona"]}} for r in rows]

    @app.get("/api/personas")
    def personas():
        return PERSONAS

    @app.get("/api/eval")
    def eval_results():
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
    def annotate_next(annotator: str):
        _need_cuad()
        return annotations.next(annotator.strip()) or {"done": True}

    @app.post("/api/annotate")
    def annotate(req: AnnotationRequest):
        _need_cuad()
        try:
            return annotations.submit(req.clause_id, req.annotator.strip(), req.requires_human, req.level, req.redlinable, req.note)
        except KeyError:
            raise HTTPException(404, f"unknown clause {req.clause_id}")

    @app.get("/api/annotate/stats")
    def annotate_stats():
        _need_cuad()
        return annotations.stats()

    @app.get("/api/outbox")
    def outbox(limit: int = 20):
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
