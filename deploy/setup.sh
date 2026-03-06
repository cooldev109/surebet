#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Surebet VPS Setup — run once as root on a fresh Ubuntu 22.04 server
#
# Steps BEFORE running this script:
#   1. SSH into the VPS:    ssh root@139.59.213.24
#   2. Clone your repo:     git clone https://github.com/YOUR_USER/YOUR_REPO /opt/surebet
#   3. Run this script:     cd /opt/surebet && bash deploy/setup.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

APP_DIR="/opt/surebet"
VENV="$APP_DIR/venv"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║   Surebet VPS Setup (GitHub + systemd)  ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── 1. System packages ───────────────────────────────────────────────────────
echo "[1/6] Installing system packages..."
apt-get update -qq
apt-get install -y -qq python3.11 python3.11-venv python3-pip nginx git curl

# Node.js 20 (to build React frontend)
if ! command -v node &>/dev/null; then
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - >/dev/null
    apt-get install -y -qq nodejs
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
    echo "      Open it and fill in your credentials:"
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

# Firewall
if command -v ufw &>/dev/null; then
    ufw allow OpenSSH  >/dev/null 2>&1 || true
    ufw allow 'Nginx Full' >/dev/null 2>&1 || true
    ufw --force enable >/dev/null 2>&1 || true
fi

# ── 7. Systemd service ───────────────────────────────────────────────────────
echo "[6/6] Installing systemd service..."
cp "$APP_DIR/deploy/surebet.service" /etc/systemd/system/surebet.service
systemctl daemon-reload
systemctl enable surebet
systemctl start surebet

echo ""
echo "  ✅  Surebet is running!"
echo "      Dashboard → http://139.59.213.24"
echo "      Status    → systemctl status surebet"
echo "      Logs      → journalctl -u surebet -f"
echo ""
