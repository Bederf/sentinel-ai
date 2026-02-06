---
title: "Fleet Learning API Reference"
type: "reference"
status: "approved"
version: "1.0.0"
created: "2026-02-06"
updated: "2026-02-06"
author: "Sentinel Development Team"
tags: ["api", "fleet-learning", "global-model", "fine-tuning", "benchmarking"]
domain: "general"
audience: "developers"
complexity: "advanced"
estimated_read_time: 10
---

# Fleet Learning API Reference

Phase 45-02 Fleet Learning endpoints. Cross-site failure patterns, global model training, local fine-tuning, and fleet benchmarking.

Base path: `/api/fleet`

## Fleet Overview

### GET `/api/fleet/summary`

Fleet-wide summary statistics (sites, equipment count, failure patterns, model count).

### GET `/api/fleet/risk-distribution`

Equipment risk distribution across the fleet.

## Failure Patterns

### GET `/api/fleet/failure-patterns`

Anonymized failure patterns aggregated across all sites.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| equipment_type | string | null | Filter by equipment type |

**Response:**
```json
{
  "patterns": [
    {
      "equipment_type": "chiller",
      "failure_type": "compressor_overload",
      "frequency": 12,
      "mean_time_between_failures_days": 180,
      "common_precursors": ["high_current", "vibration_increase"]
    }
  ],
  "total": 45
}
```

### GET `/api/fleet/similar-failures`

Find similar equipment failures across the fleet.

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| equipment_type | string | Yes | Equipment type |
| failure_type | string | No | Specific failure type |
| exclude_site | string | No | Exclude site for privacy |

## Benchmarking

### GET `/api/fleet/benchmarks`

Fleet benchmarking data for equipment types.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| equipment_type | string | null | Filter by type |

### GET `/api/fleet/benchmark-site`

Compare a site's performance against fleet average.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| site_code | string | Yes | Site to benchmark |
| site_health | float | Yes | Site's current health score |
| equipment_type | string | No | Filter comparison |

**Response:**
```json
{
  "site_code": "S002",
  "site_health": 82.5,
  "fleet_average": 78.3,
  "percentile": 72,
  "ranking": "above_average"
}
```

## Global Models

### GET `/api/fleet/global-models`

List trained global fleet models.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| model_type | string | null | Filter: lstm, autoencoder |
| equipment_type | string | null | Filter by equipment type |

### POST `/api/fleet/global-models/train`

Train a global model on aggregated fleet data.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| model_type | string | Yes | Model type |
| equipment_type | string | Yes | Equipment type |

**Response:**
```json
{
  "success": true,
  "model_id": "global_lstm_chiller_20260206",
  "sites_included": 5,
  "samples_used": 1250,
  "metrics": {"r2": 0.81, "rmse": 2.3, "mae": 1.8}
}
```

### GET `/api/fleet/global-models/compare`

Compare global vs local model performance.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| model_type | string | Yes | Model type |
| equipment_type | string | Yes | Equipment type |
| local_r2 | float | Yes | Local model R2 score |

### GET `/api/fleet/global-models/history`

Global model training history.

## Fine-Tuning

### GET `/api/fleet/fine-tuned`

List fine-tuned models. Filter by `site_code`, `model_type`, `equipment_type`.

### POST `/api/fleet/fine-tune`

Fine-tune a global model for a specific site.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| site_code | string | Yes | Target site |
| model_type | string | Yes | Model type |
| equipment_type | string | Yes | Equipment type |

**Response:**
```json
{
  "success": true,
  "model_id": "ft_lstm_chiller_S002_20260206",
  "site_code": "S002",
  "global_metrics": {"r2": 0.81},
  "fine_tuned_metrics": {"r2": 0.86},
  "improvement": 0.05,
  "samples_used": 250
}
```

### GET `/api/fleet/fine-tuned/improvement`

Summary of fine-tuning improvements. Filter by `site_code`.

### GET `/api/fleet/fine-tuned/history`

Fine-tuning operation history. Filter by `site_code`.
