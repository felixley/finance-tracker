"""pytest conftest: Isolierte File-DB für alle Tests (schützt die Produktiv-DB).

Hinweis: sqlite:///:memory: funktioniert hier NICHT — der ThreadPool der App
öffnet mehrere Verbindungen und jede SQLite-:memory:-Connection ist eine
eigene, leere DB ("no such table"). Deshalb eine gemeinsame Temp-Datei.
"""
from __future__ import annotations

import os
import tempfile

_tmpdb = os.path.join(tempfile.mkdtemp(prefix="ft-test-"), "test.db")
# Muss VOR jedem App-Import gesetzt sein: app.db liest DATABASE_URL beim Modul-Import.
os.environ["DATABASE_URL"] = f"sqlite:///{_tmpdb}"