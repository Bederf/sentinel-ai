"""
Server-Sent Events (SSE) endpoint for decision execution updates.

Phase 170-03: Control Actuation Loop — SSE Stream

Frontend opens: EventSource('/api/events?correlation_id={id}')
Backend emits events via: event_stream.emit(event_type, correlation_id, payload)
Frontend receives and processes events via EventListener
"""

import asyncio
import json
import logging
from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from app.middleware.event_stream import event_stream

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["events"])


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
                f"SSE stream error: {str(e)}",
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
