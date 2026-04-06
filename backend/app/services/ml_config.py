"""ML gate thresholds and trust weight scaling constants.

Centralised so that 08A (anomaly scoring) and 08B (blended health score)
share the same constants and formula — no magic numbers scattered across files.
"""

# ── Training gates ────────────────────────────────────────────────────────────
MIN_LSTM_TRAINING_HOURS = 500     # ~3 weeks before LSTM can train
MIN_ANOMALY_TRAINING_HOURS = 72   # ~3 days before Isolation Forest can train
MIN_ENERGY_TRAINING_HOURS = 720   # ~30 days before energy baseline can train
MIN_ANOMALY_SCORING_HOURS = 24   # Start scoring from 24h (sparse but valid)

# ── Trust weight scaling (for 08B — blended health score) ─────────────────────
ML_TRUST_WEIGHT_MIN = 0.30        # ML contribution at 72h
ML_TRUST_WEIGHT_MAX = 0.80        # ML contribution at 2000h+
ML_TRUST_SCALE_HOURS = 2000       # Hours at which max trust is reached

# ── Anomaly alert thresholds ────────────────────────────────────────────────────
ANOMALY_ALERT_THRESHOLD_MIN = 0.87   # Conservative at 72h
ANOMALY_ALERT_THRESHOLD_MAX = 0.75   # Standard at 2000h+


def get_ml_trust_weight(ml_hours_ingested: float) -> float:
    """Linearly scales ML trust from 30% at 72h to 80% at 2000h.

    Below 72h (MIN_ANOMALY_TRAINING_HOURS) the model is not yet trained,
    so ML contribution is 0.
    """
    if ml_hours_ingested < MIN_ANOMALY_TRAINING_HOURS:
        return 0.0
    t = min(ml_hours_ingested / ML_TRUST_SCALE_HOURS, 1.0)
    return ML_TRUST_WEIGHT_MIN + t * (ML_TRUST_WEIGHT_MAX - ML_TRUST_WEIGHT_MIN)


def get_anomaly_alert_threshold(ml_hours_ingested: float) -> float:
    """Graduated alert threshold: conservative at 72h, standard at 2000h+.

    At 72h   → 0.87  (conservative — sparse data, noisy model)
    At 500h  → 0.812 (transitional)
    At 2000h → 0.75  (standard — rich data, calibrated model)
    """
    t = min(ml_hours_ingested / ML_TRUST_SCALE_HOURS, 1.0)
    return ANOMALY_ALERT_THRESHOLD_MIN + t * (ANOMALY_ALERT_THRESHOLD_MAX - ANOMALY_ALERT_THRESHOLD_MIN)
