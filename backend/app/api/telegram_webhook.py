"""
Telegram Registration Webhook — inbound message handler.

Receives all Telegram bot updates via webhook (POST from Telegram Bot API).
Handles:
  - /start → 3-step registration flow (name → phone → site picker)
  - Incoming message → delegate to TelegramFlowHandlers
  - Contact sharing → capture phone number
  - Location sharing → capture location (future use)

Single bot: all technicians (any site) use the same bot token.
Site-scoped routing is enforced at query time via technician.site_id.
"""

from __future__ import annotations

import hmac
import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.config.settings import settings
from app.database.repositories.notification_repository import NotificationRepository
from app.database.repositories.technician_repository import TechnicianRepository
from app.services.telegram_conversation_manager import (
    ConversationSession,
    TelegramConversationManager,
    TelegramIntent,
)
from app.services.telegram_flow_handlers import route_to_handler
from app.services.telegram_intent_classifier import classify_intent
from app.services.telegram_message_sender import TelegramMessageSender, get_telegram_sender

logger = logging.getLogger("sentinel.telegram_webhook")
router = APIRouter(prefix="/api/telegram", tags=["telegram"])

_tech_repo = TechnicianRepository()
_notif_repo = NotificationRepository()
_mgr = TelegramConversationManager()


# ==================== Step definitions ====================

STEP_WELCOME = "welcome"
STEP_NAME = "name"
STEP_PHONE = "phone"
STEP_SITE = "site"

REGISTRATION_STEPS = [
    STEP_WELCOME,
    STEP_NAME,
    STEP_PHONE,
    STEP_SITE,
]


async def _get_site_list() -> list[dict[str, str]]:
    """Fetch active sites for the site picker."""
    try:
        from app.database.supabase_client import get_supabase_client

        client = get_supabase_client()
        result = client.table("sites").select("id, code, name").eq("status", "active").execute()
        return [{"id": r["id"], "code": r["code"], "name": r.get("name") or r["code"]} for r in (result.data or [])]
    except Exception as e:
        logger.warning("Could not fetch site list: %s", e)
        return []


def _build_site_keyboard(sites: list[dict[str, str]]) -> dict:
    """Build Telegram inline keyboard for site selection."""
    rows = []
    for i, site in enumerate(sites):
        label = f"{i + 1}️⃣ {site['name']}"
        rows.append([{"text": label, "callback_data": f"reg:site:{site['id']}"}])
    return {"inline_keyboard": rows}


async def _send_registration_message(
    chat_id: str, step: str, sender: TelegramMessageSender, session: ConversationSession | None = None
):
    """Send the appropriate message for each registration step."""
    sites = await _get_site_list()

    if step == STEP_WELCOME:
        first_name = session.chat_first_name if session else ""
        name_prompt = f" {first_name}" if first_name else ""
        await sender.send_text(
            chat_id,
            f"👋 <b>Welcome to Sentinel BMS</b>\n\n"
            f"Let's get you set up{name_prompt}.\n\n"
            f"<b>Step 1/3 — Your name</b>\n"
            f"Please type your full name (e.g. John Smith):",
        )
    elif step == STEP_NAME:
        await sender.send_text(
            chat_id,
            "📱 <b>Step 2/3 — Cell phone number</b>\n\n"
            "Tap the button below to share your number,\n"
            "or type it manually (e.g. +27 82 123 4567):",
            keyboard=None,  # Add share contact button via reply_markup below
        )
        # NOTE: Telegram contact button is sent via reply_markup (see below)
    elif step == STEP_PHONE:
        await sender.send_text(
            chat_id,
            "🏢 <b>Step 3/3 — Select your site</b>\n\nChoose the building you work at:",
            keyboard=_build_site_keyboard(sites),
        )
    else:
        await sender.send_text(chat_id, "Something went wrong. Sending /start again.")
        await _handle_start(chat_id, sender)


async def _handle_start(chat_id: str, sender: TelegramMessageSender):
    """Initiate the /start registration flow."""
    # Fetch user's Telegram profile info (first_name from update)
    # Clear any existing session and start fresh
    mgr = _mgr
    if mgr.get_session(chat_id):
        mgr.end_session(chat_id)

    session = mgr.create_session(
        chat_id=chat_id,
        intent=TelegramIntent.REGISTER,
        flow="registration",
    )
    # Track registration step
    session.current_step = 0  # 0 = welcome, 1 = name, 2 = phone, 3 = site

    await _send_registration_message(chat_id, STEP_WELCOME, sender, session)


async def _finalize_registration(chat_id: str, name: str, phone: str, site_id: str, sender: TelegramMessageSender):
    """Create technician record and confirm registration."""
    try:
        # Create technician via existing repo
        tech = await _tech_repo.create_technician(
            name=name,
            email="",  # Not collected — optional in future
            phone=phone,
            specialties=["general"],
            site_id=site_id,
            telegram_id=chat_id,
        )

        if tech:
            # Get site name for confirmation
            try:
                from app.database.supabase_client import get_supabase_client

                client = get_supabase_client()
                site_result = client.table("sites").select("name").eq("id", site_id).limit(1).execute()
                site_name = site_result.data[0]["name"] if site_result.data else site_id
            except Exception:
                site_name = site_id

            await sender.send_text(
                chat_id,
                f"✅ <b>Registration complete!</b>\n\n"
                f"<b>Name:</b> {name}\n"
                f"<b>Phone:</b> {phone}\n"
                f"<b>Site:</b> {site_name}\n\n"
                f"You'll receive alerts for {site_name} here.",
            )
            logger.info(f"Telegram registration complete for {name} ({chat_id}) at {site_id}")
        else:
            await sender.send_text(
                chat_id,
                "⚠️ Registration succeeded but profile not found. Contact your administrator.",
            )

    except Exception as e:
        logger.error(f"Registration failed for chat_id={chat_id}: {e}")
        await sender.send_text(
            chat_id,
            "❌ Registration failed. Please try /start again or contact your administrator.",
        )

    # End session
    _mgr.end_session(chat_id)


# ==================== Telegram Webhook ====================


class TelegramUpdate(BaseModel):
    update_id: int
    message: dict | None = None
    edited_message: dict | None = None
    callback_query: dict | None = None


async def verify_telegram_signature(request: Request, bot_token: str | None = None) -> bool:
    """Verify request came from Telegram via the X-Telegram-Bot-Api-Secret-Token header.

    Fails closed: if TELEGRAM_SECRET_TOKEN is not configured, all requests are
    rejected. The webhook must be registered with setWebhook(secret_token=...)
    using the same value before this endpoint will accept traffic.
    """
    expected = settings.telegram_secret_token
    if not expected:
        logger.error("TELEGRAM_SECRET_TOKEN not configured — rejecting webhook request")
        return False

    secret_token = request.headers.get("x-telegram-bot-api-secret-token") or ""
    return hmac.compare_digest(secret_token, expected)


@router.post("/webhook")
async def telegram_webhook(request: Request):
    """
    Receive inbound Telegram updates.

    Telegram sends a POST with a TelegramUpdate object.
    We process it synchronously — no long-running operations here.
    """
    if not settings.telegram_bot_token:
        logger.warning("telegram_bot_token not configured — ignoring webhook")
        return {"ok": True}

    if not await verify_telegram_signature(request):
        raise HTTPException(status_code=403, detail="Invalid webhook secret")

    try:
        body = await request.json()
    except Exception:
        return {"ok": False, "error": "invalid JSON"}

    body.get("update_id", 0)

    # Handle callback query (inline keyboard button press)
    if "callback_query" in body:
        cq = body["callback_query"]
        chat_id = str(cq.get("from", {}).get("id", ""))
        data = cq.get("data", "")
        sender = get_telegram_sender()
        session = _mgr.get_session(chat_id)

        # Acknowledge immediately to remove loading spinner
        await sender.answer_callback_query(cq.get("id", ""))

        if data.startswith("reg:site:"):
            site_id = data.split(":")[-1]
            # User selected a site — finalize registration
            name = session.answers.get("name", "Unknown") if session else "Unknown"
            phone = session.answers.get("phone", "") if session else ""
            await _finalize_registration(chat_id, name, phone, site_id, sender)
            return {"ok": True}

        # Non-registration callbacks handled by flow handlers
        if session and session.flow in ("client_complaint", "technician_report", "wo_update", "ad_hoc_fault"):
            await route_to_handler(
                session.intent, chat_id, "", callback_data=data, message_id=cq.get("message", {}).get("message_id")
            )
            return {"ok": True}

        # Handle "Create Work Order" button on advisory notifications (no active session needed)
        if data.startswith("wo:rec_id:"):
            rec_uuid = data.split(":")[-1]
            from app.services.telegram_flow_handlers import _handle_create_wo_from_rec, get_telegram_sender

            sender = get_telegram_sender()
            await _handle_create_wo_from_rec(chat_id, rec_uuid, sender)
            return {"ok": True}

        # Handle "Approve" button on supervised mode advisory notifications
        if data.startswith("approve:rec_id:"):
            rec_uuid = data.split(":")[-1]
            from app.database.repositories.recommendation_repository import RecommendationRepository
            from app.services.approval_service import get_approval_service
            from app.services.telegram_message_sender import get_telegram_sender

            sender = get_telegram_sender()
            repo = RecommendationRepository()
            rec = await repo.get_by_id(rec_uuid)
            if not rec:
                await sender.send_text(chat_id, "Recommendation not found.")
                return {"ok": True}

            approval_svc = get_approval_service()
            result = await approval_svc.execute_approval(
                recommendation_id=rec_uuid,
                approved_by=f"telegram:{chat_id}",
                approval_notes="Approved via Telegram advisory notification",
            )

            equip = rec.target_equipment or "Equipment"
            if result.success:
                msg = (
                    f"✅ *Approved — {equip}*\n"
                    f"Adjustment applied automatically via BACnet.\n"
                    f"Outcome will be verified in ~30 minutes."
                )
            else:
                msg = f"❌ *Approval failed — {equip}*\n{result.error_message or 'Unknown error'}"

            await sender.send_text(chat_id, msg, parse_mode="Markdown")
            return {"ok": True}

        # Handle menu navigation buttons from inline keyboards
        if data.startswith("menu:start:"):
            from app.services.telegram_flow_handlers import handle_unknown

            await handle_unknown(chat_id, "", callback_data=data, message_id=cq.get("message", {}).get("message_id"))
            return {"ok": True}

        return {"ok": True}

    # Handle regular message
    msg = body.get("message", {})
    if not msg:
        return {"ok": True}

    chat_id = str(msg.get("from", {}).get("id", ""))
    text = msg.get("text", "").strip()
    contact = msg.get("contact")  # Shared phone number
    location = msg.get("location")  # Shared location

    sender = get_telegram_sender()
    session = _mgr.get_session(chat_id)

    # /start — initiate registration flow
    if text == "/start" or text == "/start@sentinel_bms_bot":
        await _handle_start(chat_id, sender)
        return {"ok": True}

    # Check if we're in registration flow
    if session and session.flow == "registration":
        step = (
            REGISTRATION_STEPS[session.current_step] if session.current_step < len(REGISTRATION_STEPS) else STEP_WELCOME
        )

        if step == STEP_WELCOME:
            # User responded to welcome/name prompt — treat as name entry
            if text:
                session.answers["name"] = text
                session.current_step = 1
                await _send_registration_message(chat_id, STEP_NAME, sender, session)
            return {"ok": True}

        elif step == STEP_NAME:
            # Phone step — accept contact share OR manual text
            phone = ""
            if contact:
                phone = contact.get("phone_number", "")
            elif text:
                # Basic validation: should look like a phone number
                phone = text.strip()
                if not phone.startswith("+"):
                    phone = "+" + phone

            if phone:
                session.answers["phone"] = phone
                session.current_step = 2
                await _send_registration_message(chat_id, STEP_PHONE, sender, session)
            else:
                await sender.send_text(
                    chat_id,
                    "Please share your phone number using the button, or type it manually (e.g. +27 82 123 4567):",
                )
            return {"ok": True}

        elif step == STEP_PHONE:
            # Site selection — but if user typed something, treat it as fallback
            if text and not location:
                await sender.send_text(
                    chat_id,
                    "Please select your site by tapping one of the options below:",
                    keyboard=_build_site_keyboard(await _get_site_list()),
                )
            return {"ok": True}

        return {"ok": True}

    # Non-registration messages → delegate to flow handlers
    if session:
        intent, _ = classify_intent(text, has_active_session=True)
        await route_to_handler(intent, chat_id, text)
    else:
        # Unknown user — prompt them to /start
        await sender.send_text(
            chat_id,
            "👋 I don't recognize you yet.\n\nPlease send /start to register with Sentinel BMS.",
        )

    return {"ok": True}
