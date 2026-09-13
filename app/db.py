from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


def _make_engine(url: str | None = None):
    url = url or settings.DATABASE_URL
    kwargs = {}
    if url.startswith("sqlite"):
        # sqlite legt die DB-Datei selbst an — aber nicht das Verzeichnis.
        # Frische Clones haben data/ nicht dabei (gitignored) → "unable to open database file".
        db_path = url.split("sqlite:///", 1)[-1]
        if db_path and db_path != ":memory:" and not db_path.startswith(":memory:"):
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(url, **kwargs)


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()