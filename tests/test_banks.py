"""Tests: Bank-Verbindungen GUI-API (GET/POST/DELETE /api/banks).

Credentials-Store isoliert per FINANCE_TRACKER_SECRETS_DIR auf tmp_path —
nie die echte Ablage (~/.config/finance-tracker) oder Prod-DB anfassen.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from app.db import Base, engine


@pytest.fixture()
def client(monkeypatch, tmp_path):
    # Frische Tabellen (Lifespan seedet nur, wenn Tabellen existieren)
    Base.metadata.create_all(engine)
    # Jede Test-Session bekommt einen eigenen leeren Secrets-Store.
    monkeypatch.setenv("FINANCE_TRACKER_SECRETS_DIR", str(tmp_path))
    app = create_app()
    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(engine)
    # Aufräumen: Next-Test erzeugt die Dateien selbst wieder (chmod 600).
    for name in ("credentials.enc", "master.key"):
        (tmp_path / name).unlink(missing_ok=True)


def test_list_banks_unconfigured(client):
    r = client.get("/api/banks")
    assert r.status_code == 200
    banks = r.json()
    keys = {b["key"] for b in banks}
    assert {"comdirect", "dkb"} <= keys
    assert all(b["configured"] is False for b in banks)
    assert all("login" not in b and "pin" not in b for b in banks)


def test_set_then_configured(client):
    r = client.post("/api/banks/comdirect/credentials", json={
        "blz": "20041133",
        "login": "user-123",
        "pin": "geheim-pin",
        "fints_url": "https://fints.comdirect.de/fints",
    })
    assert r.status_code == 201, r.text
    assert r.json() == {"ok": True}

    banks = client.get("/api/banks").json()
    cd = next(b for b in banks if b["key"] == "comdirect")
    assert cd["configured"] is True
    dkb = next(b for b in banks if b["key"] == "dkb")
    assert dkb["configured"] is False


def test_list_never_leaks_secrets(client):
    client.post("/api/banks/dkb/credentials", json={
        "blz": "30050553", "login": "dkb-login", "pin": "dkb-pin-123",
        "fints_url": "https://example.org/fints",
    })
    body = client.get("/api/banks").text
    assert "dkb-pin-123" not in body
    assert "dkb-login" not in body


def test_set_missing_pin_422(client):
    r = client.post("/api/banks/comdirect/credentials", json={
        "blz": "20041133", "login": "user", "fints_url": "https://x/fints",
    })
    assert r.status_code == 422


def test_unknown_bank_404(client):
    assert client.post("/api/banks/foo/credentials", json={
        "blz": "1", "login": "a", "pin": "b", "fints_url": "c"}).status_code == 404
    assert client.delete("/api/banks/foo/credentials").status_code == 404


def test_delete_credentials(client):
    client.post("/api/banks/comdirect/credentials", json={
        "blz": "1", "login": "a", "pin": "b", "fints_url": "c"})
    r = client.delete("/api/banks/comdirect/credentials")
    assert r.status_code == 200
    assert r.json()["deleted"] is True
    banks = client.get("/api/banks").json()
    cd = next(b for b in banks if b["key"] == "comdirect")
    assert cd["configured"] is False
    # Nochmal löschen → nichts mehr da
    assert client.delete("/api/banks/comdirect/credentials").json()["deleted"] is False