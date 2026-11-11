"""The same app on a real PostgreSQL (throwaway server via the `pgserver` package).
Skipped when pgserver is not installed (CI uses SQLite)."""
import json

import pytest
from fastapi.testclient import TestClient

pgserver = pytest.importorskip("pgserver")

from conexus.api.server import create_app  # noqa: E402
from conexus.config import DATA, get_settings  # noqa: E402

PW = "correct-horse-battery"


@pytest.fixture
def pg_url(tmp_path):
    srv = pgserver.get_server(str(tmp_path / "pg"), cleanup_mode="stop")
    yield srv.get_uri()
    srv.cleanup()


def _app(monkeypatch, url, tmp_path):
    monkeypatch.setenv("DATABASE_URL", url)
    return create_app(get_settings(llm_provider="offline"), None, None, labels_export=tmp_path / "e.jsonl")


def test_postgres_end_to_end_and_survives_restart(pg_url, tmp_path, monkeypatch):
    app = _app(monkeypatch, pg_url, tmp_path)
    assert app.state.store.backend == "postgres"
    c = TestClient(app)
    admin = c.post("/api/auth/setup", json={"email": "boss@x.io", "name": "Boss", "password": PW}).json()
    assert admin["role"] == "admin"

    r = json.loads((DATA / "labels" / "contracts.jsonl").read_text().splitlines()[0])
    ctx = r["context"]
    cid = c.post("/api/contracts", data={**{k: ctx[k] for k in ("customer", "segment", "region", "product", "seats")},
                                         "sample_id": r["contract_id"]}).json()["id"]
    c.post(f"/api/contracts/{cid}/negotiate", json={"mode": "simulated", "wtp": r["hidden"]["wtp"], "delay_s": 0})
    status = c.get(f"/api/contracts/{cid}").json()["status"]
    assert status in ("signed", "closed", "awaiting_human")
    c.put("/api/policy", json={"escalation": {"max_rounds": 6}})
    events_before = c.get("/api/audit/verify").json()
    assert events_before["ok"] and events_before["events"] > 3

    # "restart": a brand-new app process on the same database
    app2 = _app(monkeypatch, pg_url, tmp_path)
    c2 = TestClient(app2)
    assert c2.get("/api/auth/status").json()["setup_required"] is False
    assert c2.post("/api/auth/login", json={"email": "boss@x.io", "password": PW}).status_code == 200
    assert c2.get(f"/api/contracts/{cid}").json()["status"] == status
    assert c2.get("/api/policy").json()["escalation"]["max_rounds"] == 6
    v = c2.get("/api/audit/verify").json()
    assert v["ok"] and v["events"] == events_before["events"]  # same chain, nothing lost
    # the chain keeps growing correctly after the restart
    c2.post("/api/contracts", data={**{k: ctx[k] for k in ("customer", "segment", "region", "product", "seats")}, "sample_id": r["contract_id"]})
    assert c2.get("/api/audit/verify").json()["ok"]
