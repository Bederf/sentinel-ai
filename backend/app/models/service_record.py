"""Service record models for Phase 41 ML Engineer Knowledge Capture."""

from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class ServiceType(str, Enum):
    MINOR = "minor"
    MAJOR = "major"
    BREAKDOWN = "breakdown"
    CALLOUT = "callout"


class ServiceStatus(str, Enum):
    NOTIFIED = "notified"
    IN_PROGRESS = "in_progress"
    DATA_COLLECTION = "data_collection"
    COMPLETE = "complete"
    CLOSED = "closed"


class AttachmentType(str, Enum):
    SERVICE_SHEET = "service_sheet"
    AUDIO_RECORDING = "audio_recording"
    OIL_SAMPLE = "oil_sample"
    DIESEL_SAMPLE = "diesel_sample"
    THERMAL_IMAGE = "thermal_image"
    ISSUE_PHOTO = "issue_photo"
    BEFORE_PHOTO = "before_photo"
    AFTER_PHOTO = "after_photo"
    LOAD_TEST_VIDEO = "load_test_video"
    OIL_ANALYSIS_REPORT = "oil_analysis_report"


class SourceType(str, Enum):
    OCR = "ocr"
    MANUAL = "manual"
    SENSOR = "sensor"


class ServiceReading(BaseModel):
    """Reading extracted from service sheet."""

    model_config = ConfigDict(from_attributes=True)

    id: Optional[str] = None
    reading_type: str  # hour_meter, battery_voltage, oil_level, etc.
    value: str
    unit: Optional[str] = None
    numeric_value: Optional[float] = None
    source: SourceType = SourceType.MANUAL
    confidence: Optional[float] = Field(None, ge=0, le=1)


class ServiceAttachment(BaseModel):
    """Photo, audio, or document from service visit."""

    model_config = ConfigDict(from_attributes=True)

    id: Optional[str] = None
    attachment_type: AttachmentType
    file_path: str
    file_name: Optional[str] = None
    file_size_bytes: Optional[int] = None
    mime_type: Optional[str] = None
    extracted_data: Optional[Dict[str, Any]] = None
    analysis_status: Optional[str] = "pending"
    created_at: Optional[datetime] = None


class ServiceObservation(BaseModel):
    """Technician observation (voice or text)."""

    model_config = ConfigDict(from_attributes=True)

    id: Optional[str] = None
    observation_type: str  # voice_note or text
    content: str
    audio_file_path: Optional[str] = None
    duration_seconds: Optional[float] = None
    sentiment: Optional[str] = None
    key_phrases: Optional[List[str]] = None
    issue_flags: Optional[List[str]] = None
    created_at: Optional[datetime] = None


class DiagnosticContext(BaseModel):
    """Context from original alert/diagnosis - passed to data collection."""

    model_config = ConfigDict(from_attributes=True)

    fault_type: Optional[str] = None  # e.g., "fcu_valve_stuck"
    fault_code: Optional[str] = None  # e.g., "E04"
    fault_description: Optional[str] = None  # e.g., "FCU valve stuck at 15%"
    original_reading: Optional[float] = None  # e.g., 25.0 (temp was 25°C)
    setpoint: Optional[float] = None  # e.g., 21.0
    deviation: Optional[float] = None  # e.g., 4.0
    faulty_equipment: Optional[str] = None  # e.g., "S002-FCU-L0-C"
    zone_id: Optional[str] = None  # e.g., "Zone-L0-C"
    recommended_actions: List[str] = Field(default_factory=list)
    parts_required: List[str] = Field(default_factory=list)
    severity: Optional[str] = None  # critical, warning, info


class ServiceRecord(BaseModel):
    """Main service record for a service visit."""

    model_config = ConfigDict(from_attributes=True)

    id: Optional[str] = None
    code: str
    work_order_id: Optional[str] = None
    equipment_id: str
    site_id: Optional[str] = None
    service_type: ServiceType
    technician_id: str
    technician_name: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    status: ServiceStatus = ServiceStatus.NOTIFIED
    telegram_chat_id: Optional[str] = None
    telegram_message_id: Optional[str] = None
    current_prompt: Optional[str] = None
    items_collected: List[str] = Field(default_factory=list)
    diagnostic_context: Optional[DiagnosticContext] = None  # Original alert context
    confirmed_fault: Optional[str] = None  # Technician's confirmed root cause
    actual_repair: Optional[str] = None  # What was actually done
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ServiceRecordDetail(ServiceRecord):
    """Service record with related data."""

    model_config = ConfigDict(from_attributes=True)

    readings: List[ServiceReading] = Field(default_factory=list)
    attachments: List[ServiceAttachment] = Field(default_factory=list)
    observations: List[ServiceObservation] = Field(default_factory=list)


class ServiceRecordCreate(BaseModel):
    """DTO for creating a service record."""

    work_order_id: Optional[str] = None
    equipment_id: str
    site_id: Optional[str] = None
    service_type: ServiceType
    technician_id: str
    technician_name: str
    telegram_chat_id: Optional[str] = None


class ServiceRecordUpdate(BaseModel):
    """DTO for updating a service record."""

    status: Optional[ServiceStatus] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    current_prompt: Optional[str] = None
    items_collected: Optional[List[str]] = None


# ML Data Templates
class MLDataTemplate(BaseModel):
    """Template for required ML data per equipment type and service."""

    equipment_type: str
    service_type: ServiceType
    required: List[str]
    optional: List[str] = Field(default_factory=list)
    prompts: Dict[str, str]


# Example template structure
generator_minor_template = MLDataTemplate(
    equipment_type="generator",
    service_type=ServiceType.MINOR,
    required=["service_sheet", "audio_recording", "oil_sample"],
    optional=["diesel_sample", "thermal_image"],
    prompts={
        "service_sheet": "📷 Send a photo of your completed service sheet",
        "audio_recording": "🔊 Record 10 seconds of the engine running",
        "oil_sample": "🛢️ Photo of oil sample (hold bottle up to light)",
        "diesel_sample": "⛽ Photo of diesel sample (hold up to light)",
    },
)
