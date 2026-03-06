#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Surebet Update — pull latest code from GitHub and restart
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

echo "Restarting with PM2..."
pm2 restart surebet

echo ""
echo "✅  Update complete!"
echo "    Logs → pm2 logs surebet"
echo ""
