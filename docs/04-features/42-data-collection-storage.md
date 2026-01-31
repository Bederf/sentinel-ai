---
status: implemented
version: 42-01
date: 2026-01-31
---

# Phase 42: Data Collection & Storage

## Overview

Phase 42 implements time-series data storage infrastructure for ML model training and equipment monitoring.

## InfluxDB Integration

### Service Architecture

```
backend/app/services/influxdb_service.py
```

The InfluxDB service provides:
- Automatic mock mode when InfluxDB is unavailable
- Multi-bucket retention policies
- Batch write support
- ML training data extraction

### Data Buckets

| Bucket | Retention | Resolution | Purpose |
|--------|-----------|------------|---------|
| sensor_data_raw | 7 days | 1 second | Raw readings |
| sensor_data_1m | 30 days | 1 minute | Short-term analysis |
| sensor_data_1h | 365 days | 1 hour | LSTM training |
| sensor_data_1d | 5 years | 1 day | Long-term trends |

### API Endpoints

```bash
# Write sensor data
POST /api/timeseries/write
{
  "equipment_id": "chiller-001",
  "sensor_type": "chw_supply_temp",
  "value": 12.5,
  "unit": "°C"
}

# Batch write
POST /api/timeseries/write/batch
{
  "readings": [
    {"equipment_id": "chiller-001", "sensor_type": "chw_supply_temp", "value": 12.5},
    {"equipment_id": "chiller-001", "sensor_type": "chw_return_temp", "value": 18.2}
  ]
}

# Query hourly data
GET /api/timeseries/query/hourly?equipment_id=chiller-001&sensor_type=chw_supply_temp&hours=168

# Get ML training data
GET /api/timeseries/query/ml-training?equipment_id=chiller-001&sensor_types=chw_supply_temp,chw_return_temp&days=180

# Health check
GET /api/timeseries/health
```

### Usage in Code

```python
from app.services.influxdb_service import get_influxdb_service

# Get singleton service
influx = get_influxdb_service()

# Write single reading
influx.write_sensor_data(
    equipment_id="chiller-001",
    sensor_type="chw_supply_temp",
    value=12.5,
    unit="°C"
)

# Query hourly data for LSTM
data = influx.query_hourly("chiller-001", "chw_supply_temp", hours=168)

# Get ML training data (multiple sensors)
ml_data = influx.get_ml_training_data(
    equipment_id="chiller-001",
    sensor_types=["chw_supply_temp", "chw_return_temp", "compressor_current"],
    days=180
)
```

### Mock Mode

When InfluxDB is not configured, the service automatically uses mock mode:
- Generates synthetic sensor data with realistic patterns
- Daily sinusoidal patterns with noise
- Suitable for development and testing

### Configuration

Environment variables:
```bash
INFLUXDB_URL=http://localhost:8086
INFLUXDB_TOKEN=<your-token>
INFLUXDB_ORG=bms-intelligence
```

If not configured, mock mode is automatically enabled.

## Integration with ML

Phase 42 provides the data foundation for Phase 43 ML models:

1. **LSTM Training**: Uses `query_hourly()` for 168-hour windows
2. **Autoencoder Training**: Uses `get_ml_training_data()` for feature arrays
3. **Real-time Inference**: Uses latest sensor readings for predictions

## Future Enhancements

- Downsampling tasks (InfluxDB Flux)
- Continuous queries for aggregations
- Retention policy enforcement
- Data quality checks
