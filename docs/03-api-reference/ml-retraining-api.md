---
title: "ML Retraining API Reference"
type: "reference"
status: "approved"
version: "1.0.0"
created: "2026-02-06"
updated: "2026-02-26"
author: "Sentinel Development Team"
tags: ["api", "ml", "retraining", "ab-testing"]
domain: "general"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 8
---

# ML Retraining API Reference

Phase 45-01 Online Learning & Automated Retraining endpoints.

Base path: `/api/ml-retraining`

## Model Status

### GET `/api/ml-retraining/status`

Check all models for staleness and performance issues.

**Response:**
```json
{
  "total_models_checked": 14,
  "needs_retrain": 2,
  "models": [
    {
      "model_type": "lstm",
      "equipment_type": "chiller",
      "model_id": "lstm_chiller_20260105_120000",
      "status": "stale",
      "age_days": 45,
      "r2_score": 0.72,
      "needs_retrain": true,
      "reason": "Model age 45d exceeds 30d threshold"
    }
  ]
}
```

Status values: `fresh`, `stale`, `underperforming`, `missing`

## Trigger Retraining

### POST `/api/ml-retraining/trigger`

Trigger model retraining for a specific model type and equipment type.

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| model_type | string | Yes | `lstm`, `autoencoder`, or `classifier` |
| equipment_type | string | Yes | `chiller`, `ahu`, `fcu`, `vav`, `generator`, `ups`, `pump` |
| reason | string | No | Reason for retraining (default: `manual`) |

**Response:**
```json
{
  "triggered": true,
  "model_type": "lstm",
  "equipment_type": "chiller",
  "reason": "manual",
  "new_model_id": "lstm_chiller_20260206_150000",
  "error": null
}
```

## Training Data Status

### GET `/api/ml-retraining/training-data`

Check available real training data per equipment type from `equipment_sensor_readings` in Supabase.

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| site_id | string | No | Filter by site ID (default: all sites) |

**Response:**
```json
{
  "site_id": "all",
  "equipment_types": {
    "chiller": {
      "available_hours": 1200,
      "ready_for_lstm": true,
      "ready_for_autoencoder": true,
      "min_lstm_hours": 500,
      "min_autoencoder_hours": 200
    },
    "ahu": {
      "available_hours": 45,
      "ready_for_lstm": false,
      "ready_for_autoencoder": false,
      "min_lstm_hours": 500,
      "min_autoencoder_hours": 200
    }
  },
  "ready_for_lstm_training": 1,
  "ready_for_autoencoder_training": 1,
  "total_types": 7
}
```

## Retrain History

### GET `/api/ml-retraining/history`

**Response:**
```json
{
  "history": [
    {
      "model_id": "lstm_chiller",
      "model_type": "lstm",
      "equipment_type": "chiller",
      "triggered_at": "2026-02-06T15:00:00",
      "reason": "auto_stale",
      "success": true,
      "new_model_id": "lstm_chiller_20260206_150000",
      "metrics": {"mae_24h": 0.42, "r2_24h": 0.84, "mae_avg": 0.51, "r2_avg": 0.78},
      "error": null
    }
  ]
}
```

## Performance Evaluation

### GET `/api/ml-retraining/performance`

Evaluate prediction accuracy against actual outcomes.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| days_back | int | 7 | Evaluation period |
| building_code | string | site-002 | Building to evaluate |

**Response:**
```json
{
  "evaluated_at": "2026-02-06T15:00:00",
  "period_days": 7,
  "building_code": "site-002",
  "predictions_count": 5,
  "alerts_count": 3,
  "metrics": {
    "accuracy": 0.85,
    "precision": 0.75,
    "recall": 0.90,
    "f1_score": 0.818
  },
  "confusion_matrix": {
    "true_positives": 3,
    "false_positives": 1,
    "false_negatives": 0,
    "true_negatives": 16
  }
}
```

### GET `/api/ml-retraining/performance/health`

Model health summary across all active models.

**Response:**
```json
{
  "summary": {
    "total_model_slots": 14,
    "fresh": 10,
    "stale": 2,
    "missing": 2,
    "underperforming": 0,
    "health_pct": 71.4
  },
  "latest_evaluation": { ... },
  "models": [ ... ],
  "evaluated_at": "2026-02-06T15:00:00"
}
```

### GET `/api/ml-retraining/performance/trend`

Recent performance evaluation history.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| limit | int | 10 | Number of evaluations |

**Response:**
```json
{
  "evaluations": [ ... ]
}
```

## A/B Testing

### POST `/api/ml-retraining/ab-test/create`

Create a new A/B test between the current active model and a candidate.

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| model_type | string | Yes | Model type |
| equipment_type | string | Yes | Equipment type |
| candidate_model_id | string | Yes | ID of candidate model to test |

**Response:**
```json
{
  "success": true,
  "test_id": "ab_0001",
  "control_model_id": "lstm_chiller_20260105_120000",
  "candidate_model_id": "lstm_chiller_20260206_150000",
  "traffic_split": "90% control / 10% candidate"
}
```

### GET `/api/ml-retraining/ab-test/{test_id}`

Evaluate test results.

**Response:**
```json
{
  "test_id": "ab_0001",
  "status": "running",
  "model_type": "lstm",
  "equipment_type": "chiller",
  "control": {
    "model_id": "lstm_chiller_20260105_120000",
    "assignments": 90,
    "metrics": {"accuracy": 0.82}
  },
  "candidate": {
    "model_id": "lstm_chiller_20260206_150000",
    "assignments": 10,
    "metrics": {"accuracy": 0.88}
  },
  "winner": "candidate",
  "created_at": "2026-02-06T15:00:00"
}
```

### POST `/api/ml-retraining/ab-test/{test_id}/promote`

Promote the candidate model to active in the registry.

**Response:**
```json
{
  "success": true,
  "test_id": "ab_0001",
  "promoted_model_id": "lstm_chiller_20260206_150000",
  "previous_model_id": "lstm_chiller_20260105_120000"
}
```

### GET `/api/ml-retraining/ab-tests`

List all A/B tests.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| status | string | null | Filter: `running`, `completed`, `promoted`, `cancelled` |

**Response:**
```json
{
  "tests": [
    {
      "test_id": "ab_0001",
      "model_type": "lstm",
      "equipment_type": "chiller",
      "control_model_id": "...",
      "candidate_model_id": "...",
      "status": "promoted",
      "created_at": "2026-02-06T15:00:00",
      "completed_at": "2026-02-07T15:00:00",
      "control_assignments": 90,
      "candidate_assignments": 10,
      "winner": "candidate"
    }
  ]
}
```
