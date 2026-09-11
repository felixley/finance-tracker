"""ETL-Pipeline: clean → external_id → sync mit Dedupe."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from .banks.base import BankConnectionError, RateLimitError, TanRequired
from .banks.factory import get_connector
from .db import SessionLocal
from .models import Account, Transaction

logger = logging.getLogger(__name__)


def clean(tx: dict) -> dict | None:
    """Bereinigt einen Roh-Transaktions-Dict. None = verwerfen (mit Log)."""
    if not isinstance(tx, dict):
        logger.warning("Roh-Datensatz kein dict: %r — übersprungen", tx)
        return None
    out = dict(tx)
    for k in ("partner_name", "verwendungszweck"):
        if out.get(k) is not None:
            out[k] = " ".join(str(out[k]).split()) or None
    if out.get("waehrung") in (None, ""):
        out["waehrung"] = "EUR"
    try:
        # Deutsche Notation (-52,30 bzw. 1.234,56) zuerst normalisieren
        raw_amount = str(out["betrag"]).strip()
        if "," in raw_amount:
            raw_amount = raw_amount.replace(".", "").replace(",", ".")
        out["betrag"] = Decimal(raw_amount)
    except (InvalidOperation, KeyError) as e:
        logger.warning("Ungültiger Betrag (%s) — übersprungen: %r", e, tx)
        return None
    for k in ("buchungsdatum", "valutadatum"):
        v = out.get(k)
        if isinstance(v, str):
            try:
                out[k] = dt.date.fromisoformat(v[:10])
            except ValueError:
                out[k] = None
        if out.get("buchungsdatum") is None:
            logger.warning("Fehlendes Buchungsdatum — übersprungen: %r", tx)
            return None
    return out


def compute_external_id(tx: dict, bank_name: str = "", iban: str = "") -> str:
    """Stabile Deterministik-ID für Dedupe (unabhängig vom Connector)."""
    raw = "|".join(
        str(x)
        for x in (
            bank_name,
            iban,
            tx.get("buchungsdatum").isoformat() if tx.get("buchungsdatum") else "",
            tx.get("betrag"),
            tx.get("partner_name") or "",
            tx.get("verwendungszweck") or "",
        )
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def sync_bank(
    bank_name: str,
    days_back: int | None = None,
    dump_path: str | None = None,
    db: Session | None = None,
) -> dict:
    days = days_back if days_back is not None else 90
    own = db is None
    if own:
        db = SessionLocal()
    try:
        connector = get_connector(bank_name)
        logger.info("Sync-Start: %s (days_back=%d)", bank_name, days)
        accounts = connector.get_accounts()
        logger.info("%s: %d Konto/Konten", bank_name, len(accounts))
        inserted = skipped = 0
        for acct in accounts:
            iban = acct.get("iban") or ""
            account = (
                db.query(Account).filter_by(bank_name=connector.bank_name, iban=iban).first()
            )
            if account is None:
                account = Account(
                    bank_name=connector.bank_name,
                    iban=iban,
                    balance=acct.get("balance"),
                    last_synced_at=dt.datetime.now(),
                )
                db.add(account)
                db.flush()
            else:
                if acct.get("balance") is not None:
                    account.balance = acct["balance"]
                account.last_synced_at = dt.datetime.now()
            raw_txs = connector.get_transactions(acct, days_back=days)
            if dump_path:
                with open(dump_path, "w", encoding="utf-8") as f:
                    json.dump(
                        [{**t, "betrag": str(t["betrag"])} for t in raw_txs],
                        f, ensure_ascii=False, indent=2, default=str,
                    )
                logger.info("Dump geschrieben: %s", dump_path)
            for raw in raw_txs:
                tx = clean(raw)
                if tx is None:
                    continue
                ext_id = tx.get("external_id") or compute_external_id(
                    tx, connector.bank_name, iban
                )
                exists = db.query(Transaction).filter_by(external_id=ext_id).first()
                if exists:
                    skipped += 1
                    continue
                db.add(
                    Transaction(
                        external_id=ext_id,
                        account_id=account.id,
                        buchungsdatum=tx["buchungsdatum"],
                        valutadatum=tx.get("valutadatum"),
                        betrag=tx["betrag"],
                        waehrung=tx.get("waehrung") or "EUR",
                        partner_name=tx.get("partner_name"),
                        verwendungszweck=tx.get("verwendungszweck"),
                        raw_data=tx.get("raw_data"),
                    )
                )
                inserted += 1
        db.commit()
        summary = {
            "bank": bank_name, "inserted": inserted, "skipped": skipped,
            "accounts": len(accounts),
        }
        logger.info("Sync-Ende: %s → %s", bank_name, summary)
        return summary
    except TanRequired as e:
        logger.warning(
            "%s: TAN erforderlich (%s) — interaktiv via scripts/fints_probe.py abrufen",
            bank_name, e.tan_mechanism,
        )
        raise
    except RateLimitError as e:
        logger.error("%s: Rate-Limit: %s", bank_name, e)
        raise
    except BankConnectionError as e:
        logger.error("%s: Verbindungsfehler: %s", bank_name, e)
        raise
    finally:
        if own:
            db.close()


def sync_all(days_back: int | None = None, banks: list[str] | None = None) -> dict:
    results: dict[str, dict] = {}
    errors: dict[str, str] = {}
    for bank in banks or ["mock"]:
        try:
            results[bank] = sync_bank(bank, days_back=days_back)
        except (BankConnectionError, RateLimitError, TanRequired, LookupError) as e:
            logger.error("Sync fehlgeschlagen für %s: %s", bank, e)
            errors[bank] = str(e)
    return {"results": results, "errors": errors}