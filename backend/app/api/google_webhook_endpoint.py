"""Google Calendar webhook endpoints.

Only the calendar webhook is an active integration. The old /token path is
kept as an explicit retired endpoint so stale local clients do not create auth
failure noise.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks/google", tags=["google_webhook"])


@router.api_route("/calendar", methods=["GET", "POST"])
async def handle_google_calendar_webhook(request: Request) -> Response:
    """Accept Google Calendar push notifications.

    Google Calendar webhooks notify that a watched calendar changed; the actual
    sync is handled elsewhere. Return 204 so Google/local probes do not retry.
    """
    channel_id = request.headers.get("X-Goog-Channel-ID")
    resource_state = request.headers.get("X-Goog-Resource-State")
    if channel_id or resource_state:
        logger.info(
            "[GoogleWebhook] Calendar notification received: channel=%s state=%s",
            channel_id or "unknown",
            resource_state or "unknown",
        )
    return Response(status_code=204)


@router.api_route("/token", methods=["GET", "POST"])
async def retired_google_token_endpoint() -> JSONResponse:
    """Retired endpoint retained to make stale callers fail cleanly."""
    return JSONResponse(
        status_code=410,
        content={
            "status": "retired",
            "detail": "Use /api/webhooks/google/calendar for Google Calendar push notifications.",
        },
    )
