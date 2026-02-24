---
title: "ML Predictions API Reference"
type: "reference"
status: "approved"
version: "3.0.0"
created: "2026-02-06"
updated: "2026-02-23"
author: "Sentinel Development Team"
tags: ["api", "ml", "predictions", "lstm", "anomaly", "classifier", "maintenance", "registry", "phase-68-03"]
domain: "general"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 18
changes: "v25.0: Fault classification pipeline — classifier training, anomaly→classification wiring, health check"
---

# ML Predictions API Reference

ML Model Development endpoints. LSTM forecasting, autoencoder anomaly detection, Random Forest fault classification, model management, training, and maintenance recommendations. **Phase 68-03+:** Database-driven registry with async support for multi-site deployment.

**Architecture:**
- Backend queries Supabase `ml_models` and `model_thresholds` tables
- Predictions use equipment type to lookup active models
- Confidence thresholds configured per equipment type (Tier 2: advisory, Tier 3: auto-execute)
- Graceful degradation: equipment without models returns no predictions (not errors)

Base path: `/api/ml`

## LSTM Predictions

### GET `/api/ml/predictions/lstm/{equipment_id}`

Get 24/48/72 hour sensor predictions.

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| equipment_type | string | Yes | chiller, ahu, fcu, vav, generator, ups, pump |
| include_explanation | bool | No | Include natural language explanation |

**Response:**
```json
{
  "equipment_id": "S002-CHILLER-B1-001",
  "equipment_type": "chiller",
  "predictions": {
    "24h": {"value": 7.5, "confidence": 0.85},
    "48h": {"value": 7.8, "confidence": 0.78},
    "72h": {"value": 8.1, "confidence": 0.72}
  },
  "confidence": 0.85,
  "explanation": "Chilled water supply temperature trending upward...",
  "maintenance_recommendations": [...]
}
```

### GET `/api/ml/predictions/trend/{equipment_id}`

Historical + predicted trend data for visualization.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| equipment_type | string | required | Equipment type |
| hours_history | int | 168 | Historical hours (7 days) |
| include_explanation | bool | false | Include explanation |

### POST `/api/ml/predictions/batch`

Batch predictions for multiple equipment.

**Request Body:**
```json
[
  {"equipment_id": "S002-CHILLER-B1-001", "equipment_type": "chiller"},
  {"equipment_id": "S002-AHU-L2-001", "equipment_type": "ahu"}
]
```

## Anomaly Detection

### GET `/api/ml/anomalies/equipment/{equipment_id}`

Check for anomalous behavior using autoencoder model.

**Response:**
```json
{
  "equipment_id": "S002-CHILLER-B1-001",
  "is_anomaly": true,
  "anomaly_score": 0.87,
  "severity": "warning",
  "explanation": "Reconstruction error elevated...",
  "related_faults": ["compressor_overload"],
  "recommended_actions": ["Inspect compressor bearings"],
  "fault_classification": {
    "predicted_failure": "compressor_failure",
    "confidence": 0.72,
    "all_probabilities": {
      "compressor_failure": 0.72,
      "refrigerant_leak": 0.12,
      "condenser_fouling": 0.08,
      "oil_issue": 0.05,
      "electrical": 0.02,
      "normal": 0.01
    },
    "contributing_factors": [
      {"feature": "avg_temp", "importance": 0.15},
      {"feature": "run_hours", "importance": 0.12},
      {"feature": "efficiency_ratio", "importance": 0.10}
    ]
  }
}
```

> **Note:** `fault_classification` is only present when `is_anomaly: true` and a trained classifier exists for the equipment type. Returns `null` if no classifier available.

### GET `/api/ml/anomalies/all`

All monitored equipment anomaly status, sorted by score (highest first).

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| limit | int | 20 | Max results |

### GET `/api/ml/anomalies/alerts`

Equipment currently flagged as anomalous only.

### GET `/api/ml/anomalies/history/{equipment_id}`

Anomaly score history for trending.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| equipment_type | string | required | Equipment type |
| days | int | 7 | Lookback period |

## Model Management

### GET `/api/ml/models`

List all registered ML models.

| Parameter | Type | Description |
|-----------|------|-------------|
| model_type | string | Filter: lstm, autoencoder, classifier |
| equipment_type | string | Filter by equipment type |
| status | string | Filter: active, candidate, retired |

### GET `/api/ml/models/{model_id}`

Get specific model details.

### POST `/api/ml/models/{model_id}/activate`

Set model as active for inference.

### GET `/api/ml/models/compare/{model_type}/{equipment_type}`

Compare all model versions for a type/equipment combination.

## Training

### POST `/api/ml/train/lstm/{equipment_type}`

Train new LSTM model (background).

**Request Body:**
```json
{
  "epochs": 50,
  "use_demo_data": true
}
```

**Response:**
```json
{
  "status": "training_started",
  "message": "LSTM model training initiated",
  "model_id": "lstm_chiller_20260206_150000",
  "metrics": {}
}
```

### POST `/api/ml/train/autoencoder/{equipment_type}`

Train new autoencoder model.

### POST `/api/ml/train/classifier/{equipment_type}`

Train a new Random Forest failure type classifier. Uses synthetic data (100 samples per failure type + normal class). Trains in ~2 seconds per equipment type.

**Response:**
```json
{
  "status": "completed",
  "message": "Classifier trained for chiller",
  "model_id": "/opt/.../chiller_rf_20260223.joblib",
  "metrics": {"accuracy": 0.61, "n_classes": 6}
}
```

Supported equipment types: `chiller`, `ahu`, `generator`, `fcu`, `ups`

### POST `/api/ml/train/all`

Train all model types (LSTM + Autoencoder + Classifier) for all equipment types.

## Maintenance Recommendations

### POST `/api/ml/maintenance/recommendations`

Generate recommendations combining ML predictions with RAG knowledge and fleet experience.

**Request Body:**
```json
{
  "equipment_id": "S002-CHILLER-B1-001",
  "equipment_type": "chiller",
  "include_historical": true,
  "urgency_filter": "high"
}
```

**Response:**
```json
{
  "recommendations": [...],
  "total_estimated_time": 4.5,
  "total_estimated_cost": 12500,
  "priority_breakdown": {"high": 2, "medium": 1, "low": 1}
}
```

### GET `/api/ml/maintenance/priorities/{equipment_type}`

Priority framework for equipment type.

### GET `/api/ml/maintenance/history/{equipment_id}`

Historical maintenance actions and outcomes.

### POST `/api/ml/maintenance/feedback`

Submit feedback on recommendation accuracy.

## Health

### GET `/api/ml/health`

ML service health and model availability.

**Response:**
```json
{
  "status": "healthy",
  "total_models": 25,
  "active_models": 20,
  "lstm_models_active": 7,
  "autoencoder_models_active": 7,
  "classifier_models_active": 5,
  "equipment_types_covered": ["chiller", "ahu", "fcu", "ups", "generator", "vav", "pump"]
}
```
