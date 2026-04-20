"""Tests for PredictionOverlayService.

Validates prediction aggregation, severity classification,
empty predictions, and site filtering for the Digital Twin overlay.
"""

from unittest.mock import MagicMock

import pytest

from app.models.equipment_status import PredictiveFault
from app.services.prediction_overlay_service import (
    PredictionOverlayService,
    get_prediction_overlay_service,
)


@pytest.fixture
def service():
    """Create a fresh PredictionOverlayService for each test."""
    svc = PredictionOverlayService()
    return svc


@pytest.fixture
def mock_predictions():
    """Sample prediction data matching the prediction repository format."""
    return [
        {
            "id": "pred-001",
            "equipment_id": "eq-001",
            "site_id": "site-001",
            "prediction_type": "bearing_failure",
            "timeframe_days": 3,
            "confidence": 0.92,
            "status": "active",
            "model_name": "lstm_chiller_v2",
        },
        {
            "id": "pred-002",
            "equipment_id": "eq-002",
            "site_id": "site-001",
            "prediction_type": "motor_degradation",
            "timeframe_days": 14,
            "confidence": 0.75,
            "status": "active",
            "model_name": "lstm_ahu_v1",
        },
        {
            "id": "pred-003",
            "equipment_id": "eq-003",
            "site_id": "site-001",
            "prediction_type": "compressor_wear",
            "timeframe_days": 25,
            "confidence": 0.60,
            "status": "active",
            "model_name": "lstm_chiller_v2",
        },
    ]


@pytest.mark.asyncio
async def test_severity_classification_critical(service, mock_predictions):
    """Test that predictions within 7 days are classified as critical."""
    mock_repo = MagicMock()
    mock_repo.get_active_by_site.return_value = [mock_predictions[0]]  # 3 days
    service._repo = mock_repo

    faults = await service.get_predictions_for_site("site-001")

    assert len(faults) == 1
    assert faults[0].severity == "critical"
    assert faults[0].timeframe_days == 3


@pytest.mark.asyncio
async def test_severity_classification_warning(service, mock_predictions):
    """Test that predictions between 7 and 30 days are classified as warning."""
    mock_repo = MagicMock()
    mock_repo.get_active_by_site.return_value = [mock_predictions[1]]  # 14 days
    service._repo = mock_repo

    faults = await service.get_predictions_for_site("site-001")

    assert len(faults) == 1
    assert faults[0].severity == "warning"
    assert faults[0].timeframe_days == 14


@pytest.mark.asyncio
async def test_predictions_beyond_30_days_filtered_out(service):
    """Test that predictions beyond 30 days are excluded."""
    mock_repo = MagicMock()
    mock_repo.get_active_by_site.return_value = [
        {
            "equipment_id": "eq-004",
            "prediction_type": "filter_clog",
            "timeframe_days": 45,
            "confidence": 0.80,
            "status": "active",
        }
    ]
    service._repo = mock_repo

    faults = await service.get_predictions_for_site("site-001")

    assert len(faults) == 0


@pytest.mark.asyncio
async def test_empty_predictions(service):
    """Test handling of no predictions for a site."""
    mock_repo = MagicMock()
    mock_repo.get_active_by_site.return_value = []
    service._repo = mock_repo

    faults = await service.get_predictions_for_site("site-001")

    assert faults == []


@pytest.mark.asyncio
async def test_sorting_severity_then_confidence(service, mock_predictions):
    """Test that results sort by severity (critical first) then confidence (highest first)."""
    mock_repo = MagicMock()
    mock_repo.get_active_by_site.return_value = mock_predictions
    service._repo = mock_repo

    faults = await service.get_predictions_for_site("site-001")

    assert len(faults) == 3
    # First: critical (3 days, 0.92 confidence)
    assert faults[0].severity == "critical"
    assert faults[0].confidence == 0.92
    # Second and third: warnings sorted by confidence desc
    assert faults[1].severity == "warning"
    assert faults[1].confidence >= faults[2].confidence


@pytest.mark.asyncio
async def test_confidence_normalization_from_percentage(service):
    """Test that probability_percent (0-100) is normalized to 0-1 confidence."""
    mock_repo = MagicMock()
    mock_repo.get_active_by_site.return_value = [
        {
            "equipment_id": "eq-005",
            "prediction_type": "valve_leak",
            "timeframe_days": 10,
            "confidence": None,
            "probability_percent": 85,
            "status": "active",
        }
    ]
    service._repo = mock_repo

    faults = await service.get_predictions_for_site("site-001")

    assert len(faults) == 1
    assert faults[0].confidence == 0.85  # Normalized from 85


@pytest.mark.asyncio
async def test_repo_exception_returns_empty(service):
    """Test graceful handling of repository errors."""
    mock_repo = MagicMock()
    mock_repo.get_active_by_site.side_effect = Exception("DB connection failed")
    service._repo = mock_repo

    faults = await service.get_predictions_for_site("site-001")

    assert faults == []


@pytest.mark.asyncio
async def test_prediction_model_fields(service, mock_predictions):
    """Test that PredictiveFault model fields are correctly populated."""
    mock_repo = MagicMock()
    mock_repo.get_active_by_site.return_value = [mock_predictions[0]]
    service._repo = mock_repo

    faults = await service.get_predictions_for_site("site-001")

    fault = faults[0]
    assert isinstance(fault, PredictiveFault)
    assert fault.equipment_id == "eq-001"
    assert fault.prediction_type == "bearing_failure"
    assert fault.model_name == "lstm_chiller_v2"


def test_singleton_factory():
    """Test that get_prediction_overlay_service returns a singleton."""
    import app.services.prediction_overlay_service as mod

    # Reset singleton
    mod._prediction_overlay_service = None

    svc1 = get_prediction_overlay_service()
    svc2 = get_prediction_overlay_service()

    assert svc1 is svc2

    # Clean up
    mod._prediction_overlay_service = None
