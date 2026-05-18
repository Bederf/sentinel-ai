"""
ODS-E (Open Data Schema for Energy) Pydantic models.

Defines the data structures for ODS-E v0.4.0 compliant energy data export.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ODSERecord(BaseModel):
    """Single ODS-E energy timeseries record."""

    timestamp: str = Field(..., description="ISO 8601 UTC timestamp")
    kWh: float = Field(..., description="Energy consumption in kilowatt-hours")
    error_type: Literal["normal", "warning", "critical", "fault", "unknown"] = Field(
        default="normal", description="Data quality/error classification"
    )
    direction: Literal["consumption", "generation", "net"] = Field(
        default="consumption", description="Energy flow direction"
    )
    fuel_type: str = Field(default="electricity", description="Energy source type")
    end_use: str | None = Field(default=None, description="End use category (cooling, heating, lighting, etc.)")
    kVA: float | None = Field(default=None, description="Apparent power in kilovolt-amperes")
    PF: float | None = Field(default=None, description="Power factor (0.0-1.0)", ge=0.0, le=1.0)
    tariff_currency: str | None = Field(default=None, description="Currency code (e.g., ZAR)")
    tariff_period: Literal["peak", "standard", "off_peak"] | None = Field(
        default=None, description="Time-of-use tariff period"
    )


class ODSERecordWithValidation(ODSERecord):
    """ODS-E record with optional validation warnings."""

    validation_warnings: list[str] | None = Field(default=None, exclude=True)


class ODSERecords(BaseModel):
    """Collection of ODS-E energy records with metadata."""

    records: list[ODSERecord]
    count: int


class ODSELocation(BaseModel):
    """ODS-E location metadata."""

    country_code: str = Field(..., description="ISO 3166-1 alpha-2 country code")
    municipality_id: str | None = Field(default=None, description="Municipality identifier")
    municipality_name: str | None = Field(default=None, description="Human-readable municipality name")
    timezone: str | None = Field(default=None, description="IANA timezone identifier")
    latitude: float | None = Field(default=None, description="Latitude in decimal degrees")
    longitude: float | None = Field(default=None, description="Longitude in decimal degrees")


class ODSEBuilding(BaseModel):
    """ODS-E building metadata."""

    building_type: str | None = Field(default=None, description="Building type (office, retail, etc.)")
    floor_area_sqm: float | None = Field(default=None, description="Total floor area in square meters")
    vintage: str | None = Field(default=None, description="Construction vintage or year range")
    climate_zone: str | None = Field(default=None, description="Climate zone classification")


class ODSEAssetMetadata(BaseModel):
    """ODS-E asset/site metadata for export."""

    asset_id: str = Field(..., description="Unique asset identifier")
    asset_type: str = Field(..., description="Asset type (commercial_building, etc.)")
    site_id: str = Field(..., description="Site identifier")
    location: ODSELocation
    building: ODSEBuilding | None = None


class ODSEValidationResult(BaseModel):
    """ODS-E validation result."""

    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ODSETimeseriesExport(BaseModel):
    """Complete ODS-E timeseries export payload."""

    schema_version: str = Field(default="0.4.0", description="ODS-E schema version")
    source_system: str = Field(default="sentinel-bms", description="Source system identifier")
    site_id: str = Field(..., description="Sentinel site identifier")
    exported_at: str = Field(..., description="ISO 8601 UTC export timestamp")
    record_count: int = Field(..., description="Number of records in export")
    records: list[ODSERecord]
    asset_metadata: ODSEAssetMetadata
    odse_validation: ODSEValidationResult


class ODSESentinelExtensions(BaseModel):
    """Sentinel-specific extensions to ODS-E asset metadata."""

    health_score: int | None = Field(default=None, ge=0, le=100, description="Sentinel health score 0-100")
    equipment_code: str = Field(..., description="Sentinel equipment code")
    floor: str | None = Field(default=None, description="Building floor")
    zone: str | None = Field(default=None, description="Zone within floor")
    protocol: str | None = Field(default=None, description="Communication protocol (BACnet/IP, Modbus, etc.)")
    last_seen: str | None = Field(default=None, description="ISO 8601 UTC last communication timestamp")


class ODSEAssetRecord(BaseModel):
    """Single ODS-E asset record with Sentinel extensions."""

    asset_id: str = Field(..., description="Unique asset identifier")
    asset_type: str = Field(..., description="Asset type (chiller, ahu, meter, etc.)")
    capacity_kw: float | None = Field(default=None, description="Rated capacity in kilowatts")
    site_id: str = Field(..., description="Site identifier")
    oem: str | None = Field(default=None, description="Original equipment manufacturer")
    location: ODSELocation
    sentinel_extensions: ODSESentinelExtensions | None = None


class ODSEAssetExport(BaseModel):
    """ODS-E asset metadata export payload."""

    schema_version: str = Field(default="0.4.0")
    source_system: str = Field(default="sentinel-bms")
    site_id: str = Field(...)
    exported_at: str = Field(...)
    assets: list[ODSEAssetRecord]


class ODSEExportRequest(BaseModel):
    """Request parameters for ODS-E timeseries export."""

    site_id: str
    start: datetime
    end: datetime
    equipment_id: str | None = None
    direction: Literal["consumption", "generation", "net"] = "consumption"
    interval_minutes: int = Field(default=15, ge=1, le=1440)
    format: Literal["json", "csv"] = "json"


class ODSEAssetMetadataRequest(BaseModel):
    """Request parameters for ODS-E asset metadata export."""

    site_id: str
    equipment_type: str | None = None
    include_health: bool = True
