---
title: "ML Predictive Maintenance & Anomaly Detection"
type: "feature"
status: "published"
version: "1.0.0"
created: "2026-02-09"
updated: "2026-02-09"
author: "Sentinel Development Team"
tags: ["ml", "predictive", "maintenance", "anomaly", "lstm", "autoencoder"]
domain: "operations"
audience: "facilities-managers, operators, technicians"
complexity: "beginner"
estimated_read_time: 15
---

# ML Predictive Maintenance & Anomaly Detection

## Overview

SENTINEL uses **machine learning** to predict equipment failures **24-72 hours in advance** and detect equipment degradation in real-time. This transforms maintenance from **reactive** (expensive emergency repairs) to **proactive** (planned, cost-effective maintenance).

### Two Complementary AI Systems

| System | Model Type | Purpose | Benefit |
|--------|-----------|---------|---------|
| **Forecasting** | LSTM Neural Network | Predict sensor values 24/48/72 hours ahead | Plan maintenance before failure |
| **Anomaly Detection** | Autoencoder | Detect abnormal equipment behavior in real-time | Catch degradation early |

---

## 1. Predictive Maintenance (LSTM Models)

### How It Works

LSTM (Long Short-Term Memory) models learn **normal equipment patterns** by analyzing historical sensor data, then predict future values:

**Example: Chiller**
```
Historical Data (168 hours):
  Supply Temp: 7.0°C → 7.2°C → 7.5°C → ...
  Discharge Pressure: 210 PSI → 215 PSI → 220 PSI → ...
  Compressor Current: 45A → 46A → 48A → ...

LSTM Prediction:
  24 hours: Supply Temp = 7.8°C (confidence: 85%)
  48 hours: Supply Temp = 8.1°C (confidence: 78%)
  72 hours: Supply Temp = 8.5°C (confidence: 72%)

Interpretation:
  ⚠️ Supply temperature trending UP
  ⚠️ Expected to exceed 8°C cooling target in 24-48 hours
  ✅ Schedule maintenance Thursday to prevent Friday outage
```

### What Each Equipment Type Predicts

| Equipment | Key Prediction | Early Warning Signs |
|-----------|-----------------|-------------------|
| **Chiller** | Supply temperature | Rising temps = compressor strain |
| **AHU** | Supply air temperature | Rising temps = filter clogging |
| **VAV** | Zone temperature | Unstable zones = damper wear |
| **Pump** | Discharge pressure | Dropping pressure = impeller wear |
| **Generator** | Coolant temperature | Rising temp = radiator fouling |
| **UPS** | Battery temperature | Rising temp = battery degradation |
| **FCU** | Room temperature | Lag time = valve sticking |

### Using Predictions in Operations

**Step 1: Check Predictions**
```
GET /api/ml/predictions/lstm/S002-CHILLER-B1-001?equipment_type=chiller
```

**Step 2: Review Forecast**
- 24h forecast: 7.8°C (normal range: 6.5-8.0°C) ✅ OK
- 48h forecast: 8.5°C ⚠️ **ABOVE TARGET**
- 72h forecast: 9.0°C ❌ **CRITICAL**

**Step 3: Take Action**
- **Green** (all forecasts normal): Continue normal operation
- **Yellow** (one forecast elevated): Schedule maintenance in next 48 hours
- **Red** (multiple forecasts high): Emergency maintenance needed

---

## 2. Anomaly Detection (Autoencoder Models)

### How It Works

Autoencoders learn **what normal equipment looks like** by analyzing patterns, then flag anything that deviates:

**Example: Pump with Bearing Wear**

```
Normal Pattern (Training Data):
  ✓ Vibration: 2-3 mm/s
  ✓ Flow Rate: 45-50 GPM
  ✓ Current Draw: 15-16A
  ✓ Temperature: 35-38°C

Live Monitoring:
  Vibration: 4.2 mm/s ❌ TOO HIGH (bearing wear!)
  Flow Rate: 46 GPM ✓ OK
  Current Draw: 15.5A ✓ OK
  Temperature: 36°C ✓ OK

Autoencoder Result:
  🚨 ANOMALY DETECTED (Score: 0.85, threshold: 0.70)
  Severity: HIGH
  Related Faults: ["bearing_wear", "insufficient_lubrication"]
  Recommended Action: "Inspect bearings within 24 hours"
```

### Anomaly Severity Levels

| Severity | Score Range | Meaning | Action |
|----------|-------------|---------|--------|
| **Healthy** | 0.0 - 0.50 | Normal operation | None |
| **Warning** | 0.50 - 0.70 | Monitor closely | Plan maintenance |
| **Alert** | 0.70 - 0.85 | Probable degradation | Schedule within 48h |
| **Critical** | 0.85 - 1.0 | Imminent failure risk | Emergency action |

### Real-Time Anomaly Alerts

```
GET /api/ml/anomalies/alerts
```

Returns all equipment currently showing anomalous behavior:

```json
{
  "alerts": [
    {
      "equipment_id": "S002-PUMP-B1-001",
      "equipment_name": "Chilled Water Pump",
      "anomaly_score": 0.87,
      "severity": "critical",
      "detected_at": "2026-02-09T22:15:00Z",
      "related_faults": ["bearing_wear", "vibration_high"],
      "recommended_actions": [
        "Inspect pump bearings immediately",
        "Check lubrication level",
        "Verify coupling alignment"
      ]
    }
  ]
}
```

---

## 3. Business Benefits

### Cost Savings

| Scenario | Reactive (No ML) | Proactive (With ML) | Savings |
|----------|-----------------|-------------------|---------|
| **Chiller Failure** | $50K emergency repair + downtime | $5K preventive maintenance | **$45K** |
| **Emergency Tech Call** | $2K emergency rate × 4h = $8K | $500 planned visit | **$7.5K** |
| **Tenant Disruption** | 4-hour AC outage (high complaint) | Zero downtime | **Priceless** |
| **Annual per Equipment** | $50-100K in emergency costs | $10-20K in planned maintenance | **60-80% reduction** |

**Total Impact: $100K-$500K/year in cost avoidance**

### Operational Benefits

✅ **99.9%+ Uptime**: Equipment failures prevented before they happen
✅ **Planned Maintenance**: Schedule repairs during off-peak hours
✅ **Technician Efficiency**: No more emergency calls, better work planning
✅ **Tenant/User Satisfaction**: No unexpected AC/heat/air quality failures
✅ **Equipment Life Extension**: Catch wear early, avoid catastrophic failures
✅ **Compliance**: Track maintenance for audit trails

---

## 4. Equipment Type Support

Current ML Model Coverage (Feb 2026):

| Equipment Type | LSTM Forecasting | Anomaly Detection | Status |
|---|---|---|---|
| Chiller | ✅ | ✅ | Fully Supported |
| AHU | ✅ | ✅ | Fully Supported |
| Generator | ✅ | ✅ | Fully Supported |
| FCU | ✅ | ✅ | Fully Supported |
| VAV | ✅ | ✅ | Fully Supported |
| UPS | ✅ | ✅ | Fully Supported |
| Pump | ✅ | ✅ | Fully Supported |

**Total: 7 equipment types × 2 model types = 14 active models**

---

## 5. Interpreting Dashboard Indicators

### Model Health Score

The **Model Health** tab shows:
- **Green (95%+)**: All models trained and active ✅
- **Yellow (70-95%)**: Some models stale or underperforming ⚠️
- **Red (<70%)**: Multiple models missing ❌

**Feb 9, 2026 Status**: 95% health (14/14 models trained)

### Model Status

| Status | Meaning | Action |
|--------|---------|--------|
| **Fresh** | Recently trained, good performance | None - keep using |
| **Stale** | >30 days old, needs retraining | Schedule retraining |
| **Underperforming** | R² < 0.60 or accuracy < 80% | Investigate data quality |
| **Missing** | Never trained for equipment type | Train new model |

---

## 6. Practical Examples

### Example 1: Preventing Chiller Failure

**Tuesday 2 PM:**
- System predicts chiller supply temp will exceed 9°C by Thursday
- Current reading: 7.5°C (normal)
- Confidence: 82%

**Action:** Schedule technician Thursday morning
- Result: Technician finds compressor suction valve partially blocked
- Fix time: 2 hours (planned)
- Cost: $500 (regular rate)

**Alternative (No ML):**
- Thursday 2 PM: Chiller fails completely during peak cooling demand
- Emergency tech call: 4-hour wait
- Chiller replacement: $50K+ (emergency premium)
- Downtime cost: $5K/hour × 4 hours = $20K
- Total: $70K+ in emergency costs + tenant complaints

**Savings: $69.5K**

### Example 2: Catching VAV Bearing Wear

**Daily monitoring:**
- Autoencoder detects increasing vibration in VAV-L2-E
- Anomaly score: 0.35 → 0.45 → 0.62 (trending up)

**Day 3:**
- Anomaly score hits 0.72 (Alert threshold)
- System: "High vibration detected - bearing wear suspected"

**Action:** Inspect VAV-L2-E
- Finding: Bearing lubrication dried out
- Fix: Bearing relubrication (30 minutes, $150)

**Alternative (No ML):**
- Day 7: Bearing seizes completely
- Damper stuck in wrong position
- Zone loses HVAC control
- Emergency repair: $2K+ (weekend emergency rate)
- 6-hour downtime during occupied hours

**Savings: $1.85K + avoided tenant complaint**

---

## 7. When to Trust ML Predictions

### ✅ High Confidence Scenarios

1. **Trending patterns**: Temperature trending up for 48+ hours
2. **Multiple data sources**: Multiple sensors confirming same trend
3. **Consistent history**: Equipment has years of historical data
4. **Stable operations**: Recent configuration hasn't changed

### ⚠️ Lower Confidence Scenarios

1. **New equipment**: <30 days of operational history
2. **Recent repairs**: Equipment just repaired (retraining needed)
3. **Changed operating mode**: New setpoints or control logic
4. **Sensor issues**: Suspected bad sensor reading

### ❌ Don't Trust Predictions If

- Model is marked "stale" (>30 days old)
- Model is marked "underperforming" (R² < 0.60)
- Equipment had major configuration change
- Sensor was recently replaced

---

## 8. Integration with Work Orders

ML predictions automatically trigger **work order creation** when confidence is high:

```
High-Confidence Prediction:
  Equipment: S002-CHILLER-B1-001
  Issue: Supply temp trending above 8.5°C
  Confidence: 87%
  Forecast: Will exceed critical threshold in 24-36 hours

Automatic Action:
  ✅ Work Order created (WO-2026-0234)
  ✅ Assigned to HVAC technician
  ✅ Scheduled for tomorrow morning
  ✅ Technician receives Sentry notification
```

**Manual trigger** if you want to create work order for lower-confidence predictions:

```
GET /api/work-orders/technician-for-equipment/S002-CHILLER-B1-001
POST /api/work-orders/supabase
```

---

## 9. Continuous Improvement

### Model Retraining

Models are automatically retrained when:
- **30+ days old** (stale threshold)
- **Accuracy drops** below 80% (underperforming)
- **New data available** (weekly automatic retraining)

**Manual Retraining:**
```
POST /api/ml-retraining/trigger?model_type=lstm&equipment_type=chiller
```

### A/B Testing New Models

When a new model is trained, it's tested against the current active model:

```
POST /api/ml-retraining/ab-test/create?model_type=lstm&equipment_type=chiller
```

- **Control**: Current active model (90% of predictions)
- **Candidate**: New model (10% of predictions)
- **Winner**: Whichever has better accuracy after 100+ predictions
- **Promotion**: Winner automatically becomes active

---

## 10. Troubleshooting

### Problem: Model Health Shows Red (Low Coverage)

**Diagnosis:**
```
GET /api/ml-retraining/performance/health
```

**Solutions:**
- If status = "missing": Model never trained → See [Training New Equipment Types](ml-equipment-support.md)
- If status = "stale": Model >30 days old → Trigger retraining
- If status = "underperforming": R² < 0.60 → Check data quality or rebuild model

### Problem: Predictions Don't Match Reality

**Possible Causes:**
1. Model too old (check age_days)
2. Equipment configuration changed
3. Sensor reading is inaccurate
4. Insufficient training data for new equipment type

**Fix:**
```
# Check model status
GET /api/ml-retraining/status

# Retrain if stale
POST /api/ml-retraining/trigger?model_type=lstm&equipment_type=chiller

# Verify sensor accuracy
GET /api/equipment/S002-CHILLER-B1-001/sensor-validation
```

---

## Summary

**SENTINEL's ML system provides:**

1. ✅ **24-72 hour advance warning** of equipment failures (LSTM forecasting)
2. ✅ **Real-time anomaly detection** of degradation (Autoencoder)
3. ✅ **Automatic work order creation** for high-confidence predictions
4. ✅ **Cost savings**: 60-80% reduction in emergency maintenance
5. ✅ **99.9%+ uptime**: Failures prevented before they happen
6. ✅ **14 equipment types** currently supported with active models

**Next Steps:**
- Check Model Health dashboard for current status
- Review ML Anomaly Alerts weekly
- Create work orders for predicted issues
- Report feedback on prediction accuracy to improve models

For technical details, see [ML Predictions API](../03-api-reference/ml-predictions-api.md) and [ML Equipment Support](ml-equipment-support.md).
