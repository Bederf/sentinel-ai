#!/bin/bash
# Module Toggle Diagnostic Test
# Tests the module activation/deactivation endpoints to identify why toggles fail

API_URL="http://localhost:9095"
SITE_ID="site-002"
SITE_NAME="Sandton Office"

echo "==============================================="
echo "Module Toggle Diagnostic Test"
echo "==============================================="
echo ""

# Test 1: Health check
echo "1. Testing backend health..."
HEALTH=$(curl -s -X GET "$API_URL/health" | grep -o '"status":"ok"')
if [ -z "$HEALTH" ]; then
    echo "❌ Backend not responding at $API_URL"
    exit 1
fi
echo "✅ Backend is running"
echo ""

# Test 2: Get available modules
echo "2. Getting available modules..."
AVAILABLE=$(curl -s -X GET "$API_URL/api/modules/available")
MODULE_COUNT=$(echo "$AVAILABLE" | grep -o '"module_type"' | wc -l)
echo "✅ Found $MODULE_COUNT available modules"
echo ""

# Test 3: Get active modules for site
echo "3. Getting active modules for $SITE_ID..."
ACTIVE=$(curl -s -X GET "$API_URL/api/modules/site/$SITE_ID/active")
ACTIVE_COUNT=$(echo "$ACTIVE" | grep -o '"module_type"' | wc -l)
echo "✅ Currently $ACTIVE_COUNT active modules"
echo "Active modules: $(echo "$ACTIVE" | grep -o '"module_type":"[^"]*"' | cut -d'"' -f4 | tr '\n' ',' | sed 's/,$//')"
echo ""

# Test 4: Test activation endpoint WITHOUT auth (should fail 401)
echo "4. Testing activate endpoint without auth..."
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$API_URL/api/modules/activate" \
  -H "Content-Type: application/json" \
  -d "{\"site_id\":\"$SITE_ID\",\"site_name\":\"$SITE_NAME\",\"module_type\":\"assets\",\"config\":null}")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | head -n-1)

if [ "$HTTP_CODE" = "401" ]; then
    echo "✅ Correctly returns 401 Unauthorized (no token)"
    echo "  Response: $(echo "$BODY" | grep -o '"detail":"[^"]*"' | cut -d'"' -f4)"
else
    echo "⚠️  Unexpected response code: $HTTP_CODE"
    echo "  Body: $BODY"
fi
echo ""

# Test 5: Check module dependency constraints
echo "5. Checking module dependencies..."
echo "  - SOLAR requires CONTROL to be active"
echo "  - LIGHTING requires CONTROL to be active"
echo ""
echo "  Attempting to activate SOLAR without CONTROL..."
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$API_URL/api/modules/activate" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer invalid-token" \
  -d "{\"site_id\":\"$SITE_ID\",\"site_name\":\"$SITE_NAME\",\"module_type\":\"solar\",\"config\":null}")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | head -n-1)
echo "  Response code: $HTTP_CODE"
if echo "$BODY" | grep -q "requires"; then
    echo "  ✅ Dependency validation working: $(echo "$BODY" | grep -o '"detail":"[^"]*"' | cut -d'"' -f4 | head -c 100)..."
fi
echo ""

# Test 6: Test endpoint with DEMO_MODE
echo "6. Checking if DEMO_MODE is enabled..."
DEMO_CHECK=$(curl -s -X POST "$API_URL/api/modules/activate" \
  -H "Content-Type: application/json" \
  -d "{\"site_id\":\"$SITE_ID\",\"site_name\":\"$SITE_NAME\",\"module_type\":\"assets\",\"config\":null}")

if echo "$DEMO_CHECK" | grep -q '"instance_id"'; then
    echo "✅ DEMO_MODE is ACTIVE - endpoints accept requests without auth"
    echo "  This means demo users should be able to toggle modules"
    echo ""
    echo "7. Testing asset module activation..."
    echo "  Request: POST /api/modules/activate with module_type=assets"
    echo "  Response: $(echo "$DEMO_CHECK" | grep -o '"module_type":"[^"]*"' | head -1)"

elif echo "$DEMO_CHECK" | grep -q "unauthorized"; then
    echo "⚠️  DEMO_MODE is DISABLED - endpoints require valid JWT tokens"
    echo "  Production users need valid authentication"
else
    echo "⚠️  Unexpected response:"
    echo "$DEMO_CHECK" | head -c 200
fi
echo ""

# Test 7: List module states
echo "8. Current module state for $SITE_ID:"
curl -s -X GET "$API_URL/api/modules/site/$SITE_ID/active" | \
  grep -o '{"instance_id":"[^"]*","site_id":"[^"]*","module_type":"[^"]*","status":"[^"]*"' | \
  sed 's/.*"module_type":"\([^"]*\)".*"status":"\([^"]*\)".*/   \1: \2/' | \
  head -20

echo ""
echo "==============================================="
echo "Diagnostic complete"
echo "==============================================="
