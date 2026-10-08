#!/usr/bin/env python
"""Phase-1-Skript: FinTS-Verbindungen testen / Transaktionen abrufen (TAN interaktiv).

Orientiert sich an ~/coding/finance-tracker-test/testverbindung.py: photoTAN-
Grafik dekodieren, im Viewer öffnen, TAN abfragen und per ``send_tan`` bestätigen.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.banks.base import BankConnectionError, RateLimitError, TanRequired  # noqa: E402
from app.banks.factory import get_connector  # noqa: F402


def _enable_debug() -> None:
    """Zeigt den rohen FinTS-Antwortcode (z.B. 9010 / 9340 / 9910) an."""
    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(name)s: %(message)s")
    for name in ("fints", "fints.client", "fints.dialog"):
        logging.getLogger(name).setLevel(logging.DEBUG)


def _show_image(image_bytes: bytes, mime_type: str = "image/png") -> None:
    """Schreibt die Bilddaten in eine Temp-Datei und öffnet sie im Standard-Viewer."""
    suffix = "." + mime_type.split("/")[-1].replace("jpeg", "jpg") if "/" in mime_type else ".png"
    path = os.path.join(tempfile.gettempdir(), "fints_phototan" + suffix)
    with open(path, "wb") as writer:
        writer.write(image_bytes)
    print(f"-> Bild gespeichert: {path}")
    try:
        webbrowser.open("file://" + path)
    except Exception:  # headless/Container
        pass


def _send_tan(response, tan_code):
    """Ruft ``client.send_tan`` auf dem vom Connector gehaltenen Client auf."""
    connector = _HOLDER.get("connector")
    client = getattr(connector, "_client", None)
    if client is None:
        raise RuntimeError("Kein FinTS-Client für send_tan verfügbar.")
    return client.send_tan(response, tan_code)


def interactive_tan_handler(response):
    """Behandelt eine decoupled/photoTAN-Freigabe (NeedTANResponse) interaktiv.

    Portiert aus der funktionierenden Referenz (testverbindung.py)."""
    from fints.utils import decode_phototan_image

    print("\n--- photoTAN-Grafik angefordert ---")
    if getattr(response, "challenge_matrix", None):
        mime_type, matrix_data = response.challenge_matrix[0], response.challenge_matrix[1]
        print(f"Grafik gefunden (MIME: {mime_type}). Öffne Bild...")
        try:
            _show_image(matrix_data, mime_type)
            print("-> Bitte scannen Sie die Grafik mit Ihrer photoTAN-App!")
        except Exception as e:
            print(f"Fehler beim Rendern der Grafik: {e}")
            print("Alternativer Text-Challenge:", response.challenge)
    elif getattr(response, "challenge_hhduc", None):
        print("challenge_hhduc gefunden. Dekodiere Challenge...")
        try:
            decoded = decode_phototan_image(response.challenge_hhduc)
            print(f"Dekodiert (MIME: {decoded['mime_type']}). Öffne Bild...")
            _show_image(decoded["image"], decoded["mime_type"])
            print("-> Bitte scannen Sie die Grafik mit Ihrer photoTAN-App!")
        except Exception as e:
            print(f"Fehler beim Dekodieren der hhduc-Challenge: {e}")
            print("Alternativer Text-Challenge:", response.challenge)
    else:
        print(response.challenge)

    tan_code = input("\nBitte geben Sie die in der photoTAN-App angezeigte TAN ein: ").strip()
    print("Sende Bestätigung an die Bank...")
    return _send_tan(response, tan_code)


# Halter, damit der TAN-Handler den Client des Connectors erreicht
_HOLDER: dict = {}


def probe(bank: str, days: int, dump: bool, test_connection: bool, debug: bool) -> int:
    if debug:
        _enable_debug()
    try:
        connector = get_connector(bank, tan_handler=interactive_tan_handler)
    except ValueError as e:
        print(f"Fehler: {e}")
        return 2
    _HOLDER["connector"] = connector
    try:
        accounts = connector.get_accounts()
        print(f"[{bank}] OK — {len(accounts)} Konto/Konten:")
        for a in accounts:
            print(f"  IBAN {a.get('iban')}  Saldo {a.get('balance')}")
        if test_connection:
            return 0
        all_txs = []
        for acct in accounts:
            txs = connector.get_transactions(acct, days_back=days)
            all_txs.extend(txs)
        print(f"[{bank}] {len(all_txs)} Buchungen abgerufen.")

        if dump:
            out = Path(f"data/fints_dump_{bank}.json")
            out.parent.mkdir(exist_ok=True)
            with out.open("w", encoding="utf-8") as f:
                json.dump(
                    [{**t, "betrag": str(t["betrag"])} for t in all_txs],
                    f,
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                )
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
    p.add_argument("--debug", action="store_true", help="Rohen FinTS-Antwortcode + Logging ausgeben")
    args = p.parse_args()
    sys.exit(probe(args.bank, args.days, args.dump, args.test_connection, args.debug))


if __name__ == "__main__":
    main()