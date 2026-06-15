#!/usr/bin/env bash
# =============================================================================
# sync-sentinel-ai.sh — Sync filtered mirror from bms-intelligence to sentinel-ai
# =============================================================================
# Clones the working repo, strips internal artifacts, and force-pushes
# to the public client-facing sentinel-ai repository.
#
# Usage:
#   ./scripts/sync-sentinel-ai.sh
#
# Requires:
#   - git filter-repo (pip install git-filter-repo)
#   - SSH access to github.com/Bederf/sentinel-ai.git
# =============================================================================

set -euo pipefail

REPO_URL="git@github.com:Bederf/bms-intelligence.git"
PUBLIC_REPO="git@github.com:Bederf/sentinel-ai.git"
TMP_DIR=$(mktemp -d)
FILTER_FILE=$(mktemp)

# Cleanup on exit
trap 'rm -rf "$TMP_DIR" "$FILTER_FILE"' EXIT

echo "==> Cloning working repo..."
git clone --bare --no-local "$REPO_URL" "$TMP_DIR" 2>/dev/null || git clone --bare "$REPO_URL" "$TMP_DIR"

# Paths to strip from history
cat > "$FILTER_FILE" << 'ENDSTRIP'
backups/
archive/
.claude/
.cursor/
.serena/
.planning/
.code-review-graph/
.carl/
.impeccable.md
.mypy_cache/
.pytest_cache/
.ruff_cache/
.pre-commit/
.pre-commit-config.yaml
.deploy/
openspec/
n8n/
simbiot_concept/
sentry-gateway/
gsd_traces/
skills/
k6/
load_tests/
performance-tests/
firmware/
remotion-sentinel/
security/
.venv/
backend/app/data/
CLAUDE.md
CONCERNS.md
FEATURES.md
TODO.md
GSD_PHASE_TRACEABILITY.csv
MIGRATION_099_SUMMARY.txt
.mcp.json
.sops.yaml
.gitattributes
.gitleaks.toml
CODEOWNERS
promote.sh
manage-services.sh
manage-tunnel.sh
sentinel-gsd-audit.sh
# Internal docs subdirs
docs/00-GSD-Phases/
docs/01-Control/
docs/claude-archive/
docs/_archive/
docs/_consolidation/
docs/_templates/
docs/_equipment-manuals/
docs/improvement-loops/
docs/DOCUMENTATION_RULES.md
*.mp4
*.wasm
*.bak
ENDSTRIP

echo "==> Filtering history..."
git -C "$TMP_DIR" filter-repo \
  --paths-from-file "$FILTER_FILE" \
  --invert-paths \
  --force

echo "==> Pushing to sentinel-ai..."
git -C "$TMP_DIR" remote add public "$PUBLIC_REPO"
git -C "$TMP_DIR" push public main --force

echo "==> Done. sentinel-ai is synced."
