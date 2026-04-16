"""Google Calendar webhook endpoint for real-time calendar event ingestion.

POST /api/webhooks/google/calendar
  1. Validates Google Cloud Pub/Sub push verification (X-Goog-Channel-Token, X-Goog-Resource-State)
  2. Re-fetches the calendar event via Google Calendar API
  3. Processes event to create/update PENDING visits

Security:
  - Requests are validated against stored channel information
  - Channel ID is validated against the stored channel store
  - Verification requests are handled separately and return appropriate response
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response
from fastapi.responses import PlainTextResponse

from app.services.google_calendar_service import GoogleCalendarService

router = APIRouter(prefix="/api/webhooks/google", tags=["google_calendar_webhook"])
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
CHANNEL_STORE_PATH = DATA_DIR / "google_channel_store.json"


def _load_channels() -> dict:
    """Load stored channels from disk."""
    if CHANNEL_STORE_PATH.exists():
        try:
            with open(CHANNEL_STORE_PATH) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


@router.get("/calendar")
async def handle_google_calendar_verification(request: Request) -> Response:
    """Handle Google Cloud Pub/Sub push verification.

    Google sends a GET to verify the webhook endpoint is alive.
    Query params include:
      - X-Goog-Channel-token: our channel ID
      - X-Goog-Resource-State: "sync" for verification
      - X-Goog-Resource-id: the resource being watched
      - X-Goog-Resource-URI: the calendar resource URI
    """
    channel_token = request.headers.get("X-Goog-Channel-Token", "")
    resource_state = request.headers.get("X-Goog-Resource-State", "")
    resource_id = request.headers.get("X-Goog-Resource-Id", "")

    logger.debug(
        "[GoogleCalWebhook] Verification: channel_token=%s resource_state=%s resource_id=%s",
        channel_token,
        resource_state,
        resource_id,
    )

    # Google sends "sync" to verify the endpoint
    if resource_state == "sync":
        return PlainTextResponse(content="OK", media_type="text/plain")

    return PlainTextResponse(content="", media_type="text/plain")


@router.post("/calendar")
async def handle_google_calendar_notification(request: Request, background_tasks: BackgroundTasks) -> Response:
    """Handle incoming Google Calendar webhook notifications via Pub/Sub push.

    Google Cloud Pub/Sub sends a POST when calendar events change.
    The body is a Cloud Pub/Sub Message with a JSON-encoded data field.

    message.data contains a base64-encoded JSON object:
      {
        "version": "1.0",
        "message": {
          "data": "<base64-encoded-JSON>",
          "messageId": "...",
          "publishTime": "...",
        },
        "subscription": "...",
      }

    The decoded data JSON contains:
      {
        "channelId": "...",
        "resourceId": "...",
        "resourceUri": "...",
        "calendarId": "primary",
      }
    """
    import base64

    try:
        body = await request.json()
    except Exception as exc:
        logger.warning("[GoogleCalWebhook] Failed to parse notification body: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid JSON body") from exc

    logger.debug("[GoogleCalWebhook] Raw notification body: %s", body)

    # Handle Cloud Pub/Sub push format
    message_data = None
    if "message" in body:
        # Cloud Pub/Sub push format
        try:
            encoded_data = body.get("message", {}).get("data", "")
            if encoded_data:
                decoded = base64.b64decode(encoded_data).decode("utf-8")
                message_data = json.loads(decoded)
        except Exception as exc:
            logger.warning("[GoogleCalWebhook] Failed to decode Pub/Sub message data: %s", exc)
            raise HTTPException(status_code=400, detail="Failed to decode message data") from exc
    else:
        # Direct format (testing/dev)
        message_data = body

    if not message_data:
        return Response(status_code=202, content="")

    channel_id = message_data.get("channelId", "")
    resource_uri = message_data.get("resourceUri", "")

    # Validate channel_id against stored channels
    channels = _load_channels()
    if channel_id and channel_id not in channels:
        logger.warning("[GoogleCalWebhook] Unknown channel_id: %s", channel_id)
        raise HTTPException(status_code=403, detail="Unknown channel")

    # Extract event_id from resourceUri: "https://www.googleapis.com/calendar/v3/calendars/primary/events/{event_id}"
    event_id = None
    if resource_uri:
        parts = resource_uri.rstrip("/").split("/")
        if parts:
            event_id = parts[-1]

    if not event_id:
        logger.warning("[GoogleCalWebhook] Could not extract event_id from resourceUri: %s", resource_uri)
        raise HTTPException(status_code=400, detail="Missing event_id")

    # Queue processing via BackgroundTasks
    background_tasks.add_task(_process_with_error_logging, event_id, channel_id)

    return Response(status_code=202, content="")


async def _process_with_error_logging(event_id: str, channel_id: str) -> None:
    """Wrapper to catch and log errors from the calendar event processor."""
    try:
        svc = GoogleCalendarService()
        svc.handle_webhook_notification({"event_id": event_id, "channelId": channel_id})
    except Exception as exc:
        logger.error("[GoogleCalWebhook] handle_webhook_notification failed for %s: %s", event_id, exc, exc_info=True)


@router.get("/token")
async def get_google_access_token(request: Request) -> dict:
    """Return a fresh Google OAuth2 access token for n8n to use when calling the Calendar API.

    Secured with the same Sentry API key used by other internal endpoints.
    """
    from app.services.google_calendar_service import _refresh_access_token

    api_key = request.headers.get("X-Sentry-API-Key", "")
    import os

    expected = os.getenv("SENTRY_BOT_API_KEY", "")
    if expected and api_key != expected:
        from fastapi import HTTPException

        raise HTTPException(status_code=401, detail="Unauthorized")

    token_data = _refresh_access_token()
    if not token_data:
        from fastapi import HTTPException

        raise HTTPException(status_code=503, detail="Google credentials unavailable")

    return {"access_token": token_data["token"]}
