"""Tests für die Schnittstellen-Diagnose (FinTS-Rückmeldungs-Log)."""

import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from app.db import Base, SessionLocal, engine
from app.seed import seed_categories
from app.fints_debug import extract_fints_codes, interpret_message


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


def test_sync_log_empty(client):
    r = client.get("/api/debug/sync-log")
    assert r.status_code == 200
    assert r.json() == []


def test_test_conn_mock_logs_success(client):
    r = client.post("/api/debug/test-conn", json={"bank": "mock"})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    log = client.get("/api/debug/sync-log").json()
    assert len(log) == 1
    assert log[0]["bank"] == "mock"
    assert log[0]["status"] == "success"
    assert log[0]["source"] == "diagnostic"


def test_test_conn_unknown_bank_404(client):
    r = client.post("/api/debug/test-conn", json={"bank": "gibtsnicht"})
    assert r.status_code == 404


def test_sync_job_logs_entry(client):
    client.post("/api/sync", json={"banks": ["mock"]})
    import time
    log = []
    for _ in range(60):
        # Nur prüfen, dass mindestens ein Eintrag entsteht; Job läuft asynchron
        log = client.get("/api/debug/sync-log").json()
        if log:
            break
        time.sleep(0.2)
    assert log and log[0]["bank"] == "mock"
    assert log[0]["status"] in ("success", "error")


def test_clear_log(client):
    client.post("/api/debug/test-conn", json={"bank": "mock"})
    r = client.delete("/api/debug/sync-log")
    assert r.status_code == 200 and r.json()["deleted"] == 1
    assert client.get("/api/debug/sync-log").json() == []


def test_extract_fints_codes():
    assert "9942" in extract_fints_codes(
        "[comdirect] Error during dialog initialization, PIN wrong? (9942)")
    assert extract_fints_codes("halt mal (9340) und (9050)") == ["9050", "9340"]


def test_interpret_message_de():
    assert "PIN ungültig" in interpret_message("code 9942")
    assert "Ungültige Signatur" in interpret_message("fehler 9340")
    # unbekannter Text bleibt als Original zur Diagnose erhalten
    assert interpret_message("irgendwas") == "irgendwas"