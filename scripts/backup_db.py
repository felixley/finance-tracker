#!/usr/bin/env python3
"""Tägliches SQLite-Backup: finance.db -> data/backups/finance-YYYYMMDD.db (behält 14)."""
import sqlite3, datetime, os

SRC = "/opt/data/workspace/finance-tracker/data/finance.db"
DST_DIR = "/opt/data/workspace/finance-tracker/data/backups"

os.makedirs(DST_DIR, exist_ok=True)
dst = os.path.join(DST_DIR, f"finance-{datetime.date.today():%Y%m%d}.db")
src = sqlite3.connect(SRC)
bck = sqlite3.connect(dst)
src.backup(bck)  # sicher auch bei laufendem WAL-Server
bck.close()
src.close()

# Rotation: nur die 14 neuesten behalten
backups = sorted(f for f in os.listdir(DST_DIR) if f.startswith("finance-") and f.endswith(".db"))
for old in backups[:-14]:
    os.remove(os.path.join(DST_DIR, old))
print(f"backup ok: {dst} ({backups and len(backups)} files retained)")