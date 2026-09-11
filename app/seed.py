from __future__ import annotations

from sqlalchemy.orm import Session

from .db import Base, engine, SessionLocal
from .models import Category

DEFAULT_CATEGORIES: list[tuple[str, str]] = [
    ("Groceries", "expense"),
    ("Leisure & Recreation", "expense"),
    ("Dining Out", "expense"),
    ("Housing/Rent", "expense"),
    ("Insurance", "expense"),
    ("Subscriptions", "expense"),
    ("Salary", "income"),
    ("Internal Transfer", "expense"),
    ("Sonstiges", "expense"),
    ("Unassigned", "expense"),
]


def seed_categories(db: Session | None = None) -> int:
    """Idempotent: legt fehlende Default-Kategorien an. Gibt Anzahl neu angelegter zurück."""
    own_session = db is None
    if own_session:
        db = SessionLocal()
    try:
        created = 0
        existing = {name for (name,) in db.query(Category.name).all()}
        for name, ctype in DEFAULT_CATEGORIES:
            if name not in existing:
                db.add(Category(name=name, type=ctype))
                created += 1
        db.commit()
        return created
    finally:
        if own_session:
            db.close()


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    seed_categories()


if __name__ == "__main__":
    created = seed_categories()
    print(f"Seed OK: {created} neue Kategorien angelegt (restliche existierten bereits).")