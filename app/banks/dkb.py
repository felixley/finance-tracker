"""DKB FinTS-Connector."""
from __future__ import annotations

from .fints_base import FinTSConnector


class DkbConnector(FinTSConnector):
    bank_name = "dkb"
    # Neue FinTS-URL seit 25.11.2024 (Referenz: fints.dkb.de).
    fints_url = "https://fints.dkb.de/fints"
    blz = "12030000"
    # Freigabe über DKB-App (decoupled/pushTAN).
    tan_mechanism = "940"
