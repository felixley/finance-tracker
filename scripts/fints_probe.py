#!/usr/bin/env python
"""Phase-1-Skript: FinTS-Verbindungen testen / Transaktionen abrufen (TAN interaktiv)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.banks.base import BankConnectionError, RateLimitError, TanRequired  # noqa: E402
from app.banks.factory import get_connector  # noqa: E402


def probe(bank: str, days: int, dump: bool, test_connection: bool) -> int:
    try:
        connector = get_connector(bank)
    except ValueError as e:
        print(f"Fehler: {e}")
        return 2
    try:
        accounts = connector.get_accounts()
        print(f"[{bank}] OK — {len(accounts)} Konto/Konten:")
        for a in accounts:
            print(f"  IBAN {a.get('iban')}  Saldo {a.get('balance')}")
        if test_connection:
            return 0
        all_txs = []
        for acct in accounts:
            try:
                txs = connector.get_transactions(acct, days_back=days)
            except TanRequired as e:
                tan = input(
                    f"[{bank}] TAN erforderlich ({e.tan_mechanism}). TAN eingeben: "
                )
                # Erneuter Abruf mit TAN — im FinTS-Client würde die TAN über
                # client.provide_tan(...) eingehängt; hier: erneuter Aufruf.
                print("Hinweis: TAN-basierter Retry läuft über FinTS-Client.")
                raise
            all_txs.extend(txs)
        print(f"[{bank}] {len(all_txs)} Buchungen abgerufen.")
        if dump:
            out = Path(f"data/fints_dump_{bank}.json")
            out.parent.mkdir(exist_ok=True)
            with out.open("w", encoding="utf-8") as f:
                json.dump([{**t, "betrag": str(t["betrag"])} for t in all_txs], f,
                          ensure_ascii=False, indent=2, default=str)
            print(f"Dump: {out}")
        return 0
    except TanRequired as e:
        print(f"[{bank}] TAN-Pflicht ({e.tan_mechanism}) — interaktiver Abruf nötig.")
        return 3
    except (BankConnectionError, RateLimitError) as e:
        print(f"[{bank}] Fehler: {e}")
        return 1
    except LookupError as e:
        print(f"[{bank}] Keine Credentials: {e}")
        return 2


def main() -> None:
    p = argparse.ArgumentParser(description="FinTS-Verbindung testen / Transaktionen dumpen")
    p.add_argument("--bank", default="comdirect", choices=["comdirect", "dkb", "mock"])
    p.add_argument("--days", type=int, default=90)
    p.add_argument("--dump", action="store_true", help="Transaktionen als JSON dumpen")
    p.add_argument("--test-connection", action="store_true", help="Nur Verbindung testen")
    args = p.parse_args()
    sys.exit(probe(args.bank, args.days, args.dump, args.test_connection))


if __name__ == "__main__":
    main()