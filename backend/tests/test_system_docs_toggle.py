"""Tests for system documentation RAG toggle (controlled access).

Test cases:
1. Toggle OFF → only operational RAG used (search_system_documents excluded)
2. Toggle ON → system docs tool available
3. Toggle OFF + platform query → hint message suggested
4. Tech Chat → never uses system docs
"""

from __future__ import annotations

import pytest

from app.services.chat_tools import get_chat_tools, _SYSTEM_DOCS_GATED_TOOLS


def _tool_names(tools: list[dict]) -> set[str]:
    return {t["name"] for t in tools}


class TestSystemDocsToggle:
    """Toggle OFF excludes system docs tool; toggle ON includes it."""

    def test_toggle_off_excludes_system_docs_tool(self):
        """Test case 1: Toggle OFF → search_system_documents not in tools."""
        tools = get_chat_tools(include_system_docs=False)
        names = _tool_names(tools)

        assert "search_documents" in names, "Operational doc search must always be available"
        assert "search_system_documents" not in names, "System docs tool must be excluded when toggle is off"

    def test_toggle_on_includes_system_docs_tool(self):
        """Test case 2: Toggle ON → search_system_documents available."""
        tools = get_chat_tools(include_system_docs=True)
        names = _tool_names(tools)

        assert "search_documents" in names
        assert "search_system_documents" in names, "System docs tool must be available when toggle is on"

    def test_toggle_off_is_default(self):
        """Default get_chat_tools() call excludes system docs."""
        tools = get_chat_tools()
        names = _tool_names(tools)

        assert "search_system_documents" not in names

    def test_toggle_with_site_id_filters_correctly(self):
        """System docs gating works alongside site-based module filtering."""
        tools_off = get_chat_tools("site-002", include_system_docs=False)
        tools_on = get_chat_tools("site-002", include_system_docs=True)

        assert "search_system_documents" not in _tool_names(tools_off)
        assert "search_system_documents" in _tool_names(tools_on)


class TestPlatformDocHint:
    """Toggle OFF + platform query → backend suggests enabling platform docs."""

    def test_platform_query_detected(self):
        """Test case 3: platform-related question triggers hint detection."""
        from app.api.chat import _is_platform_doc_query

        assert _is_platform_doc_query("How do I upload a building into SENTINEL?")
        assert _is_platform_doc_query("How does the security architecture work?")
        assert _is_platform_doc_query("What compliance controls exist?")
        assert _is_platform_doc_query("How does onboarding work?")

    def test_operational_query_not_detected_as_platform(self):
        """Operational questions should NOT trigger the platform doc hint."""
        from app.api.chat import _is_platform_doc_query

        assert not _is_platform_doc_query("What issues were reported at Fairlands generators last month?")
        assert not _is_platform_doc_query("Show me chiller performance for site-002")
        assert not _is_platform_doc_query("What is the current power consumption?")


class TestTechChatGuardrail:
    """Tech Chat must never have access to system documentation tools."""

    def test_system_docs_gated_tools_defined(self):
        """Verify the gated tools set is properly defined."""
        assert "search_system_documents" in _SYSTEM_DOCS_GATED_TOOLS

    def test_tech_chat_scenario_no_system_docs(self):
        """Test case 4: Even with include_system_docs=True, Tech Chat
        should use its own tool set (not tested here — Tech Chat uses
        separate endpoints). This test verifies the guardrail constant
        is correctly maintained."""
        # Tech Chat uses TechnicianChat.tsx → separate API endpoints
        # that don't call get_chat_tools(). This test ensures the
        # system docs tool is properly gated in the main chat pipeline.
        tools = get_chat_tools(include_system_docs=False)
        for tool in tools:
            assert tool["name"] not in _SYSTEM_DOCS_GATED_TOOLS
