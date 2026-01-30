"""
DALI Lighting Service
=====================
Mock BACnet polling for Tridonic Scenecom controllers.
Simulates tiered polling architecture for demo.
"""

from typing import Dict, List, Optional
from datetime import datetime
import json
import logging
import random
from pathlib import Path

logger = logging.getLogger(__name__)

from app.models.dali import (
    DALIController, DALISensor, DALILuminaire,
    ZoneOccupancy, ZoneLighting, FloorSummary
)


class DALIService:
    """Service for DALI lighting system data access."""

    def __init__(self):
        self._controllers: Dict[str, DALIController] = {}
        self._sensors: Dict[str, DALISensor] = {}
        self._luminaires: Dict[str, DALILuminaire] = {}
        self._zones: Dict[str, dict] = {}
        self._load_mock_data()

    def _load_mock_data(self):
        """Load mock DALI data from JSON."""
        data_path = Path(__file__).parent.parent / "data" / "dali_mock_data.json"
        if data_path.exists():
            with open(data_path) as f:
                data = json.load(f)
                # Parse into models
                for c in data.get("controllers", []):
                    self._controllers[c["controller_id"]] = DALIController(**c)
                for s in data.get("sensors", []):
                    self._sensors[s["sensor_id"]] = DALISensor(**s)
                for l in data.get("luminaires", []):
                    self._luminaires[l["luminaire_id"]] = DALILuminaire(**l)
                for z in data.get("zones", []):
                    self._zones[z["zone_id"]] = z
            logger.info(f"Loaded DALI data: {len(self._controllers)} controllers, "
                       f"{len(self._sensors)} sensors, {len(self._luminaires)} luminaires")
        else:
            logger.warning(f"DALI mock data not found at {data_path}")

    # === Controller Operations ===

    def get_controllers(self, site_id: Optional[str] = None) -> List[DALIController]:
        """Get all controllers, optionally filtered by site."""
        controllers = list(self._controllers.values())
        if site_id:
            controllers = [c for c in controllers if c.site_id == site_id]
        return controllers

    def get_controller(self, controller_id: str) -> Optional[DALIController]:
        """Get single controller by ID."""
        return self._controllers.get(controller_id)

    # === Sensor Operations ===

    def get_sensors(self, zone_id: Optional[str] = None,
                    controller_id: Optional[str] = None) -> List[DALISensor]:
        """Get sensors with optional filters."""
        sensors = list(self._sensors.values())
        if zone_id:
            sensors = [s for s in sensors if s.zone_id == zone_id]
        if controller_id:
            sensors = [s for s in sensors if s.controller_id == controller_id]
        return sensors

    def get_sensor(self, sensor_id: str) -> Optional[DALISensor]:
        """Get single sensor by ID."""
        return self._sensors.get(sensor_id)

    def get_sensor_by_desk(self, desk_id: str) -> Optional[DALISensor]:
        """Get sensor associated with a desk (for complaint handling)."""
        for sensor in self._sensors.values():
            if sensor.desk_id == desk_id:
                return sensor
        return None

    # === Luminaire Operations ===

    def get_luminaires(self, zone_id: Optional[str] = None,
                       faulty_only: bool = False) -> List[DALILuminaire]:
        """Get luminaires with optional filters."""
        luminaires = list(self._luminaires.values())
        if zone_id:
            luminaires = [l for l in luminaires if l.zone_id == zone_id]
        if faulty_only:
            luminaires = [l for l in luminaires if l.fault_status]
        return luminaires

    def get_luminaire(self, luminaire_id: str) -> Optional[DALILuminaire]:
        """Get single luminaire by ID."""
        return self._luminaires.get(luminaire_id)

    # === Zone Aggregations ===

    def get_zone_occupancy(self, zone_id: str) -> Optional[ZoneOccupancy]:
        """Get occupancy summary for a zone."""
        zone = self._zones.get(zone_id)
        if not zone:
            return None

        sensors = self.get_sensors(zone_id=zone_id)
        if not sensors:
            return None

        occupied = [s for s in sensors if s.occupancy]
        lux_values = [s.lux_level for s in sensors if s.has_daylight and s.lux_level > 0]

        return ZoneOccupancy(
            zone_id=zone_id,
            zone_name=zone.get("name", zone_id),
            total_sensors=len(sensors),
            occupied_sensors=len(occupied),
            occupancy_percent=round(len(occupied) / len(sensors) * 100, 1) if sensors else 0,
            avg_lux_level=round(sum(lux_values) / len(lux_values), 1) if lux_values else 0,
            max_lux_level=max(lux_values) if lux_values else 0
        )

    def get_zone_lighting(self, zone_id: str) -> Optional[ZoneLighting]:
        """Get lighting summary for a zone."""
        zone = self._zones.get(zone_id)
        if not zone:
            return None

        luminaires = self.get_luminaires(zone_id=zone_id)
        if not luminaires:
            return None

        active = [l for l in luminaires if l.current_level > 0]
        faulty = [l for l in luminaires if l.fault_status]

        return ZoneLighting(
            zone_id=zone_id,
            zone_name=zone.get("name", zone_id),
            total_luminaires=len(luminaires),
            active_luminaires=len(active),
            avg_dim_level=round(sum(l.current_level for l in luminaires) / len(luminaires), 1),
            total_power_w=sum(l.power_consumption for l in luminaires),
            faulty_count=len(faulty)
        )

    def get_zone_summary(self, zone_id: str) -> Dict:
        """Get combined occupancy + lighting for a zone."""
        occupancy = self.get_zone_occupancy(zone_id)
        lighting = self.get_zone_lighting(zone_id)
        return {
            "occupancy": occupancy.to_dict() if occupancy else None,
            "lighting": lighting.to_dict() if lighting else None
        }

    # === Floor Aggregations ===

    def get_floor_summary(self, floor: str) -> FloorSummary:
        """Get occupancy summary for entire floor."""
        floor_zones = [z for z in self._zones.values() if z.get("floor") == floor]
        zone_occupancies = []
        total_power = 0.0

        for zone in floor_zones:
            occ = self.get_zone_occupancy(zone["zone_id"])
            if occ:
                zone_occupancies.append(occ)
            lighting = self.get_zone_lighting(zone["zone_id"])
            if lighting:
                total_power += lighting.total_power_w

        total_sensors = sum(z.total_sensors for z in zone_occupancies)
        total_occupied = sum(z.occupied_sensors for z in zone_occupancies)

        return FloorSummary(
            floor=floor,
            zones=zone_occupancies,
            total_occupancy_percent=round(total_occupied / total_sensors * 100, 1) if total_sensors else 0,
            total_power_kw=round(total_power / 1000, 2)
        )

    def get_building_occupancy(self) -> Dict:
        """Get occupancy overview for entire building."""
        floors = set(z.get("floor") for z in self._zones.values() if z.get("floor"))
        floor_summaries = [self.get_floor_summary(f) for f in sorted(floors)]

        total_sensors = sum(len(self.get_sensors(zone_id=z["zone_id"]))
                           for z in self._zones.values())
        total_occupied = sum(1 for s in self._sensors.values() if s.occupancy)

        return {
            "floors": [f.to_dict() for f in floor_summaries],
            "total_sensors": total_sensors,
            "total_occupied": total_occupied,
            "overall_occupancy_percent": round(total_occupied / total_sensors * 100, 1) if total_sensors else 0,
            "timestamp": datetime.now().isoformat()
        }

    # === All Zones ===

    def get_all_zones(self) -> List[dict]:
        """Get all zones with basic info."""
        return list(self._zones.values())

    # === Simulation (for demo) ===

    def simulate_occupancy_change(self):
        """Simulate realistic occupancy changes for demo."""
        for sensor in self._sensors.values():
            # 10% chance of occupancy change
            if random.random() < 0.1:
                sensor.occupancy = not sensor.occupancy
            # Slight lux variation
            if sensor.has_daylight:
                sensor.lux_level = max(0, min(2000,
                    sensor.lux_level + random.uniform(-50, 50)))
            sensor.last_updated = datetime.now().isoformat()


# Singleton instance
_dali_service: Optional[DALIService] = None


def get_dali_service() -> DALIService:
    """Get the singleton DALI service instance."""
    global _dali_service
    if _dali_service is None:
        _dali_service = DALIService()
    return _dali_service
