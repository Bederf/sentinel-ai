"""WhatsApp webhook endpoints for receiving incoming messages."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

from app.api.whatsapp_visit_webhook import router as visit_reply_router
from app.handlers.whatsapp_handler import get_whatsapp_handler
from app.integrations.whatsapp_service import get_whatsapp_service
from app.security.prompt_guard import score_prompt
from app.security.webhook_auth import verify_whatsapp_webhook as verify_whatsapp_signature
from app.services.popia_consent_guard import evaluate_ingress_processing_consent

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp"])

whatsapp_service = get_whatsapp_service()
whatsapp_handler = get_whatsapp_handler()

# Mount Phase 176-03 visit reply router at /whatsapp/visit/reply
router.include_router(visit_reply_router)


def _parse_approval_command(content: str) -> dict[str, str]:
    """Parse APPROVE/REJECT command text into action/id/reason fields."""
    parts = content.strip().split(maxsplit=2)
    if not parts:
        return {"action": "", "token": "", "reason": ""}
    action = parts[0].upper()
    token = parts[1].strip() if len(parts) > 1 else ""
    reason = parts[2].strip() if len(parts) > 2 else ""
    return {"action": action, "token": token, "reason": reason}


async def _resolve_recommendation_id(token: str) -> str:
    """Resolve full recommendation ID from full/prefix token."""
    if not token:
        return ""

    try:
        from app.database.repositories import get_recommendation_repository

        repo = get_recommendation_repository()
        return await repo.resolve_id_prefix(token)
    except Exception:
        return ""

    return ""


@router.get("/webhooks")
async def verify_whatsapp_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
) -> int:
    """
    WhatsApp webhook verification endpoint (GET) — Phase 102.

    Meta sends GET request with: hub.mode=subscribe, hub.verify_token, hub.challenge
    This endpoint is called by Meta during webhook configuration to verify ownership.

    Security (Phase 100):
    - hub.verify_token is compared against WHATSAPP_WEBHOOK_TOKEN from env
    - If token matches, echo back hub.challenge to complete handshake
    - Meta then trusts this webhook for inbound messages & callbacks
    """
    logger.info(f"Webhook verification request: mode={hub_mode}")

    if hub_mode != "subscribe":
        logger.warning(f"Invalid webhook mode: {hub_mode}")
        raise HTTPException(status_code=403, detail="Invalid mode")

    if not whatsapp_service.verify_webhook_token(hub_verify_token):
        logger.warning("Invalid webhook verification token")
        raise HTTPException(status_code=403, detail="Invalid token")

    logger.info("WhatsApp webhook verified successfully - webhook is trusted by Meta")
    return int(hub_challenge)


@router.post("/webhooks", tags=["llm_touching"])
async def handle_whatsapp_message(
    request: Request,
    verified_body: bytes = Depends(verify_whatsapp_signature),
) -> dict[str, str]:
    """
    Handle incoming WhatsApp messages (POST).

    This endpoint receives all WhatsApp events (messages, status updates, etc).
    Phase 137-04: HMAC signature verification + replay protection via dependency.
    """
    try:
        body = json.loads(verified_body)
        logger.debug(f"Received WhatsApp webhook: {str(body)[:200]}...")

        # Extract message from webhook structure
        # Meta sends: { entry: [{ changes: [{ value: { messages: [] } }] }] }
        entry = body.get("entry", [{}])[0]
        changes = entry.get("changes", [{}])[0]
        value = changes.get("value", {})

        messages = value.get("messages", [])
        if not messages:
            # Not a message event (could be status, read receipt, etc)
            logger.debug("Webhook received but no messages in payload")
            return {"status": "ok"}

        message = messages[0]
        from_number = message.get("from")
        message_id = message.get("id")
        message_type = message.get("type", "text")
        waba_id = value.get("metadata", {}).get("phone_number_id", "")

        if not from_number:
            logger.warning("WhatsApp message missing sender identifier")
            return {"status": "ok"}

        # Extract message content based on type
        content = None
        if message_type == "text":
            content = message.get("text", {}).get("body", "")
        elif message_type == "button":
            content = message.get("button", {}).get("text", "")
        elif message_type == "interactive":
            # Handle interactive button responses
            interactive = message.get("interactive", {})
            button_reply = interactive.get("button_reply", {})
            content = button_reply.get("title", "")

        content_preview = content[:50] if content else "N/A"
        logger.info(f"[WhatsApp] Incoming from {from_number}: type={message_type}, content={content_preview}")

        if not content:
            logger.debug("Message received but no extractable content")
            return {"status": "ok"}

        # --- Prompt guard: score extracted content as webhook source ---
        guard_result = score_prompt(content, "webhook")
        if not guard_result.allow:
            logger.warning(
                "[WhatsApp] Prompt guard BLOCKED: from=%s score=%.2f reasons=%s",
                from_number,
                guard_result.score,
                guard_result.reasons[:3],
            )
            return {"status": "ok"}
        if guard_result.rewritten_text:
            content = guard_result.rewritten_text

        consent_decision = evaluate_ingress_processing_consent(
            data_subject_id=from_number,
            platform="whatsapp",
            message_text=content,
            ip_address=(request.client.host if request.client else None),
        )
        if not consent_decision.allow_processing:
            if consent_decision.response_message:
                await whatsapp_service.send_text_message(from_number, consent_decision.response_message)
            logger.info(
                "[WhatsApp] POPIA consent gate blocked processing: from=%s status=%s",
                from_number,
                consent_decision.status,
            )
            return {"status": "ok"}

        # Route message to appropriate handler
        reply_to_message_id = message.get("context", {}).get("id")

        await route_incoming_message(
            from_number,
            content,
            message_type,
            message_id,
            reply_to_message_id=reply_to_message_id,
            waba_id=waba_id,
        )

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Error handling WhatsApp webhook: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


def _normalise_whatsapp_number(value: str) -> str:
    """Normalize to E.164 format: +27XXXXXXXXX."""
    digits = value.replace("whatsapp:", "").replace("+", "").replace(" ", "").strip()
    if not digits.startswith("27"):
        digits = "27" + digits.lstrip("0")
    return "+" + digits


def _verify_twilio_signature(request_url: str, params: dict[str, str], signature: str | None) -> bool:
    auth_token = os.getenv("TWILIO_AUTH_TOKEN", "")
    if not auth_token:
        return True
    if not signature:
        return False
    payload = request_url + "".join(f"{key}{params[key]}" for key in sorted(params))
    digest = hmac.new(auth_token.encode("utf-8"), payload.encode("utf-8"), hashlib.sha1).digest()
    expected = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(expected, signature)


@router.post("/twilio")
async def handle_twilio_whatsapp_message(
    request: Request,
    X_Twilio_Signature: str | None = Header(default=None, alias="X-Twilio-Signature"),
) -> dict[str, str]:
    """Handle incoming Twilio WhatsApp replies."""
    # Parse all form params (Twilio sends many fields; all are part of the signature)
    form_data = await request.form()
    params = {k: v for k, v in form_data.items() if isinstance(v, str)}

    Body = params.get("Body", "")
    From = params.get("From", "")
    MessageSid = params.get("MessageSid", "")
    OriginalRepliedMessageSid = params.get("OriginalRepliedMessageSid", "")

    # Twilio signs against the public URL, not the internal proxy URL
    public_base = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
    request_url = f"{public_base}/api/whatsapp/twilio" if public_base else str(request.url)

    if not _verify_twilio_signature(request_url, params, X_Twilio_Signature):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    from_number = _normalise_whatsapp_number(From)
    if not from_number or not Body:
        return {"status": "ok"}

    await route_incoming_message(
        from_number,
        Body,
        "text",
        MessageSid,
        reply_to_message_id=OriginalRepliedMessageSid or None,
        waba_id=os.getenv("TWILIO_WHATSAPP_FROM", ""),
    )
    return {"status": "ok"}


async def route_incoming_message(
    from_number: str,
    content: str,
    message_type: str,
    message_id: str,
    *,
    reply_to_message_id: str | None = None,
    waba_id: str = "",
) -> None:
    """
    Route incoming WhatsApp message to appropriate handler.

    Supports:
    - Active comfort complaint session → Continue multi-turn agent
    - Comfort complaint detected → Start desk complaint agent
    - "WO-XXXXX" → Show work order details
    - "Status" or "Summary" → Show facility status
    - "Help" or "?" → Show available commands
    - Unknown sender → /start onboarding (name + location)
    """
    try:
        # Normalise
        normalized_phone = _normalise_whatsapp_number(from_number)

        # --- WhatsApp onboarding flow ---
        from app.services.whatsapp_conversation_manager import get_whatsapp_conversation_manager
        from app.database.repositories.occupant_repository import SiteOccupantRepository

        occupant_repo = SiteOccupantRepository()
        mgr = get_whatsapp_conversation_manager()

        # Check if already registered
        occupant = await occupant_repo.get_by_phone(normalized_phone)
        if not occupant:
            session = mgr.get_session(normalized_phone)
            if session:
                # Active onboarding session — advance step
                step = session.step
                if step == 0:
                    # Received name
                    session.name = content.strip()
                    session.step = 1
                    await whatsapp_service.send_text_message(
                        normalized_phone,
                        f"📍 Thanks {session.name}! Now tell me your location at the building.\n"
                        f"(e.g. Shop G123, Bay 4, Reception, Level 2)",
                    )
                    return
                elif step == 1:
                    # Received location — finalize registration
                    session.location = content.strip()
                    await occupant_repo.create(
                        site_id=session.site_id,
                        phone=normalized_phone,
                        name=session.name,
                        location=session.location,
                    )
                    mgr.end_session(normalized_phone)
                    await whatsapp_service.send_text_message(
                        normalized_phone,
                        f"✅ You're all set, {session.name}!\n\n"
                        f"Location: {session.location}\n\n"
                        f"Report any issues anytime — just send me a message. 👋",
                    )
                    return
            else:
                # No active session — look up site by WABA ID
                site = occupant_repo._resolve_site_by_whatsapp(waba_id=waba_id)
                if not site:
                    await whatsapp_service.send_text_message(
                        normalized_phone,
                        "👋 Welcome! This number isn't linked to a building yet.\n"
                        "Contact your facilities team to get set up.",
                    )
                    return

                # Create onboarding session for this site
                session = mgr.create_session(
                    phone=normalized_phone,
                    site_id=site["id"],
                    flow="onboarding",
                )
                await whatsapp_service.send_text_message(
                    normalized_phone,
                    "👋 <b>Welcome!</b>\n\n"
                    "You're messaging the facilities team.\n\n"
                    "First, what's your name?",
                )
                return

        # --- Ghost-room concierge reply ---
        try:
            from app.services.ghost_room_notifier import process_concierge_whatsapp_reply

            result = await process_concierge_whatsapp_reply(
                from_number,
                content,
                reply_to_message_id=reply_to_message_id,
                message_id=message_id,
            )
            if result.get("handled"):
                response_message = result.get("response_message")
                if response_message:
                    await whatsapp_service.send_text_message(from_number, response_message)
                return
        except Exception as e:
            logger.warning(f"Ghost-room reply handler error: {e}")

        # --- Focus-room concierge reply ---
        try:
            from app.services.focus_room_notifier import process_focus_room_whatsapp_reply

            result = await process_focus_room_whatsapp_reply(
                from_number,
                content,
                reply_to_message_id=reply_to_message_id,
                message_id=message_id,
            )
            if result.get("handled"):
                response_message = result.get("response_message")
                if response_message:
                    await whatsapp_service.send_text_message(from_number, response_message)
                return
        except Exception as e:
            logger.warning(f"Focus-room reply handler error: {e}")

        # --- Comfort complaint agent (multi-turn) ---
        try:
            from langchain_core.messages import HumanMessage

            from app.agents import get_desk_complaint_graph
            from app.agents.complaint_nlp import detect_comfort_complaint

            agent = get_desk_complaint_graph()
            thread_id = f"wa_{from_number}"
            config = {"configurable": {"thread_id": thread_id}}

            # 1. Check for active multi-turn session
            state = agent.get_state(config)
            if state.values and state.values.get("needs_input"):
                result = agent.invoke(
                    {"messages": [HumanMessage(content=content)]},
                    config=config,
                )
                await whatsapp_service.send_text_message(from_number, result.get("response", ""))
                return

            # 2. Detect new comfort complaint
            if detect_comfort_complaint(content):
                result = agent.invoke(
                    {
                        "messages": [HumanMessage(content=content)],
                        "user_id": from_number,
                        "channel": "whatsapp",
                    },
                    config=config,
                )
                await whatsapp_service.send_text_message(from_number, result.get("response", ""))
                return
        except ImportError:
            logger.debug("LangGraph not available, skipping comfort complaint agent")
        except Exception as e:
            logger.warning(f"Comfort complaint agent error: {e}")

        # --- Recommendation approval agent (Tier 2 reply) ---
        try:
            content_upper = content.strip().upper()
            if content_upper.startswith("APPROVE") or content_upper.startswith("REJECT"):
                from langchain_core.messages import HumanMessage

                from app.agents import get_recommendation_graph
                from app.agents.recommendation_tools import (
                    execute_approved_recommendation,
                    reject_recommendation,
                )

                agent = get_recommendation_graph()
                thread_id = f"rec_wa_{from_number}"
                config = {"configurable": {"thread_id": thread_id}}

                state = await agent.aget_state(config)
                if state.values and state.values.get("needs_input"):
                    result = await agent.ainvoke(
                        {"messages": [HumanMessage(content=content)]},
                        config=config,
                    )
                    await whatsapp_service.send_text_message(from_number, result.get("response", ""))
                    return

                # Fallback: no active checkpoint session, execute command directly by rec-id.
                parsed = _parse_approval_command(content)
                action = parsed["action"]
                token = parsed["token"]
                reason = parsed["reason"] or "Rejected via WhatsApp"
                if not token:
                    await whatsapp_service.send_text_message(
                        from_number,
                        "Include recommendation ID, e.g. APPROVE rec-... or REJECT rec-... <reason>.",
                    )
                    return

                rec_id = await _resolve_recommendation_id(token)
                if not rec_id:
                    await whatsapp_service.send_text_message(
                        from_number,
                        f"Recommendation '{token}' not found. Use the full recommendation ID.",
                    )
                    return

                if action == "APPROVE":
                    result = await execute_approved_recommendation(
                        recommendation_id=rec_id,
                        approved_by=f"whatsapp:{from_number}",
                        notes="Approved via WhatsApp fallback",
                    )
                    if result.get("success"):
                        message = f"Recommendation {rec_id[:8]} executed successfully."
                    else:
                        message = f"Could not execute {rec_id[:8]}: {result.get('error_message') or 'unknown error'}"
                else:
                    result = await reject_recommendation(
                        recommendation_id=rec_id,
                        rejected_by=f"whatsapp:{from_number}",
                        reason=reason,
                    )
                    if result.get("success"):
                        message = f"Recommendation {rec_id[:8]} rejected: {reason}"
                    else:
                        message = f"Could not reject {rec_id[:8]}: {result.get('error_message') or 'unknown error'}"

                await whatsapp_service.send_text_message(from_number, message)
                return
        except ImportError:
            logger.debug("LangGraph not available, skipping recommendation approval")
        except Exception as e:
            logger.warning(f"Recommendation approval agent error: {e}")

        # --- Existing routing ---
        if content.startswith("WO-"):
            await handle_work_order_query(from_number, content)
        elif content.lower() in ["status", "summary", "health"]:
            await handle_status_query(from_number)
        elif content.lower() in ["help", "?", "commands"]:
            await send_help_message(from_number)
        elif content.lower() in ["alert", "alerts"]:
            await handle_alerts_query(from_number)
        else:
            await send_unrecognized_message(from_number)

    except Exception as e:
        logger.error(f"Error routing WhatsApp message: {e}")
        try:
            await whatsapp_service.send_text_message(
                from_number, "Sorry, there was an error processing your message. Try again later."
            )
        except Exception as e2:
            logger.error(f"Error sending error message: {e2}")


async def handle_work_order_query(from_number: str, wo_id: str) -> None:
    """Look up and send work order details."""
    message = f"""📋 *Work Order* {wo_id}

Details: [To be integrated with BMS API]
Status: Processing
Assigned: Technician Team

Reply with WO-XXXXX to get another work order info
    """.strip()

    try:
        await whatsapp_service.send_text_message(from_number, message)
    except Exception as e:
        logger.error(f"Error sending WO details: {e}")


async def handle_status_query(from_number: str) -> None:
    """Send facility status summary."""
    message = """📊 *Current Facility Status*

🟢 Equipment: 48/52 healthy (92%)
🟡 Alerts: 3 warnings active
⚠️ Critical: None

Energy: 450 kW current load
Occupancy: 78% (312 people)

Everything operating normally!
    """.strip()

    try:
        await whatsapp_service.send_text_message(from_number, message)
    except Exception as e:
        logger.error(f"Error sending status: {e}")


async def handle_alerts_query(from_number: str) -> None:
    """Send active alerts."""
    message = """🚨 *Active Alerts*

⚠️ Zone-B1-001 occupancy high
⚠️ Chiller temp variance
⚠️ UPS battery low

No critical alerts.

Reply: WO-XXXXX for work order details
    """.strip()

    try:
        await whatsapp_service.send_text_message(from_number, message)
    except Exception as e:
        logger.error(f"Error sending alerts: {e}")


async def send_help_message(from_number: str) -> None:
    """Send help/command list."""
    message = """*SENTRY WhatsApp Bot - Commands*

📋 *WO-XXXXX* - Get work order details
📊 *Status* - Show facility status
🚨 *Alerts* - Check active alerts
❓ *Help* - Show this message

Questions? Contact support@sentry.local
    """.strip()

    try:
        await whatsapp_service.send_text_message(from_number, message)
    except Exception as e:
        logger.error(f"Error sending help: {e}")


async def send_unrecognized_message(from_number: str) -> None:
    """Send error message for unrecognized input."""
    message = "❌ Sorry, I didn't understand that.\n\nType *Help* for available commands."

    try:
        await whatsapp_service.send_text_message(from_number, message)
    except Exception as e:
        logger.error(f"Error sending unrecognized message: {e}")


# Health check endpoint
@router.get("/status")
async def whatsapp_status() -> dict[str, Any]:
    """Get WhatsApp integration status."""
    return {
        "service": whatsapp_service.get_status(),
        "handler": whatsapp_handler.get_status(),
        "enabled": whatsapp_service.enabled,
    }
