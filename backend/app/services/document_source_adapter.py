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

    async def _upsert(self, record: DocumentRecord) -> str:
        """
        Upsert a DocumentRecord into the documents table.

        B1 fix: checks column existence before writing — no-op (returns "") if migration not applied.
        B2 fix: ONLY writes the 3 new columns (source_system, source_document_id, site_id).
                Does NOT write to documents.source or documents.document_type — those
                are managed exclusively by the existing upload_technician_document flow.

        Returns the document_id on success, "" on failure (missing columns or error).
        """
        required = ("source_system", "source_document_id", "site_id")
        if not await self._columns_exist("documents", *required):
            logger.warning(
                "[%s] _upsert skipped — required columns missing; migration pending",
                self.source_system.value,
            )
            return ""

        # Map DocumentRecord fields to documents table columns
        # NOTE: only the 3 new columns are written here
        data: dict[str, Any] = {
            "source_system": record.source_system.value,
            "source_document_id": record.source_document_id or "",
            "site_id": record.site_id,
        }

        if record.source_url:
            data["source_url"] = record.source_url

        # raw_file_path maps to source_file_path
        if record.raw_file_path:
            data["source_file_path"] = record.raw_file_path

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
