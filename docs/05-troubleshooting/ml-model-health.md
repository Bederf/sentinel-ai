---
title: "Troubleshooting ML Model Health"
type: "troubleshooting"
status: "published"
version: "1.0.0"
created: "2026-02-09"
updated: "2026-02-09"
author: "Sentinel Development Team"
tags: ["ml", "troubleshooting", "model-health", "performance"]
domain: "operations"
audience: "facilities-managers, operators, developers"
complexity: "intermediate"
estimated_read_time: 12
---

# Troubleshooting ML Model Health

## Quick Reference

| Symptom | Likely Cause | Solution |
|---------|--------------|----------|
| Model Health = Red (< 70%) | Models missing or stale | Train missing models or retrain stale ones |
| No predictions available | Equipment type not supported | Add equipment type config + train models |
| Predictions don't match reality | Model too old (stale) | Retrain model with latest data |
| Too many false anomaly alerts | Threshold too sensitive | Increase anomaly threshold or retrain |
| Training fails with "Unknown equipment type" | Config not added | Add equipment to SENSOR_CONFIGS files |
| Predictions are wildly off (R² < 0.40) | Poor training data quality | Verify sensor data, increase training samples |

---

## Understanding Model Health Dashboard

### Status Colors

**🟢 Green (90-100%):** Excellent
- All models trained and fresh (< 30 days old)
- All R² scores > 0.70
- System ready for production

**🟡 Yellow (70-89%):** Warning
- Some models > 30 days old (stale)
- Some R² scores 0.60-0.70 (acceptable but declining)
- Retraining recommended but not urgent

**🔴 Red (< 70%):** Critical
- Multiple models missing or never trained
- Multiple R² scores < 0.60
- System not ready for production decisions

### Current Status (Feb 9, 2026)

```
Model Health: 95% ✅
├─ Fresh Models: 14/14 (100%)
├─ Stale Models: 0/14
├─ Missing Models: 0/14
├─ Underperforming Models: 0/14
└─ Average R² Score: 0.667
```

---

## Scenario 1: Low Model Health After Startup

### Symptom

```
Dashboard shows: Model Health = 36%
Error message: "9 models missing"
Predictions unavailable for VAV, PUMP, some FCU/UPS
```

### Diagnosis

**Before Feb 9, 2026:**
- Only 3 autoencoder models trained (Chiller, AHU, Generator)
- Missing: LSTM models for all types
- Missing: Autoencoder models for FCU, UPS, VAV, PUMP
- Result: 5/14 models available = 36% health

**After Feb 9, 2026:**
- All 14 models trained (7 LSTM + 7 Autoencoder)
- Result: 14/14 models = 95%+ health

### Solution

**If still seeing 36% (old state):**

1. Check if models were trained:
```bash
curl http://localhost:9095/api/ml/models | jq '.models | length'
# Should return 14
```

2. If < 14 models, train missing ones:
```bash
# Train all equipment types (LSTM + Autoencoder)
curl -X POST http://localhost:9095/api/ml/train/all \
  -H "Content-Type: application/json" \
  -d '{"epochs": 50, "use_demo_data": true}'
```

3. Wait for training to complete (10-15 minutes for all 14 models)

4. Verify health improved:
```bash
curl http://localhost:9095/api/ml-retraining/performance/health
# Should show ~95% health now
```

---

## Scenario 2: Model Becomes Stale (> 30 Days Old)

### Symptom

```
Model Health dropped from 95% to 89%
Dashboard alert: "2 models require retraining"
Specific models flagged:
  - lstm_chiller_20260110_101530 (age: 31 days) 🚨
  - autoencoder_pump_20260110_120000 (age: 31 days) 🚨
```

### Diagnosis

Models are automatically marked "stale" when:
- Age exceeds 30 days (configuration threshold)
- OR R² score drops below 0.60 (performance threshold)

In this case: **Age-based staleness** (normal after 30 days)

### Solution

**Automatic Retraining (Recommended):**

```bash
# System automatically retrains stale models daily
# Check status:
curl http://localhost:9095/api/ml-retraining/status

# Response shows:
{
  "total_models_checked": 14,
  "needs_retrain": 2,
  "models": [
    {
      "model_type": "lstm",
      "equipment_type": "chiller",
      "status": "stale",
      "age_days": 31,
      "needs_retrain": true,
      "reason": "Model age 31d exceeds 30d threshold"
    }
  ]
}
```

**Manual Retraining (If needed immediately):**

```bash
# Retrain stale chiller LSTM
curl -X POST http://localhost:9095/api/ml-retraining/trigger \
  -H "Content-Type: application/json" \
  -d '{"model_type": "lstm", "equipment_type": "chiller", "reason": "manual"}'

# Response:
{
  "triggered": true,
  "model_type": "lstm",
  "equipment_type": "chiller",
  "new_model_id": "lstm_chiller_20260209_150000"
}
```

### Monitoring Retraining

```bash
# Check retraining history
curl http://localhost:9095/api/ml-retraining/history

# Once completed, verify improvement:
curl http://localhost:9095/api/ml/models?equipment_type=chiller | jq '.models[0].registered_at'
# Should show today's date
```

---

## Scenario 3: Predictions Are Inaccurate

### Symptom

**24 hours ago:**
- LSTM predicted: Chiller supply temp = 7.8°C
- Confidence: 85%

**Today actual:**
- Chiller supply temp = 9.2°C (way off!)
- Difference: +1.4°C (15% error - bad)

### Root Cause Analysis

**Step 1: Check model age**

```bash
curl http://localhost:9095/api/ml/models?equipment_type=chiller | jq '.models[0]'

# Check: age_days > 30 days?
```

**Step 2: Check model performance**

```bash
curl http://localhost:9095/api/ml-retraining/performance/health

# Check: R² < 0.60? (underperforming)
# Check: accuracy < 80%?
```

**Step 3: Check if equipment configuration changed**

```
Did any of these happen recently?
- New setpoint programmed?
- Control logic updated?
- Sensor replaced?
- Equipment serviced/cleaned?
```

### Solutions

**If Model is Stale (> 30 days):**
```bash
# Retrain immediately
curl -X POST http://localhost:9095/api/ml-retraining/trigger \
  -d '{"model_type": "lstm", "equipment_type": "chiller"}'

# Then wait 5 minutes and test predictions again
```

**If Model is Underperforming (R² < 0.60):**
```bash
# Check what happened
curl http://localhost:9095/api/ml-retraining/performance \
  -d '{"building_code": "site-002", "days_back": 7}'

# Possible issues:
# 1. Sensor malfunction - verify sensor values are reasonable
# 2. Equipment configuration changed - retrain model
# 3. Insufficient training data - add more sensor history

# Rebuild model with more aggressive settings:
curl -X POST http://localhost:9095/api/ml/train/lstm/chiller \
  -d '{"epochs": 100, "use_demo_data": true}'  # More epochs
```

**If Equipment Configuration Just Changed:**

```
Examples that require retraining:
- New temperature setpoint programmed
- Control logic updated
- Sensor replaced
- Valve/damper replaced
- Equipment cleaned/serviced

Action: Retrain model after 24-48 hours of new data
curl -X POST http://localhost:9095/api/ml-retraining/trigger \
  -d '{"model_type": "lstm", "equipment_type": "chiller"}'
```

### Verification

After fixes, verify predictions are accurate:

```bash
# Get new prediction
curl "http://localhost:9095/api/ml/predictions/lstm/S002-CHILLER-B1-001?equipment_type=chiller"

# Compare to actual readings:
# 24h forecast: X.X°C
# Actual today: Y.Y°C
# Error: should be < ±0.5°C for good model
```

---

## Scenario 4: Too Many False Anomaly Alerts

### Symptom

```
2 PM: Anomaly alert - "VAV-L2-E vibration elevated"
But equipment operating normally, no issues found

10 times last week, all false alarms
Technicians ignoring alerts (alert fatigue)
```

### Root Cause Analysis

**Step 1: Check anomaly score threshold**

```bash
curl http://localhost:9095/api/ml/models?equipment_type=vav | jq '.models[] | select(.model_type=="autoencoder")'

# Look for: "threshold": 1.081577
# This is the cutoff for "anomaly detected"
```

**Step 2: Check recent anomaly scores**

```bash
curl "http://localhost:9095/api/ml/anomalies/history/S002-VAV-L2-E?equipment_type=vav&days=7"

# If scores hovering around 0.80-0.85 (just below threshold):
# - Model thinks nearly everything is suspicious
# - Too sensitive
```

### Solution: Adjust Threshold

**Option 1: Increase Anomaly Threshold (Recommended)**

Edit `backend/ml/autoencoder/model.py`:

```python
# Find this line (~line 50):
self.threshold_percentile = 90  # Current: 90th percentile

# Change to (more conservative):
self.threshold_percentile = 95  # Only flag top 5% as anomalies
```

Then retrain:
```bash
curl -X POST http://localhost:9095/api/ml/train/autoencoder/vav \
  -d '{"epochs": 50}'
```

**Option 2: Retrain Model with Better Data**

If the model was trained with noisy data:

```bash
# Retrain autoencoder with current equipment state
curl -X POST http://localhost:9095/api/ml/train/autoencoder/vav \
  -d '{"epochs": 100, "use_demo_data": false}'  # Use real data if available
```

**Option 3: Investigate Actual Issue**

Maybe the equipment IS degrading:

```bash
# Get anomaly history
curl "http://localhost:9095/api/ml/anomalies/history/S002-VAV-L2-E?days=30"

# If scores trending UP over time:
# Not a false alarm, equipment actually degrading
# Schedule maintenance before it fails
```

### Verification

After adjustment, verify alert rate normalized:

```bash
# Monitor for 7 days, count alerts
# Should drop from 10/week to 1-2/week

# Check alert quality
curl "http://localhost:9095/api/ml/anomalies/alerts" | jq '.alerts | length'
# Should be small number (1-3), not 10+
```

---

## Scenario 5: Equipment Type Not Supported

### Symptom

```
Error when trying to get predictions:
ValueError: Unknown equipment type: smart_meter
Available: ['chiller', 'ahu', 'generator', 'fcu', 'vav', 'ups', 'pump']

Model Health shows: Red (missing model)
```

### Solution

See [ML Equipment Support](../02-architecture/ml-equipment-support.md#how-to-add-support-for-new-equipment-type) for complete guide.

**Quick Steps:**

1. Add equipment config to LSTM trainer:
```python
# File: backend/ml/lstm/data_prep.py
# In EquipmentDataLoader.SENSOR_CONFIGS:

"smart_meter": {
    "features": ["voltage_a", "voltage_b", "voltage_c", "power_factor"],
    "target": "power_factor",
    "description": "Smart meter power quality monitoring"
}
```

2. Add equipment config to Autoencoder trainer:
```python
# File: backend/ml/autoencoder/data_prep.py
# In AUTOENCODER_SENSOR_CONFIGS:

"smart_meter": {
    "features": ["voltage_a", "voltage_b", "voltage_c", "power_factor"],
    "description": "Smart meter anomaly detection"
}
```

3. Train models:
```bash
# Train LSTM
curl -X POST http://localhost:9095/api/ml/train/lstm/smart_meter \
  -d '{"epochs": 50}'

# Train Autoencoder
curl -X POST http://localhost:9095/api/ml/train/autoencoder/smart_meter \
  -d '{"epochs": 50}'
```

4. Verify:
```bash
curl http://localhost:9095/api/ml/models?equipment_type=smart_meter
# Should return 2 active models (LSTM + Autoencoder)
```

---

## Scenario 6: Model Health Stuck at Low Value

### Symptom

```
Model Health: 71% (stuck for 3 days)
Dashboard shows: 2 models stale, 2 models underperforming
Expected: Auto-retraining should happen daily
```

### Diagnosis

**Possible causes:**

1. **Retraining scheduler not running**
   ```bash
   # Check if background scheduler is active
   curl http://localhost:9095/api/ml/health | jq '.scheduler_status'
   # Should show: "running"
   ```

2. **Training jobs queued but not processing**
   ```bash
   # Check job queue
   curl http://localhost:9095/api/ml-retraining/history | jq '.history[-5:]'
   # Look for recent training attempts
   ```

3. **Training failing silently**
   ```bash
   # Check for errors in logs
   tail -100 /opt/bms-intelligence/backend/logs/ml-training.log | grep ERROR
   ```

### Solution

**Option 1: Trigger Manual Retraining**

```bash
# Retrain all stale models
curl http://localhost:9095/api/ml-retraining/status | jq '.models[] | select(.needs_retrain==true)' | \
  while read model; do
    eq_type=$(echo $model | jq -r '.equipment_type')
    model_type=$(echo $model | jq -r '.model_type')
    curl -X POST http://localhost:9095/api/ml-retraining/trigger \
      -d "{\"model_type\": \"$model_type\", \"equipment_type\": \"$eq_type\"}"
  done
```

**Option 2: Restart ML Service**

```bash
# Restart backend service to kick off scheduler
systemctl restart bms-ml-service

# Verify scheduler running:
sleep 10
curl http://localhost:9095/api/ml/health
```

**Option 3: Verify Service Logs**

```bash
# Check for configuration errors
docker logs bms-intelligence_ml 2>&1 | grep -i error | head -20

# Check retraining history
curl http://localhost:9095/api/ml-retraining/history | jq '.history | sort_by(.triggered_at) | reverse | .[0:5]'
# Should show recent training attempts
```

### Recovery

After fix, model health should improve within 24 hours:

```bash
# Monitor over next day
for i in {1..24}; do
  curl http://localhost:9095/api/ml-retraining/performance/health | \
    jq '.summary.health_pct'
  echo "Waiting 1 hour..."
  sleep 3600
done
```

---

## Common Error Messages

### Error: "Model age 45d exceeds 30d threshold"

**Meaning:** Model is 45 days old, retraining needed

**Fix:**
```bash
curl -X POST http://localhost:9095/api/ml-retraining/trigger \
  -d '{"equipment_type": "chiller", "model_type": "lstm", "reason": "manual"}'
```

---

### Error: "R² score 0.52 is below 0.60 threshold"

**Meaning:** Model prediction accuracy has degraded

**Fix:**
```bash
# Option 1: Retrain (often fixes it)
curl -X POST http://localhost:9095/api/ml-retraining/trigger \
  -d '{"equipment_type": "chiller", "model_type": "lstm"}'

# Option 2: Check equipment/sensors for issues
curl http://localhost:9095/api/devices/S002-CHILLER-B1-001 | jq '.health_score'
```

---

### Error: "Unknown equipment type: new_type"

**Meaning:** Equipment type not configured in training system

**Fix:** See [Adding New Equipment Type](../02-architecture/ml-equipment-support.md)

---

### Error: "Training timed out after 3600 seconds"

**Meaning:** Model training took too long (> 1 hour)

**Causes & Fixes:**

| Cause | Fix |
|-------|-----|
| Too many features (> 10) | Reduce to 5-6 key sensors |
| Too many epochs (> 100) | Reduce to 50-75 epochs |
| Large training dataset | Reduce to 5,000 samples |
| Hardware overloaded | Retry during off-peak hours |

```bash
# Retry with reduced settings
curl -X POST http://localhost:9095/api/ml/train/lstm/chiller \
  -d '{"epochs": 30, "use_demo_data": true}'
```

---

## Performance Expectations

### By Equipment Type

| Equipment | Typical R² | Typical Precision | Status |
|-----------|-----------|-----------------|--------|
| **Chiller** | 0.84 | 76.9% | Excellent |
| **AHU** | 0.69 | 76.9% | Good |
| **Generator** | 0.61 | 74.1% | Acceptable |
| **FCU** | 0.75 | 71.4% | Good |
| **VAV** | 0.42 | 76.9% | Fair (needs investigation) |
| **UPS** | 0.48 | 69.0% | Fair (needs investigation) |
| **Pump** | 0.73 | 76.9% | Good |

**Note:** VAV and UPS show lower R² because they have more operational variability

---

## Monitoring Best Practices

### Daily Health Check

```bash
# Run daily at 3 AM to check model health
curl http://localhost:9095/api/ml-retraining/performance/health | jq '{
  health_pct: .summary.health_pct,
  fresh: .summary.fresh,
  stale: .summary.stale,
  missing: .summary.missing
}'

# Expected:
# {
#   "health_pct": 95,
#   "fresh": 14,
#   "stale": 0,
#   "missing": 0
# }
```

### Weekly Performance Report

```bash
# Run weekly to check prediction accuracy
curl http://localhost:9095/api/ml-retraining/performance?days_back=7 | jq '{
  accuracy: .metrics.accuracy,
  precision: .metrics.precision,
  recall: .metrics.recall,
  f1_score: .metrics.f1_score
}'

# Expected: All metrics > 0.80
```

### Monthly Retraining Audit

```bash
# Check which models were retrained last month
curl http://localhost:9095/api/ml-retraining/history | \
  jq '.history[] | select(.triggered_at > "2026-01-09") | {equipment_type, triggered_at, success}'

# All should show success: true
```

---

## Getting Help

If model health won't improve:

1. **Collect diagnostic data:**
```bash
# Save these to report:
curl http://localhost:9095/api/ml/health > ml_health.json
curl http://localhost:9095/api/ml-retraining/performance/health > ml_performance.json
curl http://localhost:9095/api/ml-retraining/history > retraining_history.json
```

2. **Check logs:**
```bash
tail -100 /opt/bms-intelligence/backend/logs/ml-training.log
tail -100 /opt/bms-intelligence/backend/logs/api.log | grep ml
```

3. **Report issue with:**
   - Current model health percentage
   - Which models are stale/underperforming
   - Recent changes to equipment or configuration
   - Diagnostic data files from step 1

---

## Summary

**Model Health Management:**

| Status | Action |
|--------|--------|
| 🟢 95%+ | Excellent - no action needed |
| 🟡 70-94% | Warning - schedule retraining |
| 🔴 <70% | Critical - immediate retraining needed |

**Key Commands:**

```bash
# Check health
curl http://localhost:9095/api/ml-retraining/performance/health

# Trigger retraining
curl -X POST http://localhost:9095/api/ml-retraining/trigger \
  -d '{"model_type": "lstm", "equipment_type": "chiller"}'

# Train all models
curl -X POST http://localhost:9095/api/ml/train/all \
  -d '{"epochs": 50}'
```

For detailed information, see [ML Equipment Support](../02-architecture/ml-equipment-support.md) and [ML Predictions API](../03-api-reference/ml-predictions-api.md).
