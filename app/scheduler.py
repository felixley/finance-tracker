"""APScheduler: täglicher Bank-Sync."""
from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from .config import settings
from .etl import sync_all
from .banks.base import TanRequired

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def _daily_sync() -> None:
    try:
        summary = sync_all(days_back=7)
        logger.info("Täglicher Sync: %s", summary)
    except TanRequired:
        logger.warning("Täglicher Sync: TAN-pflichtige Bank übersprungen (interaktiv nötig).")
    except Exception:
        logger.exception("Täglicher Sync fehlgeschlagen.")


def start_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        return _scheduler
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        _daily_sync,
        trigger="cron",
        hour=int(settings.SYNC_CRON_HOUR),
        minute=0,
        id="daily_bank_sync",
        replace_existing=True,
    )
    scheduler.start()
    _scheduler = scheduler
    logger.info("Scheduler gestartet: täglicher Sync um %s:00 Uhr.", settings.SYNC_CRON_HOUR)
    return scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None