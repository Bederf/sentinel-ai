#!/bin/bash

################################################################################
# Rename Script: OpenClaw → SENTRY (Simplified Version)
#
# Usage:
#   ./rename_clawd_to_sentry_v2.sh --dry-run
#   ./rename_clawd_to_sentry_v2.sh --execute
#   ./rename_clawd_to_sentry_v2.sh --rollback
#
################################################################################

set -euo pipefail

PROJECT_ROOT="/opt/bms-intelligence"
BACKUP_DIR="${PROJECT_ROOT}/.rename-backup-$(date +%s)"
LOG_FILE="${PROJECT_ROOT}/.rename-log-$(date +%Y%m%d-%H%M%S).txt"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() { echo -e "${BLUE}[INFO]${NC} $1" | tee -a "$LOG_FILE"; }
success() { echo -e "${GREEN}[✓]${NC} $1" | tee -a "$LOG_FILE"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1" | tee -a "$LOG_FILE"; }
error() { echo -e "${RED}[ERROR]${NC} $1" | tee -a "$LOG_FILE"; }

# Rename patterns
declare -A PATTERNS=(
  # Python classes
  ["SentryAuthService"]="SentryAuthService"
  ["sentry_auth"]="sentry_auth"
  ["_sentry_auth_service"]="_sentry_auth_service"

  # Imports
  ["from app.services.sentry_"]="from app.services.sentry_"
  ["from app.services import sentry"]="from app.services import sentry"

  # API endpoints
  ["/api/sentry/"]="/api/sentry/"
  ["/api/sentry-webhooks"]="/api/sentry-webhooks"

  # Functions
  ["get_sentry_"]="get_sentry_"
  ["initialize_sentry_"]="initialize_sentry_"
  ["notify_sentry"]="notify_sentry"

  # Env vars
  ["SENTRY_"]="SENTRY_"
  ["SENTRY-"]="SENTRY-"

  # Config
  ["sentry_webhook_secret"]="sentry_webhook_secret"
  ["sentry_bot_api_key"]="sentry_bot_api_key"
  ["sentry_username"]="sentry_username"
  ["sentry_password"]="sentry_password"
  ["sentry_notifications"]="sentry_notifications"

  # Headers
  ["X-Sentry-Secret"]="X-Sentry-Secret"
  ["X-Sentry-API-Key"]="X-Sentry-API-Key"

  # Secrets
  ["sentry-bms-phase-41"]="sentry-bms-phase-41"

  # Paths
  ["$SENTRY_HOME"]='$SENTRY_HOME'
  ["$SENTRY_HOME"]='$SENTRY_HOME'
  ["$SENTRY_HOME"]='$SENTRY_HOME'

  # Comments
  ["Sentry bot"]="Sentry bot"
  ["Sentry integration"]="Sentry integration"
  ["Sentry webhook"]="Sentry webhook"
  ["Sentry secret"]="Sentry secret"
)

find_clawd_files() {
  find "$PROJECT_ROOT" -type f \
    \( -name "*.py" -o -name "*.ts" -o -name "*.tsx" -o -name "*.md" \
       -o -name "*.yaml" -o -name "*.yml" -o -name "*.json" -o -name "*.sh" \) \
    -not -path '*/.git/*' \
    -not -path '*/.pytest_cache/*' \
    -not -path '*/.ruff_cache/*' \
    -not -path '*/node_modules/*' \
    -not -path '*/.rename-backup-*' \
    -print0 2>/dev/null | xargs -0 grep -l "clawd\|openclaw\|moltbot" 2>/dev/null | sort -u
}

dry_run() {
  log "Starting DRY-RUN..."
  echo ""

  local files
  files=$(find_clawd_files)

  if [[ -z "$files" ]]; then
    warn "No clawd references found"
    return 0
  fi

  local file_count=0
  local total_changes=0

  while IFS= read -r file; do
    ((file_count++))
    local rel_path="${file#$PROJECT_ROOT/}"
    echo -e "${YELLOW}$rel_path${NC}" | tee -a "$LOG_FILE"

    # Show first few matches
    local matches=0
    for pattern in "${!PATTERNS[@]}"; do
      if grep -q "$pattern" "$file"; then
        local count=$(grep -o "$pattern" "$file" | wc -l)
        ((total_changes += count))
        echo "  • $pattern → ${PATTERNS[$pattern]} ($count matches)" | tee -a "$LOG_FILE"
        ((matches++))
        if (( matches >= 3 )); then break; fi
      fi
    done
    echo ""
  done <<< "$files"

  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" | tee -a "$LOG_FILE"
  echo "Summary:" | tee -a "$LOG_FILE"
  echo "  Files to modify: $file_count" | tee -a "$LOG_FILE"
  echo "  Total changes: ~$total_changes" | tee -a "$LOG_FILE"
  echo "" | tee -a "$LOG_FILE"
  success "DRY-RUN complete. Review: cat $LOG_FILE" | tee -a "$LOG_FILE"
}

execute_rename() {
  log "Creating backup..."
  mkdir -p "$BACKUP_DIR"

  local files
  files=$(find_clawd_files)

  if [[ -z "$files" ]]; then
    warn "No files to rename"
    return 0
  fi

  # Backup
  while IFS= read -r file; do
    local rel_path="${file#$PROJECT_ROOT/}"
    mkdir -p "$(dirname "$BACKUP_DIR/$rel_path")"
    cp "$file" "$BACKUP_DIR/$rel_path"
  done <<< "$files"

  success "Backup created: $BACKUP_DIR"

  # Rename
  log "Applying replacements..."
  local file_count=0
  local change_count=0

  while IFS= read -r file; do
    local temp_file="${file}.tmp"
    cp "$file" "$temp_file"

    for pattern in "${!PATTERNS[@]}"; do
      local replacement="${PATTERNS[$pattern]}"
      local count_before=$(grep -o "$pattern" "$temp_file" 2>/dev/null | wc -l)

      sed -i "s/${pattern//\//\\/}/${replacement//\//\\/}/g" "$temp_file"

      if (( count_before > 0 )); then
        ((change_count += count_before))
      fi
    done

    if ! cmp -s "$file" "$temp_file"; then
      mv "$temp_file" "$file"
      ((file_count++))
      success "$(basename "$file")"
    else
      rm "$temp_file"
    fi
  done <<< "$files"

  echo ""
  success "Rename complete: $file_count files, $change_count changes"
  log "Backup: $BACKUP_DIR"
}

rollback() {
  local latest=$(ls -td "$PROJECT_ROOT"/.rename-backup-* 2>/dev/null | head -1)

  if [[ -z "$latest" ]]; then
    error "No backup found"
    return 1
  fi

  warn "Rolling back to: $latest"
  read -p "Confirm rollback? (yes/no): " confirm
  if [[ "$confirm" != "yes" ]]; then
    log "Cancelled"
    return 0
  fi

  rsync -av --delete "$latest/" "$PROJECT_ROOT/" --exclude .git
  success "Rollback complete"
}

main() {
  mkdir -p "$(dirname "$LOG_FILE")"

  echo "╔════════════════════════════════════════════╗" | tee -a "$LOG_FILE"
  echo "║ OpenClaw → SENTRY Rename                   ║" | tee -a "$LOG_FILE"
  echo "║ Mode: ${1:---help}                             ║" | tee -a "$LOG_FILE"
  echo "╚════════════════════════════════════════════╝" | tee -a "$LOG_FILE"
  echo ""

  case "${1:---help}" in
    --dry-run)
      dry_run
      ;;
    --execute)
      read -p "Execute rename? (yes/no): " confirm
      [[ "$confirm" = "yes" ]] && execute_rename || log "Cancelled"
      ;;
    --rollback)
      rollback
      ;;
    *)
      echo "Usage: $0 [--dry-run|--execute|--rollback]"
      ;;
  esac

  log "Log: $LOG_FILE"
}

main "$@"
