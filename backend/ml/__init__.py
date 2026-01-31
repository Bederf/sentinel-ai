"""
SENTINEL BMS ML Package - Machine Learning for Equipment Monitoring.

Phase 43: ML Model Development
- LSTM time-series forecasting (24/48/72h predictions)
- Autoencoder anomaly detection (normal vs abnormal operation)

Usage:
    # Train models
    python -m ml.lstm.train --all --epochs 50
    python -m ml.autoencoder.train --all --epochs 50

    # Use in application
    from app.services.ml_inference import get_lstm_service, get_anomaly_service

    lstm = get_lstm_service()
    prediction = lstm.predict("chiller-001", "chiller")

    anomaly = get_anomaly_service()
    result = anomaly.check_equipment("chiller-001", "chiller")

API Endpoints:
    GET /api/ml/predictions/lstm/{equipment_id}
    GET /api/ml/anomalies/equipment/{equipment_id}
    GET /api/ml/anomalies/alerts
    GET /api/ml/models
    POST /api/ml/train/lstm/{equipment_type}
    POST /api/ml/train/autoencoder/{equipment_type}
"""

__version__ = "1.0.0"
