"""Microsoft Graph webhook endpoint for real-time Outlook event ingestion.

POST /api/webhooks/graph/events
  1. Validation handshake (GET ?validationToken=XYZ -> return plain text)
  2. Notification (POST) -> validate clientState -> extract eventId -> process async

Security:
  - clientState is validated against the stored subscription secret
  - subscriptionId is validated against stored subscription
  - Requests that fail validation return 403
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import PlainTextResponse

from app.services.graph_event_processor import process_graph_event
from app.services.graph_subscription_service import graph_subscription_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks", tags=["graph_webhook"])


@router.post("/graph/events")
async def handle_graph_notification(request: Request) -> Response:
    """Handle incoming Microsoft Graph webhook notifications.

    Two modes:
    - GET with ?validationToken=XYZ: Graph subscription validation handshake
    - POST: Event notification (created/updated/deleted)

    Always returns 202 immediately for POST to avoid Graph retries.
    """
    # Mode A: Graph validation handshake (Microsoft sends GET to verify endpoint)
    validation_token = request.query_params.get("validationToken")
    if validation_token is not None:
        logger.debug("[GraphWebhook] Validation handshake received")
        return PlainTextResponse(content=validation_token, media_type="text/plain")

    # Mode B: Event notification
    try:
        body = await request.json()
    except Exception as exc:
        logger.warning("[GraphWebhook] Failed to parse notification body: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid JSON body") from exc

    notifications = body.get("value", [])
    if not notifications:
        return Response(status_code=202, content="")

    for notification in notifications:
        subscription_id = notification.get("subscriptionId", "")
        client_state = notification.get("clientState", "")
        change_type = notification.get("changeType", "")
        resource = notification.get("resource", "")

        # Security: validate subscriptionId and clientState
        stored = graph_subscription_service.get_subscription()
        if not stored:
            logger.warning("[GraphWebhook] No stored subscription — rejecting notification")
            raise HTTPException(status_code=403, detail="No active subscription")

        if stored.subscription_id != subscription_id:
            logger.warning("[GraphWebhook] Unknown subscriptionId: %s", subscription_id)
            raise HTTPException(status_code=403, detail="Unknown subscription")

        if stored.client_state != client_state:
            logger.warning("[GraphWebhook] clientState mismatch for subscription %s", subscription_id)
            raise HTTPException(status_code=403, detail="Invalid clientState")

        # Extract event_id from resource path: "Users/.../events/{event_id}"
        event_id = resource.split("/")[-1]
        if not event_id:
            logger.warning("[GraphWebhook] Could not extract event_id from resource: %s", resource)
            continue

        # Queue async processing — do NOT block the webhook response

        asyncio.create_task(_process_with_error_logging(change_type, event_id))

    return Response(status_code=202, content="")


async def _process_with_error_logging(change_type: str, event_id: str) -> None:
    """Wrapper to catch and log errors from the async event processor."""
    try:
        await process_graph_event(change_type, event_id)
    except Exception as exc:
        logger.error(
            "[GraphWebhook] process_graph_event failed for %s (%s): %s", event_id, change_type, exc, exc_info=True
        )
