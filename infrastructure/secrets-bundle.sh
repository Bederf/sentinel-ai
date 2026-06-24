#!/usr/bin/env bash
# SENTINEL Secrets Bundle — encrypt/decrypt/rotate workflow
#
# Manages an encrypted archive of all runtime secrets for offsite storage.
# Uses age (https://age-encryption.org) — no GPG infrastructure needed.
#
# USAGE:
#   ./secrets-bundle.sh encrypt    # create secrets.tar.age from live files
#   ./secrets-bundle.sh decrypt    # decrypt to secrets.tar (inspect/recover)
#   ./secrets-bundle.sh rotate     # regenerate keys, re-encrypt, push offsite
#
# REQUIREMENTS:
#   age installed: sudo apt-get install age
#   Offsite destination: set DEST= in this file or pass as env var
#
# FILES BUNDLED:
#   - backend/.env (181 lines — all API keys, DB creds, secrets)
#   - frontend/.env.production (VITE_API_URL)
#   - /etc/cloudflared/sentinel-bms-credentials.json (tunnel auth)
#   - /etc/mosquitto/passwd (MQTT credentials)
#   - WireGuard configs (/etc/wireguard/*.conf if present)
#   - SSH host keys (/etc/ssh/ssh_host_*)
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_ENV="$REPO_DIR/backend/.env"
FRONTEND_ENV="$REPO_DIR/frontend/.env.production"
CF_CRED="/etc/cloudflared/sentinel-bms-credentials.json"
MOSQUITTO_PASSWD="/etc/mosquitto/passwd"

# Offsite destination — set via env var or edit this default
DEST="${DEST:-scp://user@offsite-backup.example.com:/backups/sentinel/secrets/}"
# Or for Backblaze B2:
# DEST="${DEST:-s3://my-bucket/sentinel/secrets/}"

KEY_FILE="${KEY_FILE:-/etc/sentinel/secrets-key.txt}"
BUNDLE_NAME="sentinel-secrets-$(date +%Y%m%d).tar.age"
WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

collect_files() {
  local files=()
  for f in "$BACKEND_ENV" "$FRONTEND_ENV" "$CF_CRED" "$MOSQUITTO_PASSWD"; do
    if [[ -f "$f" ]]; then
      files+=("$f")
      echo "  + $f"
    else
      echo "  - $f (not found, skipped)"
    fi
  done
  # WireGuard configs (optional)
  if ls /etc/wireguard/*.conf 2>/dev/null; then
    files+=($(ls /etc/wireguard/*.conf))
  fi
  # SSH host keys (optional — for re-identification)
  for key in /etc/ssh/ssh_host_*; do
    if [[ -f "$key" ]]; then
      files+=("$key")
      echo "  + $key"
      break  # Only add if we haven't already
    fi
  done
  printf '%s\n' "${files[@]}"
}

cmd_encrypt() {
  echo "=== Creating secrets bundle ==="
  local files
  files=$(collect_files)

  if [[ -z "$files" ]]; then
    echo "ERROR: No secret files found to bundle."
    exit 1
  fi

  # Generate age key pair if it doesn't exist
  if [[ ! -f "$KEY_FILE" ]]; then
    echo "Generating new age key pair..."
    mkdir -p "$(dirname "$KEY_FILE")"
    age-keygen -o "$KEY_FILE"
    chmod 600 "$KEY_FILE"
    echo "  Key saved to: $KEY_FILE"
    echo "  ⚠ PUBLIC KEY (save this for recovery):"
    age-keygen -y "$KEY_FILE"
  fi

  # Create tarball and encrypt
  tar -cf "$WORK_DIR/secrets.tar" -C / $(echo "$files" | sed 's|^/||') 2>/dev/null
  age -e -i "$KEY_FILE" -o "$BUNDLE_NAME" "$WORK_DIR/secrets.tar"
  echo "  Bundle created: $BUNDLE_NAME ($(stat -c%s "$BUNDLE_NAME") bytes)"

  # Push offsite
  if [[ -n "$DEST" ]]; then
    echo "  Pushing to: $DEST"
    case "$DEST" in
      scp://*)
        rsync -avz "$BUNDLE_NAME" "${DEST/scp:\/\//}" || echo "  ⚠ rsync failed — push manually"
        ;;
      s3://*)
        aws s3 cp "$BUNDLE_NAME" "$DEST" || echo "  ⚠ aws s3 cp failed — push manually"
        ;;
      *)
        cp "$BUNDLE_NAME" "$DEST" || echo "  ⚠ copy failed — push manually"
        ;;
    esac
  else
    echo "  ⚠ No DEST set. Bundle is local: $BUNDLE_NAME"
    echo "    Store it offsite (Backblaze B2, S3, password manager vault)"
  fi

  # Test that decrypt works
  echo "  Verifying: decrypt test..."
  age -d -i "$KEY_FILE" -o /dev/null "$BUNDLE_NAME" 2>/dev/null &&
    echo "  ✅ Bundle verified" ||
    echo "  ⚠ Decrypt test FAILED"

  echo "=== Done ==="
}

cmd_decrypt() {
  local bundle="${1:-$BUNDLE_NAME}"
  if [[ ! -f "$bundle" ]]; then
    echo "Bundle not found: $bundle"
    echo "Usage: $0 decrypt <bundle-file>"
    exit 1
  fi
  echo "=== Decrypting: $bundle ==="
  age -d -i "$KEY_FILE" -o "$WORK_DIR/secrets.tar" "$bundle"
  tar -tvf "$WORK_DIR/secrets.tar"
  echo "Files extracted to: $WORK_DIR/secrets.tar"
  echo "  tar -xvf $WORK_DIR/secrets.tar -C /   # to restore"
}

cmd_rotate() {
  echo "=== Rotating secrets key ==="
  local old_key="$KEY_FILE"
  local old_backup="${KEY_FILE}.$(date +%Y%m%d).bak"
  if [[ -f "$old_key" ]]; then
    cp "$old_key" "$old_backup"
    echo "  Old key backed up: $old_backup"
  fi
  rm -f "$old_key"
  cmd_encrypt
  echo "  ⚠ Keep the old key backup until all old bundles are rotated"
}

case "${1:-help}" in
  encrypt) cmd_encrypt ;;
  decrypt) cmd_decrypt "${2:-}" ;;
  rotate)  cmd_rotate ;;
  *)
    echo "Usage: $0 {encrypt|decrypt|rotate}"
    echo ""
    echo "  encrypt  — bundle all secrets into age-encrypted tar, push offsite"
    echo "  decrypt  — decrypt a bundle for inspection or recovery"
    echo "  rotate   — generate new key, re-encrypt, push offsite"
    echo ""
    echo "Key file:    $KEY_FILE"
    echo "Offsite:     $DEST"
    echo ""
    echo "First run:   $0 encrypt"
    echo "  → generates /etc/sentinel/secrets-key.txt"
    echo "  → creates sentinel-secrets-YYYYMMDD.tar.age"
    echo "  → SAVE the PUBLIC key fingerprint for disaster recovery"
    ;;
esac
