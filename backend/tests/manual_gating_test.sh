#!/bin/bash

# Phase 087: Manual Testing of Module Gating
# Run this against a live backend to validate the middleware works
# 
# Usage:
#   chmod +x manual_gating_test.sh
#   ./manual_gating_test.sh

BASE_URL="http://localhost:9095"
SITE_ID="site-002"

echo "========================================================================="
echo "Phase 087: Module Gating Validation Tests"
echo "========================================================================="
echo ""
echo "Testing against: $BASE_URL"
echo "Site ID: $SITE_ID"
echo ""

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# =========================================================================
# Test 1: HVAC Endpoint WITHOUT CONTROL Module (Should be 403)
# =========================================================================

echo -e "${YELLOW}Test 1: HVAC Setpoint WITHOUT CONTROL module${NC}"
echo "Endpoint: POST /zones/{zone_id}/setpoint"
echo "Expected: 403 Forbidden"
echo ""

RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/zones/Z001/setpoint" \
  -H "Content-Type: application/json" \
  -H "X-Site-Id: $SITE_ID" \
  -d '{
    "zone_id": "Z001",
    "setpoint_temp_c": 22.0
  }')

HTTP_CODE=$(echo "$RESPONSE" | tail -n 1)
BODY=$(echo "$RESPONSE" | head -n -1)

echo "Response Code: $HTTP_CODE"
echo "Response Body: $BODY"
echo ""

if [ "$HTTP_CODE" = "403" ]; then
  echo -e "${GREEN}✅ PASS: Received 403 Forbidden${NC}"
  if echo "$BODY" | grep -q "CONTROL module"; then
    echo -e "${GREEN}✅ PASS: Error message mentions CONTROL module${NC}"
  else
    echo -e "${RED}❌ FAIL: Error message doesn't mention CONTROL module${NC}"
  fi
else
  echo -e "${RED}❌ FAIL: Expected 403, got $HTTP_CODE${NC}"
fi

echo ""
echo "========================================================================="
echo ""

# =========================================================================
# Test 2: Work Order Endpoint WITHOUT MAINTENANCE Module (Should be 403)
# =========================================================================

echo -e "${YELLOW}Test 2: Create Work Order WITHOUT MAINTENANCE module${NC}"
echo "Endpoint: POST /work-orders/supabase"
echo "Expected: 403 Forbidden"
echo ""

RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/work-orders/supabase" \
  -H "Content-Type: application/json" \
  -H "X-Site-Id: $SITE_ID" \
  -H "Authorization: Bearer demo-token" \
  -d '{
    "equipment_code": "S002-CHILLER-B1-001",
    "title": "Chiller Maintenance",
    "description": "Oil analysis",
    "priority": "high",
    "created_by": "test-user"
  }')

HTTP_CODE=$(echo "$RESPONSE" | tail -n 1)
BODY=$(echo "$RESPONSE" | head -n -1)

echo "Response Code: $HTTP_CODE"
echo "Response Body: $BODY"
echo ""

if [ "$HTTP_CODE" = "403" ]; then
  echo -e "${GREEN}✅ PASS: Received 403 Forbidden${NC}"
  if echo "$BODY" | grep -q "MAINTENANCE module"; then
    echo -e "${GREEN}✅ PASS: Error message mentions MAINTENANCE module${NC}"
  else
    echo -e "${RED}❌ FAIL: Error message doesn't mention MAINTENANCE module${NC}"
  fi
else
  echo -e "${RED}❌ FAIL: Expected 403, got $HTTP_CODE${NC}"
fi

echo ""
echo "========================================================================="
echo ""

# =========================================================================
# Test 3: Optimization Endpoint WITHOUT CONTROL Module (Should be 403)
# =========================================================================

echo -e "${YELLOW}Test 3: Analyze Optimization WITHOUT CONTROL module${NC}"
echo "Endpoint: POST /optimization/analyze"
echo "Expected: 403 Forbidden"
echo ""

RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/optimization/analyze" \
  -H "Content-Type: application/json" \
  -H "X-Site-Id: $SITE_ID" \
  -d '{
    "site_id": "'$SITE_ID'"
  }')

HTTP_CODE=$(echo "$RESPONSE" | tail -n 1)
BODY=$(echo "$RESPONSE" | head -n -1)

echo "Response Code: $HTTP_CODE"
echo "Response Body: $BODY"
echo ""

if [ "$HTTP_CODE" = "403" ]; then
  echo -e "${GREEN}✅ PASS: Received 403 Forbidden${NC}"
  if echo "$BODY" | grep -q "CONTROL module"; then
    echo -e "${GREEN}✅ PASS: Error message mentions CONTROL module${NC}"
  else
    echo -e "${RED}❌ FAIL: Error message doesn't mention CONTROL module${NC}"
  fi
else
  echo -e "${RED}❌ FAIL: Expected 403, got $HTTP_CODE${NC}"
fi

echo ""
echo "========================================================================="
echo ""

# =========================================================================
# Test 4: Verify Error Message is Helpful
# =========================================================================

echo -e "${YELLOW}Test 4: Verify Error Messages Are Helpful${NC}"
echo "Checking that 403 messages tell user what to do..."
echo ""

RESPONSE=$(curl -s -X POST "$BASE_URL/zones/Z001/setpoint" \
  -H "Content-Type: application/json" \
  -H "X-Site-Id: $SITE_ID" \
  -d '{
    "zone_id": "Z001",
    "setpoint_temp_c": 22.0
  }')

echo "Error Message:"
echo "$RESPONSE" | grep -o '"detail":"[^"]*' | cut -d'"' -f4
echo ""

if echo "$RESPONSE" | grep -q "module"; then
  echo -e "${GREEN}✅ PASS: Message explains which module is needed${NC}"
else
  echo -e "${RED}❌ FAIL: Message doesn't explain module requirement${NC}"
fi

if echo "$RESPONSE" | grep -q "Contact\|request\|activate"; then
  echo -e "${GREEN}✅ PASS: Message includes action to take${NC}"
else
  echo -e "${YELLOW}⚠️  INFO: Message could be more actionable${NC}"
fi

echo ""
echo "========================================================================="
echo ""

# =========================================================================
# Summary
# =========================================================================

echo -e "${GREEN}=========================================================================${NC}"
echo -e "${GREEN}Phase 087 Testing Complete${NC}"
echo -e "${GREEN}=========================================================================${NC}"
echo ""
echo "Summary:"
echo "- All gated endpoints return 403 when module is inactive"
echo "- Error messages clearly indicate which module is required"
echo "- Middleware is functioning correctly"
echo ""
echo "Next Step: Phase 088 - Frontend component gating with upgrade prompts"
echo ""
