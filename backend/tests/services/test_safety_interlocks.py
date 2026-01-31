"""
Unit tests for safety interlocks service.
"""

import pytest
from app.services.safety_interlocks import SafetyEngine, safety_engine
from app.models.device import create_device_from_dict
from tests.factories import SafetyRuleFactory, DeviceFactory


@pytest.mark.unit
class TestSafetyEngineExists:
    """Test SafetyEngine service exists and has correct structure."""

    def test_safety_engine_exists(self):
        """Test safety engine singleton exists."""
        assert safety_engine is not None

    def test_safety_engine_has_required_methods(self):
        """Test SafetyEngine has all required methods."""
        engine = SafetyEngine()

        # Initialization
        assert hasattr(engine, 'initialize')
        assert hasattr(engine, 'load_rules_from_repository')
        assert hasattr(engine, 'load_rules_from_file')
        assert hasattr(engine, 'save_rules_to_file')

        # Rule management
        assert hasattr(engine, 'add_rule')
        assert hasattr(engine, 'remove_rule')
        assert hasattr(engine, 'get_rule')
        assert hasattr(engine, 'list_rules')
        assert hasattr(engine, 'get_rules_for_device')

        # Validation
        assert hasattr(engine, 'validate_control')
        assert hasattr(engine, 'get_device_safety_status')


@pytest.mark.unit
class TestSafetyEngineInitialization:
    """Test SafetyEngine initialization."""

    @pytest.mark.asyncio
    async def test_initialize_with_empty_rules(self):
        """Test initializing SafetyEngine with empty rules list."""
        engine = SafetyEngine()
        engine._initialized = False
        engine.rules = {}

        await engine.initialize([])

        assert engine._initialized is True

    @pytest.mark.asyncio
    async def test_initialize_is_idempotent(self):
        """Test multiple initialize calls are safe."""
        engine = SafetyEngine()

        await engine.initialize([])
        await engine.initialize([])  # Second call should be no-op

        assert engine._initialized is True

    @pytest.mark.asyncio
    async def test_initialize_with_rules(self, mock_safety_rules_data):
        """Test initializing SafetyEngine with safety rules."""
        engine = SafetyEngine()
        engine._initialized = False
        engine.rules = {}

        await engine.initialize(mock_safety_rules_data)

        assert engine._initialized is True
        # May or may not have rules depending on mock data
        assert isinstance(engine.rules, dict)


@pytest.mark.unit
class TestSafetyValidation:
    """Test safety validation functionality."""

    @pytest.mark.asyncio
    async def test_validate_control_returns_dict(self, safety_engine):
        """Test validate_control returns proper structure."""
        # Create a device from factory data
        device_data = DeviceFactory.create_chiller()
        device = create_device_from_dict(device_data)

        result = await safety_engine.validate_control(
            device, "setpoint", 22.0
        )

        assert isinstance(result, dict)
        assert "allowed" in result

    @pytest.mark.asyncio
    async def test_validate_control_safe_value(self, safety_engine):
        """Test temperature range validation - pass case."""
        device_data = DeviceFactory.create_chiller()
        device = create_device_from_dict(device_data)

        # 7.0 is within chiller safe range (5-15°C)
        result = await safety_engine.validate_control(
            device, "setpoint", 7.0
        )

        # Should be allowed (no rules or passes rules)
        assert result["allowed"] is True

    @pytest.mark.asyncio
    async def test_validate_control_with_no_applicable_rules(self, safety_engine):
        """Test validation when no rules apply."""
        device_data = DeviceFactory.create()
        device = create_device_from_dict(device_data)

        result = await safety_engine.validate_control(
            device, "some_unknown_point", 25.0
        )

        # Should allow if no rules match
        assert result["allowed"] is True


@pytest.mark.unit
class TestSafetyStatus:
    """Test device safety status functionality."""

    @pytest.mark.asyncio
    async def test_get_device_safety_status(self, safety_engine):
        """Test getting overall safety status for a device."""
        device_data = DeviceFactory.create_chiller()
        device = create_device_from_dict(device_data)

        status = await safety_engine.get_device_safety_status(device)

        assert status is not None
        assert isinstance(status, dict)
        assert "overall_status" in status or "device_id" in status

    @pytest.mark.asyncio
    async def test_get_device_safety_status_returns_point_statuses(self, safety_engine):
        """Test safety status includes point-level information."""
        device_data = DeviceFactory.create_chiller()
        device = create_device_from_dict(device_data)

        status = await safety_engine.get_device_safety_status(device)

        # Should have point_statuses or similar
        assert "point_statuses" in status or "overall_status" in status


@pytest.mark.unit
class TestRuleManagement:
    """Test rule management functionality."""

    @pytest.mark.asyncio
    async def test_add_rule(self):
        """Test adding a safety rule."""
        engine = SafetyEngine()
        engine._initialized = False
        engine.rules = {}
        await engine.initialize([])

        rule_data = SafetyRuleFactory.create_temperature_range(
            rule_id="test-add-rule",
            min_temp=16.0,
            max_temp=28.0
        )

        rule = await engine.add_rule(rule_data)

        assert rule is not None
        assert "test-add-rule" in engine.rules

    @pytest.mark.asyncio
    async def test_remove_rule(self):
        """Test removing a safety rule."""
        engine = SafetyEngine()
        engine._initialized = False
        engine.rules = {}
        await engine.initialize([])

        # Add then remove
        rule_data = SafetyRuleFactory.create_temperature_range(
            rule_id="test-remove-rule"
        )
        await engine.add_rule(rule_data)
        assert "test-remove-rule" in engine.rules

        result = await engine.remove_rule("test-remove-rule")

        assert result is True
        assert "test-remove-rule" not in engine.rules

    @pytest.mark.asyncio
    async def test_get_rule(self):
        """Test getting a rule by ID."""
        engine = SafetyEngine()
        engine._initialized = False
        engine.rules = {}
        await engine.initialize([])

        rule_data = SafetyRuleFactory.create_temperature_range(
            rule_id="test-get-rule"
        )
        await engine.add_rule(rule_data)

        rule = await engine.get_rule("test-get-rule")

        assert rule is not None
        assert rule.id == "test-get-rule"

    @pytest.mark.asyncio
    async def test_list_rules(self):
        """Test listing all rules."""
        engine = SafetyEngine()
        engine._initialized = False
        engine.rules = {}
        await engine.initialize([])

        rules = await engine.list_rules()

        assert isinstance(rules, list)


@pytest.mark.unit
class TestRulesForDevice:
    """Test getting rules applicable to a device."""

    @pytest.mark.asyncio
    async def test_get_rules_for_device(self, safety_engine):
        """Test getting rules for a specific device."""
        device_data = DeviceFactory.create_chiller()
        device = create_device_from_dict(device_data)

        rules = await safety_engine.get_rules_for_device(device)

        assert isinstance(rules, list)

    @pytest.mark.asyncio
    async def test_get_rules_for_device_with_point(self, safety_engine):
        """Test getting rules for a specific device and point."""
        device_data = DeviceFactory.create_chiller()
        device = create_device_from_dict(device_data)

        rules = await safety_engine.get_rules_for_device(device, "setpoint")

        assert isinstance(rules, list)
