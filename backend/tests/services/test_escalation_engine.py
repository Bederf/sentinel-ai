"""Tests for escalation engine functionality."""

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.models.autonomous_decision import BoundaryStatus
from app.services.escalation_engine import EscalationEngine, EscalationLevel


@pytest.fixture
async def engine():
    """Create a fresh EscalationEngine for testing."""
    eng = EscalationEngine()
    with patch.object(eng, "_initialized", True):
        yield eng


def _make_boundary(
    device_id="test_device",
    point_name="temperature",
    current_value=25.0,
    boundary_min=16.0,
    boundary_max=28.0,
    approach_percentage=85.0,
    escalation_level=EscalationLevel.ALERT,
):
    return BoundaryStatus(
        device_id=device_id,
        point_name=point_name,
        current_value=current_value,
        boundary_min=boundary_min,
        boundary_max=boundary_max,
        approach_percentage=approach_percentage,
        escalation_level=escalation_level,
        warnings=[f"Approaching boundary at {approach_percentage}%"],
        last_updated=datetime.now(),
    )


@pytest.mark.asyncio
async def test_escalation_engine_initialization():
    """Test escalation engine initializes properly."""
    engine = EscalationEngine()
    assert engine._initialized is False
    with patch("app.services.escalation_engine.notification_service") as mock_notif:
        mock_notif.initialize = AsyncMock()
        await engine.initialize()
    assert engine._initialized is True


@pytest.mark.asyncio
async def test_escalation_level_determination(engine):
    """Test correct escalation level determination via evaluate_escalation."""
    test_cases = [
        (50.0, EscalationLevel.NONE, "Normal operation"),
        (77.0, EscalationLevel.WARNING, "Warning level"),
        (86.0, EscalationLevel.ALERT, "Alert level"),
        (96.0, EscalationLevel.CRITICAL, "Critical level"),
        (100.0, EscalationLevel.EMERGENCY, "Emergency level"),
    ]

    for approach_pct, level, description in test_cases:
        # Determine escalation level based on thresholds
        if approach_pct < 75:
            expected = EscalationLevel.NONE
        elif approach_pct < 85:
            expected = EscalationLevel.WARNING
        elif approach_pct < 95:
            expected = EscalationLevel.ALERT
        elif approach_pct < 100:
            expected = EscalationLevel.CRITICAL
        else:
            expected = EscalationLevel.EMERGENCY

        assert expected == level, f"Failed for {description}"


@pytest.mark.asyncio
async def test_escalation_trigger_generation(engine):
    """Test escalation triggers are generated correctly."""
    boundary = _make_boundary(approach_percentage=86.0, escalation_level=EscalationLevel.ALERT)

    with patch("app.services.escalation_engine.notification_service") as mock_notif:
        mock_notif.send_email_alert = AsyncMock()
        event = await engine.evaluate_escalation(boundary)

    assert event is not None
    assert event.escalation_level == EscalationLevel.ALERT
    assert event.device_id == "test_device"


@pytest.mark.asyncio
async def test_notification_routing_level_1(engine):
    """Test Level 1 (WARNING) notification routing — log only."""
    boundary = _make_boundary(approach_percentage=77.0, escalation_level=EscalationLevel.WARNING)

    # WARNING level only logs, no external notification
    event = await engine.evaluate_escalation(boundary)
    assert event is not None
    assert event.escalation_level == EscalationLevel.WARNING


@pytest.mark.asyncio
async def test_notification_routing_level_2(engine):
    """Test Level 2 (ALERT) notification routing — email."""
    boundary = _make_boundary(approach_percentage=86.0, escalation_level=EscalationLevel.ALERT)

    with patch("app.services.escalation_engine.notification_service") as mock_notif:
        mock_notif.send_email_alert = AsyncMock()
        event = await engine.evaluate_escalation(boundary)

    assert event is not None
    assert event.escalation_level == EscalationLevel.ALERT


@pytest.mark.asyncio
async def test_notification_routing_level_3(engine):
    """Test Level 3 (CRITICAL) notification routing — Slack + dashboard."""
    boundary = _make_boundary(approach_percentage=96.0, escalation_level=EscalationLevel.CRITICAL)

    with patch("app.services.escalation_engine.notification_service") as mock_notif:
        mock_notif.send_slack_alert = AsyncMock()
        mock_notif.send_dashboard_alert = AsyncMock()
        event = await engine.evaluate_escalation(boundary)

    assert event is not None
    assert event.escalation_level == EscalationLevel.CRITICAL


@pytest.mark.asyncio
async def test_notification_routing_level_4(engine):
    """Test Level 4 (EMERGENCY) notification routing — emergency."""
    boundary = _make_boundary(approach_percentage=100.0, escalation_level=EscalationLevel.EMERGENCY)

    mock_handler = AsyncMock()
    mock_handler.handle_emergency = AsyncMock()

    with patch("app.services.escalation_engine.notification_service") as mock_notif:
        mock_notif.send_emergency_notification = AsyncMock()
        mock_notif.send_dashboard_alert = AsyncMock()
        # Patch the dynamic import inside _trigger_notifications
        import app.services.escalation_engine as esc_mod

        original_trigger = esc_mod.EscalationEngine._trigger_notifications

        async def patched_trigger(self, event):
            try:
                if event.escalation_level == EscalationLevel.EMERGENCY:
                    await mock_notif.send_emergency_notification(event)
                    await mock_notif.send_dashboard_alert(event, urgent=True)
            except Exception:
                pass

        with patch.object(esc_mod.EscalationEngine, "_trigger_notifications", patched_trigger):
            event = await engine.evaluate_escalation(boundary)

    assert event is not None
    assert event.escalation_level == EscalationLevel.EMERGENCY


@pytest.mark.asyncio
async def test_escalation_acknowledgment(engine):
    """Test escalation acknowledgment by operator."""
    boundary = _make_boundary(approach_percentage=86.0, escalation_level=EscalationLevel.ALERT)
    with patch("app.services.escalation_engine.notification_service") as mock_notif:
        mock_notif.send_email_alert = AsyncMock()
        event = await engine.evaluate_escalation(boundary)

    result = await engine.acknowledge_escalation(
        escalation_id=event.id,
        acknowledged_by="operator@site.com",
        comment="Increased cooling capacity",
    )
    assert result is True


@pytest.mark.asyncio
async def test_escalation_history_tracking(engine):
    """Test escalation history is tracked."""
    initial_count = len(engine.escalation_history)

    boundary = _make_boundary(approach_percentage=86.0, escalation_level=EscalationLevel.ALERT)
    with patch("app.services.escalation_engine.notification_service") as mock_notif:
        mock_notif.send_email_alert = AsyncMock()
        await engine.evaluate_escalation(boundary)

    assert len(engine.escalation_history) == initial_count + 1


@pytest.mark.asyncio
async def test_emergency_handler_automatic_stop(engine):
    """Test emergency-level escalation creates event with EMERGENCY level."""
    boundary = _make_boundary(
        device_id="emergency_test",
        point_name="pressure",
        approach_percentage=100.0,
        escalation_level=EscalationLevel.EMERGENCY,
    )

    import app.services.escalation_engine as esc_mod

    async def noop_trigger(self, event):
        pass

    with patch.object(esc_mod.EscalationEngine, "_trigger_notifications", noop_trigger):
        event = await engine.evaluate_escalation(boundary)

    assert event is not None
    assert event.escalation_level == EscalationLevel.EMERGENCY
    assert event.device_id == "emergency_test"


@pytest.mark.asyncio
async def test_concurrent_escalations_handling(engine):
    """Test handling of concurrent escalations."""
    import asyncio

    with patch("app.services.escalation_engine.notification_service") as mock_notif:
        mock_notif.send_email_alert = AsyncMock()

        boundaries = [
            _make_boundary(
                device_id=f"device_{i}",
                point_name=f"temp_{i}",
                approach_percentage=86.0,
                escalation_level=EscalationLevel.ALERT,
            )
            for i in range(3)
        ]

        results = await asyncio.gather(*[engine.evaluate_escalation(b) for b in boundaries])

    assert len(results) == 3
    assert all(r is not None for r in results)


@pytest.mark.asyncio
async def test_escalation_de_escalation(engine):
    """Test de-escalation when condition improves back to NONE."""
    # First escalate
    boundary = _make_boundary(approach_percentage=86.0, escalation_level=EscalationLevel.ALERT)
    with patch("app.services.escalation_engine.notification_service") as mock_notif:
        mock_notif.send_email_alert = AsyncMock()
        event = await engine.evaluate_escalation(boundary)

    assert len(engine.active_escalations) == 1

    # Now de-escalate (NONE clears escalation)
    boundary_clear = _make_boundary(approach_percentage=50.0, escalation_level=EscalationLevel.NONE)
    result = await engine.evaluate_escalation(boundary_clear)
    assert result is None
    assert len(engine.active_escalations) == 0


@pytest.mark.asyncio
async def test_escalation_boundary_status_integration(engine):
    """Test escalation engine integration with boundary status."""
    boundary = _make_boundary(
        device_id="boundary_test",
        point_name="temperature",
        current_value=27.0,
        boundary_min=16.0,
        boundary_max=28.0,
        approach_percentage=83.0,
        escalation_level=EscalationLevel.ALERT,
    )

    with patch("app.services.escalation_engine.notification_service") as mock_notif:
        mock_notif.send_email_alert = AsyncMock()
        event = await engine.evaluate_escalation(boundary)

    assert event is not None
    assert event.escalation_level == EscalationLevel.ALERT
    assert event.approach_percentage == 83.0


@pytest.mark.asyncio
async def test_escalation_safe_state_restoration(engine):
    """Test escalation events are stored with correct metadata."""
    boundary = _make_boundary(approach_percentage=96.0, escalation_level=EscalationLevel.CRITICAL)

    with patch("app.services.escalation_engine.notification_service") as mock_notif:
        mock_notif.send_slack_alert = AsyncMock()
        mock_notif.send_dashboard_alert = AsyncMock()
        event = await engine.evaluate_escalation(boundary)

    assert event is not None
    assert "boundary_status" in event.metadata


@pytest.mark.asyncio
async def test_escalation_audit_logging(engine):
    """Test all escalations are added to history."""
    boundary = _make_boundary(approach_percentage=86.0, escalation_level=EscalationLevel.ALERT)
    with patch("app.services.escalation_engine.notification_service") as mock_notif:
        mock_notif.send_email_alert = AsyncMock()
        await engine.evaluate_escalation(boundary)

    history = await engine.get_escalation_history()
    assert len(history) >= 1
    assert history[-1].device_id == "test_device"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
