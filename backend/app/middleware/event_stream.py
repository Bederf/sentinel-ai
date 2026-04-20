"""
Server-Sent Events (SSE) event stream manager for Phase 170-03.

Manages per-correlation_id event channels for real-time decision verification updates.
"""

import asyncio
import logging

logger = logging.getLogger(__name__)


class EventStreamManager:
    """Manages SSE event channels per correlation_id."""

    def __init__(self):
        """Initialize channel registry."""
        self._channels: dict[str, asyncio.Queue] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, correlation_id: str) -> asyncio.Queue:
        """
        Subscribe to events for a correlation_id.

        Creates a queue if it doesn't exist, returns existing if it does.

        Args:
            correlation_id: UUID or string identifier

        Returns:
            asyncio.Queue for this correlation_id
        """
        async with self._lock:
            if correlation_id not in self._channels:
                self._channels[correlation_id] = asyncio.Queue()
            return self._channels[correlation_id]

    async def emit(
        self,
        event_type: str,
        correlation_id: str,
        payload: dict | None = None,
    ) -> None:
        """
        Emit an event to a correlation_id's subscribers.

        If no subscribers, event is dropped silently (frontend may have disconnected).

        Args:
            event_type: Event type (COMMAND_VERIFIED, COMMAND_TIMEOUT, etc.)
            correlation_id: Target correlation_id
            payload: Event payload (optional)

        Raises:
            None (all errors logged, not raised)
        """
        if payload is None:
            payload = {}

        event = {
            "event_type": event_type,
            "payload": payload,
        }

        async with self._lock:
            if correlation_id in self._channels:
                queue = self._channels[correlation_id]
                try:
                    queue.put_nowait(event)
                    logger.debug(
                        f"Emitted {event_type} to {correlation_id}",
                        extra={"correlation_id": correlation_id},
                    )
                except asyncio.QueueFull:
                    logger.warning(
                        f"Event queue full for {correlation_id}, dropping event",
                        extra={"correlation_id": correlation_id},
                    )
            else:
                logger.debug(
                    f"No subscribers for {correlation_id}, dropping {event_type}",
                    extra={"correlation_id": correlation_id},
                )

    async def unsubscribe(self, correlation_id: str) -> None:
        """
        Unsubscribe and clean up queue.

        Args:
            correlation_id: Target correlation_id
        """
        async with self._lock:
            if correlation_id in self._channels:
                del self._channels[correlation_id]
                logger.debug(f"Unsubscribed {correlation_id}")


# Global instance
event_stream = EventStreamManager()
