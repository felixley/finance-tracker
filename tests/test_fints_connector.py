"""Tests: FinTS-Connector-Verkabelung (Produkt-ID, TAN-Verfahren, SCA/TAN-Flow).

Ohne echte Bank: der FinTS3PinTanClient wird durch einen Fake ersetzt. Prüft, dass
  * die bei der Bank registrierte Produkt-ID + HBCI-URL verwendet werden,
  * TAN-Verfahren VOR dem Login-Dialog gesetzt wird,
  * der stehende Dialog betreten und eine SCA-Freigabe (NeedTANResponse)
    über den TAN-Handler freigegeben wird.
"""
from __future__ import annotations

import pytest

import app.banks.fints_base as fb
from app.banks.comdirect import ComdirectConnector


class FakeClient:
    def __init__(self, bank_identifier, user_id, pin, server, product_id=None, **kw):
        self.bank_identifier = bank_identifier
        self.user_id = user_id
        self.pin = pin
        self.server = server
        self.product_id = product_id
        self.mechanisms_fetched = False
        self.selected_mechanism = None
        self.init_tan_response = None
        self.entered = False
        self.exited = False

    def fetch_tan_mechanisms(self):
        self.mechanisms_fetched = True

    def set_tan_mechanism(self, sf):
        self.selected_mechanism = sf

    def get_tan_mechanisms(self):
        m = type("M", (), {"name": "photoTAN"})
        return {"902": m()}

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, *exc):
        self.exited = True


@pytest.fixture()
def creds(monkeypatch):
    data = {
        "blz": "20041133", "login": "u1", "pin": "p1",
        "fints_url": "https://fints.comdirect.de/fints/hbci",
        "tan_mechanism": "902", "product_id": "PID123",
    }
    monkeypatch.setattr(fb, "get_credentials", lambda bank: data)
    monkeypatch.setattr(fb, "FinTS3PinTanClient", FakeClient)
    # interaktives Bootstrap neutralisieren (kein stdin in Tests)
    monkeypatch.setattr(fb.FinTSConnector, "_interactive_bootstrap",
                        lambda self, client: None)
    return data


def test_connect_uses_product_id_and_selects_tan(creds):
    c = ComdirectConnector()
    client = c._connect()
    assert client.product_id == "PID123"
    assert client.server == "https://fints.comdirect.de/fints/hbci"
    assert client.bank_identifier == "20041133"
    assert client.user_id == "u1" and client.pin == "p1"
    assert client.mechanisms_fetched is True
    assert client.selected_mechanism == "902"


def test_connected_enters_dialog(creds):
    c = ComdirectConnector()
    client = c._connect()
    c._connect = lambda: client  # denselben Fake wiederverwenden
    c._connected()
    assert client.entered is True


def test_sca_need_tan_response_is_resolved(creds):
    from fints.client import NeedTANResponse

    class FakeNeedTAN(NeedTANResponse):
        def __init__(self):  # umgeht die echte __init__
            pass

    handled = []

    def handler(response):
        handled.append(response)
        return "RESUMED"

    c = ComdirectConnector(tan_handler=handler)
    client = c._connect()
    client.init_tan_response = FakeNeedTAN()
    c._client = client
    c._enter_and_authorize(client)
    assert handled, "TAN-Handler wurde für die SCA-Freigabe nicht aufgerufen"
    assert client.init_tan_response == "RESUMED"
