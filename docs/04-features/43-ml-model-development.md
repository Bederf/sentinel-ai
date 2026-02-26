---
status: implemented
version: 43-02
date: 2026-02-26
---

# Phase 43: ML Model Development

## Overview

Phase 43 implements machine learning capabilities for equipment monitoring:

1. **LSTM Time-Series Forecasting** - Predict sensor values 24/48/72 hours ahead
2. **Autoencoder Anomaly Detection** - Detect unusual equipment behavior

## Architecture

```
backend/ml/
├── __init__.py           # Package documentation
├── registry.py           # Model versioning and management
├── requirements.txt      # ML dependencies (tensorflow, sklearn, etc.)
├── models/               # Saved models
│   ├── lstm/            # LSTM model files (.h5, _scaler.joblib)
│   ├── autoencoder/     # Autoencoder model files
│   ├── classifier/      # Random Forest classifier files (.joblib)
│   └── registry.json    # Model registry
├── data/                 # Real data loading from Supabase
│   ├── __init__.py
│   └── supabase_loader.py  # SupabaseTrainingDataLoader
├── lstm/
│   ├── __init__.py
│   ├── data_prep.py     # Training data preparation
│   ├── model.py         # LSTM architecture (128-64-32)
│   └── train.py         # Training pipeline
├── autoencoder/
│   ├── __init__.py
│   ├── data_prep.py     # Normal data preparation
│   ├── model.py         # LSTM autoencoder
│   └── train.py         # Training pipeline
└── classifier/
    ├── __init__.py
    ├── data_prep.py     # Failure-labeled data prep + synthetic generation
    ├── model.py         # Random Forest multi-class classifier
    └── train.py         # Training pipeline with registry integration
```

## LSTM Forecasting

### Model Architecture

- **Input**: 168 timesteps (7 days hourly) × N features
- **LSTM Layers**: 128 → 64 → 32 units with BatchNorm and Dropout
- **Output**: 3 values (24h, 48h, 72h predictions)
- **Loss**: MSE with L2 regularization
- **Optimizer**: Adam with ReduceLROnPlateau

### Equipment Configurations

| Equipment | Features | Target |
|-----------|----------|--------|
| Chiller | chw_supply_temp, chw_return_temp, suction_pressure, discharge_pressure, compressor_current | chw_supply_temp |
| AHU | supply_temp, return_temp, filter_dp, fan_current, mixed_air_temp | supply_temp |
| Generator | battery_voltage, oil_pressure, coolant_temp, load_pct | coolant_temp |
| FCU | supply_temp, fan_current, valve_position | supply_temp |
| UPS | battery_voltage, load_pct, temperature | temperature |

### Training

```bash
# Train single equipment type (tries real Supabase data first, falls back to demo)
cd backend
python -m ml.lstm.train --equipment-type chiller --epochs 50

# Train all equipment types
python -m ml.lstm.train --all --epochs 50

# Force synthetic demo data (skip Supabase)
python -m ml.lstm.train --all --epochs 50 --demo-data

# Force real data only (fail if insufficient)
python -m ml.lstm.train --equipment-type chiller --epochs 50 --real-data
```

### API Usage

```bash
# Get predictions
curl "http://localhost:9095/api/ml/predictions/lstm/chiller-001?equipment_type=chiller"

# Get trend data for visualization
curl "http://localhost:9095/api/ml/predictions/trend/chiller-001?equipment_type=chiller"
```

Response:
```json
{
  "equipment_id": "chiller-001",
  "equipment_type": "chiller",
  "predictions": {
    "24h": 12.5,
    "48h": 12.8,
    "72h": 13.1
  },
  "confidence": 0.85,
  "timestamp": "2026-01-31T10:00:00Z"
}
```

## Autoencoder Anomaly Detection

### Concept

Autoencoders learn to compress and reconstruct "normal" operation patterns. When presented with anomalous data, they fail to reconstruct it accurately, resulting in high reconstruction error.

**Key Principle**: Train ONLY on normal data. Exclude failure periods.

### Model Architecture

- **Encoder**: LSTM(64) → LSTM(32) → Dense(16) (latent space)
- **Decoder**: RepeatVector → LSTM(32) → LSTM(64) → Dense(N)
- **Threshold**: 99th percentile of validation reconstruction errors

### Training

```bash
# Train single equipment type (tries real Supabase data first, falls back to demo)
cd backend
python -m ml.autoencoder.train --equipment-type chiller --epochs 50

# Train all equipment types
python -m ml.autoencoder.train --all --epochs 50

# Force synthetic demo data (skip Supabase)
python -m ml.autoencoder.train --all --epochs 50 --demo-data

# Force real data only (fail if insufficient)
python -m ml.autoencoder.train --equipment-type chiller --epochs 50 --real-data
```

### API Usage

```bash
# Check single equipment
curl "http://localhost:9095/api/ml/anomalies/equipment/chiller-001?equipment_type=chiller"

# Get all anomaly alerts
curl "http://localhost:9095/api/ml/anomalies/alerts"

# Get anomaly score history
curl "http://localhost:9095/api/ml/anomalies/history/chiller-001?equipment_type=chiller&days=7"
```

Response:
```json
{
  "equipment_id": "chiller-001",
  "equipment_type": "chiller",
  "is_anomaly": false,
  "anomaly_score": 0.00042,
  "threshold": 0.00068,
  "score_pct": 61.7,
  "severity": "normal",
  "timestamp": "2026-01-31T10:00:00Z"
}
```

### Severity Levels

| Score/Threshold Ratio | Severity | Description |
|-----------------------|----------|-------------|
| < 0.7 | normal | Normal operation |
| 0.7 - 1.0 | warning | Approaching threshold |
| 1.0 - 1.5 | elevated | Just above threshold |
| 1.5 - 2.0 | high | Significant anomaly |
| > 2.0 | critical | Severe anomaly |

## Model Registry

The model registry tracks trained models and their metrics:

```bash
# List all models
curl "http://localhost:9095/api/ml/models"

# Get specific model
curl "http://localhost:9095/api/ml/models/lstm_chiller_20260131_100000"

# Activate a model
curl -X POST "http://localhost:9095/api/ml/models/lstm_chiller_20260131_100000/activate"

# Compare model versions
curl "http://localhost:9095/api/ml/models/compare/lstm/chiller"
```

## Training via API

```bash
# Train LSTM model
curl -X POST "http://localhost:9095/api/ml/train/lstm/chiller" \
  -H "Content-Type: application/json" \
  -d '{"epochs": 50, "use_demo_data": true}'

# Train autoencoder
curl -X POST "http://localhost:9095/api/ml/train/autoencoder/chiller" \
  -H "Content-Type: application/json" \
  -d '{"epochs": 50, "use_demo_data": true}'

# Train all models
curl -X POST "http://localhost:9095/api/ml/train/all" \
  -H "Content-Type: application/json" \
  -d '{"epochs": 50, "use_demo_data": true}'
```

## Dependencies

Install ML dependencies:

```bash
cd backend
pip install -r ml/requirements.txt
```

Required packages:
- TensorFlow 2.x
- scikit-learn
- pandas
- numpy
- joblib

## Integration with Inference Service

```python
from app.services.ml_inference import get_lstm_service, get_anomaly_service

# LSTM predictions
lstm = get_lstm_service()
prediction = lstm.predict("chiller-001", "chiller")
print(f"24h forecast: {prediction['predictions']['24h']}")

# Anomaly detection
anomaly = get_anomaly_service()
result = anomaly.check_equipment("chiller-001", "chiller")
if result["is_anomaly"]:
    print(f"ANOMALY: score={result['anomaly_score']:.4f}")
```

## Data Requirements

### Real Data Source

Training data is loaded from the `equipment_sensor_readings` Supabase table via `SupabaseTrainingDataLoader` (`ml/data/supabase_loader.py`). This table is populated hourly by `SimulationPersistence` during lifecycle simulation or by real BMS data ingestion.

The loader:
1. Queries `equipment_sensor_readings` filtered by equipment code pattern (e.g., `%-CHILLER-%`)
2. Maps BMS sensor names to ML feature names via `SENSOR_MAPPING` from `sentinel_ml_feeder.py`
3. Pivots long-format rows (one row per sensor reading) into wide-format (one row per hour with all features as columns)
4. Falls back to synthetic demo data if insufficient real data is available

```bash
# Check available training data per equipment type
curl "http://localhost:9095/api/ml-retraining/training-data"
```

### LSTM
- Minimum 500 hours of hourly sensor data (from `equipment_sensor_readings`)
- 168+ hours of continuous data for single prediction
- Looks back up to 365 days for training data

### Autoencoder
- Minimum 200 hours of normal operation data
- Creates 24-hour sliding windows from hourly data
- Looks back up to 365 days for training data

## Random Forest Fault Classification (v25.0)

### Overview

When an anomaly is detected, the classifier identifies the **specific failure type** (compressor failure, refrigerant leak, etc.) using a Random Forest ensemble trained on failure-labeled data.

**Pipeline:** Anomaly detected → Fault classified → Actionable diagnosis

### Model Architecture

- **Algorithm**: Random Forest (scikit-learn)
- **Trees**: 100 estimators, max depth 10
- **Class weighting**: Balanced (handles imbalanced failure types)
- **Output**: Multi-class probabilities for each failure type + "normal"

### Failure Types Per Equipment

| Equipment | Failure Classes |
|-----------|----------------|
| Chiller | compressor_failure, refrigerant_leak, condenser_fouling, oil_issue, electrical, normal |
| AHU | fan_motor, belt_failure, coil_fouling, damper_actuator, filter_blockage, normal |
| Generator | battery_failure, fuel_system, starter_motor, alternator, cooling_system, normal |
| FCU | fan_motor, valve_actuator, thermostat, filter_blockage, normal |
| UPS | battery_failure, inverter, capacitor, overload, normal |

### Training

```bash
# Train single equipment type
cd backend
python -m ml.classifier.train --equipment-type chiller

# Train all equipment types (~5-10 seconds total)
python -m ml.classifier.train --all
```

### API Usage

```bash
# Train classifier via API
curl -X POST "http://localhost:9095/api/ml/train/classifier/chiller"

# Classification happens automatically during anomaly check
curl "http://localhost:9095/api/ml/anomalies/equipment/S002-CHILLER-B1-001?equipment_type=chiller"
# If anomaly detected, response includes fault_classification field

# Direct classification endpoint (7 endpoints at /api/classification)
curl "http://localhost:9095/api/classification/failure-type/S002-CHILLER-B1-001"
```

Response (when anomaly detected):
```json
{
  "is_anomaly": true,
  "fault_classification": {
    "predicted_failure": "compressor_failure",
    "confidence": 0.72,
    "all_probabilities": {"compressor_failure": 0.72, "refrigerant_leak": 0.12, ...},
    "contributing_factors": [{"feature": "avg_temp", "importance": 0.15}]
  }
}
```

### Integration with Inference

```python
from app.services.classification_service import get_classification_service

classifier = get_classification_service()
result = classifier.predict_failure_type("S002-CHILLER-B1-001")
print(f"Predicted: {result['predicted_failure']} ({result['confidence']:.0%})")
```

### Service Layer

- **ClassifierDataPrep** (`ml/classifier/data_prep.py`): Generates labeled training data from work orders or synthetic fallback
- **FailureClassifier** (`ml/classifier/model.py`): Random Forest with cross-validation, feature importance, prediction explanation
- **ClassifierTrainer** (`ml/classifier/train.py`): Training pipeline with model registry integration
- **FailureClassificationService** (`app/services/classification_service.py`): Singleton inference service with lazy model loading

## Current Limitations

1. **Single Feature Target**: LSTM predicts single target per model
2. **Fixed Window Sizes**: 168h (LSTM), 24h (autoencoder)
3. **Classifier uses synthetic data**: Real failure labels from CAFM will improve accuracy
4. **Real data requires simulation**: The `equipment_sensor_readings` table must be populated by running lifecycle simulation or connecting to real BMS

## Future Enhancements

- Multi-variate prediction
- Attention mechanisms
- Transfer learning between equipment types
- CAFM failure label integration for classifier training
- Real-time incremental learning from streaming sensor data
