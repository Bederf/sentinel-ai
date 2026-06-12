#!/usr/bin/env bash
# offsite_upload.sh — encrypt and ship a local backup directory to Cloudflare R2
#
# Usage (called automatically by run_postgres_backup_daily.sh):
#   offsite_upload.sh <local_backup_dir>
#
# Required env vars (set in /etc/sentinel/backup.env or systemd drop-in):
#   BACKUP_ENCRYPTION_RECIPIENT — age public key (recipient for encryption)
#   RCLONE_CONFIG               — path to rclone config (default: /etc/sentinel/rclone.conf)
#   R2_REMOTE                   — rclone remote name (default: r2-sentinel)
#   R2_BUCKET                   — R2 bucket name (default: sentinel-backups)
#   R2_PATH                     — prefix inside bucket (default: postgres)
#
# Retention: keeps 30 days of backups in R2 (managed via --min-age on delete).

set -euo pipefail

LOCAL_DIR="${1:?Usage: offsite_upload.sh <local_backup_dir>}"
[[ -d "${LOCAL_DIR}" ]] || { echo "Directory not found: ${LOCAL_DIR}" >&2; exit 1; }

RCLONE_CONFIG="${RCLONE_CONFIG:-/etc/sentinel/rclone.conf}"
R2_REMOTE="${R2_REMOTE:-r2-sentinel}"
R2_BUCKET="${R2_BUCKET:-sentinel-backups}"
R2_PATH="${R2_PATH:-postgres}"
R2_RETENTION_DAYS="${R2_RETENTION_DAYS:-30}"

RECIPIENT="${BACKUP_ENCRYPTION_RECIPIENT:-}"

if [[ -z "${RECIPIENT}" ]]; then
  echo "ERROR: BACKUP_ENCRYPTION_RECIPIENT not set — cannot encrypt backup" >&2
  exit 1
fi

if [[ ! -f "${RCLONE_CONFIG}" ]]; then
  echo "ERROR: rclone config not found at ${RCLONE_CONFIG}" >&2
  exit 1
fi

FOLDER_NAME="$(basename "${LOCAL_DIR}")"
STAGING_DIR="$(mktemp -d)"
trap 'rm -rf "${STAGING_DIR}"' EXIT

echo "Encrypting backup files from ${LOCAL_DIR}"
for f in "${LOCAL_DIR}"/*.dump "${LOCAL_DIR}"/*.sql "${LOCAL_DIR}"/*.env; do
  [[ -f "${f}" ]] || continue
  fname="$(basename "${f}")"
  age --recipient "${RECIPIENT}" --output "${STAGING_DIR}/${fname}.age" "${f}"
  echo "  Encrypted: ${fname}"
done

# Copy manifest unencrypted (no secrets, useful for listing/auditing)
[[ -f "${LOCAL_DIR}/backup.env" ]] && cp "${LOCAL_DIR}/backup.env" "${STAGING_DIR}/backup.env"

REMOTE_PATH="${R2_REMOTE}:${R2_BUCKET}/${R2_PATH}/${FOLDER_NAME}"
echo "Uploading to ${REMOTE_PATH}"
rclone copy \
  --config "${RCLONE_CONFIG}" \
  --transfers 4 \
  --stats 30s \
  "${STAGING_DIR}/" \
  "${REMOTE_PATH}/"

echo "Upload complete: ${REMOTE_PATH}"

# Prune backups older than retention window
echo "Pruning R2 backups older than ${R2_RETENTION_DAYS} days"
rclone delete \
  --config "${RCLONE_CONFIG}" \
  --min-age "${R2_RETENTION_DAYS}d" \
  "${R2_REMOTE}:${R2_BUCKET}/${R2_PATH}/"

echo "Offsite backup finished successfully"
