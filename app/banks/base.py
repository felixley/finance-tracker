"""Basis-Klasse und Fehlerklassen für Bank-Connectors."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from decimal import Decimal

logger = logging.getLogger(__name__)


class BankConnectionError(Exception):
    """Verbindungsfehler zur Bank (Netzwerk, Server nicht erreichbar)."""


class TanRequired(Exception):
    """TAN-Pflicht — interaktive Eingabe nötig (chipTAN/pushTAN)."""

    def __init__(self, tan_mechanism: str = "unknown", message: str | None = None):
        self.tan_mechanism = tan_mechanism
        super().__init__(message or f"TAN erforderlich ({tan_mechanism})")


class RateLimitError(Exception):
    """Rate-Limit/zu viele Anfragen bei der Bank."""


class BankConnector(ABC):
    def __init__(self, bank_name: str):
        self.bank_name = bank_name

    @abstractmethod
    def get_accounts(self) -> list[dict]:
        """Liefert Liste von Konten: {iban, balance (Decimal|None)}."""

    @abstractmethod
    def get_transactions(self, account: dict, days_back: int = 90) -> list[dict]:
        """Liefert Transaktions-Dicts:
        {external_id, buchungsdatum, valutadatum, betrag (Decimal), waehrung,
         partner_name, verwendungszweck, raw_data (dict)}"""