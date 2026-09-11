"""DKB FinTS-Connector."""
from __future__ import annotations

from .fints_base import FinTSConnector


class DkbConnector(FinTSConnector):
    bank_name = "dkb"
    fints_url = "https://banking-dkb.s-fints-pt-fsn.de/fints30"
    blz = "30050553"