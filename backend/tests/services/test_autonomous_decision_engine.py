"""Tests for autonomous decision engine core functionality."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.models.autonomous_decision import AutonomousDecision, DecisionStatus, EscalationLevel
from app.models.device import Device, DeviceEquipment, DeviceLocation, DevicePoint, DeviceType, PointType, ProtocolType
from app.services.autonomous_decision_engine import autonomous_decision_engine
from app.services.device_abstraction import device_manager
from app.services.safety_interlocks import safety_engine


def _make_test_device(device_id: str, point_name: str = "cooling_setpoint", default_value: float = 22.0):
    """Create a test Device with the given id and a single writable point."""
    point = DevicePoint(
        name=point_name,
        point_type=PointType.ANALOG_OUTPUT,
        description="Test setpoint",
        unit="°C",
        min_value=16.0,
        max_value=28.0,
        default_value=default_value,
        writable=True,
    )
    device = Device(
        id=device_id,
        name=f"Test Device {device_id}",
        device_type=DeviceType.HVAC,
        protocol=ProtocolType.MOCK,
        site_id="test-site-001",
        device_location=DeviceLocation(
            building="Test Building",
            floor="FL1",
            zone="Q1",
            room="MR1",
            description="Test location",
        ),
        equipment=DeviceEquipment(
            manufacturer="Test",
            model="Test-1000",
        ),
        points={point_name: point},
    )
    return device


@pytest.fixture
async def setup_autonomous_engine():
    """Setup autonomous decision engine for testing."""
    # Reset state so initialize() actually runs
    autonomous_decision_engine._initialized = False
    autonomous_decision_engine.decision_history.clear()
    autonomous_decision_engine.active_decisions.clear()
    autonomous_decision_engine._decision_callbacks.clear()
    autonomous_decision_engine.enabled = False

    # Initialize engine without demo data to start clean
    await autonomous_decision_engine.initialize(load_demo_data=False)
    yield autonomous_decision_engine

    # Cleanup
    autonomous_decision_engine.enabled = False
    autonomous_decision_engine.decision_history.clear()
    autonomous_decision_engine._initialized = False


@pytest.mark.asyncio
async def test_autonomous_engine_initialization(setup_autonomous_engine):
    """Test that autonomous engine initializes properly."""
    engine = setup_autonomous_engine
    assert engine._initialized is True
    assert isinstance(engine.decision_history, list)
    assert isinstance(engine.active_decisions, dict)


@pytest.mark.asyncio
async def test_enable_autonomous_mode(setup_autonomous_engine):
    """Test enabling autonomous mode."""
    engine = setup_autonomous_engine
    result = engine.enable_autonomous_mode()

    assert result["success"] is True
    assert engine.enabled is True
    assert "autonomous mode enabled" in result["message"].lower()


@pytest.mark.asyncio
async def test_disable_autonomous_mode(setup_autonomous_engine):
    """Test disabling autonomous mode."""
    engine = setup_autonomous_engine
    engine.enable_autonomous_mode()

    result = engine.disable_autonomous_mode()
    assert result["success"] is True
    assert engine.enabled is False


@pytest.mark.asyncio
async def test_decision_evaluation_and_execution(setup_autonomous_engine):
    """Test autonomous decision evaluation and execution."""
    engine = setup_autonomous_engine

    test_device = _make_test_device("hvac_test_001", "cooling_setpoint", 22.0)

    with (
        patch.object(safety_engine, "validate_control", new_callable=AsyncMock) as mock_validate,
        patch.object(device_manager, "list_devices", new_callable=AsyncMock) as mock_list,
        patch.object(device_manager, "write_device_value", new_callable=AsyncMock) as mock_write,
    ):
        # Setup mocks
        mock_list.return_value = [test_device]
        mock_validate.return_value = {
            "allowed": True,
            "reasons": [],
            "warnings": [],
            "rule_results": [],
        }
        mock_write.return_value = {"success": True}

        # Create test decision
        decision = await engine.evaluate_and_execute(
            rule_id="test_rule_001",
            device_id="hvac_test_001",
            point_name="cooling_setpoint",
            target_value=23.0,
            decision_rationale="Test energy optimization",
        )

        assert decision is not None
        assert decision.device_id == "hvac_test_001"
        assert decision.point_name == "cooling_setpoint"
        assert decision.target_value == 23.0
        assert decision.rule_triggered == "test_rule_001"


@pytest.mark.asyncio
async def test_decision_safety_validation_blocked(setup_autonomous_engine):
    """Test that unsafe decisions are blocked."""
    engine = setup_autonomous_engine

    test_device = _make_test_device("hvac_test_002", "cooling_setpoint", 22.0)

    with (
        patch.object(safety_engine, "validate_control", new_callable=AsyncMock) as mock_validate,
        patch.object(device_manager, "list_devices", new_callable=AsyncMock) as mock_list,
        patch.object(device_manager, "write_device_value", new_callable=AsyncMock) as mock_write,
    ):
        # Setup mocks to block decision
        mock_list.return_value = [test_device]
        mock_validate.return_value = {
            "allowed": False,
            "reasons": ["Temperature exceeds safe maximum of 28°C"],
            "warnings": [],
            "rule_results": [],
        }

        # Attempt unsafe decision
        decision = await engine.evaluate_and_execute(
            rule_id="unsafe_rule",
            device_id="hvac_test_002",
            point_name="cooling_setpoint",
            target_value=30.0,  # Unsafe value
            decision_rationale="Unsafe temperature",
        )

        # Should be blocked
        assert decision.status == DecisionStatus.BLOCKED
        mock_write.assert_not_called()  # Device should not be modified


@pytest.mark.asyncio
async def test_decision_history_persistence(setup_autonomous_engine):
    """Test decision history is maintained."""
    engine = setup_autonomous_engine

    with (
        patch.object(safety_engine, "validate_control", new_callable=AsyncMock) as mock_validate,
        patch.object(device_manager, "list_devices", new_callable=AsyncMock) as mock_list,
        patch.object(device_manager, "write_device_value", new_callable=AsyncMock) as mock_write,
    ):
        mock_validate.return_value = {
            "allowed": True,
            "reasons": [],
            "warnings": [],
            "rule_results": [],
        }
        mock_write.return_value = {"success": True}

        initial_count = len(engine.decision_history)

        # Create multiple decisions
        for i in range(3):
            test_device = _make_test_device(f"hvac_test_{i}", "cooling_setpoint", 22.0)
            mock_list.return_value = [test_device]

            await engine.evaluate_and_execute(
                rule_id=f"test_rule_{i}",
                device_id=f"hvac_test_{i}",
                point_name="cooling_setpoint",
                target_value=22.0 + i,
                decision_rationale=f"Test decision {i}",
            )

        # Verify history grew
        assert len(engine.decision_history) >= initial_count + 3


@pytest.mark.asyncio
async def test_get_decision_history_with_filtering(setup_autonomous_engine):
    """Test getting decision history with filters."""
    engine = setup_autonomous_engine

    test_device = _make_test_device("device_1", "setpoint", 22.0)

    with (
        patch.object(safety_engine, "validate_control", new_callable=AsyncMock) as mock_validate,
        patch.object(device_manager, "list_devices", new_callable=AsyncMock) as mock_list,
        patch.object(device_manager, "write_device_value", new_callable=AsyncMock) as mock_write,
    ):
        mock_list.return_value = [test_device]
        mock_validate.return_value = {
            "allowed": True,
            "reasons": [],
            "warnings": [],
            "rule_results": [],
        }
        mock_write.return_value = {"success": True}

        # Create decisions
        await engine.evaluate_and_execute(
            rule_id="rule_1", device_id="device_1", point_name="setpoint", target_value=23.0, decision_rationale="Test"
        )

        # Test filtering
        history = engine.get_decision_history(limit=10, offset=0)
        assert isinstance(history, list)
        assert len(history) > 0
        assert all(isinstance(d, AutonomousDecision) for d in history)


@pytest.mark.asyncio
async def test_system_status_retrieval(setup_autonomous_engine):
    """Test retrieving system status."""
    engine = setup_autonomous_engine
    engine.enable_autonomous_mode()

    status = await engine.get_system_status()

    assert status is not None
    assert status.enabled is True
    assert status.total_decisions_today >= 0
    assert status.last_decision_time is not None or status.total_decisions_today == 0


@pytest.mark.asyncio
async def test_decision_escalation_levels(setup_autonomous_engine):
    """Test escalation level values are properly defined."""
    engine = setup_autonomous_engine

    # Verify the escalation level enum values match expected thresholds
    assert EscalationLevel.NONE.value == 0  # Normal operation
    assert EscalationLevel.WARNING.value == 1  # 75% approach
    assert EscalationLevel.ALERT.value == 2  # 85% approach
    assert EscalationLevel.CRITICAL.value == 3  # 95% approach
    assert EscalationLevel.EMERGENCY.value == 4  # 100% breach

    # Verify ordering: each level is more severe than the previous
    levels = [
        EscalationLevel.NONE,
        EscalationLevel.WARNING,
        EscalationLevel.ALERT,
        EscalationLevel.CRITICAL,
        EscalationLevel.EMERGENCY,
    ]
    for i in range(len(levels) - 1):
        assert levels[i].value < levels[i + 1].value


@pytest.mark.asyncio
async def test_performance_metrics_tracking(setup_autonomous_engine):
    """Test that performance metrics are tracked."""
    engine = setup_autonomous_engine

    test_device = _make_test_device("perf_device", "setpoint", 22.0)

    with (
        patch.object(safety_engine, "validate_control", new_callable=AsyncMock) as mock_validate,
        patch.object(device_manager, "list_devices", new_callable=AsyncMock) as mock_list,
        patch.object(device_manager, "write_device_value", new_callable=AsyncMock) as mock_write,
    ):
        mock_list.return_value = [test_device]
        mock_validate.return_value = {
            "allowed": True,
            "reasons": [],
            "warnings": [],
            "rule_results": [],
        }
        mock_write.return_value = {"success": True}

        # Create decision with timing
        decision = await engine.evaluate_and_execute(
            rule_id="perf_test",
            device_id="perf_device",
            point_name="setpoint",
            target_value=23.0,
            decision_rationale="Performance test",
        )

        # Verify metrics captured
        assert decision.execution_time_ms is not None
        assert decision.execution_time_ms >= 0


@pytest.mark.asyncio
async def test_decision_error_handling(setup_autonomous_engine):
    """Test error handling in decision execution."""
    engine = setup_autonomous_engine

    test_device = _make_test_device("error_device", "setpoint", 22.0)

    with (
        patch.object(safety_engine, "validate_control", new_callable=AsyncMock) as mock_validate,
        patch.object(device_manager, "list_devices", new_callable=AsyncMock) as mock_list,
        patch.object(device_manager, "write_device_value", new_callable=AsyncMock) as mock_write,
    ):
        mock_list.return_value = [test_device]
        mock_validate.return_value = {
            "allowed": True,
            "reasons": [],
            "warnings": [],
            "rule_results": [],
        }
        # Simulate device error
        mock_write.side_effect = Exception("Device communication error")

        decision = await engine.evaluate_and_execute(
            rule_id="error_test",
            device_id="error_device",
            point_name="setpoint",
            target_value=23.0,
            decision_rationale="Error test",
        )

        # Should have failed status
        assert decision.status == DecisionStatus.FAILED
        assert "error" in decision.metadata.get("error", "").lower()


@pytest.mark.asyncio
async def test_concurrent_decisions(setup_autonomous_engine):
    """Test handling of concurrent autonomous decisions."""
    engine = setup_autonomous_engine

    # Create all test devices
    test_devices = [_make_test_device(f"device_{i}", "setpoint", 22.0) for i in range(5)]

    with (
        patch.object(safety_engine, "validate_control", new_callable=AsyncMock) as mock_validate,
        patch.object(device_manager, "list_devices", new_callable=AsyncMock) as mock_list,
        patch.object(device_manager, "write_device_value", new_callable=AsyncMock) as mock_write,
    ):
        mock_list.return_value = test_devices
        mock_validate.return_value = {
            "allowed": True,
            "reasons": [],
            "warnings": [],
            "rule_results": [],
        }
        mock_write.return_value = {"success": True}

        # Create concurrent decisions
        decisions = await asyncio.gather(
            *[
                engine.evaluate_and_execute(
                    rule_id=f"concurrent_{i}",
                    device_id=f"device_{i}",
                    point_name="setpoint",
                    target_value=22.0 + i * 0.5,
                    decision_rationale=f"Concurrent test {i}",
                )
                for i in range(5)
            ]
        )

        # Verify all completed
        assert len(decisions) == 5
        assert all(d is not None for d in decisions)


@pytest.mark.asyncio
async def test_demo_data_loading(setup_autonomous_engine):
    """Test loading demo data."""
    engine = setup_autonomous_engine

    # Reset initialized flag so initialize() runs again with demo data
    engine._initialized = False
    engine.decision_history.clear()
    await engine.initialize(load_demo_data=True)

    # Should have demo decisions
    assert len(engine.decision_history) > 0


@pytest.mark.asyncio
async def test_decision_callback_registration(setup_autonomous_engine):
    """Test callback registration for decision events."""
    engine = setup_autonomous_engine
    callback_called = False

    async def test_callback(decision):
        nonlocal callback_called
        callback_called = True

    await engine.add_decision_callback(test_callback)
    assert len(engine._decision_callbacks) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
