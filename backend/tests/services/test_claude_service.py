"""Tests for the Claude Service — RAG context injection and entity extraction."""

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from app.services.claude_service import (
    EQUIP_PLANT_PATTERN,
    EQUIP_ZONE_PATTERN,
    SITE_CODE_PATTERN,
    ClaudeService,
)


@pytest.fixture
def service():
    """Create ClaudeService instance without RAG service (prompt-only mode)."""
    return ClaudeService()


@pytest.fixture
def service_with_rag():
    """Create ClaudeService instance with mock RAG service."""
    mock_rag = Mock()
    mock_rag.get_context = AsyncMock(return_value="CHILLER-B1-001 is a 200kW machine. Last maintenance: 2026-01-15.")
    return ClaudeService(rag_service=mock_rag)


class TestExtractEntities:
    """Unit tests for _extract_entities() regex patterns."""

    def test_zone_equipment_id(self, service):
        """Zone equipment ID extracted with site and type."""
        result = service._extract_entities("What's the setpoint for S002-VAV-101?")
        assert result["equipment_id"] == "S002-VAV-101"
        assert result["site_id"] == "S002"
        assert result["equipment_type"] == "VAV"

    def test_plant_equipment_id(self, service):
        """Plant equipment ID extracted with site and type."""
        result = service._extract_entities("Help with S002-CHILLER-B1-001")
        assert result["equipment_id"] == "S002-CHILLER-B1-001"
        assert result["site_id"] == "S002"
        assert result["equipment_type"] == "CHILLER"

    def test_site_code_only(self, service):
        """Site code extracted when no equipment ID present."""
        result = service._extract_entities("Show me site-002 data")
        assert result["equipment_id"] is None
        assert result["site_id"] == "site-002"
        assert result["equipment_type"] is None

    def test_no_entities(self, service):
        """No entities returned for generic prompt."""
        result = service._extract_entities("What's the weather like?")
        assert result["equipment_id"] is None
        assert result["site_id"] is None
        assert result["equipment_type"] is None

    def test_equipment_type_extracted_from_plant(self, service):
        """Equipment type extracted from plant pattern."""
        result = service._extract_entities("Status of S002-SPLIT-EL-001")
        assert result["equipment_type"] == "SPLIT"

    def test_site_code_case_insensitive(self, service):
        """Site code matching is case-insensitive."""
        result = service._extract_entities("SITE-003 equipment status")
        assert result["site_id"] == "site-003"
        assert result["equipment_id"] is None

    def test_zone_pattern_edge_case(self, service):
        """Zone pattern handles edge cases like optional trailing dash."""
        result = service._extract_entities("S001-FCU-104 zone reading")
        assert result["equipment_id"] == "S001-FCU-104"
        assert result["equipment_type"] == "FCU"

    def test_zone_pattern_with_type_extraction(self, service):
        """Zone pattern correctly extracts equipment type from zone IDs."""
        result = service._extract_entities("S002-FCU-104A status")
        assert result["equipment_type"] == "FCU"

    def test_multiple_mentions_returns_first(self, service):
        """Only first match is returned (no multi-equipment support)."""
        result = service._extract_entities("Compare S002-VAV-101 and S002-VAV-102")
        assert result["equipment_id"] == "S002-VAV-101"
        assert result["site_id"] == "S002"

    def test_empty_prompt(self, service):
        """Empty prompt returns all None."""
        result = service._extract_entities("")
        assert result["equipment_id"] is None
        assert result["site_id"] is None
        assert result["equipment_type"] is None

    def test_patterns_directly(self):
        """Test regex patterns directly (not via service method)."""
        # Zone pattern
        assert EQUIP_ZONE_PATTERN.search("S002-VAV-101")
        assert EQUIP_ZONE_PATTERN.search("What's S002-FCU-005 status?")
        assert not EQUIP_ZONE_PATTERN.search("S002-CHILLER-B1-001")  # plant, not zone

        # Plant pattern
        assert EQUIP_PLANT_PATTERN.search("S002-CHILLER-B1-001")
        assert EQUIP_PLANT_PATTERN.search("S001-GEN-B1-001")

        # Site code pattern
        assert SITE_CODE_PATTERN.search("site-002")
        assert SITE_CODE_PATTERN.search("SITE-003")
        assert SITE_CODE_PATTERN.search("Site-001")
        assert not SITE_CODE_PATTERN.search("s002")  # no "site-" prefix


class TestBuildRagPrompt:
    """Integration tests for _build_rag_prompt() with mock RAG service."""

    @pytest.mark.asyncio
    async def test_rag_context_prepends_chunks(self, service_with_rag):
        """RAG context is prepended to prompt when entities detected."""
        entities = {
            "equipment_id": "S002-CHILLER-B1-001",
            "site_id": "S002",
            "equipment_type": "CHILLER",
        }
        prompt = "What is the capacity of this chiller?"
        result = await service_with_rag._build_rag_prompt(prompt, entities, "operator")

        assert "CHILLER-B1-001 is a 200kW machine" in result
        assert "What is the capacity" in result

    @pytest.mark.asyncio
    async def test_rag_returns_empty_fallback(self, service_with_rag):
        """Empty RAG result returns original prompt unchanged."""
        service_with_rag._rag_service.get_context = AsyncMock(return_value="")

        entities = {"equipment_id": "S002-VAV-101", "site_id": "S002", "equipment_type": "VAV"}
        prompt = "Setpoint for S002-VAV-101?"
        result = await service_with_rag._build_rag_prompt(prompt, entities, "operator")

        assert result == prompt

    @pytest.mark.asyncio
    async def test_rag_exception_proceeds_without_context(self, service_with_rag):
        """RAG exception is caught, warning logged, original prompt returned."""
        service_with_rag._rag_service.get_context = AsyncMock(side_effect=Exception("DB timeout"))

        entities = {"equipment_id": "S002-CHILLER-B1-001", "site_id": "S002", "equipment_type": "CHILLER"}
        prompt = "What is the capacity?"
        # Should not raise — graceful degradation
        result = await service_with_rag._build_rag_prompt(prompt, entities, "operator")

        assert result == prompt
        assert "200kW" not in result  # RAG context not injected

    @pytest.mark.asyncio
    async def test_no_rag_service_prompt_unchanged(self, service):
        """Without RAG service, prompt is returned unchanged."""
        entities = {"equipment_id": "S002-CHILLER-B1-001", "site_id": "S002", "equipment_type": "CHILLER"}
        prompt = "What is the capacity?"
        result = await service._build_rag_prompt(prompt, entities, "operator")

        assert result == prompt

    @pytest.mark.asyncio
    async def test_no_entities_returns_prompt_unchanged(self, service_with_rag):
        """When no entities detected, RAG is skipped and prompt returned as-is."""
        entities = {"equipment_id": None, "site_id": None, "equipment_type": None}
        prompt = "What's the weather?"
        result = await service_with_rag._build_rag_prompt(prompt, entities, "operator")

        assert result == prompt

    @pytest.mark.asyncio
    async def test_rag_timeout_proceeds_without_context(self, service_with_rag):
        """RAG timeout (2s) triggers warning and returns original prompt."""

        async def slow_get_context(*args, **kwargs):
            await asyncio.sleep(3)  # Simulate slow RAG
            return "Should not reach here"

        service_with_rag._rag_service.get_context = slow_get_context

        entities = {"equipment_id": "S002-CHILLER-B1-001", "site_id": "S002", "equipment_type": "CHILLER"}
        prompt = "What is the capacity?"
        result = await service_with_rag._build_rag_prompt(prompt, entities, "operator")

        # Original prompt returned intact
        assert result == prompt

    @pytest.mark.asyncio
    async def test_site_only_lookup(self, service_with_rag):
        """Site code without equipment ID uses site as query."""
        entities = {"equipment_id": None, "site_id": "site-002", "equipment_type": None}
        prompt = "Show site-002 overview"
        result = await service_with_rag._build_rag_prompt(prompt, entities, "operator")

        # RAG was called with site-002 as query
        service_with_rag._rag_service.get_context.assert_called_once()
        call_kwargs = service_with_rag._rag_service.get_context.call_args.kwargs
        assert call_kwargs["query"] == "site-002"
        assert call_kwargs["site_id"] == "site-002"
        assert call_kwargs["equipment_type"] is None

    @pytest.mark.asyncio
    async def test_rag_receives_user_role(self, service_with_rag):
        """User role is passed to RAG service for trust-level filtering."""
        entities = {"equipment_id": "S002-VAV-101", "site_id": "S002", "equipment_type": "VAV"}
        prompt = "Status of VAV-101"
        await service_with_rag._build_rag_prompt(prompt, entities, "admin")

        call_kwargs = service_with_rag._rag_service.get_context.call_args.kwargs
        assert call_kwargs["user_role"] == "admin"


class TestRagIntegrationWithStreamResponseWithTools:
    """Test RAG injection in the stream_response_with_tools entry point."""

    @pytest.mark.asyncio
    async def test_rag_augments_last_user_message(self, service_with_rag):
        """When last message is user with equip ID, RAG context is prepended."""
        messages = [{"role": "user", "content": "What's the setpoint for S002-VAV-101?"}]

        # We can't easily test the full streaming path without mocking the API client,
        # but we can verify that _extract_entities correctly identifies the entity
        # and _build_rag_prompt produces augmented content.
        entities = service_with_rag._extract_entities(messages[-1]["content"])
        assert entities["equipment_id"] == "S002-VAV-101"

        augmented = await service_with_rag._build_rag_prompt(messages[-1]["content"], entities, "operator")
        assert "Based on the following relevant documentation:" in augmented
        assert "What's the setpoint" in augmented

    @pytest.mark.asyncio
    async def test_no_rag_lookup_for_generic_prompt(self, service_with_rag):
        """No RAG lookup when prompt has no equipment or site entities."""
        messages = [{"role": "user", "content": "What is the current time?"}]

        entities = service_with_rag._extract_entities(messages[-1]["content"])
        assert entities["equipment_id"] is None
        assert entities["site_id"] is None

        # Without entities, _build_rag_prompt returns prompt unchanged
        result = await service_with_rag._build_rag_prompt(messages[-1]["content"], entities, "operator")
        assert result == messages[-1]["content"]
        # RAG service should NOT have been called
        service_with_rag._rag_service.get_context.assert_not_called()
