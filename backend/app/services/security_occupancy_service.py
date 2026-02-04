"""Security occupancy coordination service.

Calculates per-zone occupancy from badge events (entries - exits),
provides building-wide and floor-level occupancy aggregation, and
generates cross-module recommendations for HVAC and Lighting adjustments
based on zone occupancy levels.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.database.repositories.security_repository import get_security_repository
from app.models.security import EventDirection, OccupancySource, SecurityOccupancy

logger = logging.getLogger(__name__)

_instance: Optional["SecurityOccupancyService"] = None

# Thresholds for cross-module recommendations
OCCUPANCY_EMPTY_THRESHOLD = 0  # 0 people = empty zone
OCCUPANCY_LOW_THRESHOLD = 3    # Below this, zone considered low-occupancy
HVAC_RELAXATION_OFFSET = 2.0   # Degrees to relax setpoint for empty zones
LIGHTING_DIM_LEVEL = 20        # % brightness for empty zones
LIGHTING_LOW_LEVEL = 50        # % brightness for low-occupancy zones


class SecurityOccupancyService:
    """Service for occupancy tracking and cross-module coordination."""

    def __init__(self):
        self._repo = get_security_repository()

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
            "building_id": "site-002",
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

    # --- Cross-module coordination ---

    def check_hvac_adjustment(self, zone_id: str) -> Optional[Dict[str, Any]]:
        """Check if HVAC setpoint should be relaxed based on occupancy.

        If occupancy is below threshold, recommend setpoint relaxation
        to save energy.
        """
        occ = self._calculate_zone_occupancy(zone_id)
        count = occ["occupancy_count"]
        zone_name = occ["zone_name"]

        if count <= OCCUPANCY_EMPTY_THRESHOLD:
            return {
                "zone_id": zone_id,
                "zone_name": zone_name,
                "occupancy": count,
                "recommendation": "relax_setpoint",
                "detail": f"Zone {zone_name} is empty. Recommend relaxing cooling setpoint by +{HVAC_RELAXATION_OFFSET}°C to save energy.",
                "setpoint_offset": HVAC_RELAXATION_OFFSET,
                "reason": "Zone unoccupied based on badge data",
                "module": "hvac",
            }
        elif count <= OCCUPANCY_LOW_THRESHOLD:
            offset = HVAC_RELAXATION_OFFSET / 2
            return {
                "zone_id": zone_id,
                "zone_name": zone_name,
                "occupancy": count,
                "recommendation": "partial_relax",
                "detail": f"Zone {zone_name} has low occupancy ({count} people). Recommend relaxing cooling setpoint by +{offset}°C.",
                "setpoint_offset": offset,
                "reason": f"Low occupancy ({count} people)",
                "module": "hvac",
            }
        return None

    def check_lighting_adjustment(self, zone_id: str) -> Optional[Dict[str, Any]]:
        """Check if lighting should be dimmed based on occupancy.

        If zone is empty, recommend dimming to 20%.
        If zone has low occupancy, recommend 50%.
        """
        occ = self._calculate_zone_occupancy(zone_id)
        count = occ["occupancy_count"]
        zone_name = occ["zone_name"]

        if count <= OCCUPANCY_EMPTY_THRESHOLD:
            return {
                "zone_id": zone_id,
                "zone_name": zone_name,
                "occupancy": count,
                "recommendation": "dim_to_minimum",
                "detail": f"Zone {zone_name} is empty. Recommend dimming lights to {LIGHTING_DIM_LEVEL}%.",
                "brightness_level": LIGHTING_DIM_LEVEL,
                "reason": "Zone unoccupied based on badge data",
                "module": "lighting",
            }
        elif count <= OCCUPANCY_LOW_THRESHOLD:
            return {
                "zone_id": zone_id,
                "zone_name": zone_name,
                "occupancy": count,
                "recommendation": "dim_partial",
                "detail": f"Zone {zone_name} has low occupancy ({count} people). Recommend dimming lights to {LIGHTING_LOW_LEVEL}%.",
                "brightness_level": LIGHTING_LOW_LEVEL,
                "reason": f"Low occupancy ({count} people)",
                "module": "lighting",
            }
        return None

    def get_all_recommendations(self) -> Dict[str, Any]:
        """Get cross-module recommendations for all zones."""
        zones = self._repo.get_zones()
        hvac_recommendations = []
        lighting_recommendations = []

        for zone in zones:
            zone_id = zone.get("zone_id", "")

            hvac_rec = self.check_hvac_adjustment(zone_id)
            if hvac_rec:
                hvac_recommendations.append(hvac_rec)

            lighting_rec = self.check_lighting_adjustment(zone_id)
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
            from app.services.dali_service import get_dali_service
            dali = get_dali_service()
            zones = dali.get_zones()
            if zones:
                return {
                    "zone_count": len(zones),
                    "source": "dali_pir",
                }
        except Exception:
            pass
        return None


def get_security_occupancy_service() -> SecurityOccupancyService:
    """Get or create singleton SecurityOccupancyService."""
    global _instance
    if _instance is None:
        _instance = SecurityOccupancyService()
    return _instance
