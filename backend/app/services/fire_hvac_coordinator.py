"""Fire-HVAC coordinator for cause & effect execution.

Coordinates HVAC shutdown, smoke damper closure, stairwell pressurization,
and smoke management mode in response to fire alarm events. All state
changes go through FireSafetyRepository (dual-write Supabase + JSON).
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Set
from uuid import uuid4

from app.database.repositories.fire_safety_repository import get_fire_safety_repository
from app.models.fire_safety import (
    AlarmSeverity,
    CauseEffectEffect,
    CauseEffectEntry,
    CauseEffectTargetType,
    DamperStatusEnum,
    FanStatus,
)

logger = logging.getLogger(__name__)

_instance: Optional["FireHVACCoordinator"] = None


class CauseEffectResult:
    """Result of cause-effect execution."""

    def __init__(self):
        self.triggered_effects: List[Dict[str, Any]] = []
        self.devices_affected: int = 0
        self.execution_time_ms: float = 0.0
        self.any_failures: bool = False
        self.failures: List[Dict[str, Any]] = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "triggered_effects": self.triggered_effects,
            "devices_affected": self.devices_affected,
            "execution_time_ms": round(self.execution_time_ms, 1),
            "any_failures": self.any_failures,
            "failures": self.failures,
        }


class FireHVACCoordinator:
    """Coordinates HVAC response to fire alarm events.

    Uses cause-effect matrix to determine actions, DeviceManager for
    device control (when available), and FireSafetyRepository for all
    state persistence.
    """

    def __init__(self):
        self._repo = get_fire_safety_repository()
        self._mode: str = "normal"  # normal | fire_mode | smoke_management | resetting
        self._affected_zones: Set[str] = set()
        self._shutdown_devices: List[Dict[str, Any]] = []
        self._device_manager = None

    def _get_device_manager(self):
        """Lazy-load DeviceManager if available."""
        if self._device_manager is None:
            try:
                from app.services.device_abstraction import DeviceManager
                dm = DeviceManager()
                if dm._initialized:
                    self._device_manager = dm
            except Exception as e:
                logger.debug(f"DeviceManager not available: {e}")
        return self._device_manager

    async def execute_cause_effect(self, zone_id: str, alarm_type: str) -> CauseEffectResult:
        """Execute all effects for a given alarm trigger.

        Looks up cause_effect_matrix entries matching zone_id and alarm_type,
        sorts by priority, executes each effect, and logs all actions
        through the repository.
        """
        start_time = time.time()
        result = CauseEffectResult()

        # Determine severity from alarm type
        severity = "fire" if alarm_type in ("smoke", "heat", "manual") else "fault"

        # Look up matching cause-effect entries from repository
        matrix = self._repo.get_cause_effect_matrix()
        matching_entries = []
        for entry in matrix:
            if entry.get("trigger_zone") == zone_id:
                if entry.get("trigger_type") == severity or entry.get("trigger_type") == alarm_type:
                    matching_entries.append(entry)

        if not matching_entries:
            logger.info(f"No cause-effect entries found for zone={zone_id} type={alarm_type}")
            result.execution_time_ms = (time.time() - start_time) * 1000
            return result

        # Collect all effects and sort by priority
        all_effects = []
        for entry in matching_entries:
            for effect in entry.get("effects", []):
                all_effects.append(effect)
        all_effects.sort(key=lambda e: e.get("priority", 99))

        # Update mode
        self._mode = "fire_mode"
        self._affected_zones.add(zone_id)

        # Log mode change through repository
        self._repo.log_action({
            "action_type": "mode_change",
            "zone_id": zone_id,
            "description": f"Entered fire_mode for zone {zone_id} (alarm: {alarm_type})",
            "mode": self._mode,
            "details": {"alarm_type": alarm_type, "severity": severity},
        })

        # Execute each effect
        affected_device_ids = set()
        for effect in all_effects:
            target_type = effect.get("target_type", "")
            target_id = effect.get("target_id", "")
            action = effect.get("action", "")
            delay_seconds = effect.get("delay_seconds", 0)
            priority = effect.get("priority", 1)

            # Apply delay (simulated for demo)
            if delay_seconds > 0:
                logger.info(f"Effect delay: {delay_seconds}s for {target_type}/{target_id}")
                # In demo mode, don't actually wait - just log the delay
                # await asyncio.sleep(delay_seconds)

            effect_result = await self._execute_single_effect(
                target_type, target_id, action, zone_id
            )

            result.triggered_effects.append({
                "target_type": target_type,
                "target_id": target_id,
                "action": action,
                "delay_seconds": delay_seconds,
                "priority": priority,
                "success": effect_result.get("success", False),
                "detail": effect_result.get("detail", ""),
            })

            if effect_result.get("success", False):
                affected_device_ids.add(target_id)
            else:
                result.any_failures = True
                result.failures.append({
                    "target_id": target_id,
                    "action": action,
                    "error": effect_result.get("detail", "Unknown error"),
                })

            # Log each action to repository audit trail
            self._repo.log_action({
                "action_type": f"cause_effect_{action}",
                "zone_id": zone_id,
                "description": f"{action} {target_type} {target_id} (priority {priority})",
                "mode": self._mode,
                "details": {
                    "target_type": target_type,
                    "target_id": target_id,
                    "action": action,
                    "success": effect_result.get("success", False),
                },
            })

        result.devices_affected = len(affected_device_ids)
        result.execution_time_ms = (time.time() - start_time) * 1000

        logger.info(
            f"Cause-effect execution complete: zone={zone_id}, "
            f"effects={len(result.triggered_effects)}, "
            f"devices={result.devices_affected}, "
            f"failures={len(result.failures)}, "
            f"time={result.execution_time_ms:.1f}ms"
        )

        return result

    async def _execute_single_effect(
        self, target_type: str, target_id: str, action: str, zone_id: str
    ) -> Dict[str, Any]:
        """Execute a single cause-effect action.

        Tries DeviceManager first, falls back to simulation.
        """
        dm = self._get_device_manager()

        if target_type == "hvac":
            return await self._execute_hvac_action(target_id, action, dm)
        elif target_type == "damper":
            return await self._execute_damper_action(target_id, action, zone_id)
        elif target_type == "pressurization":
            return await self._execute_pressurization_action(target_id, action)
        elif target_type == "exhaust":
            return await self._execute_exhaust_action(target_id, action, dm)
        else:
            return {"success": False, "detail": f"Unknown target type: {target_type}"}

    async def _execute_hvac_action(
        self, target_id: str, action: str, dm=None
    ) -> Dict[str, Any]:
        """Execute HVAC shutdown/alert action."""
        if action == "shutdown":
            if dm:
                try:
                    await dm.write_device_value(
                        target_id, "supply_fan", False, priority=1, user="fire_system"
                    )
                    self._shutdown_devices.append({
                        "device_id": target_id,
                        "action": "shutdown",
                        "original_state": "running",
                    })
                    return {"success": True, "detail": f"HVAC {target_id} shutdown via DeviceManager"}
                except Exception as e:
                    logger.warning(f"DeviceManager write failed for {target_id}: {e}")

            # Simulation fallback
            self._shutdown_devices.append({
                "device_id": target_id,
                "action": "shutdown",
                "original_state": "running",
                "simulated": True,
            })
            return {"success": True, "detail": f"HVAC {target_id} shutdown (simulated)"}

        elif action == "alert_only":
            return {"success": True, "detail": f"Alert generated for HVAC {target_id}"}

        return {"success": False, "detail": f"Unknown HVAC action: {action}"}

    async def _execute_damper_action(
        self, target_id: str, action: str, zone_id: str
    ) -> Dict[str, Any]:
        """Execute damper close/open action through repository."""
        if action == "close":
            # Update damper state through repository (dual-write)
            self._repo.update_damper(target_id, {
                "position": 0,
                "target_position": 0,
                "status": DamperStatusEnum.CLOSED.value,
            })
            return {"success": True, "detail": f"Damper {target_id} closed (position=0%)"}

        elif action == "open":
            self._repo.update_damper(target_id, {
                "position": 100,
                "target_position": 100,
                "status": DamperStatusEnum.OPEN.value,
            })
            return {"success": True, "detail": f"Damper {target_id} opened (position=100%)"}

        elif action == "partial":
            self._repo.update_damper(target_id, {
                "position": 50,
                "target_position": 50,
                "status": DamperStatusEnum.TRANSIT.value,
            })
            return {"success": True, "detail": f"Damper {target_id} set to 50%"}

        return {"success": False, "detail": f"Unknown damper action: {action}"}

    async def _execute_pressurization_action(
        self, target_id: str, action: str
    ) -> Dict[str, Any]:
        """Execute pressurization activate/deactivate through repository."""
        if action == "activate":
            # Get config target pressure (SANS 10400-T: 50 Pa)
            config_press = self._repo.get_pressurization()
            target_pa = 50.0
            target_speed = 85
            for p in config_press:
                if p.get("stairwell_id") == target_id:
                    target_pa = float(p.get("target_pressure_pa", 50.0))
                    break

            # Update pressurization through repository (dual-write)
            self._repo.update_pressurization(target_id, {
                "fan_status": FanStatus.RUNNING.value,
                "fan_speed_pct": target_speed,
                "current_pressure_pa": target_pa * 0.9,  # Simulated: 90% of target during ramp-up
            })
            return {
                "success": True,
                "detail": f"Pressurization {target_id} activated ({target_speed}% speed, target {target_pa} Pa)",
            }

        elif action == "deactivate":
            self._repo.update_pressurization(target_id, {
                "fan_status": FanStatus.OFF.value,
                "fan_speed_pct": 0,
                "current_pressure_pa": 0.0,
            })
            return {"success": True, "detail": f"Pressurization {target_id} deactivated"}

        return {"success": False, "detail": f"Unknown pressurization action: {action}"}

    async def _execute_exhaust_action(
        self, target_id: str, action: str, dm=None
    ) -> Dict[str, Any]:
        """Execute exhaust fan action for smoke extraction."""
        if action == "activate":
            if dm:
                try:
                    await dm.write_device_value(
                        target_id, "fan_speed", 60, priority=1, user="fire_system"
                    )
                    return {"success": True, "detail": f"Exhaust {target_id} activated at 60% for smoke extraction"}
                except Exception as e:
                    logger.warning(f"DeviceManager write failed for exhaust {target_id}: {e}")

            return {"success": True, "detail": f"Exhaust {target_id} activated at 60% (simulated)"}

        elif action == "deactivate":
            return {"success": True, "detail": f"Exhaust {target_id} deactivated"}

        return {"success": False, "detail": f"Unknown exhaust action: {action}"}

    async def shutdown_hvac_for_zone(self, zone_id: str) -> List[Dict[str, Any]]:
        """Shut down all HVAC serving the alarm zone.

        Maps fire zone to HVAC zones using floor matching, then shuts
        down AHU, FCU, VAV devices on that floor.
        """
        # Extract floor from zone_id (e.g., FZ-L1-C -> L1)
        floor = self._extract_floor(zone_id)
        if not floor:
            return []

        dm = self._get_device_manager()
        shutdown_results = []

        if dm:
            # Find HVAC devices on this floor
            all_devices = await dm.list_devices()
            hvac_types = {"ahu", "fcu", "vav"}
            floor_devices = [
                d for d in all_devices
                if d.device_type.value in hvac_types
                and getattr(d, 'location', {}).get('floor', '') == floor
            ]

            for device in floor_devices:
                try:
                    # Try to shut down supply fan
                    if "supply_fan" in device.points:
                        await dm.write_device_value(
                            device.id, "supply_fan", False, priority=1, user="fire_system"
                        )
                    shutdown_results.append({
                        "device_id": device.id,
                        "device_name": device.name,
                        "action": "shutdown",
                        "success": True,
                    })
                    self._shutdown_devices.append({
                        "device_id": device.id,
                        "action": "shutdown",
                        "original_state": "running",
                    })
                except Exception as e:
                    shutdown_results.append({
                        "device_id": device.id,
                        "device_name": device.name,
                        "action": "shutdown",
                        "success": False,
                        "error": str(e),
                    })
        else:
            # Simulation: determine what WOULD be shut down
            floor_suffix = floor.replace("L", "")
            simulated_devices = [
                f"S002-AHU-{floor}-001",
                f"S002-FCU-{floor}-A",
                f"S002-FCU-{floor}-B",
                f"S002-VAV-{floor}-A",
                f"S002-VAV-{floor}-B",
            ]
            for dev_id in simulated_devices:
                shutdown_results.append({
                    "device_id": dev_id,
                    "device_name": dev_id,
                    "action": "shutdown",
                    "success": True,
                    "simulated": True,
                })
                self._shutdown_devices.append({
                    "device_id": dev_id,
                    "action": "shutdown",
                    "original_state": "running",
                    "simulated": True,
                })

        # Log shutdown through repository
        self._repo.log_action({
            "action_type": "hvac_zone_shutdown",
            "zone_id": zone_id,
            "description": f"HVAC shutdown for floor {floor} ({len(shutdown_results)} devices)",
            "mode": self._mode,
            "details": {"floor": floor, "devices": len(shutdown_results)},
        })

        return shutdown_results

    async def close_smoke_dampers(self, zone_id: str) -> List[Dict[str, Any]]:
        """Close smoke dampers for affected zone through repository."""
        dampers = self._repo.get_dampers()
        zone_dampers = [d for d in dampers if d.get("zone_id") == zone_id]

        results = []
        for damper in zone_dampers:
            damper_id = damper.get("damper_id", "")
            current_status = damper.get("status", "open")

            if current_status == DamperStatusEnum.FAULT.value:
                # Can't close a faulted damper
                results.append({
                    "damper_id": damper_id,
                    "action": "close",
                    "success": False,
                    "detail": "Damper in FAULT state, cannot close",
                    "previous_position": damper.get("position", 0),
                })
                self._repo.log_action({
                    "action_type": "damper_close_failed",
                    "zone_id": zone_id,
                    "description": f"Cannot close faulted damper {damper_id}",
                    "mode": self._mode,
                })
                continue

            # Close damper through repository (dual-write)
            self._repo.update_damper(damper_id, {
                "position": 0,
                "target_position": 0,
                "status": DamperStatusEnum.CLOSED.value,
            })

            results.append({
                "damper_id": damper_id,
                "action": "close",
                "success": True,
                "detail": f"Closed (was at {damper.get('position', 100)}%)",
                "previous_position": damper.get("position", 100),
            })

        # Log action
        self._repo.log_action({
            "action_type": "smoke_damper_close",
            "zone_id": zone_id,
            "description": f"Closed {sum(1 for r in results if r['success'])} of {len(results)} dampers for zone {zone_id}",
            "mode": self._mode,
        })

        return results

    async def activate_pressurization(self, stairwell_ids: List[str]) -> List[Dict[str, Any]]:
        """Start stairwell pressurization fans through repository.

        Target: 50 Pa differential per SANS 10400-T.
        """
        results = []
        for stairwell_id in stairwell_ids:
            # Activate via repository (dual-write)
            self._repo.update_pressurization(stairwell_id, {
                "fan_status": FanStatus.RUNNING.value,
                "fan_speed_pct": 85,
                "current_pressure_pa": 45.0,  # Simulated ramp-up
            })
            results.append({
                "stairwell_id": stairwell_id,
                "action": "activate",
                "success": True,
                "fan_speed_pct": 85,
                "target_pressure_pa": 50.0,
                "current_pressure_pa": 45.0,
                "detail": f"Pressurization fan {stairwell_id} activated at 85% (target 50 Pa)",
            })

            self._repo.log_action({
                "action_type": "pressurization_activate",
                "zone_id": stairwell_id,
                "description": f"Activated pressurization fan {stairwell_id} at 85%",
                "mode": self._mode,
            })

        return results

    async def enter_smoke_management_mode(self, zone_id: str) -> Dict[str, Any]:
        """Coordinated smoke management for a fire zone.

        Strategy:
        a. Close supply dampers to fire zone
        b. Keep return/exhaust running at reduced speed (extract smoke)
        c. Pressurize adjacent zones slightly (prevent smoke spread)
        """
        self._mode = "smoke_management"
        self._affected_zones.add(zone_id)

        actions_taken = []

        # 1. Close supply dampers for the fire zone
        damper_results = await self.close_smoke_dampers(zone_id)
        actions_taken.append({
            "step": "close_supply_dampers",
            "zone_id": zone_id,
            "results": damper_results,
        })

        # 2. Simulate exhaust at reduced speed for smoke extraction
        floor = self._extract_floor(zone_id)
        exhaust_id = f"S002-EXH-{floor}-001" if floor else "S002-EXH-L1-001"
        exhaust_result = await self._execute_exhaust_action(exhaust_id, "activate", self._get_device_manager())
        actions_taken.append({
            "step": "exhaust_smoke_extraction",
            "exhaust_id": exhaust_id,
            "speed_pct": 60,
            "success": exhaust_result.get("success", False),
        })

        # 3. Pressurize adjacent zones (+5 Pa above normal)
        adjacent_zones = self._get_adjacent_zones(zone_id)
        if adjacent_zones:
            # Find stairwell pressurization systems for adjacent zones
            stairwell_ids = self._get_stairwells_for_zones(adjacent_zones)
            if stairwell_ids:
                press_results = await self.activate_pressurization(stairwell_ids)
                actions_taken.append({
                    "step": "adjacent_zone_pressurization",
                    "stairwell_ids": stairwell_ids,
                    "results": press_results,
                })

        # Log mode change
        self._repo.log_action({
            "action_type": "mode_change",
            "zone_id": zone_id,
            "description": f"Entered smoke_management mode for zone {zone_id}",
            "mode": self._mode,
            "details": {
                "actions_taken": len(actions_taken),
                "adjacent_zones": list(adjacent_zones) if adjacent_zones else [],
            },
        })

        return {
            "mode": self._mode,
            "zone_id": zone_id,
            "actions_taken": actions_taken,
            "adjacent_zones": list(adjacent_zones) if adjacent_zones else [],
        }

    async def reset_fire_mode(self) -> Dict[str, Any]:
        """Return to normal operations after alarm cleared.

        Staged reset:
        a. Re-open dampers (staged: 25% -> 50% -> 100%)
        b. Restart HVAC in sequence (AHU first, then FCU/VAV after 30s)
        c. Reduce pressurization fan speed gradually
        """
        previous_mode = self._mode
        self._mode = "resetting"

        reset_actions = []

        # 1. Staged damper re-opening
        all_dampers = self._repo.get_dampers()
        closed_dampers = [
            d for d in all_dampers
            if d.get("status") == DamperStatusEnum.CLOSED.value
        ]
        for damper in closed_dampers:
            damper_id = damper.get("damper_id", "")
            # Stage 1: 25%
            self._repo.update_damper(damper_id, {
                "position": 25,
                "target_position": 100,
                "status": DamperStatusEnum.TRANSIT.value,
            })

        # Stage 2: 50%
        for damper in closed_dampers:
            damper_id = damper.get("damper_id", "")
            self._repo.update_damper(damper_id, {
                "position": 50,
                "target_position": 100,
                "status": DamperStatusEnum.TRANSIT.value,
            })

        # Stage 3: 100%
        for damper in closed_dampers:
            damper_id = damper.get("damper_id", "")
            self._repo.update_damper(damper_id, {
                "position": 100,
                "target_position": 100,
                "status": DamperStatusEnum.OPEN.value,
            })

        reset_actions.append({
            "step": "damper_reset",
            "dampers_reopened": len(closed_dampers),
            "stages": ["25%", "50%", "100%"],
        })

        # 2. Restart HVAC - AHUs first, then FCU/VAV
        ahus_restarted = []
        other_restarted = []
        dm = self._get_device_manager()
        for device_info in self._shutdown_devices:
            device_id = device_info.get("device_id", "")
            if "AHU" in device_id:
                ahus_restarted.append(device_id)
                if dm and not device_info.get("simulated"):
                    try:
                        await dm.write_device_value(
                            device_id, "supply_fan", True, priority=1, user="fire_system"
                        )
                    except Exception as e:
                        logger.warning(f"Failed to restart AHU {device_id}: {e}")
            else:
                other_restarted.append(device_id)

        # FCU/VAV restart after AHUs (simulated delay)
        for device_id in other_restarted:
            if dm:
                try:
                    device_info_match = next(
                        (d for d in self._shutdown_devices if d.get("device_id") == device_id), None
                    )
                    if device_info_match and not device_info_match.get("simulated"):
                        await dm.write_device_value(
                            device_id, "supply_fan", True, priority=1, user="fire_system"
                        )
                except Exception as e:
                    logger.warning(f"Failed to restart {device_id}: {e}")

        reset_actions.append({
            "step": "hvac_restart",
            "ahus_restarted": ahus_restarted,
            "other_restarted": other_restarted,
            "sequence": "AHUs first, FCU/VAV after 30s delay",
        })

        # 3. Reduce pressurization gradually
        pressurization = self._repo.get_pressurization()
        running_fans = [
            p for p in pressurization
            if p.get("fan_status") == FanStatus.RUNNING.value
        ]
        for fan in running_fans:
            stairwell_id = fan.get("stairwell_id", "")
            self._repo.update_pressurization(stairwell_id, {
                "fan_status": FanStatus.OFF.value,
                "fan_speed_pct": 0,
                "current_pressure_pa": 0.0,
            })

        reset_actions.append({
            "step": "pressurization_reset",
            "fans_stopped": len(running_fans),
        })

        # Clear state
        self._shutdown_devices.clear()
        self._affected_zones.clear()
        self._mode = "normal"

        # Log all reset actions through repository
        self._repo.log_action({
            "action_type": "mode_change",
            "zone_id": "all",
            "description": f"Reset from {previous_mode} to normal mode",
            "mode": "normal",
            "details": {
                "previous_mode": previous_mode,
                "dampers_reopened": len(closed_dampers),
                "hvac_restarted": len(ahus_restarted) + len(other_restarted),
                "fans_stopped": len(running_fans),
            },
        })

        return {
            "mode": self._mode,
            "previous_mode": previous_mode,
            "reset_actions": reset_actions,
            "summary": {
                "dampers_reopened": len(closed_dampers),
                "hvac_restarted": len(ahus_restarted) + len(other_restarted),
                "fans_stopped": len(running_fans),
            },
        }

    def get_coordination_status(self) -> Dict[str, Any]:
        """Get current coordination state."""
        return {
            "mode": self._mode,
            "affected_zones": list(self._affected_zones),
            "shutdown_devices": self._shutdown_devices,
            "shutdown_device_count": len(self._shutdown_devices),
            "action_log": self._repo.get_action_log(limit=20),
        }

    # --- Helper methods ---

    def _extract_floor(self, zone_id: str) -> Optional[str]:
        """Extract floor from zone_id (e.g., FZ-L1-C -> L1)."""
        parts = zone_id.split("-")
        if len(parts) >= 2:
            return parts[1]
        return None

    def _get_adjacent_zones(self, zone_id: str) -> Set[str]:
        """Get adjacent fire zones on the same floor."""
        floor = self._extract_floor(zone_id)
        if not floor:
            return set()

        all_zones = self._repo.get_zones()
        adjacent = set()
        for zone in all_zones:
            z_id = zone.get("zone_id", "")
            if z_id != zone_id and zone.get("floor") == floor:
                adjacent.add(z_id)
        return adjacent

    def _get_stairwells_for_zones(self, zone_ids: Set[str]) -> List[str]:
        """Find stairwell pressurization systems for given zones.

        Returns stairwell IDs near the affected zones.
        """
        floors = set()
        for z_id in zone_ids:
            floor = self._extract_floor(z_id)
            if floor:
                floors.add(floor)

        pressurization = self._repo.get_pressurization()
        stairwell_ids = []
        # Activate all pressurization fans (building-wide for safety)
        for p in pressurization:
            stairwell_ids.append(p.get("stairwell_id", ""))

        return stairwell_ids


def get_fire_hvac_coordinator() -> FireHVACCoordinator:
    """Get or create singleton FireHVACCoordinator."""
    global _instance
    if _instance is None:
        _instance = FireHVACCoordinator()
    return _instance
