"""Gemeinsame FinTS-Logik für echte Banken (Comdirect/DKB).

Orientiert sich an der nachweislich funktionierenden Referenz
(~/coding/finance-tracker-test/testverbindung.py):

  * echte, bei der Bank registrierte ``product_id`` (nicht "finance-tracker")
  * TAN-Verfahren VOR dem Login-Dialog laden/auswählen
    (``fetch_tan_mechanisms`` + ``set_tan_mechanism``)
  * optionaler ``minimal_interactive_cli_bootstrap`` (TAN-Medium-Auswahl)
  * decoupled/photoTAN-Freigabe (``NeedTANResponse``) beim Login UND beim
    Umsatzabruf behandeln (Grafik dekodieren → TAN abfragen → ``send_tan``)

Die zuvor im Code vorhandenen ``customer_id``/System-ID-Workarounds sind in
der funktionierenden Referenz NICHT nötig und wurden entfernt.
"""
from __future__ import annotations

import datetime as dt
import logging
from decimal import Decimal
from typing import Callable

from fints.client import FinTS3PinTanClient

from ..fints_credentials import get_credentials
from .base import BankConnectionError, BankConnector, RateLimitError, TanRequired

logger = logging.getLogger(__name__)

# Bei der comdirect registrierte Produkt-ID (siehe Referenz-Skript).
# Ohne gültige Produkt-ID lehnt comdirect die FinTS-Verbindung ab.
DEFAULT_PRODUCT_ID = "6151256F3D4F9975B877BD4A2"

# Signatur: tan_handler(response) -> NeedTANResponse|None  (None = Einmal-Freigabe)
TanHandler = Callable[[object], object]


class FinTSConnector(BankConnector):
    """Basisklasse für PIN/TAN-FinTS-Connectors."""

    fints_url: str = ""
    blz: str = ""
    bank_name: str = ""
    product_id: str = DEFAULT_PRODUCT_ID
    # TAN-Verfahren (HKTAN-Sicherheitsfunktion) des Kontos, z.B. "902" (comdirect
    # photoTAN) bzw. "940" (DKB App/decoupled). Leer = Bank entscheidet/CLI fragt.
    tan_mechanism: str = ""

    def __init__(self, bank_name: str | None = None,
                 tan_handler: TanHandler | None = None):
        super().__init__(bank_name if bank_name is not None else type(self).bank_name)
        self._client: FinTS3PinTanClient | None = None
        # Wird bei decoupled/photoTAN-Freigabe aufgerufen. Default: TanRequired
        # werfen (automatischer Sync bricht ab und überspringt die Bank).
        self._tan_handler: TanHandler = tan_handler or self._raise_tan_required

    # ------------------------------------------------------------------ #
    # Verbindungsaufbau
    # ------------------------------------------------------------------ #
    def _connect(self) -> FinTS3PinTanClient:
        creds = self._credentials()
        url = self.fints_url or creds.get("fints_url", "")
        product_id = creds.get("product_id") or self.product_id
        try:
            client = FinTS3PinTanClient(
                self.blz,
                user_id=creds["login"],
                pin=creds["pin"],
                server=url,
                product_id=product_id,
            )
        except Exception as e:
            logger.error("%s: Verbindung fehlgeschlagen: %s", self.bank_name, e)
            raise BankConnectionError(str(e)) from e

        # TAN-Verfahren VOR dem Login-Dialog setzen (wie in der Referenz).
        self._select_tan_mechanism(client, creds.get("tan_mechanism") or self.tan_mechanism)
        # Optionales interaktives Bootstrap (TAN-Medium-Auswahl).
        self._interactive_bootstrap(client)
        self._client = client
        return client

    def _select_tan_mechanism(self, client: FinTS3PinTanClient, mechanism: str) -> None:
        """Lädt die verfügbaren TAN-Verfahren und wählt das gewünschte aus."""
        try:
            client.fetch_tan_mechanisms()
        except Exception as e:  # pragma: no cover — nicht jede Bank liefert HKTAN
            logger.warning("%s: TAN-Verfahren nicht abrufbar (%s).", self.bank_name, e)
            return
        if not mechanism:
            return
        try:
            client.set_tan_mechanism(mechanism)
        except Exception as e:
            logger.warning(
                "%s: TAN-Verfahren %r nicht setzbar (%s) — es wird das "
                "Bank-Standardverfahren verwendet.",
                self.bank_name, mechanism, e,
            )

    def _interactive_bootstrap(self, client: FinTS3PinTanClient) -> None:
        """Fragt TAN-Medium etc. interaktiv ab (nur wenn eine Konsole vorhanden ist)."""
        try:
            from fints.utils import minimal_interactive_cli_bootstrap
        except ImportError:  # pragma: no cover
            return
        try:
            minimal_interactive_cli_bootstrap(client)
        except Exception as e:  # z.B. EOFError ohne stdin (Container/Scheduler)
            logger.debug("%s: interaktives Bootstrap übersprungen (%s).", self.bank_name, e)

    def _credentials(self) -> dict:
        return get_credentials(self.bank_name.lower())

    # ------------------------------------------------------------------ #
    # Decoupled/photoTAN-Freigabe
    # ------------------------------------------------------------------ #
    def _raise_tan_required(self, response) -> object:
        raise TanRequired(self._tan_mechanism(self._client))

    def _resolve_tan(self, client: FinTS3PinTanClient, response):
        """Reicht eine NeedTANResponse an den Handler weiter und gibt das Ergebnis zurück."""
        if response is None:
            return None
        from fints.client import NeedTANResponse

        if not isinstance(response, NeedTANResponse):
            return response
        return self._tan_handler(response)

    # ------------------------------------------------------------------ #
    # Dialogführung inkl. SCA/90-Tage-Freigabe
    # ------------------------------------------------------------------ #
    def _enter_and_authorize(self, client: FinTS3PinTanClient) -> FinTS3PinTanClient:
        """Öffnet den stehenden Dialog (``with client:``) und behandelt eine
        SCA-/90-Tage-Freigabe (``init_tan_response``).

        Wichtig: ``init_tan_response`` wird erst beim Dialog-Init gesetzt, also
        erst wenn in den Kontextmanager eingetreten wird. Genau wie in der
        Referenz (testverbindung.py) muss daher ZUERST ``with client:`` betreten
        und danach ggf. ``init_tan_response`` freigegeben werden.
        """
        from fints.client import NeedTANResponse

        client.__enter__()  # Dialog-Init -> setzt ggf. init_tan_response
        init = getattr(client, "init_tan_response", None)
        if isinstance(init, NeedTANResponse):
            client.init_tan_response = self._resolve_tan(client, init)
        return client

    def _exit(self, client: FinTS3PinTanClient, *exc) -> None:
        try:
            client.__exit__(*exc)
        except Exception:  # pragma: no cover — Aufräumen darf nie werfen
            logger.debug("%s: Dialog-Abbau fehlgeschlagen.", self.bank_name)

    def _connected(self) -> FinTS3PinTanClient:
        """Verbindet, betritt den stehenden Dialog und autorisiert (SCA/TAN)."""
        client = self._connect()
        return self._enter_and_authorize(client)

    # ------------------------------------------------------------------ #
    # BankConnector-Interface
    # ------------------------------------------------------------------ #
    def get_accounts(self) -> list[dict]:
        from fints.exceptions import FinTSError

        client = self._connected()
        try:
            accounts = client.get_sepa_accounts()
        except FinTSError as e:
            if "tan" in str(e).lower():
                raise TanRequired(self._tan_mechanism(client)) from e
            raise BankConnectionError(str(e)) from e
        finally:
            self._exit(client)
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

        client = self._connected()
        end = dt.date.today()
        start = end - dt.timedelta(days=days_back)
        try:
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

            # Erneute Freigabe für den Umsatzabruf (decoupled/photoTAN).
            resp = self._resolve_tan(client, resp)
        finally:
            self._exit(client)

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

    # ------------------------------------------------------------------ #
    # Helfer
    # ------------------------------------------------------------------ #
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


