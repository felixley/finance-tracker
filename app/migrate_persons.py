"""Migration: persons-Tabelle + accounts.owner_id (CREATE IF NOT EXISTS / ALTER) — idempotent."""
from sqlalchemy import text

from .db import Base, engine
# Modelle importieren, damit alle Tabellen in Base.metadata registriert sind
from . import models as _models  # noqa: F401


def migrate() -> None:
    with engine.begin() as conn:
        # Frische DB: Grundschema anlegen (idempotent), sonst schlägt das ALTER fehl
        Base.metadata.create_all(bind=conn)
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS persons ("
            "id INTEGER PRIMARY KEY, name VARCHAR(100) NOT NULL UNIQUE)"
        ))
        cols = [r[1] for r in conn.execute(text("PRAGMA table_info(accounts)"))]
        if "owner_id" not in cols:
            conn.execute(text("ALTER TABLE accounts ADD COLUMN owner_id INTEGER"))
    print("Migration ok: persons-Tabelle + accounts.owner_id vorhanden.")


if __name__ == "__main__":
    migrate()