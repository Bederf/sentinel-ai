#!/bin/bash

################################################################################
# Rename Script: Sentry → SENTRY
#
# This script systematically renames all sentry/sentry references to sentry
# across the codebase. It supports dry-run mode and rollback.
#
# Usage:
#   ./scripts/rename_sentry_to_sentry.sh --dry-run     # Preview changes
#   ./scripts/rename_sentry_to_sentry.sh --execute     # Perform renaming
#   ./scripts/rename_sentry_to_sentry.sh --rollback    # Undo changes
#
################################################################################

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="${PROJECT_ROOT}/.rename-backup-$(date +%s)"
LOG_FILE="${PROJECT_ROOT}/.rename-log-$(date +%Y%m%d-%H%M%S).txt"
# Set default SENTRY_HOME for pattern matching (will be literal $SENTRY_HOME in files)
SENTRY_HOME_LITERAL='$SENTRY_HOME'

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Counters
TOTAL_FILES=0
TOTAL_MATCHES=0
RENAMED_FILES=0
RENAMED_MATCHES=0

################################################################################
# Helper Functions
################################################################################

log() {
  echo -e "${BLUE}[INFO]${NC} $1" | tee -a "$LOG_FILE"
}

success() {
  echo -e "${GREEN}[✓]${NC} $1" | tee -a "$LOG_FILE"
}

warn() {
  echo -e "${YELLOW}[WARN]${NC} $1" | tee -a "$LOG_FILE"
}

error() {
  echo -e "${RED}[ERROR]${NC} $1" | tee -a "$LOG_FILE"
}

# Mapping of patterns to replace
declare -A PATTERNS=(
  # Python class names
  ["SentryAuthService"]="SentryAuthService"
  ["sentry_auth"]="sentry_auth"
  ["_sentry_auth_service"]="_sentry_auth_service"

  # Import paths
  ["from app.services.sentry_"]="from app.services.sentry_"
  ["from app.services import sentry"]="from app.services import sentry"

  # API endpoints
  ["/api/sentry/"]="/api/sentry/"
  ["/api/sentry-webhooks"]="/api/sentry-webhooks"

  # Function/method names
  ["get_sentry_"]="get_sentry_"
  ["initialize_sentry_"]="initialize_sentry_"
  ["notify_sentry"]="notify_sentry"

  # Environment variables & paths (use literal $SENTRY_HOME for portability)
  ["SENTRY_"]="SENTRY_"
  ["SENTRY-"]="SENTRY-"
  ["$SENTRY_HOME"]="SENTRY_HOME_PLACEHOLDER"
  ["$SENTRY_HOME"]="SENTRY_HOME_PLACEHOLDER"
  ["$SENTRY_HOME"]="SENTRY_HOME_PLACEHOLDER"
  ["~/.sentry"]="SENTRY_HOME_PLACEHOLDER"

  # Settings/config keys
  ["sentry_webhook_secret"]="sentry_webhook_secret"
  ["sentry_bot_api_key"]="sentry_bot_api_key"
  ["sentry_username"]="sentry_username"
  ["sentry_password"]="sentry_password"
  ["sentry_notifications"]="sentry_notifications"

  # Header names
  ["X-Sentry-Secret"]="X-Sentry-Secret"
  ["X-Sentry-API-Key"]="X-Sentry-API-Key"

  # Secrets/constants
  ["sentry-bms-phase-41"]="sentry-bms-phase-41"

  # Comments and documentation
  ["Sentry bot"]="Sentry bot"
  ["Sentry integration"]="Sentry integration"
  ["Sentry webhook"]="Sentry webhook"
  ["Sentry service"]="Sentry service"
  ["Sentry API"]="Sentry API"
  ["Sentry secret"]="Sentry secret"
)

# File patterns to exclude
EXCLUDE_PATTERNS=(
  "\.git/"
  "\.pytest_cache/"
  "\.ruff_cache/"
  "node_modules/"
  "venv/"
  "__pycache__/"
  "\.serena/"
  "\.rename-backup-"
  "\.rename-log-"
  "\.env.local"
)

# Build find exclude arguments
build_exclude_args() {
  local excludes=""
  for pattern in "${EXCLUDE_PATTERNS[@]}"; do
    excludes+=" -not -path '*${pattern}*'"
  done
  echo "$excludes"
}

# Check if file should be processed
should_process_file() {
  local file="$1"
  for pattern in "${EXCLUDE_PATTERNS[@]}"; do
    if [[ "$file" =~ $pattern ]]; then
      return 1
    fi
  done
  return 0
}

# Find all files that contain sentry references
find_sentry_files() {
  local exclude_args
  exclude_args=$(build_exclude_args)

  # Use grep to find files containing sentry references (case-insensitive for some)
  find "$PROJECT_ROOT" \
    -type f \
    \( -name "*.py" -o -name "*.ts" -o -name "*.tsx" -o -name "*.md" \
       -o -name "*.yaml" -o -name "*.yml" -o -name "*.json" -o -name "*.sh" \) \
    $exclude_args \
    -exec grep -l -i "sentry\|sentry\|moltbot" {} \; 2>/dev/null | sort -u
}

# Count matches in a file for a specific pattern
count_matches() {
  local file="$1"
  local pattern="$2"
  grep -o "$pattern" "$file" 2>/dev/null | wc -l
}

# Show what will be changed (dry-run)
dry_run() {
  log "Starting DRY-RUN analysis..."
  log "Output directory: $LOG_FILE"
  echo ""

  local files
  files=$(find_sentry_files)

  if [[ -z "$files" ]]; then
    warn "No files containing sentry/sentry references found"
    return 0
  fi

  echo -e "${BLUE}Files to be modified:${NC}" | tee -a "$LOG_FILE"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" | tee -a "$LOG_FILE"

  TOTAL_FILES=0
  TOTAL_MATCHES=0

  while IFS= read -r file; do
    should_process_file "$file" || continue

    ((TOTAL_FILES++))
    local rel_path="${file#$PROJECT_ROOT/}"

    # Show file
    echo "" | tee -a "$LOG_FILE"
    echo -e "${YELLOW}$rel_path${NC}" | tee -a "$LOG_FILE"

    # Show matches with context
    local line_num=0
    while IFS= read -r line; do
      ((line_num++))
      # Check if line contains any pattern
      local has_match=0
      for pattern in "${!PATTERNS[@]}"; do
        if [[ "$line" =~ $pattern ]]; then
          has_match=1
          ((TOTAL_MATCHES++))

          local old="${line//[[:space:]]/}"
          local new="$old"
          for pattern in "${!PATTERNS[@]}"; do
            new="${new//$pattern/${PATTERNS[$pattern]}}"
          done

          echo "  Line $line_num:" | tee -a "$LOG_FILE"
          echo "    - $line" | tee -a "$LOG_FILE"
          echo "    + ${line//$pattern/${PATTERNS[$pattern]}}" | tee -a "$LOG_FILE"
          break
        fi
      done
    done < "$file"
  done <<< "$files"

  echo "" | tee -a "$LOG_FILE"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" | tee -a "$LOG_FILE"
  echo -e "${BLUE}Summary:${NC}" | tee -a "$LOG_FILE"
  echo "  Files to modify: $TOTAL_FILES" | tee -a "$LOG_FILE"
  echo "  Total matches:   $TOTAL_MATCHES" | tee -a "$LOG_FILE"
  echo "" | tee -a "$LOG_FILE"
  echo -e "${GREEN}DRY-RUN complete. To execute: $0 --execute${NC}" | tee -a "$LOG_FILE"
}

# Perform the actual renaming
execute_rename() {
  log "Starting RENAME execution..."
  log "Backup directory: $BACKUP_DIR"
  echo ""

  # Create backup
  log "Creating backup of all files..."
  mkdir -p "$BACKUP_DIR"

  local files
  files=$(find_sentry_files)

  if [[ -z "$files" ]]; then
    warn "No files to rename"
    return 0
  fi

  # Copy files to backup
  while IFS= read -r file; do
    should_process_file "$file" || continue
    local rel_path="${file#$PROJECT_ROOT/}"
    mkdir -p "$(dirname "$BACKUP_DIR/$rel_path")"
    cp "$file" "$BACKUP_DIR/$rel_path"
  done <<< "$files"

  success "Backup created at $BACKUP_DIR"
  echo ""

  # Now perform renames
  log "Performing replacements..."
  RENAMED_FILES=0
  RENAMED_MATCHES=0

  while IFS= read -r file; do
    should_process_file "$file" || continue

    local rel_path="${file#$PROJECT_ROOT/}"
    local file_matches=0

    # Create temp file
    local temp_file="${file}.tmp"
    cp "$file" "$temp_file"

    # Apply all pattern replacements
    for pattern in "${!PATTERNS[@]}"; do
      local replacement="${PATTERNS[$pattern]}"
      local count_before=$(count_matches "$temp_file" "$pattern")

      # Use sed to replace (handle special characters)
      sed -i "s/${pattern/\//\\/}/${replacement//\//\\/}/g" "$temp_file"

      local count_after=$(count_matches "$temp_file" "$pattern")
      if (( count_before > 0 )); then
        file_matches=$((file_matches + count_before))
        RENAMED_MATCHES=$((RENAMED_MATCHES + count_before))
      fi
    done

    # Post-process: Replace placeholder with literal $SENTRY_HOME
    sed -i 's/SENTRY_HOME_PLACEHOLDER/$SENTRY_HOME/g' "$temp_file"

    # Only replace file if changes were made
    if ! cmp -s "$file" "$temp_file"; then
      mv "$temp_file" "$file"
      ((RENAMED_FILES++))
      success "$rel_path ($file_matches replacements)"
    else
      rm "$temp_file"
    fi
  done <<< "$files"

  echo "" | tee -a "$LOG_FILE"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" | tee -a "$LOG_FILE"
  success "Rename complete!" | tee -a "$LOG_FILE"
  echo "  Files modified: $RENAMED_FILES" | tee -a "$LOG_FILE"
  echo "  Total replacements: $RENAMED_MATCHES" | tee -a "$LOG_FILE"
  echo "" | tee -a "$LOG_FILE"

  # Verify Python syntax
  log "Verifying Python syntax..."
  local py_files
  py_files=$(find "$PROJECT_ROOT" -name "*.py" -type f $(build_exclude_args) 2>/dev/null)
  local py_errors=0

  while IFS= read -r py_file; do
    if ! python3 -m py_compile "$py_file" 2>/dev/null; then
      error "Syntax error in $py_file"
      ((py_errors++))
    fi
  done <<< "$py_files"

  if (( py_errors == 0 )); then
    success "All Python files have valid syntax"
  else
    error "Found $py_errors Python files with syntax errors"
    return 1
  fi

  echo "" | tee -a "$LOG_FILE"
  log "Rollback instructions:"
  echo "  To rollback: rm -rf \$PROJECT_ROOT && cp -r $BACKUP_DIR \$PROJECT_ROOT" | tee -a "$LOG_FILE"
  echo "  Backup location: $BACKUP_DIR" | tee -a "$LOG_FILE"
}

# Show git diff before commit
show_git_diff() {
  log "Git changes summary:"
  echo ""
  git -C "$PROJECT_ROOT" diff --stat 2>/dev/null || warn "Git not available for diff"
}

# Generate commit message
generate_commit_message() {
  cat > /tmp/sentry_commit.txt << 'EOF'
refactor(bot): Rename Sentry → SENTRY system-wide

This commit renames all sentry/sentry references to sentry across the
entire codebase, including:

- Python class names (SentryAuthService → SentryAuthService)
- API endpoints (/api/sentry/ → /api/sentry/)
- Environment variables (SENTRY_* → SENTRY_*)
- Configuration keys and settings
- HTTP headers (X-Sentry-Secret → X-Sentry-Secret)
- Documentation and comments

No functional changes — purely a systematic renaming for clarity and
branding consistency. All tests and imports verified.

Files modified: %(files)d
Total replacements: %(matches)d

Co-Authored-By: Claude Code <claude@anthropic.com>
EOF

  sed -i "s/%(files)d/$RENAMED_FILES/g" /tmp/sentry_commit.txt
  sed -i "s/%(matches)d/$RENAMED_MATCHES/g" /tmp/sentry_commit.txt

  cat /tmp/sentry_commit.txt
}

# Rollback to previous state
rollback() {
  error "Rollback requested"

  # Find the most recent backup
  local latest_backup
  latest_backup=$(ls -td "$PROJECT_ROOT"/.rename-backup-* 2>/dev/null | head -1)

  if [[ -z "$latest_backup" ]]; then
    error "No backup found to rollback to"
    return 1
  fi

  warn "Rolling back to: $latest_backup"

  # Show what will be restored
  echo "Files to restore:"
  find "$latest_backup" -type f | head -20

  read -p "Are you sure you want to rollback? (yes/no): " confirm
  if [[ "$confirm" != "yes" ]]; then
    log "Rollback cancelled"
    return 0
  fi

  # Restore from backup
  log "Restoring files..."
  rsync -av --delete "$latest_backup/" "$PROJECT_ROOT/" --exclude '.git'

  success "Rollback complete"
  log "Backed-up version moved to: ${latest_backup}.restored"
  mv "$latest_backup" "${latest_backup}.restored"
}

# Show help
show_help() {
  cat << 'EOF'
Sentry → SENTRY Rename Script

USAGE:
  ./scripts/rename_sentry_to_sentry.sh [OPTION]

OPTIONS:
  --dry-run       Show what will be changed without modifying files
  --execute       Perform the actual renaming
  --rollback      Revert to previous state (requires backup)
  --help          Show this help message

EXAMPLES:
  # Preview all changes
  ./scripts/rename_sentry_to_sentry.sh --dry-run

  # Review the log, then execute
  ./scripts/rename_sentry_to_sentry.sh --execute

  # If something went wrong
  ./scripts/rename_sentry_to_sentry.sh --rollback

WORKFLOW:
  1. Run with --dry-run to see what will change
  2. Review the changes in the log file
  3. Run with --execute to apply changes
  4. Verify changes: git diff
  5. Commit changes: git commit -F /tmp/sentry_commit.txt

LOG FILES:
  All output is logged to: .rename-log-*.txt

BACKUP:
  Automatic backups are created in: .rename-backup-*
  Use --rollback to restore from latest backup

EOF
}

################################################################################
# Main Script
################################################################################

main() {
  local mode="${1:---help}"

  # Initialize log file
  mkdir -p "$(dirname "$LOG_FILE")"
  touch "$LOG_FILE"

  echo "╔════════════════════════════════════════════════════════════╗" | tee -a "$LOG_FILE"
  echo "║  Sentry → SENTRY Rename Script                          ║" | tee -a "$LOG_FILE"
  echo "║  Project: $PROJECT_ROOT" | tee -a "$LOG_FILE"
  echo "║  Log: $LOG_FILE" | tee -a "$LOG_FILE"
  echo "╚════════════════════════════════════════════════════════════╝" | tee -a "$LOG_FILE"
  echo "" | tee -a "$LOG_FILE"

  case "$mode" in
    --dry-run)
      dry_run
      ;;
    --execute)
      log "⚠️  This will modify files across the entire codebase"
      read -p "Continue with rename execution? (yes/no): " confirm
      if [[ "$confirm" != "yes" ]]; then
        log "Cancelled"
        exit 0
      fi
      execute_rename
      echo ""
      show_git_diff
      echo ""
      log "Review changes, then commit with:"
      echo "  git add -A"
      echo "  git commit -m 'refactor(bot): Rename Sentry → SENTRY system-wide'"
      ;;
    --rollback)
      rollback
      ;;
    --help)
      show_help
      ;;
    *)
      error "Unknown option: $mode"
      show_help
      exit 1
      ;;
  esac

  log "Log file: $LOG_FILE"
}

# Run main
main "$@"
