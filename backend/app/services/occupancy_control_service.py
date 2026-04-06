"""Occupancy-driven HVAC + lighting control service (Phase 130).

Polls PIR sensors and badge readers, evaluates occupancy per zone,
and issues setpoint relaxations (HVAC) and brightness adjustments (lighting)
when zones transition between occupied and unoccupied states.

Architecture:
    PIR sensors       ─┐
                       ├─► OccupancyControlService.run_cycle()
    Badge readers     ─┘       │
                               ├─► BMSControlBridge
                               │     ├─► HVAC: DeviceManager → protocol adapter → BMS
                               │     ├─► Lighting: DeviceManager → protocol adapter → BMS
                               │     └─► SENTINEL cache: zone registry (Supabase)
                               └─► Audit: occupancy_control_actions (Supabase)

Native controllers handle IMMEDIATE occupancy response natively (<1s).
    SENTINEL adds:
    - HVAC coordination (setpoint relaxation when zone empties)
    - Cross-zone balancing (thermal capacity sharing)
    - Tariff-aware scheduling (shift timing based on TOU rates)
    - Predictive pre-conditioning (anticipate occupancy 30 min ahead)
    - Audit trail for M&V verification
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from app.core.site_resolver import get_primary_site_code

logger = logging.getLogger(__name__)


class ZoneControlState:
    """Tracks the current control state for a single zone to prevent flapping."""

    __slots__ = (
        "hvac_relaxed",
        "last_action_time",
        "last_occupancy_pct",
        "lighting_dimmed",
        "original_brightness",
        "original_setpoint",
        "zone_id",
    )

    def __init__(self, zone_id: str):
        self.zone_id = zone_id
        self.hvac_relaxed: bool = False
        self.lighting_dimmed: bool = False
        self.last_occupancy_pct: float = -1.0
        self.last_action_time: datetime | None = None
        self.original_setpoint: float | None = None
        self.original_brightness: int | None = None


class OccupancyControlService:
    """Polls occupancy sources and executes HVAC/lighting control actions."""

    def __init__(self):
        self._zone_states: dict[str, ZoneControlState] = {}
        self._initialized = False

    def _get_zone_state(self, zone_id: str) -> ZoneControlState:
        if zone_id not in self._zone_states:
            self._zone_states[zone_id] = ZoneControlState(zone_id)
        return self._zone_states[zone_id]

    async def run_cycle(self, site_id: str | None = None) -> dict[str, Any]:
        """Execute one occupancy control cycle across all zones.

        Returns:
            Summary dict with actions_taken, zones_checked, errors.
        """
        site_id = site_id or get_primary_site_code() or "unknown"
        from app.config.settings import settings

        correlation_id = f"occ-{uuid.uuid4().hex[:8]}"
        actions_taken = 0
        zones_checked = 0
        errors = []

        try:
            lighting_svc = self._get_lighting_service()
            zones = lighting_svc.get_all_zones(site_id=site_id)
        except Exception as e:
            logger.error(f"[{correlation_id}] Failed to get zones: {e}")
            return {"actions_taken": 0, "zones_checked": 0, "errors": [str(e)]}

        for zone_info in zones:
            zone_id = zone_info.get("zone_id", "")
            if not zone_id:
                continue

            zones_checked += 1

            try:
                result = await self._process_zone(
                    site_id=site_id,
                    zone_id=zone_id,
                    correlation_id=correlation_id,
                    settings=settings,
                )
                actions_taken += result
            except Exception as e:
                error_msg = f"Zone {zone_id}: {e}"
                logger.error(f"[{correlation_id}] {error_msg}")
                errors.append(error_msg)

        if actions_taken > 0:
            logger.info(
                f"[{correlation_id}] Occupancy cycle complete: {actions_taken} actions across {zones_checked} zones"
            )

        return {
            "correlation_id": correlation_id,
            "actions_taken": actions_taken,
            "zones_checked": zones_checked,
            "errors": errors,
        }

    async def _process_zone(
        self,
        site_id: str,
        zone_id: str,
        correlation_id: str,
        settings: Any,
    ) -> int:
        """Process a single zone: read occupancy, decide action, execute.

        Returns number of actions taken (0, 1, or 2).
        """
        actions = 0

        # 1. Read occupancy from PIR sensors
        lighting_svc = self._get_lighting_service()
        zone_occ = lighting_svc.get_zone_occupancy(zone_id)
        occ_pct = zone_occ.occupancy_percent if zone_occ else 0.0
        occ_status = zone_occ.status if zone_occ else "empty"

        # 2. Also check badge-based occupancy
        badge_count = self._get_badge_occupancy(zone_id)

        # 3. Combine: use PIR as primary, badge as secondary
        occupancy_source = "pir"
        if zone_occ is None and badge_count is not None:
            occupancy_source = "badge"
            occ_pct = (
                100.0
                if badge_count > settings.occupancy_low_threshold
                else (50.0 if badge_count > settings.occupancy_empty_threshold else 0.0)
            )
        elif zone_occ and badge_count is not None:
            occupancy_source = "combined"

        state = self._get_zone_state(zone_id)

        # 4. Determine if zone is empty, low, or occupied
        is_empty = occ_pct < 10.0  # <10% = empty
        is_low = 10.0 <= occ_pct < 40.0  # 10-40% = low occupancy
        is_occupied = occ_pct >= 40.0  # 40%+ = normally occupied

        # 5. HVAC control
        hvac_action = await self._evaluate_hvac(
            site_id=site_id,
            zone_id=zone_id,
            state=state,
            is_empty=is_empty,
            is_low=is_low,
            is_occupied=is_occupied,
            occ_pct=occ_pct,
            occ_status=occ_status,
            occupancy_source=occupancy_source,
            badge_count=badge_count,
            correlation_id=correlation_id,
            settings=settings,
        )
        actions += hvac_action

        # 6. Lighting control
        lighting_action = await self._evaluate_lighting(
            site_id=site_id,
            zone_id=zone_id,
            state=state,
            is_empty=is_empty,
            is_low=is_low,
            is_occupied=is_occupied,
            occ_pct=occ_pct,
            occ_status=occ_status,
            occupancy_source=occupancy_source,
            badge_count=badge_count,
            correlation_id=correlation_id,
            settings=settings,
        )
        actions += lighting_action

        # 7. Update state
        state.last_occupancy_pct = occ_pct
        if actions > 0:
            state.last_action_time = datetime.now(UTC)

        return actions

    async def _evaluate_hvac(
        self,
        site_id: str,
        zone_id: str,
        state: ZoneControlState,
        is_empty: bool,
        is_low: bool,
        is_occupied: bool,
        occ_pct: float,
        occ_status: str,
        occupancy_source: str,
        badge_count: int | None,
        correlation_id: str,
        settings: Any,
    ) -> int:
        """Evaluate and execute HVAC setpoint changes based on occupancy."""
        if is_empty and not state.hvac_relaxed:
            # Zone just went empty → relax setpoint
            return await self._relax_hvac_setpoint(
                site_id=site_id,
                zone_id=zone_id,
                state=state,
                offset=settings.occupancy_hvac_setback_c,
                action_type="relax_setpoint",
                occ_pct=occ_pct,
                occ_status=occ_status,
                occupancy_source=occupancy_source,
                badge_count=badge_count,
                correlation_id=correlation_id,
            )
        elif is_low and not state.hvac_relaxed:
            # Zone is low → partial relaxation
            return await self._relax_hvac_setpoint(
                site_id=site_id,
                zone_id=zone_id,
                state=state,
                offset=settings.occupancy_hvac_partial_setback_c,
                action_type="partial_relax_setpoint",
                occ_pct=occ_pct,
                occ_status=occ_status,
                occupancy_source=occupancy_source,
                badge_count=badge_count,
                correlation_id=correlation_id,
            )
        elif is_occupied and state.hvac_relaxed:
            # Zone now occupied → restore setpoint
            return await self._restore_hvac_setpoint(
                site_id=site_id,
                zone_id=zone_id,
                state=state,
                occ_pct=occ_pct,
                occ_status=occ_status,
                occupancy_source=occupancy_source,
                badge_count=badge_count,
                correlation_id=correlation_id,
            )
        return 0

    async def _relax_hvac_setpoint(
        self,
        site_id: str,
        zone_id: str,
        state: ZoneControlState,
        offset: float,
        action_type: str,
        occ_pct: float,
        occ_status: str,
        occupancy_source: str,
        badge_count: int | None,
        correlation_id: str,
    ) -> int:
        """Relax HVAC setpoint for an unoccupied/low-occupancy zone.

        Reads the current setpoint from the BMS via BMSControlBridge,
        calculates the new setpoint, and writes back via DeviceManager.
        """
        bridge = self._get_bridge()

        # Read current setpoint from BMS (not from cache)
        current_setpoint = await bridge.read_hvac_setpoint(zone_id)
        if current_setpoint is None:
            # No equipment mapped or read failed — skip this zone
            return 0

        new_setpoint = current_setpoint + offset

        # Safety bounds (never exceed 28°C or go below 16°C)
        new_setpoint = max(16.0, min(28.0, new_setpoint))

        if abs(new_setpoint - current_setpoint) < 0.1:
            return 0  # No meaningful change

        # Write to BMS via bridge (DeviceManager → adapter → safety engine)
        result = await bridge.write_hvac_setpoint(
            zone_id=zone_id,
            new_setpoint=new_setpoint,
            who="occupancy_poller",
            reason=f"{action_type}: occ={occ_pct:.0f}%, offset={offset:+.1f}°C",
            correlation_id=correlation_id,
        )

        if not result.success:
            await self._log_action(
                site_id=site_id,
                zone_id=zone_id,
                module="hvac",
                action_type=action_type,
                previous_value=current_setpoint,
                new_value=new_setpoint,
                offset_applied=offset,
                occ_pct=occ_pct,
                occ_status=occ_status,
                occupancy_source=occupancy_source,
                badge_count=badge_count,
                status="failed",
                error_message=result.error or "bridge write failed",
                correlation_id=correlation_id,
            )
            return 0

        # Update state
        state.hvac_relaxed = True
        state.original_setpoint = current_setpoint

        await self._log_action(
            site_id=site_id,
            zone_id=zone_id,
            module="hvac",
            action_type=action_type,
            previous_value=current_setpoint,
            new_value=new_setpoint,
            offset_applied=offset,
            occ_pct=occ_pct,
            occ_status=occ_status,
            occupancy_source=occupancy_source,
            badge_count=badge_count,
            status="executed",
            correlation_id=correlation_id,
        )
        return 1

    async def _restore_hvac_setpoint(
        self,
        site_id: str,
        zone_id: str,
        state: ZoneControlState,
        occ_pct: float,
        occ_status: str,
        occupancy_source: str,
        badge_count: int | None,
        correlation_id: str,
    ) -> int:
        """Restore HVAC setpoint when zone becomes occupied again.

        Writes the original (pre-relaxation) setpoint back to the BMS.
        """
        if state.original_setpoint is None:
            state.hvac_relaxed = False
            return 0

        bridge = self._get_bridge()
        restore_to = state.original_setpoint

        # Read current from BMS for audit delta
        current_setpoint = await bridge.read_hvac_setpoint(zone_id)
        if current_setpoint is None:
            state.hvac_relaxed = False
            return 0

        result = await bridge.write_hvac_setpoint(
            zone_id=zone_id,
            new_setpoint=restore_to,
            who="occupancy_poller",
            reason=f"restore_setpoint: occ={occ_pct:.0f}%",
            correlation_id=correlation_id,
        )

        if not result.success:
            return 0

        await self._log_action(
            site_id=site_id,
            zone_id=zone_id,
            module="hvac",
            action_type="restore_setpoint",
            previous_value=current_setpoint,
            new_value=restore_to,
            offset_applied=restore_to - current_setpoint,
            occ_pct=occ_pct,
            occ_status=occ_status,
            occupancy_source=occupancy_source,
            badge_count=badge_count,
            status="executed",
            correlation_id=correlation_id,
        )

        state.hvac_relaxed = False
        state.original_setpoint = None
        return 1

    async def _evaluate_lighting(
        self,
        site_id: str,
        zone_id: str,
        state: ZoneControlState,
        is_empty: bool,
        is_low: bool,
        is_occupied: bool,
        occ_pct: float,
        occ_status: str,
        occupancy_source: str,
        badge_count: int | None,
        correlation_id: str,
        settings: Any,
    ) -> int:
        """Evaluate and execute lighting brightness changes based on occupancy.

        Native lighting controllers handle immediate occupancy dimming (<1s).
        SENTINEL adds tariff-aware scheduling and cross-zone coordination.
        Writes go through BMSControlBridge → DeviceManager → BMS controller.
        """
        if is_empty and not state.lighting_dimmed:
            return await self._dim_lighting(
                site_id=site_id,
                zone_id=zone_id,
                state=state,
                brightness=settings.occupancy_lighting_empty_pct,
                action_type="dim_to_minimum",
                occ_pct=occ_pct,
                occ_status=occ_status,
                occupancy_source=occupancy_source,
                badge_count=badge_count,
                correlation_id=correlation_id,
            )
        elif is_low and not state.lighting_dimmed:
            return await self._dim_lighting(
                site_id=site_id,
                zone_id=zone_id,
                state=state,
                brightness=settings.occupancy_lighting_low_pct,
                action_type="dim_partial",
                occ_pct=occ_pct,
                occ_status=occ_status,
                occupancy_source=occupancy_source,
                badge_count=badge_count,
                correlation_id=correlation_id,
            )
        elif is_occupied and state.lighting_dimmed:
            return await self._restore_lighting(
                site_id=site_id,
                zone_id=zone_id,
                state=state,
                occ_pct=occ_pct,
                occ_status=occ_status,
                occupancy_source=occupancy_source,
                badge_count=badge_count,
                correlation_id=correlation_id,
            )
        return 0

    async def _dim_lighting(
        self,
        site_id: str,
        zone_id: str,
        state: ZoneControlState,
        brightness: int,
        action_type: str,
        occ_pct: float,
        occ_status: str,
        occupancy_source: str,
        badge_count: int | None,
        correlation_id: str,
    ) -> int:
        """Dim lighting for an unoccupied/low zone via BMSControlBridge.

        Reads current brightness from BMS, writes new brightness back to
        BMS via bridge → DeviceManager → adapter → BMS controller.
        """
        bridge = self._get_bridge()

        # Read current brightness from BMS
        current_brightness_f = await bridge.read_lighting_brightness(zone_id)
        current_brightness = int(current_brightness_f) if current_brightness_f is not None else None

        if current_brightness is not None and current_brightness <= brightness:
            return 0  # Already dim enough

        result = await bridge.write_lighting_brightness(
            zone_id=zone_id,
            brightness_pct=brightness,
            who="occupancy_poller",
            reason=f"{action_type}: occ={occ_pct:.0f}%",
            correlation_id=correlation_id,
        )

        if not result.success:
            await self._log_action(
                site_id=site_id,
                zone_id=zone_id,
                module="lighting",
                action_type=action_type,
                previous_value=current_brightness,
                new_value=float(brightness),
                offset_applied=float(brightness - (current_brightness or 100)),
                occ_pct=occ_pct,
                occ_status=occ_status,
                occupancy_source=occupancy_source,
                badge_count=badge_count,
                status="failed",
                error_message=result.error or "bridge write failed",
                correlation_id=correlation_id,
            )
            return 0

        state.lighting_dimmed = True
        state.original_brightness = current_brightness or 100

        await self._log_action(
            site_id=site_id,
            zone_id=zone_id,
            module="lighting",
            action_type=action_type,
            previous_value=float(current_brightness or 100),
            new_value=float(brightness),
            offset_applied=float(brightness - (current_brightness or 100)),
            occ_pct=occ_pct,
            occ_status=occ_status,
            occupancy_source=occupancy_source,
            badge_count=badge_count,
            status="executed",
            correlation_id=correlation_id,
        )
        return 1

    async def _restore_lighting(
        self,
        site_id: str,
        zone_id: str,
        state: ZoneControlState,
        occ_pct: float,
        occ_status: str,
        occupancy_source: str,
        badge_count: int | None,
        correlation_id: str,
    ) -> int:
        """Restore lighting when zone becomes occupied.

        Writes original brightness back to BMS via bridge.
        """
        if state.original_brightness is None:
            state.lighting_dimmed = False
            return 0

        bridge = self._get_bridge()
        restore_to = state.original_brightness

        # Read current from BMS for audit delta
        current_brightness_f = await bridge.read_lighting_brightness(zone_id)
        current_brightness = int(current_brightness_f) if current_brightness_f is not None else 0

        result = await bridge.write_lighting_brightness(
            zone_id=zone_id,
            brightness_pct=restore_to,
            who="occupancy_poller",
            reason=f"restore_brightness: occ={occ_pct:.0f}%",
            correlation_id=correlation_id,
        )

        if not result.success:
            return 0

        await self._log_action(
            site_id=site_id,
            zone_id=zone_id,
            module="lighting",
            action_type="restore_brightness",
            previous_value=float(current_brightness),
            new_value=float(restore_to),
            offset_applied=float(restore_to - current_brightness),
            occ_pct=occ_pct,
            occ_status=occ_status,
            occupancy_source=occupancy_source,
            badge_count=badge_count,
            status="executed",
            correlation_id=correlation_id,
        )

        state.lighting_dimmed = False
        state.original_brightness = None
        return 1

    # ------------------------------------------------------------------
    # Service accessors (lazy imports to avoid circular dependencies)
    # ------------------------------------------------------------------

    def _get_bridge(self):
        """Get the BMSControlBridge singleton for BMS reads/writes."""
        from app.services.bms_control_bridge import get_bms_control_bridge

        return get_bms_control_bridge()

    def _get_lighting_service(self):
        """Get LightingService for reading occupancy sensor data from BMS."""
        from app.services.lighting_service import LightingService

        return LightingService()

    def _get_badge_occupancy(self, zone_id: str) -> int | None:
        """Get badge-based occupancy count for a zone. Returns None if unavailable."""
        try:
            from app.services.security_occupancy_service import SecurityOccupancyService

            svc = SecurityOccupancyService()
            zone_data = svc.get_zone_occupancy(zone_id)
            if zone_data:
                return zone_data.get("occupancy_count", 0)
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    # Audit logging
    # ------------------------------------------------------------------

    async def _log_action(
        self,
        site_id: str,
        zone_id: str,
        module: str,
        action_type: str,
        previous_value: float | None,
        new_value: float | None,
        offset_applied: float | None,
        occ_pct: float,
        occ_status: str,
        occupancy_source: str,
        badge_count: int | None,
        status: str,
        correlation_id: str,
        error_message: str | None = None,
    ):
        """Log control action to Supabase occupancy_control_actions table."""
        try:
            from app.database.connection import get_supabase_client

            client = get_supabase_client()
            if not client:
                return

            record = {
                "site_id": site_id,
                "zone_id": zone_id,
                "occupancy_source": occupancy_source,
                "occupancy_percent": occ_pct,
                "occupancy_count": badge_count,
                "occupancy_status": occ_status,
                "module": module,
                "action_type": action_type,
                "previous_value": previous_value,
                "new_value": new_value,
                "offset_applied": offset_applied,
                "status": status,
                "error_message": error_message,
                "triggered_by": "occupancy_poller",
                "correlation_id": correlation_id,
            }

            client.table("occupancy_control_actions").insert(record).execute()
        except Exception as e:
            # Audit failure should never block control actions
            logger.warning(f"Failed to log occupancy action: {e}")


# Module-level singleton
_occupancy_control_service: OccupancyControlService | None = None


def get_occupancy_control_service() -> OccupancyControlService:
    """Get or create the singleton OccupancyControlService."""
    global _occupancy_control_service
    if _occupancy_control_service is None:
        _occupancy_control_service = OccupancyControlService()
    return _occupancy_control_service
