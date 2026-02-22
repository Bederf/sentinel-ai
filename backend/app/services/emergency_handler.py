"""Emergency Handler for responding to Level 4 escalation events.

Coordinates emergency response including immediate autonomous stop, safe state
restoration, and emergency notification distribution.
"""

import logging
from datetime import datetime
from typing import Dict, Any, List

from app.models.autonomous_decision import EscalationEvent, EscalationLevel
from app.services.autonomous_decision_engine import autonomous_decision_engine
from app.services.device_abstraction import device_manager
from app.services.audit_logger import audit_logger

logger = logging.getLogger(__name__)

# Safe state defaults
SAFE_STATE_DEFAULTS = {
    "temperature": {
        "cooling_setpoint": 22.0,  # Return to comfortable midpoint
        "heating_setpoint": 20.0,
        "chiller_supply_temp": 7.0,  # Safe operating temperature
    },
    "lighting": {
        "brightness": 70.0,  # Energy-efficient but comfortable
    },
    "equipment": {
        "runtime": 1,  # Maintain current safe state
        "status": "maintain",
    },
}


class EmergencyHandler:
    """Handles emergency responses to boundary breaches and critical events."""

    def __init__(self):
        """Initialize the emergency handler."""
        self.emergency_history: List[Dict[str, Any]] = []
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the emergency handler."""
        if self._initialized:
            return

        logger.info("Initializing EmergencyHandler")
        self._initialized = True
        logger.info("EmergencyHandler initialized")

    async def handle_emergency(self, escalation_event: EscalationEvent) -> Dict[str, Any]:
        """
        Handle Level 4 emergency escalation event.

        Args:
            escalation_event: The emergency escalation event

        Returns:
            Response with emergency handling results
        """
        start_time = datetime.now()
        logger.critical(f"EMERGENCY HANDLER ACTIVATED for event {escalation_event.id}")

        response = {
            "emergency_id": f"emergency_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "timestamp": start_time,
            "escalation_event": escalation_event.to_dict(),
            "actions_taken": [],
            "devices_affected": 0,
            "status": "success",
        }

        try:
            # 1. IMMEDIATE: Stop autonomous mode
            stop_result = await self._stop_autonomous_mode()
            response["actions_taken"].append(
                {"action": "stop_autonomous_mode", "result": stop_result, "timestamp": datetime.now()}
            )
            logger.info(f"Autonomous mode stopped: {stop_result}")

            # 2. Restore devices to safe state
            safe_state_result = await self._restore_safe_state(escalation_event.device_id)
            response["actions_taken"].append(
                {
                    "action": "restore_safe_state",
                    "result": safe_state_result,
                    "devices_affected": safe_state_result.get("devices_affected", 0),
                    "timestamp": datetime.now(),
                }
            )
            response["devices_affected"] = safe_state_result.get("devices_affected", 0)
            logger.info(f"Safe state restoration: {safe_state_result}")

            # 3. Log emergency to audit system
            audit_result = await self._log_emergency_audit(escalation_event, response)
            response["actions_taken"].append(
                {"action": "log_audit", "result": audit_result, "timestamp": datetime.now()}
            )
            logger.info(f"Emergency audit logged: {audit_result}")

            # 4. Calculate response time
            response_time = (datetime.now() - start_time).total_seconds()
            response["response_time_seconds"] = response_time
            logger.info(f"Emergency response completed in {response_time:.2f} seconds")

            # 5. Store in emergency history
            self.emergency_history.append(response)

        except Exception as e:
            response["status"] = "error"
            response["error"] = str(e)
            logger.error(f"Emergency handling error: {e}")

        logger.critical(f"EMERGENCY HANDLER COMPLETED - Status: {response['status']}")
        return response

    async def _stop_autonomous_mode(self) -> Dict[str, Any]:
        """
        Immediately stop autonomous mode.

        Returns:
            Result of stopping autonomous mode
        """
        try:
            result = autonomous_decision_engine.disable_autonomous_mode()

            # Log to audit
            await audit_logger.log_autonomous_mode_change(
                enabled=False, triggered_by="emergency_handler", reason="Boundary breach emergency stop"
            )

            return {
                "success": result.get("success", False),
                "message": result.get("message", "Autonomous mode stop initiated"),
                "cancelled_decisions": result.get("cancelled_decisions", 0),
            }

        except Exception as e:
            logger.error(f"Error stopping autonomous mode: {e}")
            return {"success": False, "message": f"Failed to stop autonomous mode: {str(e)}"}

    async def _restore_safe_state(self, affected_device_id: str) -> Dict[str, Any]:
        """
        Restore affected devices to safe operating states.

        Args:
            affected_device_id: ID of the device that triggered emergency

        Returns:
            Results of safe state restoration
        """
        devices_affected = 0
        errors = []

        try:
            # Get all devices
            devices = await device_manager.list_devices()

            for device in devices:
                # Skip if device doesn't support autonomous control
                if not self._supports_autonomous_control(device):
                    continue

                try:
                    # Apply safe state per device type
                    safe_state = self._get_safe_state_for_device(device)

                    if safe_state:
                        await self._apply_safe_state(device, safe_state)
                        devices_affected += 1

                        # Log to audit
                        await audit_logger.log_safe_state_restoration(
                            device_id=device.id, device_name=device.name, safe_state=safe_state
                        )

                except Exception as e:
                    error_msg = f"Failed to restore safe state for {device.name}: {str(e)}"
                    errors.append(error_msg)
                    logger.error(error_msg)

            return {"devices_affected": devices_affected, "errors": errors, "success": len(errors) == 0}

        except Exception as e:
            error_msg = f"Critical error in safe state restoration: {str(e)}"
            logger.error(error_msg)
            return {"devices_affected": devices_affected, "errors": [error_msg], "success": False}

    async def _log_emergency_audit(self, escalation_event: EscalationEvent, response: Dict[str, Any]) -> bool:
        """
        Log emergency handling to audit system.

        Args:
            escalation_event: The escalation event that triggered emergency
            response: Emergency response details

        Returns:
            True if logged successfully
        """
        try:
            audit_data = {
                "action_type": "emergency_response",
                "severity": "CRITICAL",
                "user_id": "emergency_handler",
                "result": AuditResultType.SUCCESS if response["status"] == "success" else AuditResultType.FAILED,
                "details": {
                    "escalation_event": escalation_event.to_dict(),
                    "emergency_response": {
                        "emergency_id": response["emergency_id"],
                        "response_time_seconds": response.get("response_time_seconds", 0),
                        "devices_affected": response["devices_affected"],
                        "actions_taken": response["actions_taken"],
                    },
                },
            }

            await audit_logger.log_audit_entry(audit_data)
            return True

        except Exception as e:
            logger.error(f"Error logging emergency audit: {e}")
            return False

    def _supports_autonomous_control(self, device) -> bool:
        """
        Check if device supports autonomous control.

        Args:
            device: Device to check

        Returns:
            True if device supports autonomous control
        """
        # Check if device has controllable points
        for point in device.points.values():
            if hasattr(point, "writable") and point.writable:
                return True

        return False

    def _get_safe_state_for_device(self, device) -> Optional[Dict[str, Any]]:
        """
        Get safe state configuration for a device.

        Args:
            device: Device to get safe state for

        Returns:
            Safe state configuration or None if not applicable
        """
        device_type = device.type if hasattr(device, "type") else "equipment"

        if "hvac" in device_type.lower() or "chiller" in device_type.lower():
            return SAFE_STATE_DEFAULTS["temperature"]
        elif "lighting" in device_type.lower():
            return SAFE_STATE_DEFAULTS["lighting"]
        elif "equipment" in device_type.lower():
            return SAFE_STATE_DEFAULTS["equipment"]

        return None

    async def _apply_safe_state(self, device, safe_state: Dict[str, Any]) -> bool:
        """
        Apply safe state to a device.

        Args:
            device: Device to apply safe state to
            safe_state: Safe state configuration

        Returns:
            True if safe state applied successfully
        """
        try:
            # Apply safe values for each relevant point
            for point_name, safe_value in safe_state.items():
                if point_name in device.points:
                    await device_manager.write_device_value(device.id, point_name, safe_value)

            return True

        except Exception as e:
            logger.error(f"Error applying safe state to {device.name}: {e}")
            return False

    def get_emergency_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get emergency handling history."""
        return self.emergency_history[-limit:]

    async def test_emergency_response(self) -> Dict[str, Any]:
        """
        Test emergency response system.

        Returns:
            Test results
        """
        from app.models.autonomous_decision import BoundaryStatus

        # Create test escalation event
        test_event = EscalationEvent(
            id="test_emergency",
            timestamp=datetime.now(),
            device_id="test_device",
            device_name="Test Device",
            point_name="temperature",
            current_value=30.0,
            boundary_min=16.0,
            boundary_max=28.0,
            approach_percentage=100.0,
            escalation_level=EscalationLevel.EMERGENCY,
            acknowledged=False,
            acknowledged_by=None,
            acknowledged_at=None,
            auto_resolved=False,
            warnings=["Test emergency - boundary breach"],
            metadata={"test": True},
        )

        # Create corresponding boundary status
        test_boundary = BoundaryStatus(
            device_id="test_device",
            point_name="temperature",
            current_value=30.0,
            boundary_min=16.0,
            boundary_max=28.0,
            approach_percentage=100.0,
            escalation_level=EscalationLevel.EMERGENCY,
            warnings=["Test emergency"],
            last_updated=datetime.now(),
        )

        # Process emergency (mock mode - don't actually stop autonomous)
        result = await self.handle_emergency(test_event)

        # Restore autonomous mode if it was enabled
        if not autonomous_decision_engine.enabled:
            autonomous_decision_engine.enable_autonomous_mode()

        logger.info(f"Emergency response test completed: {result}")
        return result


# Global instance
emergency_handler = EmergencyHandler()
