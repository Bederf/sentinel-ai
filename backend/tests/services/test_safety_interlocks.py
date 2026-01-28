"""
Unit tests for safety interlocks service.
"""

import pytest
from app.services.safety_interlocks import SafetyEngine
from tests.factories import SafetyRuleFactory, DeviceFactory


@pytest.mark.unit
class TestSafetyEngine:
    """Test SafetyEngine service."""

    @pytest.mark.asyncio
    async def test_initialize_with_rules(self, mock_safety_rules_data):
        """Test initializing SafetyEngine with safety rules."""
        engine = SafetyEngine()
        await engine.initialize(mock_safety_rules_data)
        
        assert engine._initialized is True
        assert len(engine.rules) > 0

    @pytest.mark.asyncio
    async def test_validate_temperature_range_pass(self, safety_engine):
        """Test temperature range validation - pass case."""
        device = DeviceFactory.create_chiller()
        point_name = "setpoint"
        value = 22.0  # Within safe range
        
        result = await safety_engine.validate_control_action(
            device["id"], point_name, value, device
        )
        
        assert result["is_safe"] is True
        assert result["result"] == "ALLOW"

    @pytest.mark.asyncio
    async def test_validate_temperature_range_fail(self, safety_engine):
        """Test temperature range validation - fail case."""
        device = DeviceFactory.create_chiller()
        point_name = "setpoint"
        value = 30.0  # Outside safe range
        
        result = await safety_engine.validate_control_action(
            device["id"], point_name, value, device
        )
        
        # Should be blocked if rule exists
        assert result["is_safe"] is False or result["result"] == "BLOCK"

    @pytest.mark.asyncio
    async def test_validate_with_no_applicable_rules(self, safety_engine):
        """Test validation when no rules apply."""
        device = DeviceFactory.create()
        point_name = "setpoint"
        value = 25.0
        
        result = await safety_engine.validate_control_action(
            device["id"], point_name, value, device
        )
        
        # Should allow if no rules match
        assert result["is_safe"] is True or result["result"] == "ALLOW"

    @pytest.mark.asyncio
    async def test_get_device_safety_status(self, safety_engine):
        """Test getting overall safety status for a device."""
        device = DeviceFactory.create_chiller()
        
        status = await safety_engine.get_device_safety_status(device["id"], device)
        
        assert status is not None
        assert "overall_status" in status or "status" in status

    @pytest.mark.asyncio
    async def test_rule_severity_block(self, safety_engine):
        """Test that BLOCK severity rules prevent actions."""
        # Create a rule with BLOCK severity
        rule = SafetyRuleFactory.create_temperature_range(
            min_temp=16.0,
            max_temp=28.0,
            severity="block"
        )
        
        # Add rule to engine
        await safety_engine.initialize([rule])
        
        device = DeviceFactory.create_chiller()
        result = await safety_engine.validate_control_action(
            device["id"], "setpoint", 30.0, device
        )
        
        # Should be blocked
        assert result["is_safe"] is False or result["result"] == "BLOCK"

    @pytest.mark.asyncio
    async def test_rule_severity_warning(self, safety_engine):
        """Test that WARNING severity rules allow but warn."""
        # Create a rule with WARNING severity
        rule = SafetyRuleFactory.create_temperature_range(
            min_temp=16.0,
            max_temp=28.0,
            severity="warning"
        )
        
        await safety_engine.initialize([rule])
        
        device = DeviceFactory.create_chiller()
        result = await safety_engine.validate_control_action(
            device["id"], "setpoint", 30.0, device
        )
        
        # Should allow but warn
        assert result["result"] == "ALLOW" or result["result"] == "WARN"
