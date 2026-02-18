"""Server-Sent Events (SSE) emitter for real-time dashboard updates.

Manages broadcasting of equipment alerts, health changes, and work order updates
to all connected dashboard clients via SSE.
"""

import asyncio
import json
import logging
from typing import Dict, List, Any
from dataclasses import dataclass
from enum import Enum
from datetime import datetime

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """Types of events that can be emitted."""
    ALERT_CREATED = "alert_created"
    HEALTH_CHANGED = "health_changed"
    WORK_ORDER_UPDATED = "work_order_updated"
    INSPECTION_COMPLETED = "inspection_completed"
    PREDICTION_GENERATED = "prediction_generated"


@dataclass
class Event:
    """SSE event with type and data."""
    event_type: EventType
    data: Dict[str, Any]
    timestamp: str = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow().isoformat()

    def to_sse(self) -> str:
        """Convert to SSE format for streaming."""
        event_dict = {
            "type": self.event_type.value,
            "data": self.data,
            "timestamp": self.timestamp
        }
        # SSE format: "data: {json}\n\n"
        return f"data: {json.dumps(event_dict)}\n\n"


class EventEmitter:
    """Singleton event emitter for broadcasting SSE events to connected clients."""

    _instance: "EventEmitter" = None
    _lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    async def __aenter__(self):
        """Context manager support."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager support."""
        pass

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        # List of async queues, one per connected client
        self._clients: List[asyncio.Queue] = []
        logger.info("EventEmitter initialized")

    async def register_client(self) -> asyncio.Queue:
        """Register a new SSE client connection.

        Returns:
            asyncio.Queue: Queue to which events will be sent for this client
        """
        async with self._lock:
            client_queue = asyncio.Queue()
            self._clients.append(client_queue)
            logger.info(f"Client registered. Total clients: {len(self._clients)}")
            return client_queue

    async def unregister_client(self, client_queue: asyncio.Queue) -> None:
        """Unregister a client when connection closes.

        Args:
            client_queue: The queue for the client being disconnected
        """
        async with self._lock:
            if client_queue in self._clients:
                self._clients.remove(client_queue)
                logger.info(f"Client unregistered. Total clients: {len(self._clients)}")

    async def emit(self, event: Event) -> None:
        """Broadcast an event to all connected clients.

        Args:
            event: Event to broadcast
        """
        if not self._clients:
            logger.debug(f"Event emitted with no connected clients: {event.event_type}")
            return

        logger.info(f"Emitting {event.event_type.value} to {len(self._clients)} clients")

        # Send to all clients concurrently
        tasks = []
        for client_queue in self._clients:
            tasks.append(self._send_to_client(client_queue, event))

        # Use gather with return_exceptions to handle errors gracefully
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _send_to_client(self, client_queue: asyncio.Queue, event: Event) -> None:
        """Send event to a single client queue.

        Args:
            client_queue: Client's event queue
            event: Event to send
        """
        try:
            # Use put_nowait to avoid blocking if queue is full
            client_queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning("Event queue full for client, dropping event")

    async def emit_alert_created(
        self,
        alert_id: str,
        equipment_id: str,
        equipment_code: str,
        equipment_name: str,
        severity: str,
        health_score: int,
        message: str,
        **kwargs
    ) -> None:
        """Emit alert creation event.

        Args:
            alert_id: Alert ID
            equipment_id: Equipment UUID
            equipment_code: Equipment code (e.g., S002-CHILLER-B1-001)
            equipment_name: Equipment name
            severity: Alert severity (critical, warning, info)
            health_score: Current equipment health score
            message: Alert message
            **kwargs: Additional event data
        """
        event = Event(
            event_type=EventType.ALERT_CREATED,
            data={
                "alert_id": alert_id,
                "equipment_id": equipment_id,
                "equipment_code": equipment_code,
                "equipment_name": equipment_name,
                "severity": severity,
                "health_score": health_score,
                "message": message,
                **kwargs
            }
        )
        await self.emit(event)

    async def emit_health_changed(
        self,
        equipment_id: str,
        equipment_code: str,
        equipment_name: str,
        old_health_score: int,
        new_health_score: int,
        reason: str = None,
        **kwargs
    ) -> None:
        """Emit health score change event.

        Args:
            equipment_id: Equipment UUID
            equipment_code: Equipment code
            equipment_name: Equipment name
            old_health_score: Previous health score
            new_health_score: New health score
            reason: Reason for change (e.g., 'service_feedback', 'alert')
            **kwargs: Additional event data
        """
        event = Event(
            event_type=EventType.HEALTH_CHANGED,
            data={
                "equipment_id": equipment_id,
                "equipment_code": equipment_code,
                "equipment_name": equipment_name,
                "old_health_score": old_health_score,
                "new_health_score": new_health_score,
                "reason": reason or "unknown",
                **kwargs
            }
        )
        await self.emit(event)

    async def emit_work_order_updated(
        self,
        work_order_id: str,
        equipment_id: str,
        equipment_code: str,
        status: str,
        work_order_type: str = None,
        **kwargs
    ) -> None:
        """Emit work order update event.

        Args:
            work_order_id: Work order ID
            equipment_id: Equipment UUID
            equipment_code: Equipment code
            status: New work order status
            work_order_type: Type of work order (inspection, maintenance, etc.)
            **kwargs: Additional event data
        """
        event = Event(
            event_type=EventType.WORK_ORDER_UPDATED,
            data={
                "work_order_id": work_order_id,
                "equipment_id": equipment_id,
                "equipment_code": equipment_code,
                "status": status,
                "work_order_type": work_order_type,
                **kwargs
            }
        )
        await self.emit(event)

    async def emit_inspection_completed(
        self,
        work_order_id: str,
        equipment_id: str,
        equipment_code: str,
        findings: str,
        recommendation: str = None,
        **kwargs
    ) -> None:
        """Emit inspection completion event.

        Args:
            work_order_id: Inspection work order ID
            equipment_id: Equipment UUID
            equipment_code: Equipment code
            findings: Technician findings text
            recommendation: Recommended next action (e.g., 'repair', 'monitor')
            **kwargs: Additional event data
        """
        event = Event(
            event_type=EventType.INSPECTION_COMPLETED,
            data={
                "work_order_id": work_order_id,
                "equipment_id": equipment_id,
                "equipment_code": equipment_code,
                "findings": findings,
                "recommendation": recommendation,
                **kwargs
            }
        )
        await self.emit(event)


# Singleton accessor
def get_event_emitter() -> EventEmitter:
    """Get or create the singleton EventEmitter instance.

    Returns:
        EventEmitter: The singleton event emitter
    """
    return EventEmitter()
