"""Server-Sent Events (SSE) API for real-time dashboard updates.

Provides streaming endpoint for dashboard to receive real-time events:
- Alert creation
- Health score changes
- Work order status updates
- Inspection completions
"""

import asyncio
import logging
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.services.event_emitter import get_event_emitter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("/stream")
async def stream_events(request: Request) -> StreamingResponse:
    """
    Server-Sent Events stream for real-time dashboard updates.

    Clients open a persistent connection and receive events as they occur:
    - alert_created: New equipment alert
    - health_changed: Equipment health score update
    - work_order_updated: Work order status change
    - inspection_completed: Inspection finding submitted

    **Event Format:**
    ```
    data: {"type": "alert_created", "data": {...}, "timestamp": "2026-02-12T..."}

    data: {"type": "health_changed", "data": {...}, "timestamp": "2026-02-12T..."}
    ```

    **Usage (Frontend):**
    ```javascript
    const eventSource = new EventSource('/api/events/stream');
    eventSource.addEventListener('message', (e) => {
        const event = JSON.parse(e.data);
        console.log(`Event: ${event.type}`, event.data);
    });
    ```

    **Returns:**
        StreamingResponse with SSE content type and persistent connection
    """
    emitter = get_event_emitter()

    async def event_generator():
        """Generate SSE events for connected client."""
        # Register this client
        client_queue = await emitter.register_client()
        logger.info("New SSE client connected")

        try:
            # Send initial keepalive
            yield "data: {\"type\": \"connected\", \"data\": {}}\n\n"

            # Listen for events on client queue
            while True:
                try:
                    # Wait for event with timeout to check if client still connected
                    event = await asyncio.wait_for(client_queue.get(), timeout=30)
                    yield event.to_sse()
                except asyncio.TimeoutError:
                    # Send keepalive comment to detect disconnections
                    yield ": keepalive\n\n"
                    continue

        except asyncio.CancelledError:
            logger.info("SSE client disconnected (cancelled)")
            await emitter.unregister_client(client_queue)
        except Exception as e:
            logger.error(f"SSE stream error: {e}")
            await emitter.unregister_client(client_queue)
        finally:
            # Ensure client is unregistered
            try:
                await emitter.unregister_client(client_queue)
            except Exception:
                pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable Nginx buffering
            "Connection": "keep-alive"
        }
    )


@router.get("/health")
async def check_events_endpoint() -> dict:
    """
    Health check for events endpoint.

    **Returns:**
        Status information for SSE service
    """
    emitter = get_event_emitter()
    return {
        "status": "healthy",
        "connected_clients": len(emitter._clients),
        "service": "events"
    }
