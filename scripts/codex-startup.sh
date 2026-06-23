#!/bin/bash
set -euo pipefail

ROOT_DIR="${1:-/opt/bms-intelligence}"
PROMPT="$("$ROOT_DIR/scripts/agent-startup-prompt.sh" "$ROOT_DIR")"

exec codex -C "$ROOT_DIR" "$PROMPT"
