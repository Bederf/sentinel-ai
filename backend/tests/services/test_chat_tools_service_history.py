"""Tests for get_equipment_service_history chat tool."""

from unittest.mock import MagicMock, patch

import pytest

from app.services.chat_tools_service_history import get_equipment_service_history


@pytest.fixture
def mock_supabase_client():
    """Patch get_supabase_client to return a magic mock."""
    with patch("app.services.chat_tools_service_history.get_supabase_client") as mock:
        yield mock.return_value


class TestGetEquipmentServiceHistory:
    """Test suite for get_equipment_service_history."""

    @pytest.mark.asyncio
    async def test_nominal_returns_history_records(self, mock_supabase_client):
        """Equipment found with knowledge records — returns them ordered by created_at DESC."""
        # Mock equipment lookup
        mock_equipment_resp = MagicMock()
        mock_equipment_resp.data = [{"code": "S002-GEN-001", "type": "GENERATOR"}]
        # Mock knowledge records
        mock_knowledge_resp = MagicMock()
        mock_knowledge_resp.data = [
            {
                "id": "kn-1",
                "knowledge_type": "service",
                "title": "Annual service",
                "description": "Oil change and filter replacement.",
                "source_document_id": "doc-abc",
                "confidence": "high",
                "created_at": "2025-11-01T10:00:00Z",
            },
            {
                "id": "kn-2",
                "knowledge_type": "repair",
                "title": "Fuel system repair",
                "description": "Replaced fuel pump.",
                "source_document_id": None,
                "confidence": "medium",
                "created_at": "2025-09-15T08:00:00Z",
            },
        ]
        # Mock documents lookup
        mock_docs_resp = MagicMock()
        mock_docs_resp.data = [{"id": "doc-abc", "source_url": "https://example.com/doc.pdf"}]

        mock_supabase_client.table.return_value.select.return_value.eq.return_value.execute.side_effect = [
            mock_equipment_resp,
            mock_knowledge_resp,
            mock_docs_resp,
        ]
        # Re-configure chain
        mock_table = mock_supabase_client.table.return_value
        mock_table.select.return_value.eq.return_value.execute.return_value = mock_equipment_resp
        mock_table.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = (
            mock_knowledge_resp
        )
        mock_table.select.return_value.in_.return_value.execute.return_value = mock_docs_resp

        result = await get_equipment_service_history("equip-uuid-123")

        assert result["success"] is True
        assert result["asset_id"] == "equip-uuid-123"
        assert result["equipment_code"] == "S002-GEN-001"
        assert result["equipment_type"] == "GENERATOR"
        assert result["total"] == 2
        assert len(result["history"]) == 2
        assert result["history"][0]["id"] == "kn-1"
        assert result["history"][0]["source_url"] == "https://example.com/doc.pdf"
        assert result["history"][1]["source_url"] is None

    @pytest.mark.asyncio
    async def test_empty_history_returns_empty_list(self, mock_supabase_client):
        """Equipment found but no knowledge records — returns empty history with success."""
        mock_equipment_resp = MagicMock()
        mock_equipment_resp.data = [{"code": "S002-VAV-101", "type": "VAV"}]
        mock_knowledge_resp = MagicMock()
        mock_knowledge_resp.data = []

        mock_table = mock_supabase_client.table.return_value
        mock_table.select.return_value.eq.return_value.execute.return_value = mock_equipment_resp
        mock_table.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = (
            mock_knowledge_resp
        )

        result = await get_equipment_service_history("equip-uuid-456")

        assert result["success"] is True
        assert result["history"] == []
        assert result["total"] == 0

    @pytest.mark.asyncio
    async def test_not_found_returns_error(self, mock_supabase_client):
        """Equipment ID not found in database — returns error dict."""
        mock_equipment_resp = MagicMock()
        mock_equipment_resp.data = []

        mock_table = mock_supabase_client.table.return_value
        mock_table.select.return_value.eq.return_value.execute.return_value = mock_equipment_resp

        result = await get_equipment_service_history("nonexistent-uuid")

        assert result["success"] is False
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_exception_returns_error_dict(self, mock_supabase_client):
        """Supabase raises an exception — returns {"success": False, "error": ...}."""
        mock_table = mock_supabase_client.table.return_value
        mock_table.select.return_value.eq.return_value.execute.side_effect = Exception("Connection timeout")

        result = await get_equipment_service_history("any-uuid")

        assert result["success"] is False
        assert "Connection timeout" in result["error"]
