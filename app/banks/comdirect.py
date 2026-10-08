"""Comdirect FinTS-Connector."""
from __future__ import annotations

from .fints_base import FinTSConnector


class ComdirectConnector(FinTSConnector):
    bank_name = "comdirect"
    # HBCI/FinTS-Endpunkt (Referenz: fints.comdirect.de/fints/hbci)
    fints_url = "https://fints.comdirect.de/fints/hbci"
    blz = "20041133"
    # photoTAN-Sicherheitsfunktion der comdirect (HKTAN).
    tan_mechanism = "902"
