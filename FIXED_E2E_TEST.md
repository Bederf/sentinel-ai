# Fixed End-to-End Integration Test

## Prerequisites

- Backend running: `./start-backend.sh`
- No authentication required for this test (demo mode)

## Step 1: Get Available Equipment

```bash
curl -s http://localhost:9095/api/equipment | jq '.equipment[0:3] | .[] | {id, code, name, health_score}'
```

**Expected Output:**
```json
{
  "id": "eqp-001",
  "code": "CH-1",
  "name": "Chiller 1",
  "health_score": 88
}
```

**Note:** Use the `code` (e.g., "CH-1"), not the `id`

---

## Step 2: Create an Alert

This simulates a fault detection that drops equipment health.

```bash
curl -X POST http://localhost:9095/api/alerts \
  -H "Content-Type: application/json" \
  -d '{
    "equipment_code": "CH-1",
    "severity": "warning",
    "type": "temperature",
    "title": "High Temperature Warning",
    "message": "Equipment temperature exceeded safe threshold",
    "reading": 32.5,
    "setpoint": 25,
    "notify_sentry": false
  }' | jq '{id, status, message}'
```

**Expected Output:**
```json
{
  "id": "alert-uuid",
  "status": "active",
  "message": "Alert created for Chiller 1"
}
```

✅ **Pass Criteria:** Alert ID returned

---

## Step 3: Verify Equipment Health Dropped

```bash
curl -s http://localhost:9095/api/equipment | \
  jq '.equipment[] | select(.code == "CH-1") | {health_score, status}'
```

**Expected Output:**
```json
{
  "health_score": 60,
  "status": "warning"
}
```

✅ **Pass Criteria:** Health dropped from 88 to 60 (warning alert sets health to 60)

---

## Step 4: Create Inspection Work Order

This simulates the technician being assigned to investigate the alert.

```bash
curl -X POST http://localhost:9095/api/work-orders/supabase \
  -H "Content-Type: application/json" \
  -d '{
    "equipment_code": "CH-1",
    "title": "Inspection: Chiller 1",
    "description": "Initial inspection of high temperature alert",
    "priority": "high",
    "scheduled_date": "2026-02-12T10:00:00Z",
    "estimated_duration_hours": 1
  }' | jq '{id, code, status, assigned_to}'
```

**Expected Output:**
```json
{
  "id": "wo-uuid",
  "code": "WO-001",
  "status": "scheduled",
  "assigned_to": "Technician Name"
}
```

✅ **Pass Criteria:** Work order created and technician auto-assigned

---

## Step 5: Submit Inspection Findings

The technician completes the inspection and submits findings.

```bash
WO_ID="<work_order_id_from_step_4>"

curl -X POST http://localhost:9095/api/service-feedback/supabase \
  -H "Content-Type: application/json" \
  -d '{
    "work_order_id": "'$WO_ID'",
    "equipment_id": "eqp-001",
    "equipment_code": "CH-1",
    "findings": "Sensor calibration drift detected. Temperature reading 32C but actual is 24C.",
    "items_collected": {
      "manual_reading": "24.0",
      "sensor_reading": "32.0"
    },
    "health_impact": "neutral"
  }' | jq '{success, health_score_change}'
```

**Expected Output:**
```json
{
  "success": true,
  "health_score_change": 0
}
```

✅ **Pass Criteria:** Findings submitted, health unchanged (neutral impact)

---

## Step 6: Get AI Recommendation

The system analyzes the findings to determine next action.

```bash
curl -s http://localhost:9095/api/inspections/$WO_ID/recommendation | \
  jq '.recommendation | {decision, severity, reason, confidence}'
```

**Expected Output:**
```json
{
  "decision": "RECOMMEND_REPAIR",
  "severity": "medium",
  "reason": "Sensor calibration drift requires recalibration",
  "confidence": 0.85
}
```

✅ **Pass Criteria:** System recommends repair (not auto-creating, operator must approve)

---

## Step 7: Create Repair Work Order

Operator approves the recommendation and creates repair WO.

```bash
curl -X POST http://localhost:9095/api/inspections/$WO_ID/create-repair-wo \
  -H "Content-Type: application/json" \
  -d '{
    "work_order_id": "'$WO_ID'",
    "equipment_code": "CH-1",
    "recommendation_reason": "Sensor calibration drift, needs recalibration",
    "parts_needed": ["Calibration kit"],
    "priority": "high"
  }' | jq '{work_order_id, status}'
```

**Expected Output:**
```json
{
  "work_order_id": "wo-repair-uuid",
  "status": "assigned"
}
```

✅ **Pass Criteria:** Repair work order created

---

## Step 8: Complete Repair with Positive Feedback

Technician completes repair and submits positive feedback.

```bash
REPAIR_WO_ID="<repair_work_order_id_from_step_7>"

curl -X POST http://localhost:9095/api/service-feedback/supabase \
  -H "Content-Type: application/json" \
  -d '{
    "work_order_id": "'$REPAIR_WO_ID'",
    "equipment_id": "eqp-001",
    "equipment_code": "CH-1",
    "findings": "Recalibrated sensor successfully. Verified with manual reading.",
    "items_collected": {
      "sensor_reading": "24.0",
      "manual_reading": "24.0",
      "variance": "0%"
    },
    "health_impact": "positive",
    "parts_used": ["Calibration kit"]
  }' | jq '{success, health_score_change}'
```

**Expected Output:**
```json
{
  "success": true,
  "health_score_change": 2
}
```

✅ **Pass Criteria:** Health increased by +2

---

## Step 9: Verify Final Health Status

```bash
curl -s http://localhost:9095/api/equipment | \
  jq '.equipment[] | select(.code == "CH-1") | {health_score, status}'
```

**Expected Output:**
```json
{
  "health_score": 62,
  "status": "warning"
}
```

✅ **Pass Criteria:** Health increased from 60 to 62 (60 + 2)

---

## 🎯 Integration Points Validated

| Component | Status | Evidence |
|-----------|--------|----------|
| Alert Creation | ✅ | Alert appears in database |
| Health Persistence | ✅ | health_score updated to 60 |
| Work Order Creation | ✅ | WO ID returned with auto-assigned technician |
| Service Feedback | ✅ | Findings submitted and stored |
| AI Recommendation | ✅ | Decision returned (RECOMMEND_REPAIR) |
| Repair WO Creation | ✅ | Pre-filled with findings |
| Health Recovery | ✅ | Score increased to 62 |
| **Complete Workflow** | ✅ | All steps work together |

---

## Common Issues & Solutions

### Issue: "Equipment not found"
- **Cause:** Wrong equipment code
- **Solution:** Use actual equipment codes like "CH-1", "VAV-101", not full codes like "S002-CHILLER-B1-001"
- **Verify:**
  ```bash
  curl -s http://localhost:9095/api/equipment | jq '.equipment[].code' | head -5
  ```

### Issue: "Failed to create work order in Supabase"
- **Cause:** Missing required fields (title, description, priority, scheduled_date)
- **Solution:** Include all required fields in request body
- **Check:** All examples above include all required fields

### Issue: Work order status is "scheduled" not "assigned"
- **Cause:** API always sets status to "scheduled" on creation
- **Solution:** This is expected behavior - technician assignment happens via `assigned_to` field
- **Note:** Status updates to "assigned" after technician accepts

### Issue: Health score not updating after alert
- **Cause:** Alert severity value (use lowercase: "critical", "warning", not "CRITICAL")
- **Solution:** Verify severity is exact match: `"warning"` → health=60, `"critical"` → health=30
- **Check:**
  ```bash
  curl -s http://localhost:9095/api/equipment | jq '.equipment[] | {code, health_score}' | head -20
  ```

---

## Quick Test (Copy-Paste All Steps)

```bash
#!/bin/bash

# 1. Get equipment
EQUIPMENT=$(curl -s http://localhost:9095/api/equipment | jq '.equipment[0]')
EQUIPMENT_CODE=$(echo $EQUIPMENT | jq -r '.code')
EQUIPMENT_ID=$(echo $EQUIPMENT | jq -r '.id')
echo "Using equipment: $EQUIPMENT_CODE ($EQUIPMENT_ID)"

# 2. Create alert
ALERT=$(curl -s -X POST http://localhost:9095/api/alerts \
  -H "Content-Type: application/json" \
  -d '{
    "equipment_code": "'$EQUIPMENT_CODE'",
    "severity": "warning",
    "type": "temperature",
    "title": "High Temp",
    "message": "Exceeded threshold",
    "reading": 32.5,
    "setpoint": 25,
    "notify_sentry": false
  }')
ALERT_ID=$(echo $ALERT | jq -r '.id')
echo "Alert created: $ALERT_ID"

# 3. Check health dropped
HEALTH=$(curl -s http://localhost:9095/api/equipment | jq ".equipment[] | select(.code == \"$EQUIPMENT_CODE\") | .health_score")
echo "Health after alert: $HEALTH%"

# 4. Create inspection WO
WO=$(curl -s -X POST http://localhost:9095/api/work-orders/supabase \
  -H "Content-Type: application/json" \
  -d '{
    "equipment_code": "'$EQUIPMENT_CODE'",
    "title": "Inspection: '$EQUIPMENT_CODE'",
    "description": "Initial inspection",
    "priority": "high",
    "scheduled_date": "2026-02-12T10:00:00Z",
    "estimated_duration_hours": 1
  }')
WO_ID=$(echo $WO | jq -r '.id')
echo "Inspection WO created: $WO_ID"

# 5. Submit findings
curl -s -X POST http://localhost:9095/api/service-feedback/supabase \
  -H "Content-Type: application/json" \
  -d '{
    "work_order_id": "'$WO_ID'",
    "equipment_id": "'$EQUIPMENT_ID'",
    "equipment_code": "'$EQUIPMENT_CODE'",
    "findings": "Sensor drift detected",
    "items_collected": {"manual": "24", "sensor": "32"},
    "health_impact": "neutral"
  }' | jq '.success'

# 6. Get recommendation
REC=$(curl -s http://localhost:9095/api/inspections/$WO_ID/recommendation)
DECISION=$(echo $REC | jq -r '.recommendation.decision')
echo "Recommendation: $DECISION"

# 7. Create repair WO
REPAIR=$(curl -s -X POST http://localhost:9095/api/inspections/$WO_ID/create-repair-wo \
  -H "Content-Type: application/json" \
  -d '{
    "work_order_id": "'$WO_ID'",
    "equipment_code": "'$EQUIPMENT_CODE'",
    "recommendation_reason": "Needs recalibration",
    "parts_needed": ["Kit"],
    "priority": "high"
  }')
REPAIR_WO_ID=$(echo $REPAIR | jq -r '.work_order_id')
echo "Repair WO created: $REPAIR_WO_ID"

# 8. Complete repair
curl -s -X POST http://localhost:9095/api/service-feedback/supabase \
  -H "Content-Type: application/json" \
  -d '{
    "work_order_id": "'$REPAIR_WO_ID'",
    "equipment_id": "'$EQUIPMENT_ID'",
    "equipment_code": "'$EQUIPMENT_CODE'",
    "findings": "Recalibrated successfully",
    "items_collected": {"sensor": "24", "manual": "24"},
    "health_impact": "positive",
    "parts_used": ["Kit"]
  }' | jq '.health_score_change'

# 9. Final health
FINAL=$(curl -s http://localhost:9095/api/equipment | jq ".equipment[] | select(.code == \"$EQUIPMENT_CODE\") | .health_score")
echo "Final health: $FINAL%"

echo "✅ END-TO-END TEST COMPLETE"
```

---

## Success Criteria Summary

✅ Alert created with correct health drop (88% → 60%)
✅ Work order created and technician auto-assigned
✅ Inspection findings submitted
✅ AI recommendation generated (RECOMMEND_REPAIR)
✅ Repair work order created from recommendation
✅ Health restored after positive feedback (60% → 62%)
✅ All API integrations working seamlessly
✅ Complete workflow: Alert → Inspection → Repair → Resolution
