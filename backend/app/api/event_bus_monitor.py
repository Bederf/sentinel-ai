"""
Event Bus Monitoring API Routes.

Provides read-only monitoring endpoints for the SENTINEL event bus:
- Metrics (events emitted, handler stats, by domain/importance)
- History (with filters)
- Event chain lookup (by correlation ID)
- Subscription listing (for debugging)

Phase 139-01: API monitoring routes.
"""

import logging

from fastapi import APIRouter, Depends, Query

from app.middleware.auth_middleware import get_current_auth
from app.models.auth import AuthContext
from app.services.event_bus import Importance, get_event_bus

logger = logging.getLogger("sentinel.event_bus.api")

router = APIRouter(prefix="/api/event-bus", tags=["event-bus"])


@router.get("/metrics")
async def get_event_bus_metrics(
    auth: AuthContext | None = Depends(get_current_auth),
) -> dict:
    """Return event bus metrics for System Health dashboard.

    Includes: events_emitted, handlers_invoked, handler_errors,
    by_domain counts, by_importance counts, subscription_count,
    history_size.
    """
    bus = get_event_bus()
    return {"status": "ok", "metrics": bus.metrics}


@router.get("/history")
async def get_event_history(
    event_type: str | None = Query(None, description="Filter by exact event type"),
    domain: str | None = Query(None, description="Filter by domain (e.g. 'sensor')"),
    site_id: str | None = Query(None, description="Filter by site ID"),
    correlation_id: str | None = Query(None, description="Filter by correlation ID"),
    min_importance: str | None = Query(
        None,
        description="Filter by minimum importance: INFO, LOW, MEDIUM, HIGH, CRITICAL",
    ),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results"),
    auth: AuthContext | None = Depends(get_current_auth),
) -> dict:
    """Query event history with optional filters.

    Returns events from the rolling buffer (most recent first).
    """
    bus = get_event_bus()

    # Parse min_importance string to enum
    importance_filter = None
    if min_importance:
        try:
            importance_filter = Importance[min_importance.upper()]
        except KeyError:
            return {
                "status": "error",
                "detail": f"Invalid importance: {min_importance}. Valid: INFO, LOW, MEDIUM, HIGH, CRITICAL",
            }

    events = bus.get_history(
        event_type=event_type,
        domain=domain,
        site_id=site_id,
        correlation_id=correlation_id,
        min_importance=importance_filter,
        limit=limit,
    )

    return {"status": "ok", "count": len(events), "events": events}


@router.get("/chain/{correlation_id}")
async def get_event_chain(
    correlation_id: str,
    auth: AuthContext | None = Depends(get_current_auth),
) -> dict:
    """Get all events in a correlation chain.

    Returns events ordered by timestamp for the given correlation ID.
    """
    bus = get_event_bus()
    chain = bus.get_event_chain(correlation_id)
    return {"status": "ok", "correlation_id": correlation_id, "count": len(chain), "events": chain}


@router.get("/subscriptions")
async def get_event_subscriptions(
    auth: AuthContext | None = Depends(get_current_auth),
) -> dict:
    """List all registered event subscriptions for debugging.

    Shows pattern, pause state, importance filters, and site/domain filters.
    """
    bus = get_event_bus()
    subs = bus.get_subscriptions()
    return {"status": "ok", "count": len(subs), "subscriptions": subs}
