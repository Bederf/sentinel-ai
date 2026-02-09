#!/usr/bin/env python3
"""
Test script for discover_tridonic_gateway MCP tool.

Usage:
    cd /opt/bms-intelligence
    python -m pytest backend/test_discover_tridonic.py -v
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_discover_tridonic_gateway_simulated():
    """Test discover_tridonic_gateway with simulated data."""
    from backend.app.mcp.simbiot_server import discover_tridonic_gateway_tool

    # Test with simulated mode
    result = await discover_tridonic_gateway_tool(
        building_id="site-002",
        gateway_ip="192.168.10.50",
        gateway_type="tridonic",
        use_simulated=True
    )

    # Verify result structure
    assert result["success"] is True
    assert result["building_id"] == "site-002"
    assert result["gateway_ip"] == "192.168.10.50"
    assert result["gateway"] is not None
    assert result["gateway"]["simulated"] is True
    
    # Check equipment list
    assert result["total_devices"] > 0
    assert len(result["equipment_list"]) > 0
    assert result["devices_by_line"] is not None
    
    # Verify equipment codes follow v2.0 format
    for equipment in result["equipment_list"]:
        assert equipment["equipment_code"].startswith("S002-")
        assert "equipment_type" in equipment
        assert "dali_line" in equipment
        assert "dali_address" in equipment
    
    # Verify summary
    assert result["summary"]["luminaires"] > 0
    assert result["summary"]["controllers"] >= 0
    
    # Verify next steps are provided
    assert len(result["next_steps"]) > 0


@pytest.mark.asyncio
async def test_discover_tridonic_gateway_offline():
    """Test discover_tridonic_gateway with offline gateway (no simulated fallback)."""
    from backend.app.mcp.simbiot_server import discover_tridonic_gateway_tool

    # Test with offline gateway and no simulated mode
    result = await discover_tridonic_gateway_tool(
        building_id="site-003",
        gateway_ip="192.168.10.99",
        gateway_type="tridonic",
        use_simulated=False
    )

    # Should fail gracefully
    assert result["success"] is False
    assert result["error"] is not None
    assert "offline" in result["error"].lower() or "unreachable" in result["error"].lower()
    assert len(result["next_steps"]) > 0


@pytest.mark.asyncio
async def test_discover_tridonic_gateway_equipment_code_format():
    """Test that equipment codes follow v2.0 naming convention."""
    from backend.app.mcp.simbiot_server import discover_tridonic_gateway_tool

    result = await discover_tridonic_gateway_tool(
        building_id="site-005",
        gateway_ip="192.168.10.50",
        use_simulated=True
    )

    assert result["success"] is True
    
    # Check equipment code formats
    dali_codes = [e for e in result["equipment_list"] if e["equipment_type"] == "DALI"]
    lum_codes = [e for e in result["equipment_list"] if e["equipment_type"] == "LUM"]
    
    # DALI controllers: S{site}-DALI-L{line}-{addr:02d}
    for code_entry in dali_codes:
        code = code_entry["equipment_code"]
        # Format: S005-DALI-L1-01
        import re
        assert re.match(r'^S\d{3}-DALI-L\d+-\d{2}$', code), f"Invalid DALI code: {code}"
    
    # Luminaires: S{site}-LUM-L{line}-{seq:03d}
    for code_entry in lum_codes:
        code = code_entry["equipment_code"]
        # Format: S005-LUM-L1-001
        import re
        assert re.match(r'^S\d{3}-LUM-L\d+-\d{3}$', code), f"Invalid LUM code: {code}"


@pytest.mark.asyncio
async def test_discover_tridonic_gateway_different_building_id_formats():
    """Test equipment code generation with different building ID formats."""
    from backend.app.mcp.simbiot_server import discover_tridonic_gateway_tool

    test_cases = [
        ("site-001", "S001"),
        ("site-099", "S099"),
        ("site-123", "S123"),
    ]

    for building_id, expected_site_code in test_cases:
        result = await discover_tridonic_gateway_tool(
            building_id=building_id,
            gateway_ip="192.168.10.50",
            use_simulated=True
        )

        assert result["success"] is True
        if result["equipment_list"]:
            # Check first equipment code starts with expected site code
            first_code = result["equipment_list"][0]["equipment_code"]
            assert first_code.startswith(expected_site_code + "-"), f"Expected {expected_site_code} prefix in {first_code}"


@pytest.mark.asyncio
async def test_discover_tridonic_gateway_summary_counts():
    """Test that summary counts match equipment list."""
    from backend.app.mcp.simbiot_server import discover_tridonic_gateway_tool

    result = await discover_tridonic_gateway_tool(
        building_id="site-002",
        gateway_ip="192.168.10.50",
        use_simulated=True
    )

    assert result["success"] is True
    
    # Count equipment by type
    counted = {
        "controllers": len([e for e in result["equipment_list"] if e["equipment_type"] == "DALI"]),
        "luminaires": len([e for e in result["equipment_list"] if e["equipment_type"] == "LUM"]),
        "sensors": len([e for e in result["equipment_list"] if e["equipment_type"] == "PIR"]),
        "other": 0
    }
    
    # Verify summary matches count
    assert result["summary"]["controllers"] == counted["controllers"]
    assert result["summary"]["luminaires"] == counted["luminaires"]
    assert result["summary"]["sensors"] == counted["sensors"]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
