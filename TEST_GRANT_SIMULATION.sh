#!/bin/bash

# TEST_GRANT_SIMULATION.sh
# Purpose: Test Grant simulation with DEMO_MODE enabled
# Strategy: Verify simulation logic produces correct energy numbers BEFORE debugging auth

set -e

BASE_URL="http://localhost:9095"
SITE_ID="site-002"

echo "=================================================="
echo "GRANT SIMULATION TEST - DEMO MODE"
echo "=================================================="
echo "Testing energy simulation logic with DEMO_MODE=true"
echo "Backend: $BASE_URL"
echo "Site: $SITE_ID"
echo ""

# Test 1: Check health endpoint (verify backend is running)
echo "TEST 1: Backend Health Check"
echo "---"
if curl -s "$BASE_URL/health" > /dev/null 2>&1; then
    echo "✓ Backend is running"
else
    echo "✗ Backend NOT running. Start with:"
    echo "   cd backend && source venv/bin/activate"
    echo "   DEMO_MODE=true python -m uvicorn app.main:app --reload --port 9095"
    exit 1
fi
echo ""

# Test 2: Get initial energy comparison (baseline before simulation)
echo "TEST 2: Get Initial Energy Comparison (Baseline)"
echo "---"
INITIAL_ENERGY=$(curl -s "$BASE_URL/api/energy/comparison?site_id=$SITE_ID&days=30")
echo "Response:"
echo "$INITIAL_ENERGY" | jq '.' 2>/dev/null || echo "$INITIAL_ENERGY"
echo ""

# Test 3: Check modules status
echo "TEST 3: Check Module Status"
echo "---"
MODULE_STATUS=$(curl -s "$BASE_URL/api/modules/status/$SITE_ID")
echo "Response:"
echo "$MODULE_STATUS" | jq '.' 2>/dev/null || echo "$MODULE_STATUS"
echo ""

# Test 4: Start lifecycle simulation for Grant scenario
echo "TEST 4: Start Grant Simulation"
echo "---"
echo "Scenario: grant_hvac_dali_ai_annual (365-day annual simulation)"
echo "Duration: ~4 minutes real time"
echo ""
START_RESPONSE=$(curl -s -X POST "$BASE_URL/api/lifecycle/start" \
  -H "Content-Type: application/json" \
  -d '{"scenario": "grant_hvac_dali_ai_annual"}')
echo "Response:"
echo "$START_RESPONSE" | jq '.' 2>/dev/null || echo "$START_RESPONSE"
echo ""

# Extract task_id if available
TASK_ID=$(echo "$START_RESPONSE" | jq -r '.task_id' 2>/dev/null)
if [ -z "$TASK_ID" ] || [ "$TASK_ID" = "null" ]; then
    echo "WARNING: Could not extract task_id from response"
    TASK_ID=""
fi
echo ""

# Test 5: Poll simulation status
if [ ! -z "$TASK_ID" ]; then
    echo "TEST 5: Monitor Simulation Progress"
    echo "---"
    echo "Polling /api/lifecycle/status/$TASK_ID every 5 seconds..."
    echo "Press Ctrl+C to stop monitoring"
    echo ""

    # Poll for up to 5 minutes (300 seconds)
    ELAPSED=0
    MAX_TIME=300

    while [ $ELAPSED -lt $MAX_TIME ]; do
        STATUS_RESPONSE=$(curl -s "$BASE_URL/api/lifecycle/status/$TASK_ID")

        # Response has running/paused/scenario fields directly (not nested in .simulation)
        RUNNING=$(echo "$STATUS_RESPONSE" | jq -r '.running // false' 2>/dev/null)
        SCENARIO=$(echo "$STATUS_RESPONSE" | jq -r '.scenario // "none"' 2>/dev/null)
        PROGRESS=$(echo "$STATUS_RESPONSE" | jq -r '.progress_pct // 0' 2>/dev/null)
        SIM_STATUS="running"
        if [ "$RUNNING" = "false" ]; then
            SIM_STATUS="not running"
        fi

        printf "\r[%d:%02d] Status: %-10s Progress: %3d%%" $((ELAPSED/60)) $((ELAPSED%60)) "$SIM_STATUS" "$PROGRESS"

        # If simulation is complete, break loop
        if [ "$SIM_STATUS" = "complete" ] || [ "$PROGRESS" = "100" ]; then
            echo ""
            echo "✓ Simulation complete!"
            break
        fi

        sleep 5
        ELAPSED=$((ELAPSED + 5))
    done
    echo ""
    echo ""
else
    echo "TEST 5: Skipped (no task_id available)"
    echo ""
fi

# Test 6: Get final energy comparison (after simulation)
echo "TEST 6: Get Final Energy Comparison (After Simulation)"
echo "---"
FINAL_ENERGY=$(curl -s "$BASE_URL/api/energy/comparison?site_id=$SITE_ID&days=30")
echo "Response:"
echo "$FINAL_ENERGY" | jq '.' 2>/dev/null || echo "$FINAL_ENERGY"
echo ""

# Test 7: Compare before/after
echo "TEST 7: Compare Initial vs Final Energy Numbers"
echo "---"
INITIAL_TOTAL=$(echo "$INITIAL_ENERGY" | jq -r '.baseline.actual.total_kwh // "N/A"' 2>/dev/null)
FINAL_TOTAL=$(echo "$FINAL_ENERGY" | jq -r '.baseline.actual.total_kwh // "N/A"' 2>/dev/null)

echo "Initial total energy: $INITIAL_TOTAL kWh"
echo "Final total energy:   $FINAL_TOTAL kWh"
echo ""

if [ "$INITIAL_TOTAL" != "N/A" ] && [ "$FINAL_TOTAL" != "N/A" ]; then
    if [ "$INITIAL_TOTAL" != "$FINAL_TOTAL" ]; then
        echo "✓ Numbers changed (simulation ran)"
        DELTA=$(echo "$FINAL_TOTAL - $INITIAL_TOTAL" | bc)
        echo "  Delta: $DELTA kWh"
    else
        echo "⚠ Numbers unchanged (data may not have updated)"
    fi
fi
echo ""

# Test 8: Check if numbers are inverted (negative)
echo "TEST 8: Verify Energy Numbers Are Positive (Not Inverted)"
echo "---"
ACTUAL_HVAC=$(echo "$FINAL_ENERGY" | jq -r '.baseline.actual.hvac_kwh // 0' 2>/dev/null)
ACTUAL_TOTAL=$(echo "$FINAL_ENERGY" | jq -r '.baseline.actual.total_kwh // 0' 2>/dev/null)

if (( $(echo "$ACTUAL_HVAC < 0" | bc -l) )); then
    echo "✗ HVAC energy is NEGATIVE: $ACTUAL_HVAC kWh (INVERTED!)"
else
    echo "✓ HVAC energy is positive: $ACTUAL_HVAC kWh"
fi

if (( $(echo "$ACTUAL_TOTAL < 0" | bc -l) )); then
    echo "✗ Total energy is NEGATIVE: $ACTUAL_TOTAL kWh (INVERTED!)"
else
    echo "✓ Total energy is positive: $ACTUAL_TOTAL kWh"
fi
echo ""

# Test 9: Check SimulationTimeIndicator status
echo "TEST 9: Get Lifecycle Status (for SimulationTimeIndicator)"
echo "---"
LIFECYCLE_STATUS=$(curl -s "$BASE_URL/api/lifecycle/status/$SITE_ID")
echo "Response:"
echo "$LIFECYCLE_STATUS" | jq '.' 2>/dev/null || echo "$LIFECYCLE_STATUS"
echo ""

echo "=================================================="
echo "TEST COMPLETE"
echo "=================================================="
echo ""
echo "SUMMARY:"
echo "--------"
echo "If all tests passed and energy numbers are POSITIVE and non-zero:"
echo "✓ Simulation logic is CORRECT"
echo "✓ Next: Debug auth middleware for POST /api/lifecycle/start"
echo ""
echo "If energy numbers are still NEGATIVE or ZERO:"
echo "✗ Simulation logic may have issues"
echo "✗ Check SimulatorService and energy generation"
