"""Solar Ingestion Service — manages manufacturer connectors and normalised reads.

Singleton service that orchestrates polling across heterogeneous solar/BESS
installations.  Each site can have multiple connectors (one per manufacturer).
All data is normalised into protocol-agnostic models before being served
to the API layer.

Pattern follows energy_centre_service.py.
"""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from app.database.supabase_client import get_supabase_client
from app.models.solar import (
    BESSContainer,
    GridMeter,
    NormalisedReading,
    SolarInverter,
    SolarPlant,
)
from app.services.solar_connector_base import SolarConnector
from app.services.solar_connector_huawei import SimulatedHuaweiConnector
from app.services.solar_connector_schneider import SimulatedSchneiderConnector

logger = logging.getLogger(__name__)


class SiteRegistration:
    """Holds all connectors and config for a single solar site."""

    def __init__(self, site_id: str, site_name: str, config: dict):
        self.site_id = site_id
        self.site_name = site_name
        self.config = config
        self.connectors: dict[str, SolarConnector] = {}
        self.plants: dict[str, SolarPlant] = {}
        self.last_poll: str | None = None


class SolarIngestionService:
    """Manages solar/BESS data ingestion across multiple sites.

    Responsibilities:
      - Load site configs from JSON (auto-registers Site-002 on startup)
      - Instantiate per-manufacturer connectors (simulated for local mode)
      - Poll all connectors and aggregate normalised readings
      - Quality-flag management: fresh (<30s) = good, >60s = stale
      - Serve site overviews, inverter details, BESS status, meter data
    """

    def __init__(self):
        self._sites: dict[str, SiteRegistration] = {}
        self._load_site_configs()

    # === Site management ===

    def _load_site_configs(self):
        """Auto-load site configurations from Supabase and JSON fallback."""
        configs_by_id: dict[str, dict] = {}

        # 1) Supabase (preferred)
        supabase_configs = self._load_site_configs_from_supabase()
        for cfg in supabase_configs:
            configs_by_id[cfg.get("site_id")] = cfg

        # 2) JSON fallback
        json_configs = self._load_site_configs_from_json()

        # If Supabase is empty but JSON exists, seed Supabase
        if not supabase_configs and json_configs:
            self._seed_supabase_from_configs(json_configs)
            supabase_configs = self._load_site_configs_from_supabase()
            for cfg in supabase_configs:
                configs_by_id[cfg.get("site_id")] = cfg

        # Fill any gaps with JSON
        for cfg in json_configs:
            configs_by_id.setdefault(cfg.get("site_id"), cfg)

        for site_id, config in configs_by_id.items():
            if not site_id:
                continue
            self.register_site(site_id, config)
            logger.info("Auto-loaded solar site: %s", site_id)

    def _load_site_configs_from_json(self) -> list[dict]:
        """Load site configurations from data/solar/ directory."""
        solar_data_dir = Path(__file__).parent.parent / "data" / "solar"
        if not solar_data_dir.exists():
            logger.warning("Solar data directory not found: %s", solar_data_dir)
            return []

        configs: list[dict] = []
        config_files = list(solar_data_dir.glob("*_config.json"))
        for config_path in config_files:
            try:
                with open(config_path) as f:
                    config = json.load(f)
                config["site_id"] = config.get("site_id", config_path.stem.replace("_config", ""))
                configs.append(config)
                logger.info("Loaded solar config from JSON: %s", config_path.name)
            except Exception as e:
                logger.error("Failed to load solar config %s: %s", config_path, e)
        return configs

    def _load_site_configs_from_supabase(self) -> list[dict]:
        """Load solar site configs from Supabase tables (if available)."""
        try:
            client = get_supabase_client()
        except Exception as e:
            logger.warning("Supabase client unavailable for solar configs: %s", e)
            return []

        try:
            sites = client.table("solar_sites").select("*").execute().data or []
            if not sites:
                return []

            plants = client.table("solar_plants").select("*").execute().data or []
            inverters = client.table("solar_inverters").select("*").execute().data or []
            bess = client.table("solar_bess").select("*").execute().data or []
            meters = client.table("solar_meters").select("*").execute().data or []

            # Build UUID → site code mapping via buildings table.
            # solar_plants/bess/meters reference buildings(id) as UUID,
            # but solar_sites uses TEXT site_id (e.g. "site-002").
            buildings_data = client.table("sites").select("id, code").execute().data or []
            site_uuid_to_code = {str(b["id"]): b["code"] for b in buildings_data}

            plants_by_site: dict[str, list[dict]] = {}
            for plant in plants:
                plant_site_uuid = str(plant["site_id"])
                resolved_site_id = site_uuid_to_code.get(plant_site_uuid, plant_site_uuid)
                plants_by_site.setdefault(resolved_site_id, []).append(plant)

            inverters_by_plant: dict[str, list[dict]] = {}
            for inv in inverters:
                inverters_by_plant.setdefault(inv["plant_id"], []).append(inv)

            bess_by_site: dict[str, dict] = {}
            for b in bess:
                bess_site_uuid = str(b.get("site_id", ""))
                resolved_bess_site = site_uuid_to_code.get(bess_site_uuid, bess_site_uuid)
                bess_by_site[resolved_bess_site] = b

            meters_by_site: dict[str, list[dict]] = {}
            for m in meters:
                meter_site_uuid = str(m.get("site_id", ""))
                resolved_meter_site = site_uuid_to_code.get(meter_site_uuid, meter_site_uuid)
                meters_by_site.setdefault(resolved_meter_site, []).append(m)

            configs: list[dict] = []
            for site in sites:
                site_id = site["site_id"]
                site_plants = []
                for plant in plants_by_site.get(site_id, []):
                    plant_inverters = inverters_by_plant.get(plant["plant_id"], [])
                    site_plants.append(
                        {
                            "plant_id": plant["plant_id"],
                            "name": plant.get("name", ""),
                            "capacity_kwp": plant.get("capacity_kwp", 0),
                            "panel_count": plant.get("panel_count", 0),
                            "panel_model": plant.get("panel_model", ""),
                            "panel_rating_w": plant.get("panel_rating_w", 0),
                            "commissioning_date": plant.get("commissioning_date"),
                            "orientation": plant.get("orientation", 0),
                            "tilt": plant.get("tilt", 0),
                            "inverters": [
                                {
                                    "id": inv["inverter_id"],
                                    "name": inv.get("name", ""),
                                    "manufacturer": inv.get("manufacturer", ""),
                                    "model": inv.get("model", ""),
                                    "rated_kva": inv.get("rated_power_kva") or inv.get("rated_kva", 0),
                                    "mppt_count": inv.get("mppt_count", 0),
                                    "protocol": inv.get("protocol", ""),
                                    "ip": inv.get("ip_address") or inv.get("ip", ""),
                                    "port": inv.get("port", 0),
                                    "unit_id": inv.get("unit_id", 0),
                                    "strings_per_mppt": inv.get("strings_per_mppt", 0),
                                    "panels_per_string": inv.get("panels_per_string", 0),
                                }
                                for inv in plant_inverters
                            ],
                        }
                    )

                config = {
                    "site_id": site_id,
                    "site_name": site.get("site_name", site_id),
                    "latitude": site.get("latitude", -26.2),
                    "longitude": site.get("longitude", 28.0),
                    "plants": site_plants,
                    "bess": None,
                    "meters": meters_by_site.get(site_id, []),
                }

                if site_id in bess_by_site:
                    b = bess_by_site[site_id]
                    config["bess"] = {
                        "container_id": b.get("container_id", b.get("bess_id", "")),
                        "name": b.get("name", ""),
                        "manufacturer": b.get("manufacturer", ""),
                        "model": b.get("model", ""),
                        "capacity_kwh": b.get("capacity_kwh", 0),
                        "rated_power_kw": b.get("rated_power_kw", 0),
                        "rack_count": b.get("rack_count", 0),
                        "cell_chemistry": b.get("cell_chemistry", ""),
                        "protocol": b.get("protocol", ""),
                    }

                configs.append(config)

            return configs
        except Exception as e:
            logger.error("Failed to load solar configs from Supabase: %s", e)
            return []

    def _seed_supabase_from_configs(self, configs: list[dict]) -> None:
        """Seed Supabase solar tables from JSON config if empty."""
        try:
            client = get_supabase_client()
        except Exception as e:
            logger.warning("Supabase client unavailable for solar seed: %s", e)
            return

        try:
            existing = client.table("solar_sites").select("site_id").execute().data or []
            if existing:
                return
        except Exception as e:
            logger.warning("Solar seed skipped (tables missing?): %s", e)
            return

        for config in configs:
            site_id = config.get("site_id")
            if not site_id:
                continue

            try:
                client.table("solar_sites").insert(
                    {
                        "site_id": site_id,
                        "site_name": config.get("site_name", site_id),
                        "latitude": config.get("latitude"),
                        "longitude": config.get("longitude"),
                    }
                ).execute()

                plants = []
                inverters = []
                for plant in config.get("plants", []):
                    plants.append(
                        {
                            "plant_id": plant.get("plant_id"),
                            "site_id": site_id,
                            "name": plant.get("name", ""),
                            "capacity_kwp": plant.get("capacity_kwp", 0),
                            "panel_count": plant.get("panel_count", 0),
                            "panel_model": plant.get("panel_model", ""),
                            "panel_rating_w": plant.get("panel_rating_w", 0),
                            "commissioning_date": plant.get("commissioning_date"),
                            "orientation": plant.get("orientation", 0),
                            "tilt": plant.get("tilt", 0),
                        }
                    )
                    for inv in plant.get("inverters", []):
                        inverters.append(
                            {
                                "inverter_id": inv.get("id"),
                                "site_id": site_id,
                                "plant_id": plant.get("plant_id"),
                                "name": inv.get("name", ""),
                                "manufacturer": inv.get("manufacturer", ""),
                                "model": inv.get("model", ""),
                                "rated_kva": inv.get("rated_kva", 0),
                                "mppt_count": inv.get("mppt_count", 0),
                                "protocol": inv.get("protocol", ""),
                                "ip": inv.get("ip", ""),
                                "port": inv.get("port", 0),
                                "unit_id": inv.get("unit_id", 0),
                                "strings_per_mppt": inv.get("strings_per_mppt", 0),
                                "panels_per_string": inv.get("panels_per_string", 0),
                            }
                        )

                if plants:
                    client.table("solar_plants").insert(plants).execute()
                if inverters:
                    client.table("solar_inverters").insert(inverters).execute()

                bess = config.get("bess")
                if bess:
                    client.table("solar_bess").insert(
                        {
                            "bess_id": bess.get("container_id"),
                            "site_id": site_id,
                            "container_id": bess.get("container_id"),
                            "name": bess.get("name", ""),
                            "manufacturer": bess.get("manufacturer", ""),
                            "model": bess.get("model", ""),
                            "capacity_kwh": bess.get("capacity_kwh", 0),
                            "rated_power_kw": bess.get("rated_power_kw", 0),
                            "rack_count": bess.get("rack_count", 0),
                            "cell_chemistry": bess.get("cell_chemistry", ""),
                            "protocol": bess.get("protocol", ""),
                        }
                    ).execute()

                meters = []
                for m in config.get("meters", []):
                    meters.append(
                        {
                            "meter_id": m.get("meter_id"),
                            "site_id": site_id,
                            "name": m.get("name", ""),
                            "manufacturer": m.get("manufacturer", ""),
                            "model": m.get("model", ""),
                            "protocol": m.get("protocol", ""),
                            "ip": m.get("ip", ""),
                            "port": m.get("port", 0),
                        }
                    )
                if meters:
                    client.table("solar_meters").insert(meters).execute()

                logger.info("Seeded solar site into Supabase: %s", site_id)
            except Exception as e:
                logger.error("Failed seeding solar site %s: %s", site_id, e)

    def register_site(self, site_id: str, config: dict) -> None:
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
            manufacturers: dict[str, list[dict]] = {}
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

        # BESS connector (usually Huawei for Site-002)
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

        # Store plant capacity for use in simulation lookups
        reg._total_plant_capacity_kwp = sum(p.capacity_kwp for p in reg.plants.values()) or 3.875

        self._sites[site_id] = reg
        logger.info(
            f"Registered solar site '{site_name}' with {len(reg.plants)} plants, {len(reg.connectors)} connectors"
        )

    def _create_connector(
        self,
        manufacturer: str,
        inverters: list[dict],
        config: dict,
        bess: dict | None = None,
    ) -> SolarConnector | None:
        """Factory method — create the appropriate connector for a manufacturer.

        Respects settings.solar_connector_mode:
          - "live" (default): attempts real Modbus TCP connector and fails closed
          - "simulation": explicit non-live mode for offline simulation work only
        """
        from app.config.settings import settings

        meters = config.get("meters", [])
        mode = settings.solar_connector_mode

        if manufacturer == "huawei":
            if mode == "live":
                try:
                    from app.services.solar_connector_huawei import RealHuaweiConnector

                    return RealHuaweiConnector(
                        inverters=inverters,
                        bess=bess or config.get("bess"),
                        meters=[m for m in meters if m.get("manufacturer", "").lower() != "schneider"],
                    )
                except Exception as e:
                    logger.error("Real Huawei connector unavailable in live mode: %s", e)
                    return None
            return SimulatedHuaweiConnector(
                inverters=inverters,
                bess=bess or config.get("bess"),
                meters=[m for m in meters if m.get("manufacturer", "").lower() != "schneider"],
            )
        elif manufacturer == "schneider":
            if mode == "live":
                logger.error("No live Schneider connector configured; refusing simulated Schneider data")
                return None
            return SimulatedSchneiderConnector(
                inverters=inverters,
                meters=[m for m in meters if m.get("manufacturer", "").lower() == "schneider"],
            )
        else:
            logger.warning(f"No connector available for manufacturer: {manufacturer}")
            return None

    # === Polling ===

    async def connect_all(self, site_id: str | None = None) -> None:
        """Connect all connectors for a site (or all sites)."""
        sites = [self._sites[site_id]] if site_id and site_id in self._sites else self._sites.values()
        for site in sites:
            for key, connector in site.connectors.items():
                try:
                    await connector.connect()
                except Exception as e:
                    logger.error(f"Failed to connect {key}: {e}")

    async def poll_site(self, site_id: str) -> dict:
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
        all_readings: list[NormalisedReading] = []
        for key, connector in site.connectors.items():
            try:
                readings = await connector.get_normalised_readings()
                all_readings.extend(readings)
            except Exception as e:
                logger.error(f"Poll failed for {key}: {e}")

        site.last_poll = datetime.now(UTC).isoformat()

        return {
            "site_id": site_id,
            "site_name": site.site_name,
            "timestamp": site.last_poll,
            "readings_count": len(all_readings),
            "readings": [r.to_dict() for r in all_readings],
        }

    # === Site overview ===

    async def get_site_overview(self, site_id: str) -> dict | None:
        """Get high-level site overview from Supabase snapshots.

        Data source priority:
        1. solar_hourly_snapshots (persisted by lifecycle simulation) — preferred
        2. Live connectors (simulated or real hardware) — fallback
        3. Zeros — when no data exists yet (start-from-0)

        Returns:
        - Annual metrics from cached simulation
        - Current solar/BESS values from latest snapshot or connector
        """
        site = self._sites.get(site_id)
        if not site:
            return None

        try:
            # === Fetch annual summary from cache ===
            annual_data = await self._get_annual_summary(site_id)

            # === Try Supabase snapshot first (persisted simulation data) ===
            snapshot = await self._get_latest_snapshot(site_id)

            # Total plant capacity from config
            total_capacity_kwp = sum(p.capacity_kwp for p in site.plants.values())
            inverter_count = sum(len(p_cfg.get("inverters", [])) for p_cfg in site.config.get("plants", []))

            if snapshot:
                # Use persisted simulation data
                total_pv_kw = snapshot["solar_gen_kw"]
                bess_soc = snapshot["bess_soc_pct"]
                bess_charge = snapshot["bess_charge_kw"]
                bess_discharge = snapshot["bess_discharge_kw"]
                grid_import_kw = snapshot["grid_import_kw"]
                grid_export_kw = snapshot["grid_export_kw"]
                data_source = "supabase_snapshot"

                # Derive BESS mode from charge/discharge
                if bess_charge > 0.1:
                    bess_mode_str = "charging"
                elif bess_discharge > 0.1:
                    bess_mode_str = "discharging"
                else:
                    bess_mode_str = "idle"

                # Daily yield from today's snapshots
                total_daily_kwh = await self._get_daily_yield(site_id, snapshot["date"])

                # Inverters: assume all online if generating
                inverters_online = inverter_count if total_pv_kw > 0 else 0
                inverters_fault = 0

                logger.debug(f"Solar overview from snapshot: {total_pv_kw:.1f} kW, SOC {bess_soc:.1f}%")
            else:
                # === Fallback: live connectors ===
                for _key, connector in site.connectors.items():
                    if not connector.is_connected():
                        try:
                            await connector.connect()
                        except Exception:
                            continue

                all_inverters = await self.get_inverters(site_id)
                inverter_count = len(all_inverters)
                inverters_online = sum(1 for i in all_inverters if i.status == "online")
                inverters_fault = sum(1 for i in all_inverters if i.status == "fault")
                total_pv_kw = sum(i.ac_power_kw for i in all_inverters)
                total_daily_kwh = sum(i.daily_yield_kwh for i in all_inverters)

                bess = await self.get_bess_status(site_id)
                bess_soc = bess.soc_pct if bess else 0
                bess_mode_str = bess.mode if bess else "idle"
                bess_charge = bess.charge_power_kw if bess else 0
                bess_discharge = bess.discharge_power_kw if bess else 0

                meters = await self.get_meter_readings(site_id)
                grid_import_kw = sum(m.import_kw for m in meters)
                grid_export_kw = sum(m.export_kw for m in meters)
                data_source = "live_connectors"

            # Compute derived values
            performance_ratio = (total_pv_kw / total_capacity_kwp * 100) if total_capacity_kwp > 0 else 0
            if performance_ratio > 1:
                perf_ratio_frac = round(performance_ratio / 100, 3)
            else:
                perf_ratio_frac = round(performance_ratio, 3)
            if total_pv_kw > 0:
                self_consumption_pct = round((total_pv_kw - grid_export_kw) / total_pv_kw * 100, 1)
            else:
                self_consumption_pct = 0

            # Plant summaries
            plant_summaries = []
            for plant in site.plants.values():
                # Distribute total PV across plants proportionally
                plant_frac = plant.capacity_kwp / total_capacity_kwp if total_capacity_kwp > 0 else 0
                plant_kw = round(total_pv_kw * plant_frac, 1)
                plant_inv_count = len(
                    [
                        inv
                        for p_cfg in site.config.get("plants", [])
                        if p_cfg["plant_id"] == plant.plant_id
                        for inv in p_cfg.get("inverters", [])
                    ]
                )
                plant_summaries.append(
                    {
                        "plant_id": plant.plant_id,
                        "name": plant.name,
                        "plant_name": plant.name,
                        "capacity_kwp": plant.capacity_kwp,
                        "current_kw": plant_kw,
                        "current_generation_kw": plant_kw,
                        "inverters_online": plant_inv_count if total_pv_kw > 0 else 0,
                        "inverters_total": plant_inv_count,
                        "inverter_count": plant_inv_count,
                        "status": "normal",
                    }
                )

            response = {
                "site_id": site_id,
                "site_name": site.site_name,
                "timestamp": datetime.now(UTC).isoformat(),
                "data_source": data_source,
                # Flat fields (frontend SolarOverview interface)
                "installed_capacity_kwp": round(total_capacity_kwp, 1),
                "current_generation_kw": round(total_pv_kw, 1),
                "daily_yield_kwh": round(total_daily_kwh, 0),
                "expected_daily_yield_kwh": round(total_capacity_kwp * 5, 0),
                "performance_ratio": perf_ratio_frac,
                "bess_soc_percent": round(bess_soc, 1),
                "bess_mode": bess_mode_str,
                "grid_import_kw": round(grid_import_kw, 1),
                "grid_export_kw": round(grid_export_kw, 1),
                "self_consumption_percent": self_consumption_pct,
                "estimated_savings_today_zar": round(total_daily_kwh * 5, 0),
                # Nested details
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
                "bess": {
                    "soc_pct": round(bess_soc, 1),
                    "mode": bess_mode_str,
                    "charge_power_kw": round(bess_charge, 1),
                    "discharge_power_kw": round(bess_discharge, 1),
                },
                "grid": {
                    "import_kw": round(grid_import_kw, 1),
                    "export_kw": round(grid_export_kw, 1),
                    "net_kw": round(grid_import_kw - grid_export_kw, 1),
                },
                "plants": plant_summaries,
                "annual_summary": annual_data,
            }

            return response

        except Exception as e:
            logger.error(f"Failed to get site overview: {e}", exc_info=True)
            return None

    async def _get_annual_summary(self, site_id: str) -> dict | None:
        """Fetch annual simulation summary from cache."""
        try:
            supabase = get_supabase_client()
            response = (
                supabase.table("solar_annual_simulations")
                .select("*")
                .eq("site_id", site_id)
                .in_("scenario", ["sentinel_annual", "grant_solar_bess_ai_annual"])
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )

            if not response.data:
                logger.debug(f"No annual summary found for {site_id}")
                return None

            result = response.data[0]
            annual_data = result.get("results", {})

            logger.info(
                f"✅ Annual summary: R{annual_data.get('annual_savings_zar', 0):,.0f}, "
                f"{annual_data.get('annual_savings_pct', 0):.1f}% savings"
            )

            return annual_data

        except Exception as e:
            logger.debug(f"Failed to fetch annual summary: {e}")
            return None

    async def _get_latest_snapshot(self, site_id: str) -> dict | None:
        """Get the most recent solar_hourly_snapshots row for a site.

        Returns None if no simulation data has been persisted yet,
        which causes the dashboard to start from 0.
        """
        try:
            supabase = get_supabase_client()
            response = (
                supabase.table("solar_hourly_snapshots")
                .select("*")
                .eq("site_id", site_id)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            if response.data:
                return response.data[0]
            return None
        except Exception as e:
            logger.debug(f"Failed to fetch solar snapshot: {e}")
            return None

    async def _get_daily_yield(self, site_id: str, sim_date: str | None = None) -> float:
        """Sum solar_gen_kw from a simulated day's hourly snapshots.

        Each snapshot represents 1 hour, so kW × 1h = kWh.
        """
        try:
            if not sim_date:
                latest = await self._get_latest_snapshot(site_id)
                if not latest:
                    return 0.0
                sim_date = latest["date"]

            supabase = get_supabase_client()
            response = (
                supabase.table("solar_hourly_snapshots")
                .select("solar_gen_kw")
                .eq("site_id", site_id)
                .eq("date", sim_date)
                .execute()
            )
            if response.data:
                return sum(row["solar_gen_kw"] for row in response.data)
            return 0.0
        except Exception as e:
            logger.debug(f"Failed to calculate daily yield: {e}")
            return 0.0

    # === Inverter detail ===

    async def get_inverters(self, site_id: str) -> list[SolarInverter]:
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

    async def get_inverter_detail(self, site_id: str, inverter_id: str) -> dict | None:
        """Get single inverter detail with string-level data."""
        site = self._sites.get(site_id)
        if not site:
            return None

        for _key, connector in site.connectors.items():
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

    async def get_bess_status(self, site_id: str) -> BESSContainer | None:
        """Get BESS container status for a site."""
        site = self._sites.get(site_id)
        if not site:
            return None

        bess_cfg = site.config.get("bess")
        if not bess_cfg:
            return None

        container_id = bess_cfg.get("container_id", "")
        for _key, connector in site.connectors.items():
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

    async def get_meter_readings(self, site_id: str) -> list[GridMeter]:
        """Get all meter readings for a site."""
        site = self._sites.get(site_id)
        if not site:
            return []

        meters = []
        for mtr_cfg in site.config.get("meters", []):
            meter_id = mtr_cfg["meter_id"]
            for _key, connector in site.connectors.items():
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
        reading_type: str | None = None,
        equipment_type: str | None = None,
    ) -> list[NormalisedReading]:
        """Get normalised readings, optionally filtered by type."""
        site = self._sites.get(site_id)
        if not site:
            return []

        all_readings: list[NormalisedReading] = []
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

    def get_connector_status(self, site_id: str) -> list[dict]:
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

    def get_registered_sites(self) -> list[dict]:
        """List all registered solar sites with building names."""
        results = []

        # Try to fetch building names from repository if available
        building_repo = None
        try:
            from app.database.repositories.site_repository import SiteRepository

            building_repo = SiteRepository()
        except Exception as e:
            logger.debug(f"Building repository unavailable: {e}")

        for site in self._sites.values():
            # Fetch building name from repository if available
            site_name = ""
            if building_repo:
                try:
                    building = building_repo.get_by_id(site.site_id)
                    site_name = building.get("name", "") if building else ""
                except Exception as e:
                    logger.debug(f"Could not fetch building {site.site_id}: {e}")

            results.append(
                {
                    "site_id": site.site_id,
                    "site_name": site_name,
                    "plants": len(site.plants),
                    "connectors": len(site.connectors),
                    "last_poll": site.last_poll,
                }
            )

        return results


# === Singleton ===

_solar_ingestion_service: SolarIngestionService | None = None


def get_solar_ingestion_service() -> SolarIngestionService:
    """Get the singleton solar ingestion service instance."""
    global _solar_ingestion_service
    if _solar_ingestion_service is None:
        _solar_ingestion_service = SolarIngestionService()
    return _solar_ingestion_service
