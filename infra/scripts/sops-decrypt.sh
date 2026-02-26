#!/usr/bin/env bash
# SENTINEL secrets decryption helper
# Decrypts SOPS-encrypted .env.enc files to plaintext .env files
#
# Usage:
#   sudo ./infra/scripts/sops-decrypt.sh           # Decrypt all
#   sudo ./infra/scripts/sops-decrypt.sh backend    # Decrypt backend only
#   sudo ./infra/scripts/sops-decrypt.sh frontend   # Decrypt frontend only
#
# Key location: /etc/sentinel/sops-key.txt (root-owned, 600)
# Requires: sops, age

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
KEY_FILE="/etc/sentinel/sops-key.txt"
SCOPE="${1:-all}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

err() { echo -e "${RED}ERROR:${NC} $*" >&2; }
ok()  { echo -e "${GREEN}  OK:${NC} $*"; }

# Preflight checks
if [[ ! -f "$KEY_FILE" ]]; then
    err "Key file not found: $KEY_FILE"
    err "Generate with: sudo age-keygen -o $KEY_FILE"
    exit 1
fi

if ! command -v sops &>/dev/null; then
    err "sops not found. Install: https://github.com/getsops/sops/releases"
    exit 1
fi

decrypt_file() {
    local enc_file="$1"
    local out_file="${enc_file%.enc}"

    if [[ ! -f "$enc_file" ]]; then
        err "Encrypted file not found: $enc_file"
        return 1
    fi

    SOPS_AGE_KEY_FILE="$KEY_FILE" sops \
        --decrypt \
        --input-type dotenv \
        --output-type dotenv \
        "$enc_file" > "$out_file"

    # Set restrictive permissions (owner read-only)
    chmod 600 "$out_file"
    # Set ownership to bederf (the service user)
    chown bederf:bederf "$out_file" 2>/dev/null || true

    ok "$enc_file → $out_file"
}

echo "SENTINEL Secrets Decryption"
echo "=========================="
echo "Key: $KEY_FILE"
echo "Scope: $SCOPE"
echo ""

if [[ "$SCOPE" == "all" || "$SCOPE" == "backend" ]]; then
    echo "Backend:"
    decrypt_file "$REPO_ROOT/backend/.env.enc"
fi

if [[ "$SCOPE" == "all" || "$SCOPE" == "frontend" ]]; then
    echo "Frontend:"
    for enc_file in "$REPO_ROOT"/frontend/.env.*.enc; do
        [[ -f "$enc_file" ]] && decrypt_file "$enc_file"
    done
fi

echo ""
echo "Done. Restart services to pick up new secrets:"
echo "  sudo systemctl restart sentinel-backend sentinel-frontend"
