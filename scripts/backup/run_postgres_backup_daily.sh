#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
LOG_DIR="${REPO_ROOT}/backups/logs"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="${LOG_DIR}/postgres_backup_daily_${TIMESTAMP}.log"

mkdir -p "${LOG_DIR}"

exec > >(tee -a "${LOG_FILE}") 2>&1

echo "Running scheduled PostgreSQL backup"
echo "Timestamp: ${TIMESTAMP}"

"${SCRIPT_DIR}/postgres_logical_backup.sh" daily

echo "Scheduled PostgreSQL backup completed"
