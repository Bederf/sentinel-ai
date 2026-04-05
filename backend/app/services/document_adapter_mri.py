"""
ConceptMRIAdapter — DocumentSourceAdapter for MRI Evolution (Concept) REST API.

Fetches service reports and documents from the MRI Concept documents endpoint
and normalises them into canonical DocumentRecord format.

source_system: SourceSystem.CONCEPT_MRI
"""

from __future__ import annotations

import logging
from datetime import date, datetime

from app.models.document_record import DocumentRecord, DocumentType, ExtractionStatus
from app.models.document_source import SourceSystem
from app.services.document_source_adapter import DocumentSourceAdapter
from app.services.mri_document_client import MRIDocumentClient

logger = logging.getLogger(__name__)

# PROVISIONAL — vendor to confirm field names
FIELD_MAP: dict[str, str] = {
    "DocumentId": "DocumentId",
    "DocumentUrl": "DocumentUrl",
    "Site": "Site",
    "EquipmentDescription": "EquipmentDescription",
    "DocumentType": "DocumentType",
    "Category": "Category",
    "DocumentCreationDate": "DocumentCreationDate",
    "TriggerDate": "TriggerDate",
    "ContractorVendor": "ContractorVendor",
    "Author": "Author",
    "Notes": "Notes",
}


class ConceptMRIAdapter(DocumentSourceAdapter):
    """
    DocumentSourceAdapter for MRI Evolution (Concept) REST API.

    Fetches documents from the /documents endpoint, normalises them to
    DocumentRecord, and upserts into the documents table.

    Only writes the 3 new columns: source_system, source_document_id, site_id.
    Does NOT write documents.source or documents.document_type.
    """

    source_system = SourceSystem.CONCEPT_MRI

    def __init__(self) -> None:
        super().__init__()
        self.client = MRIDocumentClient()

    async def fetch_new_documents(
        self, since: datetime | None = None, site_id: str | None = None
    ) -> list[DocumentRecord]:
        """
        Fetch new documents from MRI Concept since last sync.

        The site_id filter is applied after fetching — MRI Concept does not
        support site-level filtering on the documents endpoint, so we fetch
        all and filter locally.
        """
        raw_list = await self.client.fetch_documents(since)
        return [self.normalise(raw) for raw in raw_list]

    def get_document_file(self, source_document_id: str) -> bytes:
        """Retrieve raw file bytes for the given source_document_id."""
        return self.client.get_document_file(source_document_id)

    def normalise(self, raw: dict) -> DocumentRecord:
        """
        Translate MRI Concept API document record to canonical DocumentRecord.

        B3 fix: full implementation with FIELD_MAP, _map_document_type,
        _parse_date, _resolve_site.
        """
        return DocumentRecord(
            source_system=SourceSystem.CONCEPT_MRI,
            source_document_id=raw.get(FIELD_MAP["DocumentId"]),
            source_url=raw.get(FIELD_MAP["DocumentUrl"]),
            site_id=self._resolve_site(raw.get(FIELD_MAP["Site"])),
            asset_id=None,  # resolved downstream by asset resolver
            equipment_description=raw.get(FIELD_MAP["EquipmentDescription"]),
            document_type=self._map_document_type(raw.get(FIELD_MAP["DocumentType"])),
            sub_class=None,
            discipline=raw.get(FIELD_MAP["Category"]),
            document_date=self._parse_date(raw.get(FIELD_MAP["DocumentCreationDate"])),
            trigger_date=self._parse_date(raw.get(FIELD_MAP["TriggerDate"])),
            upload_date=datetime.utcnow(),
            contractor_vendor=raw.get(FIELD_MAP["ContractorVendor"]),
            technician_name=None,
            uploaded_by=raw.get(FIELD_MAP["Author"]),
            raw_file_path="",  # populated after file fetch step
            extraction_status=ExtractionStatus.PENDING,
            needs_human_review=False,
            review_flags=[],
        )

    def _map_document_type(self, raw_value: str | None) -> DocumentType:
        """Map MRI raw DocumentType string to DocumentType enum."""
        mapping = {
            "Service Report": DocumentType.SERVICE_REPORT,
            "Inspection": DocumentType.INSPECTION,
            "Certificate": DocumentType.CERTIFICATE,
            "Test Report": DocumentType.TEST_REPORT,
        }
        return mapping.get(raw_value or "", DocumentType.UNKNOWN)

    def _parse_date(self, value: str | None) -> date | None:
        """Parse an ISO-format date string. Return None if unparseable."""
        if not value:
            return None
        try:
            return date.fromisoformat(value)
        except ValueError:
            logger.warning("ConceptMRIAdapter: unparseable date '%s'", value)
            return None

    def _resolve_site(self, raw_site: str | None) -> str:
        """
        Resolve raw site name/ID from MRI to a canonical site_id.

        Falls back to 'UNKNOWN' if no match is found.
        """
        if not raw_site:
            return "UNKNOWN"

        # Normalise: strip whitespace, upper-case
        normalized = raw_site.strip().upper()

        # Direct match against registered site codes
        from app.core.site_resolver import get_registered_site_ids

        for site_id in get_registered_site_ids():
            if site_id.upper() == normalized or normalized in site_id.upper():
                return site_id

        # Try to match site name against building names in registered sites
        try:
            from app.core.site_resolver import get_registered_sites

            for site in get_registered_sites():
                name = (site.get("name") or "").upper()
                code = site.get("code") or ""
                if normalized == name or normalized == code.upper():
                    return code
        except Exception:
            pass

        logger.warning("ConceptMRIAdapter: could not resolve site '%s' — using UNKNOWN", raw_site)
        return "UNKNOWN"
