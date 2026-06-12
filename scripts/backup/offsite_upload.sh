#!/usr/bin/env bash
# offsite_upload.sh — encrypt and ship a local backup directory to replica VPS via SCP
#
# Usage (called automatically by run_postgres_backup_daily.sh):
#   offsite_upload.sh <local_backup_dir>
#
# Required env vars (set in /etc/sentinel/backup.env):
#   BACKUP_ENCRYPTION_RECIPIENT — age public key (recipient for encryption)
#   BACKUP_SSH_KEY              — path to backup SSH private key
#   BACKUP_REMOTE_HOST          — replica VPS hostname or IP
#   BACKUP_REMOTE_USER          — SSH user on replica (default: shad)
#   BACKUP_REMOTE_PATH          — base path on replica (default: ~/backup)
#
# Retention:
#   Daily:   14 days   (-max-age 14d on remote prune)
#   Weekly:   8 weeks  (-max-age 56d)
#   Monthly:  6 months (-max-age 180d)

set -euo pipefail

# Load backup env vars (backup encryption key, replica connection)
[[ -f /etc/sentinel/backup.env ]] && source /etc/sentinel/backup.env

LOCAL_DIR="${1:?Usage: offsite_upload.sh <local_backup_dir>}"
[[ -d "${LOCAL_DIR}" ]] || { echo "Directory not found: ${LOCAL_DIR}" >&2; exit 1; }

RECIPIENT="${BACKUP_ENCRYPTION_RECIPIENT:-}"
SSH_KEY="${BACKUP_SSH_KEY:-/etc/sentinel/backup-ssh-key}"
REMOTE_HOST="${BACKUP_REMOTE_HOST:-}"
REMOTE_USER="${BACKUP_REMOTE_USER:-shad}"
REMOTE_BASE="${BACKUP_REMOTE_PATH:-backup}"

if [[ -z "${RECIPIENT}" ]]; then
  echo "ERROR: BACKUP_ENCRYPTION_RECIPIENT not set" >&2
  exit 1
fi
if [[ -z "${REMOTE_HOST}" ]]; then
  echo "ERROR: BACKUP_REMOTE_HOST not set" >&2
  exit 1
fi
if [[ ! -f "${SSH_KEY}" ]]; then
  echo "ERROR: SSH key not found at ${SSH_KEY}" >&2
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

[[ -f "${LOCAL_DIR}/backup.env" ]] && cp "${LOCAL_DIR}/backup.env" "${STAGING_DIR}/backup.env"

REMOTE_DIR="${REMOTE_BASE}/daily/${FOLDER_NAME}"
echo "Uploading to ${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}"
ssh -i "${SSH_KEY}" -o StrictHostKeyChecking=accept-new "${REMOTE_USER}@${REMOTE_HOST}" "mkdir -p ${REMOTE_DIR}"
scp -i "${SSH_KEY}" -o StrictHostKeyChecking=accept-new -r -q "${STAGING_DIR}/." "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/"

echo "Upload complete"

# Prune old backups on replica
DAILY_RETENTION="${BACKUP_RETENTION_DAILY:-14}"
WEEKLY_RETENTION="${BACKUP_RETENTION_WEEKLY:-56}"
MONTHLY_RETENTION="${BACKUP_RETENTION_MONTHLY:-180}"

echo "Pruning daily backups older than ${DAILY_RETENTION} days"
ssh -i "${SSH_KEY}" "${REMOTE_USER}@${REMOTE_HOST}" \
  "find ${REMOTE_BASE}/daily -mindepth 1 -maxdepth 1 -type d -mtime +${DAILY_RETENTION} -exec rm -rf {} + 2>/dev/null; echo 'Daily prune complete'"

echo "Pruning weekly backups older than ${WEEKLY_RETENTION} days"
ssh -i "${SSH_KEY}" "${REMOTE_USER}@${REMOTE_HOST}" \
  "find ${REMOTE_BASE}/weekly -mindepth 1 -maxdepth 1 -type d -mtime +${WEEKLY_RETENTION} -exec rm -rf {} + 2>/dev/null; echo 'Weekly prune complete'"

echo "Pruning monthly backups older than ${MONTHLY_RETENTION} days"
ssh -i "${SSH_KEY}" "${REMOTE_USER}@${REMOTE_HOST}" \
  "find ${REMOTE_BASE}/monthly -mindepth 1 -maxdepth 1 -type d -mtime +${MONTHLY_RETENTION} -exec rm -rf {} + 2>/dev/null; echo 'Monthly prune complete'"

echo "Offsite backup finished successfully"
