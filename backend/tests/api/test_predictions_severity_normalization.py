from app.api.predictions import _normalize_prediction_severity


def test_normalize_prediction_severity_canonical_values():
    assert _normalize_prediction_severity("critical") == "critical"
    assert _normalize_prediction_severity("warning") == "warning"
    assert _normalize_prediction_severity("healthy") == "healthy"


def test_normalize_prediction_severity_legacy_values():
    assert _normalize_prediction_severity("high") == "warning"
    assert _normalize_prediction_severity("medium") == "warning"
    assert _normalize_prediction_severity("low") == "healthy"


def test_normalize_prediction_severity_input_variants():
    assert _normalize_prediction_severity("  HIGH ") == "warning"
    assert _normalize_prediction_severity(" LoW") == "healthy"
    assert _normalize_prediction_severity(None) is None
    assert _normalize_prediction_severity("unknown") is None
