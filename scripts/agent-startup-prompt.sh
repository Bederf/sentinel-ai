#!/bin/bash
set -euo pipefail

ROOT_DIR="${1:-/opt/bms-intelligence}"
VAULT_DIR="${SENTINEL_VAULT:-$HOME/sentinel-vault}"

cat <<EOF
SENTINEL startup contract

Read and follow these sources in order:
1. $VAULT_DIR/MEMORY.md
2. $VAULT_DIR/01-Control/current-priority.md
3. $VAULT_DIR/01-Control/active-decision-log.md
4. $VAULT_DIR/01-Control/runtime-authority.md
5. $ROOT_DIR/docs/claude-archive/CLAUDE_AGENT_STARTUP_STANDARD.md
6. $ROOT_DIR/docs/claude-archive/CLAUDE_CODEBASE_MAP.md

Use the shared session rules:
- follow the debug order: config, registration, permissions, site context, feature logic
- use the diary skill or equivalent at session end
- update MEMORY.md at session end
- sync SENTINEL-SYSTEM-ARCHITECTURE.md when the codebase map changes
- do not auto-edit canvas files; flag them for manual review only
- keep the workflow consistent across model or client changes
EOF
