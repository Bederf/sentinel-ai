"""Source-agnostic document extraction and vector indexing."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Literal
from uuid import UUID

from app.database.supabase_client import get_supabase_client
from app.services.document_extractor import extract_text_from_docx, extract_text_from_pdf_with_fallback
from app.services.vector_db import get_vector_db_service

logger = logging.getLogger(__name__)

DocClass = Literal["system", "site"]
STUCK_INDEXING_STATUSES = ("extracting", "embedding")


class IndexingStatus(StrEnum):
    PENDING = "pending"
    EXTRACTING = "extracting"
    EMBEDDING = "embedding"
    COMPLETE = "complete"
    FAILED = "failed"
    QUARANTINE = "quarantine"


@dataclass(frozen=True)
class IndexingResult:
    document_id: UUID
    status: IndexingStatus
    chunks: int = 0
    error: str | None = None


class DocumentIndexingService:
    """Extract text from file bytes and index an existing documents row."""

    def __init__(self, db=None, vector_db=None) -> None:
        self.db = db or get_supabase_client()
        self.vector_db = vector_db or get_vector_db_service(self.db)

    async def index_document(
        self,
        document_id: UUID,
        file_bytes: bytes,
        doc_class: DocClass,
        asset_id: str | None = None,
        source_system: str = "manual_upload",
    ) -> IndexingResult:
        """Extract, persist text, delete stale chunks, and embed a document."""
        if doc_class not in {"system", "site"}:
            raise ValueError("doc_class must be either 'system' or 'site'")

        if doc_class == "site" and not asset_id:
            error = "site document requires asset_id before indexing"
            self._update_document(
                document_id,
                indexing_status=IndexingStatus.QUARANTINE,
                indexing_error=error,
                source_system=source_system,
            )
            return IndexingResult(document_id=document_id, status=IndexingStatus.QUARANTINE, error=error)

        self._update_document(
            document_id,
            indexing_status=IndexingStatus.EXTRACTING,
            indexing_error=None,
            source_system=source_system,
            asset_id=asset_id,
        )

        try:
            full_text, metadata = self._extract_text(file_bytes)
            if not full_text.strip():
                raise ValueError("document text extraction returned empty content")
        except Exception as exc:
            error = str(exc)
            logger.warning("Document extraction failed for %s: %s", document_id, error)
            self._update_document(
                document_id,
                indexing_status=IndexingStatus.FAILED,
                indexing_error=error,
            )
            return IndexingResult(document_id=document_id, status=IndexingStatus.FAILED, error=error)

        self._update_document(
            document_id,
            indexing_status=IndexingStatus.EMBEDDING,
            indexing_error=None,
            full_text=full_text,
            summary=full_text[:500],
            ocr_extracted=bool(metadata.get("ocr_used")),
        )

        try:
            self.db.table("document_chunks").delete().eq("document_id", str(document_id)).execute()
            chunks = self.vector_db.chunk_and_embed_markdown(
                document_id=str(document_id),
                doc_class=doc_class,
            )
        except Exception as exc:
            error = str(exc)
            logger.warning("Document embedding failed for %s: %s", document_id, error)
            self._update_document(
                document_id,
                indexing_status=IndexingStatus.FAILED,
                indexing_error=error,
            )
            return IndexingResult(document_id=document_id, status=IndexingStatus.FAILED, error=error)

        return IndexingResult(document_id=document_id, status=IndexingStatus.COMPLETE, chunks=chunks)

    async def index_document_by_id(
        self,
        document_id: UUID,
        doc_class: DocClass,
        source_system: str = "oem_manual",
    ) -> IndexingResult:
        """Index a document that already has full_text in the DB (no file_bytes needed).

        Used by the OEM manual adapter path where text is stored directly
        in the documents row rather than extracted from raw file bytes.
        """
        result = self.db.table("documents").select("id,full_text").eq("id", str(document_id)).execute()
        if not result.data:
            return IndexingResult(
                document_id=document_id,
                status=IndexingStatus.FAILED,
                error=f"document {document_id} not found",
            )

        full_text = (result.data[0].get("full_text") or "").strip()
        if not full_text:
            self._update_document(
                document_id,
                indexing_status=IndexingStatus.FAILED,
                indexing_error="document has no full_text — ingest via index_document() with file_bytes",
            )
            return IndexingResult(
                document_id=document_id,
                status=IndexingStatus.FAILED,
                error="document has no full_text",
            )

        self._update_document(
            document_id,
            indexing_status=IndexingStatus.EXTRACTING,
            indexing_error=None,
            source_system=source_system,
        )

        self._update_document(
            document_id,
            indexing_status=IndexingStatus.EMBEDDING,
            indexing_error=None,
            ocr_extracted=False,
        )

        try:
            self.db.table("document_chunks").delete().eq("document_id", str(document_id)).execute()
            chunks = self.vector_db.chunk_and_embed_markdown(
                document_id=str(document_id),
                doc_class=doc_class,
            )
        except Exception as exc:
            error = str(exc)
            logger.warning("Document embedding failed for %s: %s", document_id, error)
            self._update_document(
                document_id,
                indexing_status=IndexingStatus.FAILED,
                indexing_error=error,
            )
            return IndexingResult(document_id=document_id, status=IndexingStatus.FAILED, error=error)

        return IndexingResult(document_id=document_id, status=IndexingStatus.COMPLETE, chunks=chunks)

    def sweep_stuck_documents(self, older_than_minutes: int = 30) -> int:
        """Fail documents left in transient indexing statuses."""
        cutoff = datetime.now(UTC) - timedelta(minutes=older_than_minutes)
        result = (
            self.db.table("documents")
            .select("id,indexing_status")
            .in_("indexing_status", list(STUCK_INDEXING_STATUSES))
            .lt("updated_at", cutoff.isoformat())
            .execute()
        )
        rows = result.data or []
        for row in rows:
            self._update_document(
                UUID(str(row["id"])),
                indexing_status=IndexingStatus.FAILED,
                indexing_error=f"indexing stuck in {row.get('indexing_status')} for >{older_than_minutes} minutes",
            )
        return len(rows)

    def _extract_text(self, file_bytes: bytes) -> tuple[str, dict]:
        if not file_bytes:
            raise ValueError("document file is empty")

        if file_bytes.startswith(b"%PDF"):
            return extract_text_from_pdf_with_fallback(file_bytes)

        if file_bytes.startswith(b"PK"):
            text = extract_text_from_docx(file_bytes)
            return text, {"file_type": ".docx", "ocr_used": False}

        try:
            text = file_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("unsupported document bytes; expected PDF, DOCX, or UTF-8 text") from exc
        return text, {"file_type": ".txt", "ocr_used": False}

    def _update_document(self, document_id: UUID, **fields) -> None:
        payload = {key: self._status_value(value) for key, value in fields.items()}
        payload["updated_at"] = datetime.now(UTC).isoformat()
        self.db.table("documents").update(payload).eq("id", str(document_id)).execute()

    @staticmethod
    def _status_value(value):
        if isinstance(value, IndexingStatus):
            return value.value
        return value


def get_document_indexing_service(db=None, vector_db=None) -> DocumentIndexingService:
    return DocumentIndexingService(db=db, vector_db=vector_db)
