"""Tests for Niagara point discovery and classification services.

Tests cover:
- Point classification with Haystack/Brick ontology
- Equipment type detection via regex patterns
- Point type inference from BACnet object types
- Confidence scoring (high/medium/low)
- Standardized name generation
- Batch classification and summary
- Demo point discovery workflow
- Discovery result caching and persistence
"""

import json
import pytest
from pathlib import Path

from app.services.niagara.point_classifier import (
    ConfidenceLevel,
    PointClassifier,
    PointType,
    get_point_classifier,
)
from app.services.niagara.point_discovery import (
    DiscoveryResult,
    PointDiscoveryService,
    get_point_discovery_service,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def classifier():
    """Create a fresh PointClassifier instance."""
    return PointClassifier()


@pytest.fixture
def discovery_service():
    """Create a fresh PointDiscoveryService."""
    return PointDiscoveryService()


@pytest.fixture
def demo_points():
    """Load demo points from haystack_tags.json."""
    tags_path = Path(__file__).parent.parent.parent / "app" / "data" / "niagara" / "haystack_tags.json"
    with open(tags_path) as f:
        data = json.load(f)
    return data.get("demo_points", [])


# ---------------------------------------------------------------------------
# Point Classifier Tests
# ---------------------------------------------------------------------------


class TestPointClassifier:
    """Tests for PointClassifier."""

    def test_classify_chiller_temperature(self, classifier):
        """Classify a chiller supply temperature point."""
        result = classifier.classify_point(
            "CH-1_CHW_Supply_Temp",
            "Chiller 1 Chilled Water Supply Temperature",
            object_type="analogInput",
            units="degC",
        )
        assert result.equipment_type == "chiller"
        assert result.point_category == "temperature"
        assert result.point_type == PointType.SENSOR
        assert result.confidence in (ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM)
        assert result.equipment_id == "CH-1"

    def test_classify_ahu_fan_speed(self, classifier):
        """Classify an AHU fan speed point."""
        result = classifier.classify_point(
            "AHU-1_Fan_Speed",
            "AHU-1 Supply Fan Speed",
            object_type="analogOutput",
            units="%",
        )
        assert result.equipment_type == "ahu"
        assert result.point_category == "speed"
        assert result.equipment_id == "AHU-1"

    def test_classify_vav_zone_temp(self, classifier):
        """Classify a VAV zone temperature point."""
        result = classifier.classify_point(
            "VAV-L1-A_Zone_Temp",
            "VAV Level 1 Zone A Temperature",
            object_type="analogInput",
            units="degC",
        )
        assert result.equipment_type == "vav"
        assert result.point_category == "temperature"
        assert result.equipment_id == "VAV-L1-A"

    def test_classify_fcu_valve_position(self, classifier):
        """Classify an FCU valve position point."""
        result = classifier.classify_point(
            "FCU-L1-A_Valve_Pos",
            "FCU Level 1 Zone A Cooling Valve",
            object_type="analogOutput",
            units="%",
        )
        assert result.equipment_type == "fcu"
        assert result.point_category == "valve_position"
        assert result.equipment_id == "FCU-L1-A"

    def test_classify_pump_status(self, classifier):
        """Classify a pump status point."""
        result = classifier.classify_point(
            "PUMP-CW-1_Status",
            "Condenser Water Pump 1 Status",
            object_type="binaryInput",
        )
        assert result.equipment_type == "pump"
        assert result.point_type == PointType.STATUS
        assert result.equipment_id == "PUMP-CW-1"

    def test_classify_generator_fuel_level(self, classifier):
        """Classify a generator fuel level point."""
        result = classifier.classify_point(
            "GEN-1_Fuel_Level",
            "Generator 1 Fuel Level",
            object_type="analogInput",
            units="%",
        )
        assert result.equipment_type == "generator"
        assert result.point_category == "level"
        assert result.equipment_id == "GEN-1"

    def test_classify_meter_power(self, classifier):
        """Classify a power meter point."""
        result = classifier.classify_point(
            "MTR-MAIN_kW",
            "Main Power Meter Active Power",
            object_type="analogInput",
            units="kW",
        )
        assert result.equipment_type == "meter"
        assert result.point_category == "power"
        assert result.equipment_id == "MTR-MAIN"

    def test_classify_alarm_point(self, classifier):
        """Classify an alarm point."""
        result = classifier.classify_point(
            "CH-1_Alarm",
            "Chiller 1 General Alarm",
            object_type="binaryInput",
        )
        assert result.equipment_type == "chiller"
        assert result.point_type == PointType.ALARM

    def test_classify_setpoint(self, classifier):
        """Classify a setpoint point."""
        result = classifier.classify_point(
            "CH-1_CHW_SP",
            "Chiller 1 CHW Supply Setpoint",
            object_type="analogValue",
            units="degC",
        )
        assert result.equipment_type == "chiller"
        assert result.point_type == PointType.SETPOINT

    def test_classify_co2_sensor(self, classifier):
        """Classify a CO2 sensor point."""
        result = classifier.classify_point(
            "ZONE-L1_CO2",
            "Level 1 CO2 Sensor",
            object_type="analogInput",
            units="ppm",
        )
        assert result.point_category == "co2"
        assert result.point_type == PointType.SENSOR

    def test_classify_unknown_point(self, classifier):
        """Classify a point with no recognizable patterns."""
        result = classifier.classify_point(
            "XYZ_123",
            "",
            object_type="analogInput",
        )
        # Should handle gracefully with low/unknown confidence
        assert result.confidence in (ConfidenceLevel.LOW, ConfidenceLevel.UNKNOWN)

    def test_extract_equipment_id(self, classifier):
        """Test equipment ID extraction from various name formats."""
        classifier._load_tags()

        assert classifier._extract_equipment_id("CH-1_CHW_Supply_Temp") == "CH-1"
        assert classifier._extract_equipment_id("AHU-1_Supply_Air_Temp") == "AHU-1"
        assert classifier._extract_equipment_id("VAV-L1-A_Zone_Temp") == "VAV-L1-A"
        assert classifier._extract_equipment_id("FCU-L1-A_Room_Temp") == "FCU-L1-A"
        assert classifier._extract_equipment_id("PUMP-CW-1_Status") == "PUMP-CW-1"
        assert classifier._extract_equipment_id("MTR-MAIN_kW") == "MTR-MAIN"
        assert classifier._extract_equipment_id("GEN-1_Status") == "GEN-1"

    def test_unit_resolution(self, classifier):
        """Test unit standardization."""
        classifier._load_tags()

        assert classifier._resolve_unit("degc", "") == "degC"
        assert classifier._resolve_unit("kpa", "") == "kPa"
        assert classifier._resolve_unit("percent", "") == "%"
        assert classifier._resolve_unit("", "degC") == "degC"  # fallback to category

    def test_batch_classification(self, classifier, demo_points):
        """Test batch classification of all demo points."""
        results = classifier.classify_points(demo_points)

        assert len(results) == len(demo_points)

        # Verify minimum classification accuracy (80%+ should be classified)
        classified = [r for r in results if r.equipment_type != "unknown"]
        accuracy = len(classified) / len(results) * 100
        assert accuracy >= 80, f"Classification accuracy {accuracy:.1f}% below 80% threshold"

    def test_classification_summary(self, classifier, demo_points):
        """Test classification summary generation."""
        results = classifier.classify_points(demo_points)
        summary = classifier.get_classification_summary(results)

        assert summary["total_points"] == len(demo_points)
        assert "equipment_type_counts" in summary
        assert "confidence_counts" in summary
        assert "point_type_counts" in summary
        assert "unique_equipment" in summary
        assert "needs_review" in summary

        # Should identify at least 5 different equipment types
        known_types = {k: v for k, v in summary["equipment_type_counts"].items() if k != "unknown"}
        assert len(known_types) >= 5, f"Only found {len(known_types)} equipment types"

    def test_standardized_name_generation(self, classifier):
        """Test Brick-style standardized name generation."""
        result = classifier.classify_point(
            "CH-1_CHW_Supply_Temp",
            "Chiller 1 Supply Temperature",
            object_type="analogInput",
        )
        assert "/" in result.standardized_name
        assert "CH-1" in result.standardized_name

    def test_tags_generated(self, classifier):
        """Test that Haystack-style tags are generated."""
        result = classifier.classify_point(
            "CH-1_CHW_Supply_Temp",
            "Chiller 1 Supply Temperature",
            object_type="analogInput",
        )
        assert len(result.tags) > 0
        assert "point" in result.tags
        assert "chiller" in result.tags


# ---------------------------------------------------------------------------
# Point Discovery Service Tests
# ---------------------------------------------------------------------------


class TestPointDiscoveryService:
    """Tests for PointDiscoveryService."""

    @pytest.mark.asyncio
    async def test_discover_with_demo_data(self, discovery_service):
        """Test discovery using demo data fallback."""
        result = await discovery_service.discover_and_classify(
            device_ip="192.168.1.100",
            site_id="site-002",
            use_demo=True,
        )

        assert result.status == "complete"
        assert result.discovery_id
        assert len(result.classified_points) > 0
        assert result.summary.get("total_points", 0) > 0
        assert result.error is None

    @pytest.mark.asyncio
    async def test_discovery_result_cached(self, discovery_service):
        """Test that discovery results are cached."""
        result = await discovery_service.discover_and_classify(
            device_ip="192.168.1.100",
            site_id="site-002",
            use_demo=True,
        )

        cached = discovery_service.get_discovery_result(result.discovery_id)
        assert cached is not None
        assert cached.discovery_id == result.discovery_id

    @pytest.mark.asyncio
    async def test_discovery_summary_structure(self, discovery_service):
        """Test that discovery summary has expected structure."""
        result = await discovery_service.discover_and_classify(
            device_ip="192.168.1.100",
            site_id="site-002",
            use_demo=True,
        )

        summary = result.summary
        assert "total_points" in summary
        assert "equipment_type_counts" in summary
        assert "confidence_counts" in summary
        assert "unique_equipment" in summary
        assert "needs_review" in summary

    @pytest.mark.asyncio
    async def test_list_discoveries(self, discovery_service):
        """Test listing discovery results."""
        await discovery_service.discover_and_classify(
            device_ip="192.168.1.100",
            site_id="site-002",
            use_demo=True,
        )

        discoveries = discovery_service.list_discoveries()
        assert len(discoveries) >= 1
        assert discoveries[0]["status"] == "complete"

    def test_discovery_result_serialization(self):
        """Test DiscoveryResult serialization."""
        result = DiscoveryResult(
            discovery_id="test-001",
            device_ip="192.168.1.100",
            site_id="site-002",
            device_id=1234,
        )

        data = result.to_dict()
        assert data["discovery_id"] == "test-001"
        assert data["device_ip"] == "192.168.1.100"
        assert data["site_id"] == "site-002"
        assert data["device_id"] == 1234
        assert data["status"] == "pending"

    @pytest.mark.asyncio
    async def test_demo_points_classification_accuracy(self, discovery_service):
        """Verify 80%+ accuracy on demo points."""
        result = await discovery_service.discover_and_classify(
            device_ip="192.168.1.100",
            site_id="site-002",
            use_demo=True,
        )

        total = result.summary.get("total_points", 0)
        high = result.summary.get("confidence_counts", {}).get("high", 0)
        medium = result.summary.get("confidence_counts", {}).get("medium", 0)

        classified_pct = (high + medium) / total * 100 if total > 0 else 0
        assert classified_pct >= 80, f"Only {classified_pct:.1f}% classified with high/medium confidence"


# ---------------------------------------------------------------------------
# Singleton Tests
# ---------------------------------------------------------------------------


class TestSingletons:
    """Test singleton factory functions."""

    def test_get_point_classifier_singleton(self):
        """Verify singleton pattern for classifier."""
        import app.services.niagara.point_classifier as mod

        old = mod._classifier_instance
        mod._classifier_instance = None
        try:
            c1 = get_point_classifier()
            c2 = get_point_classifier()
            assert c1 is c2
        finally:
            mod._classifier_instance = old

    def test_get_discovery_service_singleton(self):
        """Verify singleton pattern for discovery service."""
        import app.services.niagara.point_discovery as mod

        old = mod._discovery_service
        mod._discovery_service = None
        try:
            s1 = get_point_discovery_service()
            s2 = get_point_discovery_service()
            assert s1 is s2
        finally:
            mod._discovery_service = old
