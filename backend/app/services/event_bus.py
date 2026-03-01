"""
SENTINEL Event Bus — Lightweight async pub/sub with importance scoring.

Provides glob-pattern subscriptions, event chaining, 3 built-in middleware
(dedup, enrichment, escalation), and monitoring metrics. Zero external
dependencies — pure asyncio, runs on SBCs.

Phase 139-01: Core engine.
"""

import asyncio
import logging
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import IntEnum
from fnmatch import fnmatch
from typing import Any, Callable, Coroutine, Deque, Dict, List, Optional, Set

logger = logging.getLogger("sentinel.event_bus")

# Type alias for event handlers
EventHandler = Callable[["SentinelEvent"], Coroutine[Any, Any, None]]
EventMiddleware = Callable[["SentinelEvent"], Coroutine[Any, Any, Optional["SentinelEvent"]]]


# =============================================================================
# Importance Enum
# =============================================================================


class Importance(IntEnum):
    """Event importance levels for delivery routing and filtering."""

    INFO = 1
    LOW = 3
    MEDIUM = 5
    HIGH = 7
    CRITICAL = 9

    @classmethod
    def from_severity(cls, severity: str) -> "Importance":
        """Map severity string to Importance level.

        Args:
            severity: One of "critical", "high", "warning", "medium", "low", "info"

        Returns:
            Corresponding Importance level
        """
        mapping = {
            "critical": cls.CRITICAL,
            "high": cls.HIGH,
            "warning": cls.MEDIUM,
            "medium": cls.MEDIUM,
            "low": cls.LOW,
            "info": cls.INFO,
        }
        return mapping.get(severity.lower(), cls.INFO)

    @classmethod
    def from_priority(cls, priority: int) -> "Importance":
        """Map numeric priority (1=highest) to Importance level.

        Args:
            priority: Integer priority where 1 is most critical

        Returns:
            Corresponding Importance level
        """
        mapping = {
            1: cls.CRITICAL,
            2: cls.HIGH,
            3: cls.MEDIUM,
            4: cls.LOW,
        }
        return mapping.get(priority, cls.INFO)


# =============================================================================
# SentinelEvent Dataclass
# =============================================================================


@dataclass
class SentinelEvent:
    """Core event structure for the SENTINEL event bus.

    Uses domain.action naming convention (e.g. "sensor.anomaly_detected").
    Supports event chaining via correlation_id and caused_by fields.
    """

    event_type: str
    source: str
    payload: Dict[str, Any]
    importance: Importance = Importance.INFO
    site_id: Optional[str] = None
    equipment_id: Optional[str] = None
    building_name: Optional[str] = None
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: _utc_iso())
    correlation_id: Optional[str] = None
    caused_by: Optional[str] = None

    @property
    def domain(self) -> str:
        """Extract domain from event_type (e.g. 'sensor' from 'sensor.anomaly_detected')."""
        parts = self.event_type.split(".", 1)
        return parts[0] if parts else ""

    @property
    def action(self) -> str:
        """Extract action from event_type (e.g. 'anomaly_detected' from 'sensor.anomaly_detected')."""
        parts = self.event_type.split(".", 1)
        return parts[1] if len(parts) > 1 else ""

    def chain(self, event_type: str, source: str, **kwargs: Any) -> "SentinelEvent":
        """Create a follow-up event preserving the correlation chain.

        The new event's correlation_id is set to this event's event_id (or
        this event's correlation_id if already part of a chain). The caused_by
        field always points to this event.

        Args:
            event_type: New event type
            source: Source of the new event
            **kwargs: Additional fields to set on the new event

        Returns:
            New SentinelEvent linked to this event
        """
        return SentinelEvent(
            event_type=event_type,
            source=source,
            payload=kwargs.pop("payload", {}),
            importance=kwargs.pop("importance", self.importance),
            site_id=kwargs.pop("site_id", self.site_id),
            equipment_id=kwargs.pop("equipment_id", self.equipment_id),
            building_name=kwargs.pop("building_name", self.building_name),
            correlation_id=self.correlation_id or self.event_id,
            caused_by=self.event_id,
            **kwargs,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize event to dictionary with importance name and value."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "source": self.source,
            "payload": self.payload,
            "importance": {
                "name": self.importance.name,
                "value": self.importance.value,
            },
            "site_id": self.site_id,
            "equipment_id": self.equipment_id,
            "building_name": self.building_name,
            "timestamp": self.timestamp,
            "correlation_id": self.correlation_id,
            "caused_by": self.caused_by,
            "domain": self.domain,
            "action": self.action,
        }


def _utc_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


# =============================================================================
# Subscription Dataclass
# =============================================================================


@dataclass
class Subscription:
    """A registered event subscription with pattern matching and filters."""

    pattern: str
    handler: EventHandler
    sub_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    filter: Optional[Callable[[SentinelEvent], bool]] = None
    min_importance: Importance = Importance.INFO
    site_ids: Optional[Set[str]] = None
    domains: Optional[Set[str]] = None
    paused: bool = False

    def matches(self, event: SentinelEvent) -> bool:
        """Check if an event matches this subscription's criteria.

        Checks: paused state, glob pattern, importance threshold, site filter,
        domain filter, and custom filter function.

        Args:
            event: The event to check

        Returns:
            True if the event matches all subscription criteria
        """
        if self.paused:
            return False

        # Glob pattern match on event_type
        if not fnmatch(event.event_type, self.pattern):
            return False

        # Importance threshold
        if event.importance < self.min_importance:
            return False

        # Site filter
        if self.site_ids and event.site_id not in self.site_ids:
            return False

        # Domain filter
        if self.domains and event.domain not in self.domains:
            return False

        # Custom filter function
        if self.filter and not self.filter(event):
            return False

        return True


# =============================================================================
# Built-in Middleware
# =============================================================================


class DeduplicationMiddleware:
    """Suppress duplicate events within a time window.

    Deduplicates on event_type + equipment_id + site_id combination.
    Cleans up stale entries when cache exceeds 10000 entries.
    """

    def __init__(self, window_seconds: float = 60.0):
        self.window_seconds = window_seconds
        self._seen: Dict[str, float] = {}  # dedup_key -> last_seen_timestamp

    def _dedup_key(self, event: SentinelEvent) -> str:
        """Generate deduplication key from event fields."""
        return f"{event.event_type}:{event.equipment_id or ''}:{event.site_id or ''}"

    def _cleanup(self) -> None:
        """Remove stale entries when cache is too large."""
        if len(self._seen) > 10000:
            cutoff = time.monotonic() - self.window_seconds
            self._seen = {k: v for k, v in self._seen.items() if v > cutoff}

    async def __call__(self, event: SentinelEvent) -> Optional[SentinelEvent]:
        """Process event through deduplication.

        Returns None if duplicate, event otherwise.
        """
        self._cleanup()

        key = self._dedup_key(event)
        now = time.monotonic()

        last_seen = self._seen.get(key)
        if last_seen is not None and (now - last_seen) < self.window_seconds:
            logger.debug("Dedup suppressed event: %s (key=%s)", event.event_type, key)
            return None

        self._seen[key] = now
        return event


class EnrichmentMiddleware:
    """Enrich events with additional context (e.g. building name from site_id).

    Accepts a pluggable async lookup function. Default is no-op.
    """

    def __init__(self, site_lookup: Optional[Callable[[str], Coroutine[Any, Any, Optional[str]]]] = None):
        self._site_lookup = site_lookup

    async def __call__(self, event: SentinelEvent) -> Optional[SentinelEvent]:
        """Enrich event with building name if site_id is present and building_name is missing."""
        if self._site_lookup and event.site_id and not event.building_name:
            try:
                building_name = await self._site_lookup(event.site_id)
                if building_name:
                    event.building_name = building_name
            except Exception as e:
                logger.warning("Enrichment lookup failed for site %s: %s", event.site_id, e)
        return event


class ImportanceEscalationMiddleware:
    """Escalate importance when the same event type recurs frequently.

    3 occurrences within the window -> escalate to HIGH.
    5 occurrences within the window -> escalate to CRITICAL.
    Adds `escalated` and `escalation_reason` to event payload.
    """

    def __init__(self, window_seconds: float = 300.0):
        self.window_seconds = window_seconds
        self._counts: Dict[str, List[float]] = defaultdict(list)

    def _event_key(self, event: SentinelEvent) -> str:
        """Generate tracking key from event fields."""
        return f"{event.event_type}:{event.equipment_id or ''}:{event.site_id or ''}"

    def _cleanup_window(self, key: str) -> None:
        """Remove timestamps outside the window for a given key."""
        cutoff = time.monotonic() - self.window_seconds
        self._counts[key] = [t for t in self._counts[key] if t > cutoff]
        if not self._counts[key]:
            del self._counts[key]

    async def __call__(self, event: SentinelEvent) -> Optional[SentinelEvent]:
        """Check recurrence count and escalate importance if needed."""
        key = self._event_key(event)
        now = time.monotonic()

        self._cleanup_window(key)
        self._counts[key].append(now)

        count = len(self._counts[key])

        if count >= 5 and event.importance < Importance.CRITICAL:
            logger.info(
                "Escalating %s to CRITICAL (%d occurrences in %.0fs)",
                event.event_type,
                count,
                self.window_seconds,
            )
            event.importance = Importance.CRITICAL
            event.payload["escalated"] = True
            event.payload["escalation_reason"] = f"{count} occurrences in {self.window_seconds}s window"
        elif count >= 3 and event.importance < Importance.HIGH:
            logger.info(
                "Escalating %s to HIGH (%d occurrences in %.0fs)",
                event.event_type,
                count,
                self.window_seconds,
            )
            event.importance = Importance.HIGH
            event.payload["escalated"] = True
            event.payload["escalation_reason"] = f"{count} occurrences in {self.window_seconds}s window"

        return event


# =============================================================================
# EventBus Class
# =============================================================================


class EventBus:
    """Lightweight async pub/sub event bus with middleware pipeline.

    Features:
    - Glob-pattern subscriptions (fnmatch)
    - Importance-based filtering
    - Middleware pipeline (dedup, enrichment, escalation)
    - Event chaining via correlation IDs
    - Rolling history buffer for monitoring
    - Per-handler 30s timeout with error isolation
    """

    def __init__(self, history_size: int = 1000):
        self._subscriptions: Dict[str, Subscription] = {}
        self._middleware: List[EventMiddleware] = []
        self._history: Deque[SentinelEvent] = deque(maxlen=history_size)
        self._events_emitted: int = 0
        self._handlers_invoked: int = 0
        self._handler_errors: int = 0
        self._by_domain: Dict[str, int] = defaultdict(int)
        self._by_importance: Dict[str, int] = defaultdict(int)

    # -------------------------------------------------------------------------
    # Subscriptions
    # -------------------------------------------------------------------------

    def subscribe(
        self,
        pattern: str,
        handler: EventHandler,
        filter: Optional[Callable[[SentinelEvent], bool]] = None,
        min_importance: Importance = Importance.INFO,
        site_ids: Optional[Set[str]] = None,
        domains: Optional[Set[str]] = None,
    ) -> str:
        """Register a new subscription.

        Args:
            pattern: Glob pattern for event_type matching (e.g. "sensor.*")
            handler: Async callable to invoke on match
            filter: Optional custom filter function
            min_importance: Minimum importance to trigger
            site_ids: Optional set of site IDs to filter on
            domains: Optional set of domains to filter on

        Returns:
            Subscription ID for management operations
        """
        sub = Subscription(
            pattern=pattern,
            handler=handler,
            filter=filter,
            min_importance=min_importance,
            site_ids=site_ids,
            domains=domains,
        )
        self._subscriptions[sub.sub_id] = sub
        logger.debug("Subscription added: id=%s pattern=%s", sub.sub_id, pattern)
        return sub.sub_id

    def on(self, pattern: str, **kwargs: Any) -> Callable:
        """Decorator form of subscribe.

        Usage:
            @bus.on("sensor.*")
            async def handle_sensor(event: SentinelEvent):
                ...
        """

        def decorator(handler: EventHandler) -> EventHandler:
            self.subscribe(pattern, handler, **kwargs)
            return handler

        return decorator

    def unsubscribe(self, sub_id: str) -> bool:
        """Remove a subscription by ID.

        Returns:
            True if removed, False if not found
        """
        removed = self._subscriptions.pop(sub_id, None)
        if removed:
            logger.debug("Subscription removed: id=%s", sub_id)
        return removed is not None

    def pause(self, sub_id: str) -> bool:
        """Pause a subscription (stops matching, keeps registration).

        Returns:
            True if paused, False if not found
        """
        sub = self._subscriptions.get(sub_id)
        if sub:
            sub.paused = True
            return True
        return False

    def resume(self, sub_id: str) -> bool:
        """Resume a paused subscription.

        Returns:
            True if resumed, False if not found
        """
        sub = self._subscriptions.get(sub_id)
        if sub:
            sub.paused = False
            return True
        return False

    # -------------------------------------------------------------------------
    # Middleware
    # -------------------------------------------------------------------------

    def use(self, middleware: EventMiddleware) -> None:
        """Add a processing middleware to the pipeline.

        Middleware are executed in order. If any middleware returns None,
        the event is suppressed (not delivered to subscribers).

        Args:
            middleware: Async callable that takes SentinelEvent and returns
                        SentinelEvent (possibly modified) or None to suppress
        """
        self._middleware.append(middleware)

    # -------------------------------------------------------------------------
    # Emit
    # -------------------------------------------------------------------------

    async def emit(self, event: SentinelEvent) -> None:
        """Emit an event through the middleware pipeline and deliver to matching subscribers.

        Middleware are run sequentially (order matters). If any middleware
        returns None, the event is suppressed. Matching subscriber handlers
        run concurrently with error isolation (asyncio.gather) and a 30s
        timeout per handler.

        Args:
            event: The event to emit
        """
        # Run middleware pipeline
        processed: Optional[SentinelEvent] = event
        for mw in self._middleware:
            if processed is None:
                logger.debug("Event %s suppressed by middleware", event.event_type)
                return
            try:
                processed = await mw(processed)
            except Exception as e:
                logger.error("Middleware error processing %s: %s", event.event_type, e)
                return

        if processed is None:
            logger.debug("Event %s suppressed by middleware", event.event_type)
            return

        # Update metrics
        self._events_emitted += 1
        self._by_domain[processed.domain] += 1
        self._by_importance[processed.importance.name] += 1

        # Add to history
        self._history.append(processed)

        # Find matching subscriptions
        matching_subs = [sub for sub in self._subscriptions.values() if sub.matches(processed)]

        if not matching_subs:
            logger.debug("No subscribers for event: %s", processed.event_type)
            return

        # Execute handlers concurrently with error isolation
        async def _safe_invoke(sub: Subscription, evt: SentinelEvent) -> None:
            try:
                await asyncio.wait_for(sub.handler(evt), timeout=30.0)
                self._handlers_invoked += 1
            except asyncio.TimeoutError:
                self._handler_errors += 1
                logger.error(
                    "Handler timeout (30s) for sub=%s event=%s",
                    sub.sub_id,
                    evt.event_type,
                )
            except Exception as e:
                self._handler_errors += 1
                logger.error(
                    "Handler error for sub=%s event=%s: %s",
                    sub.sub_id,
                    evt.event_type,
                    e,
                )

        await asyncio.gather(
            *[_safe_invoke(sub, processed) for sub in matching_subs],
            return_exceptions=True,
        )

    # -------------------------------------------------------------------------
    # History / Query
    # -------------------------------------------------------------------------

    def get_history(
        self,
        event_type: Optional[str] = None,
        domain: Optional[str] = None,
        site_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        min_importance: Optional[Importance] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Query rolling history buffer with optional filters.

        Args:
            event_type: Filter by exact event type
            domain: Filter by domain
            site_id: Filter by site ID
            correlation_id: Filter by correlation ID
            min_importance: Filter by minimum importance
            limit: Maximum results to return

        Returns:
            List of event dicts, most recent first
        """
        results: List[Dict[str, Any]] = []

        for event in reversed(self._history):
            if event_type and event.event_type != event_type:
                continue
            if domain and event.domain != domain:
                continue
            if site_id and event.site_id != site_id:
                continue
            if correlation_id and event.correlation_id != correlation_id:
                continue
            if min_importance and event.importance < min_importance:
                continue

            results.append(event.to_dict())
            if len(results) >= limit:
                break

        return results

    def get_event_chain(self, correlation_id: str) -> List[Dict[str, Any]]:
        """Get all events in a correlation chain, ordered by timestamp.

        Args:
            correlation_id: The correlation ID linking the chain

        Returns:
            List of event dicts in timestamp order
        """
        chain = []
        for event in self._history:
            if event.correlation_id == correlation_id or event.event_id == correlation_id:
                chain.append(event.to_dict())
        return chain

    def get_subscriptions(self) -> List[Dict[str, Any]]:
        """List all registered subscriptions for debugging.

        Returns:
            List of subscription info dicts
        """
        return [
            {
                "sub_id": sub.sub_id,
                "pattern": sub.pattern,
                "paused": sub.paused,
                "min_importance": sub.min_importance.name,
                "site_ids": list(sub.site_ids) if sub.site_ids else None,
                "domains": list(sub.domains) if sub.domains else None,
                "has_filter": sub.filter is not None,
            }
            for sub in self._subscriptions.values()
        ]

    # -------------------------------------------------------------------------
    # Metrics
    # -------------------------------------------------------------------------

    @property
    def metrics(self) -> Dict[str, Any]:
        """Return event bus metrics for monitoring.

        Returns:
            Dict with events_emitted, handlers_invoked, handler_errors,
            by_domain, by_importance, subscription_count, history_size
        """
        return {
            "events_emitted": self._events_emitted,
            "handlers_invoked": self._handlers_invoked,
            "handler_errors": self._handler_errors,
            "by_domain": dict(self._by_domain),
            "by_importance": dict(self._by_importance),
            "subscription_count": len(self._subscriptions),
            "history_size": len(self._history),
        }


# =============================================================================
# Singleton
# =============================================================================

_bus: Optional[EventBus] = None


def get_event_bus(history_size: int = 1000) -> EventBus:
    """Get or create the module-level EventBus singleton.

    Creates the bus with dedup and escalation middleware installed by default.

    Args:
        history_size: Maximum events in rolling history buffer

    Returns:
        The EventBus singleton
    """
    global _bus
    if _bus is None:
        _bus = EventBus(history_size=history_size)
        _bus.use(DeduplicationMiddleware())
        _bus.use(ImportanceEscalationMiddleware())
        logger.info("Event bus created (history_size=%d, middleware=dedup+escalation)", history_size)
    return _bus


def reset_event_bus() -> None:
    """Reset the singleton for testing. Clears all state."""
    global _bus
    _bus = None
    logger.debug("Event bus reset")
