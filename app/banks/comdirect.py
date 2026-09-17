"""Comdirect FinTS-Connector."""
from __future__ import annotations

from .fints_base import FinTSConnector


class ComdirectConnector(FinTSConnector):
    bank_name = "comdirect"
    fints_url = "https://fints.comdirect.de/fints"
    blz = "20041133"