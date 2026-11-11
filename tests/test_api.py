import json

import pytest
from fastapi.testclient import TestClient

from conexus.api.auth import hash_password
from conexus.api.server import create_app
from conexus.config import DATA, get_settings

PW = "correct-horse-battery"


@pytest.fixture
def app(tmp_path):
    app = create_app(get_settings(llm_provider="offline"), tmp_path / "t.db", tmp_path / "audit.jsonl",
                     labels_export=tmp_path / "expert.jsonl")
    for email, role in (("admin@x.io", "admin"), ("legal@x.io", "legal"), ("legal2@x.io", "legal"), ("sales@x.io", "sales")):
        app.state.store.create_user(email, email.split("@")[0].title(), role, hash_password(PW))
    return app


def login(app, email: str) -> TestClient:
    c = TestClient(app)
    assert c.post("/api/auth/login", json={"email": email, "password": PW}).status_code == 200
    return c


@pytest.fixture
def client(app):
    return login(app, "legal@x.io")


def _sample(pred):
    for line in (DATA / "labels" / "contracts.jsonl").read_text().splitlines():
        r = json.loads(line)
        if pred(r):
            return r
    raise LookupError


def _create(client, r):
    c = r["context"]
    resp = client.post("/api/contracts", data={"customer": c["customer"], "segment": c["segment"], "region": c["region"],
                                               "product": c["product"], "seats": c["seats"], "sample_id": r["contract_id"]})
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_upload_txt_and_analyze(client):
    text = (DATA / "contracts" / "contract_000.txt").read_bytes()
    resp = client.post("/api/contracts", data={"customer": "Acme", "seats": 30, "product": "core"},
                       files={"file": ("msa.txt", text, "text/plain")})
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "analyzed" and len(body["clauses"]) > 5 and body["opening_terms"]


def test_rejects_unsupported_file(client):
    resp = client.post("/api/contracts", data={"customer": "Acme"}, files={"file": ("x.exe", b"MZ", "application/octet-stream")})
    assert resp.status_code == 415


def test_simulated_negotiation_runs_to_terminal_or_human(client):
    r = _sample(lambda r: not r["should_escalate"] and r["context"]["list_price"] < 50_000)
    cid = _create(client, r)["id"]
    resp = client.post(f"/api/contracts/{cid}/negotiate",
                       json={"mode": "simulated", "persona": r["hidden"]["persona"], "wtp": r["hidden"]["wtp"], "delay_s": 0})
    assert resp.status_code == 200
    st = client.get(f"/api/contracts/{cid}").json()  # background task already ran in TestClient
    assert st["status"] in ("signed", "closed", "awaiting_human")
    assert client.get("/api/audit/verify").json()["ok"]
    assert len(client.get(f"/api/contracts/{cid}/audit").json()) >= 3


def test_human_in_the_loop_reject_and_approve(client):
    blocking = lambda r: any(c["requires_human"] and not c["redlinable"] for c in r["clauses"])
    r = _sample(blocking)
    cid = _create(client, r)["id"]
    st = client.post(f"/api/contracts/{cid}/negotiate", json={"mode": "simulated", "wtp": r["hidden"]["wtp"], "delay_s": 0}).json()
    assert st["status"] == "awaiting_human" and st["escalation"]["kind"] == "risky_clause"
    inbox = client.get("/api/escalations").json()
    assert any(x["id"] == cid for x in inbox)

    # reviewer approves -> negotiation resumes autonomously
    st = client.post(f"/api/contracts/{cid}/decision", json={"approve": True, "note": "acceptable"}).json()
    st = client.get(f"/api/contracts/{cid}").json()
    assert st["status"] != "analyzed" and st["reviewed_clauses"]
    assert st["human_decisions"][0]["reviewer"] == "legal@x.io"  # recorded from the session, not typed

    # second contract: reviewer rejects -> closed
    r2 = [json.loads(l) for l in (DATA / "labels" / "contracts.jsonl").read_text().splitlines() if blocking(json.loads(l))][1]
    cid2 = _create(client, r2)["id"]
    client.post(f"/api/contracts/{cid2}/negotiate", json={"mode": "simulated", "delay_s": 0})
    st2 = client.post(f"/api/contracts/{cid2}/decision", json={"approve": False, "note": "IP clause unacceptable"}).json()
    assert st2["status"] == "closed" and st2["outcome"]["status"] == "rejected_by_human"


def test_email_mode_with_reply_webhook(client):
    r = _sample(lambda r: not r["should_escalate"])
    cid = _create(client, r)["id"]
    st = client.post(f"/api/contracts/{cid}/negotiate", json={"mode": "email"}).json()
    assert st["status"] == "awaiting_reply" and st["round"] == 1
    price = st["last_our_offer"]["price"]
    st = client.post(f"/api/contracts/{cid}/reply", json={"message": f"We accept your proposal of ${price:,.0f}. Deal."}).json()
    assert st["status"] in ("signed", "awaiting_human")
    if st["status"] == "signed":
        assert st["outcome"]["envelope_id"]
    m = client.get("/api/metrics").json()
    assert m["contracts"] == 1


def test_cannot_start_twice(client):
    r = _sample(lambda r: not r["should_escalate"])
    cid = _create(client, r)["id"]
    client.post(f"/api/contracts/{cid}/negotiate", json={"mode": "email"})
    assert client.post(f"/api/contracts/{cid}/negotiate", json={"mode": "email"}).status_code == 409


@pytest.mark.skipif(not (DATA / "cuad" / "clauses.jsonl").exists(), reason="CUAD not downloaded")
def test_annotation_flow_with_overlap_and_kappa(app, client, tmp_path):
    a = client.get("/api/annotate/next").json()
    assert "text" in a and "categories" not in a  # no anchoring before the label is committed
    reveal = client.post("/api/annotate", json={"clause_id": a["clause_id"], "requires_human": True, "level": "high"}).json()
    assert "proxy_human" in reveal and "model" in reveal
    second = login(app, "legal2@x.io")
    b = second.get("/api/annotate/next").json()
    assert b["clause_id"] == a["clause_id"]  # overlap offered first, for agreement
    second.post("/api/annotate", json={"clause_id": b["clause_id"], "requires_human": True})
    st = client.get("/api/annotate/stats").json()
    assert st["pairs"][0]["overlap"] == 1 and st["pairs"][0]["agreement"] == 1.0
    assert (tmp_path / "expert.jsonl").read_text().count("\n") == 2


# ---------------------------------------------------------------- auth, roles, policy, export
def test_requires_sign_in(app):
    anon = TestClient(app)
    assert anon.get("/api/contracts").status_code == 401
    assert anon.get("/health").status_code == 200
    st = anon.get("/api/auth/status").json()
    assert st["setup_required"] is False and st["user"] is None
    assert anon.post("/api/auth/login", json={"email": "legal@x.io", "password": "wrong-password"}).status_code == 401


def test_roles_enforced(app):
    sales = login(app, "sales@x.io")
    r = _sample(lambda r: any(c["requires_human"] and not c["redlinable"] for c in r["clauses"]))
    cid = _create(sales, r)["id"]
    sales.post(f"/api/contracts/{cid}/negotiate", json={"mode": "simulated", "delay_s": 0})
    assert sales.post(f"/api/contracts/{cid}/decision", json={"approve": True}).status_code == 403  # sales cannot approve
    assert sales.put("/api/policy", json={"escalation": {"max_rounds": 5}}).status_code == 403
    assert sales.get("/api/users").status_code == 403
    assert login(app, "legal@x.io").post(f"/api/contracts/{cid}/decision", json={"approve": False}).status_code == 200


def test_first_run_setup_only_once(tmp_path):
    app = create_app(get_settings(llm_provider="offline"), tmp_path / "s.db", tmp_path / "a.jsonl", labels_export=tmp_path / "e.jsonl")
    c = TestClient(app)
    assert c.get("/api/auth/status").json()["setup_required"] is True
    assert c.post("/api/auth/setup", json={"email": "a@x.io", "name": "A", "password": "short"}).status_code == 422
    me = c.post("/api/auth/setup", json={"email": "a@x.io", "name": "A", "password": PW}).json()
    assert me["role"] == "admin" and c.get("/api/users").status_code == 200
    assert TestClient(app).post("/api/auth/setup", json={"email": "b@x.io", "name": "B", "password": PW}).status_code == 409


def test_admin_manages_users_and_cannot_lock_self_out(app):
    a = login(app, "admin@x.io")
    new = a.post("/api/users", json={"email": "new@x.io", "name": "New", "role": "sales", "password": PW}).json()
    assert a.patch(f"/api/users/{new['id']}", json={"role": "legal"}).json()["role"] == "legal"
    me = a.get("/api/auth/status").json()["user"]
    assert a.patch(f"/api/users/{me['id']}", json={"role": "sales"}).status_code == 409
    a.patch(f"/api/users/{new['id']}", json={"active": False})
    assert TestClient(app).post("/api/auth/login", json={"email": "new@x.io", "password": PW}).status_code == 401


def test_policy_change_validated_applied_and_audited(app):
    a = login(app, "admin@x.io")
    assert a.put("/api/policy", json={"pricing": {"max_payment_days": 10}}).status_code == 422  # below target 30
    assert a.put("/api/policy", json={"escalation": {"clause_threshold": 2}}).status_code == 422
    res = a.put("/api/policy", json={"escalation": {"max_rounds": 5, "autonomy_value_limit": 50000}}).json()
    assert res["changed"] == {"escalation.max_rounds": 5, "escalation.autonomy_value_limit": 50000}
    assert a.get("/api/policy").json()["escalation"]["max_rounds"] == 5
    hist = a.get("/api/policy/history").json()
    assert hist[0]["agent"] == "human:admin@x.io" and "max_rounds: 8 -> 5" in hist[0]["rationale"]
    # the agents use the new policy: negotiation stops by round 5
    r = _sample(lambda r: not r["should_escalate"])
    cid = _create(a, r)["id"]
    st = a.post(f"/api/contracts/{cid}/negotiate", json={"mode": "simulated", "persona": "hardball", "wtp": 1, "delay_s": 0}).json()
    assert a.get(f"/api/contracts/{cid}").json()["round"] <= 5


def test_redline_docx_has_tracked_changes(client):
    import io
    import zipfile

    r = _sample(lambda r: any(c["redlinable"] and c["level"] != "low" for c in r["clauses"]))
    cid = _create(client, r)["id"]
    resp = client.get(f"/api/contracts/{cid}/redline.docx")
    assert resp.status_code == 200 and "redline.docx" in resp.headers["content-disposition"]
    xml = zipfile.ZipFile(io.BytesIO(resp.content)).read("word/document.xml").decode()
    assert "<w:ins " in xml and "<w:del " in xml and "CoNexus Legal/Risk Agent" in xml
    assert "word/comments.xml" in zipfile.ZipFile(io.BytesIO(resp.content)).namelist()


def test_reply_webhook_token(app, monkeypatch):
    monkeypatch.setenv("CONEXUS_WEBHOOK_TOKEN", "hook-secret")
    c = login(app, "sales@x.io")
    cid = _create(c, _sample(lambda r: not r["should_escalate"]))["id"]
    c.post(f"/api/contracts/{cid}/negotiate", json={"mode": "email"})
    anon = TestClient(app)
    assert anon.post(f"/api/contracts/{cid}/reply", json={"message": "hi"}).status_code == 401
    ok = anon.post(f"/api/contracts/{cid}/reply", json={"message": "Our counter-proposal is $1,000 per year, net 30."},
                   headers={"X-Conexus-Webhook-Token": "hook-secret"})
    assert ok.status_code == 200


def test_demo_login_seeds_and_does_not_block_setup(tmp_path, monkeypatch):
    monkeypatch.setenv("CONEXUS_DEMO", "1")
    app = create_app(get_settings(llm_provider="offline"), tmp_path / "d.db", tmp_path / "a.jsonl", labels_export=tmp_path / "e.jsonl")
    c = TestClient(app)
    assert c.get("/api/auth/status").json()["demo_enabled"] is True
    me = c.post("/api/auth/demo").json()
    assert me["role"] == "legal"
    rows = c.get("/api/contracts").json()
    assert len(rows) >= 5 and {r["status"] for r in rows} >= {"signed", "analyzed"}
    assert c.get("/api/users").status_code == 403  # demo cannot manage users
    # the demo account must not count as a real user: first-run setup is still available
    assert TestClient(app).get("/api/auth/status").json()["setup_required"] is True


def test_demo_disabled_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("CONEXUS_DEMO", raising=False)
    app = create_app(get_settings(llm_provider="offline"), tmp_path / "d.db", tmp_path / "a.jsonl", labels_export=tmp_path / "e.jsonl")
    assert TestClient(app).post("/api/auth/demo").status_code == 404


def test_document_offsets_cover_clauses(client):
    r = _sample(lambda r: True)
    cid = _create(client, r)["id"]
    doc = client.get(f"/api/contracts/{cid}/document").json()
    st = client.get(f"/api/contracts/{cid}").json()
    assert len(doc["segments"]) == len(st["clauses"])
    for seg, cl in zip(doc["segments"], st["clauses"]):
        assert doc["text"][seg["body_start"]:seg["end"]].strip() == cl["text"].strip()
        assert seg["start"] <= seg["body_start"] < seg["end"]


# ---------------------------------------------------------------- self sign-up, verification, reset
from urllib.parse import parse_qs, urlparse


def _token(link: str) -> str:
    return parse_qs(urlparse(link).query)["token"][0]


def test_signup_verify_login_and_reset(app, monkeypatch):
    monkeypatch.setenv("CONEXUS_DEV_EMAIL_LINKS", "1")
    for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD"):
        monkeypatch.delenv(k, raising=False)
    c = TestClient(app)
    assert c.get("/api/auth/status").json()["signup_enabled"] is True
    r = c.post("/api/auth/signup", json={"name": "Asha Rao", "email": "Asha@New.io", "password": PW})
    assert r.status_code == 201 and r.json()["email_sent"] is False and "/verify?token=" in r.json()["dev_link"]
    # cannot sign in before confirming the e-mail
    assert c.post("/api/auth/login", json={"email": "asha@new.io", "password": PW}).status_code == 403
    tok = _token(r.json()["dev_link"])
    me = c.post("/api/auth/verify", json={"token": tok}).json()
    assert me["email"] == "asha@new.io" and me["role"] == "sales"
    assert c.post("/api/auth/verify", json={"token": tok}).status_code == 400  # single use
    assert TestClient(app).post("/api/auth/login", json={"email": "asha@new.io", "password": PW}).status_code == 200
    # duplicate sign-up of a verified account is refused
    assert c.post("/api/auth/signup", json={"name": "X", "email": "asha@new.io", "password": PW}).status_code == 409
    # forgot -> reset -> sign in with the new password; old password stops working
    f = c.post("/api/auth/forgot", json={"email": "asha@new.io"}).json()
    new_pw = "brand-new-password-42"
    assert c.post("/api/auth/reset", json={"token": _token(f["dev_link"]), "password": new_pw}).status_code == 200
    assert TestClient(app).post("/api/auth/login", json={"email": "asha@new.io", "password": PW}).status_code == 401
    assert TestClient(app).post("/api/auth/login", json={"email": "asha@new.io", "password": new_pw}).status_code == 200


def test_no_links_exposed_without_dev_flag(app, monkeypatch):
    monkeypatch.delenv("CONEXUS_DEV_EMAIL_LINKS", raising=False)
    for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD"):
        monkeypatch.delenv(k, raising=False)
    c = TestClient(app)
    r = c.post("/api/auth/signup", json={"name": "Bo", "email": "bo@new.io", "password": PW}).json()
    assert "dev_link" not in r
    assert "dev_link" not in c.post("/api/auth/forgot", json={"email": "legal@x.io"}).json()
    # unknown e-mails get the same answer (no account enumeration)
    assert c.post("/api/auth/forgot", json={"email": "nobody@x.io"}).json() == {"ok": True, "email_sent": False}


def test_signup_blocked_before_first_admin(tmp_path):
    app = create_app(get_settings(llm_provider="offline"), tmp_path / "s.db", tmp_path / "a.jsonl", labels_export=tmp_path / "e.jsonl")
    assert TestClient(app).post("/api/auth/signup", json={"name": "A", "email": "a@x.io", "password": PW}).status_code == 409


def test_notifications_follow_stage_changes(app):
    legal = login(app, "legal@x.io")
    sales = login(app, "sales@x.io")
    r = _sample(lambda r: any(c["requires_human"] and not c["redlinable"] for c in r["clauses"]))
    cid = _create(sales, r)["id"]
    sales.post(f"/api/contracts/{cid}/negotiate", json={"mode": "simulated", "delay_s": 0})
    ln = legal.get("/api/notifications").json()
    assert ln["unread"] >= 1 and ln["items"][0]["kind"] == "escalation" and ln["items"][0]["link"] == f"/contracts/{cid}"
    assert all(i["kind"] != "escalation" for i in sales.get("/api/notifications").json()["items"])  # Legal-only
    legal.post(f"/api/contracts/{cid}/decision", json={"approve": False, "note": "no"})
    kinds = [i["kind"] for i in sales.get("/api/notifications").json()["items"]]
    assert "closed" in kinds  # everyone hears the outcome
    legal.post("/api/notifications/read", json={"all": True})
    assert legal.get("/api/notifications").json()["unread"] == 0


def test_analytics_shape(client):
    r = _sample(lambda r: not r["should_escalate"] and r["context"]["list_price"] < 50_000)
    cid = _create(client, r)["id"]
    client.post(f"/api/contracts/{cid}/negotiate", json={"mode": "simulated", "wtp": r["hidden"]["wtp"], "delay_s": 0})
    a = client.get("/api/analytics").json()
    assert len(a["days"]) == 14 and a["totals"]["contracts"] == 1
    assert sum(d["analyzed"] for d in a["days"]) == 1
    assert len(a["rounds"]) == 8
