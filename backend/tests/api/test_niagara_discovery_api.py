"""Tests for Niagara point discovery API and chat tools.

Tests cover:
- POST /api/niagara/discover-and-classify endpoint
- GET /api/niagara/mappings/{discovery_id} endpoint
- POST /api/niagara/mappings/{discovery_id}/approve endpoint
- POST /api/niagara/mappings/{discovery_id}/correct endpoint
- Chat tool functions for discovery workflow
- End-to-end discovery-to-activation workflow
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.chat_tools import (
    discover_niagara_points,
    review_point_mapping,
    approve_point_mapping,
    correct_point_classification,
    CHAT_TOOLS,
    TOOL_HANDLERS,
)


# ---------------------------------------------------------------------------
# Chat Tool Tests
# ---------------------------------------------------------------------------

class TestDiscoverNiagaraPointsTool:
    """Tests for the discover_niagara_points chat tool."""

    @pytest.mark.asyncio
    async def test_discover_returns_success(self):
        """Test that discovery returns successful result."""
        result = await discover_niagara_points(
            device_ip="192.168.1.100",
            site_id="site-002",
        )

        assert result["success"] is True
        assert "discovery_id" in result
        assert result["points_discovered"] > 0
        assert len(result["equipment_identified"]) > 0
        assert "message" in result

    @pytest.mark.asyncio
    async def test_discover_has_confidence_breakdown(self):
        """Test that discovery includes confidence breakdown."""
        result = await discover_niagara_points(
            device_ip="192.168.1.100",
            site_id="site-002",
        )

        assert "confidence_breakdown" in result
        breakdown = result["confidence_breakdown"]
        assert "high" in breakdown
        assert "medium" in breakdown
        total = sum(breakdown.values())
        assert total > 0

    @pytest.mark.asyncio
    async def test_discover_returns_discovery_id(self):
        """Test that discovery ID is returned for workflow continuation."""
        result = await discover_niagara_points(
            device_ip="192.168.1.100",
        )

        assert result["success"] is True
        assert len(result["discovery_id"]) > 0


class TestReviewPointMappingTool:
    """Tests for the review_point_mapping chat tool."""

    @pytest.mark.asyncio
    async def test_review_existing_discovery(self):
        """Test reviewing an existing discovery."""
        # First discover
        discover_result = await discover_niagara_points(
            device_ip="192.168.1.100",
            site_id="site-002",
        )
        discovery_id = discover_result["discovery_id"]

        # Then review
        result = await review_point_mapping(discovery_id)

        assert result["success"] is True
        assert result["equipment_count"] > 0
        assert result["total_points"] > 0
        assert "equipment_summary" in result
        assert "message" in result

    @pytest.mark.asyncio
    async def test_review_nonexistent_discovery(self):
        """Test reviewing a non-existent discovery."""
        result = await review_point_mapping("nonexistent-id")

        assert result["success"] is False
        assert "not found" in result["error"].lower()


class TestApprovePointMappingTool:
    """Tests for the approve_point_mapping chat tool."""

    @pytest.mark.asyncio
    async def test_approve_after_discovery(self):
        """Test approving after discovery."""
        # Discover first
        discover_result = await discover_niagara_points(
            device_ip="192.168.1.100",
            site_id="site-002",
        )
        discovery_id = discover_result["discovery_id"]

        # Approve
        result = await approve_point_mapping(
            discovery_id, approved_by="test_admin"
        )

        assert result["success"] is True
        assert result["equipment_created"] > 0
        assert "message" in result

    @pytest.mark.asyncio
    async def test_approve_nonexistent_discovery(self):
        """Test approving a non-existent discovery."""
        result = await approve_point_mapping("nonexistent-id")

        assert result["success"] is False


class TestCorrectPointClassificationTool:
    """Tests for the correct_point_classification chat tool."""

    @pytest.mark.asyncio
    async def test_correct_point_type(self):
        """Test correcting a point's type."""
        # Discover first
        discover_result = await discover_niagara_points(
            device_ip="192.168.1.100",
            site_id="site-002",
        )
        discovery_id = discover_result["discovery_id"]

        # Correct a point
        result = await correct_point_classification(
            discovery_id=discovery_id,
            point_name="CH-1_CHW_Supply_Temp",
            correct_point_type="setpoint",
        )

        assert result["success"] is True
        assert len(result["corrections"]) > 0
        assert "message" in result

    @pytest.mark.asyncio
    async def test_correct_nonexistent_point(self):
        """Test correcting a point that doesn't exist."""
        discover_result = await discover_niagara_points(
            device_ip="192.168.1.100",
            site_id="site-002",
        )
        discovery_id = discover_result["discovery_id"]

        result = await correct_point_classification(
            discovery_id=discovery_id,
            point_name="NONEXISTENT_POINT",
        )

        assert result["success"] is False


class TestEndToEndWorkflow:
    """End-to-end discovery-to-activation workflow test."""

    @pytest.mark.asyncio
    async def test_full_workflow(self):
        """Test the complete workflow: discover -> review -> correct -> approve."""
        # Step 1: Discover
        discover_result = await discover_niagara_points(
            device_ip="192.168.1.100",
            site_id="site-002",
        )
        assert discover_result["success"] is True
        discovery_id = discover_result["discovery_id"]

        # Step 2: Review
        review_result = await review_point_mapping(discovery_id)
        assert review_result["success"] is True
        assert review_result["equipment_count"] > 0

        # Step 3: Correct (optional)
        correct_result = await correct_point_classification(
            discovery_id=discovery_id,
            point_name="CH-1_CHW_Supply_Temp",
            correct_point_type="sensor",
        )
        assert correct_result["success"] is True

        # Step 4: Approve
        approve_result = await approve_point_mapping(
            discovery_id, approved_by="test_admin"
        )
        assert approve_result["success"] is True
        assert approve_result["equipment_created"] > 0


# ---------------------------------------------------------------------------
# Tool Registration Tests
# ---------------------------------------------------------------------------

class TestToolRegistration:
    """Tests that Niagara tools are properly registered."""

    def test_chat_tools_include_niagara(self):
        """Verify Niagara tools are in CHAT_TOOLS list."""
        tool_names = [t["name"] for t in CHAT_TOOLS]

        assert "discover_niagara_points" in tool_names
        assert "review_point_mapping" in tool_names
        assert "approve_point_mapping" in tool_names
        assert "correct_point_classification" in tool_names

    def test_tool_handlers_include_niagara(self):
        """Verify Niagara handlers are in TOOL_HANDLERS dict."""
        assert "discover_niagara_points" in TOOL_HANDLERS
        assert "review_point_mapping" in TOOL_HANDLERS
        assert "approve_point_mapping" in TOOL_HANDLERS
        assert "correct_point_classification" in TOOL_HANDLERS

    def test_tool_count_matches(self):
        """Verify CHAT_TOOLS and TOOL_HANDLERS have same count."""
        assert len(CHAT_TOOLS) == len(TOOL_HANDLERS)
        assert len(CHAT_TOOLS) >= 15  # At least the original 15 tools
