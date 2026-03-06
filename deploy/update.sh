#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Surebet Update — run on VPS to deploy the latest code from GitHub
# Usage:  bash /opt/surebet/deploy/update.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

APP_DIR="/opt/surebet"
VENV="$APP_DIR/venv"

echo "Pulling latest code from GitHub..."
cd "$APP_DIR"
git pull

echo "Installing new Python dependencies (if any)..."
"$VENV/bin/pip" install --quiet -r requirements.txt

echo "Rebuilding React frontend..."
cd "$APP_DIR/frontend"
npm install --silent
npm run build --silent
cd "$APP_DIR"

echo "Restarting service..."
systemctl restart surebet

echo ""
echo "✅  Update complete!"
echo "    Logs → journalctl -u surebet -f"
echo ""
