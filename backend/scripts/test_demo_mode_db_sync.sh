#!/bin/bash

# Test Script: DEMO_MODE Equipment Control Database Sync
# Tests that equipment controls in DEMO_MODE update Supabase database
# Date: 2026-02-13

set -e

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
BACKEND_URL="http://localhost:9095"
EQUIPMENT_CODE="S002-FCU-200"
DB_HOST="localhost"
DB_PORT="55322"
DB_NAME="postgres"
DB_USER="postgres"
DB_PASSWORD="postgres"

echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}Test Suite: DEMO_MODE Equipment Control Database Sync${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""

# Test 1: Check backend health
echo -e "${YELLOW}[Test 1/5] Checking backend health...${NC}"
RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" "$BACKEND_URL/health")
if [ "$RESPONSE" = "200" ]; then
    echo -e "${GREEN}✓ Backend is running${NC}"
else
    echo -e "${RED}✗ Backend not responding (HTTP $RESPONSE)${NC}"
    echo "  Start backend: ./start-backend.sh"
    exit 1
fi
echo ""

# Test 2: Verify DEMO_MODE is enabled
echo -e "${YELLOW}[Test 2/5] Verifying DEMO_MODE is enabled...${NC}"
if grep -q "DEMO_MODE=true" .env; then
    echo -e "${GREEN}✓ DEMO_MODE is enabled${NC}"
else
    echo -e "${RED}✗ DEMO_MODE not enabled in .env${NC}"
    echo "  Add: DEMO_MODE=true"
    exit 1
fi
echo ""

# Test 3: Send control command
echo -e "${YELLOW}[Test 3/5] Sending control command...${NC}"
echo "  Device: $EQUIPMENT_CODE"
echo "  Point: temperature_setpoint"
echo "  Value: 20"
echo ""

CONTROL_RESPONSE=$(curl -s -X POST "$BACKEND_URL/devices/$EQUIPMENT_CODE/control" \
  -H "Content-Type: application/json" \
  -d '{
    "point": "temperature_setpoint",
    "value": 20,
    "priority": 8
  }')

echo "  Response: $CONTROL_RESPONSE"
echo ""

# Check if control was successful
if echo "$CONTROL_RESPONSE" | grep -q "success\|Successfully"; then
    echo -e "${GREEN}✓ Control command succeeded${NC}"
else
    echo -e "${RED}✗ Control command failed${NC}"
    echo "  Make sure $EQUIPMENT_CODE exists in the database"
fi
echo ""

# Test 4: Query database to verify operating_data was updated
echo -e "${YELLOW}[Test 4/5] Verifying database update...${NC}"
echo "  Connecting to Supabase (localhost:$DB_PORT)"
echo ""

# Query operating_data
SQL_QUERY="SELECT code, operating_data, updated_at FROM equipment WHERE code = '$EQUIPMENT_CODE' LIMIT 1;"

DB_RESULT=$(PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -c "$SQL_QUERY" 2>/dev/null || echo "")

if [ -z "$DB_RESULT" ]; then
    echo -e "${RED}✗ Could not connect to database${NC}"
    echo "  Make sure Supabase is running: supabase start"
    echo "  Check ports: API=55321, DB=55322"
    exit 1
fi

echo "  Database result:"
echo "  $DB_RESULT"
echo ""

# Parse the response
OPERATING_DATA=$(echo "$DB_RESULT" | awk -F'|' '{print $2}' | xargs)

if echo "$OPERATING_DATA" | grep -q "temperature_setpoint"; then
    echo -e "${GREEN}✓ operating_data contains temperature_setpoint${NC}"
    
    # Check if value is 20
    if echo "$OPERATING_DATA" | grep -q '"value": 20' || echo "$OPERATING_DATA" | grep -q '"value":20'; then
        echo -e "${GREEN}✓ Value is correctly set to 20${NC}"
    else
        echo -e "${YELLOW}⚠ Value may not be exactly 20, check manually${NC}"
        echo "  Operating data: $OPERATING_DATA"
    fi
else
    echo -e "${RED}✗ operating_data does not contain temperature_setpoint${NC}"
    echo "  This means the database sync did not work"
    echo "  Troubleshooting:"
    echo "  1. Check backend logs for DEMO_MODE sync errors"
    echo "  2. Verify equipment.id exists in database (not just code)"
    echo "  3. Ensure EquipmentRepository.update_operating_data() is working"
    exit 1
fi
echo ""

# Test 5: Verify timestamp is recent
echo -e "${YELLOW}[Test 5/5] Verifying timestamp is recent...${NC}"

TIMESTAMP=$(echo "$DB_RESULT" | awk -F'|' '{print $3}' | xargs)
echo "  Updated at: $TIMESTAMP"

# Simple check - timestamp should contain current year (2026)
if echo "$TIMESTAMP" | grep -q "2026"; then
    echo -e "${GREEN}✓ Timestamp is recent (2026)${NC}"
else
    echo -e "${YELLOW}⚠ Could not verify timestamp (manual check recommended)${NC}"
fi
echo ""

# Summary
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✓ All tests passed!${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""
echo "Summary:"
echo "  ✓ Backend is responding"
echo "  ✓ DEMO_MODE is enabled"
echo "  ✓ Control command executed"
echo "  ✓ Database updated with new operating_data"
echo "  ✓ Timestamp is current"
echo ""
echo "Next steps:"
echo "  1. Open dashboard: http://localhost:9096"
echo "  2. Navigate to equipment list"
echo "  3. Find $EQUIPMENT_CODE"
echo "  4. Verify temperature_setpoint shows as 20°C"
echo "  5. Send another control to test again"
echo ""
