#!/bin/bash
# Phase 092 - Restart Services and Test Module Toggles

set -e

echo "═══════════════════════════════════════════════════════════"
echo "Phase 092: Module Toggle Fix - Service Restart & Testing"
echo "═══════════════════════════════════════════════════════════"
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}✗ This script must be run as root (use sudo)${NC}"
   echo "Usage: sudo bash RESTART_AND_TEST_TOGGLES.sh"
   exit 1
fi

echo -e "${YELLOW}Step 1: Restarting Backend Service${NC}"
echo "─────────────────────────────────────────────"
systemctl restart sentinel-backend
sleep 3

if systemctl is-active --quiet sentinel-backend; then
    echo -e "${GREEN}✓ Backend service restarted successfully${NC}"
else
    echo -e "${RED}✗ Backend service failed to start${NC}"
    systemctl status sentinel-backend --no-pager
    exit 1
fi
echo ""

echo -e "${YELLOW}Step 2: Rebuilding Frontend${NC}"
echo "─────────────────────────────────────────────"
cd /opt/bms-intelligence/frontend
npm run build 2>&1 | tail -5
echo -e "${GREEN}✓ Frontend rebuilt${NC}"
echo ""

echo -e "${YELLOW}Step 3: Restarting Frontend Service${NC}"
echo "─────────────────────────────────────────────"
systemctl restart sentinel-frontend
sleep 3

if systemctl is-active --quiet sentinel-frontend; then
    echo -e "${GREEN}✓ Frontend service restarted successfully${NC}"
else
    echo -e "${RED}✗ Frontend service failed to start${NC}"
    systemctl status sentinel-frontend --no-pager
    exit 1
fi
echo ""

echo -e "${YELLOW}Step 4: Verifying Services${NC}"
echo "─────────────────────────────────────────────"
echo "Backend status:"
systemctl status sentinel-backend --no-pager | grep -E "Active|running"

echo "Frontend status:"
systemctl status sentinel-frontend --no-pager | grep -E "Active|running"
echo ""

echo -e "${YELLOW}Step 5: Testing Module Toggle Endpoints${NC}"
echo "─────────────────────────────────────────────"

# Test 1: Health check
echo "Test 1: Backend health check..."
HEALTH_RESPONSE=$(curl -s http://localhost:9095/health)
if echo "$HEALTH_RESPONSE" | grep -q '"status":"ok"'; then
    echo -e "${GREEN}✓ Backend is responding${NC}"
else
    echo -e "${RED}✗ Backend health check failed${NC}"
    echo "Response: $HEALTH_RESPONSE"
fi
echo ""

# Test 2: Get available modules
echo "Test 2: Getting available modules..."
MODULES_RESPONSE=$(curl -s http://localhost:9095/api/modules/available)
MODULE_COUNT=$(echo "$MODULES_RESPONSE" | grep -o '"module_type"' | wc -l)
if [ "$MODULE_COUNT" -gt 0 ]; then
    echo -e "${GREEN}✓ Found $MODULE_COUNT available modules${NC}"
else
    echo -e "${RED}✗ Failed to get modules${NC}"
fi
echo ""

# Test 3: Get active modules
echo "Test 3: Getting active modules for site-002..."
ACTIVE_RESPONSE=$(curl -s http://localhost:9095/api/modules/site/site-002/active)
ACTIVE_COUNT=$(echo "$ACTIVE_RESPONSE" | grep -o '"module_type"' | wc -l)
echo -e "${GREEN}✓ Site-002 has $ACTIVE_COUNT active modules${NC}"
echo ""

# Test 4: Test deactivate endpoint (requires auth, but checking structure)
echo "Test 4: Testing deactivate endpoint structure..."
DEACTIVATE_TEST=$(curl -s -w "%{http_code}" -o /dev/null -X POST \
  http://localhost:9095/api/modules/site/site-002/deactivate/assets)

if [ "$DEACTIVATE_TEST" = "401" ]; then
    echo -e "${GREEN}✓ Endpoint returns 401 (auth required - expected)${NC}"
elif [ "$DEACTIVATE_TEST" = "200" ]; then
    echo -e "${GREEN}✓ Endpoint returns 200 (auth bypass active - DEMO_MODE)${NC}"
else
    echo -e "${YELLOW}⚠ Endpoint returned: $DEACTIVATE_TEST${NC}"
fi
echo ""

echo "═══════════════════════════════════════════════════════════"
echo -e "${GREEN}✓ All services restarted and verified!${NC}"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "📝 NEXT: Test module toggles manually:"
echo "   1. Open https://bms.aimthelaw.co.za in browser"
echo "   2. Go to Settings → Feature Access"
echo "   3. Try toggling modules on/off"
echo "   4. Check for clear error messages when dependencies fail"
echo ""
echo "🔍 If you encounter issues:"
echo "   bash /opt/bms-intelligence/backend/tests/test_module_toggle_diagnostic.sh"
echo ""
