from app.services.prediction_taxonomy import (
    normalize_prediction_confidence,
    normalize_prediction_severity,
    normalize_prediction_urgency,
)


def test_normalize_prediction_severity_canonical_values():
    assert normalize_prediction_severity("critical") == "critical"
    assert normalize_prediction_severity("warning") == "warning"
    assert normalize_prediction_severity("healthy") == "healthy"


def test_normalize_prediction_severity_legacy_values():
    assert normalize_prediction_severity("high") == "warning"
    assert normalize_prediction_severity("medium") == "warning"
    assert normalize_prediction_severity("low") == "healthy"


def test_normalize_prediction_severity_input_variants():
    assert normalize_prediction_severity("  HIGH ") == "warning"
    assert normalize_prediction_severity(" LoW") == "healthy"
    assert normalize_prediction_severity(None) is None
    assert normalize_prediction_severity("unknown") is None


def test_normalize_prediction_confidence_values():
    assert normalize_prediction_confidence("high") == "high"
    assert normalize_prediction_confidence("medium") == "medium"
    assert normalize_prediction_confidence("low") == "low"
    assert normalize_prediction_confidence("unknown") is None


def test_normalize_prediction_urgency_values():
    assert normalize_prediction_urgency("immediate") == "critical"
    assert normalize_prediction_urgency("soon") == "warning"
    assert normalize_prediction_urgency("scheduled") == "healthy"
    assert normalize_prediction_urgency("high") == "critical"
    assert normalize_prediction_urgency("low") == "healthy"
