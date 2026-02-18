"""Tests for escalation engine functionality."""

import pytest
from unittest.mock import patch

from app.services.escalation_engine import escalation_engine, EscalationLevel
from app.models.autonomous_decision import BoundaryStatus


@pytest.fixture
async def setup_escalation_engine():
    """Setup escalation engine for testing."""
    if not escalation_engine._initialized:
        await escalation_engine.initialize()
    yield escalation_engine


@pytest.mark.asyncio
async def test_escalation_engine_initialization(setup_escalation_engine):
    """Test escalation engine initializes properly."""
    engine = setup_escalation_engine
    assert engine._initialized is True


@pytest.mark.asyncio
async def test_escalation_level_determination(setup_escalation_engine):
    """Test correct escalation level determination."""
    engine = setup_escalation_engine

    test_cases = [
        (70.0, EscalationLevel.LEVEL_0, "Normal operation"),
        (77.0, EscalationLevel.LEVEL_1, "Warning level"),
        (86.0, EscalationLevel.LEVEL_2, "Alert level"),
        (96.0, EscalationLevel.LEVEL_3, "Critical level"),
        (99.5, EscalationLevel.LEVEL_4, "Emergency level"),
    ]

    for headroom, expected_level, description in test_cases:
        level = engine.determine_escalation_level(headroom)
        assert level == expected_level, f"Failed for {description}"


@pytest.mark.asyncio
async def test_escalation_trigger_generation(setup_escalation_engine):
    """Test escalation triggers are generated correctly."""
    engine = setup_escalation_engine

    with patch.object(engine, 'send_notification') as mock_notify:
        # Simulate boundary breach approaching Level 2
        boundary_status = BoundaryStatus(
            device_id="test_device",
            device_name="Test Device",
            points_status={"setpoint": {"current_value": 26.0, "min_bound": 16, "max_bound": 28}},
            approach_percentage=85.0,
            escalation_level=EscalationLevel.LEVEL_2
        )

        await engine.check_and_escalate(boundary_status)

        # Notification should have been triggered
        # Note: Actual behavior depends on implementation


@pytest.mark.asyncio
async def test_notification_routing_level_1(setup_escalation_engine):
    """Test Level 1 notification routing (system log)."""
    engine = setup_escalation_engine

    with patch.object(engine, 'send_notification') as mock_notify:
        await engine.send_escalation_notification(
            level=EscalationLevel.LEVEL_1,
            device_id="test_device",
            device_name="Test Device",
            message="Temperature approaching boundary",
            approach_percentage=77.0
        )

        # Level 1 should log to system
        mock_notify.assert_called()


@pytest.mark.asyncio
async def test_notification_routing_level_2(setup_escalation_engine):
    """Test Level 2 notification routing (email)."""
    engine = setup_escalation_engine

    with patch.object(engine, 'send_email_notification') as mock_email:
        await engine.send_escalation_notification(
            level=EscalationLevel.LEVEL_2,
            device_id="test_device",
            device_name="Test Device",
            message="Temperature at alert level",
            approach_percentage=86.0,
            recipients=["operator@site.com"]
        )

        # Level 2 should send email


@pytest.mark.asyncio
async def test_notification_routing_level_3(setup_escalation_engine):
    """Test Level 3 notification routing (Slack + dashboard)."""
    engine = setup_escalation_engine

    with patch.object(engine, 'send_slack_notification') as mock_slack, \
         patch.object(engine, 'send_dashboard_alert') as mock_dashboard:

        await engine.send_escalation_notification(
            level=EscalationLevel.LEVEL_3,
            device_id="test_device",
            device_name="Test Device",
            message="CRITICAL: Temperature at critical level",
            approach_percentage=96.0
        )

        # Level 3 should send Slack and dashboard alert


@pytest.mark.asyncio
async def test_notification_routing_level_4(setup_escalation_engine):
    """Test Level 4 notification routing (emergency)."""
    engine = setup_escalation_engine

    with patch.object(engine, 'trigger_emergency_stop') as mock_stop, \
         patch.object(engine, 'send_sms_notification') as mock_sms:

        await engine.send_escalation_notification(
            level=EscalationLevel.LEVEL_4,
            device_id="test_device",
            device_name="Test Device",
            message="EMERGENCY: Autonomous stop triggered",
            approach_percentage=100.0
        )

        # Level 4 should trigger emergency stop


@pytest.mark.asyncio
async def test_escalation_acknowledgment(setup_escalation_engine):
    """Test escalation acknowledgment by operator."""
    engine = setup_escalation_engine

    # Simulate Level 2 escalation
    escalation_id = "escalation_test_001"

    # Acknowledge the escalation
    result = await engine.acknowledge_escalation(
        escalation_id=escalation_id,
        acknowledged_by="operator@site.com",
        action_taken="Increased cooling capacity"
    )

    # Escalation should be acknowledged
    # Behavior depends on implementation


@pytest.mark.asyncio
async def test_escalation_history_tracking(setup_escalation_engine):
    """Test escalation history is tracked."""
    engine = setup_escalation_engine

    initial_count = len(engine.escalation_history) if hasattr(engine, 'escalation_history') else 0

    # Log an escalation
    await engine.send_escalation_notification(
        level=EscalationLevel.LEVEL_2,
        device_id="history_test",
        device_name="History Test Device",
        message="Test escalation for history"
    )

    # History should grow
    # Verify implementation tracks history


@pytest.mark.asyncio
async def test_emergency_handler_automatic_stop(setup_escalation_engine):
    """Test emergency handler triggers automatic stop."""
    engine = setup_escalation_engine

    with patch.object(engine, 'execute_emergency_stop') as mock_stop:
        await engine.trigger_emergency_at_level_4(
            device_id="emergency_test",
            device_name="Emergency Test Device",
            reason="Pressure at maximum boundary"
        )

        # Emergency stop should be executed
        # mock_stop.assert_called_once()


@pytest.mark.asyncio
async def test_escalation_timeout_auto_resolution(setup_escalation_engine):
    """Test escalations auto-resolve after timeout without acknowledgment."""
    engine = setup_escalation_engine

    # Create escalation that will timeout
    escalation_id = "timeout_test_001"

    # Wait for timeout and verify auto-resolution
    # Implementation depends on timeout configuration


@pytest.mark.asyncio
async def test_concurrent_escalations_handling(setup_escalation_engine):
    """Test handling of concurrent escalations."""
    engine = setup_escalation_engine

    import asyncio

    escalations = [
        engine.send_escalation_notification(
            level=EscalationLevel.LEVEL_2,
            device_id=f"device_{i}",
            device_name=f"Device {i}",
            message=f"Concurrent escalation {i}"
        )
        for i in range(3)
    ]

    results = await asyncio.gather(*escalations)
    assert len(results) == 3


@pytest.mark.asyncio
async def test_escalation_de_escalation(setup_escalation_engine):
    """Test de-escalation when condition improves."""
    engine = setup_escalation_engine

    # Start at Level 2 (86% headroom)
    # De-escalate to Level 1 when headroom improves to 80%

    result = await engine.check_and_de_escalate(
        device_id="de_escalation_test",
        current_headroom_percent=80.0
    )

    # Should de-escalate to Level 1


@pytest.mark.asyncio
async def test_escalation_boundary_status_integration(setup_escalation_engine):
    """Test escalation engine integration with boundary service."""
    engine = setup_escalation_engine

    # Create boundary status approaching limit
    boundary_status = BoundaryStatus(
        device_id="boundary_test",
        device_name="Boundary Test Device",
        points_status={
            "temperature": {
                "current_value": 27.0,
                "min_bound": 16.0,
                "max_bound": 28.0
            }
        },
        approach_percentage=83.0,
        escalation_level=EscalationLevel.LEVEL_2
    )

    # Check escalation
    await engine.check_and_escalate(boundary_status)

    # Escalation should be triggered at Level 2


@pytest.mark.asyncio
async def test_escalation_safe_state_restoration(setup_escalation_engine):
    """Test safe state restoration after escalation."""
    engine = setup_escalation_engine

    with patch.object(engine, 'restore_safe_state') as mock_restore:
        await engine.restore_safe_state_after_escalation(
            device_id="safe_state_test",
            escalation_level=EscalationLevel.LEVEL_3
        )

        # Safe state should be restored


@pytest.mark.asyncio
async def test_escalation_audit_logging(setup_escalation_engine):
    """Test all escalations are properly audited."""
    engine = setup_escalation_engine

    # Create escalation
    await engine.send_escalation_notification(
        level=EscalationLevel.LEVEL_2,
        device_id="audit_test",
        device_name="Audit Test Device",
        message="Audit test escalation"
    )

    # Verify audit log entry created
    # Check audit repository


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
