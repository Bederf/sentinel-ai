"""Service record models for Phase 41 ML Engineer Knowledge Capture."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ServiceType(StrEnum):
    MINOR = "minor"
    MAJOR = "major"
    BREAKDOWN = "breakdown"
    CALLOUT = "callout"


class ServiceStatus(StrEnum):
    NOTIFIED = "notified"
    IN_PROGRESS = "in_progress"
    DATA_COLLECTION = "data_collection"
    COMPLETE = "complete"
    CLOSED = "closed"


class AttachmentType(StrEnum):
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


class SourceType(StrEnum):
    OCR = "ocr"
    MANUAL = "manual"
    SENSOR = "sensor"


class ServiceReading(BaseModel):
    """Reading extracted from service sheet."""

    model_config = ConfigDict(from_attributes=True)

    id: str | None = None
    reading_type: str  # hour_meter, battery_voltage, oil_level, etc.
    value: str
    unit: str | None = None
    numeric_value: float | None = None
    source: SourceType = SourceType.MANUAL
    confidence: float | None = Field(None, ge=0, le=1)


class ServiceAttachment(BaseModel):
    """Photo, audio, or document from service visit."""

    model_config = ConfigDict(from_attributes=True)

    id: str | None = None
    attachment_type: AttachmentType
    file_path: str
    file_name: str | None = None
    file_size_bytes: int | None = None
    mime_type: str | None = None
    extracted_data: dict[str, Any] | None = None
    analysis_status: str | None = "pending"
    created_at: datetime | None = None


class ServiceObservation(BaseModel):
    """Technician observation (voice or text)."""

    model_config = ConfigDict(from_attributes=True)

    id: str | None = None
    observation_type: str  # voice_note or text
    content: str
    audio_file_path: str | None = None
    duration_seconds: float | None = None
    sentiment: str | None = None
    key_phrases: list[str] | None = None
    issue_flags: list[str] | None = None
    created_at: datetime | None = None


class DiagnosticContext(BaseModel):
    """Context from original alert/diagnosis - passed to data collection."""

    model_config = ConfigDict(from_attributes=True)

    fault_type: str | None = None  # e.g., "fcu_valve_stuck"
    fault_code: str | None = None  # e.g., "E04"
    fault_description: str | None = None  # e.g., "FCU valve stuck at 15%"
    original_reading: float | None = None  # e.g., 25.0 (temp was 25°C)
    setpoint: float | None = None  # e.g., 21.0
    deviation: float | None = None  # e.g., 4.0
    faulty_equipment: str | None = None  # e.g., "S002-FCU-L0-C"
    zone_id: str | None = None  # e.g., "Zone-L0-C"
    recommended_actions: list[str] = Field(default_factory=list)
    parts_required: list[str] = Field(default_factory=list)
    severity: str | None = None  # critical, warning, info


class ServiceRecord(BaseModel):
    """Main service record for a service visit."""

    model_config = ConfigDict(from_attributes=True)

    id: str | None = None
    code: str
    work_order_id: str | None = None
    equipment_id: str
    site_id: str | None = None
    service_type: ServiceType
    technician_id: str
    technician_name: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    status: ServiceStatus = ServiceStatus.NOTIFIED
    telegram_chat_id: str | None = None
    telegram_message_id: str | None = None
    current_prompt: str | None = None
    items_collected: list[str] = Field(default_factory=list)
    diagnostic_context: DiagnosticContext | None = None  # Original alert context
    confirmed_fault: str | None = None  # Technician's confirmed root cause
    actual_repair: str | None = None  # What was actually done
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ServiceRecordDetail(ServiceRecord):
    """Service record with related data."""

    model_config = ConfigDict(from_attributes=True)

    readings: list[ServiceReading] = Field(default_factory=list)
    attachments: list[ServiceAttachment] = Field(default_factory=list)
    observations: list[ServiceObservation] = Field(default_factory=list)


class ServiceRecordCreate(BaseModel):
    """DTO for creating a service record."""

    work_order_id: str | None = None
    equipment_id: str
    site_id: str | None = None
    service_type: ServiceType
    technician_id: str
    technician_name: str
    telegram_chat_id: str | None = None


class ServiceRecordUpdate(BaseModel):
    """DTO for updating a service record."""

    status: ServiceStatus | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    current_prompt: str | None = None
    items_collected: list[str] | None = None


# ML Data Templates
class MLDataTemplate(BaseModel):
    """Template for required ML data per equipment type and service."""

    equipment_type: str
    service_type: ServiceType
    required: list[str]
    optional: list[str] = Field(default_factory=list)
    prompts: dict[str, str]


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
