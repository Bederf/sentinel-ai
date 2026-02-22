"""Water Ingestion Service — manages water meter polling and consumption tracking.

Singleton service that orchestrates water meter data ingestion across multiple sites.
Follows the same pattern as solar_ingestion_service.py and energy_centre_service.py.
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path
import json

from app.models.water_meter import WaterMeter, WaterConsumption
from app.services.water_meter_adapter import create_water_meter_adapter
from app.database.repositories.water_consumption_repository import WaterConsumptionRepository

logger = logging.getLogger(__name__)


class SiteRegistration:
    """Holds meter and config for a single site."""

    def __init__(self, site_id: str, config: Dict):
        self.site_id = site_id
        self.config = config
        self.meters: Dict[str, WaterMeter] = {}
        self.adapters: Dict[str, any] = {}  # device_id -> adapter
        self.last_poll: Optional[datetime] = None
        self.previous_pulse_counts: Dict[str, int] = {}  # For flow rate calculation
        self.meter_zone_map: Dict[str, Optional[str]] = {}  # meter_id -> zone_id mapping


class WaterIngestionService:
    """Manages water meter data ingestion across multiple sites.

    Responsibilities:
      - Auto-register sites from equipment files
      - Create meter adapters (Modbus pulse counters)
      - Poll meters at configured interval (default 60 seconds)
      - Calculate flow rate from pulse count delta
      - Store consumption readings to repository
      - Handle pulse counter wraparound (32-bit integer max)
    """

    _instance: Optional["WaterIngestionService"] = None
    _polling_interval_seconds: int = 60
    _running: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self._sites: Dict[str, SiteRegistration] = {}
        self._repository = WaterConsumptionRepository()
        self._load_sites()

    # === Site management ===

    def _load_sites(self):
        """Auto-load sites from equipment files."""
        buildings_dir = Path(__file__).parent.parent / "data" / "buildings"

        for site_dir in buildings_dir.iterdir():
            if not site_dir.is_dir() or not site_dir.name.startswith("site-"):
                continue

            site_id = site_dir.name
            equipment_dir = site_dir / "equipment"

            if not equipment_dir.exists():
                continue

            # Find water meter equipment files
            water_meters = []
            meter_zone_map = {}
            for equipment_file in equipment_dir.glob("S*-*-W-*.json"):
                try:
                    with open(equipment_file) as f:
                        equipment_data = json.load(f)

                    if equipment_data.get("equipment_type") == "METER" and "W" in equipment_data.get(
                        "equipment_code", ""
                    ):
                        meter = WaterMeter.from_dict(
                            {
                                "meter_id": equipment_data["equipment_code"],
                                "site": site_id,
                                "meter_type": equipment_data.get("properties", {}).get("meter_type", "main"),
                                "pulse_weight": equipment_data.get("properties", {}).get("pulse_weight", 10.0),
                                "installation_date": datetime.fromisoformat(
                                    equipment_data.get("properties", {}).get("installation_date", "2023-01-01")
                                ),
                                "location": equipment_data.get("metadata", {}).get("location", ""),
                                "protocol": equipment_data.get("protocol", "modbus"),
                                "register_address": equipment_data.get("points", [{}])[0].get("address", 30001),
                                "max_flow_rate_lpm": equipment_data.get("properties", {}).get(
                                    "max_flow_rate_lpm", 100.0
                                ),
                                "baseline_flow_lpm": equipment_data.get("properties", {}).get("baseline_flow_lpm", 2.0),
                            }
                        )
                        water_meters.append(meter)

                        # Extract zone_id from metadata
                        zone_id = equipment_data.get("metadata", {}).get("zone_id") or equipment_data.get("zone")
                        meter_zone_map[meter.meter_id] = zone_id
                        if zone_id:
                            logger.info(
                                f"Loaded water meter: {meter.meter_id} (zone: {zone_id}) from {equipment_file.name}"
                            )
                        else:
                            logger.info(
                                f"Loaded water meter: {meter.meter_id} (no zone assigned) from {equipment_file.name}"
                            )
                except Exception as e:
                    logger.error(f"Failed to load water meter from {equipment_file}: {e}")

            if water_meters:
                config = {
                    "site_id": site_id,
                    "polling_interval_seconds": 60,
                }
                self.register_site(site_id, config, water_meters, meter_zone_map)
                logger.info(f"Registered {len(water_meters)} water meter(s) for {site_id}")

    def register_site(
        self,
        site_id: str,
        config: Dict,
        meters: List[WaterMeter],
        meter_zone_map: Optional[Dict[str, Optional[str]]] = None,
    ):
        """Register a site with its water meters.

        Args:
            site_id: Site identifier
            config: Site configuration
            meters: List of water meters
            meter_zone_map: Optional mapping of meter_id to zone_id
        """
        registration = SiteRegistration(site_id, config)

        for meter in meters:
            registration.meters[meter.meter_id] = meter
            # Store zone assignment for this meter
            if meter_zone_map:
                zone_id = meter_zone_map.get(meter.meter_id)
                registration.meter_zone_map[meter.meter_id] = zone_id
            else:
                registration.meter_zone_map[meter.meter_id] = None

            # Create adapter for each meter
            adapter_config = {
                "pulse_weight": meter.pulse_weight,
                "register_address": meter.register_address,
                "protocol": meter.protocol,
                "site": site_id,
            }
            adapter = create_water_meter_adapter(meter.meter_id, adapter_config)
            adapter.connect()
            registration.adapters[meter.meter_id] = adapter
            registration.previous_pulse_counts[meter.meter_id] = 0

        self._sites[site_id] = registration
        logger.info(f"Registered site {site_id} with {len(meters)} water meter(s)")

    def get_sites(self) -> List[str]:
        """Get list of registered sites."""
        return list(self._sites.keys())

    # === Polling ===

    async def start_ingestion(self):
        """Start background polling loop."""
        if self._running:
            logger.warning("Water ingestion already running")
            return

        self._running = True
        logger.info(f"Starting water ingestion (interval: {self._polling_interval_seconds}s)")

        while self._running:
            try:
                await self._poll_all_sites()
            except Exception as e:
                logger.error(f"Error during water polling: {e}")

            await asyncio.sleep(self._polling_interval_seconds)

    def stop_ingestion(self):
        """Stop background polling loop."""
        self._running = False
        logger.info("Stopped water ingestion")

    async def _poll_all_sites(self):
        """Poll all registered sites."""
        for site_id, registration in self._sites.items():
            try:
                await self._poll_site(site_id, registration)
            except Exception as e:
                logger.error(f"Error polling site {site_id}: {e}")

    async def _poll_site(self, site_id: str, registration: SiteRegistration):
        """Poll all meters at a site."""
        timestamp = datetime.now()

        for meter_id, adapter in registration.adapters.items():
            try:
                # Read all points from meter
                points = adapter.read_all_points()

                pulse_count = points.get("pulse_count", 0)
                flow_rate = points.get("flow_rate", 0.0)
                volume_liters = points.get("volume_liters", 0.0)

                # Calculate flow rate from pulse delta if not provided
                previous_count = registration.previous_pulse_counts.get(meter_id, 0)
                if flow_rate == 0.0 and pulse_count != previous_count:
                    # Calculate flow rate: delta_volume / delta_time
                    # Assuming 60s polling interval
                    delta_pulses = pulse_count - previous_count

                    # Handle wraparound (32-bit signed int: 2^31 - 1 = 2147483647)
                    MAX_INT32 = 2147483647
                    if delta_pulses < -MAX_INT32 / 2:  # Likely wraparound
                        delta_pulses += MAX_INT32

                    meter = registration.meters[meter_id]
                    delta_volume_liters = delta_pulses * meter.pulse_weight
                    flow_rate = delta_volume_liters / (self._polling_interval_seconds / 60.0)

                    registration.previous_pulse_counts[meter_id] = pulse_count

                # Get zone_id for this meter
                zone_id = registration.meter_zone_map.get(meter_id)

                # Save to repository
                self._repository.create_consumption(
                    meter_id=meter_id,
                    site=site_id,
                    volume_liters=volume_liters,
                    flow_rate_lpm=flow_rate,
                    timestamp=timestamp,
                    pulse_count=pulse_count,
                    temperature=points.get("temperature"),
                    pressure=points.get("pressure"),
                    zone_id=zone_id,
                )

                logger.debug(f"Polled {meter_id}: {flow_rate} LPM, {volume_liters} L")

            except Exception as e:
                logger.error(f"Error polling meter {meter_id}: {e}")

        registration.last_poll = timestamp

    # === Queries ===

    def get_latest_consumption(self, site_id: str) -> Optional[WaterConsumption]:
        """Get latest consumption reading for a site."""
        record = self._repository.get_latest_consumption(site_id)
        if record:
            return WaterConsumption.from_dict(record)
        return None

    def get_consumption_history(
        self,
        site_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 1000,
    ) -> List[WaterConsumption]:
        """Get consumption history for a site."""
        records = self._repository.get_consumption_by_site(
            site=site_id,
            start_date=start_date.date() if start_date else None,
            end_date=end_date.date() if end_date else None,
            limit=limit,
        )
        return [WaterConsumption.from_dict(r) for r in records]

    def get_site_status(self, site_id: str) -> Dict:
        """Get ingestion status for a site."""
        if site_id not in self._sites:
            return {"error": "Site not registered"}

        registration = self._sites[site_id]
        return {
            "site_id": site_id,
            "meter_count": len(registration.meters),
            "last_poll": registration.last_poll.isoformat() if registration.last_poll else None,
            "meters": list(registration.meters.keys()),
        }


# Singleton instance
_water_ingestion_service: Optional[WaterIngestionService] = None


def get_water_ingestion_service() -> WaterIngestionService:
    """Get singleton instance of WaterIngestionService."""
    global _water_ingestion_service
    if _water_ingestion_service is None:
        _water_ingestion_service = WaterIngestionService()
    return _water_ingestion_service
