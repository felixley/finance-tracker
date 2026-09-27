"""FinTS-Diagnose: Fehlermeldungen interpretieren, Codes extrahieren, Sync-Log persistieren."""
from __future__ import annotations

import datetime as dt
import logging
import re

from sqlalchemy.orm import Session

from .models import SyncLog

logger = logging.getLogger(__name__)

# FinTS-Rückmeldungscodes (deutsch) — Quelle: projektinterne Diagnose (SKILL.md).
# 9942 & 9340 sind authentische Authentifizierungs-Responses der Bank, KEINE Code-Bugs.
FINTS_CODE_DE: dict[str, str] = {
    "9000": "Allgemeiner Fehler des Teilnehmer-/Zentralrechners",
    "9010": "Unberechtigter Nutzer — Zugang zu diesem Zeitpunkt nicht erlaubt",
    "9050": "Aktion derzeit nicht möglich (vorübergehende Sperre oder Zentralrechner-Fehler)",
    "9060": "Berechtigung für die Anforderung verweigert",
    "9100": "PIN fehlerhaft — Zugang möglicherweise gesperrt",
    "9340": "Ungültige Signatur (folgt meist auf eine falsche PIN)",
    "9800": "Allgemeine Zurückweisung — Nachricht vom Teilnehmer-/Zentralrechner abgelehnt",
    "9942": "PIN ungültig — die hinterlegte PIN ist falsch oder abgelaufen",
}

# Nur die spezifischen, verlässlich gedeuteten Codes hervorheben; der Rest bleibt generisch.
KNOWN_CODES = ("9942", "9340", "9100")


def extract_fints_codes(msg: str | None) -> list[str]:
    """Extrahiert 4-stellige FinTS-Fehlercodes (9942, 9340, 9050, …) aus einer Meldung."""
    if not msg:
        return []
    return [m for m in sorted(set(re.findall(r"\b(\d{4})\b", msg)))
            if m in FINTS_CODE_DE]


def interpret_message(msg: str | None) -> str:
    """Liefert einen deutschsprachigen Hinweis zu einer FinTS-Meldung (fallback: Original)."""
    codes = extract_fints_codes(msg)
    if not codes:
        return msg or "Unbekannter Schnittstellen-Fehler"
    primary = next((c for c in codes if c in KNOWN_CODES), codes[0])
    return FINTS_CODE_DE.get(primary, primary)


def classify_exception(exc: BaseException) -> tuple[str, str | None]:
    """Status-Kürzel aus der Exception (bank/connection/…)."""
    cls = type(exc).__name__
    try:
        from .banks.base import BankConnectionError, RateLimitError, TanRequired

        if isinstance(exc, TanRequired):
            return "tan_required", cls
        if isinstance(exc, RateLimitError):
            return "error", cls
        if isinstance(exc, BankConnectionError):
            return "error", cls
    except ImportError:  # pragma: no cover
        pass
    return "error", cls


def record(
    db: Session,
    *,
    bank: str,
    status: str,
    exception_type: str | None = None,
    message: str | None = None,
    codes: list[str] | None = None,
    detail: str | None = None,
    job_id: str | None = None,
    source: str = "sync",
) -> SyncLog:
    """Persistiert einen Sync-/Diagnose-Eintrag. Details NIE PIN/Login — nur Meldungstext."""
    # Sicherheitshalber Geheimnis-Verdacht maskieren (robust, falls eine Meldung durchrutscht).
    message = _scrub(message or "")
    detail = _scrub(detail or "")
    entry = SyncLog(
        job_id=job_id,
        bank=bank,
        status=status,
        exception_type=exception_type,
        codes=codes or [],
        message=message,
        detail=detail,
        source=source,
    )
    db.add(entry)
    db.commit()
    return entry


def _scrub(text: str) -> str:
    # Entfernt eine möglicherweise in der Meldung auftauchende Benutzerkennung/PIN nicht —
    # wir loggen nur Exception-Texte von Bank/Schnittstelle, niemals Credential-Speicher.
    for key in ("PIN", "Login", "passwort"):
        text = re.sub(rf"(?i)({key}[\s:]*)\S+", rf"\1[redigiert]", text)
    return text


def list_log(db: Session, limit: int = 50, bank: str | None = None) -> list[dict]:
    q = db.query(SyncLog)
    if bank:
        q = q.filter(SyncLog.bank == bank)
    rows = q.order_by(SyncLog.id.desc()).limit(max(limit, 1)).all()
    return [
        {
            "id": r.id,
            "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "job_id": r.job_id,
            "bank": r.bank,
            "status": r.status,
            "exception_type": r.exception_type,
            "codes": r.codes or [],
            "message": r.message,
            "detail": r.detail,
            "source": r.source,
        }
        for r in rows
    ]