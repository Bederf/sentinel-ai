"""Phase D baseline gate: baseline_state pass-through + service-interval request contract."""

import pytest
from pydantic import ValidationError

from app.api.equipment_metadata import ServiceIntervalRequest
from app.api.predictions import format_prediction_for_frontend


def _pred(equipment: dict) -> dict:
    return {
        "id": "uuid-1",
        "code": "pred-auto-abc123",
        "site_id": "site-uuid",
        "equipment_id": "eq-uuid",
        "severity": "warning",
        "prediction_type": "bearing_failure",
        "probability_percent": 62,
        "confidence": "medium",
        "predicted_failure_date": "2026-07-19T00:00:00",
        "timeframe_days": 14,
        "status": "active",
        "evidence": {},
        "contributing_factors": [],
        "similar_failures": [],
        "building": {"id": "b", "name": "B", "code": "site-002"},
        "equipment": equipment,
    }


def test_baseline_state_passed_through():
    formatted = format_prediction_for_frontend(
        _pred(
            {"id": "eq", "code": "S002-PUMP-B1-001", "name": "Pump", "type": "pump", "baseline_state": "rolling_active"}
        )
    )
    assert formatted["baseline_state"] == "rolling_active"


def test_baseline_state_defaults_to_none():
    formatted = format_prediction_for_frontend(
        _pred({"id": "eq", "code": "S002-PUMP-B1-001", "name": "Pump", "type": "pump"})
    )
    assert formatted["baseline_state"] == "none"


def test_baseline_state_null_defaults_to_none():
    formatted = format_prediction_for_frontend(
        _pred({"id": "eq", "code": "S002-PUMP-B1-001", "name": "Pump", "type": "pump", "baseline_state": None})
    )
    assert formatted["baseline_state"] == "none"


def test_service_interval_accepts_valid_range():
    assert ServiceIntervalRequest(service_interval_days=7).service_interval_days == 7
    assert ServiceIntervalRequest(service_interval_days=365).service_interval_days == 365


def test_service_interval_accepts_null_to_clear_override():
    assert ServiceIntervalRequest(service_interval_days=None).service_interval_days is None


def test_service_interval_rejects_out_of_range():
    with pytest.raises(ValidationError):
        ServiceIntervalRequest(service_interval_days=0)
    with pytest.raises(ValidationError):
        ServiceIntervalRequest(service_interval_days=366)
