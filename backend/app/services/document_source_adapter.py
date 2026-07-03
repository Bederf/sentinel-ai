"""
Abstract base class for all document source adapters.

Pattern: same as MaintenanceAdapter — self.db in __init__, ABC with abstract methods.

Subclasses implement:
  - source_system: SourceSystem class variable
  - fetch_new_documents(since, site_id) — pull new documents from the source
  - get_document_file(source_document_id) — retrieve raw file bytes

Base class provides:
  - _columns_exist() — B1 fix: guard against missing columns (migration not applied)
  - _upsert(record) — B1/B2 fix: upsert with column guard; only writes 3 new columns
  - _get_last_sync(site_id) / _update_sync_state — per-adapter sync tracking

B1 fix: _columns_exist guard on BOTH _upsert AND fetch_new_documents prevents
        500 errors when the migration has not yet been applied.

B2 fix: _upsert ONLY writes source_system, source_document_id, site_id.
        documents.source and documents.document_type are managed exclusively
        by the existing upload_technician_document flow.
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from app.models.document_record import DocumentRecord
from app.models.document_source import SourceSystem

logger = logging.getLogger(__name__)


def _get_supabase():
    from app.database.supabase_client import get_supabase_client

    return get_supabase_client()


class DocumentSourceAdapter(ABC):
    """
    Abstract base for document source adapters.

    Subclass implements:
      - source_system: SourceSystem class variable — which source system this adapter handles
      - fetch_new_documents(since, site_id) — pull new documents from the source
      - get_document_file(source_document_id) — retrieve raw file bytes

    Base class provides:
      - _columns_exist(table, *columns) — check information_schema before writing (B1 fix)
      - _upsert(record) — upsert with column guard; only writes source_system, source_document_id, site_id (B2 fix)
      - _get_last_sync(site_id) / _update_sync_state — per-adapter sync tracking
    """

    source_system: SourceSystem
    adapter_table: str = "document_connector_sync"

    def __init__(self) -> None:
        self.db = _get_supabase()

    @abstractmethod
    async def fetch_new_documents(
        self, since: datetime | None = None, site_id: str | None = None
    ) -> list[DocumentRecord]:
        """
        Fetch new documents from the source system since last sync.

        B1 fix: if the required columns are not yet in the documents table
        (migration not applied), return an empty list gracefully.
        """

    @abstractmethod
    def get_document_file(self, source_document_id: str) -> bytes:
        """Retrieve the raw file bytes for the given source_document_id."""

    async def run_sync(self, site_id: str | None = None) -> dict:
        """
        Run a full sync cycle: fetch → normalise → upsert → update state.

        Calls fetch_new_documents, upserts each record, then updates sync state.
        Returns {"synced": N, "failed": M, "errors": [...]}.
        """
        last_sync = self._get_last_sync(site_id)
        records = await self.fetch_new_documents(since=last_sync, site_id=site_id)

        synced = failed = 0
        errors: list[str] = []
        for record in records:
            try:
                doc_id = await self._upsert(record)
                if doc_id:
                    synced += 1
                else:
                    failed += 1
            except Exception as exc:
                failed += 1
                errors.append(str(exc))
                logger.error(
                    "[%s] run_sync: failed to upsert document %s: %s",
                    self.source_system.value,
                    record.source_document_id,
                    exc,
                )

        self._update_sync_state(site_id, synced, failed, len(errors))
        return {"synced": synced, "failed": failed, "errors": errors}

    # -------------------------------------------------------------------------
    # Helper methods (not abstract)
    # -------------------------------------------------------------------------

    async def _columns_exist(self, table: str, *columns: str) -> bool:
        """
        Check whether all specified columns exist in the given table.

        Queries information_schema.columns. Returns False if any column is missing.
        This is the B1 fix: prevents 500 errors when the migration has not been applied.
        """
        result = (
            self.db.table("information_schema.columns")
            .select("column_name")
            .eq("table_name", table)
            .in_("column_name", list(columns))
            .execute()
        )
        if len(result.data) != len(columns):
            logger.warning(
                "[%s] _columns_exist: table=%s columns=%s — some columns missing; migration may be pending",
                self.source_system.value,
                table,
                columns,
            )
            return False
        return True

    def _resolve_site_uuid(self, site_id: str | None) -> str | None:
        """Resolve site codes to the live documents.site_id UUID FK."""
        if not site_id:
            return None
        if re.fullmatch(r"[0-9a-fA-F-]{36}", site_id):
            return site_id
        try:
            result = self.db.table("sites").select("id").eq("code", site_id).limit(1).execute()
            if result.data:
                return result.data[0]["id"]
        except Exception as exc:
            logger.warning("[%s] failed to resolve site %s to UUID: %s", self.source_system.value, site_id, exc)
        return None

    def _document_code(self, record: DocumentRecord) -> str:
        """Build a stable code that satisfies the documents.code unique key."""
        source_doc_id = record.source_document_id or datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
        safe_source = re.sub(r"[^A-Za-z0-9]+", "-", self.source_system.value).strip("-").upper()
        safe_doc_id = re.sub(r"[^A-Za-z0-9]+", "-", source_doc_id).strip("-").upper()
        return f"{safe_source}-{safe_doc_id}"[:120]

    def _document_title(self, record: DocumentRecord) -> str:
        """Prefer human-facing metadata, then fall back to the source id."""
        if record.tech_notes:
            return record.tech_notes[:255]
        if record.equipment_description:
            return record.equipment_description[:255]
        if record.source_document_id:
            return f"{record.document_type.value.replace('_', ' ').title()} {record.source_document_id}"[:255]
        return f"{record.source_system.value} document"[:255]

    def _document_source(self) -> str:
        """Map adapter provenance into the constrained documents.source values."""
        if self.source_system.value == "manual_upload":
            return "user_upload"
        return "service_history"

    async def _upsert(self, record: DocumentRecord) -> str:
        """
        Upsert a DocumentRecord into the documents table.

        B1 fix: checks source columns before writing — no-op (returns "") if migration not applied.
        Live schema fix: provides required documents fields while keeping adapter
        provenance in source_system/source_document_id.

        Returns the document_id on success, "" on failure (missing columns or error).
        """
        required = ("source_system", "source_document_id", "site_id")
        if not await self._columns_exist("documents", *required):
            logger.warning(
                "[%s] _upsert skipped — required columns missing; migration pending",
                self.source_system.value,
            )
            return ""

        data: dict[str, Any] = {
            "code": self._document_code(record),
            "title": self._document_title(record),
            "document_type": record.document_type.value if record.document_type else "unknown",
            "equipment_type": record.sub_class or "general",
            "source": self._document_source(),
            "source_system": record.source_system.value,
            "source_document_id": record.source_document_id or "",
            "site_id": self._resolve_site_uuid(record.site_id),
        }

        if record.equipment_description:
            data["summary"] = record.equipment_description[:500]

        if record.ocr_text:
            data["full_text"] = record.ocr_text
            data["summary"] = record.ocr_text[:500]
            data["indexing_status"] = "pending"

        if record.source_url:
            data["source_url"] = record.source_url

        # raw_file_path maps to source_file_path
        if record.raw_file_path:
            data["source_file_path"] = record.raw_file_path

        # Phase 181-03: write equipment_description if the column exists.
        # Protected by B1-style column guard: no-op if column missing (migration pending).
        if record.equipment_description:
            if await self._columns_exist("documents", "equipment_description"):
                data["equipment_description"] = record.equipment_description
            else:
                logger.debug(
                    "[%s] equipment_description column missing; write skipped (migration pending)",
                    self.source_system.value,
                )

        # Build keywords from available fields
        keywords: list[str] = []
        for field in (
            record.site_id,
            record.asset_id,
            record.document_type.value if record.document_type else None,
            record.sub_class,
            record.contractor_vendor,
        ):
            if field:
                keywords.append(str(field))
        if keywords:
            data["keywords"] = keywords

        # upsert ON CONFLICT (source_document_id, source_system)
        # DO UPDATE SET source_system=EXCLUDED.source_system, updated_at=NOW()
        result = (
            self.db.table("documents")
            .upsert(
                data,
                on_conflict="source_document_id,source_system",
            )
            .execute()
        )

        if result.data:
            return result.data[0].get("id", "")
        return ""

    def _get_last_sync(self, site_id: str | None) -> datetime | None:
        """Return the last successful sync datetime for this adapter and site."""
        query = (
            self.db.table(self.adapter_table)
            .select("last_successful_sync")
            .eq("adapter_source", self.source_system.value)
        )
        if site_id:
            query = query.eq("site_id", site_id)
        result = query.execute()
        if result.data and result.data[0].get("last_successful_sync"):
            return datetime.fromisoformat(result.data[0]["last_successful_sync"])
        return None

    def _update_sync_state(
        self,
        site_id: str | None,
        ingested: int,
        updated: int,
        errors: int,
    ) -> None:
        """Update the sync state for this adapter and site after a sync run."""
        now = datetime.utcnow().isoformat()
        self.db.table(self.adapter_table).upsert(
            {
                "adapter_source": self.source_system.value,
                "site_id": site_id,
                "last_successful_sync": now,
                "last_sync_attempted": now,
                "records_ingested": ingested,
                "records_updated": updated,
                "errors": errors,
            },
            on_conflict="adapter_source,site_id",
        ).execute()
