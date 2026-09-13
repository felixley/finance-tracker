# Finance Tracker

Selbst-gehosteter, automatisierter Personal-Finance-Tracker für Deutschland: Holt Banktransaktionen per FinTS von Comdirect und DKB, speichert sie in SQLite (PostgreSQL-kompatibel), kategorisiert automatisch per Regel-Engine mit Lernfunktion und visualisiert alles in einem FastAPI-Dashboard.

## Features

| Bereich | Was drin ist |
|---|---|
| **Bank-Sync** | FinTS/HBCI-Connector pro Bank (`app/banks/`), chipTAN & pushTAN via CLI-Prompt, Mock-Modus für Demo/Test |
| **Pipeline** | Bereinigung → deterministische IDs (SHA-256) → Dedupe via Unique-Constraint, strukturiertes Logging |
| **Kategorisierung** | Regel-Engine (Keyword + Regex) mit Priorisierung; manuelle Kategorie-Korrektur in der UI erzeugt automatisch eine neue Regel |
| **Dashboard** | KPI-Cards (Gesamtsaldo, Einkommen/Ausgaben/Monat, Netto-Cashflow), Einnahmen-vs-Ausgaben-Chart, Kategorie-Donut, filterbare Transaktionstabelle mit Inline-Edit |
| **Scheduler** | APScheduler, täglicher Auto-Sync zur konfigurierbaren Uhrzeit (`SYNC_CRON_HOUR`) |
| **Backup** | `scripts/backup_db.py` — tägliches SQLite-Backup mit 14er-Rotation, sicher bei laufendem Server (WAL) |

## Quickstart

```bash
# 1. Dependencies
poetry install
#    oder ohne Poetry:
uv venv && uv pip install fints "sqlalchemy>=2" alembic fastapi uvicorn \
    jinja2 python-dotenv keyring apscheduler pytest

# 2. Konfiguration
cp .env.example .env          # anpassen

# 3. Datenbank anlegen + Kategorien/Regeln seeden
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m app.seed
.venv/bin/python -m app.seed_rules

# 4. Erster Sync (Demo-Daten, keine Bank nötig)
.venv/bin/python scripts/run_sync.py --banks mock

# 5. Dashboard starten
.venv/bin/python -m uvicorn app.api:create_app --factory --port 4712
# → http://localhost:4712
```

### Tests

```bash
.venv/bin/python -m pytest tests/ -v     # 19 Tests: ETL, Kategorisierer, API, FinTS-Engine
```

## Echte Bankanbindung (Comdirect / DKB)

Offizielle Infos der Banken zu FinTS/HBCI und TAN-Verfahren:

- **Comdirect**: [HBCI Banking & Brokerage (Was ist FinTS/HBCI, welche Geschäftsvorfälle)](https://www.comdirect.de/cms/kontakt-zugaenge-hbci.html) · [Software-Banking per FinTS](https://www.comdirect.de/cms/sicherheit-software-banking-fints.html)
- **DKB**: [Kann ich eine Finanzsoftware fürs Banking benutzen? (FinTS-Parameter inkl. Server-URL)](https://www.dkb.de/fragen-antworten/kann-ich-eine-finanzsoftware-fuers-banking-benutzen) · [Welche TAN-Verfahren bietet die DKB an? (DKB-App, chipTAN)](https://www.dkb.de/fragen-antworten/welche-tan-verfahren-bietet-die-dkb-an)

> Hinweis DKB: Seit 25.11.2024 gilt die neue FinTS-URL `https://fints.dkb.de/fints` (statt `banking-dkb.s-fints-pt-dkb.de/fints30`), Kunden-ID leer lassen, TAN2go ist abgeschaltet — Freigabe nur noch über DKB-App oder chipTAN. Die App-basierte Freigabe (decoupled) erfordert eine Bestätigung in der DKB-App je Sync.

### 1. Credentials hinterlegen (einmalig, im System-Keyring)

```bash
.venv/bin/python -m app.fints_credentials set comdirect
# fragt BLZ, Login, PIN, FinTS-URL ab; speichert im Keyring — niemals im Klartext
```

Headless/Container-Alternative: Env-Variablen `FT_COMDIRECT_*` bzw. `FT_DKB_*` (siehe `.env.example`) oder Docker Secrets.

### 2. Verbindung testen

```bash
.venv/bin/python scripts/fints_probe.py --bank comdirect --test-connection
```

### 3. TAN-Ablauf

Der automatische Scheduler **wartet nicht** auf TAN-Eingabe — TAN-pflichtige Syncs brechen ab und werden mit Log-Warnung übersprungen. Manueller Abruf mit TAN läuft interaktiv:

```bash
.venv/bin/python scripts/fints_probe.py --bank comdirect --days 90 --dump
# chipTAN: Flicker-Code ins TAN-Gerät, Code eingeben
# pushTAN: Push in der App bestätigen, Code eingeben
# → Transaktionen landen in data/fints_dump_comdirect.json
```

## Konfiguration (.env)

| Variable | Default | Bedeutung |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./data/finance.db` | SQLite-Default; PostgreSQL durch Connection-String |
| `BANKS` | `mock` | Aktive Banken, kommasepariert (`comdirect,dkb`) |
| `TAN_MODE` | `interactive` | `interactive` \| `mock` (nur Dev!) |
| `SYNC_DAYS_BACK` | `90` | Rückwirkender Abrufzeitraum |
| `SYNC_CRON_HOUR` | `6` | Stunde für täglichen Auto-Sync |
| `LOG_LEVEL` | `INFO` | DEBUG \| INFO \| WARNING \| ERROR |

## Backup

```bash
python3 scripts/backup_db.py
# → data/backups/finance-YYYYMMDD.db, behält die letzten 14
```

Nutzt `sqlite3.backup()` — funktioniert sicher auch, während der Server läuft (WAL-Modus). Empfehlung: als Cron-Job täglich einplanen.

## Docker

```bash
cp .env.example .env
docker compose up -d     # App auf :4712
```

Hinweis: Keyring funktioniert in Containern ohne D-Bus nicht — im Container Env-Variablen oder Docker Secrets verwenden (vorbereitet in `docker-compose.yml`).

## Architektur

```
app/
  config.py         dotenv-Settings
  db.py             SQLAlchemy Engine/Sessions
  models.py         accounts, transactions, categories, rules
  etl.py            clean → external_id → sync/dedupe
  categorizer.py    Regel-Engine + Lernfunktion (aus manuellen Overrides)
  scheduler.py      APScheduler, täglicher Sync
  api.py            FastAPI (Dashboard + REST)
  fints_credentials.py  Keyring-Verwaltung
  banks/            base, comdirect, dkb, mock (Dev), factory
  templates/ static/
alembic/versions/   Migrationen
scripts/            run_sync.py, fints_probe.py (TAN-CLI), backup_db.py
tests/              pytest: ETL, Kategorisierer, API, FinTS-Engine
```

## Sicherheit

- Zugangsdaten ausschließlich im System-Keyring (Service: `finance-tracker`) oder Docker Secrets — nie im Klartext in Code, Logs oder Repo
- `.gitignore` blockt `.env`, `data/`, `*.db`
- PIN wird in Logs explizit gefiltert

## PostgreSQL

Standard ist SQLite. Für PostgreSQL nur `DATABASE_URL` ändern (z. B. `postgresql+psycopg://user:pass@host:5432/finance`) — das Schema nutzt ausschließlich Standard-SQLAlchemy-Typen.

## Roadmap / offene Punkte

- [ ] FinTS-Credentials für echte Banken setzen (Keyring + TAN) — Sync läuft bisher im Mock-Modus
- [ ] Budgets pro Kategorie mit Ampel-Status im Dashboard
- [ ] CSV/JSON-Export der Transaktionen
- [ ] Automatischer TAN-Retry-Fallback
