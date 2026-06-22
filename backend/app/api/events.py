"""Server-Sent Events endpoints.

This module now serves two SSE flows:

1. Legacy correlation-scoped execution updates at ``GET /api/events``.
2. Dashboard-wide event streaming via:
   - ``POST /api/events/ticket``
   - ``GET /api/events/stream?ticket=...``

Tickets are stored in Redis so they're shared across all uvicorn workers.
"""

import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from app.middleware.event_stream import event_stream
from app.services.event_emitter import get_event_emitter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["events"])

_TICKET_TTL_SECONDS = 30


def _redis() -> "redis.Redis":  # noqa: F821
    import redis as _redis

    return _redis.Redis.from_url("redis://localhost:6379/0")


def _create_ticket(user_id: str) -> str:
    """Create a short-lived, single-use SSE ticket in Redis."""
    r = _redis()
    ticket = str(uuid.uuid4())
    key = f"sse:ticket:{ticket}"
    r.setex(key, _TICKET_TTL_SECONDS, user_id)
    return ticket


def _validate_ticket(ticket: str) -> str | None:
    """Validate and consume a dashboard SSE ticket from Redis (single-use)."""
    r = _redis()
    key = f"sse:ticket:{ticket}"
    user_id = r.get(key)
    if user_id is None:
        return None
    r.delete(key)
    return user_id.decode("utf-8") if isinstance(user_id, bytes) else user_id


@router.post("/events/ticket")
async def create_dashboard_events_ticket(request: Request) -> dict[str, str]:
    """Create a short-lived ticket for the dashboard SSE stream."""
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required for SSE ticket",
        )

    user_id = auth_header[7:][:32] or "anonymous"
    return {"ticket": _create_ticket(user_id)}


@router.get("/events/stream")
async def stream_dashboard_events(request: Request) -> StreamingResponse:
    """Stream dashboard-wide equipment and work-order events over SSE."""
    ticket = request.query_params.get("ticket", "")
    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="SSE ticket required. POST /api/events/ticket first.",
        )

    user_id = _validate_ticket(ticket)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired SSE ticket",
        )

    emitter = get_event_emitter()

    async def dashboard_event_generator():
        client_queue = await emitter.register_client()
        logger.info("Dashboard SSE client connected", extra={"user_id": user_id})

        try:
            # Let the frontend know the stream is live immediately.
            yield 'data: {"type":"connected","data":{},"timestamp":null}\n\n'

            while True:
                try:
                    event = await asyncio.wait_for(client_queue.get(), timeout=15)
                    yield event.to_sse()
                except TimeoutError:
                    # Heartbeat keeps proxies and browsers from closing idle streams.
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            logger.debug("Dashboard SSE stream cancelled", extra={"user_id": user_id})
        finally:
            await emitter.unregister_client(client_queue)
            logger.info("Dashboard SSE client disconnected", extra={"user_id": user_id})

    return StreamingResponse(
        dashboard_event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/events/health")
async def dashboard_events_health() -> dict[str, str]:
    """Lightweight health probe for the dashboard SSE transport."""
    return {"status": "ok"}


@router.get("/events")
async def event_stream_endpoint(correlation_id: str = Query(...)):
    """
    Server-Sent Events endpoint for decision verification updates.

    Frontend subscribes with:
        const eventSource = new EventSource(
            `/api/events?correlation_id=${correlationId}`
        );
        eventSource.addEventListener("COMMAND_VERIFIED", (event) => {
            const data = JSON.parse(event.data);
            // Handle verification
        });

    Backend emits with:
        await event_stream.emit(
            event_type="COMMAND_VERIFIED",
            correlation_id=correlation_id,
            payload={"decision_id": "...", "verification_time": ...}
        )

    Args:
        correlation_id: UUID linking frontend request to backend execution

    Returns:
        StreamingResponse with text/event-stream content type
    """

    async def event_generator():
        """Generate SSE events from queue."""
        # Subscribe to events for this correlation_id
        channel = await event_stream.subscribe(correlation_id)

        logger.debug(
            "SSE client connected",
            extra={"correlation_id": correlation_id},
        )

        try:
            while True:
                # Wait for event (blocks until available)
                event = await channel.get()

                event_type = event.get("event_type", "UNKNOWN")
                payload = event.get("payload", {})

                # SSE format: event: {type}\ndata: {json}\n\n
                yield f"event: {event_type}\n"
                yield f"data: {json.dumps(payload)}\n\n"

                logger.debug(
                    f"Emitted SSE event {event_type}",
                    extra={"correlation_id": correlation_id},
                )

                # Auto-close after terminal events
                if event_type in ["COMMAND_VERIFIED", "COMMAND_TIMEOUT", "COMMAND_FAILED"]:
                    logger.debug(
                        f"Terminal event {event_type}, closing SSE stream",
                        extra={"correlation_id": correlation_id},
                    )
                    break

        except asyncio.CancelledError:
            logger.debug(
                "SSE stream cancelled",
                extra={"correlation_id": correlation_id},
            )
        except Exception as e:
            logger.error(
                f"SSE stream error: {e!s}",
                extra={"correlation_id": correlation_id},
                exc_info=True,
            )
        finally:
            # Cleanup: unsubscribe and close connection
            await event_stream.unsubscribe(correlation_id)
            logger.debug(
                "SSE client disconnected",
                extra={"correlation_id": correlation_id},
            )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable proxy buffering
        },
    )
