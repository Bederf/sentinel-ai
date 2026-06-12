#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
LOG_DIR="${REPO_ROOT}/backups/logs"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="${LOG_DIR}/postgres_backup_daily_${TIMESTAMP}.log"

# Load backup env vars (R2 credentials, encryption key) if present
[[ -f /etc/sentinel/backup.env ]] && source /etc/sentinel/backup.env

mkdir -p "${LOG_DIR}"

exec > >(tee -a "${LOG_FILE}") 2>&1

echo "Running scheduled PostgreSQL backup"
echo "Timestamp: ${TIMESTAMP}"

"${SCRIPT_DIR}/postgres_logical_backup.sh" daily

# Offsite upload — ships encrypted copy to Cloudflare R2
LATEST_BACKUP="$(find "${REPO_ROOT}/backups/postgres/daily" -mindepth 1 -maxdepth 1 -type d | sort | tail -1)"
if [[ -n "${LATEST_BACKUP}" && -f "${SCRIPT_DIR}/offsite_upload.sh" ]]; then
  echo "Starting offsite upload of ${LATEST_BACKUP}"
  "${SCRIPT_DIR}/offsite_upload.sh" "${LATEST_BACKUP}" \
    || echo "WARNING: Offsite upload failed — local backup still intact"
else
  echo "WARNING: No backup directory found for offsite upload"
fi

echo "Scheduled PostgreSQL backup completed"
