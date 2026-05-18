"""
ODS-E Export Service

Transforms Sentinel energy data into ODS-E v0.4.0 format for Asoba eSUMS/Ona Platform ingestion.
"""

import logging
from datetime import datetime, timedelta
from typing import Any

from app.models.odse_models import (
    ODSEAssetExport,
    ODSEAssetMetadata,
    ODSEAssetRecord,
    ODSEBuilding,
    ODSELocation,
    ODSELocation,
    ODSERecord,
    ODSESentinelExtensions,
    ODSETimeseriesExport,
    ODSEValidationResult,
)

logger = logging.getLogger(__name__)


class ODSEExportService:
    """Service for exporting Sentinel data in ODS-E format."""

    # Equipment type to end_use mapping
    END_USE_MAPPING: dict[str, str] = {
        "CHILLER": "cooling",
        "AHU": "cooling",
        "FCU": "cooling",
        "VAV": "cooling",
        "CRAC": "cooling",
        "SPLIT": "cooling",
        "COOLING_TOWER": "cooling",
        "COLD_ROOM": "cooling",
        "KEF": "cooling",
        "BOILER": "heating",
        "DALI_CONTROLLER": "lighting",
        "LUMINAIRE": "lighting",
        "GEN": "generation",
        "SOLAR_INVERTER": "generation",
        "UPS": "other",
        "MSB": "other",
        "ATS": "other",
        "INCOMER": "other",
        "METER": "other",
    }

    # Health score to error_type mapping
    HEALTH_SCORE_THRESHOLDS = [
        (80, "normal"),
        (60, "warning"),
        (40, "critical"),
    ]

    async def export_timeseries(
        self,
        site_id: str,
        start: datetime,
        end: datetime,
        equipment_id: str | None = None,
        direction: str = "consumption",
        interval_minutes: int = 15,
    ) -> ODSETimeseriesExport:
        """
        Export Sentinel energy readings in ODS-E format.

        Args:
            site_id: Sentinel site identifier
            start: Start of export window (UTC)
            end: End of export window (UTC)
            equipment_id: Optional filter to single equipment
            direction: Energy flow direction (consumption/generation/net)
            interval_minutes: Aggregation interval

        Returns:
            ODSETimeseriesExport with records and metadata
        """
        logger.info(
            f"ODS-E export: site={site_id}, range={start.isoformat()} to {end.isoformat()}, "
            f"equipment={equipment_id or 'all'}, interval={interval_minutes}min"
        )

        # Fetch energy readings from repository
        # Note: This is a placeholder - actual implementation will use EnergyRepository
        records = await self._fetch_energy_readings(
            site_id=site_id,
            start=start,
            end=end,
            equipment_id=equipment_id,
            interval_minutes=interval_minutes,
        )

        # Map to ODS-E format
        odse_records = []
        validation_errors = []
        validation_warnings = []

        for reading in records:
            try:
                record = self._map_reading_to_odse(reading, direction)
                odse_records.append(record)
            except Exception as e:
                logger.warning(f"Failed to map reading to ODS-E: {e}")
                validation_errors.append(str(e))

        # Build asset metadata
        asset_metadata = await self._build_asset_metadata(site_id)

        # Validate
        is_valid = len(validation_errors) == 0

        return ODSETimeseriesExport(
            schema_version="0.4.0",
            source_system="sentinel-bms",
            site_id=site_id,
            exported_at=datetime.utcnow().isoformat() + "Z",
            record_count=len(odse_records),
            records=odse_records,
            asset_metadata=asset_metadata,
            odse_validation=ODSEValidationResult(
                valid=is_valid,
                errors=validation_errors,
                warnings=validation_warnings,
            ),
        )

    async def export_asset_metadata(
        self,
        site_id: str,
        equipment_type: str | None = None,
        include_health: bool = True,
    ) -> ODSEAssetExport:
        """
        Export Sentinel equipment inventory as ODS-E asset metadata.

        Args:
            site_id: Sentinel site identifier
            equipment_type: Optional filter by equipment type
            include_health: Whether to include health scores

        Returns:
            ODSEAssetExport with asset records
        """
        logger.info(
            f"ODS-E asset metadata export: site={site_id}, "
            f"type={equipment_type or 'all'}, include_health={include_health}"
        )

        # Fetch equipment from repository
        equipment_list = await self._fetch_equipment(
            site_id=site_id,
            equipment_type=equipment_type,
        )

        # Map to ODS-E asset records
        assets = []
        for eq in equipment_list:
            asset = self._map_equipment_to_odse_asset(eq, include_health)
            assets.append(asset)

        return ODSEAssetExport(
            schema_version="0.4.0",
            source_system="sentinel-bms",
            site_id=site_id,
            exported_at=datetime.utcnow().isoformat() + "Z",
            assets=assets,
        )

    def _map_reading_to_odse(self, reading: dict[str, Any], direction: str) -> ODSERecord:
        """Map a Sentinel energy reading to ODS-E record format."""
        timestamp = reading.get("timestamp")
        if isinstance(timestamp, datetime):
            timestamp = timestamp.isoformat()

        # Get equipment type for end_use mapping
        equipment_type = reading.get("equipment_type", "")
        end_use = self.END_USE_MAPPING.get(equipment_type.upper())

        # Map health score to error_type
        health_score = reading.get("health_score")
        error_type = self._map_health_to_error_type(health_score)

        # Determine tariff period
        ts = reading.get("timestamp")
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        tariff_period = self._get_eskom_tariff_period(ts) if ts else None

        return ODSERecord(
            timestamp=timestamp,
            kWh=reading.get("kwh", 0.0),
            error_type=error_type,
            direction=direction,
            fuel_type="electricity",
            end_use=end_use,
            kVA=reading.get("kva"),
            PF=reading.get("power_factor"),
            tariff_currency="ZAR",
            tariff_period=tariff_period,
        )

    def _map_equipment_to_odse_asset(
        self, equipment: dict[str, Any], include_health: bool
    ) -> ODSEAssetRecord:
        """Map Sentinel equipment to ODS-E asset record."""
        equipment_code = equipment.get("equipment_code", "")
        equipment_type = equipment.get("equipment_type", "unknown")

        # Extract floor from equipment code (e.g., S002-CHILLER-B1-001 -> B1)
        floor = None
        zone = None
        parts = equipment_code.split("-")
        if len(parts) >= 3:
            floor_zone = parts[2] if len(parts) > 2 else None
            if floor_zone:
                # Floor codes typically like B1, L3, G, R
                floor = floor_zone
                zone = equipment.get("zone") or parts[3] if len(parts) > 3 else None

        # Build location
        site_config = equipment.get("site_config", {})
        location = ODSELocation(
            country_code=site_config.get("country_code", "ZA"),
            municipality_id=site_config.get("municipality_id", "za.gt.johannesburg"),
            municipality_name=site_config.get("municipality_name", "City of Johannesburg"),
            timezone=site_config.get("timezone", "Africa/Johannesburg"),
            latitude=site_config.get("latitude"),
            longitude=site_config.get("longitude"),
        )

        # Build sentinel extensions
        health_score = equipment.get("health_score") if include_health else None
        last_seen = equipment.get("last_seen")
        if isinstance(last_seen, datetime):
            last_seen = last_seen.isoformat()

        sentinel_extensions = ODSESentinelExtensions(
            health_score=health_score,
            equipment_code=equipment_code,
            floor=floor,
            zone=zone,
            protocol=equipment.get("protocol", "BACnet/IP"),
            last_seen=last_seen,
        )

        return ODSEAssetRecord(
            asset_id=equipment_code,
            asset_type=equipment_type.lower(),
            capacity_kw=equipment.get("capacity_kw"),
            site_id=equipment.get("site_id", ""),
            oem=equipment.get("manufacturer"),
            location=location,
            sentinel_extensions=sentinel_extensions,
        )

    def _map_health_to_error_type(self, health_score: float | None) -> str:
        """Map Sentinel health score to ODS-E error_type."""
        if health_score is None:
            return "unknown"

        for threshold, error_type in self.HEALTH_SCORE_THRESHOLDS:
            if health_score >= threshold:
                return error_type

        return "fault"

    def _get_eskom_tariff_period(self, ts: datetime) -> str:
        """
        Return Eskom Megaflex tariff period for a ZA timestamp.

        Simplified schedule:
        - Peak: 07:00-10:00, 18:00-20:00 (weekdays)
        - Standard: 06:00-07:00, 10:00-18:00, 20:00-22:00 (weekdays)
        - Off-peak: All other times + weekends
        """
        hour = ts.hour
        weekday = ts.weekday()  # 0=Monday, 6=Sunday

        # Weekend is always off-peak
        if weekday >= 5:
            return "off_peak"

        # Weekday schedule
        if 7 <= hour < 10 or 18 <= hour < 20:
            return "peak"
        elif 6 <= hour < 7 or 10 <= hour < 18 or 20 <= hour < 22:
            return "standard"
        else:
            return "off_peak"

    async def _fetch_energy_readings(
        self,
        site_id: str,
        start: datetime,
        end: datetime,
        equipment_id: str | None,
        interval_minutes: int,
    ) -> list[dict[str, Any]]:
        """
        Fetch energy readings from repository.

        TODO: Replace with actual EnergyRepository integration.
        For now, returns mock data for testing.
        """
        # Placeholder: This should call EnergyRepository.get_interval_readings()
        # For testing/demo purposes, return mock data
        logger.warning("Using mock energy data - integrate with EnergyRepository")

        mock_readings = []
        current = start
        while current < end:
            mock_readings.append({
                "timestamp": current,
                "kwh": 12.4 + (current.hour % 5),  # Mock varying consumption
                "equipment_type": "CHILLER",
                "health_score": 82.0,
                "power_factor": 0.95,
                "kva": 13.1,
            })
            current += timedelta(minutes=interval_minutes)

        return mock_readings

    async def _fetch_equipment(
        self,
        site_id: str,
        equipment_type: str | None,
    ) -> list[dict[str, Any]]:
        """
        Fetch equipment from repository.

        TODO: Replace with actual EquipmentRepository integration.
        For now, returns mock data for testing.
        """
        # Placeholder: This should call EquipmentRepository
        logger.warning("Using mock equipment data - integrate with EquipmentRepository")

        mock_equipment = [
            {
                "equipment_code": "S002-CHILLER-B1-001",
                "equipment_type": "CHILLER",
                "capacity_kw": 350.0,
                "site_id": site_id,
                "manufacturer": "Carrier",
                "protocol": "BACnet/IP",
                "health_score": 82,
                "last_seen": datetime.utcnow(),
                "zone": "plant-room",
                "site_config": {
                    "country_code": "ZA",
                    "municipality_id": "za.gt.johannesburg",
                    "municipality_name": "City of Johannesburg",
                    "timezone": "Africa/Johannesburg",
                    "latitude": -26.1076,
                    "longitude": 28.0567,
                },
            },
            {
                "equipment_code": "S002-AHU-L1-001",
                "equipment_type": "AHU",
                "capacity_kw": 75.0,
                "site_id": site_id,
                "manufacturer": "Siemens",
                "protocol": "BACnet/IP",
                "health_score": 91,
                "last_seen": datetime.utcnow(),
                "zone": "office-north",
                "site_config": {
                    "country_code": "ZA",
                    "municipality_id": "za.gt.johannesburg",
                    "timezone": "Africa/Johannesburg",
                },
            },
        ]

        if equipment_type:
            mock_equipment = [
                eq for eq in mock_equipment
                if eq["equipment_type"].upper() == equipment_type.upper()
            ]

        return mock_equipment

    async def _build_asset_metadata(self, site_id: str) -> ODSEAssetMetadata:
        """Build ODS-E asset metadata for a site."""
        # TODO: Fetch actual site configuration
        return ODSEAssetMetadata(
            asset_id=site_id,
            asset_type="commercial_building",
            site_id=site_id,
            location=ODSELocation(
                country_code="ZA",
                municipality_id="za.gt.johannesburg",
                municipality_name="City of Johannesburg",
                timezone="Africa/Johannesburg",
                latitude=-26.1076,
                longitude=28.0567,
            ),
            building=ODSEBuilding(
                building_type="office",
                floor_area_sqm=4500.0,
                vintage="2000_to_2003",
                climate_zone="H4",
            ),
        )


# Singleton instance
odse_service = ODSEExportService()
