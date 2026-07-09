"""OEM manual document adapter.

This adapter is the provenance boundary for manufacturer manuals used by PPM
checklist extraction. It deliberately does not handle technician service sheets,
Concept MRI legacy documents, or spare-parts scraping output.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from urllib.parse import urlparse

from app.models.document_record import DocumentRecord, DocumentType, ExtractionStatus
from app.models.document_source import SourceSystem
from app.services.document_source_adapter import DocumentSourceAdapter

logger = logging.getLogger(__name__)


class OEMManualAdapter(DocumentSourceAdapter):
    """DocumentSourceAdapter for OEM equipment manuals."""

    source_system = SourceSystem.OEM_MANUAL

    async def fetch_new_documents(
        self, since: datetime | None = None, site_id: str | None = None
    ) -> list[DocumentRecord]:
        """Fetch already-ingested OEM manual records from the canonical documents table."""
        if not await self._columns_exist("documents", "source_system"):
            logger.warning("[oem_manual] fetch_new_documents skipped; source_system column missing")
            return []

        query = self.db.table("documents").select("*").eq("source_system", self.source_system.value)
        if site_id:
            resolved_site_id = self._resolve_site_uuid(site_id)
            query = query.eq("site_id", resolved_site_id or site_id)
        if since:
            query = query.gte("created_at", since.isoformat())

        result = query.execute()
        return [self._reconstruct(row) for row in result.data or []]

    def get_document_file(self, source_document_id: str) -> bytes:
        """Fetch manual bytes from Supabase storage using the stored source_file_path."""
        doc_result = (
            self.db.table("documents")
            .select("source_file_path")
            .eq("source_system", self.source_system.value)
            .eq("source_document_id", source_document_id)
            .limit(1)
            .execute()
        )
        if not doc_result.data:
            raise FileNotFoundError(f"OEM manual {source_document_id} not found")

        source_file_path = doc_result.data[0].get("source_file_path")
        if not source_file_path:
            raise FileNotFoundError(f"No source_file_path for OEM manual {source_document_id}")

        bucket, *path_parts = source_file_path.split("/", 1)
        file_path = path_parts[0] if path_parts else ""
        return self.db.storage.from_(bucket).download(file_path)

    def normalise_manual(
        self,
        *,
        site_id: str,
        equipment_code: str,
        equipment_type: str,
        manufacturer: str | None = None,
        model: str | None = None,
        title: str | None = None,
        source_url: str | None = None,
        source_document_id: str | None = None,
        raw_file_path: str = "",
        ocr_text: str | None = None,
        asset_id: str | None = None,
        acquisition_method: str = "oem_manual_acquisition",
        uploaded_by: str | None = None,
    ) -> DocumentRecord:
        """Map acquired OEM manual metadata to a canonical DocumentRecord."""
        manual_id = source_document_id or self._stable_source_document_id(
            site_id=site_id,
            equipment_code=equipment_code,
            equipment_type=equipment_type,
            manufacturer=manufacturer,
            model=model,
            source_url=source_url,
        )
        resolved_title = title or self._manual_title(manufacturer, model, equipment_type, equipment_code)
        equipment_description = self._equipment_description(
            manufacturer=manufacturer,
            model=model,
            equipment_type=equipment_type,
            equipment_code=equipment_code,
        )

        return DocumentRecord(
            source_system=SourceSystem.OEM_MANUAL,
            source_document_id=manual_id,
            source_url=source_url,
            site_id=site_id,
            asset_id=asset_id or equipment_code,
            equipment_description=equipment_description,
            document_type=DocumentType.EQUIPMENT_MANUAL,
            sub_class=equipment_type.strip().lower() or None,
            discipline="HVAC" if equipment_type.strip().lower() in {"ahu", "chiller", "fcu", "vav"} else None,
            document_date=None,
            trigger_date=None,
            upload_date=datetime.utcnow(),
            contractor_vendor=manufacturer,
            technician_name=None,
            uploaded_by=uploaded_by,
            raw_file_path=raw_file_path,
            ocr_text=ocr_text,
            tech_notes=resolved_title,
            extraction_status=ExtractionStatus.EXTRACTED if ocr_text else ExtractionStatus.PENDING,
            needs_human_review=True,
            review_flags=["oem_manual_requires_checklist_approval"],
            extra={
                "manufacturer": manufacturer,
                "model": model,
                "equipment_code": equipment_code,
                "manual_source": self._manual_source_label(source_url, raw_file_path),
                "acquisition_method": acquisition_method,
            },
        )

    async def upsert_manual(self, **manual_metadata) -> str:
        """Normalise and upsert a manual record. Returns the document id or empty string."""
        record = self.normalise_manual(**manual_metadata)
        return await self._upsert(record)

    def _reconstruct(self, row: dict) -> DocumentRecord:
        keywords = row.get("keywords") or []
        equipment_code = next((kw for kw in keywords if isinstance(kw, str) and kw.startswith("S")), None)
        return DocumentRecord(
            source_system=SourceSystem.OEM_MANUAL,
            source_document_id=row.get("source_document_id"),
            source_url=row.get("source_url"),
            site_id=str(row.get("site_id") or ""),
            asset_id=row.get("asset_id"),
            equipment_description=row.get("equipment_description") or row.get("summary"),
            document_type=DocumentType.EQUIPMENT_MANUAL,
            sub_class=row.get("equipment_type"),
            discipline=None,
            upload_date=row.get("created_at"),
            contractor_vendor=row.get("manufacturer"),
            raw_file_path=row.get("source_file_path") or "",
            ocr_text=row.get("full_text"),
            tech_notes=row.get("title"),
            extraction_status=ExtractionStatus.EXTRACTED if row.get("full_text") else ExtractionStatus.PENDING,
            needs_human_review=True,
            review_flags=["oem_manual_requires_checklist_approval"],
            extra={
                "manufacturer": row.get("manufacturer"),
                "model": row.get("model"),
                "equipment_code": equipment_code,
                "manual_source": row.get("source_url") or row.get("source_file_path"),
            },
        )

    @staticmethod
    def _stable_source_document_id(
        *,
        site_id: str,
        equipment_code: str,
        equipment_type: str,
        manufacturer: str | None,
        model: str | None,
        source_url: str | None,
    ) -> str:
        raw = "|".join(
            [
                site_id.strip().lower(),
                equipment_code.strip().lower(),
                equipment_type.strip().lower(),
                (manufacturer or "").strip().lower(),
                (model or "").strip().lower(),
                (source_url or "").strip().lower(),
            ]
        )
        return f"oem-manual-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"

    @staticmethod
    def _manual_title(
        manufacturer: str | None,
        model: str | None,
        equipment_type: str,
        equipment_code: str,
    ) -> str:
        identity = " ".join(part for part in [manufacturer, model, equipment_type] if part).strip()
        return f"{identity or equipment_type} OEM Manual - {equipment_code}"

    @staticmethod
    def _equipment_description(
        *,
        manufacturer: str | None,
        model: str | None,
        equipment_type: str,
        equipment_code: str,
    ) -> str:
        identity = " ".join(part for part in [manufacturer, model, equipment_type] if part).strip()
        return f"{identity or equipment_type} manual for {equipment_code}"

    @staticmethod
    def _manual_source_label(source_url: str | None, raw_file_path: str) -> str | None:
        if source_url:
            parsed = urlparse(source_url)
            return parsed.netloc or source_url
        return raw_file_path or None
