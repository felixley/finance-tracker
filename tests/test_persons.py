"""Feature-Tests: Personen / Konto-Zuordnung / Summary."""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from app.db import Base, SessionLocal, engine
from app.seed import seed_categories


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = SessionLocal()
    seed_categories(db)
    db.close()
    app = create_app()
    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(engine)


def _sync_mock(client):
    r = client.post("/api/sync", json={"banks": ["mock"]})
    job = r.json()["job_id"]
    for _ in range(60):
        st = client.get(f"/api/sync/status/{job}").json()
        if st.get("status") != "running":
            break
        time.sleep(0.2)
    assert st["status"] == "done", st


def test_person_crud_and_owner(client):
    r = client.post("/api/persons", json={"name": "Felix"})
    assert r.status_code == 201
    felix = r.json()
    # Dublette abgelehnt
    assert client.post("/api/persons", json={"name": "Felix"}).status_code == 409

    _sync_mock(client)
    accts = client.get("/api/accounts").json()
    aid = accts[0]["id"]
    r = client.patch(f"/api/accounts/{aid}/owner", json={"owner_id": felix["id"]})
    assert r.status_code == 200 and r.json()["owner_id"] == felix["id"]
    assert client.get("/api/accounts").json()[0]["owner_name"] == "Felix"

    # Person löschen → Konto wieder ohne Zuordnung
    assert client.delete(f"/api/persons/{felix['id']}").json()["ok"] is True
    assert client.get("/api/accounts").json()[0]["owner_id"] is None


def test_persons_summary_and_filter(client):
    _sync_mock(client)
    r = client.post("/api/persons", json={"name": "Partner"})
    pid = r.json()["id"]
    accts = client.get("/api/accounts").json()
    client.patch(f"/api/accounts/{accts[0]['id']}/owner", json={"owner_id": pid})

    summary = client.get("/api/persons/summary").json()
    by_name = {p["name"]: p for p in summary}
    assert "Partner" in by_name and by_name["Partner"]["n_accounts"] == 1
    # Wenn es mehrere Konten gibt: Rest landet bei "Ohne Zuordnung"
    if len(accts) > 1:
        assert "Ohne Zuordnung" in by_name
        assert by_name["Ohne Zuordnung"]["n_accounts"] == len(accts) - 1
    # Saldo je Person summiert sich zum Gesamtsaldo
    kpis = client.get("/api/kpis").json()
    assert round(sum(p["total_balance"] for p in summary), 2) == round(kpis["total_balance"], 2)

    # Transaktions-Filter nach Person
    txs_all = client.get("/api/transactions").json()["total"]
    txs_p = client.get(f"/api/transactions?person_id={pid}").json()["total"]
    assert 0 < txs_p <= txs_all