#!/bin/bash
set -euo pipefail

ROOT_DIR="${1:-/opt/bms-intelligence}"
VAULT_DIR="${SENTINEL_VAULT:-$HOME/sentinel-vault}"

STANDARD_DOC="$ROOT_DIR/docs/claude-archive/CLAUDE_AGENT_STARTUP_STANDARD.md"
MAP_DOC="$ROOT_DIR/docs/claude-archive/CLAUDE_CODEBASE_MAP.md"

required_files=(
  "$STANDARD_DOC"
  "$MAP_DOC"
  "$VAULT_DIR/MEMORY.md"
  "$VAULT_DIR/01-Control/current-priority.md"
  "$VAULT_DIR/01-Control/active-decision-log.md"
  "$VAULT_DIR/01-Control/runtime-authority.md"
)

for file in "${required_files[@]}"; do
  if [[ ! -f "$file" ]]; then
    echo "Missing required startup file: $file" >&2
    exit 1
  fi
done

cat <<EOF
SENTINEL Agent Startup Bundle
Root: $ROOT_DIR
Vault: $VAULT_DIR

Read in this order:
1. $VAULT_DIR/MEMORY.md
2. $VAULT_DIR/01-Control/current-priority.md
3. $VAULT_DIR/01-Control/active-decision-log.md
4. $VAULT_DIR/01-Control/runtime-authority.md
5. $STANDARD_DOC
6. $MAP_DOC

Session-close contract:
- write diary entry
- update MEMORY.md
- sync SENTINEL-SYSTEM-ARCHITECTURE.md if the codebase map changed
- flag canvas files for manual review only
- commit vault changes
EOF
