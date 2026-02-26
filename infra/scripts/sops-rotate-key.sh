#!/usr/bin/env bash
# SENTINEL age key rotation script
# Generates a new age key and re-encrypts all secrets
#
# Usage:
#   sudo ./infra/scripts/sops-rotate-key.sh
#
# Recommended: Run quarterly (90-day cycle) per FSR compliance
#
# Steps:
#   1. Decrypt all .enc files with current key
#   2. Generate new age key
#   3. Update .sops.yaml with new public key
#   4. Re-encrypt all files with new key
#   5. Archive old key (kept for 90 days in case of rollback)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
KEY_FILE="/etc/sentinel/sops-key.txt"
SOPS_CONFIG="$REPO_ROOT/.sops.yaml"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

err()  { echo -e "${RED}ERROR:${NC} $*" >&2; }
ok()   { echo -e "${GREEN}  OK:${NC} $*"; }
warn() { echo -e "${YELLOW}WARN:${NC} $*"; }

echo "SENTINEL Key Rotation"
echo "====================="
echo ""

# Step 1: Verify current key works
if [[ ! -f "$KEY_FILE" ]]; then
    err "Current key not found: $KEY_FILE"
    exit 1
fi

CURRENT_PUB=$(grep 'public key' "$KEY_FILE" | awk '{print $NF}')
echo "Current public key: $CURRENT_PUB"

# Step 2: Decrypt all files with current key
echo ""
echo "Step 1: Decrypting with current key..."
"$REPO_ROOT/infra/scripts/sops-decrypt.sh" all

# Step 3: Archive current key
ARCHIVE_DIR="/etc/sentinel/archived-keys"
mkdir -p "$ARCHIVE_DIR"
ARCHIVE_NAME="sops-key-$(date +%Y%m%d-%H%M%S).txt"
cp "$KEY_FILE" "$ARCHIVE_DIR/$ARCHIVE_NAME"
chmod 600 "$ARCHIVE_DIR/$ARCHIVE_NAME"
ok "Archived current key to $ARCHIVE_DIR/$ARCHIVE_NAME"

# Step 4: Generate new key
echo ""
echo "Step 2: Generating new key..."
age-keygen -o "$KEY_FILE" 2>&1
chmod 600 "$KEY_FILE"
NEW_PUB=$(grep 'public key' "$KEY_FILE" | awk '{print $NF}')
ok "New public key: $NEW_PUB"

# Step 5: Update .sops.yaml with new public key
echo ""
echo "Step 3: Updating .sops.yaml..."
sed -i "s|$CURRENT_PUB|$NEW_PUB|g" "$SOPS_CONFIG"
ok "Updated .sops.yaml"

# Step 6: Re-encrypt with new key
echo ""
echo "Step 4: Re-encrypting with new key..."
"$REPO_ROOT/infra/scripts/sops-encrypt.sh" all

# Step 7: Verify round-trip
echo ""
echo "Step 5: Verifying round-trip..."
SOPS_AGE_KEY_FILE="$KEY_FILE" sops --decrypt --input-type dotenv --output-type dotenv "$REPO_ROOT/backend/.env.enc" > /dev/null 2>&1
ok "Round-trip verification passed"

# Step 8: Clean up old archived keys (>90 days)
find "$ARCHIVE_DIR" -name 'sops-key-*.txt' -mtime +90 -delete 2>/dev/null && \
    ok "Cleaned up archived keys older than 90 days" || true

echo ""
echo "Key rotation complete!"
echo ""
echo "Next steps:"
echo "  1. Commit updated .sops.yaml and .enc files"
echo "  2. Restart services: sudo systemctl restart sentinel-backend sentinel-frontend"
echo "  3. Verify services start correctly"
echo ""
echo "Rollback (if needed):"
echo "  sudo cp $ARCHIVE_DIR/$ARCHIVE_NAME $KEY_FILE"
echo "  sudo ./infra/scripts/sops-decrypt.sh"
