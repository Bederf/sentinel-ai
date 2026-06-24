#!/usr/bin/env bash
# SENTINEL Infra Bootstrap — bare VPS to running system
# Usage: sudo ./bootstrap.sh
# Run on a fresh Ubuntu 22.04+ VPS after initial SSH and DNS are set.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
INFRA_DIR="$REPO_DIR/infrastructure"

echo "=== SENTINEL Infra Bootstrap ==="
echo "Repo: $REPO_DIR"

# ── Prerequisites ──────────────────────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
  echo "Run as root: sudo ./bootstrap.sh"
  exit 1
fi

echo "[1/7] Installing system packages..."
apt-get update -qq
apt-get install -y -qq curl wget gnupg2 ca-certificates lsb-release age jq

# ── Docker ─────────────────────────────────────────────────────────────────
echo "[2/7] Installing Docker..."
if ! command -v docker &>/dev/null; then
  curl -fsSL https://get.docker.com | bash
  systemctl enable --now docker
fi

# ── Systemd units ──────────────────────────────────────────────────────────
echo "[3/7] Installing systemd units..."
if [[ -d "$INFRA_DIR/systemd" ]]; then
  cp "$INFRA_DIR/systemd"/*.service /etc/systemd/system/
  systemctl daemon-reload
  for unit in sentinel-backend sentinel-frontend sentinel-caddy sentinel-bms-tunnel; do
    systemctl enable "$unit" 2>/dev/null || true
  done
  echo "  → Installed $(ls -1 "$INFRA_DIR"/systemd/*.service | wc -l) units"
fi

# ── Cloudflare Tunnel ──────────────────────────────────────────────────────
echo "[4/7] Setting up Cloudflare Tunnel..."
mkdir -p /etc/cloudflared
if [[ -f "$INFRA_DIR/cloudflared/config.yml" ]]; then
  cp "$INFRA_DIR/cloudflared/config.yml" /etc/cloudflared/
fi
# NOTE: sentinel-bms-credentials.json is NOT in git.
# Place it manually at /etc/cloudflared/sentinel-bms-credentials.json
# or restore from the secrets bundle.

# ── Caddy ──────────────────────────────────────────────────────────────────
echo "[5/7] Installing Caddy..."
if ! command -v caddy &>/dev/null; then
  curl -fsSL https://getcaddy.com | bash -s personal
fi
if [[ -f "$INFRA_DIR/caddy/Caddyfile" ]]; then
  cp "$INFRA_DIR/caddy/Caddyfile" "$REPO_DIR/"
fi

# ── Mosquitto ──────────────────────────────────────────────────────────────
echo "[6/7] Configuring Mosquitto..."
mkdir -p /etc/mosquitto/conf.d
if [[ -f "$INFRA_DIR/mosquitto/sentinel.conf" ]]; then
  cp "$INFRA_DIR/mosquitto/sentinel.conf" /etc/mosquitto/conf.d/
fi
if [[ -f "$INFRA_DIR/mosquitto/sentinel.acl" ]]; then
  cp "$INFRA_DIR/mosquitto/sentinel.acl" /etc/mosquitto/conf.d/
fi
# NOTE: Mosquitto password file is NOT in git.
# Generate with: mosquitto_passwd -c /etc/mosquitto/passwd <username>
# or restore from the secrets bundle.

# ── Secrets reminder ──────────────────────────────────────────────────────
echo "[7/7] Secrets check..."
SECRETS_MISSING=0
for f in \
  /etc/cloudflared/sentinel-bms-credentials.json \
  /opt/bms-intelligence/backend/.env \
  /opt/bms-intelligence/frontend/.env.production \
  /etc/mosquitto/passwd; do
  if [[ ! -f "$f" ]]; then
    echo "  ⚠ MISSING: $f"
    SECRETS_MISSING=1
  fi
done
if [[ "$SECRETS_MISSING" -eq 1 ]]; then
  echo ""
  echo "  Restore secrets from the encrypted bundle:"
  echo "    age --decrypt -i /path/to/key.txt secrets.tar.age | tar xvf -"
  echo "  Then run: systemctl restart sentinel-backend sentinel-frontend"
fi

echo "=== Bootstrap complete ==="
echo "Start services: systemctl start sentinel-backend sentinel-frontend sentinel-caddy sentinel-bms-tunnel"
