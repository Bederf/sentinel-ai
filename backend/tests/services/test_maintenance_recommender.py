"""Tests for the Maintenance Recommender Service."""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from app.services.maintenance_recommender import (
    MaintenanceRecommender,
    MaintenanceRecommendation,
    DEFAULT_MAINTENANCE_ACTIONS,
    COMMON_SPARE_PARTS,
    get_maintenance_recommender,
)


@pytest.fixture
def mock_ollama():
    """Mock Ollama client."""
    with patch('app.services.maintenance_recommender.get_ollama_client') as mock:
        client = AsyncMock()
        client.is_available = AsyncMock(return_value=False)
        client.generate = AsyncMock(return_value="No LLM response")
        mock.return_value = client
        yield client


@pytest.fixture
def mock_vector_db():
    """Mock vector DB service."""
    with patch('app.services.maintenance_recommender.get_vector_db_service') as mock:
        service = Mock()
        service.search_knowledge = Mock(return_value=[])
        mock.return_value = service
        yield service


@pytest.fixture
def mock_supabase():
    """Mock Supabase client."""
    return Mock()


@pytest.fixture
def recommender(mock_ollama, mock_vector_db, mock_supabase):
    """Create maintenance recommender with mocked dependencies."""
    return MaintenanceRecommender(mock_supabase)


class TestMaintenanceRecommendation:
    """Test cases for MaintenanceRecommendation dataclass."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        rec = MaintenanceRecommendation(
            equipment_id="chiller-001",
            equipment_type="chiller",
            risk_level="high",
            immediate_actions=["Inspect unit"],
            priority="urgent",
            generated_at="2026-01-01T00:00:00",
        )

        d = rec.to_dict()
        assert d["equipment_id"] == "chiller-001"
        assert d["risk_level"] == "high"
        assert d["priority"] == "urgent"
        assert d["immediate_actions"] == ["Inspect unit"]
        assert d["llm_used"] is False

    def test_default_values(self):
        """Test default field values."""
        rec = MaintenanceRecommendation(
            equipment_id="test",
            equipment_type="chiller",
            risk_level="low",
        )

        assert rec.immediate_actions == []
        assert rec.scheduled_maintenance == []
        assert rec.preventive_measures == []
        assert rec.spare_parts == []
        assert rec.technician_skills == []
        assert rec.estimated_downtime == ""
        assert rec.priority == "medium"
        assert rec.llm_used is False


class TestMaintenanceRecommender:
    """Test cases for MaintenanceRecommender."""

    @pytest.mark.asyncio
    async def test_generate_fallback_chiller_critical(self, recommender):
        """Test fallback recommendation for critical chiller risk."""
        predictions = {
            "overall_risk": {"risk_level": "critical"},
            "predictions": {"failure_type": {"predicted_failure": "Compressor failure"}}
        }

        result = await recommender.generate_recommendation(
            equipment_id="chiller-001",
            equipment_type="chiller",
            predictions=predictions,
        )

        assert isinstance(result, MaintenanceRecommendation)
        assert result.equipment_id == "chiller-001"
        assert result.risk_level == "critical"
        assert result.priority == "emergency"
        assert result.llm_used is False
        assert len(result.immediate_actions) > 0
        assert "Shut down" in result.immediate_actions[0]

    @pytest.mark.asyncio
    async def test_generate_fallback_ahu_high(self, recommender):
        """Test fallback recommendation for high-risk AHU."""
        predictions = {
            "overall_risk": {"risk_level": "high"},
            "predictions": {"failure_type": {"predicted_failure": "Belt failure"}}
        }

        result = await recommender.generate_recommendation(
            equipment_id="ahu-001",
            equipment_type="ahu",
            predictions=predictions,
        )

        assert result.risk_level == "high"
        assert result.priority == "urgent"
        assert len(result.immediate_actions) > 0
        assert any("filter" in a.lower() or "belt" in a.lower() for a in result.immediate_actions)

    @pytest.mark.asyncio
    async def test_generate_fallback_generator_medium(self, recommender):
        """Test fallback recommendation for medium-risk generator."""
        predictions = {
            "overall_risk": {"risk_level": "medium"},
            "predictions": {"failure_type": {"predicted_failure": "Battery degradation"}}
        }

        result = await recommender.generate_recommendation(
            equipment_id="gen-001",
            equipment_type="generator",
            predictions=predictions,
        )

        assert result.risk_level == "medium"
        assert result.priority == "planned"
        assert len(result.scheduled_maintenance) > 0

    @pytest.mark.asyncio
    async def test_generate_fallback_low_risk(self, recommender):
        """Test fallback recommendation for low risk."""
        predictions = {
            "overall_risk": {"risk_level": "low"},
            "predictions": {"failure_type": {"predicted_failure": "Unknown"}}
        }

        result = await recommender.generate_recommendation(
            equipment_id="fcu-001",
            equipment_type="fcu",
            predictions=predictions,
        )

        assert result.risk_level == "low"
        assert result.priority == "routine"

    @pytest.mark.asyncio
    async def test_generate_fallback_unknown_equipment(self, recommender):
        """Test fallback for unknown equipment type uses default actions."""
        predictions = {
            "overall_risk": {"risk_level": "high"},
            "predictions": {"failure_type": {"predicted_failure": "Unknown"}}
        }

        result = await recommender.generate_recommendation(
            equipment_id="custom-001",
            equipment_type="custom_device",
            predictions=predictions,
        )

        # Should use default actions
        assert result.risk_level == "high"
        assert len(result.immediate_actions) > 0
        assert "Schedule priority inspection" in result.immediate_actions[0]

    @pytest.mark.asyncio
    async def test_generate_with_maintenance_history(self, recommender):
        """Test passing maintenance history (used by LLM path)."""
        predictions = {
            "overall_risk": {"risk_level": "medium"},
            "predictions": {"failure_type": {"predicted_failure": "Filter clog"}}
        }
        history = [
            {"date": "2026-01-01", "description": "Filter replaced"},
            {"date": "2025-12-01", "description": "Routine PM"},
        ]

        # With LLM unavailable, falls back to rule-based (ignores history)
        result = await recommender.generate_recommendation(
            equipment_id="ahu-001",
            equipment_type="ahu",
            predictions=predictions,
            maintenance_history=history,
        )

        assert result.llm_used is False
        assert result.risk_level == "medium"

    @pytest.mark.asyncio
    async def test_generate_with_llm_available(self, recommender, mock_ollama):
        """Test recommendation generation when LLM is available."""
        mock_ollama.is_available = AsyncMock(return_value=True)
        mock_ollama.generate = AsyncMock(return_value="""
### IMMEDIATE_ACTIONS
- Check refrigerant levels immediately
- Inspect compressor contacts

### SCHEDULED_MAINTENANCE
- [48 hours] Full inspection

### PREVENTIVE_MEASURES
- Monthly vibration analysis

### SPARE_PARTS
- Compressor contactor | CC-100 | 1

### TECHNICIAN_SKILLS
- HVAC certification

### ESTIMATED_DOWNTIME
2-4 hours
""")

        predictions = {
            "overall_risk": {"risk_level": "high"},
            "predictions": {"failure_type": {"predicted_failure": "Compressor issue"}}
        }

        result = await recommender.generate_recommendation(
            equipment_id="chiller-001",
            equipment_type="chiller",
            predictions=predictions,
        )

        assert result.llm_used is True
        assert result.risk_level == "high"
        assert len(result.immediate_actions) >= 1

    def test_risk_to_priority(self, recommender):
        """Test risk level to priority mapping."""
        assert recommender._risk_to_priority("critical") == "emergency"
        assert recommender._risk_to_priority("high") == "urgent"
        assert recommender._risk_to_priority("medium") == "planned"
        assert recommender._risk_to_priority("low") == "routine"
        assert recommender._risk_to_priority("unknown") == "routine"

    def test_estimate_downtime(self, recommender):
        """Test downtime estimation by risk level."""
        assert "4-8" in recommender._estimate_downtime("critical")
        assert "2-4" in recommender._estimate_downtime("high")
        assert "1-2" in recommender._estimate_downtime("medium")
        assert "0.5-1" in recommender._estimate_downtime("low")

    @pytest.mark.asyncio
    async def test_get_fleet_recommendations(self, recommender):
        """Test generating recommendations for multiple equipment."""
        equipment_list = [
            {"id": "ch-001", "equipment_type": "chiller"},
            {"id": "ahu-001", "equipment_type": "ahu"},
        ]
        predictions_map = {
            "ch-001": {
                "overall_risk": {"risk_level": "high"},
                "predictions": {"failure_type": {"predicted_failure": "Refrigerant leak"}}
            },
            "ahu-001": {
                "overall_risk": {"risk_level": "low"},
                "predictions": {"failure_type": {"predicted_failure": "Normal"}}
            },
        }

        results = await recommender.get_fleet_recommendations(
            equipment_list, predictions_map
        )

        assert len(results) == 2
        # Should be sorted by priority (urgent before routine)
        assert results[0].priority == "urgent"
        assert results[1].priority == "routine"

    @pytest.mark.asyncio
    async def test_get_fleet_skips_missing_predictions(self, recommender):
        """Test fleet recommendations skip equipment without predictions."""
        equipment_list = [
            {"id": "ch-001", "equipment_type": "chiller"},
            {"id": "ch-002", "equipment_type": "chiller"},
        ]
        predictions_map = {
            "ch-001": {
                "overall_risk": {"risk_level": "medium"},
                "predictions": {"failure_type": {"predicted_failure": "Normal"}}
            },
            # ch-002 missing from predictions
        }

        results = await recommender.get_fleet_recommendations(
            equipment_list, predictions_map
        )

        assert len(results) == 1
        assert results[0].equipment_id == "ch-001"

    def test_fallback_includes_spare_parts(self, recommender):
        """Test that fallback recommendations include spare parts."""
        rec = recommender._generate_fallback_recommendation(
            equipment_id="ch-001",
            equipment_type="chiller",
            risk_level="high",
            predicted_failure="Compressor issue",
        )

        assert len(rec.spare_parts) > 0
        # Should include chiller-specific parts
        part_names = [p["name"] for p in rec.spare_parts]
        assert any("Refrigerant" in name or "Compressor" in name for name in part_names)

    def test_fallback_includes_preventive_measures(self, recommender):
        """Test that fallback recommendations include preventive measures."""
        rec = recommender._generate_fallback_recommendation(
            equipment_id="ahu-001",
            equipment_type="ahu",
            risk_level="medium",
            predicted_failure="Filter issue",
        )

        assert len(rec.preventive_measures) > 0
        assert rec.generated_at != ""

    def test_fallback_includes_technician_skills(self, recommender):
        """Test that HVAC equipment gets HVAC certification requirement."""
        rec = recommender._generate_fallback_recommendation(
            equipment_id="ch-001",
            equipment_type="chiller",
            risk_level="medium",
            predicted_failure="Normal",
        )

        assert "HVAC certification" in rec.technician_skills


class TestDefaultActions:
    """Test the default maintenance action definitions."""

    def test_chiller_actions_exist(self):
        """Test chiller has actions for all risk levels."""
        assert "chiller" in DEFAULT_MAINTENANCE_ACTIONS
        for level in ["critical", "high", "medium", "low"]:
            assert level in DEFAULT_MAINTENANCE_ACTIONS["chiller"]
            assert len(DEFAULT_MAINTENANCE_ACTIONS["chiller"][level]) > 0

    def test_default_actions_exist(self):
        """Test default actions exist for fallback."""
        assert "default" in DEFAULT_MAINTENANCE_ACTIONS
        for level in ["critical", "high", "medium", "low"]:
            assert level in DEFAULT_MAINTENANCE_ACTIONS["default"]

    def test_common_spare_parts(self):
        """Test spare parts defined for major equipment types."""
        for eq_type in ["chiller", "ahu", "generator", "fcu"]:
            assert eq_type in COMMON_SPARE_PARTS
            assert len(COMMON_SPARE_PARTS[eq_type]) > 0


class TestFactoryFunction:
    """Test the factory function."""

    def test_get_maintenance_recommender(self, mock_ollama, mock_vector_db):
        """Test factory creates recommender."""
        client = Mock()
        recommender = get_maintenance_recommender(client)
        assert isinstance(recommender, MaintenanceRecommender)
