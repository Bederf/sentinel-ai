"""Security occupancy coordination service.

Calculates per-zone occupancy from badge events (entries - exits),
provides building-wide and floor-level occupancy aggregation, and
generates cross-module recommendations for HVAC and Lighting adjustments
based on zone occupancy levels.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.database.repositories.security_repository import get_security_repository
from app.models.security import OccupancySource, SecurityOccupancy
from app.core.site_resolver import get_primary_site
from app.services.profile_service import get_profile_service

logger = logging.getLogger(__name__)

_instance: Optional["SecurityOccupancyService"] = None

# Default thresholds for cross-module recommendations (fallback if profile not available)
OCCUPANCY_EMPTY_THRESHOLD = 0  # 0 people = empty zone
OCCUPANCY_LOW_THRESHOLD = 3  # Below this, zone considered low-occupancy
HVAC_RELAXATION_OFFSET = 2.0  # Degrees to relax setpoint for empty zones
LIGHTING_DIM_LEVEL = 20  # % brightness for empty zones
LIGHTING_LOW_LEVEL = 50  # % brightness for low-occupancy zones


class SecurityOccupancyService:
    """Service for occupancy tracking and cross-module coordination."""

    def __init__(self):
        self._repo = get_security_repository()
        self._profile_service = get_profile_service()

    def _get_profile_thresholds(self, site_id: str) -> Dict[str, Any]:
        """Get occupancy thresholds from site profile, or use defaults.

        Returns a dict with profile-specific thresholds for HVAC and lighting
        adjustments based on zone occupancy levels.
        """
        try:
            profile = self._profile_service.get_site_profile(site_id)
            if profile:
                thresholds = profile.get("thresholds", {})
                return {
                    "hvac_setback": thresholds.get("empty_zone_setback", HVAC_RELAXATION_OFFSET),
                    "lighting_empty": thresholds.get("empty_zone_lighting", LIGHTING_DIM_LEVEL),
                    "lighting_low": thresholds.get("low_occupancy_lighting", LIGHTING_LOW_LEVEL),
                }
        except Exception as e:
            logger.warning(f"Failed to load profile thresholds for site {site_id}: {e}")

        # Return defaults
        return {
            "hvac_setback": HVAC_RELAXATION_OFFSET,
            "lighting_empty": LIGHTING_DIM_LEVEL,
            "lighting_low": LIGHTING_LOW_LEVEL,
        }

    def _calculate_zone_occupancy(self, zone_id: str) -> Dict[str, Any]:
        """Calculate occupancy for a zone from badge events."""
        events = self._repo.get_badge_events(zone_id=zone_id, limit=500)

        entries = sum(1 for e in events if e.get("direction") == "entry" and e.get("granted", True))
        exits = sum(1 for e in events if e.get("direction") == "exit" and e.get("granted", True))

        # Occupancy = entries - exits (minimum 0)
        occupancy = max(0, entries - exits)

        # Get zone name
        zone = self._repo.get_zone(zone_id)
        zone_name = zone.get("name", zone_id) if zone else zone_id

        return {
            "zone_id": zone_id,
            "zone_name": zone_name,
            "occupancy_count": occupancy,
            "badge_entries": entries,
            "badge_exits": exits,
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "source": "badge",
        }

    def get_zone_occupancy(self, zone_id: str) -> SecurityOccupancy:
        """Get occupancy for a specific zone."""
        data = self._calculate_zone_occupancy(zone_id)
        return SecurityOccupancy(
            zone_id=data["zone_id"],
            zone_name=data["zone_name"],
            occupancy_count=data["occupancy_count"],
            badge_entries=data["badge_entries"],
            badge_exits=data["badge_exits"],
            last_updated=data["last_updated"],
            source=OccupancySource(data["source"]),
        )

    def get_building_occupancy(self) -> Dict[str, Any]:
        """Get total building occupancy from all zones."""
        zones = self._repo.get_zones()
        zone_occupancies = []
        total = 0

        for zone in zones:
            zone_id = zone.get("zone_id", "")
            occ_data = self._calculate_zone_occupancy(zone_id)
            zone_occupancies.append(occ_data)
            total += occ_data["occupancy_count"]

        return {
            "building_id": get_primary_site() or "unknown",
            "building_name": "Sandton City Office Tower",
            "total_occupancy": total,
            "zones": zone_occupancies,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

    def get_occupancy_by_floor(self, floor: str) -> Dict[str, Any]:
        """Get floor-level occupancy aggregation."""
        zones = self._repo.get_zones()
        floor_zones = [z for z in zones if z.get("floor") == floor]
        zone_occupancies = []
        total = 0

        for zone in floor_zones:
            zone_id = zone.get("zone_id", "")
            occ_data = self._calculate_zone_occupancy(zone_id)
            zone_occupancies.append(occ_data)
            total += occ_data["occupancy_count"]

        return {
            "floor": floor,
            "total_occupancy": total,
            "zone_count": len(floor_zones),
            "zones": zone_occupancies,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

    def get_floor_occupancy(self, floor: str) -> Dict[str, Any]:
        """Alias for get_occupancy_by_floor — used by API endpoints."""
        return self.get_occupancy_by_floor(floor)

    def process_access_event(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle a badge access event and update zone occupancy.

        Args:
            event_data: Dict with keys: equipment_id, person_id, direction, timestamp, zone_id

        Returns:
            Dict with processing result including updated occupancy.
        """
        zone_id = event_data.get("zone_id", "")
        direction = event_data.get("direction", "")
        person_id = event_data.get("person_id", "unknown")

        if not zone_id:
            logger.warning("process_access_event: missing zone_id, skipping")
            return {"status": "skipped", "reason": "missing zone_id"}

        if direction not in ("entry", "exit"):
            logger.warning(f"process_access_event: invalid direction '{direction}', skipping")
            return {"status": "skipped", "reason": f"invalid direction: {direction}"}

        # Recalculate occupancy after event
        occ_data = self._calculate_zone_occupancy(zone_id)

        logger.info(
            f"Access event processed: {person_id} {direction} zone {zone_id}, "
            f"occupancy now {occ_data['occupancy_count']}"
        )

        # Check for cross-module triggers
        hvac_rec = self.check_hvac_adjustment(zone_id)
        lighting_rec = self.check_lighting_adjustment(zone_id)

        return {
            "status": "processed",
            "zone_id": zone_id,
            "direction": direction,
            "person_id": person_id,
            "current_occupancy": occ_data["occupancy_count"],
            "hvac_recommendation": hvac_rec,
            "lighting_recommendation": lighting_rec,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def get_occupancy_trend(self, zone_id: str, hours: int = 24) -> List[Dict[str, Any]]:
        """Get hourly occupancy trend data for a zone.

        Queries badge events for the specified time range and returns
        hourly occupancy snapshots for trending and analysis.

        Args:
            zone_id: Zone identifier
            hours: Number of hours to look back (default 24)

        Returns:
            List of hourly occupancy readings for graphing.
        """
        now = datetime.now(timezone.utc)
        start_time = now - timedelta(hours=hours)

        # Get badge events for time range
        events = self._repo.get_badge_events(zone_id=zone_id, limit=2000)

        # Filter events to time window
        filtered_events = []
        for event in events:
            ts_str = event.get("timestamp", "")
            if ts_str:
                try:
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    if ts >= start_time:
                        filtered_events.append(event)
                except (ValueError, TypeError):
                    continue

        # Build hourly buckets
        hourly_data: List[Dict[str, Any]] = []
        for h in range(hours):
            bucket_start = start_time + timedelta(hours=h)
            bucket_end = bucket_start + timedelta(hours=1)

            # Count entries and exits in this hour
            entries = 0
            exits = 0
            for event in filtered_events:
                ts_str = event.get("timestamp", "")
                try:
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    if bucket_start <= ts < bucket_end:
                        if event.get("direction") == "entry" and event.get("granted", True):
                            entries += 1
                        elif event.get("direction") == "exit" and event.get("granted", True):
                            exits += 1
                except (ValueError, TypeError):
                    continue

            # Net occupancy for this hour
            net_occupancy = max(0, entries - exits)

            hourly_data.append(
                {
                    "hour": bucket_start.isoformat(),
                    "entries": entries,
                    "exits": exits,
                    "net_occupancy": net_occupancy,
                    "zone_id": zone_id,
                }
            )

        return hourly_data

    # --- Cross-module coordination ---

    def check_hvac_adjustment(
        self, zone_id: str, thresholds: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Check if HVAC setpoint should be relaxed based on occupancy.

        Uses profile-driven thresholds if provided, otherwise uses defaults.

        Args:
            zone_id: Zone identifier
            thresholds: Profile-driven thresholds (contains hvac_setback)
        """
        if thresholds is None:
            thresholds = {"hvac_setback": HVAC_RELAXATION_OFFSET}

        hvac_setback = thresholds.get("hvac_setback", HVAC_RELAXATION_OFFSET)

        occ = self._calculate_zone_occupancy(zone_id)
        count = occ["occupancy_count"]
        zone_name = occ["zone_name"]

        if count <= OCCUPANCY_EMPTY_THRESHOLD:
            return {
                "zone_id": zone_id,
                "zone_name": zone_name,
                "occupancy": count,
                "recommendation": "relax_setpoint",
                "detail": (
                    f"Zone {zone_name} is empty. Recommend relaxing cooling "
                    f"setpoint by +{hvac_setback}°C to save energy."
                ),
                "setpoint_offset": hvac_setback,
                "reason": "Zone unoccupied based on badge data",
                "module": "hvac",
            }
        elif count <= OCCUPANCY_LOW_THRESHOLD:
            offset = hvac_setback / 2
            return {
                "zone_id": zone_id,
                "zone_name": zone_name,
                "occupancy": count,
                "recommendation": "partial_relax",
                "detail": (
                    f"Zone {zone_name} has low occupancy ({count} people). "
                    f"Recommend relaxing cooling setpoint by +{offset}°C."
                ),
                "setpoint_offset": offset,
                "reason": f"Low occupancy ({count} people)",
                "module": "hvac",
            }
        return None

    def check_lighting_adjustment(
        self, zone_id: str, thresholds: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Check if lighting should be dimmed based on occupancy.

        Uses profile-driven thresholds if provided, otherwise uses defaults.

        Args:
            zone_id: Zone identifier
            thresholds: Profile-driven thresholds (contains lighting_empty, lighting_low)
        """
        if thresholds is None:
            thresholds = {
                "lighting_empty": LIGHTING_DIM_LEVEL,
                "lighting_low": LIGHTING_LOW_LEVEL,
            }

        lighting_empty = thresholds.get("lighting_empty", LIGHTING_DIM_LEVEL)
        lighting_low = thresholds.get("lighting_low", LIGHTING_LOW_LEVEL)

        occ = self._calculate_zone_occupancy(zone_id)
        count = occ["occupancy_count"]
        zone_name = occ["zone_name"]

        if count <= OCCUPANCY_EMPTY_THRESHOLD:
            return {
                "zone_id": zone_id,
                "zone_name": zone_name,
                "occupancy": count,
                "recommendation": "dim_to_minimum",
                "detail": f"Zone {zone_name} is empty. Recommend dimming lights to {lighting_empty}%.",
                "brightness_level": lighting_empty,
                "reason": "Zone unoccupied based on badge data",
                "module": "lighting",
            }
        elif count <= OCCUPANCY_LOW_THRESHOLD:
            return {
                "zone_id": zone_id,
                "zone_name": zone_name,
                "occupancy": count,
                "recommendation": "dim_partial",
                "detail": (
                    f"Zone {zone_name} has low occupancy ({count} people). Recommend dimming lights to {lighting_low}%."
                ),
                "brightness_level": lighting_low,
                "reason": f"Low occupancy ({count} people)",
                "module": "lighting",
            }
        return None

    def get_all_recommendations(self, site_id: str) -> Dict[str, Any]:
        """Get cross-module recommendations for all zones.

        Uses profile-driven thresholds from the site's active profile.

        Args:
            site_id: Site identifier for profile lookup
        """
        zones = self._repo.get_zones()
        hvac_recommendations = []
        lighting_recommendations = []

        # Load profile thresholds for this site
        thresholds = self._get_profile_thresholds(site_id)

        for zone in zones:
            zone_id = zone.get("zone_id", "")

            hvac_rec = self.check_hvac_adjustment(zone_id, thresholds)
            if hvac_rec:
                hvac_recommendations.append(hvac_rec)

            lighting_rec = self.check_lighting_adjustment(zone_id, thresholds)
            if lighting_rec:
                lighting_recommendations.append(lighting_rec)

        # Try to get DALI sensor data for combined occupancy
        dali_data = self._get_dali_occupancy_data()

        return {
            "hvac": hvac_recommendations,
            "lighting": lighting_recommendations,
            "total_recommendations": len(hvac_recommendations) + len(lighting_recommendations),
            "dali_data_available": dali_data is not None,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

    def _get_dali_occupancy_data(self) -> Optional[Dict[str, Any]]:
        """Try to get DALI PIR sensor data for combined occupancy."""
        try:
            from app.services.lighting_service import get_lighting_service

            dali = get_lighting_service()
            zones = dali.get_zones()
            if zones:
                return {
                    "zone_count": len(zones),
                    "source": "dali_pir",
                }
        except Exception:
            pass
        return None

    # --- C•CURE 9000 Integration: Anomaly Detection (Phase 58.2) ---

    def detect_after_hours_anomaly(self, site_id: str | None = None) -> List[Dict]:
        """Detect after-hours badge access + HVAC/lighting activation correlation.

        Priority 1: After-hours anomaly detection

        Args:
            site_id: Site identifier

        Returns:
            List of anomaly dicts with:
            - type: "after_hours_access"
            - severity: "warning" | "critical"
            - badge_event: Badge event details
            - hvac_activation: HVAC zone activation details
            - lighting_activation: Lighting zone activation details
            - energy_impact: Estimated kWh excess consumption
            - recommendation: Action for operator
        """
        from app.services.ccure import CCureAdapter

        after_hours_events = []

        # Create CCure adapter in demo mode
        adapter = CCureAdapter(demo_mode=True)

        # Get badge events from C•CURE
        import asyncio

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        events = loop.run_until_complete(adapter.get_badge_events(limit=50))

        for event in events:
            # Check if event is marked as after_hours or timestamp is after 18:00 / before 06:00
            timestamp_str = event.get("timestamp")
            if timestamp_str:
                event_time = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                hour = event_time.hour

                # After hours: 18:00 (6 PM) to 06:00 (6 AM)
                is_after_hours = event.get("after_hours", False) or (hour >= 18 or hour < 6)

                if is_after_hours and event.get("granted", True):
                    zone_id = event.get("zone_id")

                    # For demo: simulate HVAC/lighting activation
                    hvac_activation = self._simulate_hvac_activation(zone_id, event_time)
                    lighting_activation = self._simulate_lighting_activation(zone_id, event_time)

                    if hvac_activation or lighting_activation:
                        anomaly = {
                            "type": "after_hours_access",
                            "severity": "warning",
                            "badge_event": event,
                            "hvac_correlation": hvac_activation,
                            "lighting_correlation": lighting_activation,
                            "energy_impact": self._estimate_energy_impact(hvac_activation, lighting_activation),
                            "recommendation": self._generate_after_hours_recommendation(
                                event, hvac_activation, lighting_activation
                            ),
                            "detected_at": datetime.now(timezone.utc).isoformat(),
                        }
                        after_hours_events.append(anomaly)

        return after_hours_events

    def _simulate_hvac_activation(self, zone_id: str, event_time: datetime) -> Optional[Dict]:
        """Simulate HVAC zone activation for demo mode."""
        # Convert CCURE zone to HVAC zone ID
        hvac_zone_id = zone_id.replace("CCURE-ZN", "HVAC-ZN")

        # Return mock activation (replace with actual HVAC service query in production)
        return {
            "zone_id": hvac_zone_id,
            "activated_at": (event_time + timedelta(minutes=5)).isoformat(),
            "setpoint_before": 28,  # Unoccupied setpoint
            "setpoint_after": 22,  # Occupied setpoint
            "mode": "cooling",
        }

    def _simulate_lighting_activation(self, zone_id: str, event_time: datetime) -> Optional[Dict]:
        """Simulate lighting zone activation for demo mode."""
        # Convert CCURE zone to DALI zone ID
        lighting_zone_id = zone_id.replace("CCURE-ZN", "DALI-ZN")

        # Return mock activation (replace with actual lighting service query in production)
        return {
            "zone_id": lighting_zone_id,
            "activated_at": (event_time + timedelta(minutes=2)).isoformat(),
            "brightness_before": 0,  # Off
            "brightness_after": 100,  # Full brightness
            "occupancy_detected": True,
        }

    def _estimate_energy_impact(self, hvac_activation: Optional[Dict], lighting_activation: Optional[Dict]) -> str:
        """Estimate energy impact of after-hours activation."""
        total_kwh = 0

        if hvac_activation:
            # Estimate: 1 hour of HVAC = 2-5 kWh
            total_kwh += 3.5

        if lighting_activation:
            # Estimate: 1 hour of lighting = 0.5-1 kWh
            total_kwh += 0.75

        return f"Estimated {total_kwh:.1f} kWh excess consumption per hour"

    def _generate_after_hours_recommendation(
        self,
        badge_event: Dict,
        hvac_activation: Optional[Dict],
        lighting_activation: Optional[Dict],
    ) -> str:
        """Generate recommendation for after-hours anomaly."""
        person_name = badge_event.get("person_name", "Unknown")

        actions = []
        if hvac_activation:
            actions.append("reduce HVAC setpoint to +2°C unoccupied mode")
        if lighting_activation:
            actions.append("dim lights to 50% if low occupancy")

        return (
            f"After-hours access by {person_name}. "
            f"Consider: {', '.join(actions)} to save energy. "
            f"Verify access was authorized."
        )

    def detect_security_equipment_health_issues(self) -> List[Dict]:
        """Detect controller offline + network/UPS correlation.

        Priority 2: Security equipment health monitoring

        Returns:
            List of health issue dicts with:
            - type: "controller_offline"
            - controller: Controller details
            - network_status: Network switch status
            - ups_status: UPS battery level
            - recommendation: Action for operator
        """
        from app.services.ccure import CCureAdapter

        health_issues = []

        # Create CCure adapter in demo mode
        adapter = CCureAdapter(demo_mode=True)

        # Get controllers from C•CURE
        import asyncio

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        controllers = loop.run_until_complete(adapter.get_controllers())

        for controller in controllers:
            if controller.status == "offline":
                # Correlate with network health
                network_status = self._simulate_network_health(controller.ip_address)

                # Correlate with UPS status
                ups_status = self._simulate_ups_health()

                issue = {
                    "type": "controller_offline",
                    "severity": "critical",
                    "controller": controller.model_dump(),
                    "network_status": network_status,
                    "ups_status": ups_status,
                    "recommendation": self._generate_equipment_health_recommendation(
                        controller.model_dump(), network_status, ups_status
                    ),
                    "detected_at": datetime.now(timezone.utc).isoformat(),
                }
                health_issues.append(issue)

        return health_issues

    def _simulate_network_health(self, ip_address: str) -> Dict:
        """Simulate network switch health for controller IP."""
        # For demo: Return mock status
        return {
            "switch": "SW-01",
            "port": "GigabitEthernet1/0/24",
            "status": "down",
            "last_seen": "2026-02-10T03:20:00Z",
            "errors": 0,
        }

    def _simulate_ups_health(self) -> Dict:
        """Simulate UPS battery level and status."""
        # For demo: Return mock status
        return {
            "ups_id": "UPS-COMMS-01",
            "battery_level": 95,
            "status": "online",
            "estimated_runtime_minutes": 45,
        }

    def _generate_equipment_health_recommendation(
        self, controller: Dict, network_status: Dict, ups_status: Dict
    ) -> str:
        """Generate recommendation for equipment health issue."""
        controller_name = controller.get("name", "Unknown")

        if network_status.get("status") == "down":
            return (
                f"Controller {controller_name} offline due to network issue. "
                f"Check switch {network_status.get('switch')} port {network_status.get('port')}. "
                f"UPS battery at {ups_status.get('battery_level')}% - system stable."
            )
        else:
            return (
                f"Controller {controller_name} offline despite network OK. "
                f"Check controller power supply, enclosure tamper status, or firmware fault. "
                f"May require technician dispatch."
            )


def get_security_occupancy_service() -> SecurityOccupancyService:
    """Get or create singleton SecurityOccupancyService."""
    global _instance
    if _instance is None:
        _instance = SecurityOccupancyService()
    return _instance
