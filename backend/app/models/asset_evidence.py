"""
Asset Evidence Data Models (Phase 171-02)

Pydantic models for evidence data validation and serialization.
Supports classification, normalization, and CRUD operations.
"""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ============================================================================
# Enums (matching Supabase enum types)
# ============================================================================


class SourceType(StrEnum):
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


class ArtifactType(StrEnum):
    """Evidence artifact type."""

    DOCUMENT = "document"
    AUDIO = "audio"
    IMAGE = "image"
    STRUCTURED_DATA = "structured_data"
    METADATA = "metadata"


class EvidenceClass(StrEnum):
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


class ProvenanceType(StrEnum):
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

    model_config = ConfigDict(use_enum_values=False)

    site_id: UUID
    equipment_id: UUID
    source_type: SourceType
    artifact_type: ArtifactType
    evidence_class: EvidenceClass
    document_id: UUID | None = None
    source_ref: str | None = None
    event_timestamp: datetime
    raw_payload: dict = Field(default_factory=dict)
    normalized_payload: dict = Field(default_factory=dict)
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    assessment_relevance: bool = True
    provenance_type: ProvenanceType
    provenance_uri: str
    uploader_user_id: UUID | None = None


class AssetEvidence(BaseModel):
    """Complete asset evidence record (from database)."""

    model_config = ConfigDict(from_attributes=True, use_enum_values=False)

    evidence_id: UUID
    site_id: UUID
    equipment_id: UUID
    source_type: SourceType
    artifact_type: ArtifactType
    evidence_class: EvidenceClass
    document_id: UUID | None = None
    source_ref: str | None = None
    event_timestamp: datetime
    raw_payload: dict
    normalized_payload: dict
    confidence_score: float
    assessment_relevance: bool
    provenance_type: ProvenanceType
    provenance_uri: str
    uploader_user_id: UUID | None = None
    uploader_user_email: str | None = None
    created_at: datetime
    supersedes_evidence_id: UUID | None = None


class AssetEvidenceFilter(BaseModel):
    """Filter model for flexible evidence querying."""

    model_config = ConfigDict(use_enum_values=False)

    site_id: UUID | None = None
    equipment_id: UUID | None = None
    source_type: SourceType | None = None
    evidence_class: EvidenceClass | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    active_only: bool = True  # supersedes_evidence_id IS NULL


class AssetEvidencePatch(BaseModel):
    """Patch model for rare service_role updates (immutability exceptions)."""

    model_config = ConfigDict(use_enum_values=False)

    confidence_score: float | None = Field(None, ge=0.0, le=1.0)
    assessment_relevance: bool | None = None
    normalized_payload: dict | None = None
    supersedes_evidence_id: UUID | None = None


class AssetEvidenceSupersession(BaseModel):
    """Model for tracking evidence supersession chains."""

    model_config = ConfigDict(use_enum_values=False)

    old_evidence_id: UUID
    new_evidence_id: UUID
    reason: str | None = None


def __getattr__(name: str):
    """Backward-compatible lazy export for legacy service imports."""

    if name == "AssetEvidenceService":
        from backend.app.services.asset_evidence_service import AssetEvidenceService

        return AssetEvidenceService
    raise AttributeError(name)
