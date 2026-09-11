import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings:
    """Zentrale Konfiguration. Secrets NIE hier im Klartext — Bank-Zugänge
    liegen ausschließlich im System-Keyring (app/fints_credentials.py)."""

    DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'data' / 'finance.db'}")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    # Bank-Verbindungen: Liste z.B. "comdirect,dkb"
    BANKS: str = os.getenv("BANKS", "comdirect,dkb")
    # TAN-Modus: interactive (CLI-Prompt) — automatischer Sync ohne TAN-Pflicht nur wenn TAN nicht nötig
    TAN_MODE: str = os.getenv("TAN_MODE", "interactive")
    # Sync-Fenster für Abruf
    SYNC_DAYS_BACK: int = int(os.getenv("SYNC_DAYS_BACK", "90"))
    # Scheduler
    SYNC_CRON_HOUR: str = os.getenv("SYNC_CRON_HOUR", "6")  # täglicher Sync-Uhrzeit

    @property
    def banks(self) -> list[str]:
        return [b.strip() for b in self.BANKS.split(",") if b.strip()]


settings = Settings()