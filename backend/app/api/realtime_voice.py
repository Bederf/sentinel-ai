"""OpenAI Realtime-2 voice pipeline — ephemeral token endpoint.

POST /api/chat/realtime/connect
  → validates JWT via existing auth middleware
  → creates OpenAI Realtime session server-side (key never exposed to frontend)
  → returns { token, expires_in, model }
"""

import json
import logging
from datetime import datetime, time
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.config.settings import settings
from app.database.repositories.site_repository import SiteRepository
from app.middleware.auth_middleware import get_current_auth
from app.models.auth import AuthContext

logger = logging.getLogger(__name__)

router = APIRouter()


class RealtimeConnectResponse(BaseModel):
    token: str
    expires_in: int
    model: str = "gpt-4o-mini-realtime"


@router.post("/chat/realtime/connect")
async def connect_realtime_session(
    auth: AuthContext = Depends(get_current_auth),
) -> RealtimeConnectResponse:
    """Create an OpenAI Realtime-2 ephemeral session token.

    Validates the user's JWT, then calls OpenAI's /v1/realtime/sessions endpoint
    server-side to obtain a short-lived ephemeral token that the frontend uses
    to connect directly to OpenAI's WebSocket.

    Rate limited to 30/minute per IP (inherited from the chat router limiter).
    """
    if not settings.openai_realtime_api_key:
        raise HTTPException(
            status_code=503,
            detail="OpenAI Realtime voice is not configured. Set OPENAI_REALTIME_API_KEY.",
        )

    if not settings.realtime_voice_enabled:
        raise HTTPException(
            status_code=503,
            detail="OpenAI Realtime voice is disabled.",
        )

    # Occupied-hours gating: enforce operating hours before issuing token
    site = SiteRepository().get_by_id(auth.site_id)
    if not site:
        raise HTTPException(
            status_code=404,
            detail=f"Site {auth.site_id!r} not found or inaccessible",
        )

    operating_hours = site.get("operating_hours") or {"start": "08:00", "end": "18:00"}
    if isinstance(operating_hours, str):
        try:
            operating_hours = json.loads(operating_hours)
        except (json.JSONDecodeError, TypeError):
            operating_hours = {"start": "08:00", "end": "18:00"}
    if "start" not in operating_hours and "weekday" in operating_hours:
        weekday = operating_hours.get("weekday", "08:00-18:00")
        if "-" in str(weekday):
            parts = str(weekday).split("-", 1)
            operating_hours = {"start": parts[0], "end": parts[1]}
        else:
            operating_hours = {"start": "08:00", "end": "18:00"}

    start_str = operating_hours.get("start", "08:00")
    end_str = operating_hours.get("end", "18:00")
    start = time.fromisoformat(start_str)
    end = time.fromisoformat(end_str)
    now = datetime.now()
    current = time.fromisoformat(f"{now.hour:02}:{now.minute:02}")
    if not (start <= current <= end):
        raise HTTPException(
            status_code=403,
            detail=f"Voice unavailable outside operating hours ({start_str}-{end_str})",
        )

    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
        try:
            response = await client.post(
                "https://api.openai.com/v1/realtime/sessions",
                headers={
                    "Authorization": f"Bearer {settings.openai_realtime_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-4o-mini-realtime",
                    "voice": "alloy",
                },
            )
        except httpx.TimeoutException:
            logger.error("OpenAI Realtime session creation timed out")
            raise HTTPException(status_code=504, detail="OpenAI timeout")
        except httpx.HTTPError as e:
            logger.error(f"OpenAI Realtime session creation failed: {e}")
            raise HTTPException(status_code=502, detail="OpenAI API error")

    if response.status_code != 200:
        logger.error(f"OpenAI Realtime session error {response.status_code}: {response.text[:200]}")
        raise HTTPException(status_code=502, detail="Failed to create Realtime session")

    data: dict[str, Any] = response.json()

    # Extract ephemeral token from the nested client_secret structure
    client_secret: dict[str, Any] = data.get("client_secret", {})
    token: str = client_secret.get("token", "")
    expires_in: int = client_secret.get("expires_in", 3600)

    if not token:
        logger.error("OpenAI returned empty token in Realtime session response")
        raise HTTPException(status_code=502, detail="Empty token from OpenAI")

    logger.info(f"Realtime session token created for user {auth.user_id}")

    return RealtimeConnectResponse(
        token=token,
        expires_in=expires_in,
        model="gpt-4o-mini-realtime",
    )
