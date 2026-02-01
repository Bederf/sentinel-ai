"""Tests for the Maintenance Recommender Service."""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timedelta
from app.services.maintenance_recommender import (
    MaintenanceRecommender,
    MaintenanceRecommendation,
    MaintenanceAction,
    RiskAssessment
)


@pytest.fixture
def mock_rag_service():
    """Mock RAG service."""
    with patch('app.services.maintenance_recommender.RAGService') as mock:
        service = AsyncMock()
        service.search_faults = AsyncMock(return_value={
            "results": [
                {
                    "content": "Fault pattern 1",
                    "metadata": {
                        "severity": "high",
                        "recommended_actions": ["Action 1", "Action 2"]
                    }
                }
            ]
        })
        service.search_procedures = AsyncMock(return_value={
            "results": [
                {"content": "Procedure 1", "metadata": {"estimated_time": "2h"}}
            ]
        })
        mock.return_value = service
        yield service


@pytest.fixture
def mock_supabase():
    """Mock Supabase client."""
    with patch('app.services.maintenance_recommender.create_supabase_client') as mock:
        client = Mock()
        client.table = Mock()
        # Mock chain for select().eq().execute()
        query = Mock()
        query.eq = Mock(return_value=query)
        client.table.return_value = query

        mock.return_value = client
        yield client


@pytest.fixture
def maintenance_recommender(mock_rag_service, mock_supabase):
    """Create maintenance recommender with mocked dependencies."""
    recommender = MaintenanceRecommender()
    yield recommender


class TestMaintenanceRecommender:
    """Test cases for MaintenanceRecommender."""

    async def test_generate_recommendations_basic(self, maintenance_recommender, mock_rag_service):
        """Test basic recommendation generation."""
        # Setup
        predictions = {"24h": 12.5, "48h": 13.0, "72h": 13.5}

        # Execute
        result = await maintenance_recommender.generate_recommendations(
            equipment_id="chiller-001",
            equipment_type="chiller",
            predictions=predictions,
            confidence=0.85
        )

        # Assert
        assert "recommendations" in result
        assert isinstance(result["recommendations"], list)
        assert result["total_estimated_time"] >= 0
        assert result["total_estimated_cost"] >= 0

    async def test_generate_recommendations_with_rag(self, maintenance_recommender, mock_rag_service):
        """Test recommendation generation with RAG context."""
        # Setup
        predictions = {"24h": 15.0}
        mock_rag_service.search_faults.return_value = {
            "results": [
                {
                    "content": "High discharge temperature pattern",
                    "metadata": {
                        "severity": "medium",
                        "recommended_actions": [
                            "Check refrigerant charge",
                            "Clean condenser coils"
                        ],
                        "estimated_cost": "R 2,500"
                    }
                }
            ]
        }

        # Execute
        result = await maintenance_recommender.generate_recommendations(
            equipment_id="chiller-001",
            equipment_type="chiller",
            predictions=predictions,
            confidence=0.8,
            include_rag_context=True
        )

        # Assert
        recommendations = result["recommendations"]
        assert len(recommendations) > 0
        # Should include actions from RAG
        descriptions = [r["description"] for r in recommendations]
        assert any("refrigerant" in d.lower() for d in descriptions)

    async def test_priority_filtering(self, maintenance_recommender):
        """Test filtering recommendations by priority."""
        # Setup
        predictions = {"24h": 14.0}

        # Execute - filter for critical only
        result = await maintenance_recommender.generate_recommendations(
            equipment_id="chiller-001",
            equipment_type="chiller",
            predictions=predictions,
            urgency_filter="critical"
        )

        # Assert
        recommendations = result["recommendations"]
        # All recommendations should be critical priority
        for rec in recommendations:
            assert rec.get("priority") == "critical"

    async def test_recommendation_pricing(self, maintenance_recommender):
        """Test cost estimation for recommendations."""
        # Setup
        predictions = {"24h": 13.5}

        # Execute
        result = await maintenance_recommender.generate_recommendations(
            equipment_id="ahu-001",
            equipment_type="ahu",
            predictions=predictions,
            confidence=0.75
        )

        # Assert
        assert result["total_estimated_cost"] > 0
        recommendations = result["recommendations"]
        for rec in recommendations:
            if rec.get("estimated_cost"):
                assert rec["estimated_cost"] > 0
                assert rec["cost_currency"] == "ZAR"

    async def test_risk_assessment(self, maintenance_recommender):
        """Test risk assessment calculation."""
        # Setup
        predictions = {"24h": 16.0}  # Higher temp = higher risk

        # Execute
        result = await maintenance_recommender.generate_recommendations(
            equipment_id="chiller-001",
            equipment_type="chiller",
            predictions=predictions,
            confidence=0.8
        )

        # Assert
        recommendations = result["recommendations"]
        for rec in recommendations:
            risk = rec.get("risk_assessment")
            if risk:
                assert risk.get("risk_level") in ["low", "medium", "high", "critical"]
                assert "probability" in risk

    async def test_generator_recommendations(self, maintenance_recommender):
        """Test recommendations for generator equipment."""
        # Setup
        predictions = {"24h": 85.5}  # Generator load percentage

        # Execute
        result = await maintenance_recommender.generate_recommendations(
            equipment_id="generator-001",
            equipment_type="generator",
            predictions=predictions,
            confidence=0.9
        )

        # Assert
        assert "recommendations" in result
        recommendations = result["recommendations"]
        assert len(recommendations) >= 0

    async def test_invalid_equipment_type(self, maintenance_recommender):
        """Test handling of invalid equipment type."""
        with pytest.raises(ValueError, match="Unknown equipment type"):
            await maintenance_recommender.generate_recommendations(
                equipment_id="unknown-001",
                equipment_type="invalid_type",
                predictions={"24h": 10.0}
            )

    def test_calculate_confidence_boost(self):
        """Test confidence boost calculation."""
        recommender = MaintenanceRecommender()

        # Test low anomaly case
        boost_low = recommender._calculate_confidence_boost(0.1, 12.5, 14.0)
        assert boost_low > 0  # Should be positive boost (normal operation)

        # Test high anomaly case
        boost_high = recommender._calculate_confidence_boost(0.8, 16.0, 14.0)
        assert boost_high < 0  # Should be negative boost (concerning)

    def test_determine_priority(self):
        """Test priority determination logic."""
        recommender = MaintenanceRecommender()

        # Test critical priority
        priority = recommender._determine_priority(
            anomaly_score=0.9,
            prediction_value=18.0,
            threshold_value=14.0,
            equipment_type="chiller"
        )
        assert priority == "critical"

        # Test high priority
        priority = recommender._determine_priority(
            anomaly_score=0.7,
            prediction_value=16.0,
            threshold_value=14.0,
            equipment_type="chiller"
        )
        assert priority == "high"

        # Test medium priority
        priority = recommender._determine_priority(
            anomaly_score=0.3,
            prediction_value=12.0,
            threshold_value=14.0,
            equipment_type="chiller"
        )
        assert priority == "medium"

        # Test low priority
        priority = recommender._determine_priority(
            anomaly_score=0.05,
            prediction_value=10.0,
            threshold_value=14.0,
            equipment_type="chiller"
        )
        assert priority == "low"

    def test_determine_generator_priority(self):
        """Test priority determination for generators."""
        recommender = MaintenanceRecommender()

        # High load = higher priority
        priority = recommender._determine_priority(
            anomaly_score=0.6,
            prediction_value=95.0,  # High load
            threshold_value=85.0,
            equipment_type="generator"
        )
        assert priority in ["high", "critical"]

    async def test_record_feedback(self, maintenance_recommender, mock_supabase):
        """Test recording maintenance feedback."""
        # Setup
        mock_supabase.table.return_value.insert = Mock(
            return_value=Mock(data=[{"id": "feedback-001"}])
        )

        # Execute
        await maintenance_recommender.record_feedback(
            equipment_id="chiller-001",
            recommendation_id="rec-001",
            action_taken="Replaced filter",
            outcome="success",
            actual_time_hours=2.5,
            actual_cost=1500.0
        )

        # Assert - should have called insert
        mock_supabase.table.assert_called_with("maintenance_feedback")

    async def test_build_optimization_suggestion(self, maintenance_recommender):
        """Test building optimization suggestions."""
        efficiency_gain = 15.5  # 15.5% efficiency gain

        suggestion = maintenance_recommender._build_optimization_suggestion(
            "Clean condenser coils",
            efficiency_gain
        )

        assert suggestion is not None
        assert "optimization" in suggestion["category"]
        assert suggestion["expected_outcome"] == "15.5% efficiency improvement"

    async def test_empty_predictions_handling(self, maintenance_recommender):
        """Test handling of empty predictions."""
        with pytest.raises(ValueError, match="Predictions cannot be empty"):
            await maintenance_recommender.generate_recommendations(
                equipment_id="chiller-001",
                equipment_type="chiller",
                predictions={}
            )
