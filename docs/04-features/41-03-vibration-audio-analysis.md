---
title: "Vibration & Audio Analysis via phyphox"
type: "spec"
status: "approved"
version: "1.0.0"
created: "2026-02-06"
updated: "2026-02-06"
author: "Sentinel Development Team"
tags: ["ml", "vibration", "audio", "phyphox", "condition-monitoring", "bearing-analysis"]
domain: "bms"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 8
---

# Phase 41-03: Vibration & Audio Analysis via phyphox

Mobile sensor data ingestion and anomaly detection for equipment condition monitoring using phyphox smartphone sensors.

## Overview

Technicians use the phyphox app on their smartphones to record vibration and audio data from equipment in the field. SENTINEL ingests this data (screenshots, CSV, or JSON), runs anomaly detection algorithms, and produces condition scores that feed into the ML training pipeline.

## Architecture

```
+------------------+     +---------------------+     +-------------------+
| phyphox App      |---->| PhyphoxHandler      |---->| Anomaly Suite     |
| (smartphone)     |     | (screenshot/CSV/JSON)|    | (bearing, knock,  |
+------------------+     +---------------------+     |  baseline, scorer) |
                                                      +-------------------+
                                                              |
                                                              v
                                                      +-------------------+
                                                      | Condition API     |
                                                      | /api/condition/*  |
                                                      +-------------------+
```

## Components

### PhyphoxHandler

**File:** `backend/app/services/clawd_integration/phyphox_handler.py`

Ingests phyphox data in multiple formats:
- **Screenshot analysis** — Claude Vision extracts values from phyphox app screenshots
- **CSV parsing** — Direct CSV export from phyphox with time-series columns
- **JSON parsing** — phyphox native JSON export format

### Bearing Defect Analyzer

**File:** `backend/app/services/bearing_analyzer.py` (via condition service)

Detects bearing defects from vibration data:
- RMS velocity analysis against ISO 10816 thresholds
- Frequency domain analysis (FFT) for characteristic defect frequencies
- BPFO, BPFI, BSF, FTF calculation from bearing geometry
- Severity classification: normal, marginal, warning, critical

### Engine Knock Detector

**File:** `backend/app/services/knock_detector.py`

Detects engine knock from audio recordings:
- Peak amplitude detection
- Frequency band analysis for knock signatures
- Repetition pattern matching

### Baseline Comparator

**File:** `backend/app/services/baseline_comparator.py`

Compares current readings against established baselines:
- Per-equipment baseline profiles
- Deviation percentage calculation
- Trend direction detection (improving, stable, degrading)
- R-squared confidence scoring

### Condition Scorer

Aggregates all analysis into a single condition score (0-100):
- Weighted combination of vibration, audio, and visual indicators
- Equipment-type-specific weighting profiles
- Health impact calculation for equipment health score updates

## API Endpoints

All endpoints under `/api/condition/`:

| Method | Path | Description |
|--------|------|-------------|
| GET | `/trends/{equipment_id}` | Trend analysis for all monitored elements |
| GET | `/trends/{equipment_id}/{element_name}` | Detailed trend for specific element |
| GET | `/degradation-rates/{equipment_id}` | Degradation rates for all elements |
| POST | `/analyze-changes` | Full trend analysis |
| GET | `/rul/{equipment_id}` | Remaining Useful Life prediction |
| GET | `/recommendations/{equipment_id}` | Prioritized service recommendations |
| GET | `/fleet-risk` | Fleet-wide RUL risk overview |
| POST | `/optimize-service-schedule` | Optimize fleet service schedule |
| GET | `/utilization/{equipment_id}` | Asset utilization metrics |
| GET | `/cost-comparison/{equipment_id}` | Fixed vs condition-based cost comparison |

See [Condition API Reference](../03-api-reference/condition-api.md) for full details.

## Database Schema

Sensor analysis results stored in Supabase `sensor_readings` table with:
- `equipment_id` — linked to equipment registry
- `sensor_type` — vibration_rms, vibration_fft, audio_db, temperature, etc.
- `value`, `unit`, `timestamp`
- `tags` — metadata (source: phyphox, analysis_type, etc.)

## Integration with ML Pipeline

Condition data feeds into:
1. **Feature Store** (Phase 42) — vibration/audio features for ML training
2. **LSTM Forecasting** (Phase 43) — sensor trend prediction
3. **Anomaly Detection** (Phase 43) — autoencoder baseline comparison
4. **Service Feedback** (Phase 41-01) — technician field measurements

## Testing

```bash
pytest tests/services/test_condition_analysis.py -v
```
