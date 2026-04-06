"""
Decision Moment Event Bus Subscribers — Phase 164-04.

Wires the event bus to the Decision Moment cache so the Crisis State page
receives pre-assembled payloads within milliseconds of a CRITICAL fault firing.

Subscriber list:
1. _on_critical_event   — pre-warms the decision payload cache on CRITICAL events
2. _on_fault_resolved   — invalidates the cache when INFO-level events indicate resolution

Note on fault resolution: The event bus does not have a dedicated "fault_resolved"
event type in the current implementation. INFO-importance events are used as a proxy
for resolution (low-urgency state). If a dedicated fault_resolved event type is added
in future, replace the INFO subscription with a pattern like "fault.resolved".
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from app.api.decisions import cache_decision_payload, clear_decision_payload
from app.services.decision_moment_aggregator import DecisionMomentAggregator
from app.services.event_bus import Importance, SentinelEvent, get_event_bus

logger = logging.getLogger(__name__)
_aggregator = DecisionMomentAggregator()


async def _assemble_and_cache(event: SentinelEvent) -> None:
    """Inner coroutine — runs as background task, does not block the event bus publish loop.

    assemble() is synchronous (CPU-bound, < 50ms on Jetson). Wrapping in
    asyncio.create_task() releases the event bus handler immediately so other
    subscribers can continue while the payload is being assembled.
    """
    try:
        payload = _aggregator.assemble(
            building_id=event.site_id or "unknown",
            fault_type=event.event_type,
            severity="critical",
            asset_id=event.equipment_id or "",
            trigger_reason=event.event_type,
            current_hour=datetime.now().hour,
        )
        cache_decision_payload(event.site_id or "unknown", payload.to_dict())
        logger.info(
            "Decision payload pre-warmed for %s site %s",
            event.event_type,
            event.site_id,
        )
    except Exception as e:
        logger.warning("Decision pre-warm failed: %s", e)


async def _on_critical_event(event: SentinelEvent) -> None:
    """Pre-warm the Decision Page cache when a CRITICAL event fires.

    Fire-and-forget: spawns _assemble_and_cache as a background task so the
    event bus publish loop is never blocked by the synchronous assemble() call.
    """
    asyncio.create_task(_assemble_and_cache(event))


async def _on_fault_resolved(event: SentinelEvent) -> None:
    """
    Invalidate the cache when an INFO-importance event signals resolution.
    Prevents the crisis page showing stale urgency after the fault clears.
    Without this: operator dismisses, fault resolves, but kiosk shows urgency 0.82
    until the 30s TTL expires — eroding trust in the system.
    """
    try:
        if event.site_id:
            clear_decision_payload(event.site_id)
            logger.info(
                "Decision cache invalidated — fault resolved: %s site %s",
                event.event_type,
                event.site_id,
            )
    except Exception as e:
        logger.warning("Decision cache clear failed: %s", e)


def register_decision_subscribers() -> None:
    """Register all decision-moment event subscribers. Call during app startup.

    Subscribes to:
    - All events with min_importance=CRITICAL  → pre-warms decision payload cache
    - All events with min_importance=INFO (exact INFO level via filter) → clears cache
      (proxy for fault resolution until a dedicated fault_resolved event type exists)
    """
    bus = get_event_bus()

    # Subscribe to all CRITICAL-importance events (any pattern)
    bus.subscribe(
        pattern="*",
        handler=_on_critical_event,
        min_importance=Importance.CRITICAL,
    )

    # Subscribe to INFO-importance events as fault-resolved proxy.
    # Filter: only exact INFO level (not HIGH/CRITICAL passing through)
    # so we don't clear the cache on every escalated event.
    # Gap: no dedicated "fault.resolved" event type exists in the current event bus.
    # Using INFO as a proxy. Document in SUMMARY.md.
    try:
        bus.subscribe(
            pattern="*",
            handler=_on_fault_resolved,
            min_importance=Importance.INFO,
            filter=lambda e: e.importance == Importance.INFO,
        )
        logger.info("Decision moment subscribers registered (CRITICAL pre-warm + INFO fault resolution proxy)")
    except Exception as e:
        logger.warning("Could not register fault resolution subscriber: %s — cache TTL only", e)
