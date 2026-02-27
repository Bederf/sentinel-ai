---
title: "Recommendations System Troubleshooting Guide"
type: "operational"
status: "complete"
version: "1.0.0"
created: "2026-02-11"
updated: "2026-02-11"
author: "Sentinel Development Team"
tags: ["troubleshooting", "recommendations", "debugging", "operations"]
related: ["./background-recommendation-generation.md", "../03-api-reference/recommendations-api.md"]
domain: "bms"
audience: "operators|developers"
complexity: "intermediate"
estimated_read_time: 10
---

# Recommendations System Troubleshooting Guide

## Quick Checklist

Before diving into details, check these 4 things:

- [ ] Backend service is running: `systemctl status sentinel-backend.service`
- [ ] Has been running for ≥10 minutes (first recommendations take 10 minutes to generate)
- [ ] Equipment exists: Check Supabase `equipment` table has > 0 rows
- [ ] Some equipment has health < 90%: `SELECT code, health_score FROM equipment WHERE health_score < 90`

## Common Issues & Solutions

### Issue 1: "No recommendations on dashboard"

**Symptom:** Dashboard loads but no recommendations appear, even after waiting 10+ minutes

**Root Cause:** Either scheduler not running, or all equipment is healthy (≥90%)

**Solution:**

1. **Verify scheduler is running:**
   ```bash
   systemctl status sentinel-backend.service
   # Should show: Active: active (running)
   ```

2. **Check if recommendations job exists:**
   ```python
   # In Python console with backend context
   from app.services.background_scheduler import scheduler_service
   jobs = scheduler_service.scheduler.get_jobs()
   print([j.id for j in jobs])
   # Should include 'generate_recommendations'
   ```

3. **Check equipment health status:**
   ```sql
   -- In Supabase
   SELECT code, health_score, status FROM equipment
   ORDER BY health_score ASC LIMIT 10;

   -- If all >= 90%, no recommendations will be generated
   -- Need to degrade health by creating alerts
   ```

4. **If equipment is healthy, create an alert to degrade health:**
   ```bash
   # Option A: Manually insert alert in Supabase
   INSERT INTO alerts (equipment_id, severity, type, message, status)
   VALUES ('equipment-uuid', 'critical', 'health_warning', 'Test alert', 'active');

   # This triggers health_score update in alerts.py
   # Next job cycle (10 min) will generate recommendation
   ```

5. **Or run a simulation (faster for testing):**
   ```bash
   curl -X POST http://localhost:9095/api/lifecycle/demo/quick-cycle \
     -H "Content-Type: application/json" \
     -d '{"site": "site-002"}'

   # This injects faults → health drops → recommendations appear within 5 minutes
   ```

### Issue 2: "Recommendations disappeared after I approved them"

**Symptom:** Recommendations were shown, user approved them, now they're gone from dashboard

**Expected Behavior:**
- Approved recommendations move to "Completed" status
- Create corresponding work orders
- Still visible in API but marked as approved

**Solution:**
- Check the `/api/recommendations/{site_id}` endpoint with filters for status
- View work orders created: `GET /api/work-orders`
- Dashboard may filter to show only "pending" recommendations by default

### Issue 3: "Same recommendation keeps reappearing"

**Symptom:** User approves a recommendation, but identical one appears again in next cycle

**Root Cause:** Underlying equipment health hasn't changed enough

**Solution:**
1. Verify equipment health improved after work order completion
2. Request service feedback from technician
3. Feedback should update equipment health score
4. Next cycle should not generate same recommendation

### Issue 4: "Backend keeps restarting, scheduler loses jobs"

**Symptom:** Backend crashes/restarts and recommendations stop appearing

**Root Cause:** Jobs are not persistent; they're created fresh on startup

**Solution:**
1. **Check if startup event is running:**
   ```bash
   journalctl -u sentinel-backend.service -n 50 -f
   # Look for: "Added recommendation generation job with 600s interval"
   ```

2. **If not present, startup event may be failing:**
   ```bash
   # Check for startup errors
   journalctl -u sentinel-backend.service | grep -i "error\|failed\|startup"
   ```

3. **Restart backend:**
   ```bash
   sudo systemctl restart sentinel-backend.service
   sleep 3
   journalctl -u sentinel-backend.service -n 20  # View startup logs
   ```

### Issue 5: "Recommendations generation is very slow (>30 seconds)"

**Symptom:** Background job takes a long time, slows down API responses

**Root Cause:**
- Too many equipment items (500+)
- Supabase query rate limiting (429 errors)
- Database performance issues

**Solution:**

1. **Check job execution time in logs:**
   ```bash
   journalctl -u sentinel-backend.service -g "generate_recommendations" -n 20
   # Look for duration info
   ```

2. **Check for rate limit errors:**
   ```bash
   journalctl -u sentinel-backend.service | grep -i "429\|rate limit"
   # If present, job is retrying - normal behavior
   ```

3. **Reduce equipment count for testing:**
   ```sql
   -- Temporarily disable some equipment from recommendations
   UPDATE equipment SET status = 'offline'
   WHERE code LIKE 'site-005%';

   -- Recommendations job will skip offline equipment
   ```

4. **Increase interval if needed (less frequent execution):**
   ```python
   # In backend/app/startup/events.py
   scheduler_service.add_recommendation_generation_job(
       interval_seconds=1200  # 20 minutes instead of 10
   )
   ```

### Issue 6: "Recommendations missing data (null fields)"

**Symptom:** Recommendations appear but have missing fields (no manufacturer, model, age)

**Root Cause:** Equipment metadata not populated (missing from device_info, commissioning_date)

**Solution:**

1. **Run equipment discovery to populate metadata:**
   ```bash
   cd /opt/bms-intelligence/backend
   python3 scripts/run_equipment_discovery_site002.py site-002
   # For other sites:
   python3 scripts/run_equipment_discovery_site002.py site-005
   ```

2. **Check if metadata exists:**
   ```sql
   SELECT code, manufacturer, model, commissioning_date, device_info
   FROM equipment
   WHERE code LIKE 'site-002%'
   LIMIT 5;
   ```

3. **Manually populate missing fields:**
   ```sql
   UPDATE equipment
   SET manufacturer = 'Carrier', model = 'AquaEdge'
   WHERE code = 'S002-CHILLER-B1-001';
   ```

## Performance Benchmarks

### Expected Execution Times

| Equipment Count | Execution Time | Queries | Status |
|-----------------|----------------|---------|--------|
| 50 items | 1-2 sec | 100 | ✅ Optimal |
| 175 items | 2-5 sec | 350 | ✅ Good |
| 500 items | 5-12 sec | 1000 | ✅ Acceptable |
| 1000+ items | 15+ sec | 2000+ | ⚠️ Consider optimization |

### If Slow (>10 seconds):

1. Check Supabase query performance
2. Consider adding indexes on equipment.health_score, equipment.building_id
3. Batch queries if possible
4. Increase job interval to reduce frequency

## Monitoring & Health Checks

### Check Health Every 10 Minutes

```bash
# Script to run in cron every 10 min
# Verifies scheduler is executing

#!/bin/bash
JOB_NAME='generate_recommendations'

# Check if job exists
python3 << 'EOF'
from app.services.background_scheduler import scheduler_service
job = scheduler_service.scheduler.get_job('generate_recommendations')
if job:
    print("✅ Recommendation job is running")
else:
    print("❌ Recommendation job not found - restarting...")
    # Trigger restart
    import os
    os.system('systemctl restart sentinel-backend.service')
EOF
```

### Check Job Execution

```sql
-- Count recommendations generated per hour (requires audit trail)
SELECT DATE_TRUNC('hour', created_at) as hour, COUNT(*) as count
FROM recommendations
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY hour
ORDER BY hour DESC;

-- Should see recommendations generated every hour
-- (generated at :00, :10, :20, :30, :40, :50 minutes)
```

## Debugging Logs

### Enable Debug Logging

```bash
# Edit backend/app/startup/events.py to add verbose logging
logger.setLevel(logging.DEBUG)

# Then restart
systemctl restart sentinel-backend.service

# View detailed logs
journalctl -u sentinel-backend.service -f -g "generate_recommendations"
```

### Key Log Messages to Look For

| Message | Meaning |
|---------|---------|
| "Running scheduled AI recommendation generation..." | Job started normally |
| "Generating recommendations for X equipment" | Processing in progress |
| "Rate limit hit, retrying in..." | Rate limit encountered (temporary) |
| "Failed to store recommendations" | Supabase error - check connection |
| "Job execution completed" | Job finished successfully |

## Manual Testing

### Test Recommendation Generation Manually

```python
# In Python console with backend context
from app.services.background_scheduler import scheduler_service

# Get the job
job = scheduler_service.scheduler.get_job('generate_recommendations')

# Execute immediately (don't wait 10 minutes)
job.func()

# Check Supabase for new recommendations
# SELECT * FROM recommendations ORDER BY created_at DESC LIMIT 1;
```

### Verify Full Workflow

```bash
# 1. Create test equipment alert
curl -X POST http://localhost:9095/api/alerts \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "equipment_id": "uuid",
    "severity": "critical",
    "type": "health_warning",
    "message": "Test alert for recommendation"
  }'

# 2. Wait 10 minutes OR manually trigger job
# (Python console: job.func())

# 3. Check recommendations appear
curl http://localhost:9095/api/recommendations/site-002 \
  -H "Authorization: Bearer $TOKEN" | jq .

# 4. Approve recommendation
curl -X POST http://localhost:9095/api/recommendations/{rec_id}/approve \
  -H "Authorization: Bearer $TOKEN"

# 5. Verify work order created
curl http://localhost:9095/api/work-orders \
  -H "Authorization: Bearer $TOKEN" | jq .
```

## Getting Help

### Key Documentation Files

1. **Architecture & Design:** `docs/08-ai-ml/background-recommendation-generation.md`
2. **API Reference:** `docs/03-api-reference/recommendations-api.md`
3. **AI System:** `docs/08-ai-ml/ai-recommendation-system.md`
4. **Profile-Based:** `docs/04-features/72-profile-based-optimization.md`

### Escalation Path

1. **Check logs:** `journalctl -u sentinel-backend.service`
2. **Check database:** Verify Supabase tables have data
3. **Restart service:** `systemctl restart sentinel-backend.service`
4. **Run discovery:** `python3 backend/scripts/run_equipment_discovery_site002.py`
5. **Create alerts:** Manually trigger health degradation
6. **Run simulation:** Demo quick-cycle to test full workflow

### Issue 7: "Recommendations don't reference ML predictions"

**Symptom:** Recommendations are generated but don't mention LSTM forecasts, anomaly scores, or fault classifications

**Root Cause:** ML Context Injection (Phase 132) requires trained models and recent telemetry

**Solution:**

1. **Verify ML models are registered:**
   ```bash
   curl http://localhost:9095/api/ml-retraining/status | jq '.total_models_checked'
   # Should return: 14+ (7 LSTM + 7 Autoencoder minimum)
   ```

2. **Check if ML context is being gathered:**
   ```bash
   # Look for ML context gathering in logs
   journalctl -u sentinel-backend.service | grep -i "ml_context\|gather_ml"
   ```

3. **Verify individual ML services:**
   ```bash
   # LSTM forecasts
   curl http://localhost:9095/api/ml/predictions/lstm/S002-CHILLER-B1-001?equipment_type=chiller

   # Anomaly scores
   curl http://localhost:9095/api/ml/anomalies/equipment/S002-CHILLER-B1-001
   ```

4. **If ML models exist but context is empty:**
   - Ensure `_gather_ml_context()` in `ai_optimizer.py` can reach all ML services
   - Each ML service call is wrapped in try/except — check debug logs for suppressed errors
   - Verify equipment types match ML model registry entries

**Related:** See [ML Context Injection](ai-recommendation-system.md#ml-context-injection-phase-132) and [ML Data Architecture](../02-architecture/ML-DATA-ARCHITECTURE.md)

---

## Summary

✅ **Recommendations run automatically every 10 minutes**
✅ **No manual triggers needed**
✅ **Requires at-risk equipment (health < 90%)**
✅ **Full audit trail in Supabase**
✅ **Integrated with work orders and service feedback**
✅ **ML context injection enriches Claude's reasoning (Phase 132)**

Most issues resolved by:
1. Restarting backend service
2. Creating alerts to degrade equipment health
3. Running equipment discovery if metadata missing
4. Waiting 10 minutes for next job cycle
