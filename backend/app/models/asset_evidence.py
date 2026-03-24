"""
Asset Evidence Data Models (Phase 171-02)

Pydantic models for evidence data validation and serialization.
Supports classification, normalization, and CRUD operations.
"""

from enum import Enum
from typing import Optional
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


# ============================================================================
# Enums (matching Supabase enum types)
# ============================================================================


class SourceType(str, Enum):
    """Evidence source type."""

    UPLOAD = "upload"
    FEEDBACK = "feedback"
    TELEMETRY = "telemetry"
    INSPECTION = "inspection"
    CERTIFICATE = "certificate"
    INCIDENT = "incident"
    REPAIR = "repair"
    OBSERVATION = "observation"
    MEDIA = "media"
    TELEMETRY_SUMMARY = "telemetry_summary"


class ArtifactType(str, Enum):
    """Evidence artifact type."""

    DOCUMENT = "document"
    AUDIO = "audio"
    IMAGE = "image"
    STRUCTURED_DATA = "structured_data"
    METADATA = "metadata"


class EvidenceClass(str, Enum):
    """Evidence classification (business meaning)."""

    SERVICE_REPORT = "service_report"
    INSPECTION_CHECKLIST = "inspection_checklist"
    CONDITION_ASSESSMENT = "condition_assessment"
    CERTIFICATE = "certificate"
    INCIDENT_REPORT = "incident_report"
    REPAIR_EVENT = "repair_event"
    TECHNICIAN_OBSERVATION = "technician_observation"
    MEDIA_EVIDENCE = "media_evidence"
    TELEMETRY_SUMMARY = "telemetry_summary"


class ProvenanceType(str, Enum):
    """Evidence provenance (origin)."""

    USER_UPLOAD = "user_upload"
    SYSTEM_INGEST = "system_ingest"
    ML_ENRICHMENT = "ml_enrichment"
    MANUAL_ENTRY = "manual_entry"


# ============================================================================
# Pydantic Models
# ============================================================================


class CreateAssetEvidenceInput(BaseModel):
    """Input model for creating new asset evidence."""

    site_id: UUID
    equipment_id: UUID
    source_type: SourceType
    artifact_type: ArtifactType
    evidence_class: EvidenceClass
    document_id: Optional[UUID] = None
    source_ref: Optional[str] = None
    event_timestamp: datetime
    raw_payload: dict = Field(default_factory=dict)
    normalized_payload: dict = Field(default_factory=dict)
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    assessment_relevance: bool = True
    provenance_type: ProvenanceType
    provenance_uri: str
    uploader_user_id: Optional[UUID] = None

    class Config:
        use_enum_values = False  # Keep enums as objects, not strings


class AssetEvidence(BaseModel):
    """Complete asset evidence record (from database)."""

    evidence_id: UUID
    site_id: UUID
    equipment_id: UUID
    source_type: SourceType
    artifact_type: ArtifactType
    evidence_class: EvidenceClass
    document_id: Optional[UUID] = None
    source_ref: Optional[str] = None
    event_timestamp: datetime
    raw_payload: dict
    normalized_payload: dict
    confidence_score: float
    assessment_relevance: bool
    provenance_type: ProvenanceType
    provenance_uri: str
    uploader_user_id: Optional[UUID] = None
    uploader_user_email: Optional[str] = None
    created_at: datetime
    supersedes_evidence_id: Optional[UUID] = None

    class Config:
        from_attributes = True
        use_enum_values = False


class AssetEvidenceFilter(BaseModel):
    """Filter model for flexible evidence querying."""

    site_id: Optional[UUID] = None
    equipment_id: Optional[UUID] = None
    source_type: Optional[SourceType] = None
    evidence_class: Optional[EvidenceClass] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    active_only: bool = True  # supersedes_evidence_id IS NULL

    class Config:
        use_enum_values = False


class AssetEvidencePatch(BaseModel):
    """Patch model for rare service_role updates (immutability exceptions)."""

    confidence_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    assessment_relevance: Optional[bool] = None
    normalized_payload: Optional[dict] = None
    supersedes_evidence_id: Optional[UUID] = None

    class Config:
        use_enum_values = False


class AssetEvidenceSupersession(BaseModel):
    """Model for tracking evidence supersession chains."""

    old_evidence_id: UUID
    new_evidence_id: UUID
    reason: Optional[str] = None

    class Config:
        use_enum_values = False
