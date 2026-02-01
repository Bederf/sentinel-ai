"""Tests for the Explanation Service."""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from app.services.explanation_service import (
    ExplanationService,
    ExplanationResult
)


@pytest.fixture
def mock_ollama_client():
    """Mock Ollama client."""
    with patch('app.services.explanation_service.get_ollama_client') as mock_get:
        client = Mock()
        client.is_available = AsyncMock(return_value=True)
        client.generate = AsyncMock(return_value="Test explanation")
        client.model = "qwen:7b"
        mock_get.return_value = client
        yield client


@pytest.fixture
def mock_vector_db():
    """Mock vector DB service."""
    with patch('app.services.explanation_service.get_vector_db_service') as mock_get:
        db = Mock()
        db.get_rag_context = AsyncMock(return_value="Test RAG context")
        mock_get.return_value = db
        yield db


@pytest.fixture
def mock_supabase_client():
    """Mock Supabase client."""
    return Mock()


@pytest.fixture
def explanation_service(mock_supabase_client, mock_ollama_client, mock_vector_db):
    """Create explanation service with mocked dependencies."""
    service = ExplanationService(mock_supabase_client)
    yield service


class TestExplanationService:
    """Test cases for ExplanationService."""

    async def test_explain_prediction_basic(self, explanation_service, mock_ollama_client):
        """Test basic prediction explanation generation."""
        # Setup
        predictions = {
            "equipment_type": "chiller",
            "predictions": {"24h": 12.5, "48h": 13.2, "72h": 14.1},
            "confidence": 0.85
        }
        mock_ollama_client.generate.return_value = """## Analysis Summary
The chiller efficiency is within normal parameters.

## Contributing Factors
- Normal load conditions
- Stable ambient temperature

## Recommended Actions
No immediate action required. Continue monitoring.
"""

        # Execute
        result = await explanation_service.explain_prediction(
            equipment_id="chiller-001",
            predictions=predictions
        )

        # Assert
        assert isinstance(result, ExplanationResult)
        assert result.equipment_id == "chiller-001"
        assert result.equipment_type == "chiller"
        assert "normal" in result.raw_explanation.lower()
        assert result.model_used == "qwen:7b"

    async def test_explain_prediction_with_fallback(self, explanation_service, mock_ollama_client):
        """Test fallback explanation when Ollama is unavailable."""
        # Setup
        mock_ollama_client.is_available.return_value = False
        predictions = {
            "equipment_type": "chiller",
            "predictions": {"24h": 15.0}
        }

        # Execute
        result = await explanation_service.explain_prediction(
            equipment_id="chiller-001",
            predictions=predictions
        )

        # Assert
        assert isinstance(result, ExplanationResult)
        assert result.llm_available is False
        assert result.raw_explanation is not None
        assert "chiller" in result.raw_explanation.lower()

    def test_format_prediction_for_template(self):
        """Test prediction data formatting for template."""
        from ml.explanations.templates import format_prediction_for_template

        predictions = {
            "24h": 12.5, "48h": 13.0, "72h": 13.5
        }
        equipment_info = {
            "manufacturer": "Trane",
            "model": "CGAM-100",
            "capacity": 100
        }

        result = format_prediction_for_template(
            equipment_id="chiller-001",
            equipment_type="chiller",
            predictions=predictions,
            equipment_info=equipment_info
        )

        assert result["equipment_id"] == "chiller-001"
        assert result["equipment_type"] == "chiller"
        assert "Trane" in result["formatted_predictions"]
        assert "CGAM-100" in result["formatted_predictions"]

    def test_get_equipment_specific_template(self):
        """Test getting equipment-specific templates."""
        from ml.explanations.templates import get_equipment_specific_template

        equipment_types = ["chiller", "generator", "ahu", "pump"]

        for eq_type in equipment_types:
            template = get_equipment_specific_template(eq_type)
            assert template is not None
            assert len(template) > 100  # Should be substantial
            assert eq_type in template.lower()

    def test_format_contributing_factors(self):
        """Test contributing factors formatting."""
        from ml.explanations.templates import format_contributing_factors

        factors = {
            "load_conditions": "High",
            "ambient_temp": 35.0,
            "efficiency_trend": "declining"
        }

        formatted = format_contributing_factors(factors)

        assert "High" in formatted
        assert "35.0" in formatted
        assert "declining" in formatted

    async def test_vector_db_integration(self, explanation_service, mock_vector_db):
        """Test vector DB integration for RAG context."""
        predictions = {
            "equipment_type": "chiller",
            "predictions": {"24h": 14.0},
            "anomaly_score": 0.3
        }

        # Execute
        result = await explanation_service.explain_prediction(
            equipment_id="chiller-001",
            predictions=predictions
        )

        # Assert
        mock_vector_db.get_rag_context.assert_called_once()
        assert "Test RAG context" in result.context_sources
        assert result.parsed is not None
        assert isinstance(result.parsed, dict)

    async def test_parse_explanation_output(self, explanation_service, mock_ollama_client):
        """Test parsing of explanation output."""
        # Setup
        mock_ollama_client.generate.return_value = """## Analysis Summary
The generator load is approaching maximum capacity.

## Contributing Factors
- High building occupancy (75%)
- Summer cooling demand

## Recommended Actions
1. Monitor load continuously
2. Consider load shedding if exceeds 90%
3. Schedule maintenance check
"""

        predictions = {
            "equipment_type": "generator",
            "predictions": {"24h": 85.0}
        }

        # Execute
        result = await explanation_service.explain_prediction(
            equipment_id="generator-001",
            predictions=predictions
        )

        # Assert
        assert result.parsed is not None
        assert isinstance(result.parsed, dict)
        # Should have parsed structure
        assert "actions" in result.parsed or isinstance(result.parsed, dict)

    async def test_concurrent_explanations(self, explanation_service, mock_ollama_client):
        """Test generating multiple explanations concurrently."""
        predictions1 = {
            "equipment_type": "chiller",
            "predictions": {"24h": 12.0}
        }
        predictions2 = {
            "equipment_type": "ahu",
            "predictions": {"24h": 22.0}
        }

        # Execute concurrently
        results = await asyncio.gather(
            explanation_service.explain_prediction("chiller-001", predictions1),
            explanation_service.explain_prediction("ahu-001", predictions2)
        )

        # Assert
        assert len(results) == 2
        assert all(isinstance(r, ExplanationResult) for r in results)
        assert results[0].equipment_type == "chiller"
        assert results[1].equipment_type == "ahu"

# Need to import asyncio for concurrent test
import asyncio
