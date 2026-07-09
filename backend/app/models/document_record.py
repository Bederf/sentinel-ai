"""
Canonical DocumentRecord Pydantic model.

All source adapters (MRI, SharePoint, Manual Upload) normalise documents
to this model before calling _upsert() on the DocumentSourceAdapter.

source vs source_system distinction (same as document_source.py):
  - source_system: SourceSystem enum — where the document came from (upsert key)
  - source_document_id: unique ID within that source system
  - site_id: which site this document belongs to

Note: documents.source and documents.document_type are written exclusively
by the existing upload_technician_document flow. This model does NOT
populate those columns — the adapter _upsert ONLY writes the 3 new columns:
source_system, source_document_id, site_id (via ON CONFLICT).
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from app.models.document_source import SourceSystem


class DocumentType(StrEnum):
    """
    Document type — mirrors DocumentSource values.
    Used for the documents.document_type column.
    """

    SERVICE_REPORT = "service_report"
    INSPECTION = "inspection"
    CERTIFICATE = "certificate"
    TEST_REPORT = "test_report"
    MANUAL = "manual"
    EQUIPMENT_MANUAL = "equipment_manual"
    UNKNOWN = "unknown"


class ExtractionStatus(StrEnum):
    """Status of OCR / text extraction from the document."""

    PENDING = "pending"
    EXTRACTED = "extracted"
    FAILED = "failed"
    QUARANTINED = "quarantined"


class DocumentRecord(BaseModel):
    """
    Canonical document record for all source adapters.

    Fields:
        source_system: SourceSystem enum — where the document came from.
            This is the upsert key component (with source_document_id).
        source_document_id: unique ID within that source system.
            For MRI this is the work order number; for SharePoint the item ID.
        source_url: URL to the document in the source system (read-only link).
        site_id: which site this document belongs to (e.g. 'S002').
        asset_id: optional equipment/asset UUID this document is attached to.
        equipment_description: free-text description of related equipment.
        document_type: DocumentType — what the document IS.
            Mirrors DocumentSource but used for documents.document_type column.
        sub_class: optional sub-classification (e.g. 'chiller', 'pump').
        discipline: discipline (e.g. 'HVAC', 'Electrical', 'Plumbing').
        document_date: date the document was created at source.
        trigger_date: date this document should trigger a review/alert.
        upload_date: datetime the document was ingested into SENTINEL.
        contractor_vendor: name of the contractor/vendor who issued the document.
        technician_name: name of the technician who performed the work.
        uploaded_by: user who uploaded the document to SENTINEL.
        raw_file_path: storage path of the raw file in Supabase.
        ocr_text: full text extracted via OCR (for RAG chunking).
        tech_notes: technician notes appended during intake.
        extraction_status: ExtractionStatus — current extraction state.
        needs_human_review: flag indicating manual review required.
        review_flags: list of flags for human review (e.g. ['expired_coc', 'missing_signature']).
    """

    source_system: SourceSystem  # type: ignore[name-defined]
    source_document_id: str | None = None
    source_url: str | None = None

    site_id: str
    asset_id: str | None = None
    equipment_description: str | None = None

    document_type: DocumentType = DocumentType.UNKNOWN
    sub_class: str | None = None
    discipline: str | None = None

    document_date: date | None = None
    trigger_date: date | None = None
    upload_date: datetime | None = None

    contractor_vendor: str | None = None
    technician_name: str | None = None
    uploaded_by: str | None = None

    raw_file_path: str
    ocr_text: str | None = None
    tech_notes: str | None = None

    extraction_status: ExtractionStatus = ExtractionStatus.PENDING
    needs_human_review: bool = False
    review_flags: list[str] = Field(default_factory=list)

    # Extra for adapter-specific metadata not captured above
    extra: dict[str, Any] = Field(default_factory=dict)

    model_config = {
        "use_enum_values": False,  # Keep enum instances for _upsert mapping
        "extra": "allow",
    }
