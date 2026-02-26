#!/usr/bin/env bash
# SENTINEL secrets encryption helper
# Encrypts plaintext .env files to .env.enc (safe to commit to git)
#
# Usage:
#   sudo ./infra/scripts/sops-encrypt.sh           # Encrypt all
#   sudo ./infra/scripts/sops-encrypt.sh backend    # Encrypt backend only
#   sudo ./infra/scripts/sops-encrypt.sh frontend   # Encrypt frontend only
#
# After encrypting, commit the .enc files:
#   git add backend/.env.enc frontend/*.env.*.enc
#   git commit -m "chore(secrets): update encrypted env files"
#
# Key location: /etc/sentinel/sops-key.txt (root-owned, 600)
# Requires: sops, age

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
KEY_FILE="/etc/sentinel/sops-key.txt"
SCOPE="${1:-all}"

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

err() { echo -e "${RED}ERROR:${NC} $*" >&2; }
ok()  { echo -e "${GREEN}  OK:${NC} $*"; }

if [[ ! -f "$KEY_FILE" ]]; then
    err "Key file not found: $KEY_FILE"
    exit 1
fi

if ! command -v sops &>/dev/null; then
    err "sops not found."
    exit 1
fi

AGE_PUBKEY="age15fnu6t3nln087fx4qlzgms5zk6e00xy49dqqmu22t5eh8yp7wdxq6v3kc0"

encrypt_file() {
    local plain_file="$1"
    local enc_file="${plain_file}.enc"
    local input_type="${2:-dotenv}"

    if [[ ! -f "$plain_file" ]]; then
        err "Plaintext file not found: $plain_file"
        return 1
    fi

    SOPS_AGE_KEY_FILE="$KEY_FILE" sops \
        --encrypt \
        --age "$AGE_PUBKEY" \
        --input-type "$input_type" \
        --output-type "$input_type" \
        --config /dev/null \
        "$plain_file" > "$enc_file"

    ok "$plain_file → $enc_file"
}

echo "SENTINEL Secrets Encryption"
echo "==========================="
echo "Key: $KEY_FILE"
echo "Scope: $SCOPE"
echo ""

if [[ "$SCOPE" == "all" || "$SCOPE" == "backend" ]]; then
    echo "Backend:"
    encrypt_file "$REPO_ROOT/backend/.env"
fi

if [[ "$SCOPE" == "all" || "$SCOPE" == "frontend" ]]; then
    echo "Frontend:"
    for plain_file in "$REPO_ROOT"/frontend/.env.production "$REPO_ROOT"/frontend/.env.local "$REPO_ROOT"/frontend/.env.development; do
        [[ -f "$plain_file" ]] && encrypt_file "$plain_file"
    done
fi

SENTRY_DIR="$HOME/.sentry/gateway"
if [[ "$SCOPE" == "all" || "$SCOPE" == "sentry" ]]; then
    echo "Sentry Gateway:"
    [[ -f "$SENTRY_DIR/.env" ]] && encrypt_file "$SENTRY_DIR/.env" dotenv
    [[ -f "$SENTRY_DIR/sentry.json" ]] && encrypt_file "$SENTRY_DIR/sentry.json" json
    for plain_file in "$SENTRY_DIR"/credentials/*.json; do
        [[ -f "$plain_file" && ! "$plain_file" == *.enc ]] && encrypt_file "$plain_file" json
    done
fi

echo ""
echo "Done. Encrypted files are safe to commit:"
echo "  git add backend/.env.enc frontend/*.enc"
echo "  git commit -m 'chore(secrets): update encrypted env files'"
