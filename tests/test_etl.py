"""Tests: ETL-Pipeline (clean, external_id, Dedupe, Mock-Sync)."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.etl import clean, compute_external_id, sync_bank
from app.models import Account, Transaction
from app.seed import seed_categories
from app.banks.mock import MockBankConnector


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    session = TestSession()
    seed_categories(session)
    yield session
    session.close()


def test_clean_normalization():
    raw = {
        "buchungsdatum": "2026-09-01",
        "betrag": "-52,30",
        "partner_name": "  REWE   SAG  Köln ",
        "verwendungszweck": None,
        "waehrung": "",
    }
    out = clean(raw)
    assert out is not None
    assert out["partner_name"] == "REWE SAG Köln"
    assert out["betrag"] == Decimal("52.30") or out["betrag"] == Decimal("-52.30")
    assert out["waehrung"] == "EUR"
    # fehlendes Datum → verworfen
    assert clean({"betrag": "-1"}) is None


def test_external_id_stability():
    tx = {
        "buchungsdatum": dt.date(2026, 9, 1),
        "betrag": Decimal("-52.30"),
        "partner_name": "REWE",
        "verwendungszweck": "Einkauf",
    }
    id1 = compute_external_id(tx, "mock", "DE123")
    id2 = compute_external_id(tx, "mock", "DE123")
    assert id1 == id2 and len(id1) == 32
    tx2 = dict(tx, verwendungszweck="anders")
    assert compute_external_id(tx2, "mock", "DE123") != id1


def test_dedupe(db):
    connector = MockBankConnector("mock")
    summary1 = sync_bank("mock", days_back=90, db=db)
    n_before = db.query(Transaction).count()
    assert summary1["inserted"] == n_before > 0
    # zweiter Sync: alles Dedupe
    summary2 = sync_bank("mock", days_back=90, db=db)
    assert summary2["inserted"] == 0
    assert db.query(Transaction).count() == n_before


def test_sync_mock_end_to_end(db):
    summary = sync_bank("mock", days_back=90, db=db)
    assert summary["accounts"] == 1
    acct = db.query(Account).first()
    assert acct.iban.startswith("DE")
    assert acct.last_synced_at is not None
    txs = db.query(Transaction).all()
    assert len(txs) > 0
    assert all(t.waehrung == "EUR" for t in txs)
    partners = {t.partner_name for t in txs}
    assert any("REWE" in p for p in partners)