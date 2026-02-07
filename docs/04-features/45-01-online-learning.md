---
title: "Online Learning & Automated Retraining"
type: "spec"
status: "approved"
version: "1.0.0"
created: "2026-02-06"
updated: "2026-02-06"
author: "Sentinel Development Team"
tags: ["ml", "retraining", "online-learning", "ab-testing", "monitoring"]
domain: "general"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 10
---

# Phase 45-01: Online Learning & Automated Retraining

Closes the feedback loop between ML predictions and real-world outcomes by monitoring model accuracy, auto-retraining stale models, and A/B testing new model versions before promotion.

## Overview

The system continuously evaluates prediction quality against actual alerts and faults. When models degrade (staleness or poor accuracy), automated retraining kicks in. New model versions are validated through controlled A/B experiments before replacing production models.

## Architecture

```
+-------------------+     +------------------------+     +------------------+
| Prediction Repo   |---->| PerformanceMonitor     |---->| Health Dashboard  |
| Alert Repo        |     | (accuracy/F1/recall)   |     | /api/ml-retrain  |
+-------------------+     +------------------------+     +------------------+
                                    |
                                    v
                          +--------------------+
                          | RetrainingScheduler |
                          | (daily cron check)  |
                          +--------------------+
                                    |
                                    v
                          +--------------------+
                          |  ABTestManager     |
                          | (10% candidate)    |
                          +--------------------+
                                    |
                                    v
                          +--------------------+
                          |  ModelRegistry     |
                          |  (promote winner)  |
                          +--------------------+
```

## Components

### RetrainingScheduler

**File:** `backend/ml/training/retraining_scheduler.py`

Monitors model freshness and triggers retraining:
- **Staleness check:** Models older than 30 days flagged for retraining
- **Performance check:** Models with R2 < 0.65 flagged as underperforming
- **Auto-retrain:** Daily background job retrains first stale model found
- **Equipment types:** chiller, ahu, fcu, vav, generator, ups, pump
- **Model types:** lstm, autoencoder

### ModelPerformanceMonitor

**File:** `backend/ml/monitoring/performance_monitor.py`

Evaluates prediction accuracy against actual outcomes:
- Compares predicted equipment failures with actual alert history
- Computes accuracy, precision, recall, and F1 score
- Tracks evaluation history for trend analysis
- Provides model health summary (fresh/stale/missing/underperforming)

### ABTestManager

**File:** `backend/ml/ab_testing/ab_test_manager.py`

Controlled experiments between model versions:
- **Hash-based splitting:** 90% control / 10% candidate traffic
- **Consistent assignment:** Same equipment always gets same model within a test
- **Evaluation:** 5% improvement threshold required to declare candidate winner
- **Promotion:** Winners are promoted to active in the ModelRegistry

## API Endpoints

All endpoints under `/api/ml-retraining/`:

| Method | Path | Description |
|--------|------|-------------|
| GET | `/status` | Check all models for staleness |
| POST | `/trigger` | Trigger retraining for specific model |
| GET | `/history` | Retrain operation history |
| GET | `/performance` | Evaluate prediction accuracy |
| GET | `/performance/health` | Model health summary |
| GET | `/performance/trend` | Recent evaluation trend |
| POST | `/ab-test/create` | Create A/B test |
| GET | `/ab-test/{id}` | Evaluate test results |
| POST | `/ab-test/{id}/promote` | Promote winning model |
| GET | `/ab-tests` | List all A/B tests |

See [ML Retraining API Reference](../03-api-reference/ml-retraining-api.md) for full details.

## Background Jobs

Two scheduler jobs added to `BackgroundSchedulerService`:

1. **Model Freshness Check** (daily, 86400s)
   - Iterates all model_type x equipment_type combinations
   - Auto-retrains first stale model found per cycle
   - Avoids overload by limiting to one retrain per cycle

2. **Performance Evaluation** (hourly, 3600s)
   - Compares predictions vs actual alerts over last 7 days
   - Logs accuracy and F1 metrics
   - Results available via `/performance/trend`

## Thresholds

| Parameter | Default | Description |
|-----------|---------|-------------|
| MAX_MODEL_AGE_DAYS | 30 | Days before model considered stale |
| MIN_R2_SCORE | 0.65 | Minimum R2 to avoid retraining |
| CANDIDATE_TRAFFIC_PCT | 10 | % of traffic to A/B test candidate |
| Improvement threshold | 5% | Required improvement to promote candidate |

## Simulation Analytics Fix

This phase also fixes the simulation analytics runtime tracking. The lifecycle orchestrator now emits per-equipment `AI_OPTIMIZATION` events with `equipment_id` set, and `SETPOINT_CHANGE` events carry representative equipment context. This ensures the Asset Sweating optimization profile correctly scores runtime utilization.

## Testing

```bash
# Simulation analytics tests (4 tests)
pytest tests/services/test_simulation_analytics.py -v

# Retraining system tests (6 tests)
pytest tests/ml/test_retraining_scheduler.py -v
```
