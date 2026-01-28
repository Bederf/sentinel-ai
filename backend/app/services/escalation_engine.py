"""Escalation Engine for managing multi-level escalation paths in autonomous system.

Handles escalation level evaluation, automatic escalation triggers, and escalation
history tracking for autonomous boundary management.
"""

import logging
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional, Callable
from enum import Enum

from app.models.autonomous_decision import (
    BoundaryStatus,
    EscalationLevel,
    EscalationEvent
)
from app.models.audit_log import AuditResultType
from app.services.notification_service import notification_service

logger = logging.getLogger(__name__)


class EscalationEngine:
    """Engine for managing multi-level escalation paths based on boundary approach."""

    def __init__(self):
        """Initialize the escalation engine."""
        self.escalation_history: List[EscalationEvent] = []
        self.active_escalations: Dict[str, EscalationEvent] = {}
        self._escalation_callbacks: List[Callable] = []
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the escalation engine."""
        if self._initialized:
            return

        logger.info("Initializing EscalationEngine")
        await notification_service.initialize()
        self._initialized = True
        logger.info("EscalationEngine initialized")

    async def evaluate_escalation(
        self,
        boundary_status: BoundaryStatus
    ) -> Optional[EscalationEvent]:
        """
        Evaluate boundary status and trigger appropriate escalation if needed.

        Args:
            boundary_status: Current boundary status to evaluate

        Returns:
            EscalationEvent if escalation triggered, None otherwise
        """
        # Create escalation key
        escalation_key = f"{boundary_status.device_id}:{boundary_status.point_name}"

        # Check if we're already at this escalation level
        if escalation_key in self.active_escalations:
            current_event = self.active_escalations[escalation_key]
            if current_event.escalation_level == boundary_status.escalation_level:
                # No change in escalation level
                return None

        # Only escalate if we have a real escalation level (not NONE)
        if boundary_status.escalation_level == EscalationLevel.NONE:
            # Clear any existing escalation for this key
            if escalation_key in self.active_escalations:
                await self._clear_escalation(escalation_key)
            return None

        # Create new escalation event
        event = EscalationEvent(
            id=f"esc_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{boundary_status.device_id}_{boundary_status.point_name}",
            timestamp=datetime.now(),
            device_id=boundary_status.device_id,
            device_name=self._get_device_name(boundary_status.device_id),
            point_name=boundary_status.point_name,
            current_value=boundary_status.current_value,
            boundary_min=boundary_status.boundary_min,
            boundary_max=boundary_status.boundary_max,
            approach_percentage=boundary_status.approach_percentage,
            escalation_level=boundary_status.escalation_level,
            acknowledged=False,
            acknowledged_by=None,
            acknowledged_at=None,
            auto_resolved=False,
            warnings=boundary_status.warnings.copy(),
            metadata={
                "boundary_status": boundary_status.to_dict()
            }
        )

        # Store escalation event
        self.active_escalations[escalation_key] = event
        self.escalation_history.append(event)

        # Trigger notifications based on escalation level
        await self._trigger_notifications(event)

        # Log escalation
        logger.warning(
            f"ESCALATION {event.escalation_level.name}: {event.device_name} {event.point_name} "
            f"at {event.approach_percentage:.1f}% of boundary"
        )

        # Notify callbacks
        await self._notify_escalation_callbacks(event)

        return event

    async def _trigger_notifications(self, event: EscalationEvent) -> None:
        """Trigger appropriate notifications based on escalation level."""
        try:
            if event.escalation_level == EscalationLevel.WARNING:
                # Level 1: Log only (no external notifications)
                logger.info(f"Level 1 escalation logged: {event.device_name}")

            elif event.escalation_level == EscalationLevel.ALERT:
                # Level 2: Email notification
                await notification_service.send_email_alert(event)
                logger.info(f"Level 2 email alert sent: {event.device_name}")

            elif event.escalation_level == EscalationLevel.CRITICAL:
                # Level 3: Slack + Dashboard notification
                await notification_service.send_slack_alert(event)
                await notification_service.send_dashboard_alert(event)
                logger.info(f"Level 3 critical alerts sent: {event.device_name}")

            elif event.escalation_level == EscalationLevel.EMERGENCY:
                # Level 4: Emergency notification + Auto-stop
                await notification_service.send_emergency_notification(event)
                await notification_service.send_dashboard_alert(event, urgent=True)

                # Trigger emergency handler
                from app.services.emergency_handler import emergency_handler
                await emergency_handler.handle_emergency(event)

                logger.error(f"Level 4 EMERGENCY: {event.device_name} - Auto-stop triggered")

        except Exception as e:
            logger.error(f"Error triggering notifications for escalation {event.id}: {e}")

    async def acknowledge_escalation(
        self,
        escalation_id: str,
        acknowledged_by: str,
        comment: Optional[str] = None
    ) -> bool:
        """
        Acknowledge an escalation event.

        Args:
            escalation_id: ID of the escalation to acknowledge
            acknowledged_by: User acknowledging the escalation
            comment: Optional comment

        Returns:
            True if successfully acknowledged
        """
        # Find escalation in active escalations
        for key, event in self.active_escalations.items():
            if event.id == escalation_id:
                event.acknowledged = True
                event.acknowledged_by = acknowledged_by
                event.acknowledged_at = datetime.now()
                if comment:
                    event.metadata["acknowledgment_comment"] = comment

                logger.info(f"Escalation {escalation_id} acknowledged by {acknowledged_by}")

                # Stop further escalation notifications
                await self._clear_escalation(key)

                return True

        return False

    async def _clear_escalation(self, escalation_key: str) -> None:
        """Clear an escalation from active escalations."""
        if escalation_key in self.active_escalations:
            del self.active_escalations[escalation_key]
            logger.info(f"Escalation cleared: {escalation_key}")

    async def get_escalation_history(
        self,
        limit: int = 100,
        escalation_level: Optional[EscalationLevel] = None,
        acknowledged: Optional[bool] = None
    ) -> List[EscalationEvent]:
        """
        Get escalation history with optional filtering.

        Args:
            limit: Maximum number of events to return
            escalation_level: Filter by escalation level
            acknowledged: Filter by acknowledgment status

        Returns:
            List of escalation events
        """
        filtered_events = self.escalation_history

        if escalation_level:
            filtered_events = [e for e in filtered_events if e.escalation_level == escalation_level]

        if acknowledged is not None:
            filtered_events = [e for e in filtered_events if e.acknowledged == acknowledged]

        return filtered_events[-limit:]

    async def get_active_escalations(self) -> List[EscalationEvent]:
        """Get currently active escalation events."""
        return list(self.active_escalations.values())

    async def get_escalation_status(self, device_id: str, point_name: str) -> Optional[EscalationEvent]:
        """
        Get escalation status for a specific device/point.

        Args:
            device_id: Device ID
            point_name: Point name

        Returns:
            EscalationEvent if active escalation exists, None otherwise
        """
        escalation_key = f"{device_id}:{point_name}"
        return self.active_escalations.get(escalation_key)

    def _get_device_name(self, device_id: str) -> str:
        """Get device name from device_id (fallback to device_id if not found)."""
        # Try to get actual device name from device manager
        try:
            from app.services.device_abstraction import device_manager
            # Note: This would need async context, so we'll use fallback for now
            return device_id  # Placeholder
        except:
            return device_id

    async def add_escalation_callback(self, callback: Callable[[EscalationEvent], None]) -> None:
        """Add a callback to be notified when escalations occur."""
        self._escalation_callbacks.append(callback)

    async def _notify_escalation_callbacks(self, event: EscalationEvent) -> None:
        """Notify all registered callbacks about a new escalation."""
        for callback in self._escalation_callbacks:
            try:
                await callback(event)
            except Exception as e:
                logger.error(f"Error in escalation callback: {e}")

    async def test_escalation(
        self,
        device_id: str = "test_device",
        point_name: str = "test_point",
        escalation_level: EscalationLevel = EscalationLevel.WARNING
    ) -> EscalationEvent:
        """
        Test escalation system by creating a test escalation.

        Args:
            device_id: Device ID for test (default: test_device)
            point_name: Point name for test (default: test_point)
            escalation_level: Escalation level to test (default: WARNING)

        Returns:
            Created escalation event
        """
        # Create test boundary status
        from app.models.autonomous_decision import BoundaryStatus

        test_boundary = BoundaryStatus(
            device_id=device_id,
            point_name=point_name,
            current_value=25.0,
            boundary_min=16.0,
            boundary_max=28.0,
            approach_percentage=85.0 if escalation_level == EscalationLevel.ALERT else 95.0,
            escalation_level=escalation_level,
            warnings=[f"Test {escalation_level.name} escalation"],
            last_updated=datetime.now()
        )

        return await self.evaluate_escalation(test_boundary)

    async def auto_resolve_escalations(self) -> int:
        """
        Automatically resolve escalations that are no longer valid.

        Returns:
            Number of escalations auto-resolved
        """
        resolved_count = 0

        for key, event in list(self.active_escalations.items()):
            # Check if escalation is still valid (simplified check)
            # In production, this would re-evaluate boundary status
            time_elapsed = (datetime.now() - event.timestamp).total_seconds() / 60  # minutes

            # Auto-resolve if older than 30 minutes
            if time_elapsed > 30:
                event.auto_resolved = True
                del self.active_escalations[key]
                resolved_count += 1

                logger.info(f"Auto-resolved escalation {event.id} (age: {time_elapsed:.1f} minutes)")

        return resolved_count


# Global instance
escalation_engine = EscalationEngine()
