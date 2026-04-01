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

import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response
from fastapi.responses import PlainTextResponse

from app.services.graph_event_processor import process_graph_event
from app.services.graph_subscription_service import graph_subscription_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks", tags=["graph_webhook"])


@router.post("/graph/events")
async def handle_graph_notification(request: Request, background_tasks: BackgroundTasks) -> Response:
    """Handle incoming Microsoft Graph webhook notifications.

    Two modes:
    - GET with ?validationToken=XYZ: Graph subscription validation handshake
    - POST: Event notification (created/updated/deleted)

    Always returns 202 immediately for POST to avoid Graph retries.
    Uses FastAPI BackgroundTasks (not asyncio.create_task) to survive request context teardown.
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

    # Validate subscription once for all notifications in this batch
    stored = graph_subscription_service.get_subscription()
    if not stored:
        logger.warning("[GraphWebhook] No stored subscription — rejecting batch")
        raise HTTPException(status_code=403, detail="No active subscription")

    processed = 0
    for notification in notifications:
        subscription_id = notification.get("subscriptionId", "")
        client_state = notification.get("clientState", "")
        change_type = notification.get("changeType", "")
        resource = notification.get("resource", "")

        # Security: validate subscriptionId and clientState per notification
        if stored.subscription_id != subscription_id:
            logger.warning("[GraphWebhook] Unknown subscriptionId: %s", subscription_id)
            continue  # Skip invalid notification, process rest of batch

        if stored.client_state != client_state:
            logger.warning("[GraphWebhook] clientState mismatch for subscription %s", subscription_id)
            continue  # Skip invalid notification, process rest of batch

        # Extract event_id from resource path: "Users/.../events/{event_id}"
        event_id = resource.split("/")[-1]
        if not event_id:
            logger.warning("[GraphWebhook] Could not extract event_id from resource: %s", resource)
            continue

        # Queue via BackgroundTasks — survives request context teardown
        background_tasks.add_task(_process_with_error_logging, change_type, event_id)
        processed += 1

    if processed == 0:
        logger.warning("[GraphWebhook] No valid notifications in batch after filtering")
        raise HTTPException(status_code=403, detail="No valid notifications")

    return Response(status_code=202, content="")


async def _process_with_error_logging(change_type: str, event_id: str) -> None:
    """Wrapper to catch and log errors from the async event processor."""
    try:
        await process_graph_event(change_type, event_id)
    except Exception as exc:
        logger.error(
            "[GraphWebhook] process_graph_event failed for %s (%s): %s", event_id, change_type, exc, exc_info=True
        )
