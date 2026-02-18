"""Pydantic models for integration/log ingestion."""

from datetime import datetime
from typing import List, Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field


class SourceType(str, Enum):
    BMS_ALARM = "bms_alarm"
    BMS_TREND = "bms_trend"
    CAFM_ASSET = "cafm_asset"
    CAFM_WORKORDER = "cafm_workorder"
    BCC_ALARM = "bcc_alarm"
    DALI_LIGHTING = "dali_lighting"


class ConnectionType(str, Enum):
    FILE_DROP = "file_drop"
    SFTP = "sftp"
    DATABASE = "database"
    API = "api"
    MANUAL_UPLOAD = "manual_upload"
    NIAGARA_BACNET = "niagara_bacnet"


class FileFormat(str, Enum):
    CSV = "csv"
    EXCEL = "excel"
    JSON = "json"
    XML = "xml"


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AlarmState(str, Enum):
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    CLEARED = "cleared"


class MatchConfidence(str, Enum):
    EXACT = "exact"
    FUZZY = "fuzzy"
    MANUAL = "manual"
    UNMATCHED = "unmatched"


# Log Source Configuration
class LogSourceBase(BaseModel):
    name: str
    source_type: SourceType
    connection_type: ConnectionType
    file_pattern: Optional[str] = None
    folder_path: Optional[str] = None
    file_format: Optional[FileFormat] = None
    delimiter: str = ","
    date_format: str = "YYYY-MM-DD HH:MI:SS"
    timezone: str = "Africa/Johannesburg"
    sync_frequency_minutes: int = 15


class LogSourceCreate(LogSourceBase):
    building_id: str


class LogSourceUpdate(BaseModel):
    name: Optional[str] = None
    file_pattern: Optional[str] = None
    folder_path: Optional[str] = None
    file_format: Optional[FileFormat] = None
    delimiter: Optional[str] = None
    date_format: Optional[str] = None
    timezone: Optional[str] = None
    sync_frequency_minutes: Optional[int] = None
    is_active: Optional[bool] = None


class LogSource(LogSourceBase):
    id: str
    building_id: str
    vendor_pattern: Optional[str] = None
    is_active: bool = False
    last_sync_at: Optional[datetime] = None
    last_sync_status: Optional[str] = None
    last_sync_records: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Column Mapping
class ColumnMappingCreate(BaseModel):
    source_column: str
    sentinel_field: str
    transform: Optional[str] = None
    transform_params: Optional[Dict[str, Any]] = None


class ColumnMapping(ColumnMappingCreate):
    id: str
    log_source_id: str

    class Config:
        from_attributes = True


# Point-Asset Mapping
class PointAssetMappingCreate(BaseModel):
    bms_point_id: str
    extracted_asset_id: Optional[str] = None
    cafm_asset_id: Optional[str] = None
    parameter_name: Optional[str] = None
    parameter_type: Optional[str] = None
    match_confidence: MatchConfidence = MatchConfidence.UNMATCHED


class PointAssetMapping(PointAssetMappingCreate):
    id: str
    building_id: str
    is_verified: bool = False
    created_at: datetime

    class Config:
        from_attributes = True


# Parsed/Normalized Records
class ParsedAlarm(BaseModel):
    """A single parsed alarm record."""
    occurred_at: datetime
    point_id: str
    asset_id: Optional[str] = None
    alarm_code: Optional[str] = None
    sentinel_code: Optional[str] = None
    description: Optional[str] = None
    value: Optional[float] = None
    threshold: Optional[float] = None
    unit: Optional[str] = None
    severity: Optional[Severity] = None
    state: Optional[AlarmState] = None
    acknowledged_by: Optional[str] = None
    notes: Optional[str] = None
    raw_data: Dict[str, Any] = Field(default_factory=dict)


class ParsedTrend(BaseModel):
    """A single parsed trend record."""
    recorded_at: datetime
    point_id: str
    asset_id: Optional[str] = None
    parameter_name: Optional[str] = None
    value: float
    unit: Optional[str] = None
    quality: str = "good"


# Format Detection Results
class FormatDetectionResult(BaseModel):
    """Result of auto-detecting file format."""
    file_format: FileFormat
    delimiter: str
    date_format: str
    vendor_pattern: Optional[str] = None
    columns: List[str]
    row_count: int
    date_range_start: Optional[datetime] = None
    date_range_end: Optional[datetime] = None
    sample_rows: List[Dict[str, Any]] = Field(default_factory=list)
    suggested_mappings: Dict[str, str] = Field(default_factory=dict)


# Validation Results
class ParseValidationError(BaseModel):
    row: int
    field: str
    message: str
    value: Optional[str] = None


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
    errors: List[ParseValidationError] = Field(default_factory=list)
    warnings: List[ParseValidationWarning] = Field(default_factory=list)
    parsed_alarms: List[ParsedAlarm] = Field(default_factory=list)
    parsed_trends: List[ParsedTrend] = Field(default_factory=list)
    unmatched_points: List[str] = Field(default_factory=list)


# Asset Matching Results
class AssetMatchResult(BaseModel):
    """Result of matching a BMS point to CAFM asset."""
    bms_point_id: str
    extracted_asset_id: str
    parameter_name: Optional[str] = None
    cafm_asset_id: Optional[str] = None
    cafm_asset_description: Optional[str] = None
    confidence: MatchConfidence
    alternatives: List[Dict[str, str]] = Field(default_factory=list)


class BulkMatchResult(BaseModel):
    """Result of bulk point-to-asset matching."""
    total_points: int
    matched_exact: int
    matched_fuzzy: int
    unmatched: int
    matches: List[AssetMatchResult] = Field(default_factory=list)


# ==================== Building Status / Go-Live Workflow ====================

class BuildingStatus(str, Enum):
    """Building activation status for go-live workflow."""
    DRAFT = "draft"
    PENDING_VALIDATION = "pending_validation"
    ACTIVE = "active"
    SUSPENDED = "suspended"


class ChecklistItem(BaseModel):
    """Single validation checklist item."""
    id: str
    category: str  # 'data_source', 'point_mapping', 'data_quality', 'configuration'
    name: str
    description: str
    status: str  # 'pass', 'fail', 'warning', 'not_checked'
    value: Optional[Any] = None
    threshold: Optional[Any] = None
    details: Optional[str] = None


class ValidationChecklist(BaseModel):
    """Complete go-live validation checklist."""
    building_id: str
    building_name: Optional[str] = None
    status: BuildingStatus
    checked_at: datetime
    items: List[ChecklistItem]
    summary: Dict[str, int]  # {passed: int, failed: int, warnings: int}
    can_activate: bool
    blocking_issues: List[str] = Field(default_factory=list)
