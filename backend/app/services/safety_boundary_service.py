"""Safety Boundary Service for monitoring and enforcing safety boundaries.

Provides real-time boundary monitoring, breach detection, and dynamic boundary
adjustment capabilities for the autonomous system.
"""

import logging
from datetime import datetime
from typing import Any

from app.models.autonomous_decision import BoundaryStatus, EscalationLevel
from app.models.device import Device
from app.models.safety_rules import RuleType
from app.services.safety_interlocks import safety_engine

logger = logging.getLogger(__name__)


class SafetyBoundaryService:
    """Service for monitoring safety boundaries and detecting approaches/breaches."""

    def __init__(self):
        """Initialize the safety boundary service."""
        self._initialized = False

    async def initialize(self):
        """Initialize the safety boundary service."""
        if not self._initialized:
            self._initialized = True
            logger.info("Safety boundary service initialized")

    async def check_boundary_approach(
        self, device: Device, point_name: str, current_value: float, proposed_value: float | None = None
    ) -> BoundaryStatus:
        """
        Check how close a value is to safety boundaries.

        Args:
            device: Device being monitored
            point_name: Name of the point
            current_value: Current value of the point
            proposed_value: Optional proposed new value to check

        Returns:
            BoundaryStatus with approach information
        """
        # Get applicable safety rules
        rules = await safety_engine.get_rules_for_device(device, point_name)

        boundary_min = None
        boundary_max = None
        approach_percentage = 0.0
        escalation_level = EscalationLevel.NONE
        warnings = []

        # Only consider temperature and brightness rules for boundary monitoring
        for rule in rules:
            if rule.rule_type == RuleType.TEMPERATURE_RANGE:
                min_temp = getattr(rule, "min_temp", None)
                max_temp = getattr(rule, "max_temp", None)

                if min_temp is not None:
                    boundary_min = min_temp
                if max_temp is not None:
                    boundary_max = max_temp

            elif rule.rule_type == RuleType.BRIGHTNESS_LIMIT:
                max_brightness = getattr(rule, "max_brightness", None)
                if max_brightness is not None:
                    boundary_max = max_brightness

        # Calculate boundary approach for current or proposed value
        check_value = proposed_value if proposed_value is not None else current_value

        if boundary_min is not None and boundary_max is not None:
            # Two-sided boundary (e.g., temperature range)
            boundary_range = boundary_max - boundary_min
            if boundary_range > 0:
                # Calculate distance to nearest boundary
                distance_to_min = check_value - boundary_min
                distance_to_max = boundary_max - check_value

                # Closer to min boundary
                if distance_to_min < distance_to_max:
                    if check_value < boundary_min:
                        # Boundary breach!
                        approach_percentage = 100.0
                        escalation_level = EscalationLevel.EMERGENCY
                        warnings.append(f"CRITICAL: Value {check_value} below minimum boundary {boundary_min}")
                    else:
                        # Calculate approach percentage from min boundary (25% of range)
                        approach_distance = boundary_range * 0.25  # 25% buffer
                        if distance_to_min < approach_distance:
                            approach_percentage = (1 - (distance_to_min / approach_distance)) * 100
                            if approach_percentage >= 95:
                                escalation_level = EscalationLevel.EMERGENCY
                                warnings.append(
                                    f"EMERGENCY: Value {check_value} is "
                                    f"{approach_percentage:.1f}% of the way to minimum limit"
                                )
                            elif approach_percentage >= 85:
                                escalation_level = EscalationLevel.CRITICAL
                                warnings.append(
                                    f"CRITICAL: Value {check_value} approaching minimum limit {boundary_min}"
                                )
                            elif approach_percentage >= 75:
                                escalation_level = EscalationLevel.ALERT
                                warnings.append(f"ALERT: Value {check_value} within 25% of minimum limit")
                            elif approach_percentage >= 50:
                                escalation_level = EscalationLevel.WARNING
                                warnings.append(f"Warning: Value {check_value} approaching minimum boundary")

                # Closer to max boundary (or at max)
                else:
                    if check_value > boundary_max:
                        # Boundary breach!
                        approach_percentage = 100.0
                        escalation_level = EscalationLevel.EMERGENCY
                        warnings.append(f"CRITICAL: Value {check_value} exceeds maximum boundary {boundary_max}")
                    else:
                        # Calculate approach percentage from max boundary (25% of range)
                        approach_distance = boundary_range * 0.25
                        if distance_to_max < approach_distance:
                            approach_percentage = (1 - (distance_to_max / approach_distance)) * 100
                            if approach_percentage >= 95:
                                escalation_level = EscalationLevel.EMERGENCY
                                warnings.append(
                                    f"EMERGENCY: Value {check_value} is "
                                    f"{approach_percentage:.1f}% of the way to maximum limit"
                                )
                            elif approach_percentage >= 85:
                                escalation_level = EscalationLevel.CRITICAL
                                warnings.append(
                                    f"CRITICAL: Value {check_value} approaching maximum limit {boundary_max}"
                                )
                            elif approach_percentage >= 75:
                                escalation_level = EscalationLevel.ALERT
                                warnings.append(f"ALERT: Value {check_value} within 25% of maximum limit")
                            elif approach_percentage >= 50:
                                escalation_level = EscalationLevel.WARNING
                                warnings.append(f"Warning: Value {check_value} approaching maximum boundary")

        elif boundary_max is not None:
            # Upper boundary only (e.g., brightness limit)
            if check_value > boundary_max:
                # Boundary breach!
                approach_percentage = 100.0
                escalation_level = EscalationLevel.EMERGENCY
                warnings.append(f"CRITICAL: Value {check_value} exceeds maximum boundary {boundary_max}")
            else:
                # Calculate approach percentage (consider 90% as the warning threshold)
                if boundary_max > 0:
                    approach_percentage = (check_value / boundary_max) * 100
                    if approach_percentage >= 95:
                        escalation_level = EscalationLevel.EMERGENCY
                        warnings.append(
                            f"EMERGENCY: Value {check_value} at {approach_percentage:.1f}% of maximum limit"
                        )
                    elif approach_percentage >= 85:
                        escalation_level = EscalationLevel.CRITICAL
                        warnings.append(f"CRITICAL: Value {check_value} approaching maximum limit {boundary_max}")
                    elif approach_percentage >= 75:
                        escalation_level = EscalationLevel.ALERT
                        warnings.append(f"ALERT: Value {check_value} at {approach_percentage:.1f}% of limit")
                    elif approach_percentage >= 65:
                        escalation_level = EscalationLevel.WARNING
                        warnings.append(f"Warning: Value {check_value} at {approach_percentage:.1f}% of limit")

        return BoundaryStatus(
            device_id=device.id,
            point_name=point_name,
            current_value=current_value,
            boundary_min=boundary_min,
            boundary_max=boundary_max,
            approach_percentage=min(100.0, approach_percentage),
            escalation_level=escalation_level,
            warnings=warnings,
            last_updated=datetime.now(),
        )

    async def get_all_boundary_statuses(self, device: Device) -> list[BoundaryStatus]:
        """
        Get boundary status for all controllable points on a device.

        Args:
            device: Device to check

        Returns:
            List of BoundaryStatus for each point
        """
        from app.services.device_abstraction import device_manager

        statuses = []

        for point_name, point in device.points.items():
            if point.readable:
                try:
                    # Get current value
                    current_point = await device_manager.read_device_value(device.id, point_name)
                    current_value = current_point.value if current_point else point.default_value or 0

                    # Check boundary approach
                    status = await self.check_boundary_approach(device, point_name, current_value)
                    statuses.append(status)

                except Exception as e:
                    logger.error(f"Error checking boundary status for {device.id}.{point_name}: {e}")

        return statuses

    async def get_boundary_status_summary(self, device: Device) -> dict[str, Any]:
        """
        Get a summary of boundary status for all points on a device.

        Args:
            device: Device to check

        Returns:
            Summary with highest escalation level and overall status
        """
        statuses = await self.get_all_boundary_statuses(device)

        if not statuses:
            return {
                "device_id": device.id,
                "device_name": device.name,
                "overall_escalation": EscalationLevel.NONE,
                "max_approach_percentage": 0.0,
                "boundary_count": 0,
                "warning_count": 0,
                "critical_count": 0,
                "overall_status": "safe",
                "details": [],
            }

        # Find highest escalation level
        max_escalation = max(statuses, key=lambda s: s.escalation_level.value)
        max_approach = max(statuses, key=lambda s: s.approach_percentage)

        # Count warnings and critical status
        warning_count = len([s for s in statuses if s.escalation_level == EscalationLevel.WARNING])
        critical_count = len([s for s in statuses if s.escalation_level.value >= EscalationLevel.CRITICAL.value])

        # Determine overall status
        if max_escalation.escalation_level.value >= EscalationLevel.EMERGENCY.value:
            overall_status = "emergency"
        elif max_escalation.escalation_level.value >= EscalationLevel.CRITICAL.value:
            overall_status = "critical"
        elif max_escalation.escalation_level.value >= EscalationLevel.ALERT.value:
            overall_status = "alert"
        elif max_escalation.escalation_level.value >= EscalationLevel.WARNING.value:
            overall_status = "warning"
        else:
            overall_status = "safe"

        return {
            "device_id": device.id,
            "device_name": device.name,
            "overall_escalation": max_escalation.escalation_level,
            "max_approach_percentage": max_approach.approach_percentage,
            "boundary_count": len(statuses),
            "warning_count": warning_count,
            "critical_count": critical_count,
            "overall_status": overall_status,
            "details": [s.to_dict() for s in statuses],
        }

    async def update_boundary_config(self, device_id: str, point_name: str, new_boundaries: dict[str, float]) -> bool:
        """
        Update boundary configuration for a device/point.

        Args:
            device_id: Device ID
            point_name: Point name
            new_boundaries: Dict with 'min' and/or 'max' keys

        Returns:
            True if successful
        """
        # TODO: Implement dynamic boundary updates
        # This would modify the safety rules for the device
        logger.info(f"Boundary config update requested for {device_id}.{point_name}: {new_boundaries}")
        return True


# Global instance
safety_boundary_service = SafetyBoundaryService()
