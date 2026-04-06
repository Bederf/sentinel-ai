"""Fire & life safety system service.

Provides fire alarm panel monitoring, zone-level alarm tracking,
smoke damper status, stairwell pressurization, and system health.
Uses FireSafetyRepository for all data operations (Supabase + JSON fallback).
Integrates with FireHVACCoordinator for cause-effect execution on alarms.
"""

import logging
from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from app.database.repositories.fire_safety_repository import get_fire_safety_repository
from app.models.fire_safety import (
    AlarmSeverity,
    AlarmType,
    CauseEffectEffect,
    CauseEffectEntry,
    DamperStatus,
    DamperStatusEnum,
    FanStatus,
    FireAlarm,
    FireSystemHealth,
    FireSystemStatus,
    FireZone,
    FireZoneType,
    HealthStatus,
    PanelStatus,
    StairwellPressure,
)

logger = logging.getLogger(__name__)

_instance: Optional["FireSystemService"] = None


class FireSystemService:
    """Service for fire & life safety system operations."""

    def __init__(self):
        self._repo = get_fire_safety_repository()

    def get_system_status(self) -> FireSystemStatus:
        """Get aggregate fire system status."""
        # Get panel info and local fallback state
        panel_info = self._repo.get_panel_info()
        local_state = self._repo.get_local_state()

        # Get active alarms
        active_alarms = self.get_active_alarms()

        # Get dampers
        dampers = self.get_damper_status()
        all_dampers_healthy = all(d.status != DamperStatusEnum.FAULT for d in dampers)

        # Get pressurization
        press_list = self.get_pressurization_status()
        pressurization_ok = all(p.fan_status != FanStatus.FAULT for p in press_list)

        # Determine panel status
        if any(a.severity == AlarmSeverity.FIRE for a in active_alarms):
            panel_status = PanelStatus.ALARM
        elif any(a.severity == AlarmSeverity.FAULT for a in active_alarms) or not all_dampers_healthy:
            panel_status = PanelStatus.FAULT
        else:
            panel_status = PanelStatus(local_state.get("panel_status", "normal"))

        # Zone count
        zones = self._repo.get_zones()
        zone_count = len(zones)

        # Battery voltage from local fallback state or panel info
        battery_voltage = local_state.get("battery_voltage", panel_info.get("battery_voltage", 27.6))

        return FireSystemStatus(
            panel_status=panel_status,
            active_alarms=active_alarms,
            zone_count=zone_count,
            damper_count=len(dampers),
            all_dampers_healthy=all_dampers_healthy,
            pressurization_ok=pressurization_ok,
            battery_voltage=battery_voltage,
            last_test_date=panel_info.get("last_test_date"),
        )

    def get_active_alarms(self) -> list[FireAlarm]:
        """Get all active (uncleared) fire alarms."""
        raw_alarms = self._repo.get_active_alarms()
        alarms = []
        for a in raw_alarms:
            try:
                alarms.append(
                    FireAlarm(
                        alarm_id=a.get("alarm_id", ""),
                        zone_id=a.get("zone_id", ""),
                        alarm_type=AlarmType(a.get("alarm_type", "fault")),
                        severity=AlarmSeverity(a.get("severity", "fault")),
                        description=a.get("description", ""),
                        acknowledged=a.get("acknowledged", False),
                        acknowledged_by=a.get("acknowledged_by"),
                        cleared=a.get("cleared", False),
                        created_at=a.get("created_at", datetime.utcnow()),
                    )
                )
            except Exception as e:
                logger.warning(f"Error parsing alarm: {e}")
        return alarms

    def get_zone_status(self, zone_id: str) -> dict | None:
        """Get details for a specific fire zone including active alarms."""
        zone_data = self._repo.get_zone(zone_id)
        if not zone_data:
            return None

        # Get alarms for this zone
        all_alarms = self._repo.get_active_alarms()
        zone_alarms = [a for a in all_alarms if a.get("zone_id") == zone_id]

        return {
            "zone": zone_data,
            "active_alarms": zone_alarms,
            "alarm_count": len(zone_alarms),
            "has_active_alarm": len(zone_alarms) > 0,
        }

    def get_zones(self) -> list[FireZone]:
        """Get all fire zones."""
        raw_zones = self._repo.get_zones()
        zones = []
        for z in raw_zones:
            try:
                zones.append(
                    FireZone(
                        zone_id=z.get("zone_id", ""),
                        zone_name=z.get("zone_name", ""),
                        floor=z.get("floor", ""),
                        zone_type=FireZoneType(z.get("zone_type", "office")),
                        smoke_detectors=z.get("smoke_detectors", 0),
                        heat_detectors=z.get("heat_detectors", 0),
                        beam_detectors=z.get("beam_detectors", 0),
                        manual_call_points=z.get("manual_call_points", 0),
                    )
                )
            except Exception as e:
                logger.warning(f"Error parsing zone: {e}")
        return zones

    def get_damper_status(self) -> list[DamperStatus]:
        """Get all smoke damper positions and health."""
        raw_dampers = self._repo.get_dampers()
        dampers = []
        for d in raw_dampers:
            try:
                dampers.append(
                    DamperStatus(
                        damper_id=d.get("damper_id", ""),
                        equipment_id=d.get("equipment_id"),
                        zone_id=d.get("zone_id"),
                        floor=d.get("floor", ""),
                        position=d.get("position", 100),
                        target_position=d.get("target_position", 100),
                        status=DamperStatusEnum(d.get("status", "open")),
                        last_tested=d.get("last_tested"),
                    )
                )
            except Exception as e:
                logger.warning(f"Error parsing damper: {e}")
        return dampers

    def get_pressurization_status(self) -> list[StairwellPressure]:
        """Get stairwell pressurization fan status."""
        raw_press = self._repo.get_pressurization()
        pressurization = []
        for p in raw_press:
            try:
                pressurization.append(
                    StairwellPressure(
                        stairwell_id=p.get("stairwell_id", ""),
                        floor=p.get("floor", ""),
                        current_pressure_pa=float(p.get("current_pressure_pa", 0)),
                        target_pressure_pa=float(p.get("target_pressure_pa", 50)),
                        fan_status=FanStatus(p.get("fan_status", "off")),
                        fan_speed_pct=int(p.get("fan_speed_pct", 0)),
                    )
                )
            except Exception as e:
                logger.warning(f"Error parsing pressurization: {e}")
        return pressurization

    def get_cause_effect_matrix(self) -> list[CauseEffectEntry]:
        """Get the cause-effect matrix."""
        raw_matrix = self._repo.get_cause_effect_matrix()
        entries = []
        for m in raw_matrix:
            try:
                effects = []
                for e in m.get("effects", []):
                    effects.append(
                        CauseEffectEffect(
                            target_type=e.get("target_type", "hvac"),
                            target_id=e.get("target_id", ""),
                            action=e.get("action", ""),
                            delay_seconds=e.get("delay_seconds", 0),
                            priority=e.get("priority", 1),
                        )
                    )
                entries.append(
                    CauseEffectEntry(
                        trigger_zone=m.get("trigger_zone", ""),
                        trigger_type=m.get("trigger_type", ""),
                        effects=effects,
                    )
                )
            except Exception as e:
                logger.warning(f"Error parsing cause-effect entry: {e}")
        return entries

    def get_system_health(self) -> FireSystemHealth:
        """Get fire system health summary."""
        local_state = self._repo.get_local_state()
        battery_voltage = local_state.get("battery_voltage", 27.6)

        # Check battery status
        if battery_voltage < 23.0:
            battery_status = "critical"
        elif battery_voltage < 24.5:
            battery_status = "low"
        else:
            battery_status = "ok"

        # Check damper faults
        dampers = self.get_damper_status()
        damper_faults = sum(1 for d in dampers if d.status == DamperStatusEnum.FAULT)

        # Check detector faults from active alarms
        active_alarms = self.get_active_alarms()
        detector_faults = sum(1 for a in active_alarms if a.alarm_type == AlarmType.FAULT)

        # Panel comms - if we can read data, comms are OK
        panel_comms = "ok"

        # Overall health
        if damper_faults > 0 or detector_faults > 0 or battery_status == "critical":
            if damper_faults > 2 or battery_status == "critical":
                overall = HealthStatus.CRITICAL
            else:
                overall = HealthStatus.DEGRADED
        else:
            overall = HealthStatus.HEALTHY

        return FireSystemHealth(
            panel_comms=panel_comms,
            battery_status=battery_status,
            detector_faults=detector_faults,
            damper_faults=damper_faults,
            overall_health=overall,
        )

    async def trigger_alarm(self, zone_id: str, alarm_type: str) -> dict[str, Any]:
        """Trigger a fire alarm and execute cause-effect chain.

        Creates a FireAlarm entry via repository, then calls
        FireHVACCoordinator.execute_cause_effect() for the full
        HVAC/damper/pressurization response.

        Returns combined result (alarm + effects executed).
        """
        from app.services.fire_hvac_coordinator import get_fire_hvac_coordinator

        # Validate zone exists
        zone = self._repo.get_zone(zone_id)
        if not zone:
            return {"error": f"Zone {zone_id} not found"}

        # Create alarm via repository (dual-write)
        alarm_data = {
            "alarm_id": f"ALM-{uuid4().hex[:8].upper()}",
            "zone_id": zone_id,
            "alarm_type": alarm_type,
            "severity": "fire" if alarm_type in ("smoke", "heat", "manual") else "fault",
            "description": f"{alarm_type.upper()} alarm in {zone.get('zone_name', zone_id)}",
            "acknowledged": False,
            "cleared": False,
            "created_at": datetime.utcnow().isoformat(),
        }
        self._repo.create_alarm(alarm_data)

        # Execute cause-effect chain via coordinator
        coordinator = get_fire_hvac_coordinator()
        cause_effect_result = await coordinator.execute_cause_effect(zone_id, alarm_type)

        return {
            "alarm_id": alarm_data["alarm_id"],
            "alarm": alarm_data,
            "zone": zone,
            "cause_effect": cause_effect_result.to_dict(),
            "coordinator_mode": coordinator._mode,
        }

    async def clear_alarm(self, alarm_id: str) -> dict[str, Any]:
        """Clear a fire alarm and trigger reset if no more active alarms.

        Marks alarm as acknowledged/cleared via repository, then checks
        if any alarms remain. If none, calls coordinator.reset_fire_mode().
        """
        from app.services.fire_hvac_coordinator import get_fire_hvac_coordinator

        # Mark alarm as cleared via repository (dual-write)
        self._repo.update_alarm(
            alarm_id,
            {
                "acknowledged": True,
                "acknowledged_by": "operator",
                "acknowledged_at": datetime.utcnow().isoformat(),
                "cleared": True,
                "cleared_at": datetime.utcnow().isoformat(),
            },
        )

        # Log the clear action
        self._repo.log_action(
            {
                "action_type": "alarm_cleared",
                "zone_id": "unknown",
                "description": f"Alarm {alarm_id} cleared by operator",
                "mode": "normal",
            }
        )

        # Check remaining active alarms
        remaining = self._repo.get_active_alarms()
        remaining_active = [a for a in remaining if a.get("alarm_id") != alarm_id and not a.get("cleared", False)]

        result: dict[str, Any] = {
            "alarm_id": alarm_id,
            "cleared": True,
            "remaining_active_alarms": len(remaining_active),
        }

        # If no more active alarms, reset fire mode
        if len(remaining_active) == 0:
            coordinator = get_fire_hvac_coordinator()
            if coordinator._mode != "normal":
                reset_result = await coordinator.reset_fire_mode()
                result["reset"] = reset_result
                result["coordinator_mode"] = "normal"
            else:
                result["coordinator_mode"] = "normal"
                result["reset"] = None
        else:
            coordinator = get_fire_hvac_coordinator()
            result["coordinator_mode"] = coordinator._mode
            result["reset"] = None

        return result

    def simulate_alarm(self, zone_id: str, alarm_type: str = "smoke") -> dict:
        """Simulate a fire alarm for local testing (legacy sync method).

        Returns the alarm details and the cause-effect actions that would activate.
        For full coordination, use trigger_alarm() instead.
        """
        # Validate zone exists
        zone = self._repo.get_zone(zone_id)
        if not zone:
            return {"error": f"Zone {zone_id} not found"}

        # Create simulated alarm
        alarm_data = {
            "alarm_id": f"ALM-SIM-{uuid4().hex[:8]}",
            "zone_id": zone_id,
            "alarm_type": alarm_type,
            "severity": "fire" if alarm_type in ("smoke", "heat", "manual") else "fault",
            "description": f"SIMULATED {alarm_type.upper()} alarm in {zone.get('zone_name', zone_id)}",
            "acknowledged": False,
            "cleared": False,
            "created_at": datetime.utcnow().isoformat(),
        }

        # Find matching cause-effect entries
        matrix = self._repo.get_cause_effect_matrix()
        triggered_effects = []
        for entry in matrix:
            if entry.get("trigger_zone") == zone_id:
                severity = "fire" if alarm_type in ("smoke", "heat", "manual") else "fault"
                if entry.get("trigger_type") == severity or entry.get("trigger_type") == alarm_type:
                    for effect in entry.get("effects", []):
                        triggered_effects.append(effect)

        # Log the simulation action
        self._repo.log_action(
            {
                "action_type": "simulate_alarm",
                "zone_id": zone_id,
                "description": f"Simulated {alarm_type} alarm in {zone_id}",
                "mode": "local",
            }
        )

        # Save alarm to repository
        self._repo.create_alarm(alarm_data)

        return {
            "alarm": alarm_data,
            "zone": zone,
            "triggered_effects": triggered_effects,
            "effect_count": len(triggered_effects),
        }


def get_fire_system_service() -> FireSystemService:
    """Get or create singleton FireSystemService."""
    global _instance
    if _instance is None:
        _instance = FireSystemService()
    return _instance
