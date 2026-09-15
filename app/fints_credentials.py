"""Bank-Zugangsdaten: System-Keyring (bevorzugt) oder Env-Fallback (headless)."""
from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)

SERVICE = "finance-tracker"


def _allow_insecure_env() -> bool:
    """Env-Fallback speichert/sendet PINs im Klartext (Umgebungsvariablen). Er ist
    nur für headless CI/Entwicklung gedacht und muss bewusst aktiviert werden
    (ALLOW_INSECURE_ENV_CREDS=1)."""
    return os.getenv("ALLOW_INSECURE_ENV_CREDS", "").strip().lower() in ("1", "true", "yes")


def get_credentials(bank: str) -> dict:
    """Liefert {blz, login, pin, fints_url}. Keyring first, Env-Fallback (FT_<BANK>_*).

    Env-Fallback nur wenn ALLOW_INSECURE_ENV_CREDS=1 — sonst Fail-closed."""
    bank = bank.lower()
    try:
        import keyring

        raw = keyring.get_password(SERVICE, bank)
        if raw:
            return json.loads(raw)
    except Exception as e:
        logger.warning("Keyring nicht verfügbar (%s) — Fallback auf Env.", e)

    if not _allow_insecure_env():
        raise LookupError(
            f"Keine Zugangsdaten für {bank!r}: Keyring leer/verfügbar, "
            f"Env-Fallback deaktiviert (setze ALLOW_INSECURE_ENV_CREDS=1 oder "
            f"hinterlege via 'python -m app.fints_credentials set {bank}')."
        )

    prefix = f"FT_{bank.upper()}_"
    creds = {
        "blz": os.getenv(prefix + "BLZ", ""),
        "login": os.getenv(prefix + "LOGIN", ""),
        "pin": os.getenv(prefix + "PIN", ""),
        "fints_url": os.getenv(prefix + "URL", ""),
    }
    if not all(creds.values()):
        missing = [k for k, v in creds.items() if not v]
        raise LookupError(
            f"Keine Zugangsdaten für {bank!r} (Keyring leer, Env unvollständig: {missing}). "
            f"Hinterlegen via 'python -m app.fints_credentials set {bank}'."
        )
    return creds


def set_credentials(bank: str, blz: str, login: str, pin: str, fints_url: str) -> None:
    """Speichert Credentials im System-Keyring. PIN landet nie in Logs/Repo."""
    import keyring

    keyring.set_password(
        SERVICE, bank.lower(), json.dumps({
            "blz": blz, "login": login, "pin": pin, "fints_url": fints_url,
        })
    )
    logger.info("Credentials für %s im Keyring gespeichert.", bank)


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Bank-Credentials im Keyring verwalten")
    p.add_argument("action", choices=["set", "check"])
    p.add_argument("bank", choices=["comdirect", "dkb"])
    args = p.parse_args()
    if args.action == "set":
        blz = input("BLZ: ")
        login = input("Login/Benutzerkennung: ")
        pin = input("PIN: ")
        url = input(f"FinTS-URL [{args.bank}]: ")
        set_credentials(args.bank, blz, login, pin, url)
        print("Gespeichert (Keyring).")
    else:
        try:
            creds = get_credentials(args.bank)
            print(f"Credentials vorhanden (BLZ {creds['blz']}, Login {creds['login']}).")
        except LookupError as e:
            print(f"Fehlt: {e}")