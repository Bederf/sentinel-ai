"""BMS Control Bridge — routes SENTINEL decisions to building equipment.

Resolves zone IDs to equipment, reads current state from the BMS via
DeviceManager, writes new setpoints/commands via protocol adapters
(BACnet, Modbus, Mock), and updates SENTINEL's cache in Supabase.

SENTINEL is brand-agnostic and protocol-agnostic.  This bridge behaves
identically regardless of whether the equipment behind a zone is
Tridonic DALI, Schneider, Siemens, or any other manufacturer.
The DeviceManager + adapter layer handles protocol differences.

Architecture:
    SENTINEL decision (occupancy, optimizer, API)
        │
        ▼
    BMSControlBridge
        ├─► 1. Resolve zone → equipment (zone registry: vav_id / fcu_id / lighting_id)
        ├─► 2. Ensure DeviceManager initialised
        ├─► 3. DeviceManager.read_device_value()  ← current state from BMS
        ├─► 4. DeviceManager.write_device_value() ← command to BMS controller
        │       └─► SafetyEngine validates
        │       └─► Adapter handles protocol (BACnet / Modbus / Mock / …)
        ├─► 5. Update SENTINEL's cache (zone registry in Supabase)
        └─► 6. Return WriteResult for audit

    Equipment exposes *points* (temperature_setpoint, brightness, on_off, …)
    discovered during onboarding.  The bridge writes to points, never to
    brand-specific APIs.
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class WriteResult:
    """Result of a BMS write operation — audit-friendly."""

    success: bool
    equipment_id: str
    point_name: str
    previous_value: Optional[float] = None
    requested_value: Optional[float] = None
    actual_value: Optional[float] = None  # After safety clamping
    verified: bool = False
    error: Optional[str] = None
    correlation_id: str = ""
    who: str = "sentinel"
    reason: str = ""
    timestamp: str = ""
    write_latency_ms: float = 0.0
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.correlation_id:
            self.correlation_id = f"bms-{uuid.uuid4().hex[:8]}"
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


class BMSControlBridge:
    """Routes SENTINEL control decisions to building equipment via DeviceManager.

    Brand-agnostic: resolves zones to equipment IDs, reads/writes points.
    The DeviceManager and its adapters handle protocol details.
    """

    def __init__(self):
        self._dm_initialised = False

    async def _ensure_device_manager(self):
        """Ensure DeviceManager is initialised with equipment from buildings."""
        if self._dm_initialised:
            return
        from app.services.ai_optimizer import ensure_device_manager_initialized

        await ensure_device_manager_initialized()
        self._dm_initialised = True

    # ------------------------------------------------------------------
    # Zone → Equipment resolution
    # ------------------------------------------------------------------

    def _resolve_zone_equipment(self, zone_id: str) -> dict:
        """Resolve a zone ID to all its mapped equipment codes.

        Reads from SENTINEL's zone registry (hvac_zones table — our cache
        of what was discovered during onboarding).

        Returns:
            dict with keys: vav_id, fcu_id, ahu_id, lighting_id (any may be None)
        """
        from app.database.repositories.hvac_zone_repository import HvacZoneRepository

        repo = HvacZoneRepository()
        zone = repo.get_by_zone_id(zone_id)
        if not zone:
            return {}
        return {
            "vav_id": zone.get("vav_id"),
            "fcu_id": zone.get("fcu_id"),
            "ahu_id": zone.get("ahu_id"),
            "lighting_id": zone.get("lighting_id"),
            "zone_data": zone,
        }

    def _pick_setpoint_equipment(self, zone_equipment: dict) -> Optional[str]:
        """Pick the best equipment for temperature setpoint control.

        VAVs are preferred because they directly control zone air supply.
        FCUs are fallback.  AHUs serve multiple zones so are not used for
        zone-level setpoint changes.
        """
        return zone_equipment.get("vav_id") or zone_equipment.get("fcu_id")

    def _pick_lighting_equipment(self, zone_equipment: dict) -> Optional[str]:
        """Pick the equipment for lighting control in this zone.

        Returns the lighting_id from the zone registry — whatever equipment
        handles lighting for this zone, regardless of brand or protocol.
        """
        return zone_equipment.get("lighting_id")

    # ------------------------------------------------------------------
    # Generic point read/write (the core of the bridge)
    # ------------------------------------------------------------------

    async def _read_point(self, equipment_id: str, point_name: str) -> Optional[float]:
        """Read a point value from the BMS for a given equipment.

        Returns None if the read fails or equipment not found.
        """
        await self._ensure_device_manager()
        from app.services.device_abstraction import device_manager

        try:
            result = await device_manager.read_device_value(equipment_id, point_name)
            return result.value
        except Exception as e:
            logger.debug(f"Could not read {point_name} for {equipment_id}: {e}")
            return None

    async def _write_point(
        self,
        equipment_id: str,
        point_name: str,
        value: float,
        *,
        who: str = "sentinel",
        reason: str = "",
        correlation_id: str = "",
    ) -> WriteResult:
        """Write a point value to the BMS for a given equipment.

        Routes through DeviceManager → adapter → safety engine → protocol.
        Returns WriteResult for audit regardless of success or failure.
        """
        result_id = correlation_id or f"bms-{uuid.uuid4().hex[:8]}"
        start = datetime.now(timezone.utc)

        await self._ensure_device_manager()
        from app.services.device_abstraction import device_manager

        # Check adapter exists
        adapter = await device_manager.get_adapter(equipment_id)
        if not adapter:
            return WriteResult(
                success=False,
                equipment_id=equipment_id,
                point_name=point_name,
                requested_value=value,
                error=f"No adapter for equipment {equipment_id}",
                correlation_id=result_id,
                who=who,
                reason=reason,
            )

        # Read current value from BMS
        previous_value = None
        try:
            current = await device_manager.read_device_value(equipment_id, point_name)
            previous_value = current.value
        except Exception as e:
            logger.warning(f"[{result_id}] Could not read current {point_name} for {equipment_id}: {e}")

        # Write to BMS via DeviceManager (safety engine validates inside adapter)
        try:
            success = await device_manager.write_device_value(
                device_id=equipment_id,
                point_name=point_name,
                value=value,
                priority=8,  # BACnet priority 8 = SENTINEL level
                user=who,
            )
        except ValueError as e:
            # Safety engine blocked or validation failed
            elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
            return WriteResult(
                success=False,
                equipment_id=equipment_id,
                point_name=point_name,
                previous_value=previous_value,
                requested_value=value,
                error=str(e),
                correlation_id=result_id,
                who=who,
                reason=reason,
                write_latency_ms=elapsed,
            )
        except Exception as e:
            elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
            return WriteResult(
                success=False,
                equipment_id=equipment_id,
                point_name=point_name,
                previous_value=previous_value,
                requested_value=value,
                error=f"Write failed: {e}",
                correlation_id=result_id,
                who=who,
                reason=reason,
                write_latency_ms=elapsed,
            )

        elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000

        if success:
            logger.info(f"[{result_id}] BMS write: {equipment_id}.{point_name} {previous_value} → {value} (who={who})")

        return WriteResult(
            success=success,
            equipment_id=equipment_id,
            point_name=point_name,
            previous_value=previous_value,
            requested_value=value,
            actual_value=value if success else None,
            correlation_id=result_id,
            who=who,
            reason=reason,
            write_latency_ms=elapsed,
        )

    # ------------------------------------------------------------------
    # HVAC Setpoint Control
    # ------------------------------------------------------------------

    async def write_hvac_setpoint(
        self,
        zone_id: str,
        new_setpoint: float,
        *,
        who: str = "sentinel",
        reason: str = "",
        correlation_id: str = "",
    ) -> WriteResult:
        """Write an HVAC setpoint to the BMS for a given zone.

        1. Resolve zone → HVAC equipment (VAV preferred, FCU fallback)
        2. Write temperature_setpoint point via DeviceManager
        3. Update SENTINEL's zone registry cache
        4. Return WriteResult for audit
        """
        result_id = correlation_id or f"hvac-{uuid.uuid4().hex[:8]}"

        # 1. Resolve zone → equipment
        zone_eq = self._resolve_zone_equipment(zone_id)
        equipment_id = self._pick_setpoint_equipment(zone_eq)

        if not equipment_id:
            return WriteResult(
                success=False,
                equipment_id="",
                point_name="temperature_setpoint",
                requested_value=new_setpoint,
                error=f"No HVAC equipment mapped to zone {zone_id}",
                correlation_id=result_id,
                who=who,
                reason=reason,
            )

        # 2. Write via generic point write
        result = await self._write_point(
            equipment_id=equipment_id,
            point_name="temperature_setpoint",
            value=new_setpoint,
            who=who,
            reason=reason,
            correlation_id=result_id,
        )

        # 3. Update SENTINEL's cache on success
        if result.success:
            self._update_sentinel_cache(zone_id, "setpoint", new_setpoint)

        result.metadata["zone_id"] = zone_id
        return result

    async def write_lighting_brightness(
        self,
        zone_id: str,
        brightness_pct: int,
        *,
        who: str = "sentinel",
        reason: str = "",
        correlation_id: str = "",
    ) -> WriteResult:
        """Write a lighting brightness level to the BMS for a given zone.

        1. Resolve zone → lighting equipment (brand-agnostic)
        2. Write brightness point via DeviceManager
        3. Return WriteResult for audit
        """
        result_id = correlation_id or f"light-{uuid.uuid4().hex[:8]}"

        # 1. Resolve zone → lighting equipment
        zone_eq = self._resolve_zone_equipment(zone_id)
        equipment_id = self._pick_lighting_equipment(zone_eq)

        if not equipment_id:
            return WriteResult(
                success=False,
                equipment_id="",
                point_name="brightness",
                requested_value=float(brightness_pct),
                error=f"No lighting equipment mapped to zone {zone_id}",
                correlation_id=result_id,
                who=who,
                reason=reason,
            )

        # 2. Write via generic point write
        result = await self._write_point(
            equipment_id=equipment_id,
            point_name="brightness",
            value=float(brightness_pct),
            who=who,
            reason=reason,
            correlation_id=result_id,
        )

        result.metadata["zone_id"] = zone_id
        return result

    # ------------------------------------------------------------------
    # Read current state from BMS
    # ------------------------------------------------------------------

    async def read_hvac_setpoint(self, zone_id: str) -> Optional[float]:
        """Read the current HVAC setpoint from the BMS for a zone.

        Returns None if the zone has no mapped equipment or the read fails.
        """
        zone_eq = self._resolve_zone_equipment(zone_id)
        equipment_id = self._pick_setpoint_equipment(zone_eq)
        if not equipment_id:
            return None
        return await self._read_point(equipment_id, "temperature_setpoint")

    async def read_zone_temperature(self, zone_id: str) -> Optional[float]:
        """Read the current room temperature from the BMS for a zone."""
        zone_eq = self._resolve_zone_equipment(zone_id)
        equipment_id = self._pick_setpoint_equipment(zone_eq)
        if not equipment_id:
            return None
        return await self._read_point(equipment_id, "room_temperature")

    async def read_lighting_brightness(self, zone_id: str) -> Optional[float]:
        """Read the current brightness from the BMS for a zone.

        Returns None if the zone has no lighting equipment or the read fails.
        """
        zone_eq = self._resolve_zone_equipment(zone_id)
        equipment_id = self._pick_lighting_equipment(zone_eq)
        if not equipment_id:
            return None
        return await self._read_point(equipment_id, "brightness")

    # ------------------------------------------------------------------
    # SENTINEL cache update (our Supabase, not the building's DB)
    # ------------------------------------------------------------------

    def _update_sentinel_cache(self, zone_id: str, field: str, value: float):
        """Update SENTINEL's zone registry with a new value.

        This is our cache of the building state — not the building's DB.
        """
        try:
            from app.database.repositories.hvac_zone_repository import HvacZoneRepository

            repo = HvacZoneRepository()
            if field == "setpoint":
                repo.update_setpoint(zone_id, value)
            # Other fields can be added as needed
        except Exception as e:
            # Cache update failure should never block the control action
            logger.warning(f"Failed to update SENTINEL cache for {zone_id}.{field}: {e}")


# Module-level singleton
_bridge: Optional[BMSControlBridge] = None


def get_bms_control_bridge() -> BMSControlBridge:
    """Get or create the singleton BMSControlBridge."""
    global _bridge
    if _bridge is None:
        _bridge = BMSControlBridge()
    return _bridge
