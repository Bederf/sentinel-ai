"""Tests for recommendation Telegram notifications."""

from __future__ import annotations

import asyncio
import concurrent.futures
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestNotifyPendingRecommendations:
    @pytest.mark.asyncio
    async def test_notify_skips_warning_severity(self):
        """Warning severity rec does NOT trigger Telegram alert (only critical fires)."""
        from app.services.background_scheduler import BackgroundSchedulerService

        svc = BackgroundSchedulerService.__new__(BackgroundSchedulerService)
        svc.logger = MagicMock()

        ai_rec = MagicMock()
        ai_rec.priority.name.lower.return_value = "warning"
        ai_rec.telemetry_context = {"equipment_id": "S002-AHU-201"}
        ai_rec.title = "Bearing wear detected"
        ai_rec.confidence = 0.72
        ai_rec.suggested_action = {"type": "pending_approval"}

        svc._notify_recommendation_alert("S002", ai_rec)

    @pytest.mark.asyncio
    async def test_notify_sends_telegram_for_high_severity(self):
        """High severity rec now triggers Telegram alert (not just critical)."""
        from app.services.background_scheduler import BackgroundSchedulerService

        svc = BackgroundSchedulerService.__new__(BackgroundSchedulerService)
        svc.logger = MagicMock()

        ai_rec = MagicMock()
        ai_rec.priority.name.lower.return_value = "high"
        ai_rec.telemetry_context = {"equipment_id": "S002-AHU-201"}
        ai_rec.title = "High priority issue"
        ai_rec.confidence = 0.72
        ai_rec.suggested_action = {"type": "pending_approval"}

        with patch("app.services.telegram_message_sender.get_telegram_sender") as mock_sender:
            mock_instance = AsyncMock()
            mock_sender.return_value = mock_instance
            with patch("app.config.settings") as mock_settings:
                mock_settings.telegram_alert_chat_id = "12345"

                try:
                    loop = asyncio.get_running_loop()
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        future = pool.submit(svc._notify_recommendation_alert, "S002", ai_rec)
                        future.result()
                except RuntimeError:
                    svc._notify_recommendation_alert("S002", ai_rec)

                mock_instance.send_text.assert_called_once()
                call_args = mock_instance.send_text.call_args
                assert "S002-AHU-201" in call_args[0][1]
                assert "HIGH" in call_args[0][1]

    @pytest.mark.asyncio
    async def test_notify_skips_info_severity(self):
        """Info severity rec does NOT trigger Telegram alert."""
        from app.services.background_scheduler import BackgroundSchedulerService

        svc = BackgroundSchedulerService.__new__(BackgroundSchedulerService)
        svc.logger = MagicMock()

        ai_rec = MagicMock()
        ai_rec.priority.name.lower.return_value = "info"
        ai_rec.telemetry_context = {"equipment_id": "S002-VAV-101"}
        ai_rec.title = "Minor deviation"
        ai_rec.confidence = 0.3
        ai_rec.suggested_action = {"type": "log_only"}

        svc._notify_recommendation_alert("S002", ai_rec)

    def test_manual_action_advisory_is_sendable(self):
        """Blocked write-back advisories remain operator-visible."""
        from app.models.recommendation import ActionRiskLevel, Recommendation, RecommendationStatus
        from app.services.background_scheduler import BackgroundSchedulerService

        svc = BackgroundSchedulerService.__new__(BackgroundSchedulerService)
        rec = Recommendation(
            site_id="site-002",
            action_type="ai_optimization",
            risk_level=ActionRiskLevel.LOW,
            target_equipment="S002-CHILLER-B01",
            action={
                "point": None,
                "value": "Apply after-hours HVAC setback",
                "execution_blocked": True,
            },
            reason="No writable BACnet point resolved — manual operator action required.",
            expected_impact={},
            confidence="0.72",
            status=RecommendationStatus.ADVISORY_INFO,
            metadata={"execution_status": "manual_action_required", "manual_action_required": True},
        )

        assert svc._is_sendable_ai_recommendation(rec) is True

    @pytest.mark.asyncio
    async def test_notify_skips_healthy_severity(self):
        """Healthy severity rec does NOT trigger Telegram alert."""
        from app.services.background_scheduler import BackgroundSchedulerService

        svc = BackgroundSchedulerService.__new__(BackgroundSchedulerService)
        svc.logger = MagicMock()

        ai_rec = MagicMock()
        ai_rec.priority.name.lower.return_value = "healthy"
        ai_rec.telemetry_context = {"equipment_id": "S002-PUMP-B1-CHW1"}
        ai_rec.title = "Normal operation"
        ai_rec.confidence = 0.95
        ai_rec.suggested_action = {"type": "log_only"}

        svc._notify_recommendation_alert("S002", ai_rec)

    @pytest.mark.asyncio
    async def test_notify_sends_telegram_for_critical_severity(self):
        """Critical severity rec triggers Telegram alert."""
        from app.services.background_scheduler import BackgroundSchedulerService

        svc = BackgroundSchedulerService.__new__(BackgroundSchedulerService)
        svc.logger = MagicMock()

        ai_rec = MagicMock()
        ai_rec.priority.name.lower.return_value = "critical"
        ai_rec.telemetry_context = {"equipment_id": "S002-CHILLER-B1-001"}
        ai_rec.title = "Compressor failure imminent"
        ai_rec.confidence = 0.88
        ai_rec.suggested_action = {"type": "emergency_shutdown"}

        with patch("app.services.telegram_message_sender.get_telegram_sender") as mock_sender:
            mock_instance = AsyncMock()
            mock_sender.return_value = mock_instance
            with patch("app.config.settings") as mock_settings:
                mock_settings.telegram_alert_chat_id = "12345"

                try:
                    loop = asyncio.get_running_loop()
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        future = pool.submit(svc._notify_recommendation_alert, "S002", ai_rec)
                        future.result()
                except RuntimeError:
                    svc._notify_recommendation_alert("S002", ai_rec)

                mock_instance.send_text.assert_called_once()
                call_args = mock_instance.send_text.call_args
                # Message includes S002-CHILLER-B1-001 and emergency_shutdown action
                assert "S002-CHILLER-B1-001" in call_args[0][1]
                assert "emergency_shutdown" in call_args[0][1].lower()
