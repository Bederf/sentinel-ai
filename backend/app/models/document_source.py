"""
Canonical enums for document source classification.

source vs source_system distinction:
  - source (DocumentSource): what the document IS — a content-type classifier.
    Write-once at first intake. Never overwritten on update.
    Values: SERVICE_REPORT, INSPECTION, CERTIFICATE, TEST_REPORT, MANUAL, UNKNOWN

  - source_system (SourceSystem): ingestion adapter — where the document CAME FROM.
    This is the upsert key component, allowing the same source_document_id
    to appear from different adapters (e.g. same WO number from MRI vs SharePoint).
    Values: CONCEPT_MRI, SHAREPOINT, MANUAL_UPLOAD
"""

from __future__ import annotations

from enum import Enum


class DocumentSource(str, Enum):
    """
    Content-type classifier — what the document IS.
    Write-once at first intake. Never overwritten on update.
    """

    SERVICE_REPORT = "service_report"  # Historical service/call-out reports
    INSPECTION = "inspection"  # Periodic inspection records
    CERTIFICATE = "certificate"  # Compliance certificates (COC, FICA, etc.)
    TEST_REPORT = "test_report"  # Test results, commissioning reports
    MANUAL = "manual"  # OEM manuals, equipment documentation
    UNKNOWN = "unknown"  # Fallback when type cannot be determined


class SourceSystem(str, Enum):
    """
    Ingestion adapter — where the document CAME FROM.
    This is the upsert key component (with source_document_id).
    """

    CONCEPT_MRI = "concept_mri"  # MRI Evolution work order system
    SHAREPOINT = "sharepoint"  # SharePoint document library
    MANUAL_UPLOAD = "manual_upload"  # Manual upload via SENTINEL UI
