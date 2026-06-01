"""ResidentialSetareaService — /setarea command handler.

Phase 214 — Wave 4
"""

from __future__ import annotations

import asyncio
import logging

from app.database.supabase_client import get_supabase_client
from app.services.residential.eskomsepush_client import validate_area_code as _validate_area_code_sync
from app.services.residential.residential_telegram_sender import ResidentialTelegramSender
from app.services.sentry.conversation_state import ConversationStateManager

logger = logging.getLogger(__name__)

_sender = ResidentialTelegramSender()

# ── State steps ─────────────────────────────────────────────────────────────────

AWAITING_AREA_CODE = "waiting_area_code"
AWAITING_AREA_CODE_CONFIRMED = "waiting_area_code_confirmed"

# ── Conversation flow helpers ──────────────────────────────────────────────────


def _send(chat_id: int, text: str, reply_markup: dict | None = None) -> dict | None:
    """Send text via ResidentialTelegramSender."""
    try:
        result = asyncio.get_event_loop().run_until_complete(_sender.send_text(chat_id, text, reply_markup))
        return {"message_id": 0} if result else None
    except Exception as exc:
        logger.error("Telegram send failed: %s", exc)
        return None


def _send_confirmation_inline(
    chat_id: int,
    current_area: str,
    new_area_placeholder: str,
    confirm_data: str,
    cancel_data: str,
) -> None:
    """Send confirmation inline keyboard asking if user wants to update."""
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "Yes", "callback_data": confirm_data},
                {"text": "Cancel", "callback_data": cancel_data},
            ]
        ]
    }
    _send(
        chat_id,
        f"Current area: {current_area}\nUpdate to {new_area_placeholder}?",
        reply_markup=keyboard,
    )


def _lookup_active_site(chat_id: int) -> dict | None:
    """Return the active residential_sites row for this chat_id, or None."""
    try:
        supabase = get_supabase_client()
        result = (
            supabase.table("residential_sites")
            .select("id, site_id, eskom_area_code, is_active")
            .eq("chat_id", chat_id)
            .eq("is_active", True)
            .execute()
        )
        if result.data:
            return result.data[0]
    except Exception as exc:
        logger.warning("Failed to lookup active site for chat_id=%s: %s", chat_id, exc)
    return None


def _has_active_onboarding_flow(chat_id: int) -> bool:
    """Return True if an active /connect onboarding flow exists for this chat_id."""
    state = ConversationStateManager().get(chat_id)
    if state is None:
        return False
    return state.flow == "residential_onboarding" and state.step != "discovering_complete"


# ── validate_area_code wrapper ──────────────────────────────────────────────────


async def _validate_area_code_async(area_code: str) -> bool:
    """
    Validate area code via eskomsepush_client.validate_area_code().
    Checks cached area list — NOT a live API call.
    """
    return await _validate_area_code_sync(area_code)


def _validate_area_code(area_code: str) -> bool:
    """Sync wrapper for eskomsepush_client.validate_area_code()."""
    try:
        return asyncio.get_event_loop().run_until_complete(_validate_area_code_async(area_code))
    except Exception as exc:
        logger.warning("validate_area_code failed for %s: %s", area_code, exc)
        return True  # fail-open


# ── Service ─────────────────────────────────────────────────────────────────────


class ResidentialSetareaService:
    """
    Handles /setarea command for residential users.

    State key: conv:{chat_id} (managed by ConversationStateManager)
    TTL: 600s — session expires mid-flow

    Flow A (no area set):
      /setarea → ask for area code → user types code → validate → confirm save → done

    Flow B (area already set):
      /setarea → confirmation inline (current → update?) → user taps Yes →
      ask for new area code → user types → validate → confirm save → done
    """

    def __init__(self) -> None:
        self._state = ConversationStateManager()

    def _new_state(
        self,
        step: str,
        data: dict | None = None,
    ) -> ConversationStateManager.ConversationState:
        return ConversationStateManager.ConversationState(
            flow="setarea",
            step=step,
            data=data or {},
            created_at="",
            updated_at="",
        )

    # ── Entry point ────────────────────────────────────────────────────────────

    def handle_setarea(self, chat_id: int) -> str:
        """
        Called when user sends /setarea.
        Returns the bot message text to send.
        """
        # 1. Block if active /connect onboarding flow exists
        if _has_active_onboarding_flow(chat_id):
            return "Complete your /connect first.\nFinish onboarding before setting your area code."

        # 2. Lookup active connection
        site = _lookup_active_site(chat_id)
        if site is None:
            return "No active connection found.\n\nSend /connect first to link your solar system."

        site_id = site["site_id"]
        current_area = site.get("eskom_area_code") or ""

        # 3. If area already set, ask for update confirmation first
        if current_area:
            state = self._new_state(
                AWAITING_AREA_CODE_CONFIRMED,
                {
                    "site_id": site_id,
                    "current_area": current_area,
                    "new_area": "",
                },
            )
            self._state.set(chat_id, state)

            _send_confirmation_inline(
                chat_id,
                current_area=current_area,
                new_area_placeholder="<new area>",
                confirm_data="setarea_confirm",
                cancel_data="setarea_cancel",
            )
            return "Awaiting update confirmation..."

        # 4. No area set — ask for area code directly
        state = self._new_state(
            AWAITING_AREA_CODE,
            {"site_id": site_id, "new_area": ""},
        )
        self._state.set(chat_id, state)

        _send(
            chat_id,
            "Enter your Eskom area code to enable loadshedding alerts.\n\n"
            "Find yours at eskomsepush.co.za\n\n"
            "Example: sandton-2",
        )
        return "Asking for area code..."

    # ── Text handler (free-form area code entry) ───────────────────────────────

    def handle_area_code_text(self, chat_id: int, text: str) -> str:
        """
        Called when user sends free-form text while in AWAITING_AREA_CODE step.
        Returns the bot message text to send.
        """
        state = self._state.get(chat_id)
        if state is None or state.step not in (AWAITING_AREA_CODE, AWAITING_AREA_CODE_CONFIRMED):
            return "Send /setarea to set your area code."

        area_code = text.strip().lower()
        if not area_code:
            return "Area code cannot be empty. Enter your Eskom area code."

        # site_id not needed here

        # Validate area code — checks _area_cache, NOT live API
        if not _validate_area_code(area_code):
            _send(
                chat_id,
                "Area code not found. Check eskomsepush.co.za and try again.",
            )
            return "Invalid area code."

        # Store validated area code in state
        state.data["new_area"] = area_code
        self._state.set(chat_id, state)

        # If user is providing area directly (no prior confirmation needed), ask confirm
        if state.step == AWAITING_AREA_CODE:
            keyboard = {
                "inline_keyboard": [
                    [
                        {"text": "Save", "callback_data": "setarea_confirm"},
                        {"text": "Cancel", "callback_data": "setarea_cancel"},
                    ]
                ]
            }
            _send(
                chat_id,
                f"Area code: {area_code}\nSave this?",
                reply_markup=keyboard,
            )
            return "Awaiting save confirmation..."
        else:
            # AWAITING_AREA_CODE_CONFIRMED: user already tapped Yes, got new area
            # Ask confirm for the new value
            keyboard = {
                "inline_keyboard": [
                    [
                        {"text": "Save", "callback_data": "setarea_confirm"},
                        {"text": "Cancel", "callback_data": "setarea_cancel"},
                    ]
                ]
            }
            _send(
                chat_id,
                f"New area code: {area_code}\nUpdate from {state.data.get('current_area', '')}?",
                reply_markup=keyboard,
            )
            return "Awaiting save confirmation..."

    # ── Callback handler (inline keyboard) ─────────────────────────────────────

    def handle_confirmation(self, chat_id: int, callback_query_id: str, action: str) -> str:
        """
        Called when user taps inline keyboard button.
        action: 'setarea_confirm' | 'setarea_cancel'
        Returns the bot message text to send.
        """
        # Always dismiss spinner first
        try:
            asyncio.get_event_loop().run_until_complete(_sender.answer_callback_query(callback_query_id))
        except Exception as exc:
            logger.warning("answerCallbackQuery failed: %s", exc)

        state = self._state.get(chat_id)
        if state is None or state.step not in (AWAITING_AREA_CODE, AWAITING_AREA_CODE_CONFIRMED):
            return "Your session timed out. Send /setarea to start again."

        if action == "setarea_cancel":
            self._state.clear(chat_id)
            return "Area code update cancelled."

        if action != "setarea_confirm":
            return "Unknown action. Send /setarea to try again."

        new_area = state.data.get("new_area", "")

        if not new_area:
            # User tapped Save but no area code in state — ask for it now
            state.step = AWAITING_AREA_CODE_CONFIRMED
            state.data["new_area"] = ""
            self._state.set(chat_id, state)

            _send(
                chat_id,
                "Enter your new Eskom area code:",
            )
            return "Awaiting new area code..."

        # We have a validated area code — persist to DB
        site_id = state.data.get("site_id", "")

        try:
            supabase = get_supabase_client()
            supabase.table("residential_sites").update({"eskom_area_code": new_area}).eq("site_id", site_id).execute()
        except Exception as exc:
            logger.error("Failed to update eskom_area_code for %s: %s", site_id, exc)
            return "Failed to save area code. Please try again later."

        self._state.clear(chat_id)

        _send(
            chat_id,
            f"✅ Loadshedding alerts enabled for {new_area}.\n\n"
            "You'll be notified when load shedding is scheduled\n"
            "and your battery needs attention.",
        )
        return "Area code saved."
