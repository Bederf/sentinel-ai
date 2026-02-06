"""Solar Ingestion Service — manages manufacturer connectors and normalised reads.

Singleton service that orchestrates polling across heterogeneous solar/BESS
installations.  Each site can have multiple connectors (one per manufacturer).
All data is normalised into protocol-agnostic models before being served
to the API layer.

Pattern follows energy_centre_service.py.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from app.models.solar import (
    SolarPlant,
    SolarInverter,
    SolarString,
    BESSContainer,
    GridMeter,
    NormalisedReading,
    ConnectorStatus,
    QualityFlag,
)
from app.services.solar_connector_base import SolarConnector
from app.services.solar_connector_huawei import SimulatedHuaweiConnector
from app.services.solar_connector_schneider import SimulatedSchneiderConnector

logger = logging.getLogger(__name__)


class SiteRegistration:
    """Holds all connectors and config for a single solar site."""

    def __init__(self, site_id: str, site_name: str, config: Dict):
        self.site_id = site_id
        self.site_name = site_name
        self.config = config
        self.connectors: Dict[str, SolarConnector] = {}
        self.plants: Dict[str, SolarPlant] = {}
        self.last_poll: Optional[str] = None


class SolarIngestionService:
    """Manages solar/BESS data ingestion across multiple sites.

    Responsibilities:
      - Load site configs from JSON (auto-registers Fairlands on startup)
      - Instantiate per-manufacturer connectors (simulated for demo)
      - Poll all connectors and aggregate normalised readings
      - Quality-flag management: fresh (<30s) = good, >60s = stale
      - Serve site overviews, inverter details, BESS status, meter data
    """

    def __init__(self):
        self._sites: Dict[str, SiteRegistration] = {}
        self._load_site_configs()

    # === Site management ===

    def _load_site_configs(self):
        """Auto-load site configurations from data/solar/ directory."""
        solar_data_dir = Path(__file__).parent.parent / "data" / "solar"
        if not solar_data_dir.exists():
            logger.warning(f"Solar data directory not found: {solar_data_dir}")
            return

        config_files = list(solar_data_dir.glob("*_config.json"))
        for config_path in config_files:
            try:
                with open(config_path) as f:
                    config = json.load(f)
                site_id = config.get("site_id", config_path.stem.replace("_config", ""))
                self.register_site(site_id, config)
                logger.info(f"Auto-loaded solar site: {site_id} from {config_path.name}")
            except Exception as e:
                logger.error(f"Failed to load solar config {config_path}: {e}")

    def register_site(self, site_id: str, config: Dict) -> None:
        """Register a solar site and instantiate its connectors."""
        site_name = config.get("site_name", site_id)
        reg = SiteRegistration(site_id, site_name, config)

        # Build plant inventory
        for plant_cfg in config.get("plants", []):
            plant = SolarPlant(
                plant_id=plant_cfg["plant_id"],
                name=plant_cfg["name"],
                site_id=site_id,
                capacity_kwp=plant_cfg.get("capacity_kwp", 0),
                panel_count=plant_cfg.get("panel_count", 0),
                inverter_count=len(plant_cfg.get("inverters", [])),
                panel_model=plant_cfg.get("panel_model", ""),
                panel_rating_w=plant_cfg.get("panel_rating_w", 0),
                commissioning_date=plant_cfg.get("commissioning_date"),
                latitude=config.get("latitude", -26.2),
                longitude=config.get("longitude", 28.0),
                orientation=plant_cfg.get("orientation", 0),
                tilt=plant_cfg.get("tilt", 20),
            )
            reg.plants[plant.plant_id] = plant

            # Group inverters by manufacturer and create connectors
            manufacturers: Dict[str, List[Dict]] = {}
            for inv_cfg in plant_cfg.get("inverters", []):
                inv_cfg["plant_id"] = plant.plant_id
                inv_cfg["site_id"] = site_id
                inv_cfg["panel_model"] = plant_cfg.get("panel_model", "")
                inv_cfg["panel_rating_w"] = plant_cfg.get("panel_rating_w", 0)
                mfr = inv_cfg.get("manufacturer", "unknown").lower()
                manufacturers.setdefault(mfr, []).append(inv_cfg)

            for mfr, inv_list in manufacturers.items():
                connector_key = f"{plant.plant_id}_{mfr}"
                connector = self._create_connector(mfr, inv_list, config)
                if connector:
                    reg.connectors[connector_key] = connector

        # BESS connector (usually Huawei for Fairlands)
        bess_cfg = config.get("bess")
        if bess_cfg:
            bess_cfg["site_id"] = site_id
            mfr = bess_cfg.get("manufacturer", "huawei").lower()
            bess_key = f"bess_{mfr}"
            if bess_key not in reg.connectors:
                # Create a dedicated BESS connector
                connector = self._create_connector(mfr, [], config, bess=bess_cfg)
                if connector:
                    reg.connectors[bess_key] = connector

        # Meter connectors
        meters = config.get("meters", [])
        for mtr_cfg in meters:
            mtr_cfg["site_id"] = site_id

        self._sites[site_id] = reg
        logger.info(
            f"Registered solar site '{site_name}' with "
            f"{len(reg.plants)} plants, {len(reg.connectors)} connectors"
        )

    def _create_connector(
        self,
        manufacturer: str,
        inverters: List[Dict],
        config: Dict,
        bess: Optional[Dict] = None,
    ) -> Optional[SolarConnector]:
        """Factory method — create the appropriate connector for a manufacturer."""
        meters = config.get("meters", [])

        if manufacturer == "huawei":
            return SimulatedHuaweiConnector(
                inverters=inverters,
                bess=bess or config.get("bess"),
                meters=[m for m in meters if m.get("manufacturer", "").lower() != "schneider"],
            )
        elif manufacturer == "schneider":
            return SimulatedSchneiderConnector(
                inverters=inverters,
                meters=[m for m in meters if m.get("manufacturer", "").lower() == "schneider"],
            )
        else:
            logger.warning(f"No connector available for manufacturer: {manufacturer}")
            return None

    # === Polling ===

    async def connect_all(self, site_id: Optional[str] = None) -> None:
        """Connect all connectors for a site (or all sites)."""
        sites = [self._sites[site_id]] if site_id and site_id in self._sites else self._sites.values()
        for site in sites:
            for key, connector in site.connectors.items():
                try:
                    await connector.connect()
                except Exception as e:
                    logger.error(f"Failed to connect {key}: {e}")

    async def poll_site(self, site_id: str) -> Dict:
        """Poll all connectors for a site and return aggregated overview."""
        site = self._sites.get(site_id)
        if not site:
            return {"error": f"Site {site_id} not registered"}

        # Ensure connected
        for key, connector in site.connectors.items():
            if not connector.is_connected():
                try:
                    await connector.connect()
                except Exception as e:
                    logger.error(f"Connect failed for {key}: {e}")

        # Aggregate readings
        all_readings: List[NormalisedReading] = []
        for key, connector in site.connectors.items():
            try:
                readings = await connector.get_normalised_readings()
                all_readings.extend(readings)
            except Exception as e:
                logger.error(f"Poll failed for {key}: {e}")

        site.last_poll = datetime.now(timezone.utc).isoformat()

        return {
            "site_id": site_id,
            "site_name": site.site_name,
            "timestamp": site.last_poll,
            "readings_count": len(all_readings),
            "readings": [r.to_dict() for r in all_readings],
        }

    # === Site overview ===

    async def get_site_overview(self, site_id: str) -> Optional[Dict]:
        """Get high-level site overview: total generation, BESS SOC, grid flow."""
        site = self._sites.get(site_id)
        if not site:
            return None

        # Collect all inverter readings
        total_pv_kw = 0.0
        total_daily_kwh = 0.0
        inverter_count = 0
        inverters_online = 0
        inverters_fault = 0

        for key, connector in site.connectors.items():
            if not connector.is_connected():
                try:
                    await connector.connect()
                except Exception:
                    continue

        # Read all inverters from all connectors
        all_inverters = await self.get_inverters(site_id)
        for inv in all_inverters:
            inverter_count += 1
            total_pv_kw += inv.ac_power_kw
            total_daily_kwh += inv.daily_yield_kwh
            if inv.status == "online":
                inverters_online += 1
            elif inv.status == "fault":
                inverters_fault += 1

        # BESS status
        bess = await self.get_bess_status(site_id)
        bess_data = bess.to_dict() if bess else None

        # Meter readings
        meters = await self.get_meter_readings(site_id)
        grid_import_kw = sum(m.import_kw for m in meters)
        grid_export_kw = sum(m.export_kw for m in meters)

        # Plant summaries
        plant_summaries = []
        for plant in site.plants.values():
            plant_inverters = [i for i in all_inverters if i.plant_id == plant.plant_id]
            plant_summaries.append({
                "plant_id": plant.plant_id,
                "name": plant.name,
                "capacity_kwp": plant.capacity_kwp,
                "current_kw": round(sum(i.ac_power_kw for i in plant_inverters), 1),
                "inverters_online": sum(1 for i in plant_inverters if i.status == "online"),
                "inverters_total": len(plant_inverters),
            })

        # Total plant capacity
        total_capacity_kwp = sum(p.capacity_kwp for p in site.plants.values())
        performance_ratio = (total_pv_kw / total_capacity_kwp * 100) if total_capacity_kwp > 0 else 0

        return {
            "site_id": site_id,
            "site_name": site.site_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "generation": {
                "total_pv_kw": round(total_pv_kw, 1),
                "total_daily_kwh": round(total_daily_kwh, 0),
                "total_capacity_kwp": round(total_capacity_kwp, 1),
                "performance_ratio_pct": round(performance_ratio, 1),
            },
            "inverters": {
                "total": inverter_count,
                "online": inverters_online,
                "fault": inverters_fault,
                "offline": inverter_count - inverters_online - inverters_fault,
            },
            "bess": bess_data,
            "grid": {
                "import_kw": round(grid_import_kw, 1),
                "export_kw": round(grid_export_kw, 1),
                "net_kw": round(grid_import_kw - grid_export_kw, 1),
            },
            "plants": plant_summaries,
        }

    # === Inverter detail ===

    async def get_inverters(self, site_id: str) -> List[SolarInverter]:
        """Get all inverters for a site with current readings."""
        site = self._sites.get(site_id)
        if not site:
            return []

        inverters = []
        for key, connector in site.connectors.items():
            if not connector.is_connected():
                try:
                    await connector.connect()
                except Exception:
                    continue
            # Read inverters based on the config
            for plant_cfg in site.config.get("plants", []):
                for inv_cfg in plant_cfg.get("inverters", []):
                    mfr = inv_cfg.get("manufacturer", "").lower()
                    if mfr in key:
                        try:
                            inv = await connector.read_inverter(inv_cfg["id"])
                            if inv:
                                inverters.append(inv)
                        except Exception as e:
                            logger.error(f"Failed to read inverter {inv_cfg['id']}: {e}")
        return inverters

    async def get_inverter_detail(
        self, site_id: str, inverter_id: str
    ) -> Optional[Dict]:
        """Get single inverter detail with string-level data."""
        site = self._sites.get(site_id)
        if not site:
            return None

        for key, connector in site.connectors.items():
            if not connector.is_connected():
                try:
                    await connector.connect()
                except Exception:
                    continue
            inv = await connector.read_inverter(inverter_id)
            if inv:
                strings = await connector.read_all_strings(inverter_id)
                return {
                    "inverter": inv.to_dict(),
                    "strings": [s.to_dict() for s in strings],
                    "string_count": len(strings),
                }
        return None

    # === BESS ===

    async def get_bess_status(self, site_id: str) -> Optional[BESSContainer]:
        """Get BESS container status for a site."""
        site = self._sites.get(site_id)
        if not site:
            return None

        bess_cfg = site.config.get("bess")
        if not bess_cfg:
            return None

        container_id = bess_cfg.get("container_id", "")
        for key, connector in site.connectors.items():
            if not connector.is_connected():
                try:
                    await connector.connect()
                except Exception:
                    continue
            bess = await connector.read_bess(container_id)
            if bess:
                return bess
        return None

    # === Meters ===

    async def get_meter_readings(self, site_id: str) -> List[GridMeter]:
        """Get all meter readings for a site."""
        site = self._sites.get(site_id)
        if not site:
            return []

        meters = []
        for mtr_cfg in site.config.get("meters", []):
            meter_id = mtr_cfg["meter_id"]
            for key, connector in site.connectors.items():
                if not connector.is_connected():
                    try:
                        await connector.connect()
                    except Exception:
                        continue
                mtr = await connector.read_meter(meter_id)
                if mtr:
                    meters.append(mtr)
                    break  # found it, don't ask other connectors
        return meters

    # === Normalised readings ===

    async def get_readings(
        self,
        site_id: str,
        reading_type: Optional[str] = None,
        equipment_type: Optional[str] = None,
    ) -> List[NormalisedReading]:
        """Get normalised readings, optionally filtered by type."""
        site = self._sites.get(site_id)
        if not site:
            return []

        all_readings: List[NormalisedReading] = []
        for key, connector in site.connectors.items():
            if not connector.is_connected():
                try:
                    await connector.connect()
                except Exception:
                    continue
            try:
                readings = await connector.get_normalised_readings()
                all_readings.extend(readings)
            except Exception as e:
                logger.error(f"Failed to get readings from {key}: {e}")

        # Filter
        if reading_type:
            all_readings = [r for r in all_readings if r.reading_type == reading_type]
        if equipment_type:
            all_readings = [r for r in all_readings if r.equipment_type == equipment_type]

        return all_readings

    # === Connector health ===

    def get_connector_status(self, site_id: str) -> List[Dict]:
        """Get health status of all connectors for a site."""
        site = self._sites.get(site_id)
        if not site:
            return []

        return [
            {
                "connector": key,
                "manufacturer": connector.manufacturer,
                "protocol": connector.protocol,
                **connector.get_status().to_dict(),
            }
            for key, connector in site.connectors.items()
        ]

    # === Site listing ===

    def get_registered_sites(self) -> List[Dict]:
        """List all registered solar sites."""
        return [
            {
                "site_id": site.site_id,
                "site_name": site.site_name,
                "plants": len(site.plants),
                "connectors": len(site.connectors),
                "last_poll": site.last_poll,
            }
            for site in self._sites.values()
        ]


# === Singleton ===

_solar_ingestion_service: Optional[SolarIngestionService] = None


def get_solar_ingestion_service() -> SolarIngestionService:
    """Get the singleton solar ingestion service instance."""
    global _solar_ingestion_service
    if _solar_ingestion_service is None:
        _solar_ingestion_service = SolarIngestionService()
    return _solar_ingestion_service
