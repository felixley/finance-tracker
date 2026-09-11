"""Connector-Factory: bank_name -> Connector-Instanz."""
from __future__ import annotations

from ..config import settings
from .base import BankConnector, BankConnectionError, RateLimitError, TanRequired  # noqa: F401


def get_connector(bank_name: str) -> BankConnector:
    name = bank_name.strip().lower()
    if name == "mock":
        from .mock import MockBankConnector

        return MockBankConnector("Mock Bank")
    if name == "comdirect":
        from .comdirect import ComdirectConnector

        return ComdirectConnector()
    if name == "dkb":
        from .dkb import DkbConnector

        return DkbConnector()
    raise ValueError(f"Unbekannte Bank: {bank_name!r} (erlaubt: comdirect, dkb, mock)")


def configured_banks() -> list[str]:
    return settings.banks