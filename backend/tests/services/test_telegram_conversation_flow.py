"""Tests for Telegram Conversation Flow Handlers."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.telegram_conversation_manager import (
    SESSION_TIMEOUT_MINUTES,
    TelegramConversationManager,
)
from app.services.telegram_flow_handlers import (
    _handle_checklist_reply,
    handle_adhoc_fault,
    handle_client_complaint,
    handle_technician_report,
    handle_unknown,
    handle_wo_update,
    route_to_handler,
)
from app.services.telegram_intent_classifier import TelegramIntent


@pytest.fixture
def mock_sender():
    """Mock TelegramMessageSender."""
    sender = MagicMock()
    sender.send_text = AsyncMock(return_value={"ok": True})
    sender.answer_callback_query = AsyncMock()
    sender.edit_message_reply_markup = AsyncMock()
    return sender


@pytest.fixture
def mock_manager():
    """Fresh conversation manager."""
    return TelegramConversationManager()


@pytest.fixture(autouse=True)
def patch_dependencies(mock_sender, mock_manager):
    """Patch sender and manager singletons."""
    with (
        patch(
            "app.services.telegram_flow_handlers.get_telegram_sender",
            return_value=mock_sender,
        ),
        patch(
            "app.services.telegram_flow_handlers.get_conversation_manager",
            return_value=mock_manager,
        ),
    ):
        yield


# ===================================================================
# Client Complaint Flow
# ===================================================================


class TestClientComplaintFlow:
    @pytest.mark.asyncio
    async def test_start_shows_category_keyboard(self, mock_sender, mock_manager):
        await handle_client_complaint("chat-1", "something is wrong")
        mock_sender.send_text.assert_called_once()
        call_args = mock_sender.send_text.call_args
        assert "best describes" in call_args[1].get("text", call_args[0][1])

    @pytest.mark.asyncio
    async def test_pre_classified_skips_category(self, mock_sender, mock_manager):
        """'too hot on level 3' should auto-classify and ask for location."""
        await handle_client_complaint("chat-1", "it's too hot on level 3")
        text = mock_sender.send_text.call_args[0][1]
        assert "floor" in text.lower() or "area" in text.lower()

    @pytest.mark.asyncio
    async def test_category_callback_advances_to_location(self, mock_sender, mock_manager):
        # Start flow
        await handle_client_complaint("chat-1", "help")
        mock_sender.send_text.reset_mock()

        # Send category callback
        await handle_client_complaint("chat-1", "", callback_data="complaint:category:plumbing", message_id=10)
        text = mock_sender.send_text.call_args[0][1]
        assert "floor" in text.lower() or "area" in text.lower()

    @pytest.mark.asyncio
    async def test_location_advances_to_duration(self, mock_sender, mock_manager):
        # Start + category
        await handle_client_complaint("chat-1", "help")
        await handle_client_complaint("chat-1", "", callback_data="complaint:category:hvac")
        mock_sender.send_text.reset_mock()

        # Send location
        await handle_client_complaint("chat-1", "Level 2, near the kitchen")
        text = mock_sender.send_text.call_args[0][1]
        assert "how long" in text.lower()

    @pytest.mark.asyncio
    async def test_duration_advances_to_photo(self, mock_sender, mock_manager):
        # Start + category + location
        await handle_client_complaint("chat-1", "help")
        await handle_client_complaint("chat-1", "", callback_data="complaint:category:hvac")
        await handle_client_complaint("chat-1", "Level 2")
        mock_sender.send_text.reset_mock()

        # Send duration
        await handle_client_complaint("chat-1", "", callback_data="complaint:duration:just_started")
        text = mock_sender.send_text.call_args[0][1]
        assert "photo" in text.lower()

    @pytest.mark.asyncio
    async def test_skip_photo_creates_wo(self, mock_sender, mock_manager):
        # Full flow
        await handle_client_complaint("chat-1", "help")
        await handle_client_complaint("chat-1", "", callback_data="complaint:category:plumbing")
        await handle_client_complaint("chat-1", "Level 1")
        await handle_client_complaint("chat-1", "", callback_data="complaint:duration:several_days")
        mock_sender.send_text.reset_mock()

        # Skip photo
        with patch(
            "app.services.telegram_flow_handlers._create_complaint_wo",
            new_callable=AsyncMock,
            return_value="WO-2026-0099",
        ):
            await handle_client_complaint("chat-1", "", callback_data="complaint:photo:skip", message_id=20)

        text = mock_sender.send_text.call_args[0][1]
        assert "WO-2026-0099" in text
        # Session should be ended
        assert mock_manager.get_session("chat-1") is None

    @pytest.mark.asyncio
    async def test_text_fallback_for_category(self, mock_sender, mock_manager):
        await handle_client_complaint("chat-1", "help")
        mock_sender.send_text.reset_mock()

        # Text instead of button
        await handle_client_complaint("chat-1", "plumbing")
        text = mock_sender.send_text.call_args[0][1]
        assert "floor" in text.lower() or "area" in text.lower()


# ===================================================================
# Technician Report / Checklist Flow
# ===================================================================


class TestTechnicianReportFlow:
    @pytest.mark.asyncio
    async def test_start_with_equipment_id(self, mock_sender, mock_manager):
        await handle_technician_report("chat-1", "I'm at S002-AHU-L2-001 starting inspection")
        text = mock_sender.send_text.call_args[0][1]
        # Should show first checklist question
        assert "Filter" in text or "S002-AHU-L2-001" in text

    @pytest.mark.asyncio
    async def test_start_without_equipment_asks(self, mock_sender, mock_manager):
        await handle_technician_report("chat-1", "starting inspection")
        text = mock_sender.send_text.call_args[0][1]
        assert "equipment" in text.lower()

    @pytest.mark.asyncio
    async def test_provide_equipment_id_after_ask(self, mock_sender, mock_manager):
        await handle_technician_report("chat-1", "starting inspection")
        mock_sender.send_text.reset_mock()

        await handle_technician_report("chat-1", "S002-AHU-L2-001")
        text = mock_sender.send_text.call_args[0][1]
        assert "Filter" in text

    @pytest.mark.asyncio
    async def test_good_answer_advances(self, mock_sender, mock_manager):
        await handle_technician_report("chat-1", "S002-AHU-L2-001 inspection")
        mock_sender.send_text.reset_mock()

        # Answer first question Good
        await handle_technician_report("chat-1", "", callback_data="inspect:filter:good", message_id=5)
        text = mock_sender.send_text.call_args[0][1]
        assert "Pressure" in text  # Next question

    @pytest.mark.asyncio
    async def test_dirty_filter_triggers_followup(self, mock_sender, mock_manager):
        await handle_technician_report("chat-1", "S002-AHU-L2-001 inspection")
        mock_sender.send_text.reset_mock()

        # Answer Dirty
        await handle_technician_report("chat-1", "", callback_data="inspect:filter:dirty", message_id=5)
        text = mock_sender.send_text.call_args[0][1]
        assert "airflow" in text.lower()  # Follow-up question

    @pytest.mark.asyncio
    async def test_followup_then_next_question(self, mock_sender, mock_manager):
        await handle_technician_report("chat-1", "S002-AHU-L2-001 inspection")

        # Dirty filter
        await handle_technician_report("chat-1", "", callback_data="inspect:filter:dirty")
        mock_sender.send_text.reset_mock()

        # Answer followup
        with patch(
            "app.services.telegram_flow_handlers._create_inspection_wo",
            new_callable=AsyncMock,
            return_value="WO-2026-0100",
        ):
            await handle_technician_report("chat-1", "", callback_data="inspect:filter_detail:change_soon")

        text = mock_sender.send_text.call_args[0][1]
        assert "Pressure" in text  # Moved to next question

    @pytest.mark.asyncio
    async def test_full_checklist_shows_summary(self, mock_sender, mock_manager):
        """Complete all 6 questions with Good answers -> summary."""
        await handle_technician_report("chat-1", "S002-AHU-L2-001 inspection")

        callbacks = [
            "inspect:filter:good",
            "inspect:pressure:normal",
            "inspect:vibration:good",
            "inspect:belt:good",
            "inspect:coil:no_photo",
            "inspect:damper:normal",
        ]
        for cb in callbacks:
            await handle_technician_report("chat-1", "", callback_data=cb)

        text = mock_sender.send_text.call_args[0][1]
        assert "Inspection Complete" in text
        assert mock_manager.get_session("chat-1") is None


# ===================================================================
# WO Update Flow
# ===================================================================


class TestWOUpdateFlow:
    @pytest.mark.asyncio
    async def test_wo_done_quick_complete(self, mock_sender, mock_manager):
        with (
            patch(
                "app.services.telegram_flow_handlers._lookup_wo",
                new_callable=AsyncMock,
                return_value={"id": "uuid-1", "title": "Test", "status": "scheduled"},
            ),
            patch(
                "app.services.telegram_flow_handlers._update_wo_status",
                new_callable=AsyncMock,
                return_value=True,
            ),
        ):
            await handle_wo_update("chat-1", "WO-2026-0045 done")

        text = mock_sender.send_text.call_args[0][1]
        assert "completed" in text.lower()

    @pytest.mark.asyncio
    async def test_wo_not_found(self, mock_sender, mock_manager):
        with patch(
            "app.services.telegram_flow_handlers._lookup_wo",
            new_callable=AsyncMock,
            return_value=None,
        ):
            await handle_wo_update("chat-1", "WO-2026-9999")

        text = mock_sender.send_text.call_args[0][1]
        assert "not found" in text.lower()

    @pytest.mark.asyncio
    async def test_wo_no_reference(self, mock_sender, mock_manager):
        await handle_wo_update("chat-1", "some random text")
        text = mock_sender.send_text.call_args[0][1]
        assert "work order number" in text.lower()

    @pytest.mark.asyncio
    async def test_wo_lookup_shows_summary(self, mock_sender, mock_manager):
        with patch(
            "app.services.telegram_flow_handlers._lookup_wo",
            new_callable=AsyncMock,
            return_value={
                "id": "uuid-1",
                "title": "Belt replacement",
                "status": "scheduled",
                "priority": "high",
                "assigned_to": "John Smith",
            },
        ):
            await handle_wo_update("chat-1", "WO-2026-0045")

        text = mock_sender.send_text.call_args[0][1]
        assert "Belt replacement" in text
        # Should have status buttons
        kb = mock_sender.send_text.call_args[1].get("keyboard")
        assert kb is not None

    @pytest.mark.asyncio
    async def test_wo_status_callback(self, mock_sender, mock_manager):
        # Create session with wo_id
        session = mock_manager.create_session("chat-1", TelegramIntent.WO_UPDATE, "wo_update")
        session.wo_id = "WO-2026-0045"
        mock_manager.update_session(session)

        with patch(
            "app.services.telegram_flow_handlers._update_wo_status",
            new_callable=AsyncMock,
            return_value=True,
        ):
            await handle_wo_update("chat-1", "", callback_data="wo:status:completed", message_id=15)

        text = mock_sender.send_text.call_args[0][1]
        assert "Completed" in text


# ===================================================================
# Ad-Hoc Fault Flow
# ===================================================================


class TestAdHocFaultFlow:
    @pytest.mark.asyncio
    async def test_start_asks_location(self, mock_sender, mock_manager):
        await handle_adhoc_fault("chat-1", "broken chair")
        text = mock_sender.send_text.call_args[0][1]
        assert "where" in text.lower()

    @pytest.mark.asyncio
    async def test_location_creates_wo(self, mock_sender, mock_manager):
        await handle_adhoc_fault("chat-1", "broken chair")
        mock_sender.send_text.reset_mock()

        with patch(
            "app.services.telegram_flow_handlers._create_complaint_wo",
            new_callable=AsyncMock,
            return_value="WO-2026-0101",
        ):
            await handle_adhoc_fault("chat-1", "desk 204, level 2")

        text = mock_sender.send_text.call_args[0][1]
        assert "WO-2026-0101" in text
        assert mock_manager.get_session("chat-1") is None


# ===================================================================
# Unknown / Orientation
# ===================================================================


class TestUnknownFlow:
    @pytest.mark.asyncio
    async def test_shows_menu(self, mock_sender, mock_manager):
        await handle_unknown("chat-1", "hello")
        text = mock_sender.send_text.call_args[0][1]
        assert "help" in text.lower()
        kb = mock_sender.send_text.call_args[1].get("keyboard")
        assert kb is not None


# ===================================================================
# Router
# ===================================================================


class TestRouter:
    @pytest.mark.asyncio
    async def test_routes_complaint(self, mock_sender, mock_manager):
        with patch(
            "app.services.telegram_flow_handlers.handle_client_complaint",
            new_callable=AsyncMock,
        ) as mock_handler:
            await route_to_handler(TelegramIntent.CLIENT_COMPLAINT, "chat-1", "too hot")
            mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_routes_unknown(self, mock_sender, mock_manager):
        with patch(
            "app.services.telegram_flow_handlers.handle_unknown",
            new_callable=AsyncMock,
        ) as mock_handler:
            await route_to_handler(TelegramIntent.UNKNOWN, "chat-1", "hello")
            mock_handler.assert_called_once()


# ===================================================================
# Session Expiry Mid-Flow
# ===================================================================


class TestSessionExpiry:
    @pytest.mark.asyncio
    async def test_expired_session_shows_fresh_start(self, mock_sender, mock_manager):
        """Start a flow, expire the session, next message gets orientation."""
        session = mock_manager.create_session("chat-1", TelegramIntent.CLIENT_COMPLAINT, "client_complaint")
        session.last_activity = datetime.utcnow() - timedelta(minutes=SESSION_TIMEOUT_MINUTES + 5)
        mock_manager._sessions["chat-1"] = session

        await _handle_checklist_reply("chat-1", "some text")
        text = mock_sender.send_text.call_args[0][1]
        assert "expired" in text.lower() or "help" in text.lower()
