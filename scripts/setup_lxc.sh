#!/usr/bin/env bash
# Finance-Tracker: Einmal-Setup in einem frischen Proxmox-LXC (Debian 12).
# Ausführen als root im Container:
#   bash scripts/setup_lxc.sh [REPO_URL] [INSTALL_DIR]
#   REPO_URL     optional, Default: https://github.com/felixley/finance-tracker.git
#   INSTALL_DIR  optional, Default: /opt/finance-tracker
# Optional vorher: DB rüberkopieren (data/finance.db + data/backups/) — dann bleibt alles erhalten.
set -euo pipefail

REPO_URL="${1:-https://github.com/felixley/finance-tracker.git}"
INSTALL_DIR="${2:-/opt/finance-tracker}"
SVC_NAME="finance-tracker"
PORT="${FT_PORT:-4711}"

log() { echo -e "\n=== $1 ==="; }

log "1/6 Systempakete"
apt-get update -qq
apt-get install -y -qq python3-venv python3-pip git curl >/dev/null

log "2/6 Code klonen nach $INSTALL_DIR"
if [ -d "$INSTALL_DIR/.git" ]; then
  git -C "$INSTALL_DIR" pull --ff-only
else
  git clone "$REPO_URL" "$INSTALL_DIR"
fi
cd "$INSTALL_DIR"

log "3/6 Virtualenv + Abhängigkeiten"
# Manche Umgebungen (Container ohne ensurepip) haben kein python3-venv-Modul → uv-Fallback
if ! python3 -m venv .venv 2>/dev/null; then
  if ! command -v uv >/dev/null; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
  fi
  uv venv .venv
  VIRTUAL_ENV="$INSTALL_DIR/.venv" uv pip install -e . keyrings.alt
else
  .venv/bin/pip install --quiet --upgrade pip
  .venv/bin/pip install --quiet -e .
  # Container ohne Desktop: File-Backend für Keyring (PIN landet in ~/.local/share/keyrings)
  .venv/bin/pip install --quiet keyrings.alt
fi

log "4/6 DB-Schema + Seeds"
.venv/bin/python -m app.migrate_persons
.venv/bin/python -m app.seed
.venv/bin/python -m app.seed_rules

log "5/6 systemd-Unit $SVC_NAME.service"
cat > "/etc/systemd/system/$SVC_NAME.service" <<EOF
[Unit]
Description=Finance Tracker (FastAPI/uvicorn)
After=network-online.target
Wants=network-online.target

[Service]
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/.venv/bin/uvicorn app.api:create_app --factory --host 0.0.0.0 --port $PORT
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now "$SVC_NAME"

log "6/6 Verifikation"
sleep 2
HTTP=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/api/kpis" || true)
if [ "$HTTP" = "200" ]; then
  echo "OK: Finance Tracker läuft auf Port $PORT (HTTP $HTTP)"
  IP=$(hostname -I | awk '{print $1}')
  echo "Dashboard: http://$IP:$PORT/"
else
  echo "WARNUNG: Health-Check lief HTTP $HTTP — Logs: journalctl -u $SVC_NAME -n 50"
fi

cat <<'HINTS'

Nächste Schritte (manuell):
 1. Bank-Zugänge:  .venv/bin/python -m app.fints_credentials set comdirect
    (im Container wird automatisch das File-Backend via keyrings.alt genutzt;
     alternativ .env mit FT_<BANK>_BLZ/LOGIN/PIN/URL)
 2. .env anpassen:  BANKS=..., TAN_MODE=interactive, SYNC_DAYS_BACK=90
 3. Backup-Cron:    crontab -e  →  0 6 * * *  cd <INSTALL_DIR> && .venv/bin/python scripts/backup_db.py
 4. TAN-Pflichtige Syncs laufen im Container interaktiv:
    systemctl stop finance-tracker && .venv/bin/python scripts/fints_probe.py --bank <bank>
HINTS