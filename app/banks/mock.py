"""Mock-Bank-Connector für Entwicklung und Tests — deterministische Fake-Transaktionen."""
from __future__ import annotations

import datetime as dt
import hashlib
from decimal import Decimal

from .base import BankConnector

_MERCHANTS = [
    ("REWE SAG Köln 112", "-52.30"),
    ("ALDI Sued Köln", "-33.15"),
    ("Netflix Entertainment", "-12.99"),
    ("Deutsche Bahn AG", "-89.50"),
    ("Gehalt Arbeitgeber X", "3200.00"),
    ("Miete Wohnung", "-950.00"),
    ("Restaurant Vapiano", "-34.80"),
    ("Techniker Krankenkasse", "-187.30"),
]

_IBAN = "DE02120300000000202051"


class MockBankConnector(BankConnector):
    """Erzeugt deterministische Transaktionen der letzten N Tage (Wiederholung alle 14 Tage)."""

    def get_accounts(self) -> list[dict]:
        return [{"iban": _IBAN, "balance": Decimal("4321.00")}]

    def get_transactions(self, account: dict, days_back: int = 90) -> list[dict]:
        today = dt.date.today()
        txs: list[dict] = []
        for offset in range(0, days_back, 14):
            day = today - dt.timedelta(days=offset)
            for i, (partner, amount) in enumerate(_MERCHANTS):
                date = day - dt.timedelta(days=i % 3)
                txs.append(
                    {
                        "external_id": self._make_id(date, partner, amount),
                        "buchungsdatum": date,
                        "valutadatum": date,
                        "betrag": Decimal(amount),
                        "waehrung": "EUR",
                        "partner_name": partner,
                        "verwendungszweck": f"{partner} Zahlung",
                        "raw_data": {"source": "mock", "merchant_index": i},
                    }
                )
        return txs

    @staticmethod
    def _make_id(date: dt.date, partner: str, amount: str) -> str:
        raw = f"mock|{_IBAN}|{date.isoformat()}|{amount}|{partner}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]