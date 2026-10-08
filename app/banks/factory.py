"""Connector-Factory: bank_name -> Connector-Instanz."""
from __future__ import annotations

from typing import Callable

from ..config import settings
from .base import BankConnector, BankConnectionError, RateLimitError, TanRequired  # noqa: F401


def get_connector(bank_name: str, tan_handler: Callable | None = None) -> BankConnector:
    name = bank_name.strip().lower()
    if name == "mock":
        from .mock import MockBankConnector

        return MockBankConnector("Mock Bank")
    if name == "comdirect":
        from .comdirect import ComdirectConnector

        return ComdirectConnector(tan_handler=tan_handler)
    if name == "dkb":
        from .dkb import DkbConnector

        return DkbConnector(tan_handler=tan_handler)
    raise ValueError(f"Unbekannte Bank: {bank_name!r} (erlaubt: comdirect, dkb, mock)")



def configured_banks() -> list[str]:
    return settings.banks