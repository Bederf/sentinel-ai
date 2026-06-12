#!/usr/bin/env bash
# Rollback Phase 226.1.1 EnvironmentFile migration.
# Recreates the original DropIns from /etc/sentinel/backend.env + secrets.env
# (the two managed EnvironmentFiles introduced by Phase 226.1.1).
#
# Use this if the new envfiles.conf caused a service failure and you need to
# restore the old behavior without losing the values you already captured.
#
# Run as:
#   sudo bash /opt/bms-intelligence/scripts/operations/rollback-envfile-migration.sh
#
# What it does:
#   1. Deletes /etc/systemd/system/sentinel-backend.service.d/envfiles.conf
#      (this is what makes the unit consume the new EnvironmentFiles)
#   2. Recreates a consolidated rollback DropIn (00-rollback-envfile.conf)
#      that re-exports every KEY=VALUE pair from the .env files as
#      `Environment=` directives. For a faithful per-DropIn restoration,
#      edit the script to route each variable back to its original DropIn
#      (see /opt/bms-intelligence/docs/09-security/secret-rotation-log.md).
#   3. Runs `systemctl daemon-reload` and `systemctl restart sentinel-backend`,
#      then waits 30s and hits /api/health.

set -euo pipefail

DROPIN_DIR="/etc/systemd/system/sentinel-backend.service.d"
BACKEND_ENV="/etc/sentinel/backend.env"
SECRETS_ENV="/etc/sentinel/secrets.env"
SERVICE_NAME="sentinel-backend"

if [[ $EUID -ne 0 ]]; then
  echo "ERROR: must run as root (use sudo)" >&2
  exit 1
fi

if [[ ! -f "$BACKEND_ENV" || ! -f "$SECRETS_ENV" ]]; then
  echo "ERROR: EnvironmentFiles not found at $BACKEND_ENV / $SECRETS_ENV" >&2
  echo "       Aborting rollback - nothing to roll back from." >&2
  exit 1
fi

echo "Removing envfiles.conf DropIn..."
rm -f "$DROPIN_DIR/envfiles.conf"

echo "Recreating consolidated rollback DropIn from .env sources..."
mkdir -p "$DROPIN_DIR"
ROLLBACK_CONF="$DROPIN_DIR/00-rollback-envfile.conf"
{
  echo "[Service]"
  while IFS='=' read -r key val; do
    [[ -z "$key" || "$key" =~ ^# ]] && continue
    echo "Environment=\"$key=$val\""
  done < "$BACKEND_ENV"
  while IFS='=' read -r key val; do
    [[ -z "$key" || "$key" =~ ^# ]] && continue
    echo "Environment=\"$key=$val\""
  done < "$SECRETS_ENV"
} > "$ROLLBACK_CONF"
chmod 0600 "$ROLLBACK_CONF"
chown root:bederf "$ROLLBACK_CONF"

echo "Reloading systemd and restarting $SERVICE_NAME..."
systemctl daemon-reload
systemctl restart "$SERVICE_NAME"

echo "Rollback complete. Verifying health..."
sleep 30
if curl -fsS http://localhost:9095/api/health >/dev/null; then
  echo "OK: $SERVICE_NAME is healthy after rollback."
else
  echo "ERROR: $SERVICE_NAME did not become healthy. Check: journalctl -u $SERVICE_NAME -n 100" >&2
  exit 1
fi
