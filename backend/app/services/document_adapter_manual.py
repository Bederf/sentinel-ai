"""
ManualUploadAdapter — concrete DocumentSourceAdapter for technician uploads.

This adapter handles the site-agnostic fallback: any site without an API-based
adapter (MRI, SharePoint) uses this for technician uploads via
upload_technician_document.

B1 fix: _upsert and fetch_new_documents gracefully no-op if migration not applied.
B4/B5 fix: _upsert does NOT write documents.source or documents.document_type.
B6 fix: document_name mapped via _DOCUMENT_NAME_TO_SOURCE lookup.
"""

from __future__ import annotations

import contextlib
import logging
from datetime import date, datetime

from app.models.document_record import DocumentRecord, DocumentType, ExtractionStatus
from app.models.document_source import DocumentSource, SourceSystem
from app.services.document_source_adapter import DocumentSourceAdapter

logger = logging.getLogger(__name__)

# Maps technician document_name (from TECHNICIAN_DOCUMENT_NAMES) to DocumentSource.
# B6 fix: prevents ValueError on unknown document names.
_DOCUMENT_NAME_TO_SOURCE: dict[str, DocumentSource] = {
    # HVAC
    "Air-Handler Unit (AHU) Major Service": DocumentSource.SERVICE_REPORT,
    "Air-Handler Unit (AHU) Minor Service": DocumentSource.SERVICE_REPORT,
    "Air-Handler Unit (AHU) Weekly Inspection": DocumentSource.SERVICE_REPORT,
    "Cooling Tower (CT) Major Service": DocumentSource.SERVICE_REPORT,
    "Cooling Tower (CT) Minor Service": DocumentSource.SERVICE_REPORT,
    "Cooling Tower (CT) Weekly Inspection": DocumentSource.SERVICE_REPORT,
    "Chiller Major Service": DocumentSource.SERVICE_REPORT,
    "Chiller Minor Service": DocumentSource.SERVICE_REPORT,
    "Chiller Weekly Inspection": DocumentSource.SERVICE_REPORT,
    "Kitchen Canopy Manual Service": DocumentSource.SERVICE_REPORT,
    "Building Management System (BMS) Service": DocumentSource.SERVICE_REPORT,
    # Fire
    "Fire Pump System Inspection": DocumentSource.INSPECTION,
    "Generator Major Service": DocumentSource.SERVICE_REPORT,
    "Generator Minor Service": DocumentSource.SERVICE_REPORT,
    "Generator Weekly Test": DocumentSource.SERVICE_REPORT,
    "Smoke Detectors Service": DocumentSource.INSPECTION,
    # Electrical
    "Transformer Service": DocumentSource.SERVICE_REPORT,
    "Distribution Boards (DB) Maintenance": DocumentSource.SERVICE_REPORT,
    "Electrical Equipment Certificates": DocumentSource.CERTIFICATE,
    "Earth Leakage Test": DocumentSource.TEST_REPORT,
    # Lifts
    "Lift Service": DocumentSource.SERVICE_REPORT,
    "Lift test Report": DocumentSource.TEST_REPORT,
    "Escalator Monthly Service": DocumentSource.SERVICE_REPORT,
    # Compliance certificates
    "Certificate of Compliance (COC)": DocumentSource.CERTIFICATE,
    "Plumbing Certificate of Compliance": DocumentSource.CERTIFICATE,
    "ASIB Certificate": DocumentSource.CERTIFICATE,
    "Portable Electrical Tool Inspection": DocumentSource.INSPECTION,
    "BSI Audit certificate": DocumentSource.CERTIFICATE,
    # Water/Energy
    "Water Consumption Reports": DocumentSource.SERVICE_REPORT,
    "Pressure Vessel Test Certificate": DocumentSource.CERTIFICATE,
    "Spillage Incidents Report": DocumentSource.SERVICE_REPORT,
    # Inspections
    "Building Inspection Report": DocumentSource.INSPECTION,
    "Occupational Hygiene Surveys": DocumentSource.INSPECTION,
    # Waste
    "Waste Management Service": DocumentSource.SERVICE_REPORT,
    "Waste disposal certificates": DocumentSource.CERTIFICATE,
    # Solar
    "Solar PV Weekly Inspection": DocumentSource.INSPECTION,
    # UPS
    "UPS Weekly Inspection": DocumentSource.INSPECTION,
    # General
    "Audit Reports": DocumentSource.INSPECTION,
    "Warranties": DocumentSource.SERVICE_REPORT,
    "Roof Guarantee Certificate": DocumentSource.CERTIFICATE,
    "Potable Water Test Results": DocumentSource.TEST_REPORT,
    # Structural
    "Structural Integrity Report": DocumentSource.INSPECTION,
}


class ManualUploadAdapter(DocumentSourceAdapter):
    """
    Concrete adapter for technician uploads via upload_technician_document.

    source_system: SourceSystem.MANUAL_UPLOAD

    This adapter is automatically used for every technician upload — it
    normalises the upload response + form data into a DocumentRecord and
    calls _upsert() to create the cross-adapter record.

    The existing upload_technician_document endpoint continues to own
    documents.source and documents.document_type. This adapter's _upsert
    ONLY writes source_system, source_document_id, and site_id.
    """

    source_system = SourceSystem.MANUAL_UPLOAD

    def __init__(self) -> None:
        super().__init__()

    async def fetch_new_documents(
        self, since: datetime | None = None, site_id: str | None = None
    ) -> list[DocumentRecord]:
        """
        Fetch documents ingested via upload_technician_document.

        B1 fix: if source_system column missing, return [] gracefully.
        """
        if not await self._columns_exist("documents", "source_system"):
            logger.warning(
                "[manual_upload] fetch_new_documents skipped — source_system column missing; migration pending"
            )
            return []

        query = (
            self.db.table("documents")
            .select("*")
            .eq("source_system", self.source_system.value)
        )
        if site_id:
            query = query.eq("site_id", site_id)
        if since:
            query = query.gte("created_at", since.isoformat())

        result = query.execute()
        records: list[DocumentRecord] = []
        for row in result.data or []:
            records.append(self._reconstruct(row))
        return records

    def get_document_file(self, source_document_id: str) -> bytes:
        """
        Fetch raw file bytes from Supabase storage.

        Uses source_file_path stored on the documents record to locate the file.
        """
        doc_result = (
            self.db.table("documents")
            .select("source_file_path")
            .eq("id", source_document_id)
            .execute()
        )
        if not doc_result.data:
            raise FileNotFoundError(f"Document {source_document_id} not found")

        source_file_path = doc_result.data[0].get("source_file_path")
        if not source_file_path:
            raise FileNotFoundError(f"No source_file_path for document {source_document_id}")

        storage = self.db.storage
        bucket, *path_parts = source_file_path.split("/", 1)
        file_path = path_parts[0] if path_parts else ""
        response = storage.from_(bucket).download(file_path)
        return response

    def normalise_upload(
        self,
        upload_response: dict,
        form_data: dict,
        site_id: str,
    ) -> DocumentRecord:
        """
        Map upload_technician_document response + Form data to a DocumentRecord.

        B4/B5 fix: this method does NOT write to documents.source or
        documents.document_type. Those are managed exclusively by the existing
        upload_technician_document endpoint's own upsert path.

        B6 fix: document_name mapped via _DOCUMENT_NAME_TO_SOURCE — no ValueError.

        Parameters:
            upload_response: dict with document_id, storage_path from upload_document
            form_data: dict with equipment_id, document_name, document_sub_class,
                       category_discipline, document_creation_date, trigger_date, title
            site_id: resolved site_id (not from form_data — prevents override)
        """
        # Extract source_document_id from upload response
        source_document_id = upload_response.get("document_id") or ""

        # Parse document_date from form_data
        document_date: date | None = None
        doc_date_str = form_data.get("document_creation_date")
        if doc_date_str:
            try:
                document_date = datetime.strptime(doc_date_str, "%Y-%m-%d").date()
            except ValueError:
                logger.warning(
                    "[manual_upload] Could not parse document_creation_date: %s",
                    doc_date_str,
                )

        # Parse trigger_date from form_data
        trigger: date | None = None
        trigger_str = form_data.get("trigger_date")
        if trigger_str:
            try:
                trigger = datetime.strptime(trigger_str, "%Y-%m-%d").date()
            except ValueError:
                logger.warning(
                    "[manual_upload] Could not parse trigger_date: %s",
                    trigger_str,
                )

        # Map document_name to DocumentSource (B6 fix)
        doc_name = form_data.get("document_name", "")
        doc_source = _DOCUMENT_NAME_TO_SOURCE.get(doc_name, DocumentSource.UNKNOWN)

        # tech_notes from title field
        tech_notes = form_data.get("title") or None

        return DocumentRecord(
            source_system=SourceSystem.MANUAL_UPLOAD,
            source_document_id=source_document_id,
            source_url=None,  # No external URL for manual uploads
            site_id=site_id,
            asset_id=form_data.get("equipment_id") or None,
            equipment_description=None,
            document_type=DocumentType(doc_source.value),  # mirrors DocumentSource
            sub_class=form_data.get("document_sub_class") or None,
            discipline=form_data.get("category_discipline") or None,
            document_date=document_date,
            trigger_date=trigger,
            upload_date=datetime.utcnow(),
            contractor_vendor=None,
            technician_name=None,
            uploaded_by=form_data.get("uploaded_by_user_id") or None,
            raw_file_path=upload_response.get("storage_path") or "",
            ocr_text=None,  # existing upload endpoint handles OCR immediately
            tech_notes=tech_notes,
            extraction_status=ExtractionStatus.EXTRACTED,  # upload does OCR synchronously
            needs_human_review=False,
            review_flags=[],
        )

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def _reconstruct(self, row: dict) -> DocumentRecord:
        """
        Reconstruct a DocumentRecord from a documents table row.

        Handles the fact that not all DocumentRecord fields map directly to
        columns — some are stored in keywords or not yet available.
        """
        keywords = row.get("keywords") or []
        kw_map: dict[str, str] = {}
        for kw in keywords:
            if ":" in kw:
                k, v = kw.split(":", 1)
                kw_map[k] = v

        # Parse document_date from keywords (stored as document_creation_date:{date})
        document_date: date | None = None
        doc_date_str = kw_map.get("document_creation_date")
        if doc_date_str:
            with contextlib.suppress(ValueError):
                document_date = datetime.strptime(doc_date_str, "%Y-%m-%d").date()

        # Parse trigger_date from keywords
        trigger_date: date | None = None
        trigger_str = kw_map.get("trigger_date")
        if trigger_str:
            with contextlib.suppress(ValueError):
                trigger_date = datetime.strptime(trigger_str, "%Y-%m-%d").date()

        # uploaded_by from keywords
        uploaded_by = kw_map.get("uploaded_by_user_id")

        # Map stored doc_type string back to DocumentType (handle old records)
        doc_type_str = row.get("document_type", "unknown")
        try:
            doc_type = DocumentType(doc_type_str)
        except ValueError:
            doc_type = DocumentType.UNKNOWN

        return DocumentRecord(
            source_system=SourceSystem.MANUAL_UPLOAD,
            source_document_id=row.get("source_document_id") or row.get("id", ""),
            source_url=row.get("source_url"),
            site_id=row.get("site_id", ""),
            asset_id=kw_map.get("equipment_id") or None,
            equipment_description=None,
            document_type=doc_type,
            sub_class=kw_map.get("document_sub_class") or None,
            discipline=kw_map.get("category_discipline") or None,
            document_date=document_date,
            trigger_date=trigger_date,
            upload_date=None,
            contractor_vendor=kw_map.get("contractor_vendor") or None,
            technician_name=None,
            uploaded_by=uploaded_by,
            raw_file_path=row.get("source_file_path") or "",
            ocr_text=None,
            tech_notes=row.get("title") or None,
            extraction_status=ExtractionStatus.EXTRACTED,
            needs_human_review=False,
            review_flags=[],
        )
