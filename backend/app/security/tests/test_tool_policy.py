"""Tests for Tool Policy Engine (137-07 Task 1).

Covers:
    - Unknown tool denied (default deny)
    - Tool tier classification
    - Tool result sanitization (summary for non-safe, full for safe)
    - Secret redaction in tool results
    - Safe tools echo full result
    - generate_tool_summary formatting
    - REGISTERED_TOOLS is union of all sets
"""

from app.security.tool_policy import (
    ANALYSIS_TOOLS,
    CONTROL_TOOLS,
    REGISTERED_TOOLS,
    SAFE_TO_ECHO_TOOLS,
    WRITE_TOOLS,
    generate_tool_summary,
    get_tool_tier,
    sanitize_tool_result,
    get_raw_result,
)


# ---------------------------------------------------------------------------
# Tier classification
# ---------------------------------------------------------------------------


class TestGetToolTier:
    def test_analysis_tools(self):
        assert get_tool_tier("list_devices") == "analysis"
        assert get_tool_tier("get_equipment_health") == "analysis"
        assert get_tool_tier("get_solar_overview") == "analysis"

    def test_control_tools(self):
        assert get_tool_tier("control_device") == "control"
        assert get_tool_tier("adjust_setpoint") == "control"
        assert get_tool_tier("reset_equipment_fault") == "control"

    def test_write_tools(self):
        assert get_tool_tier("create_work_order") == "write"
        assert get_tool_tier("discover_niagara_points") == "write"

    def test_unknown_tool_returns_unknown(self):
        assert get_tool_tier("nonexistent_tool") == "unknown"
        assert get_tool_tier("drop_database") == "unknown"
        assert get_tool_tier("") == "unknown"


# ---------------------------------------------------------------------------
# Default deny: unknown tools
# ---------------------------------------------------------------------------


class TestDefaultDeny:
    def test_unknown_tool_not_in_registered(self):
        assert "drop_database" not in REGISTERED_TOOLS
        assert "exec_shell" not in REGISTERED_TOOLS

    def test_registered_tools_is_union(self):
        expected = ANALYSIS_TOOLS | CONTROL_TOOLS | WRITE_TOOLS
        assert REGISTERED_TOOLS == expected

    def test_all_safe_tools_are_analysis(self):
        """Safe-to-echo tools must be a subset of analysis tools."""
        assert SAFE_TO_ECHO_TOOLS.issubset(ANALYSIS_TOOLS)


# ---------------------------------------------------------------------------
# Tool result summary
# ---------------------------------------------------------------------------


class TestGenerateToolSummary:
    def test_summary_with_success(self):
        result = {"success": True, "count": 5, "devices": [1, 2, 3, 4, 5]}
        summary = generate_tool_summary(result, "list_devices")
        assert "[list_devices]" in summary
        assert "success=True" in summary
        assert "count=5" in summary

    def test_summary_with_error(self):
        result = {"success": False, "error": "Device not found"}
        summary = generate_tool_summary(result, "control_device")
        assert "[control_device]" in summary
        assert "error=Device not found" in summary

    def test_summary_non_dict(self):
        summary = generate_tool_summary("plain string", "some_tool")
        assert "[some_tool]" in summary
        assert "non-dict" in summary

    def test_summary_with_status(self):
        result = {"status": "completed", "items": []}
        summary = generate_tool_summary(result, "create_work_order")
        assert "status=completed" in summary


# ---------------------------------------------------------------------------
# Result sanitization
# ---------------------------------------------------------------------------


class TestSanitizeToolResult:
    def test_safe_tools_echo_full_result(self):
        """Safe-to-echo tools should return the full result with _result_id."""
        result = {"success": True, "count": 3, "devices": ["a", "b", "c"]}
        sanitized = sanitize_tool_result(result, "list_devices")
        assert "_result_id" in sanitized
        assert sanitized.get("success") is True
        assert sanitized.get("count") == 3
        assert "_sanitized" not in sanitized

    def test_non_safe_tools_return_summary(self):
        """Non-safe tools should return a summary, not full result."""
        result = {"success": True, "work_order_id": "WO-123", "details": "sensitive"}
        sanitized = sanitize_tool_result(result, "create_work_order")
        assert "_result_id" in sanitized
        assert sanitized.get("_sanitized") is True
        assert "summary" in sanitized
        assert "work_order_id" not in sanitized  # Full data not exposed

    def test_control_tool_summarized(self):
        """Control tools should be summarized."""
        result = {"success": True, "device_id": "S002-VAV-101", "new_value": 22.0}
        sanitized = sanitize_tool_result(result, "control_device")
        assert sanitized.get("_sanitized") is True
        assert "summary" in sanitized

    def test_raw_result_stored(self):
        """Raw result should be stored server-side with result_id."""
        result = {"success": True, "data": "important"}
        sanitized = sanitize_tool_result(result, "get_device_details", result_id="test-123")
        assert sanitized["_result_id"] == "test-123"
        raw = get_raw_result("test-123")
        assert raw is not None
        assert raw["tool_name"] == "get_device_details"
        assert raw["result"]["data"] == "important"

    def test_tool_result_secrets_redacted(self):
        """Secrets in tool results should be redacted (via scan_output_for_secrets)."""
        # scan_output_for_secrets redacts fields like "password", "secret_key"
        result = {
            "success": True,
            "password": "super_secret_123",
            "data": "normal",
        }
        sanitized = sanitize_tool_result(result, "get_device_details")
        # The secret scanner should redact the password field
        # The result is safe-to-echo, so full result returned but password redacted
        if "password" in sanitized:
            assert sanitized["password"] != "super_secret_123"

    def test_custom_result_id(self):
        """Custom result_id should be used when provided."""
        result = {"success": True}
        sanitized = sanitize_tool_result(result, "list_devices", result_id="custom-id")
        assert sanitized["_result_id"] == "custom-id"

    def test_auto_generated_result_id(self):
        """Result ID should be auto-generated when not provided."""
        result = {"success": True}
        sanitized = sanitize_tool_result(result, "list_devices")
        assert "_result_id" in sanitized
        assert len(sanitized["_result_id"]) > 0


# ---------------------------------------------------------------------------
# Integration: tier + classification consistency
# ---------------------------------------------------------------------------


class TestToolSetConsistency:
    def test_no_overlap_between_tiers(self):
        """No tool should appear in more than one tier."""
        assert len(ANALYSIS_TOOLS & CONTROL_TOOLS) == 0
        assert len(ANALYSIS_TOOLS & WRITE_TOOLS) == 0
        assert len(CONTROL_TOOLS & WRITE_TOOLS) == 0

    def test_all_tools_classified(self):
        """Every tool in REGISTERED_TOOLS should have a non-unknown tier."""
        for tool in REGISTERED_TOOLS:
            tier = get_tool_tier(tool)
            assert tier != "unknown", f"Tool {tool} has unknown tier"
