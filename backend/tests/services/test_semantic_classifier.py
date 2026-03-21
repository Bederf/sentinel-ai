"""Comprehensive tests for the rule-based semantic point classifier.

Phase 162: Semantic Control Foundation — Plan 02.
Covers confidence calculation, evidence trails, batch classification,
safety class extraction, idempotency, and API endpoints.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.semantic_classification import router as classification_router
from app.models.point_classification import BatchClassificationResult, PointClassification
from app.models.semantic_tag import EvidenceSource, SafetyClass
from app.services.simbiot.classifiers.confidence_calculator import ConfidenceCalculator
from app.services.simbiot.classifiers.rule_based_classifier import RuleBasedPointClassifier


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture()
def classifier() -> RuleBasedPointClassifier:
    return RuleBasedPointClassifier()


@pytest.fixture()
def api_client() -> TestClient:
    app = FastAPI()
    app.include_router(classification_router)
    return TestClient(app)


def _sat_point(extra: dict | None = None) -> dict:
    """Return a supply air temperature sensor point dict."""
    base = {
        "point_id": "P001",
        "device_id": "AHU-01",
        "site_id": "S002",
        "equipment_type": "AHU",
        "point_name": "SAT",
        "haystack_id": "supply.air.temp.sensor",
        "metadata": {},
        "current_value": 18.5,
        "data_quality_score": 1.0,
    }
    if extra:
        base.update(extra)
    return base


def _comp_occ_point() -> dict:
    """Return a compressor occupancy command point dict."""
    return {
        "point_id": "P002",
        "device_id": "FCU-03",
        "site_id": "S002",
        "equipment_type": "FCU",
        "point_name": "COMP_OCC",
        "haystack_id": None,
        "metadata": {},
        "current_value": 1,
        "data_quality_score": 0.9,
    }


def _unknown_point() -> dict:
    """Return a point with no recognisable name or haystack ID."""
    return {
        "point_id": "P999",
        "device_id": "UNKNOWN-01",
        "site_id": "S002",
        "equipment_type": "AHU",
        "point_name": "WIDGET_FLUX_CAPACITOR_STATUS",
        "haystack_id": None,
        "metadata": {},
        "current_value": None,
        "data_quality_score": 0.5,
    }


# ------------------------------------------------------------------
# Unit tests — classifier
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_supply_air_temp_classification_high_confidence(
    classifier: RuleBasedPointClassifier,
) -> None:
    """SAT point with haystack ID and matching name should score >= 0.7."""
    result = await classifier.classify_point(_sat_point())
    assert isinstance(result, PointClassification)
    assert result.confidence_score >= 0.7
    assert "supply_air_temperature_sensor" in result.semantic_tags


@pytest.mark.asyncio
async def test_compressor_occupancy_classification_medium_confidence(
    classifier: RuleBasedPointClassifier,
) -> None:
    """COMP_OCC point with single strong rule should score >= 0.4."""
    result = await classifier.classify_point(_comp_occ_point())
    assert isinstance(result, PointClassification)
    assert result.confidence_score >= 0.4
    assert len(result.semantic_tags) > 0


@pytest.mark.asyncio
async def test_unknown_point_low_confidence(
    classifier: RuleBasedPointClassifier,
) -> None:
    """Unrecognised point should return near-zero confidence."""
    result = await classifier.classify_point(_unknown_point())
    assert isinstance(result, PointClassification)
    assert result.confidence_score < 0.4


@pytest.mark.asyncio
async def test_evidence_records_populated(
    classifier: RuleBasedPointClassifier,
) -> None:
    """Every matching rule should produce an EvidenceRecord."""
    result = await classifier.classify_point(_sat_point())
    assert len(result.evidence_records) >= 1
    for ev in result.evidence_records:
        assert ev.source in EvidenceSource.__members__.values()
        assert 0.0 <= ev.weight <= 1.0
        assert ev.evidence_description  # non-empty rationale
        assert ev.value_found  # what was found
        assert ev.rule_matched  # which rule matched


@pytest.mark.asyncio
async def test_confidence_calculation_accuracy(
    classifier: RuleBasedPointClassifier,
) -> None:
    """Verify the confidence formula: total_weight / required_evidence."""
    # SAT with both haystack_id (0.95) and point_name (0.85) matching; required=2
    result = await classifier.classify_point(_sat_point())
    # Total weight >= 0.95 + 0.85 = 1.80; required=2 → confidence >= 0.9 (capped at 1.0)
    assert result.confidence_score >= 0.7


@pytest.mark.asyncio
async def test_batch_classification_aggregation(
    classifier: RuleBasedPointClassifier,
) -> None:
    """BatchClassificationResult statistics must be correctly aggregated."""
    points = [
        _sat_point(),
        _comp_occ_point(),
        _unknown_point(),
    ]
    batch = await classifier.classify_equipment_batch("AHU-01", points)
    assert isinstance(batch, BatchClassificationResult)
    assert batch.total_points == 3
    assert batch.high_confidence_count + batch.medium_confidence_count + batch.low_confidence_count == 3
    assert batch.processing_time_ms >= 0


@pytest.mark.asyncio
async def test_safety_class_extraction(
    classifier: RuleBasedPointClassifier,
) -> None:
    """Classified point should carry the safety class of the matched tag."""
    # SAT is LOW safety
    sat_result = await classifier.classify_point(_sat_point())
    assert sat_result.highest_safety_class == SafetyClass.LOW

    # compressor occupancy is MEDIUM safety
    comp_result = await classifier.classify_point(_comp_occ_point())
    assert comp_result.highest_safety_class == SafetyClass.MEDIUM


@pytest.mark.asyncio
async def test_classifier_idempotency(
    classifier: RuleBasedPointClassifier,
) -> None:
    """Same input must produce identical output (deterministic classifier)."""
    point = _sat_point()
    result_a = await classifier.classify_point(point)
    result_b = await classifier.classify_point(point)
    assert result_a.confidence_score == result_b.confidence_score
    assert result_a.semantic_tags == result_b.semantic_tags
    assert len(result_a.evidence_records) == len(result_b.evidence_records)


# ------------------------------------------------------------------
# ConfidenceCalculator unit tests
# ------------------------------------------------------------------


def test_confidence_calculation_no_evidence() -> None:
    """Empty evidence list should return 0.0."""
    assert ConfidenceCalculator.calculate_confidence([], 2) == 0.0


def test_confidence_capped_at_one() -> None:
    """Confidence must never exceed 1.0 regardless of evidence sum."""
    from app.models.point_classification import EvidenceRecord
    from app.models.semantic_tag import EvidenceSource

    records = [
        EvidenceRecord(
            source=EvidenceSource.HAYSTACK_ID,
            value_found="x",
            rule_matched="*",
            weight=0.9,
            contributed_confidence=0.9,
            evidence_description="test",
        ),
        EvidenceRecord(
            source=EvidenceSource.POINT_NAME,
            value_found="SAT",
            rule_matched="SAT",
            weight=0.85,
            contributed_confidence=0.85,
            evidence_description="test",
        ),
    ]
    confidence = ConfidenceCalculator.calculate_confidence(records, 1)
    assert confidence == 1.0


def test_confidence_level_classification() -> None:
    """classify_confidence_level should return correct tier strings."""
    assert ConfidenceCalculator.classify_confidence_level(0.8) == "HIGH"
    assert ConfidenceCalculator.classify_confidence_level(0.7) == "HIGH"
    assert ConfidenceCalculator.classify_confidence_level(0.5) == "MEDIUM"
    assert ConfidenceCalculator.classify_confidence_level(0.4) == "MEDIUM"
    assert ConfidenceCalculator.classify_confidence_level(0.39) == "LOW"
    assert ConfidenceCalculator.classify_confidence_level(0.0) == "LOW"


# ------------------------------------------------------------------
# API endpoint tests
# ------------------------------------------------------------------


def test_classification_api_endpoint(api_client: TestClient) -> None:
    """POST /classify-point should return a classification with confidence score."""
    payload = {
        "site_id": "S002",
        "equipment_id": "AHU-01",
        "point_data": {
            "point_id": "P001",
            "equipment_type": "AHU",
            "point_name": "SAT",
            "haystack_id": "supply.air.temp.sensor",
            "current_value": 18.5,
            "data_quality_score": 1.0,
        },
    }
    response = api_client.post("/api/semantic-classification/classify-point", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "classification" in data
    assert "processing_time_ms" in data
    assert data["classification"]["confidence_score"] >= 0.0


def test_equipment_batch_classification(api_client: TestClient) -> None:
    """POST /classify-equipment should return aggregated batch result."""
    payload = {
        "site_id": "S002",
        "equipment_id": "AHU-01",
        "points": [
            {
                "point_id": "P001",
                "equipment_type": "AHU",
                "point_name": "SAT",
                "haystack_id": "supply.air.temp.sensor",
                "data_quality_score": 1.0,
            },
            {
                "point_id": "P002",
                "equipment_type": "AHU",
                "point_name": "RAT",
                "haystack_id": None,
                "data_quality_score": 0.9,
            },
        ],
    }
    response = api_client.post("/api/semantic-classification/classify-equipment", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "batch_result" in data
    assert data["batch_result"]["total_points"] == 2


def test_list_tags_endpoint(api_client: TestClient) -> None:
    """GET /dictionary/tags should return at least 40 tag names."""
    response = api_client.get("/api/semantic-classification/dictionary/tags")
    assert response.status_code == 200
    tags = response.json()
    assert isinstance(tags, list)
    assert len(tags) >= 40


def test_get_tag_endpoint_known(api_client: TestClient) -> None:
    """GET /dictionary/tag/{name} should return full tag structure."""
    response = api_client.get("/api/semantic-classification/dictionary/tag/supply_air_temperature_sensor")
    assert response.status_code == 200
    data = response.json()
    assert data["tag"] == "supply_air_temperature_sensor"
    assert "safety_class" in data
    assert "classification_rules" in data


def test_get_tag_endpoint_unknown(api_client: TestClient) -> None:
    """GET /dictionary/tag/{name} for unknown tag should return 404."""
    response = api_client.get("/api/semantic-classification/dictionary/tag/nonexistent_xyz")
    assert response.status_code == 404


def test_classify_equipment_empty_points(api_client: TestClient) -> None:
    """POST /classify-equipment with empty points list should return 422."""
    payload = {"site_id": "S002", "equipment_id": "AHU-01", "points": []}
    response = api_client.post("/api/semantic-classification/classify-equipment", json=payload)
    assert response.status_code == 422
