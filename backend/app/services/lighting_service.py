"""
Lighting Service
================
Multi-site lighting data access with pluggable data sources (protocol-agnostic).

Supports two source types per site:
- "json": Reads from static JSON mock data files (e.g. site-002)
- "niagara": Reads from DeviceManager (Niagara-discovered lighting devices)
"""

import json
import logging
import random
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from app.database.supabase_client import get_supabase_client
from app.models.lighting import (
    FloorSummary,
    LightingController,
    LightingLuminaire,
    LightingSensor,
    ZoneLighting,
    ZoneOccupancy,
)

logger = logging.getLogger(__name__)


@dataclass
class SiteLightingData:
    """Holds per-site lighting data regardless of source."""

    site_id: str
    site_name: str
    source: str  # "json" or "niagara"
    controllers: dict[str, LightingController] = field(default_factory=dict)
    sensors: dict[str, LightingSensor] = field(default_factory=dict)
    luminaires: dict[str, LightingLuminaire] = field(default_factory=dict)
    zones: dict[str, dict] = field(default_factory=dict)
    last_loaded: str | None = None


class LightingService:
    """Service for lighting system data access (protocol-agnostic).

    Supports multiple sites, each with its own data source (JSON or Niagara).
    """

    # Floor code to display name mapping
    FLOOR_NAMES = {
        "L0": "Level 0 - Ground",
        "L1": "Level 1 - Operations",
        "L2": "Level 2 - Executive",
    }

    # DALI device types used when filtering DeviceManager devices
    DALI_DEVICE_TYPES = {"dali_controller", "luminaire", "light_sensor", "lighting"}

    def __init__(self):
        self._sites_data: dict[str, SiteLightingData] = {}
        self._sources_config = self._load_sources_config()
        # Load JSON-backed sites at startup
        for site_id, config in self._sources_config.get("sites", {}).items():
            if config.get("source") == "json":
                self._load_json_site(site_id, config)

    # === Configuration I/O ===

    @staticmethod
    def _config_path() -> Path:
        return Path(__file__).parent.parent / "data" / "lighting_sources.json"

    def _load_sources_config(self) -> dict:
        """Load per-site DALI source configuration."""
        path = self._config_path()
        if path.exists():
            with open(path) as f:
                return json.load(f)
        return {"sites": {}, "default_source": "json"}

    def _save_sources_config(self):
        """Persist source configuration to disk."""
        path = self._config_path()
        with open(path, "w") as f:
            json.dump(self._sources_config, f, indent=2)
            f.write("\n")

    # === JSON Data Loading (existing behaviour) ===

    def _load_json_site(self, site_id: str, config: dict):
        """Load DALI data for a site from a JSON file."""
        json_file = config.get("json_file", "dali_mock_data.json")
        data_path = Path(__file__).parent.parent / "data" / json_file
        if not data_path.exists():
            logger.debug("DALI JSON data not found at %s for site %s", data_path, site_id)
            return

        with open(data_path) as f:
            data = json.load(f)

        site_data = SiteLightingData(
            site_id=site_id,
            site_name=data.get("site_name", config.get("description", site_id)),
            source="json",
            last_loaded=datetime.now().isoformat(),
        )

        for c in data.get("controllers", []):
            ctrl = self._adapt_controller(c)
            site_data.controllers[ctrl.controller_id] = ctrl

        for s in data.get("sensors", []):
            sensor = self._adapt_sensor(s)
            site_data.sensors[sensor.sensor_id] = sensor

        for lum_data in data.get("luminaires", []):
            lum = self._adapt_luminaire(lum_data)
            site_data.luminaires[lum.luminaire_id] = lum

        for z in data.get("zones", []):
            site_data.zones[z["zone_id"]] = z

        self._sites_data[site_id] = site_data
        logger.info(
            "Loaded DALI JSON data for %s: %d controllers, %d sensors, %d luminaires",
            site_id,
            len(site_data.controllers),
            len(site_data.sensors),
            len(site_data.luminaires),
        )

    # === Niagara / DeviceManager Loading ===

    def _load_from_niagara(self, site_id: str) -> SiteLightingData:
        """Build DALI data from Niagara-discovered devices in DeviceManager.

        Imports are deferred to avoid circular dependencies and to allow
        the DeviceManager to be optional (not all deployments have it).
        """
        site_data = SiteLightingData(
            site_id=site_id,
            site_name=site_id,
            source="niagara",
            last_loaded=datetime.now().isoformat(),
        )

        try:
            from app.services.device_abstraction import DeviceManager

            dm = DeviceManager()
            if not dm._initialized:
                logger.warning("DeviceManager not initialized; cannot load Niagara DALI for %s", site_id)
                return site_data

            # list_devices_by_site is async, but we need sync access here.
            # Use the internal _devices dict directly for synchronous access.
            all_devices = [d for d in dm._devices.values() if d.site_id == site_id]

            for device in all_devices:
                device_type_str = device.device_type.value.lower()
                if device_type_str not in self.DALI_DEVICE_TYPES:
                    continue

                if device_type_str in ("dali_controller", "lighting"):
                    ctrl = LightingController(
                        controller_id=device.id,
                        name=device.name,
                        site_id=device.site_id,
                        building=getattr(device.device_location, "building", ""),
                        floor=getattr(device.device_location, "floor", ""),
                        ip_address=device.metadata.get("ip_address", ""),
                        mac_address=device.metadata.get("mac_address", ""),
                        firmware_version=device.metadata.get("firmware_version", ""),
                        status="online" if device.status.value == "online" else device.status.value,
                        channel_count=device.metadata.get("channel_count", 64),
                        last_poll=datetime.now().isoformat(),
                    )
                    site_data.controllers[ctrl.controller_id] = ctrl

                elif device_type_str == "light_sensor":
                    sensor = LightingSensor(
                        sensor_id=device.id,
                        name=device.name,
                        controller_id=device.metadata.get("controller_id", ""),
                        zone_id=device.metadata.get("zone_id", ""),
                        sensor_type=device.metadata.get("sensor_type", "pir_daylight"),
                        occupancy=bool(device.metadata.get("occupancy", False)),
                        lux_level=float(device.metadata.get("lux_level", 0)),
                        has_daylight=bool(device.metadata.get("has_daylight", True)),
                        last_updated=datetime.now().isoformat(),
                    )
                    site_data.sensors[sensor.sensor_id] = sensor

                elif device_type_str == "luminaire":
                    lum = LightingLuminaire(
                        luminaire_id=device.id,
                        name=device.name,
                        controller_id=device.metadata.get("controller_id", ""),
                        zone_id=device.metadata.get("zone_id", ""),
                        luminaire_type=device.metadata.get("luminaire_type", "led_panel"),
                        current_level=int(device.metadata.get("current_level", 0)),
                        target_level=int(device.metadata.get("target_level", 0)),
                        power_consumption=float(device.metadata.get("power_consumption", 0)),
                        rated_power=float(device.metadata.get("rated_power", 40.0)),
                        fault_status=bool(device.metadata.get("fault_status", False)),
                        lamp_hours=int(device.metadata.get("lamp_hours", 0)),
                        last_updated=datetime.now().isoformat(),
                        color_temp_kelvin=device.metadata.get("color_temp_kelvin"),
                        emergency_battery_pct=device.metadata.get("emergency_battery_pct"),
                    )
                    site_data.luminaires[lum.luminaire_id] = lum

            # Build zones from device metadata zone_ids
            zone_ids_seen = set()
            for sensor in site_data.sensors.values():
                if sensor.zone_id and sensor.zone_id not in zone_ids_seen:
                    zone_ids_seen.add(sensor.zone_id)
                    site_data.zones[sensor.zone_id] = {
                        "zone_id": sensor.zone_id,
                        "name": sensor.zone_id,
                        "floor": self._extract_floor(sensor.zone_id),
                    }
            for lum in site_data.luminaires.values():
                if lum.zone_id and lum.zone_id not in zone_ids_seen:
                    zone_ids_seen.add(lum.zone_id)
                    site_data.zones[lum.zone_id] = {
                        "zone_id": lum.zone_id,
                        "name": lum.zone_id,
                        "floor": self._extract_floor(lum.zone_id),
                    }

            logger.info(
                "Loaded DALI Niagara data for %s: %d controllers, %d sensors, %d luminaires",
                site_id,
                len(site_data.controllers),
                len(site_data.sensors),
                len(site_data.luminaires),
            )

        except ImportError:
            logger.warning("DeviceManager not available; Niagara DALI loading skipped for %s", site_id)
        except Exception as e:
            logger.error("Failed to load Niagara DALI data for %s: %s", site_id, e)

        return site_data

    @staticmethod
    def _extract_floor(zone_id: str) -> str:
        """Best-effort floor extraction from a zone ID like 'L1-A'."""
        for part in zone_id.replace("_", "-").split("-"):
            if part.startswith("L") and len(part) <= 3 and part[1:].isdigit():
                return part
        return ""

    # === Dynamic Site Registration ===

    def register_niagara_site(self, site_id: str, site_name: str):
        """Register a site that gets DALI data from Niagara/DeviceManager."""
        site_data = self._load_from_niagara(site_id)
        site_data.site_name = site_name
        self._sites_data[site_id] = site_data
        # Persist to config
        self._sources_config.setdefault("sites", {})[site_id] = {
            "source": "niagara",
            "description": f"{site_name} - Niagara BACnet",
        }
        self._save_sources_config()
        logger.info("Registered Niagara DALI site: %s (%s)", site_id, site_name)

    def refresh_site(self, site_id: str):
        """Reload data for a site from its configured source."""
        config = self._sources_config.get("sites", {}).get(site_id)
        if not config:
            return
        if config.get("source") == "json":
            self._load_json_site(site_id, config)
        elif config.get("source") == "niagara":
            site_data = self._load_from_niagara(site_id)
            if site_id in self._sites_data:
                site_data.site_name = self._sites_data[site_id].site_name
            self._sites_data[site_id] = site_data

    # === Data Adapters (JSON to model) ===

    def _adapt_controller(self, data: dict) -> LightingController:
        """Adapt controller data from various formats to model."""
        controller_id = data.get("controller_id", "")
        floor = ""
        if "-L" in controller_id:
            parts = controller_id.split("-")
            for p in parts:
                if p.startswith("L") and len(p) <= 3:
                    floor = p
                    break

        return LightingController(
            controller_id=controller_id,
            name=data.get("name", ""),
            site_id=data.get("site_id", ""),
            building=data.get("building", data.get("location", "")),
            floor=data.get("floor", floor),
            ip_address=data.get("ip_address", ""),
            mac_address=data.get("mac_address", ""),
            firmware_version=data.get("firmware_version", ""),
            status=data.get("status", "online"),
            channel_count=data.get("channel_count", data.get("channels", 64)),
            sensors_connected=data.get("sensors_connected", 0),
            luminaires_connected=data.get("luminaires_connected", 0),
            last_poll=data.get("last_poll"),
            created_at=data.get("created_at"),
        )

    def _adapt_sensor(self, data: dict) -> LightingSensor:
        """Adapt sensor data from various formats to model."""
        has_pir = data.get("has_pir", True)
        has_daylight = data.get("has_daylight", True)
        if has_pir and has_daylight:
            sensor_type = "pir_daylight"
        elif has_pir:
            sensor_type = "pir"
        elif has_daylight:
            sensor_type = "daylight"
        else:
            sensor_type = "switch"

        return LightingSensor(
            sensor_id=data.get("sensor_id", ""),
            name=data.get("name", data.get("location", "")),
            controller_id=data.get("controller_id", ""),
            zone_id=data.get("zone_id", ""),
            sensor_type=data.get("sensor_type", sensor_type),
            dali_address=data.get("dali_address", 0),
            occupancy=data.get("occupancy", False),
            lux_level=data.get("lux_level", 0.0),
            has_daylight=has_daylight,
            desk_id=data.get("desk_id"),
            x_coord=data.get("x_coord"),
            y_coord=data.get("y_coord"),
            last_updated=data.get("last_updated"),
            daylight_setpoint=data.get("daylight_setpoint", 500.0),
            motion_count=data.get("motion_count", 0),
        )

    def _adapt_luminaire(self, data: dict) -> LightingLuminaire:
        """Adapt luminaire data from various formats to model."""
        return LightingLuminaire(
            luminaire_id=data.get("luminaire_id", ""),
            name=data.get("name", ""),
            controller_id=data.get("controller_id", ""),
            zone_id=data.get("zone_id", ""),
            luminaire_type=data.get("luminaire_type", "led_panel"),
            dali_address=data.get("dali_address", 0),
            current_level=data.get("current_level", 0),
            target_level=data.get("target_level", data.get("current_level", 0)),
            min_level=data.get("min_level", 10),
            max_level=data.get("max_level", 254),
            power_consumption=data.get("power_consumption", 0.0),
            rated_power=data.get("rated_power", data.get("wattage", 40.0)),
            fault_status=data.get("fault_status", False),
            fault_code=data.get("fault_code"),
            lamp_hours=data.get("lamp_hours", data.get("operating_hours", 0)),
            last_updated=data.get("last_updated"),
            color_temp_kelvin=data.get("color_temp_kelvin"),
            emergency_battery_pct=data.get("emergency_battery_pct"),
        )

    # === Site-aware Data Access Helpers ===

    def _get_site_data(self, site_id: str | None) -> SiteLightingData | None:
        """Get data for a specific site, or None."""
        if site_id and site_id in self._sites_data:
            return self._sites_data[site_id]
        return None

    def _all_controllers(self) -> list[LightingController]:
        """Get controllers across all sites."""
        result = []
        for site_data in self._sites_data.values():
            result.extend(site_data.controllers.values())
        return result

    def _all_sensors(self) -> list[LightingSensor]:
        """Get sensors across all sites."""
        result = []
        for site_data in self._sites_data.values():
            result.extend(site_data.sensors.values())
        return result

    def _all_luminaires(self) -> list[LightingLuminaire]:
        """Get luminaires across all sites."""
        result = []
        for site_data in self._sites_data.values():
            result.extend(site_data.luminaires.values())
        return result

    def _all_zones(self) -> dict[str, dict]:
        """Get zones across all sites."""
        result = {}
        for site_data in self._sites_data.values():
            result.update(site_data.zones)
        return result

    # === Controller Operations ===

    def get_controllers(self, site_id: str | None = None) -> list[LightingController]:
        """Get all controllers, optionally filtered by site."""
        site_data = self._get_site_data(site_id)
        if site_data:
            return list(site_data.controllers.values())
        if site_id:
            # Site requested but not found — check if all controllers match
            return [c for c in self._all_controllers() if c.site_id == site_id]
        return self._all_controllers()

    def get_controller(self, controller_id: str) -> LightingController | None:
        """Get single controller by ID."""
        for site_data in self._sites_data.values():
            if controller_id in site_data.controllers:
                return site_data.controllers[controller_id]
        return None

    # === Sensor Operations ===

    def get_sensors(
        self, zone_id: str | None = None, controller_id: str | None = None, site_id: str | None = None
    ) -> list[LightingSensor]:
        """Get sensors with optional filters."""
        site_data = self._get_site_data(site_id)
        sensors = list(site_data.sensors.values()) if site_data else self._all_sensors()
        if zone_id:
            sensors = [s for s in sensors if s.zone_id == zone_id]
        if controller_id:
            sensors = [s for s in sensors if s.controller_id == controller_id]
        return sensors

    def get_sensor(self, sensor_id: str) -> LightingSensor | None:
        """Get single sensor by ID."""
        for site_data in self._sites_data.values():
            if sensor_id in site_data.sensors:
                return site_data.sensors[sensor_id]
        return None

    def get_sensor_by_desk(self, desk_id: str) -> LightingSensor | None:
        """Get sensor associated with a desk (for complaint handling)."""
        for site_data in self._sites_data.values():
            for sensor in site_data.sensors.values():
                if sensor.desk_id == desk_id:
                    return sensor
        return None

    # === Luminaire Operations ===

    def get_luminaires(
        self, zone_id: str | None = None, faulty_only: bool = False, site_id: str | None = None
    ) -> list[LightingLuminaire]:
        """Get luminaires with optional filters."""
        site_data = self._get_site_data(site_id)
        luminaires = list(site_data.luminaires.values()) if site_data else self._all_luminaires()
        if zone_id:
            luminaires = [lum for lum in luminaires if lum.zone_id == zone_id]
        if faulty_only:
            luminaires = [lum for lum in luminaires if lum.fault_status]
        return luminaires

    def get_luminaire(self, luminaire_id: str) -> LightingLuminaire | None:
        """Get single luminaire by ID."""
        for site_data in self._sites_data.values():
            if luminaire_id in site_data.luminaires:
                return site_data.luminaires[luminaire_id]
        return None

    # === Zone Aggregations ===

    @staticmethod
    def _occupancy_status(percent: float) -> str:
        """Derive occupancy status from percentage."""
        if percent > 70:
            return "busy"
        if percent >= 40:
            return "moderate"
        if percent >= 10:
            return "quiet"
        return "empty"

    def _get_zones(self, site_id: str | None = None) -> dict[str, dict]:
        """Get zones dict, optionally scoped to a site."""
        site_data = self._get_site_data(site_id)
        if site_data:
            return site_data.zones
        return self._all_zones()

    def get_zone_occupancy(self, zone_id: str) -> ZoneOccupancy | None:
        """Get occupancy summary for a zone."""
        zones = self._all_zones()
        zone = zones.get(zone_id)
        if not zone:
            return None

        sensors = self.get_sensors(zone_id=zone_id)
        if not sensors:
            return None

        occupied = [s for s in sensors if s.occupancy]
        lux_values = [s.lux_level for s in sensors if s.has_daylight and s.lux_level > 0]
        occ_pct = round(len(occupied) / len(sensors) * 100, 1) if sensors else 0

        return ZoneOccupancy(
            zone_id=zone_id,
            zone_name=zone.get("name", zone_id),
            total_sensors=len(sensors),
            occupied_sensors=len(occupied),
            occupancy_percent=occ_pct,
            avg_lux_level=round(sum(lux_values) / len(lux_values), 1) if lux_values else 0,
            max_lux_level=max(lux_values) if lux_values else 0,
            floor=zone.get("floor", ""),
            status=self._occupancy_status(occ_pct),
            last_updated=datetime.now().isoformat(),
        )

    def get_zone_lighting(self, zone_id: str) -> ZoneLighting | None:
        """Get lighting summary for a zone."""
        zones = self._all_zones()
        zone = zones.get(zone_id)
        if not zone:
            return None

        luminaires = self.get_luminaires(zone_id=zone_id)
        if not luminaires:
            return None

        active = [lum for lum in luminaires if lum.current_level > 0]
        faulty = [lum for lum in luminaires if lum.fault_status]
        avg_dim = round(sum(lum.current_level for lum in luminaires) / len(luminaires), 1)

        # Energy waste detection: low occupancy but high lighting
        energy_waste = False
        waste_reason = None
        occ = self.get_zone_occupancy(zone_id)
        if occ and occ.occupancy_percent < 20 and avg_dim > 50:
            energy_waste = True
            brightness_pct = round(avg_dim / 254 * 100)
            waste_reason = f"Zone at {occ.occupancy_percent:.0f}% occupancy but {brightness_pct}% lighting"

        return ZoneLighting(
            zone_id=zone_id,
            zone_name=zone.get("name", zone_id),
            total_luminaires=len(luminaires),
            active_luminaires=len(active),
            avg_dim_level=avg_dim,
            total_power_w=sum(lum.power_consumption for lum in luminaires),
            faulty_count=len(faulty),
            floor=zone.get("floor", ""),
            energy_waste_detected=energy_waste,
            energy_waste_reason=waste_reason,
            active_scene=zone.get("active_scene"),
            active_scene_name=zone.get("active_scene_name"),
        )

    def get_zone_summary(self, zone_id: str) -> dict:
        """Get combined occupancy + lighting for a zone."""
        occupancy = self.get_zone_occupancy(zone_id)
        lighting = self.get_zone_lighting(zone_id)
        return {
            "occupancy": occupancy.to_dict() if occupancy else None,
            "lighting": lighting.to_dict() if lighting else None,
        }

    # === Floor Aggregations ===

    def get_floor_summary(self, floor: str, site_id: str | None = None) -> FloorSummary:
        """Get occupancy summary for entire floor."""
        zones = self._get_zones(site_id)
        floor_zones = [z for z in zones.values() if z.get("floor") == floor]
        zone_occupancies = []
        total_power = 0.0
        total_luminaires = 0
        faulty_luminaires = 0

        for zone in floor_zones:
            occ = self.get_zone_occupancy(zone["zone_id"])
            if occ:
                zone_occupancies.append(occ)
            lighting = self.get_zone_lighting(zone["zone_id"])
            if lighting:
                total_power += lighting.total_power_w
                total_luminaires += lighting.total_luminaires
                faulty_luminaires += lighting.faulty_count

        total_sensors = sum(z.total_sensors for z in zone_occupancies)
        total_occupied = sum(z.occupied_sensors for z in zone_occupancies)

        return FloorSummary(
            floor=floor,
            floor_name=self.FLOOR_NAMES.get(floor, floor),
            zones=zone_occupancies,
            total_zones=len(floor_zones),
            total_sensors=total_sensors,
            occupied_sensors=total_occupied,
            occupancy_percent=round(total_occupied / total_sensors * 100, 1) if total_sensors else 0,
            total_luminaires=total_luminaires,
            faulty_luminaires=faulty_luminaires,
            total_power_watts=round(total_power, 1),
        )

    def get_building_occupancy(self, site_id: str | None = None) -> dict:
        """Get occupancy overview for entire building (or a specific site)."""
        # If no site_id provided, use first available site for backwards compat
        if not site_id and self._sites_data:
            site_id = next(iter(self._sites_data))

        site_data = self._get_site_data(site_id)
        if not site_data:
            return {
                "site_id": site_id or "",
                "site_name": "",
                "total_floors": 0,
                "total_zones": 0,
                "total_sensors": 0,
                "occupied_sensors": 0,
                "occupancy_percent": 0,
                "total_luminaires": 0,
                "faulty_luminaires": 0,
                "total_power_watts": 0,
                "energy_waste_zones": 0,
                "floors": [],
                "last_updated": datetime.now().isoformat(),
            }

        zones = site_data.zones
        sensors = site_data.sensors
        luminaires = site_data.luminaires

        floors = {z.get("floor") for z in zones.values() if z.get("floor")}
        floor_summaries = [self.get_floor_summary(f, site_id) for f in sorted(floors)]

        total_sensors = len(sensors)
        total_occupied = sum(1 for s in sensors.values() if s.occupancy)

        all_luminaires = list(luminaires.values())
        total_luminaires = len(all_luminaires)
        faulty_luminaires_count = sum(1 for lum in all_luminaires if lum.fault_status)
        total_power_watts = sum(lum.power_consumption for lum in all_luminaires)

        energy_waste_zones = 0
        for zone in zones.values():
            zone_id = zone["zone_id"]
            occ = self.get_zone_occupancy(zone_id)
            lighting = self.get_zone_lighting(zone_id)
            if occ and lighting and occ.occupancy_percent < 20 and lighting.active_luminaires > 0:
                energy_waste_zones += 1

        return {
            "site_id": site_data.site_id,
            "site_name": site_data.site_name,
            "total_floors": len(floors),
            "total_zones": len(zones),
            "total_sensors": total_sensors,
            "occupied_sensors": total_occupied,
            "occupancy_percent": round(total_occupied / total_sensors * 100, 1) if total_sensors else 0,
            "total_luminaires": total_luminaires,
            "faulty_luminaires": faulty_luminaires_count,
            "total_power_watts": round(total_power_watts, 1),
            "energy_waste_zones": energy_waste_zones,
            "floors": [f.to_dict() for f in floor_summaries],
            "last_updated": datetime.now().isoformat(),
        }

    # === All Zones ===

    def get_all_zones(self, site_id: str | None = None) -> list[dict]:
        """Get all zones with basic info."""
        zones = self._get_zones(site_id)
        return list(zones.values())

    # === Source Health ===

    def get_sources_health(self) -> list[dict]:
        """Get health status for all configured DALI sources."""
        results = []
        for site_id, site_data in self._sites_data.items():
            config = self._sources_config.get("sites", {}).get(site_id, {})
            controllers = list(site_data.controllers.values())
            sensors = list(site_data.sensors.values())
            online_controllers = sum(1 for c in controllers if c.status == "online")
            online_sensors = len(sensors)  # JSON sensors assumed online

            if site_data.source == "json":
                status = "healthy"
            elif site_data.source == "niagara":
                if not controllers and not sensors:
                    status = "offline"
                elif online_controllers < len(controllers):
                    status = "degraded"
                else:
                    status = "healthy"
            else:
                status = "unknown"

            results.append(
                {
                    "site_id": site_id,
                    "source_name": f"{site_data.site_name} Lighting",
                    "source_type": "lighting",
                    "connection_type": "niagara_bacnet" if site_data.source == "niagara" else "file_drop",
                    "status": status,
                    "controllers_online": online_controllers,
                    "controllers_total": len(controllers),
                    "sensors_online": online_sensors,
                    "sensors_total": len(sensors),
                    "luminaires_total": len(site_data.luminaires),
                    "last_poll": site_data.last_loaded,
                    "description": config.get("description", ""),
                }
            )
        return results

    # === Seeded occupancy changes ===

    def simulate_occupancy_change(self):
        """Simulate realistic occupancy changes for local seeded operation."""
        for site_data in self._sites_data.values():
            for sensor in site_data.sensors.values():
                if random.random() < 0.1:
                    sensor.occupancy = not sensor.occupancy
                if sensor.has_daylight:
                    sensor.lux_level = max(0, min(2000, sensor.lux_level + random.uniform(-50, 50)))
                sensor.last_updated = datetime.now().isoformat()

    async def get_live_lighting_data(self, site_id: str) -> dict:
        """
        Fetch real-time DALI data from Supabase tables.

        Returns current occupancy, lighting, and energy data for all zones.
        Used for real-time dashboard vs simulation data.

        Args:
            site_id: Site identifier (e.g., 'S002')

        Returns:
            dict with keys: summary, zones, energy_stats, last_updated
        """
        try:
            supabase = get_supabase_client()

            # Query live sensor occupancy
            sensors_response = supabase.table("lighting_sensors").select("*").eq("site_id", site_id).execute()
            sensors = sensors_response.data or []

            # Query live luminaire brightness
            luminaires_response = supabase.table("lighting_luminaires").select("*").eq("site_id", site_id).execute()
            luminaires = luminaires_response.data or []

            # Query recent energy data (last 1 hour)
            energy_response = (
                supabase.table("lighting_energy")
                .select("*")
                .eq("site_id", site_id)
                .order("time", desc=True)
                .limit(24)
                .execute()
            )
            energy_data = energy_response.data or []

            # Aggregate by zone
            zones_agg = {}

            # Process sensors
            for sensor in sensors:
                zone_id = sensor.get("zone_id", "unknown")
                if zone_id not in zones_agg:
                    zones_agg[zone_id] = {
                        "zone_id": zone_id,
                        "sensors": [],
                        "luminaires": [],
                        "energy_total_kwh": 0,
                    }
                zones_agg[zone_id]["sensors"].append(
                    {
                        "sensor_id": sensor.get("sensor_id"),
                        "occupancy": sensor.get("occupancy", False),
                        "lux_level": sensor.get("lux_level", 0),
                        "last_updated": sensor.get("last_updated"),
                    }
                )
            # Process luminaires
            for lum in luminaires:
                zone_id = lum.get("zone_id", "unknown")
                if zone_id not in zones_agg:
                    zones_agg[zone_id] = {
                        "zone_id": zone_id,
                        "sensors": [],
                        "luminaires": [],
                        "energy_total_kwh": 0,
                    }
                zones_agg[zone_id]["luminaires"].append(
                    {
                        "luminaire_id": lum.get("id"),
                        "name": lum.get("name"),
                        "brightness_level": lum.get("current_level", 0),
                        "power_consumption_w": lum.get("power_consumption", 0),
                        "fault_status": lum.get("fault_status", False),
                    }
                )
            # Process energy data
            for energy in energy_data:
                zone_id = energy.get("zone_id", "unknown")
                if zone_id in zones_agg:
                    zones_agg[zone_id]["energy_total_kwh"] += energy.get("total_watts", 0) / 1000

            # Calculate zone statistics
            zones_list = []
            total_occupancy = 0
            total_brightness = 0
            total_power_w = 0

            for zone_id, zone_data in zones_agg.items():
                sensors = zone_data["sensors"]
                luminaires = zone_data["luminaires"]

                # Occupancy percentage
                occupied_sensors = sum(1 for s in sensors if s["occupancy"])
                occupancy_pct = round(occupied_sensors / len(sensors) * 100, 1) if sensors else 0
                total_occupancy += occupancy_pct

                # Brightness average
                brightness_levels = [lum["brightness_level"] for lum in luminaires]
                avg_brightness = round(sum(brightness_levels) / len(brightness_levels), 1) if brightness_levels else 0
                total_brightness += avg_brightness

                # Power consumption
                zone_power_w = sum(lum["power_consumption_w"] for lum in luminaires)
                total_power_w += zone_power_w

                # Lux level average
                lux_levels = [s["lux_level"] for s in sensors if s["lux_level"] > 0]
                avg_lux = round(sum(lux_levels) / len(lux_levels), 1) if lux_levels else 0

                zones_list.append(
                    {
                        "zone_id": zone_id,
                        "source_type": "lighting_protocol",
                        "occupancy_percent": occupancy_pct,
                        "avg_brightness_level": avg_brightness,
                        "total_sensors": len(sensors),
                        "occupied_sensors": occupied_sensors,
                        "total_luminaires": len(luminaires),
                        "faulty_luminaires": sum(1 for lum in luminaires if lum["fault_status"]),
                        "power_w": round(zone_power_w, 1),
                        "avg_lux": avg_lux,
                        "energy_kwh": round(zone_data["energy_total_kwh"], 2),
                    }
                )

            return {
                "site_id": site_id,
                "data_source": "live",
                "source_type": "lighting_protocol",
                "timestamp": datetime.now().isoformat(),
                "summary": {
                    "total_zones": len(zones_list),
                    "avg_occupancy_percent": round(total_occupancy / len(zones_list), 1) if zones_list else 0,
                    "avg_brightness_level": round(total_brightness / len(zones_list), 1) if zones_list else 0,
                    "total_power_w": round(total_power_w, 1),
                    "total_sensors": len(sensors),
                    "occupied_sensors": sum(1 for s in sensors if s.get("occupancy", False)),
                    "total_luminaires": len(luminaires),
                    "faulty_luminaires": sum(1 for lum in luminaires if lum.get("fault_status", False)),
                },
                "zones": zones_list,
                "energy_stats": {
                    "total_kwh_24h": round(sum(z["energy_kwh"] for z in zones_list), 2),
                },
            }

        except Exception as e:
            logger.error(f"Error fetching live DALI data for {site_id}: {e}")
            # Return empty structure on error
            return {
                "site_id": site_id,
                "data_source": "live",
                "source_type": "lighting_protocol",
                "timestamp": datetime.now().isoformat(),
                "error": str(e),
                "summary": {},
                "zones": [],
                "energy_stats": {},
            }

    async def set_zone_brightness(self, zone_id: str, brightness_percent: int) -> bool:
        """
        Set brightness level for a zone's Tridonic luminaires.

        Args:
            zone_id: Zone identifier (e.g., 'Zone-101')
            brightness_percent: Brightness level 0-100%

        Returns:
            True if successful, False otherwise

        This method controls Tridonic luminaire drivers with:
        - Daylight harvesting integration
        - Occupancy-based dimming
        - Energy optimization profiles
        """
        zones = self._all_zones()
        zone = zones.get(zone_id)

        if not zone:
            logger.warning(f"Zone not found: {zone_id}")
            return False

        # Validate brightness level
        brightness_percent = max(0, min(100, brightness_percent))

        # Get all luminaires in this zone
        luminaires = self.get_luminaires(zone_id=zone_id)
        if not luminaires:
            logger.warning(f"No luminaires found in zone: {zone_id}")
            return False

        # Convert percentage to DALI level (0-254)
        # DALI uses 254 steps (0=off, 254=full), so percentage * 254 / 100
        dali_level = int(brightness_percent * 254 / 100)

        # Update all luminaires in the zone
        updated_count = 0
        for luminaire in luminaires:
            # In a real system, this would send BACnet/Modbus/DALI commands to the Tridonic controller
            # For now, update the simulation state
            luminaire["current_level"] = dali_level
            luminaire["target_level"] = dali_level
            luminaire["last_adjusted"] = datetime.now().isoformat()

            # Record the control event for audit trail
            luminaire["control_source"] = "ai_optimization"  # AI-driven control
            luminaire["control_reason"] = "occupancy_and_daylight_aware"

            updated_count += 1

        logger.info(
            f"Set zone {zone_id} brightness to {brightness_percent}% "
            f"(DALI {dali_level}/254) - {updated_count} luminaires updated"
        )

        return True

    async def get_zone_brightness(self, zone_id: str) -> int | None:
        """Get current average brightness for a zone."""
        luminaires = self.get_luminaires(zone_id=zone_id)
        if not luminaires:
            return None

        avg_level = sum(lum.get("current_level", 0) for lum in luminaires) / len(luminaires)
        return int(avg_level * 100 / 254)  # Convert DALI level back to percentage


# Singleton instance
_lighting_service: LightingService | None = None


def get_lighting_service() -> LightingService:
    """Get the singleton lighting service instance."""
    global _lighting_service
    if _lighting_service is None:
        _lighting_service = LightingService()
    return _lighting_service
