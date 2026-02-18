"""Server-Sent Events (SSE) API for real-time dashboard updates.

Provides streaming endpoint for dashboard to receive real-time events:
- Alert creation
- Health score changes
- Work order status updates
- Inspection completions

Security: Uses ticket-based auth to avoid exposing JWTs in EventSource URLs.
Frontend POSTs to /ticket with Bearer token, gets a short-lived random ticket,
then opens EventSource with ?ticket=UUID (safe to appear in logs/console).
"""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.middleware.auth_middleware import require_auth
from app.models.auth import AuthContext, AuthLevel
from app.services.event_emitter import get_event_emitter
from app.config.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/events", tags=["events"])

# =============================================================================
# In-memory ticket store for SSE auth
# Tickets are single-use, short-lived (30s), and random UUIDs (not JWTs)
# =============================================================================

_SSE_TICKETS: Dict[str, Tuple[datetime, str]] = {}  # ticket -> (expires_at, user_id)
_TICKET_TTL_SECONDS = 30
_MAX_TICKETS = 1000  # Prevent memory bloat


def _cleanup_expired_tickets() -> None:
    """Remove expired tickets from the store."""
    now = datetime.utcnow()
    expired = [t for t, (exp, _) in _SSE_TICKETS.items() if now > exp]
    for t in expired:
        _SSE_TICKETS.pop(t, None)


def _create_ticket(user_id: str) -> str:
    """Create a short-lived, single-use SSE ticket.

    Returns:
        Random UUID ticket string
    """
    _cleanup_expired_tickets()

    # Enforce max tickets to prevent memory issues
    if len(_SSE_TICKETS) >= _MAX_TICKETS:
        # Remove oldest tickets
        sorted_tickets = sorted(_SSE_TICKETS.items(), key=lambda x: x[1][0])
        for t, _ in sorted_tickets[: len(sorted_tickets) // 2]:
            _SSE_TICKETS.pop(t, None)

    ticket = str(uuid.uuid4())
    expires_at = datetime.utcnow() + timedelta(seconds=_TICKET_TTL_SECONDS)
    _SSE_TICKETS[ticket] = (expires_at, user_id)
    return ticket


def _validate_ticket(ticket: str) -> Optional[str]:
    """Validate and consume a single-use SSE ticket.

    Returns:
        user_id if valid, None if invalid/expired/already-used
    """
    _cleanup_expired_tickets()

    entry = _SSE_TICKETS.pop(ticket, None)  # Remove immediately (single-use)
    if entry is None:
        return None

    expires_at, user_id = entry
    if datetime.utcnow() > expires_at:
        return None

    return user_id


# =============================================================================
# Endpoints
# =============================================================================


@router.post("/ticket")
async def create_sse_ticket(
    auth: AuthContext = Depends(require_auth(AuthLevel.AUTHENTICATED)),
) -> dict:
    """Create a short-lived, single-use ticket for SSE stream authentication.

    The frontend calls this with a Bearer token in the Authorization header
    (which is NOT visible in the URL), then uses the returned ticket UUID
    to open the EventSource connection.

    **Security:**
    - Ticket is a random UUID (not a JWT) - safe to appear in URLs/logs
    - Single-use: consumed on first SSE connection
    - Expires in 30 seconds if unused
    - JWT never appears in any URL

    **Returns:**
        {"ticket": "random-uuid-string"}
    """
    ticket = _create_ticket(auth.user_id)
    return {"ticket": ticket}


@router.get("/stream")
async def stream_events(request: Request) -> StreamingResponse:
    """
    Server-Sent Events stream for real-time dashboard updates.

    Authentication: Pass a ticket from POST /api/events/ticket as query param.
    In demo mode, unauthenticated connections are allowed.

    Clients open a persistent connection and receive events as they occur:
    - alert_created: New equipment alert
    - health_changed: Equipment health score update
    - work_order_updated: Work order status change
    - inspection_completed: Inspection finding submitted

    **Event Format:**
    ```
    data: {"type": "alert_created", "data": {...}, "timestamp": "2026-02-12T..."}
    ```

    **Usage (Frontend):**
    ```javascript
    // Step 1: Get ticket (JWT in Authorization header, not in URL)
    const res = await fetch('/api/events/ticket', {
        method: 'POST',
        headers: { 'Authorization': 'Bearer <jwt>' }
    });
    const { ticket } = await res.json();

    // Step 2: Open SSE with ticket (random UUID, safe in URL)
    const eventSource = new EventSource(`/api/events/stream?ticket=${ticket}`);
    ```

    **Returns:**
        StreamingResponse with SSE content type and persistent connection
    """
    # Validate ticket if provided
    ticket = request.query_params.get("ticket", "")
    user_id = None

    if ticket:
        user_id = _validate_ticket(ticket)
        if user_id is None and not settings.demo_mode:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired SSE ticket",
            )
    elif not settings.demo_mode:
        # No ticket and not demo mode - reject
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="SSE ticket required. POST /api/events/ticket first.",
        )

    emitter = get_event_emitter()

    async def event_generator():
        """Generate SSE events for connected client."""
        # Register this client
        client_queue = await emitter.register_client()
        logger.info("New SSE client connected (user=%s)", user_id or "anonymous")

        try:
            # Send initial keepalive
            yield 'data: {"type": "connected", "data": {}}\n\n'

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
            "Connection": "keep-alive",
        },
    )


@router.get("/health")
async def check_events_endpoint() -> dict:
    """
    Health check for events endpoint.

    **Returns:**
        Status information for SSE service
    """
    emitter = get_event_emitter()
    return {"status": "healthy", "connected_clients": len(emitter._clients), "service": "events"}
