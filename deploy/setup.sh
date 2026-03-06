#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Surebet VPS Setup — run once as root on a fresh Ubuntu 22.04 server
#
# Steps BEFORE running this script:
#   1. SSH into the VPS:  ssh root@139.59.213.24
#   2. Clone your repo:   git clone https://github.com/cooldev109/surebet.git /opt/surebet
#   3. Run this script:   cd /opt/surebet && bash deploy/setup.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

APP_DIR="/opt/surebet"
VENV="$APP_DIR/venv"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║   Surebet VPS Setup  (GitHub + PM2)     ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── 1. System packages ───────────────────────────────────────────────────────
echo "[1/6] Installing system packages..."
apt-get update -qq
apt-get install -y -qq python3.11 python3.11-venv python3-pip nginx git curl

# Node.js 20 (frontend build + PM2)
if ! command -v node &>/dev/null; then
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - >/dev/null
    apt-get install -y -qq nodejs
fi

# PM2 (global)
if ! command -v pm2 &>/dev/null; then
    npm install -g pm2 --silent
fi

# ── 2. Python virtual environment ────────────────────────────────────────────
echo "[2/6] Setting up Python environment..."
cd "$APP_DIR"
python3.11 -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r requirements.txt

# ── 3. Playwright browser ────────────────────────────────────────────────────
echo "[3/6] Installing Playwright Chromium (takes ~1 min)..."
"$VENV/bin/playwright" install chromium --with-deps >/dev/null

# ── 4. Build React frontend ───────────────────────────────────────────────────
echo "[4/6] Building React frontend..."
cd "$APP_DIR/frontend"
npm install --silent
npm run build --silent
cd "$APP_DIR"

# ── 5. Create .env from template ─────────────────────────────────────────────
if [ ! -f "$APP_DIR/.env" ]; then
    cp "$APP_DIR/.env.example" "$APP_DIR/.env"
    echo ""
    echo "  ⚠️  .env was created from .env.example."
    echo "      Fill in your credentials:"
    echo ""
    echo "      nano $APP_DIR/.env"
    echo ""
    read -rp "  Press ENTER after saving .env to continue... " _
fi

# ── 6. Nginx ─────────────────────────────────────────────────────────────────
echo "[5/6] Configuring Nginx..."
cp "$APP_DIR/deploy/nginx.conf" /etc/nginx/sites-available/surebet
ln -sf /etc/nginx/sites-available/surebet /etc/nginx/sites-enabled/surebet
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl enable nginx
systemctl reload nginx

if command -v ufw &>/dev/null; then
    ufw allow OpenSSH      >/dev/null 2>&1 || true
    ufw allow 'Nginx Full' >/dev/null 2>&1 || true
    ufw --force enable     >/dev/null 2>&1 || true
fi

# ── 7. Start with PM2 ────────────────────────────────────────────────────────
echo "[6/6] Starting Surebet with PM2..."
cd "$APP_DIR"
pm2 start deploy/ecosystem.config.js
pm2 save               # persist process list across reboots
pm2 startup | tail -1 | bash  # register PM2 with system init

echo ""
echo "  ✅  Surebet is running!"
echo "      Dashboard → http://139.59.213.24"
echo "      Status    → pm2 status"
echo "      Logs      → pm2 logs surebet"
echo ""
