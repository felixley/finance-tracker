"""Bank-Zugangsdaten: verschlüsseltes File-Backend (bevorzugt) oder Env-Fallback (headless).

Ablage: ~/.config/finance-tracker/credentials.enc — Fernet (AES128-CBC+HMAC),
Master-Key liegt in einer SEPARATEN Datei (~/.config/finance-tracker/master.key,
chmod 600), NICHT im Projektverzeichnis und NICHT in der .env."""
from __future__ import annotations

import json
import logging
import os
import stat
from pathlib import Path

logger = logging.getLogger(__name__)

SERVICE = "finance-tracker"


def _paths() -> tuple[Path, Path, Path]:
    """Store-Pfade lazy ermitteln (ENV-Override für Tests)."""
    base = Path(os.getenv("FINANCE_TRACKER_SECRETS_DIR", Path.home() / ".config" / "finance-tracker"))
    return base, base / "credentials.enc", base / "master.key"


def _enforce_600(path: Path) -> None:
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise PermissionError(f"{path} hat zu offene Rechte ({stat.filemode(mode)}) — chmod 600 nötig.")


def _load_fernet(key_file: Path):
    from cryptography.fernet import Fernet

    if not key_file.exists():
        raise FileNotFoundError(f"Master-Key fehlt: {key_file}")
    _enforce_600(key_file)
    return Fernet(key_file.read_bytes().strip())


def _read_store() -> dict:
    """Liefert {bank: {blz, login, pin, fints_url}} aus der verschlüsselten Ablage."""
    _, creds_file, key_file = _paths()
    if not creds_file.exists():
        return {}
    _enforce_600(creds_file)
    return json.loads(_load_fernet(key_file).decrypt(creds_file.read_bytes()))


def _write_store(data: dict) -> None:
    store_dir, creds_file, key_file = _paths()
    store_dir.mkdir(parents=True, exist_ok=True)
    if not key_file.exists():
        from cryptography.fernet import Fernet

        key_file.write_bytes(Fernet.generate_key())
        os.chmod(key_file, 0o600)
    os.chmod(store_dir, 0o700)
    creds_file.write_bytes(_load_fernet(key_file).encrypt(json.dumps(data).encode()))
    os.chmod(creds_file, 0o600)


def _allow_insecure_env() -> bool:
    """Env-Fallback speichert/sendet PINs im Klartext (Umgebungsvariablen). Er ist
    nur für headless CI/Entwicklung gedacht und muss bewusst aktiviert werden
    (ALLOW_INSECURE_ENV_CREDS=1)."""
    return os.getenv("ALLOW_INSECURE_ENV_CREDS", "").strip().lower() in ("1", "true", "yes")


def get_credentials(bank: str) -> dict:
    """Liefert {blz, login, pin, fints_url, tan_mechanism, product_id}.
    Verschlüsselte Ablage first, Env-Fallback nur wenn ALLOW_INSECURE_ENV_CREDS=1
    — sonst Fail-closed."""
    bank = bank.lower()
    _, creds_file, _ = _paths()
    try:
        store = _read_store()
        if bank in store:
            return store[bank]
    except Exception as e:
        logger.warning("Verschlüsselte Credential-Ablage nicht lesbar (%s).", e)

    if not _allow_insecure_env():
        raise LookupError(
            f"Keine Zugangsdaten für {bank!r}: Ablage leer/fehlerhaft ({creds_file}), "
            f"Env-Fallback deaktiviert (setze ALLOW_INSECURE_ENV_CREDS=1 oder "
            f"hinterlege via 'python -m app.fints_credentials set {bank}')."
        )

    prefix = f"FT_{bank.upper()}_"
    creds = {
        "blz": os.getenv(prefix + "BLZ", ""),
        "login": os.getenv(prefix + "LOGIN", ""),
        "pin": os.getenv(prefix + "PIN", ""),
        "fints_url": os.getenv(prefix + "URL", "") or os.getenv(prefix + "HBCI", ""),
        "tan_mechanism": os.getenv(prefix + "TAN_MECHANISM", ""),
        "product_id": os.getenv(prefix + "PRODUCT_ID", ""),
    }
    if not all(creds[k] for k in ("blz", "login", "pin", "fints_url")):
        missing = [k for k in ("blz", "login", "pin", "fints_url") if not creds[k]]
        raise LookupError(
            f"Keine Zugangsdaten für {bank!r} (Ablage leer, Env unvollständig: {missing}). "
            f"Hinterlegen via 'python -m app.fints_credentials set {bank}'."
        )
    return creds


def set_credentials(bank: str, blz: str, login: str, pin: str, fints_url: str,
                    tan_mechanism: str = "", product_id: str = "") -> None:
    """Speichert Credentials verschlüsselt in der File-Ablage. PIN landet nie in Logs/Repo."""
    data = _read_store()
    data[bank.lower()] = {
        "blz": blz, "login": login, "pin": pin, "fints_url": fints_url,
        "tan_mechanism": tan_mechanism, "product_id": product_id,
    }
    _write_store(data)
    logger.info("Credentials für %s verschlüsselt gespeichert (%s).", bank, _paths()[1])


def stored_banks() -> list[str]:
    """Namen der Banken in der verschlüsselten Ablage — OHNE Geheimnisse.

    Keyring-tauglicher Status-Check für das Dashboard: liefert nie PIN/Login."""

    try:
        return sorted(_read_store().keys())
    except Exception as e:  # pragma: no cover
        logger.warning("Credential-Ablage nicht lesbar (%s).", e)
        return []


def delete_credentials(bank: str) -> bool:
    """Entfernt die Credentials einer Bank. True, wenn etwas gelöscht wurde."""
    bank = bank.lower()
    data = _read_store()
    if bank not in data:
        return False
    del data[bank]
    _write_store(data)
    logger.info("Credentials für %s entfernt (%s).", bank, _paths()[1])
    return True


if __name__ == "__main__":
    import argparse
    import getpass

    p = argparse.ArgumentParser(description="Bank-Credentials verschlüsselt verwalten")
    p.add_argument("action", choices=["set", "check"])
    p.add_argument("bank", choices=["comdirect", "dkb"])
    args = p.parse_args()
    if args.action == "set":
        defaults = {"comdirect": ("20041133", "https://fints.comdirect.de/fints/hbci", "902"),
                    "dkb": ("12030000", "https://fints.dkb.de/fints", "940")}
        d_blz, d_url, d_tan = defaults[args.bank]
        blz = input(f"BLZ [{d_blz}]: ").strip() or d_blz
        login = input("Login/Benutzerkennung: ")
        pin = getpass.getpass("PIN: ")
        url = input(f"FinTS-URL [{d_url}]: ").strip() or d_url
        tan = input(f"TAN-Verfahren (HKTAN, z.B. {d_tan}): ").strip() or d_tan
        product_id = input("Produkt-ID [Standard]: ").strip()
        set_credentials(args.bank, blz, login, pin, url,
                        tan_mechanism=tan, product_id=product_id)
        print(f"Gespeichert (verschlüsselt in {_paths()[1]}).")
    else:
        try:
            creds = get_credentials(args.bank)
            print(f"Credentials vorhanden (BLZ {creds['blz']}, Login {creds['login']}).")
        except LookupError as e:
            print(f"Fehlt: {e}")
