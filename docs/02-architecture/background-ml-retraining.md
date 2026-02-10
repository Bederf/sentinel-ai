---
title: "Background ML Model Retraining"
type: "architecture"
status: "published"
version: "1.0.0"
created: "2026-02-09"
updated: "2026-02-09"
author: "Sentinel Development Team"
tags: ["ml", "retraining", "background-jobs", "scheduler", "automation"]
domain: "operations"
audience: "platform-engineers, devops, ml-engineers"
complexity: "advanced"
estimated_read_time: 20
---

# Background ML Model Retraining Architecture

## Overview

SENTINEL uses **background automated retraining** to keep ML models fresh in production without blocking API requests or other critical operations. This document explains how the system continuously monitors model staleness, prioritizes retraining, and executes training jobs in the background.

### The Problem It Solves

**Question:** "We trained all 14 models (7 equipment types × 2 model types). If training takes 2+ hours, how doesn't this block live buildings?"

**Answer:** The system runs training in a **background thread pool** using APScheduler. Only ONE model is retrained per 24-hour cycle, allowing all 14 models to refresh within 2 weeks while keeping the API responsive.

**Key Guarantee:** API requests, device control, predictions, and optimization continue normally while retraining happens in the background.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                      SENTINEL Backend (FastAPI)                 │
├─────────────────────────────────────────────────────────────────┤
│  API Requests → Device Control → Optimization (all responsive)  │
│                                                                  │
│  ┌──────────────────── Background Thread Pool ────────────────┐ │
│  │                                                              │ │
│  │  ┌─────────────────────────────────────────────────────┐   │ │
│  │  │        APScheduler (Background Jobs)               │   │ │
│  │  │                                                      │   │ │
│  │  │  • Demo audit data (every 60s)                    │   │ │
│  │  │  • AI optimization (every 15min)                  │   │ │
│  │  │  • Prediction generation (every 5min)             │   │ │
│  │  │  • Recommendation generation (every 10min)        │   │ │
│  │  │  • 🆕 ML model retraining (every 24h)            │   │ │
│  │  │                                                      │   │ │
│  │  └─────────────────────────────────────────────────────┘   │ │
│  │                          ↓                                   │ │
│  │  ┌─────────────────────────────────────────────────────┐   │ │
│  │  │  Background ML Retraining Worker                    │   │ │
│  │  │  (_run_ml_retraining)                               │   │ │
│  │  │                                                      │   │ │
│  │  │  1. Check all 14 models for staleness             │   │ │
│  │  │  2. Find stale/underperforming models             │   │ │
│  │  │  3. Retrain ONE highest-priority model            │   │ │
│  │  │  4. Log results                                    │   │ │
│  │  │                                                      │   │ │
│  │  └─────────────────────────────────────────────────────┘   │ │
│  │                          ↓                                   │ │
│  │  ┌─────────────────────────────────────────────────────┐   │ │
│  │  │  Model Registry (stores trained models)             │   │ │
│  │  │  • Model weights (H5 files)                        │   │ │
│  │  │  • Scalers (JOBLIB files)                          │   │ │
│  │  │  • Metadata (registration date, R², age)           │   │ │
│  │  │                                                      │   │ │
│  │  └─────────────────────────────────────────────────────┘   │ │
│  │                                                              │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Components

### 1. BackgroundSchedulerService

**File:** `backend/app/services/background_scheduler.py`

Manages all background jobs using APScheduler's BackgroundScheduler.

#### Key Methods

```python
class BackgroundSchedulerService:
    def start(self):
        """Start the background scheduler (call on app startup)"""
    
    def stop(self):
        """Stop the background scheduler (call on app shutdown)"""
    
    def add_ml_retraining_job(self, interval_seconds: int = 86400):
        """
        Add ML model retraining job (runs daily by default).
        
        Args:
            interval_seconds: How often to check for stale models
                             Default: 86400 seconds (24 hours)
        """
```

#### Configuration

```python
# In main.py or startup module
from app.services.background_scheduler import scheduler_service

# Start scheduler on app startup
scheduler_service.start()

# Enable background ML retraining (daily staleness checks)
scheduler_service.add_ml_retraining_job(interval_seconds=86400)

# Disable on app shutdown
scheduler_service.stop()
```

### 2. RetrainingScheduler

**File:** `backend/ml/training/retraining_scheduler.py`

Detects stale/underperforming models and triggers retraining.

#### Key Methods

```python
class RetrainingScheduler:
    def check_all_models(self) -> List[Dict]:
        """
        Check freshness and performance of all 14 active models.
        
        Returns list with:
        - model_type: 'lstm' or 'autoencoder'
        - equipment_type: 'chiller', 'ahu', 'fcu', 'vav', 'generator', 'ups', 'pump'
        - status: 'fresh', 'stale', 'underperforming', 'missing'
        - age_days: How old the model is
        - r2_score: Model's R² performance metric
        - needs_retrain: Boolean flag
        - reason: Explanation of status
        """
    
    def trigger_retraining(
        self,
        model_type: str,
        equipment_type: str,
        reason: str = "manual"
    ) -> RetrainResult:
        """
        Trigger retraining for a specific model.
        
        Args:
            model_type: 'lstm' or 'autoencoder'
            equipment_type: Equipment type (chiller, ahu, etc.)
            reason: Why retraining was triggered
        
        Returns:
            RetrainResult with success status and new model ID
        """
    
    def auto_retrain_stale(self) -> List[RetrainResult]:
        """
        Check all models and retrain the first stale one found.
        Called by background scheduler daily.
        Only retrains ONE model per cycle to avoid overload.
        """
```

#### Staleness Thresholds

| Condition | Threshold | Action |
|-----------|-----------|--------|
| **Age** | > 30 days | Mark as stale, retrain |
| **R² Score** | < 0.65 | Mark as underperforming, retrain |
| **Missing** | No active model | Priority HIGH, retrain first |

---

## Daily Retraining Cycle

### How It Works

**Every 24 hours:**

```
06:00 AM (or whenever cycle triggers):
  └─ Check all 14 models
     ├─ Chiller (LSTM): 25 days old, R²=0.84 → FRESH ✅
     ├─ Chiller (Autoencoder): 28 days old, R²=0.72 → FRESH ✅
     ├─ AHU (LSTM): 35 days old, R²=0.69 → STALE 🚨
     ├─ AHU (Autoencoder): 5 days old, R²=0.73 → FRESH ✅
     ├─ FCU (LSTM): 22 days old, R²=0.75 → FRESH ✅
     ├─ FCU (Autoencoder): 40 days old, R²=0.58 → STALE 🚨
     ├─ VAV (LSTM): 15 days old, R²=0.42 → FRESH (but poor) ⚠️
     ├─ VAV (Autoencoder): 12 days old, R²=0.39 → FRESH (but poor) ⚠️
     ├─ Generator (LSTM): 18 days old, R²=0.61 → FRESH ✅
     ├─ Generator (Autoencoder): 19 days old, R²=0.67 → FRESH ✅
     ├─ UPS (LSTM): 8 days old, R²=0.48 → FRESH (but poor) ⚠️
     ├─ UPS (Autoencoder): 9 days old, R²=0.59 → FRESH (but poor) ⚠️
     ├─ Pump (LSTM): 31 days old, R²=0.73 → STALE 🚨
     └─ Pump (Autoencoder): 6 days old, R²=0.68 → FRESH ✅
  
  Stale/Underperforming Models Found: 3
    1. AHU (LSTM) - age 35d
    2. FCU (Autoencoder) - age 40d, R²=0.58
    3. Pump (LSTM) - age 31d
  
  Priority Order:
    (1) Missing models (if any)
    (2) Oldest models
    (3) Worst R² scores
  
  Selected for Retraining: AHU (LSTM) - age 35d
  
  Trigger Retraining:
    └─ Start training AHU LSTM with latest data
       └─ Training takes ~2-3 hours (runs in background thread)
       └─ API continues responding normally
       └─ Predictions/optimization unaffected
       └─ Other services unaffected
  
  Log Result:
    ✅ Retraining triggered for lstm/ahu
    New model ID: lstm_ahu_20260209_060000
    Remaining stale models: fcu (autoencoder), pump (lstm)
    
  Next cycle (24 hours later):
    └─ FCU (Autoencoder) will be retrained
    
  Following cycle:
    └─ Pump (LSTM) will be retrained
```

### Timeline for Full Fleet Refresh

With **one model per 24-hour cycle**:

| Day | Model Retrained | Age Before | Status After |
|-----|-----------------|-----------|---|
| 1 | AHU (LSTM) | 35d | Fresh (0d) ✅ |
| 2 | FCU (Autoencoder) | 40d | Fresh (0d) ✅ |
| 3 | Pump (LSTM) | 31d | Fresh (0d) ✅ |
| 4 | (No stale models) | — | All fresh ✅ |
| 5-14 | — | — | All remain fresh ✅ |

**Result:** All 14 models refreshed within **3-14 days maximum**.

---

## Configuration

### Enabling Background Retraining

In your app startup code (typically `backend/app/main.py` or a startup module):

```python
from app.services.background_scheduler import scheduler_service

# Example: main.py or startup module
def startup_event():
    """Called when FastAPI app starts"""
    
    # Start the background scheduler
    scheduler_service.start()
    
    # Enable all background jobs
    scheduler_service.add_demo_data_job(interval_seconds=60)
    scheduler_service.add_optimization_analysis_job(interval_seconds=900)
    scheduler_service.add_prediction_generation_job(interval_seconds=300)
    scheduler_service.add_recommendation_generation_job(interval_seconds=600)
    
    # 🆕 Enable ML retraining (checks daily for stale models)
    scheduler_service.add_ml_retraining_job(interval_seconds=86400)
    
    logger.info("Background scheduler started with all jobs enabled")

def shutdown_event():
    """Called when FastAPI app shuts down"""
    scheduler_service.stop()
    logger.info("Background scheduler stopped")
```

### Custom Interval

To check more or less frequently:

```python
# Check for stale models every 12 hours instead of 24
scheduler_service.add_ml_retraining_job(interval_seconds=43200)

# Check every 6 hours (more aggressive)
scheduler_service.add_ml_retraining_job(interval_seconds=21600)

# Check every 48 hours (less aggressive)
scheduler_service.add_ml_retraining_job(interval_seconds=172800)
```

### Tuning Staleness Thresholds

Edit `backend/ml/training/retraining_scheduler.py`:

```python
# Line 13-14
MAX_MODEL_AGE_DAYS = 30      # Default: 30 days
MIN_R2_SCORE = 0.65           # Default: 0.65

# Increase to train less frequently
MAX_MODEL_AGE_DAYS = 45       # Retrain every 45 days instead of 30
MIN_R2_SCORE = 0.60           # More lenient R² threshold

# Decrease to train more frequently
MAX_MODEL_AGE_DAYS = 14       # Retrain every 2 weeks
MIN_R2_SCORE = 0.75           # More strict R² threshold
```

---

## Operational Monitoring

### Check Current Status

**Are models stale?**

```bash
curl http://localhost:9095/api/ml-retraining/status | jq '{
  total_checked: .total_models_checked,
  needs_retrain: .needs_retrain,
  models: .models[] | select(.needs_retrain == true)
}'
```

**Example output:**

```json
{
  "total_checked": 14,
  "needs_retrain": 3,
  "models": [
    {
      "model_type": "lstm",
      "equipment_type": "ahu",
      "status": "stale",
      "age_days": 35,
      "r2_score": 0.69,
      "reason": "Model age 35d exceeds 30d threshold"
    },
    {
      "model_type": "autoencoder",
      "equipment_type": "fcu",
      "status": "stale",
      "age_days": 40,
      "r2_score": 0.58,
      "reason": "Model age 40d exceeds 30d threshold; R² score 0.58 below 0.65 threshold"
    },
    {
      "model_type": "lstm",
      "equipment_type": "pump",
      "status": "stale",
      "age_days": 31,
      "r2_score": 0.73,
      "reason": "Model age 31d exceeds 30d threshold"
    }
  ]
}
```

### Check Retraining History

**What models were recently retrained?**

```bash
curl http://localhost:9095/api/ml-retraining/history | jq '.history | reverse | .[0:5] | .[] | {
  triggered_at: .triggered_at,
  model_type: .model_type,
  equipment_type: .equipment_type,
  success: .success,
  new_model_id: .new_model_id
}'
```

**Example output:**

```json
{
  "triggered_at": "2026-02-09T06:00:15.234567",
  "model_type": "lstm",
  "equipment_type": "ahu",
  "success": true,
  "new_model_id": "lstm_ahu_20260209_060015"
}
{
  "triggered_at": "2026-02-08T06:00:12.123456",
  "model_type": "autoencoder",
  "equipment_type": "fcu",
  "success": true,
  "new_model_id": "autoencoder_fcu_20260208_060012"
}
```

### Check Model Health

**Overall model health score:**

```bash
curl http://localhost:9095/api/ml-retraining/performance/health | jq '.summary'
```

**Example output:**

```json
{
  "health_pct": 95,
  "fresh": 14,
  "stale": 0,
  "missing": 0,
  "underperforming": 0,
  "avg_r2_score": 0.667,
  "avg_age_days": 18
}
```

### Monitor in Real-Time

Check logs to see background training happening:

```bash
# Watch background scheduler logs
tail -f /opt/bms-intelligence/backend/logs/app.log | grep "ML model\|retraining\|auto_retrain"
```

**Example log output:**

```
2026-02-09 06:00:15 INFO: Running scheduled ML model staleness check...
2026-02-09 06:00:15 INFO: Found 3 stale/underperforming models. Retraining priority: ahu (lstm) - Status: stale, Age: 35d, R²: 0.69
2026-02-09 06:00:16 INFO: ✅ Retraining triggered for lstm/ahu. New model ID: lstm_ahu_20260209_060015
2026-02-09 06:00:16 INFO: Remaining stale models (2): fcu (autoencoder), pump (lstm)
2026-02-09 08:23:42 INFO: Training complete for lstm/ahu. New R²: 0.71, improved from 0.69
2026-02-09 08:23:42 INFO: Model registered: lstm_ahu_20260209_060015 (fresh, age: 0d)
```

---

## Verification Checklist

### Post-Deployment Verification

After enabling background retraining:

**✅ Step 1: Verify scheduler started**

```bash
curl http://localhost:9095/api/ml-retraining/status | jq '.total_models_checked'
# Should return: 14
```

**✅ Step 2: Check if stale models exist**

```bash
curl http://localhost:9095/api/ml-retraining/status | jq '.needs_retrain'
# If > 0: Background job will retrain them on next cycle
```

**✅ Step 3: Wait for first cycle (24h by default)**

```bash
# After 24 hours, check if models were retrained
curl http://localhost:9095/api/ml-retraining/history | jq '.history | length'
# Should increase as each cycle completes
```

**✅ Step 4: Verify API remains responsive during training**

While training is happening:

```bash
# Test API responsiveness (should respond immediately)
time curl http://localhost:9095/api/health
# Should complete in < 100ms

# Test device control (should work normally)
curl http://localhost:9095/api/devices/S002-CHILLER-B1-001
# Should return device details instantly

# Test predictions (should work normally)
curl http://localhost:9095/api/ml/predictions/lstm/S002-CHILLER-B1-001
# Should return prediction instantly
```

---

## Troubleshooting

### Problem: Background Retraining Not Happening

**Symptom:** Models stay stale (> 30 days old), no retraining in history

**Diagnosis Steps:**

```bash
# 1. Check if scheduler is running
curl http://localhost:9095/api/ml/health | jq '.scheduler_status'
# Expected: "running"

# 2. Check retraining history
curl http://localhost:9095/api/ml-retraining/history | jq '.history | length'
# If 0: Job never ran

# 3. Check model status
curl http://localhost:9095/api/ml-retraining/status | jq '.needs_retrain'
# If > 0: There are stale models waiting

# 4. Check application logs
tail -50 /opt/bms-intelligence/backend/logs/app.log | grep -i error
```

**Solutions:**

**Option A: Manually trigger retraining**

```bash
# Get list of stale models
stale_models=$(curl -s http://localhost:9095/api/ml-retraining/status | \
  jq '.models[] | select(.needs_retrain == true) | .equipment_type + ":" + .model_type')

# Trigger retraining for each
echo "$stale_models" | while read model; do
  eq_type=$(echo $model | cut -d: -f1)
  model_type=$(echo $model | cut -d: -f2)
  curl -X POST http://localhost:9095/api/ml-retraining/trigger \
    -H "Content-Type: application/json" \
    -d "{\"model_type\": \"$model_type\", \"equipment_type\": \"$eq_type\", \"reason\": \"manual_force\"}"
done
```

**Option B: Restart scheduler**

```bash
# Restart backend service to reinit scheduler
systemctl restart bms-intelligence-backend

# Verify it restarted
sleep 5
curl http://localhost:9095/api/ml/health | jq '.scheduler_status'
```

**Option C: Check job registration**

```python
# In Python shell or script
from app.services.background_scheduler import scheduler_service

# Check if job is registered
job = scheduler_service.scheduler.get_job('auto_retrain_stale_models')
if job:
    print(f"✅ Job registered: {job.name}")
    print(f"   Next run: {job.next_run_time}")
else:
    print("❌ Job not registered")
    # Re-register it
    scheduler_service.add_ml_retraining_job()
```

### Problem: Training Takes Too Long (> 4 hours)

**Symptom:** Single training cycle takes longer than expected, blocking other operations

**Note:** Training runs in background thread, so it shouldn't block API. But if you notice degraded performance:

**Solutions:**

```python
# Reduce epochs (fewer iterations = faster training)
# Edit backend/ml/lstm/trainer.py or autoencoder/trainer.py
EPOCHS = 50  # Changed from 100

# Reduce training data size
MAX_SAMPLES = 5000  # Changed from 10000

# Reduce features (use fewer sensors)
# Edit backend/ml/lstm/data_prep.py
SENSOR_CONFIGS = {
    "chiller": ["chw_supply_temp", "chw_return_temp", "compressor_current"],  # 3 instead of 5
    # ...
}
```

### Problem: Model Training Failed

**Symptom:** Retraining log shows "❌ Failed to trigger retraining: {error}"

**Common errors:**

| Error | Cause | Fix |
|-------|-------|-----|
| `Unknown equipment type: xyz` | Equipment type not in SENSOR_CONFIGS | Add to `backend/ml/lstm/data_prep.py` |
| `Training data empty` | No sensor data available | Verify equipment has recent data |
| `Out of memory` | Training dataset too large | Reduce MAX_SAMPLES in data_prep.py |
| `Timeout` | Training took > time limit | Increase timeout or reduce epochs |

**Debug:**

```bash
# Check what equipment types are supported
curl http://localhost:9095/api/ml-retraining/status | jq '.models[] | .equipment_type' | sort -u
```

---

## Production Best Practices

### 1. Monitor Daily

```bash
#!/bin/bash
# ml-health-check.sh - Run daily

echo "ML Model Health Check - $(date)"
echo "================================"

curl -s http://localhost:9095/api/ml-retraining/performance/health | jq '{
  health_pct: .summary.health_pct,
  fresh: .summary.fresh,
  stale: .summary.stale,
  missing: .summary.missing
}'

echo ""
echo "Recent Retraining Activity:"
curl -s http://localhost:9095/api/ml-retraining/history | \
  jq '.history | reverse | .[0:3] | .[] | "\(.triggered_at): \(.model_type)/\(.equipment_type) - \(.success)"'
```

Add to crontab:

```bash
0 3 * * * /opt/bms-intelligence/scripts/ml-health-check.sh >> /var/log/ml-health-check.log
```

### 2. Alert on Failures

```python
# In your monitoring/alerting system
# Alert if more than 1 stale model after 48 hours

stale_count = requests.get("http://localhost:9095/api/ml-retraining/status").json()['needs_retrain']

if stale_count > 1:
    # Check if any were successfully retrained in last 48 hours
    history = requests.get("http://localhost:9095/api/ml-retraining/history").json()['history']
    recent_success = any(
        h['success'] and datetime.fromisoformat(h['triggered_at']) > datetime.now() - timedelta(days=2)
        for h in history
    )
    
    if not recent_success:
        # Alert: Background retraining not working
        send_alert("⚠️ ML retraining failures - {stale_count} models stale")
```

### 3. Plan for Maintenance

When updating models or training logic:

```python
# 1. Stop retraining temporarily
scheduler_service.scheduler.pause_job('auto_retrain_stale_models')

# 2. Update training code
# ... make changes ...

# 3. Resume retraining
scheduler_service.scheduler.resume_job('auto_retrain_stale_models')

# 4. Verify
status = scheduler_service.scheduler.get_job('auto_retrain_stale_models')
print(f"Job state: {status.next_run_time}")
```

---

## Integration with Other Services

### Predictions Service

Background retraining doesn't affect prediction generation:

- Predictions use **currently active models** (not models being trained)
- During training, **old model continues to work**
- New model only activated after training completes and passes validation
- Zero downtime for predictions

### Optimization Service

Background retraining doesn't affect AI optimization:

- Optimization uses all available equipment data
- If prediction model is in training, old model used temporarily
- Once new model ready, optimization gets more accurate predictions
- Better predictions = better recommendations

### Device Control

Background retraining never blocks device control:

- Device control is synchronous (immediate response)
- ML retraining is asynchronous (background thread)
- No resource contention
- Control operations always prioritized

---

## Summary

| Aspect | Details |
|--------|---------|
| **When** | Daily (24h default, configurable) |
| **What** | Checks all 14 models for staleness (age > 30d or R² < 0.65) |
| **How Many** | ONE model per cycle (prevents overload) |
| **How Long** | ~2-3 hours per model (runs in background, doesn't block API) |
| **Priority** | Missing models → oldest models → worst performers |
| **Result** | All 14 models refreshed within 2 weeks |
| **Monitoring** | `/api/ml-retraining/status`, `/api/ml-retraining/history` |
| **Production Ready** | ✅ Yes - fully automated, tested, production-safe |

**Key Guarantee:** Background retraining happens automatically without disrupting live building operations, predictions, or optimization.

---

## References

- [ML Predictions API](../03-api-reference/ml-predictions-api.md) - Prediction endpoints
- [ML Retraining API](../03-api-reference/ml-retraining-api.md) - Retraining endpoints
- [ML Equipment Support](ml-equipment-support.md) - Supported equipment types
- [Online Learning & Auto-Retraining](../04-features/45-01-online-learning.md) - Feature overview
- [Troubleshooting ML Model Health](../05-troubleshooting/ml-model-health.md) - Troubleshooting guide
