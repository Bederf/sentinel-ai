from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from app.services.residential.morning_summary_service import MorningSummaryService


class TestMorningSummary:
    @patch("app.services.residential.morning_summary_service.get_supabase_client")
    @patch("app.services.residential.morning_summary_service.ResidentialTelegramSender")
    def test_send_summary_uses_sender(self, mock_sender_cls, mock_sb):
        mock_sb.return_value.table.return_value.select.return_value.eq.return_value.maybe_execute.return_value = (
            MagicMock(data=[{"chat_id": 99999, "eskom_area_code": None}])
        )
        sender = MagicMock()
        sender.send_text = AsyncMock(return_value=True)
        mock_sender_cls.return_value = sender

        svc = MorningSummaryService()
        # Patch MQTT read to avoid network
        svc._read_current_status = lambda site_id: {
            "battery_soc_pct": 55.0,
            "pv_power_w": 1200.0,
            "grid_power_w": 0.0,
            "load_power_w": 1400.0,
            "last_updated": None,
        }
        svc._get_loadshedding = lambda area: None

        import asyncio

        asyncio.get_event_loop().run_until_complete(svc.send_summary("res-99999"))
        sender.send_text.assert_awaited()
