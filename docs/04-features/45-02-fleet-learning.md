---
title: "Fleet Learning & Cross-Site Insights"
type: "spec"
status: "approved"
version: "1.0.0"
created: "2026-02-06"
updated: "2026-02-06"
author: "Sentinel Development Team"
tags: ["ml", "fleet-learning", "cross-site", "global-model", "fine-tuning", "privacy"]
domain: "general"
audience: "developers"
complexity: "advanced"
estimated_read_time: 10
---

# Phase 45-02: Fleet Learning & Cross-Site Insights

Privacy-first anonymized failure pattern aggregation across sites, global model training with local fine-tuning, and fleet-wide benchmarking.

## Overview

Fleet Learning enables SENTINEL to learn from equipment failures across all managed sites without exposing site-specific data. Failure patterns are anonymized and aggregated, global models are trained on fleet-wide data, and each site can fine-tune global models for 3-8% accuracy improvement.

## Architecture

```
+------------------+     +---------------------+     +-------------------+
| Site A Data      |---->|                     |     | Global Model      |
+------------------+     |  FleetAggregator    |---->| Trainer           |
| Site B Data      |---->|  (anonymized)       |     | (fleet-wide)      |
+------------------+     |                     |     +-------------------+
| Site C Data      |---->|                     |             |
+------------------+     +---------------------+             v
                                                      +-------------------+
                                                      | LocalFineTuner    |
                                                      | (per-site 3-8%    |
                                                      |  improvement)     |
                                                      +-------------------+
```

## Components

### FleetAggregator

**File:** `backend/ml/fleet/aggregator.py`

Anonymized cross-site failure pattern collection:
- Strips site identifiers, retains equipment type + failure patterns
- Aggregates failure frequencies, mean time between failures
- Risk distribution analysis across fleet
- Privacy-first: no raw site data shared

### GlobalModelTrainer

**File:** `backend/ml/fleet/global_model.py`

Fleet-wide model training:
- Trains on aggregated fleet data across all sites
- Supports LSTM and autoencoder model types
- Tracks training history with metrics (R2, RMSE, MAE)
- Comparison against local models

### LocalFineTuner

**File:** `backend/ml/fleet/fine_tuning.py`

Site-specific model fine-tuning:
- Takes global model as starting point
- Fine-tunes with site-local data
- Achieves 3-8% R2 improvement over global baseline
- Tracks improvement history per site

## API Endpoints

All endpoints under `/api/fleet/`:

| Method | Path | Description |
|--------|------|-------------|
| GET | `/summary` | Fleet-wide summary statistics |
| GET | `/failure-patterns` | Anonymized failure patterns |
| GET | `/similar-failures` | Find similar failures across fleet |
| GET | `/risk-distribution` | Fleet-wide risk distribution |
| GET | `/benchmarks` | Fleet benchmarking data |
| GET | `/benchmark-site` | Compare site vs fleet average |
| GET | `/global-models` | List global fleet models |
| POST | `/global-models/train` | Train global model |
| GET | `/global-models/compare` | Compare global vs local |
| GET | `/global-models/history` | Training history |
| GET | `/fine-tuned` | List fine-tuned models |
| POST | `/fine-tune` | Fine-tune model for site |
| GET | `/fine-tuned/improvement` | Fine-tuning improvement summary |
| GET | `/fine-tuned/history` | Fine-tuning operation history |

See [Fleet Learning API Reference](../03-api-reference/fleet-learning-api.md) for full details.

## Privacy Design

- **Anonymization:** Site codes stripped before aggregation
- **No raw data sharing:** Only failure patterns and aggregate metrics
- **Exclude parameter:** `/similar-failures?exclude_site=S002` prevents self-matching
- **Aggregate only:** Global models trained on pooled patterns, never raw readings

## Frontend

**File:** `frontend/src/components/FleetInsights.tsx`

Dashboard showing:
- Fleet summary statistics (sites, equipment, patterns)
- Failure pattern browser with equipment type filter
- Site benchmarking comparison
- Global model training controls
- Fine-tuning results and improvement metrics

## Testing

```bash
pytest tests/ml/test_fleet_learning.py -v  # 31 tests
```
