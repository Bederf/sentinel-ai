"""Pydantic models for integration/log ingestion."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SourceType(StrEnum):
    BMS_ALARM = "bms_alarm"
    BMS_TREND = "bms_trend"
    CAFM_ASSET = "cafm_asset"
    CAFM_WORKORDER = "cafm_workorder"
    BCC_ALARM = "bcc_alarm"
    DALI_LIGHTING = "dali_lighting"


class ConnectionType(StrEnum):
    FILE_DROP = "file_drop"
    SFTP = "sftp"
    DATABASE = "database"
    API = "api"
    MANUAL_UPLOAD = "manual_upload"
    NIAGARA_BACNET = "niagara_bacnet"


class FileFormat(StrEnum):
    CSV = "csv"
    EXCEL = "excel"
    JSON = "json"
    XML = "xml"


class Severity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AlarmState(StrEnum):
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    CLEARED = "cleared"


class MatchConfidence(StrEnum):
    EXACT = "exact"
    FUZZY = "fuzzy"
    MANUAL = "manual"
    UNMATCHED = "unmatched"


# Log Source Configuration
class LogSourceBase(BaseModel):
    name: str
    source_type: SourceType
    connection_type: ConnectionType
    file_pattern: str | None = None
    folder_path: str | None = None
    file_format: FileFormat | None = None
    delimiter: str = ","
    date_format: str = "YYYY-MM-DD HH:MI:SS"
    timezone: str = "Africa/Johannesburg"
    sync_frequency_minutes: int = 15


class LogSourceCreate(LogSourceBase):
    site_id: str


class LogSourceUpdate(BaseModel):
    name: str | None = None
    file_pattern: str | None = None
    folder_path: str | None = None
    file_format: FileFormat | None = None
    delimiter: str | None = None
    date_format: str | None = None
    timezone: str | None = None
    sync_frequency_minutes: int | None = None
    is_active: bool | None = None


class LogSource(LogSourceBase):
    model_config = ConfigDict(from_attributes=True)
    id: str
    site_id: str
    vendor_pattern: str | None = None
    is_active: bool = False
    last_sync_at: datetime | None = None
    last_sync_status: str | None = None
    last_sync_records: int | None = None
    created_at: datetime
    updated_at: datetime


# Column Mapping
class ColumnMappingCreate(BaseModel):
    source_column: str
    sentinel_field: str
    transform: str | None = None
    transform_params: dict[str, Any] | None = None


class ColumnMapping(ColumnMappingCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    log_source_id: str


# Point-Asset Mapping
class PointAssetMappingCreate(BaseModel):
    bms_point_id: str
    extracted_asset_id: str | None = None
    cafm_asset_id: str | None = None
    parameter_name: str | None = None
    parameter_type: str | None = None
    match_confidence: MatchConfidence = MatchConfidence.UNMATCHED


class PointAssetMapping(PointAssetMappingCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    site_id: str
    is_verified: bool = False
    created_at: datetime


# Parsed/Normalized Records
class ParsedAlarm(BaseModel):
    """A single parsed alarm record."""

    occurred_at: datetime
    point_id: str
    asset_id: str | None = None
    alarm_code: str | None = None
    sentinel_code: str | None = None
    description: str | None = None
    value: float | None = None
    threshold: float | None = None
    unit: str | None = None
    severity: Severity | None = None
    state: AlarmState | None = None
    acknowledged_by: str | None = None
    notes: str | None = None
    raw_data: dict[str, Any] = Field(default_factory=dict)


class ParsedTrend(BaseModel):
    """A single parsed trend record."""

    recorded_at: datetime
    point_id: str
    asset_id: str | None = None
    parameter_name: str | None = None
    value: float
    unit: str | None = None
    quality: str = "good"


# Format Detection Results
class FormatDetectionResult(BaseModel):
    """Result of auto-detecting file format."""

    file_format: FileFormat
    delimiter: str
    date_format: str
    vendor_pattern: str | None = None
    columns: list[str]
    row_count: int
    date_range_start: datetime | None = None
    date_range_end: datetime | None = None
    sample_rows: list[dict[str, Any]] = Field(default_factory=list)
    suggested_mappings: dict[str, str] = Field(default_factory=dict)


# Validation Results
class ParseValidationError(BaseModel):
    row: int
    field: str
    message: str
    value: str | None = None


class ParseValidationWarning(BaseModel):
    row: int
    field: str
    message: str


class ParseResult(BaseModel):
    """Result of parsing a log file."""

    total_rows: int
    valid_rows: int
    error_count: int
    warning_count: int
    errors: list[ParseValidationError] = Field(default_factory=list)
    warnings: list[ParseValidationWarning] = Field(default_factory=list)
    parsed_alarms: list[ParsedAlarm] = Field(default_factory=list)
    parsed_trends: list[ParsedTrend] = Field(default_factory=list)
    unmatched_points: list[str] = Field(default_factory=list)


# Asset Matching Results
class AssetMatchResult(BaseModel):
    """Result of matching a BMS point to CAFM asset."""

    bms_point_id: str
    extracted_asset_id: str
    parameter_name: str | None = None
    cafm_asset_id: str | None = None
    cafm_asset_description: str | None = None
    confidence: MatchConfidence
    alternatives: list[dict[str, str]] = Field(default_factory=list)


class BulkMatchResult(BaseModel):
    """Result of bulk point-to-asset matching."""

    total_points: int
    matched_exact: int
    matched_fuzzy: int
    unmatched: int
    matches: list[AssetMatchResult] = Field(default_factory=list)


# ==================== Building Status / Go-Live Workflow ====================


class BuildingStatus(StrEnum):
    """Building activation status for go-live workflow."""

    DRAFT = "draft"
    PENDING_VALIDATION = "pending_validation"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    SHADOW_LIVE = "shadow_live"
    LIVE_CONTROL = "live_control"


class ChecklistItem(BaseModel):
    """Single validation checklist item."""

    id: str
    category: str  # 'data_source', 'point_mapping', 'data_quality', 'configuration'
    name: str
    description: str
    status: str  # 'pass', 'fail', 'warning', 'not_checked'
    value: Any | None = None
    threshold: Any | None = None
    details: str | None = None


class ValidationChecklist(BaseModel):
    """Complete go-live validation checklist."""

    site_id: str
    site_name: str | None = None
    status: BuildingStatus
    checked_at: datetime
    items: list[ChecklistItem]
    summary: dict[str, int]  # {passed: int, failed: int, warnings: int}
    can_activate: bool
    blocking_issues: list[str] = Field(default_factory=list)
