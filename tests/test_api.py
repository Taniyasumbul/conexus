import json

import pytest
from fastapi.testclient import TestClient

from conexus.api.server import create_app
from conexus.config import DATA, get_settings


@pytest.fixture
def client(tmp_path):
    app = create_app(get_settings(llm_provider="offline"), tmp_path / "t.db", tmp_path / "audit.jsonl",
                     labels_export=tmp_path / "expert.jsonl")
    return TestClient(app)


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
    st = client.post(f"/api/contracts/{cid}/decision", json={"approve": True, "reviewer": "asha", "note": "acceptable"}).json()
    st = client.get(f"/api/contracts/{cid}").json()
    assert st["status"] != "analyzed" and st["reviewed_clauses"]
    assert st["human_decisions"][0]["reviewer"] == "asha"

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
def test_annotation_flow_with_overlap_and_kappa(client, tmp_path):
    a = client.get("/api/annotate/next", params={"annotator": "ann1"}).json()
    assert "text" in a and "categories" not in a  # no anchoring before the label is committed
    reveal = client.post("/api/annotate", json={"clause_id": a["clause_id"], "annotator": "ann1", "requires_human": True, "level": "high"}).json()
    assert "proxy_human" in reveal and "model" in reveal
    b = client.get("/api/annotate/next", params={"annotator": "ann2"}).json()
    assert b["clause_id"] == a["clause_id"]  # overlap offered first, for agreement
    client.post("/api/annotate", json={"clause_id": b["clause_id"], "annotator": "ann2", "requires_human": True})
    st = client.get("/api/annotate/stats").json()
    assert st["pairs"][0]["overlap"] == 1 and st["pairs"][0]["agreement"] == 1.0
    assert (tmp_path / "expert.jsonl").read_text().count("\n") == 2
