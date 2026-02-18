"""
WhatsApp webhook endpoint for receiving incoming messages.
Integrates with FastAPI for webhook verification and message handling.
"""

from fastapi import APIRouter, Request, HTTPException, Query
from app.handlers.whatsapp_handler import get_whatsapp_handler
from app.integrations.whatsapp_service import get_whatsapp_service
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp"])

whatsapp_service = get_whatsapp_service()
whatsapp_handler = get_whatsapp_handler()


@router.get("/webhooks")
async def verify_whatsapp_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge")
) -> int:
    """
    WhatsApp webhook verification endpoint (GET).
    Meta sends: hub.mode, hub.verify_token, hub.challenge

    This endpoint is called by Meta during webhook configuration.
    """
    logger.info(f"Webhook verification request: mode={hub_mode}")

    if hub_mode != "subscribe":
        logger.warning(f"Invalid webhook mode: {hub_mode}")
        raise HTTPException(status_code=403, detail="Invalid mode")

    if not whatsapp_service.verify_webhook_token(hub_verify_token):
        logger.warning("Invalid webhook verification token")
        raise HTTPException(status_code=403, detail="Invalid token")

    logger.info("WhatsApp webhook verified successfully")
    return int(hub_challenge)


@router.post("/webhooks")
async def handle_whatsapp_message(request: Request) -> Dict[str, str]:
    """
    Handle incoming WhatsApp messages (POST).

    This endpoint receives all WhatsApp events (messages, status updates, etc).
    """
    try:
        body = await request.json()
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
        timestamp = message.get("timestamp")
        message_type = message.get("type", "text")

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

        logger.info(f"[WhatsApp] Incoming from {from_number}: type={message_type}, content={content[:50] if content else 'N/A'}")

        if not content:
            logger.debug("Message received but no extractable content")
            return {"status": "ok"}

        # Route message to appropriate handler
        await route_incoming_message(from_number, content, message_type, message_id)

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Error handling WhatsApp webhook: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


async def route_incoming_message(
    from_number: str,
    content: str,
    message_type: str,
    message_id: str
) -> None:
    """
    Route incoming WhatsApp message to appropriate handler.

    Supports:
    - "WO-XXXXX" → Show work order details
    - "Status" or "Summary" → Show facility status
    - "Help" or "?" → Show available commands
    - Other text → Send help message
    """
    try:
        # Log interaction
        logger.debug(f"Routing message from {from_number}: {content}")

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
                from_number,
                "Sorry, there was an error processing your message. Try again later."
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
async def whatsapp_status() -> Dict[str, Any]:
    """Get WhatsApp integration status."""
    return {
        "service": whatsapp_service.get_status(),
        "handler": whatsapp_handler.get_status(),
        "enabled": whatsapp_service.enabled
    }
