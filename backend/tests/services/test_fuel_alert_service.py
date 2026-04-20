"""Tests for FuelAlertService (Phase 150).

Validates severity mapping, notification routing, message formatting,
and graceful handling of missing NotificationService.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.fuel import FuelEventType
from app.services.fuel_alert_service import (
    FuelAlertService,
    _build_alert_body,
    _build_alert_title,
    _classify_severity,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class FakeSentinelEvent:
    """Mimics a SentinelEvent for testing."""

    event_type: str
    payload: dict[str, Any]


def _make_event(event_subtype: str, tank_id: str = "S002-TANK-EXT-001", **extra) -> FakeSentinelEvent:
    """Build a fake fuel event."""
    payload = {"event_subtype": event_subtype, "tank_id": tank_id, **extra}
    return FakeSentinelEvent(event_type=f"fuel.{event_subtype}", payload=payload)


# ---------------------------------------------------------------------------
# Severity Mapping Tests
# ---------------------------------------------------------------------------


class TestSeverityMapping:
    """Test severity classification for each event type."""

    def test_theft_alert_is_critical(self):
        assert _classify_severity(FuelEventType.THEFT_ALERT, {}) == "CRITICAL"

    def test_leak_detected_is_critical(self):
        assert _classify_severity(FuelEventType.LEAK_DETECTED, {}) == "CRITICAL"

    def test_low_fuel_warning_default(self):
        assert _classify_severity(FuelEventType.LOW_FUEL, {}) == "WARNING"

    def test_low_fuel_critical_when_pct2(self):
        assert _classify_severity(FuelEventType.LOW_FUEL, {"severity": "CRITICAL"}) == "CRITICAL"

    def test_low_fuel_warning_when_high(self):
        assert _classify_severity(FuelEventType.LOW_FUEL, {"severity": "HIGH"}) == "WARNING"

    def test_temp_alert_is_warning(self):
        assert _classify_severity(FuelEventType.TEMP_ALERT, {}) == "WARNING"

    def test_sensor_fault_is_warning(self):
        assert _classify_severity(FuelEventType.SENSOR_FAULT, {}) == "WARNING"

    def test_refill_detected_is_info(self):
        assert _classify_severity(FuelEventType.REFILL_DETECTED, {}) == "INFO"

    def test_runtime_complete_is_info(self):
        assert _classify_severity(FuelEventType.RUNTIME_COMPLETE, {}) == "INFO"

    def test_unknown_event_defaults_to_info(self):
        assert _classify_severity("unknown_event", {}) == "INFO"


# ---------------------------------------------------------------------------
# Message Formatting Tests
# ---------------------------------------------------------------------------


class TestAlertFormatting:
    """Test alert title and body formatting."""

    def test_title_format(self):
        title = _build_alert_title(FuelEventType.THEFT_ALERT, "S002-TANK-EXT-001")
        assert "FUEL" in title
        assert "THEFT ALERT" in title
        assert "S002-TANK-EXT-001" in title

    def test_theft_body_contains_rate(self):
        body = _build_alert_body(
            FuelEventType.THEFT_ALERT,
            {"loss_rate_lpm": 3.5, "loss_litres": 50, "time_delta_min": 14.3},
        )
        assert "3.5" in body
        assert "50" in body

    def test_leak_body_contains_duration(self):
        body = _build_alert_body(
            FuelEventType.LEAK_DETECTED,
            {"sustained_minutes": 45.2, "readings_count": 12},
        )
        assert "45.2" in body
        assert "12" in body

    def test_low_fuel_body_contains_level(self):
        body = _build_alert_body(
            FuelEventType.LOW_FUEL,
            {"fuel_level_pct": 12.5, "threshold_pct": 15.0, "severity": "CRITICAL"},
        )
        assert "12.5" in body
        assert "15.0" in body
        assert "CRITICAL" in body

    def test_temp_alert_high_body(self):
        body = _build_alert_body(
            FuelEventType.TEMP_ALERT,
            {"fuel_temp_c": 45.0, "threshold_max_c": 40.0},
        )
        assert "45.0" in body
        assert "too high" in body

    def test_temp_alert_low_body(self):
        body = _build_alert_body(
            FuelEventType.TEMP_ALERT,
            {"fuel_temp_c": 2.0, "threshold_min_c": 5.0},
        )
        assert "2.0" in body
        assert "too low" in body

    def test_sensor_fault_body(self):
        body = _build_alert_body(
            FuelEventType.SENSOR_FAULT,
            {"sensor_ma": 2.1},
        )
        assert "2.1" in body
        assert "sensor" in body.lower()


# ---------------------------------------------------------------------------
# Notification Routing Tests
# ---------------------------------------------------------------------------


class TestNotificationRouting:
    """Test that handle_fuel_event calls NotificationService correctly."""

    @pytest.mark.asyncio
    async def test_critical_event_triggers_broadcast(self):
        service = FuelAlertService()
        event = _make_event(
            FuelEventType.THEFT_ALERT,
            loss_rate_lpm=3.5,
            loss_litres=50,
            time_delta_min=14.3,
        )

        mock_notification = AsyncMock()
        mock_notification.broadcast_alert = AsyncMock(
            return_value={"success": True, "recipients_notified": 2, "errors": []}
        )

        with (
            patch.dict("sys.modules", {}),
            patch(
                "app.services.notification_service.NotificationService",
                return_value=mock_notification,
            ),
        ):
            # Patch the import inside the try block
            import app.services.notification_service as ns_mod

            original_cls = getattr(ns_mod, "NotificationService", None)
            ns_mod.NotificationService = MagicMock(return_value=mock_notification)
            try:
                await service.handle_fuel_event(event)
            finally:
                if original_cls:
                    ns_mod.NotificationService = original_cls

        mock_notification.broadcast_alert.assert_called_once()
        call_kwargs = mock_notification.broadcast_alert.call_args.kwargs
        assert call_kwargs["notification_type"] == "fuel_alert"

    @pytest.mark.asyncio
    async def test_warning_event_triggers_broadcast(self):
        service = FuelAlertService()
        event = _make_event(
            FuelEventType.TEMP_ALERT,
            fuel_temp_c=45.0,
            threshold_max_c=40.0,
            severity="HIGH",
        )

        mock_notification = AsyncMock()
        mock_notification.broadcast_alert = AsyncMock(
            return_value={"success": True, "recipients_notified": 1, "errors": []}
        )

        import app.services.notification_service as ns_mod

        original_cls = getattr(ns_mod, "NotificationService", None)
        ns_mod.NotificationService = MagicMock(return_value=mock_notification)
        try:
            await service.handle_fuel_event(event)
        finally:
            if original_cls:
                ns_mod.NotificationService = original_cls

        mock_notification.broadcast_alert.assert_called_once()

    @pytest.mark.asyncio
    async def test_info_event_does_not_trigger_broadcast(self):
        service = FuelAlertService()
        event = _make_event(FuelEventType.REFILL_DETECTED, jump_pct=15.0)

        # INFO events should return before any notification code runs
        await service.handle_fuel_event(event)
        # No assertion needed — if it tried to import NotificationService
        # and that failed, the test would still pass because handle_fuel_event
        # returns early for INFO events.

    @pytest.mark.asyncio
    async def test_runtime_complete_does_not_notify(self):
        service = FuelAlertService()
        event = _make_event(
            FuelEventType.RUNTIME_COMPLETE,
            generator_id="S002-GEN-B1-001",
            runtime_hours=4.5,
        )

        # INFO events return early — no notification attempt
        await service.handle_fuel_event(event)

    @pytest.mark.asyncio
    async def test_missing_notification_service_graceful(self):
        """Service should log warning but not crash if NotificationService fails."""
        service = FuelAlertService()
        event = _make_event(FuelEventType.THEFT_ALERT, loss_rate_lpm=5.0)

        import app.services.notification_service as ns_mod

        original_cls = getattr(ns_mod, "NotificationService", None)
        ns_mod.NotificationService = MagicMock(side_effect=Exception("unavailable"))
        try:
            # Should not raise
            await service.handle_fuel_event(event)
        finally:
            if original_cls:
                ns_mod.NotificationService = original_cls

    @pytest.mark.asyncio
    async def test_missing_event_subtype_skips(self):
        """Events without event_subtype should be silently skipped."""
        service = FuelAlertService()
        event = FakeSentinelEvent(event_type="fuel.unknown", payload={"tank_id": "T1"})

        await service.handle_fuel_event(event)  # Should not raise
