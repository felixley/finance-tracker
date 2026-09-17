"""Gemeinsame FinTS-Logik für echte Banken (Comdirect/DKB)."""
from __future__ import annotations

import datetime as dt
import logging
from decimal import Decimal

from fints.client import FinTS3PinTanClient
from fints.formals import CUSTOMER_ID_ANONYMOUS

from ..fints_credentials import get_credentials
from .base import BankConnectionError, BankConnector, RateLimitError, TanRequired

logger = logging.getLogger(__name__)


class FinTSConnector(BankConnector):
    """Basisklasse für PIN/TAN-FinTS-Connectors."""

    fints_url: str = ""
    blz: str = ""
    bank_name: str = ""
    product_id: str = "finance-tracker"

    def __init__(self, bank_name: str | None = None):
        super().__init__(bank_name if bank_name is not None else type(self).bank_name)
        self._client: FinTS3PinTanClient | None = None
        try:
            from fints.client import FinTS3PinTanClient  # noqa: F401
        except ImportError as e:  # pragma: no cover
            raise BankConnectionError(f"fints package fehlt: {e}") from e

    def _connect(self) -> "FinTS3PinTanClient":
        creds = self._credentials()
        try:
            from fints.client import FinTS3PinTanClient

            client = FinTS3PinTanClient(
                self.blz,
                user_id=creds["login"],
                pin=creds["pin"],
                server=self.fints_url or creds.get("fints_url", ""),
                product_id=self.product_id,
                customer_id=CUSTOMER_ID_ANONYMOUS,
            )
        except Exception as e:
            logger.error("%s: Verbindung fehlgeschlagen: %s", self.bank_name, e)
            raise BankConnectionError(str(e)) from e
        self._client = client
        return client

    def _connect_with_tan(self) -> "FinTS3PinTanClient":
        """Verbindet; bei TAN-Anforderung wird TanRequired mit Mechanismus geworfen."""
        client = self._connect()
        try:
            client.init_tan_response
        except AttributeError:
            pass
        return client

    def _credentials(self) -> dict:
        from ..fints_credentials import get_credentials

        return get_credentials(self.bank_name.lower())

    def get_accounts(self) -> list[dict]:
        from fints.exceptions import FinTSError

        client = self._connect()
        try:
            accounts = client.get_sepa_accounts()
        except FinTSError as e:
            if "tan" in str(e).lower():
                raise TanRequired(self._tan_mechanism(client)) from e
            raise BankConnectionError(str(e)) from e
        return [
            {
                "iban": str(a.iban or ""),
                "balance": None,
                "raw": {"account_number": str(a.account_number)},
            }
            for a in accounts
        ]

    def get_transactions(self, account: dict, days_back: int = 90) -> list[dict]:
        from fints.exceptions import FinTSError

        client = self._connect()
        end = dt.date.today()
        start = end - dt.timedelta(days=days_back)
        target = self._find_account(client, account.get("iban", ""))
        if target is None:
            raise BankConnectionError(
                f"Konto {account.get('iban')} bei {self.bank_name} nicht gefunden"
            )
        try:
            resp = client.get_transactions(target, start_date=start, end_date=end)
        except FinTSError as e:
            msg = str(e).lower()
            if "tan" in msg:
                raise TanRequired(self._tan_mechanism(client)) from e
            if "rate" in msg or "limit" in msg:
                raise RateLimitError(str(e)) from e
            raise BankConnectionError(str(e)) from e

        out: list[dict] = []
        for tx in resp or []:
            data = tx.data
            amount = data.get("amount_value") or Decimal("0")
            currency = str(data.get("amount_currency") or "EUR")
            date = data.get("date")
            entry = {
                "external_id": self._external_id(tx, data),
                "buchungsdatum": date if isinstance(date, dt.date) else end,
                "valutadatum": data.get("guad") if isinstance(data.get("guad"), dt.date) else None,
                "betrag": Decimal(str(amount)),
                "waehrung": currency,
                "partner_name": self._partner_name(data),
                "verwendungszweck": " ".join(
                    str(x) for x in (data.get("purpose") or [])
                ) or None,
                "raw_data": {
                    "iban": account.get("iban"),
                    "raw_fields": {k: str(v) for k, v in data.items()
                                   if k in ("applicant_name", "end_to_end", "posting_text",
                                            "prima_nota", "sepa_counterparty_iban")},
                },
            }
            out.append(entry)
        logger.info("%s: %d Buchungen abgerufen", self.bank_name, len(out))
        return out

    def _find_account(self, client, iban: str):
        try:
            for acc in client.get_sepa_accounts():
                if str(acc.iban or "") == iban:
                    return acc
        except Exception:
            return None
        return None

    @staticmethod
    def _tan_mechanism(client) -> str:
        try:
            tan_modes = client.get_tan_mechanisms()
            for name, m in tan_modes.items():
                if "push" in str(getattr(m, "name", name)).lower():
                    return "pushTAN (App)"
                if "chip" in str(getattr(m, "name", name)).lower():
                    return "chipTAN"
            return str(list(tan_modes.values())[:1])
        except Exception:
            return "unknown"

    @staticmethod
    def _external_id(tx, data) -> str:
        import hashlib

        base = (
            str(data.get("id") or "")
            or str(data.get("end_to_end") or "")
            or f"{data.get('date')}|{data.get('amount_value')}|{data.get('applicant_name')}"
        )
        return hashlib.sha256(base.encode()).hexdigest()[:32]

    @staticmethod
    def _partner_name(data) -> str | None:
        for k in ("applicant_name", "sepa_counterparty_name"):
            if data.get(k):
                return str(data[k])
        return None


from fints.client import FinTS3PinTanClient  # noqa: E402  (für Typannotation)