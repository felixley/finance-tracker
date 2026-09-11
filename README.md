# Finance Tracker

Selbst-gehosteter, automatisierter Personal-Finance-Tracker: Banktransaktionen via FinTS (Comdirect, DKB), SQLite/PostgreSQL-Speicher, regelbasierte Kategorisierung mit Lernfunktion, FastAPI-Dashboard mit TailwindCSS + Chart.js.

## Features

- **FinTS-Integration**: Pro Bank ein Connector (`app/banks/comdirect.py`, `app/banks/dkb.py`); chipTAN/pushTAN über CLI-Prompt; Credentials ausschließlich im System-Keyring
- **Datenpipeline**: Bereinigung, deterministische Transaktions-IDs (SHA-256), Dedupe via Unique-Constraint, strukturiertes Logging
- **Kategorisierung**: Regel-Engine (Keyword + Regex) mit Priorisierung; manuelle Korrekturen erzeugen automatisch neue Regeln (`created_from_manual_override`)
- **Dashboard**: KPI-Cards (Gesamtsaldo, Einkommen/Ausgaben/Monat, Netto-Cashflow), Zeitverlauf (monatlich/jährlich), Kategorie-Donut, filterbare Transaktionstabelle mit Inline-Kategorie-Edit, Sync-Trigger
- **Scheduler**: APScheduler — täglicher Sync (`SYNC_CRON_HOUR`)

## Setup

```bash
# 1. Dependencies (Poetry ODER uv)
poetry install            # oder: uv venv && uv pip install fints "sqlalchemy>=2" alembic fastapi uvicorn jinja2 python-dotenv keyring apscheduler pytest

# 2. Konfiguration
cp .env.example .env      # anpassen (DATABASE_URL, BANKS, ...)

# 3. Datenbank anlegen + Seed
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m app.seed
.venv/bin/python -m app.seed_rules   # Regel-Seed für deutsche Händler

# 4. Demo ohne echte Bank: .env → BANKS=mock
.venv/bin/python scripts/run_sync.py --banks mock
.venv/bin/python -m app.seed_rules && .venv/bin/python - <<'PY'
from app.db import SessionLocal
from app.categorizer import RuleMatchEngine, apply_to_pending
PY

# 5. Dashboard starten
.venv/bin/python -m uvicorn app.api:create_app --factory --port 4712
# → http://localhost:4712  (Port nach Wahl)
```

### Tests

```bash
.venv/bin/python -m pytest tests/ -v
```

## TAN-Interaktionsablauf (Comdirect/DKB)

1. **Credentials hinterlegen** (einmalig, im Keyring — niemals im Repo):
   ```bash
   .venv/bin/python -m app.fints_credentials set comdirect
   # fragt BLZ, Login, PIN, FinTS-URL ab; speichert im System-Keyring
   ```
   Alternative für Headless/Container: Umgebungsvariablen `FT_COMDIRECT_*` bzw. `FT_DKB_*` (siehe `.env.example`) oder Docker Secrets.

2. **Erstverbindung testen**:
   ```bash
   .venv/bin/python scripts/fints_probe.py --bank comdirect --test-connection
   ```

3. **TAN-Pflicht** (chipTAN/pushTAN): Der Sync **wartet nicht automatisch** — bei TAN-Anforderung bricht der Job ab und meldet `TanRequired`. TAN-Abruf interaktiv:
   ```bash
   .venv/bin/python scripts/fints_probe.py --bank comdirect --days 90 --dump
   # → listet Konten, fragt TAN via input() ab (chipTAN: flashing/Flicker-Code ins TAN-Gerät, pushTAN: App-Push bestätigen + Code eingeben)
   # → dumpet Transaktionen nach data/fints_dump_comdirect.json
   ```
   Der automatische Scheduler überspringt TAN-pflichtige Banken mit Log-Warnung; manuelle Buchungsabrufe mit TAN laufen über das Probe-Skript.

## Security

- PIN/Login **nie** im Klartext: Keyring (`keyring`-Package, service `finance-tracker`) oder Env-Fallback nur für Headless-Setups
- `.gitignore` blockt `.env`, `data/`, `*.db`
- Logs enthalten nie Zugangsdaten (eigene Logger, PIN-Ausnahme gefiltert)

## Docker

```bash
cp .env.example .env   # konfigurieren
docker compose up -d   # App auf :4712, Sync-Scheduler im Container
```

## Architektur

```
app/
  config.py        # dotenv-Settings
  db.py            # SQLAlchemy engine/session
  models.py        # accounts, transactions, categories, rules
  etl.py           # clean → external_id → sync/dedupe
  categorizer.py   # Rule-Match-Engine + Lernfunktion
  scheduler.py     # APScheduler (täglich)
  api.py           # FastAPI (Dashboard + REST)
  banks/           # base, comdirect, dkb, mock (DEV), factory
  templates/ static/
alembic/versions/  # Migrationen
scripts/           # fints_probe.py (TAN-CLI), run_sync.py
tests/             # pytest: ETL, Kategorisierer, API, FinTS-Engine
```

## PostgreSQL

Standard: SQLite (`sqlite:///./data/finance.db`). PostgreSQL: nur `DATABASE_URL` ändern (z.B. `postgresql+psycopg://user:pass@host:5432/finance`) — alle Typen sind Standard-SQLAlchemy.