#!/usr/bin/env bash
# Smoke test for compiled SENTINEL backend.
# Usage: ./deployment/smoke_test.sh [path-to-binary]
set -uo pipefail

BINARY="${1:-deployment/dist/sentinel-backend}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PORT="${PORT:-9090}"

if [ ! -f "$BINARY" ]; then
    echo "ERROR: Binary not found at $BINARY"
    echo "Run deployment/build.sh first."
    exit 1
fi

echo "=== SENTINEL Smoke Test ==="
echo "Binary: $BINARY ($(du -h "$BINARY" | cut -f1))"
echo "Port:   $PORT"
echo ""

# Verify required env vars are set
REQUIRED_VARS=(SITE_ID PLANT_SITE_ID BUILDING_NAME JWT_SECRET_KEY SENTRY_WEBHOOK_SECRET CONSENT_HASH_SALT INGESTION_MODE SUPABASE_URL SUPABASE_KEY SUPABASE_SERVICE_ROLE_KEY)
for var in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!var:-}" ]; then
        echo "ERROR: $var is not set. All env vars are required."
        echo "Required: ${REQUIRED_VARS[*]}"
        exit 1
    fi
done
export PORT="$PORT"

echo "1. Starting backend..."
"$BINARY" &
PID=$!

cleanup() {
    kill "$PID" 2>/dev/null || true
    wait "$PID" 2>/dev/null || true
}
trap cleanup EXIT

echo "2. Waiting for startup (polling health endpoint)..."
for i in $(seq 1 30); do
    HEALTH_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:$PORT/api/health" 2>/dev/null || echo "000")
    if [ "$HEALTH_CODE" = "200" ]; then
        echo "   ✅ Health endpoint ready after ${i}s"
        break
    fi
    sleep 1
done

if [ "$HEALTH_CODE" != "200" ]; then
    echo "   ❌ Health endpoint not ready after 30s (last code: $HEALTH_CODE)"
    exit 1
fi

echo "3. Checking root endpoint..."
ROOT_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:$PORT/" 2>/dev/null || echo "000")
if [ "$ROOT_CODE" = "200" ] || [ "$ROOT_CODE" = "302" ]; then
    echo "   ✅ Root endpoint: $ROOT_CODE"
else
    echo "   ❌ Root endpoint: $ROOT_CODE"
    exit 1
fi

echo "4. Checking OpenAPI schema..."
OAPI_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:$PORT/openapi.json" 2>/dev/null || echo "000")
OAPI_PATHS=$(curl -s "http://localhost:$PORT/openapi.json" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('paths',{})))" 2>/dev/null || echo "0")
if [ "$OAPI_CODE" = "200" ] && [ "$OAPI_PATHS" -gt 10 ]; then
    echo "   ✅ OpenAPI schema: $OAPI_CODE ($OAPI_PATHS paths)"
else
    echo "   ⚠️  OpenAPI schema: $OAPI_CODE ($OAPI_PATHS paths)"
fi

echo ""
echo "=== Smoke test complete ==="
echo "Binary size: $(du -h "$BINARY" | cut -f1)"
echo "Health check: $HEALTH_CODE"
echo "Routes: $OAPI_PATHS"
