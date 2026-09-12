"""API-Layer-Tests: FastAPI TestClient gegen frische In-Memory-DB."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from app.db import Base, SessionLocal, engine
from app.models import Category, Rule, Transaction
from app.seed import seed_categories


@pytest.fixture()
def client(monkeypatch):
    # Frische In-Memory-DB für jeden Test
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = SessionLocal()
    seed_categories(db)
    db.close()
    app = create_app()
    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(engine)


def test_kpis_empty(client):
    r = client.get("/api/kpis")
    assert r.status_code == 200
    data = r.json()
    assert data == {"total_balance": 0.0, "income_month": 0, "expenses_month": 0, "net_cashflow": 0}


def test_sync_and_kpis(client):
    r = client.post("/api/sync", json={"banks": ["mock"]})
    assert r.status_code == 200
    job_id = r.json()["job_id"]
    # Sync-Job abwarten (Executor arbeitet asynchron)
    import time
    for _ in range(60):
        st = client.get(f"/api/sync/status/{job_id}").json()
        if st.get("status") != "running":
            break
        time.sleep(0.2)
    assert st["status"] == "done", st
    assert st["result"]["results"]["mock"]["inserted"] > 0
    kpis = client.get("/api/kpis").json()
    assert kpis["total_balance"] > 0
    # Durch Startup-Seeding (Lifespan) sollen Regeln existieren und Tx kategorisiert sein
    txs = client.get("/api/transactions").json()
    assert txs["total"] > 0
    assert all(i["category_name"] is not None for i in txs["items"]), "nach Startup-Seed darf nichts Unassigned sein"


def test_transaction_category_override_creates_rule(client):
    client.post("/api/sync", json={"banks": ["mock"]})
    import time
    for _ in range(60):
        txs = client.get("/api/transactions?per_page=1").json()
        if txs["total"] > 0:
            break
        time.sleep(0.2)
    tx = txs["items"][0]
    cats = client.get("/api/categories").json()
    target = next(c["id"] for c in cats if c["name"] == "Insurance")
    r = client.patch(f"/api/transactions/{tx['id']}/category", json={"category_id": target})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["rule_created"] is True
    rules = client.get("/api/rules").json()
    manual = [x for x in rules if x.get("created_from_manual_override")]
    assert manual and manual[-1]["priority"] == 10


def test_timeline_and_breakdown(client):
    client.post("/api/sync", json={"banks": ["mock"]})
    import time
    time.sleep(2)
    tl = client.get("/api/timeline").json()
    assert isinstance(tl, list) and tl and {"period", "income", "expenses"} <= set(tl[0])
    bd = client.get("/api/categories/breakdown").json()
    assert isinstance(bd, list) and all({"category", "total"} <= set(x) for x in bd)
    assert all(x["total"] >= 0 for x in bd)
