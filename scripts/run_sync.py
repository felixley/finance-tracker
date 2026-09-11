#!/usr/bin/env python
"""CLI: Bank-Sync anstoßen (Default: konfigurierte Banks oder mock)."""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.etl import sync_all  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def main() -> None:
    p = argparse.ArgumentParser(description="Bank-Sync ausführen")
    p.add_argument("--banks", default=",".join(settings.banks) or "mock")
    p.add_argument("--days", type=int, default=settings.SYNC_DAYS_BACK)
    p.add_argument("--dump", action="store_true", help="JSON-Dumps schreiben")
    args = p.parse_args()
    banks = [b.strip() for b in args.banks.split(",") if b.strip()]
    result = sync_all(days_back=args.days, banks=banks)
    print("Ergebnis:", result)
    sys.exit(0 if not result["errors"] else 1)


if __name__ == "__main__":
    main()