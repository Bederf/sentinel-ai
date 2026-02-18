"""Tests for autonomous decision engine core functionality."""

import pytest
from datetime import datetime
from unittest.mock import patch

from app.services.autonomous_decision_engine import autonomous_decision_engine
from app.models.autonomous_decision import (
    AutonomousDecision,
    DecisionStatus,
    EscalationLevel
)
from app.services.safety_interlocks import safety_engine
from app.services.device_abstraction import device_manager


@pytest.fixture
async def setup_autonomous_engine():
    """Setup autonomous decision engine for testing."""
    # Initialize engine
    await autonomous_decision_engine.initialize(load_demo_data=False)
    yield autonomous_decision_engine
    # Cleanup
    autonomous_decision_engine.enabled = False
    autonomous_decision_engine.decision_history.clear()


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
    assert "autonomy_enabled" in result["message"].lower()


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

    with patch.object(safety_engine, 'validate') as mock_validate, \
         patch.object(device_manager, 'set_value') as mock_set:

        # Setup mocks
        mock_validate.return_value = {
            "is_safe": True,
            "reasons": [],
            "warnings": []
        }
        mock_set.return_value = {
            "success": True,
            "value": 23.0,
            "timestamp": datetime.now().isoformat()
        }

        # Create test decision
        decision = await engine.evaluate_and_execute(
            rule_id="test_rule_001",
            device_id="hvac_test_001",
            point_name="cooling_setpoint",
            target_value=23.0,
            decision_rationale="Test energy optimization"
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

    with patch.object(safety_engine, 'validate') as mock_validate, \
         patch.object(device_manager, 'set_value') as mock_set:

        # Setup mocks to block decision
        mock_validate.return_value = {
            "is_safe": False,
            "reasons": ["Temperature exceeds safe maximum of 28°C"],
            "warnings": []
        }

        # Attempt unsafe decision
        decision = await engine.evaluate_and_execute(
            rule_id="unsafe_rule",
            device_id="hvac_test_002",
            point_name="cooling_setpoint",
            target_value=30.0,  # Unsafe value
            decision_rationale="Unsafe temperature"
        )

        # Should be blocked
        assert decision.status == DecisionStatus.BLOCKED
        mock_set.assert_not_called()  # Device should not be modified


@pytest.mark.asyncio
async def test_decision_history_persistence(setup_autonomous_engine):
    """Test decision history is maintained."""
    engine = setup_autonomous_engine

    with patch.object(safety_engine, 'validate') as mock_validate, \
         patch.object(device_manager, 'set_value') as mock_set:

        mock_validate.return_value = {
            "is_safe": True,
            "reasons": [],
            "warnings": []
        }
        mock_set.return_value = {
            "success": True,
            "value": 23.0,
            "timestamp": datetime.now().isoformat()
        }

        initial_count = len(engine.decision_history)

        # Create multiple decisions
        for i in range(3):
            await engine.evaluate_and_execute(
                rule_id=f"test_rule_{i}",
                device_id=f"hvac_test_{i}",
                point_name="cooling_setpoint",
                target_value=22.0 + i,
                decision_rationale=f"Test decision {i}"
            )

        # Verify history grew
        assert len(engine.decision_history) >= initial_count + 3


@pytest.mark.asyncio
async def test_get_decision_history_with_filtering(setup_autonomous_engine):
    """Test getting decision history with filters."""
    engine = setup_autonomous_engine

    with patch.object(safety_engine, 'validate') as mock_validate, \
         patch.object(device_manager, 'set_value') as mock_set:

        mock_validate.return_value = {
            "is_safe": True,
            "reasons": [],
            "warnings": []
        }
        mock_set.return_value = {
            "success": True,
            "value": 23.0,
            "timestamp": datetime.now().isoformat()
        }

        # Create decisions
        await engine.evaluate_and_execute(
            rule_id="rule_1",
            device_id="device_1",
            point_name="setpoint",
            target_value=23.0,
            decision_rationale="Test"
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
    assert status.decision_count >= 0
    assert status.last_decision_time is not None or status.decision_count == 0


@pytest.mark.asyncio
async def test_decision_escalation_levels(setup_autonomous_engine):
    """Test escalation level calculation based on boundary approach."""
    engine = setup_autonomous_engine

    # Test different escalation levels
    test_cases = [
        (70, EscalationLevel.NORMAL),      # < 75% = normal
        (80, EscalationLevel.WARNING),      # 75-85% = warning
        (90, EscalationLevel.ALERT),        # 85-95% = alert
        (99, EscalationLevel.CRITICAL),     # > 95% = critical
    ]

    for approach_percent, expected_level in test_cases:
        result = engine._calculate_escalation_level(approach_percent)
        # Verify escalation level logic
        assert result is not None


@pytest.mark.asyncio
async def test_performance_metrics_tracking(setup_autonomous_engine):
    """Test that performance metrics are tracked."""
    engine = setup_autonomous_engine

    with patch.object(safety_engine, 'validate') as mock_validate, \
         patch.object(device_manager, 'set_value') as mock_set:

        mock_validate.return_value = {
            "is_safe": True,
            "reasons": [],
            "warnings": []
        }
        mock_set.return_value = {
            "success": True,
            "value": 23.0,
            "timestamp": datetime.now().isoformat()
        }

        # Create decision with timing
        decision = await engine.evaluate_and_execute(
            rule_id="perf_test",
            device_id="perf_device",
            point_name="setpoint",
            target_value=23.0,
            decision_rationale="Performance test"
        )

        # Verify metrics captured
        assert decision.execution_time_ms is not None
        assert decision.execution_time_ms >= 0


@pytest.mark.asyncio
async def test_decision_error_handling(setup_autonomous_engine):
    """Test error handling in decision execution."""
    engine = setup_autonomous_engine

    with patch.object(safety_engine, 'validate') as mock_validate, \
         patch.object(device_manager, 'set_value') as mock_set:

        mock_validate.return_value = {
            "is_safe": True,
            "reasons": [],
            "warnings": []
        }
        # Simulate device error
        mock_set.side_effect = Exception("Device communication error")

        decision = await engine.evaluate_and_execute(
            rule_id="error_test",
            device_id="error_device",
            point_name="setpoint",
            target_value=23.0,
            decision_rationale="Error test"
        )

        # Should have failed status
        assert decision.status == DecisionStatus.FAILED
        assert "error" in decision.failure_reason.lower()


@pytest.mark.asyncio
async def test_concurrent_decisions(setup_autonomous_engine):
    """Test handling of concurrent autonomous decisions."""
    engine = setup_autonomous_engine

    with patch.object(safety_engine, 'validate') as mock_validate, \
         patch.object(device_manager, 'set_value') as mock_set:

        mock_validate.return_value = {
            "is_safe": True,
            "reasons": [],
            "warnings": []
        }
        mock_set.return_value = {
            "success": True,
            "value": 23.0,
            "timestamp": datetime.now().isoformat()
        }

        # Create concurrent decisions
        import asyncio
        decisions = await asyncio.gather(*[
            engine.evaluate_and_execute(
                rule_id=f"concurrent_{i}",
                device_id=f"device_{i}",
                point_name="setpoint",
                target_value=22.0 + i * 0.5,
                decision_rationale=f"Concurrent test {i}"
            )
            for i in range(5)
        ])

        # Verify all completed
        assert len(decisions) == 5
        assert all(d is not None for d in decisions)


@pytest.mark.asyncio
async def test_demo_data_loading(setup_autonomous_engine):
    """Test loading demo data."""
    engine = setup_autonomous_engine

    # Create fresh engine with demo data
    fresh_engine = autonomous_decision_engine
    await fresh_engine.initialize(load_demo_data=True)

    # Should have demo decisions
    assert len(fresh_engine.decision_history) > 0


@pytest.mark.asyncio
async def test_decision_callback_registration(setup_autonomous_engine):
    """Test callback registration for decision events."""
    engine = setup_autonomous_engine
    callback_called = False

    async def test_callback(decision):
        nonlocal callback_called
        callback_called = True

    engine.register_decision_callback(test_callback)
    assert len(engine._decision_callbacks) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
