"""Tests: FinTS-Engine (Credentials-Env-Fallback, Mock-Connector, Fehlerklassen)."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from app.banks.base import BankConnectionError, RateLimitError, TanRequired
from app.banks.mock import MockBankConnector
from app.fints_credentials import get_credentials


def test_error_classes():
    e = TanRequired("pushTAN (App)")
    assert e.tan_mechanism == "pushTAN (App)"
    assert issubclass(TanRequired, Exception)
    assert issubclass(BankConnectionError, Exception)
    assert issubclass(RateLimitError, Exception)


def test_mock_connector_schema():
    c = MockBankConnector("mock")
    accounts = c.get_accounts()
    assert len(accounts) == 1
    assert accounts[0]["iban"].startswith("DE")
    txs = c.get_transactions(accounts[0], days_back=28)
    assert txs, "Mock muss Transaktionen liefern"
    required = {"external_id", "buchungsdatum", "valutadatum", "betrag", "waehrung",
                "partner_name", "verwendungszweck", "raw_data"}
    for tx in txs:
        assert required <= set(tx.keys())
        assert isinstance(tx["betrag"], Decimal)
        assert isinstance(tx["buchungsdatum"], dt.date)


def test_mock_external_id_stability():
    c = MockBankConnector("mock")
    acct = c.get_accounts()[0]
    txs1 = c.get_transactions(acct, days_back=28)
    txs2 = c.get_transactions(acct, days_back=28)
    ids1 = [t["external_id"] for t in txs1]
    ids2 = [t["external_id"] for t in txs2]
    assert ids1 == ids2  # deterministisch → Dedupe-fähig


def test_credentials_env_fallback(monkeypatch):
    monkeypatch.setenv("FT_TESTBANK_BLZ", "10000000")
    monkeypatch.setenv("FT_TESTBANK_LOGIN", "user1")
    monkeypatch.setenv("FT_TESTBANK_PIN", "secret-pin")
    monkeypatch.setenv("FT_TESTBANK_URL", "https://example.org/fints")
    creds = get_credentials("testbank")
    assert creds == {
        "blz": "10000000", "login": "user1",
        "pin": "secret-pin", "fints_url": "https://example.org/fints",
    }


def test_credentials_missing_raises(monkeypatch):
    monkeypatch.setattr("app.fints_credentials.keyring", None, raising=False)
    # keyring-Import fehlt → Env-Fallback → LookupError wenn unvollständig
    import app.fints_credentials as fc

    def _no_keyring(*a, **k):
        raise ImportError("kein keyring in Tests")

    monkeypatch.setattr("keyring.get_password", _no_keyring, raising=False)
    with pytest.raises(LookupError):
        get_credentials("nichtexistierende-bank-xyz")