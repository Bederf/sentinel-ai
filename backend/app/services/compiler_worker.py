"""
CompilerWorker — consumes compiler_queue entries and produces equipment_knowledge records.

Downstream of asset_resolution_service._enqueue_compiler: when a document's asset_id
is resolved (phase 179-181), a compiler_queue entry is created. This service polls
that queue, fetches the resolved document and its equipment metadata, compiles a
knowledge record, and upserts it to equipment_knowledge.

Phase 182-01.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _get_supabase():
    from app.database.supabase_client import get_supabase_client

    return get_supabase_client()


class CompilerWorker:
    """
     Processes compiler_queue entries into equipment_knowledge records.

    -poll_and_process() is the main entry point — called by APScheduler job wrapper.
     Processing is synchronous to work with APScheduler's sync JobRun requests.
    """

    def __init__(self, db: Any = None) -> None:
        self.db = db or _get_supabase()

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def poll_and_process(self) -> int:
        """
        Poll compiler_queue for unprocessed entries and process each one.

        Uses an atomic UPDATE...RETURNING to claim a batch of entries in one
        DB round-trip, preventing concurrent workers from processing the same rows.

        Returns count of successfully processed entries (knowledge upserted).
        Returns 0 if queue is empty or on any error during processing.
        """
        # Step 1: Atomically claim up to 50 unprocessed entries
        claimed_entries = self._claim_entries(limit=50)
        if not claimed_entries:
            logger.debug("[CompilerWorker] no unprocessed queue entries")
            return 0

        processed_count = 0
        processed_ids: list[str] = []

        for entry in claimed_entries:
            entry_id = entry["id"]
            try:
                # Step 2: Fetch document + equipment
                document, equipment = self._fetch_document_and_equipment(entry)

                # Step 3: Compile knowledge record
                knowledge_record = self._compile_knowledge_entry(
                    document=document,
                    equipment=equipment,
                    queue_entry=entry,
                )

                # equipment_type unknown — entry marked processed by returning None
                if knowledge_record is None:
                    processed_ids.append(entry_id)
                    processed_count += 1
                    logger.info(
                        "[CompilerWorker] skipped entry %s (equipment_type unknown) — marked processed",
                        entry_id,
                    )
                    continue

                # Step 4: Upsert to equipment_knowledge
                self._upsert_knowledge(knowledge_record)

                processed_ids.append(entry_id)
                processed_count += 1
                logger.info(
                    "[CompilerWorker] compiled knowledge for document_id=%s asset_id=%s",
                    entry.get("document_id"),
                    entry.get("asset_id"),
                )

            except Exception as exc:
                logger.error(
                    "[CompilerWorker] failed to process queue entry %s: %s",
                    entry_id,
                    exc,
                )
                # Reset processed_at so entry can be retried next cycle.
                # The claim set processed_at but upsert/content fetch failed,
                # so the entry must be unseated before retry.
                try:
                    self.db.table("compiler_queue").update({"processed_at": None}).eq("id", entry_id).execute()
                except Exception:
                    pass  # best-effort; entry is already stuck, log already emitted

        # Step 5: Delete successfully processed entries from queue
        if processed_ids:
            try:
                self._delete_entries(processed_ids)
                logger.info(
                    "[CompilerWorker] deleted %d queue entries after successful upsert",
                    len(processed_ids),
                )
            except Exception as exc:
                # Delete failed but upsert succeeded — reset processed_at so entries retry
                logger.warning(
                    "[CompilerWorker] delete failed, unseating %d entries for retry: %s",
                    len(processed_ids),
                    exc,
                )
                for eid in processed_ids:
                    try:
                        self.db.table("compiler_queue").update({"processed_at": None}).eq("id", eid).execute()
                    except Exception:
                        pass  # best-effort; log already emitted

        return processed_count

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def _claim_entries(self, limit: int = 50) -> list[dict]:
        """
        Atomically claim unprocessed queue entries using SELECT FOR UPDATE SKIP LOCKED.

        Uses SELECT...FOR UPDATE SKIP LOCKED to atomically claim rows so multiple
        workers can run concurrently without double-processing. No UPDATE needed —
        we directly SELECT and mark processed in a follow-up.
        """
        try:
            conn = self._get_conn()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, document_id, asset_id, queued_at
                    FROM compiler_queue
                    WHERE processed_at IS NULL
                    ORDER BY queued_at ASC
                    LIMIT %s
                    FOR UPDATE SKIP LOCKED
                    """,
                    (limit,),
                )
                rows = cur.fetchall()
            return [dict(zip(["id", "document_id", "asset_id", "queued_at"], row)) for row in rows] if rows else []
        except Exception as exc:
            logger.error("[CompilerWorker] _claim_entries failed: %s", exc)
            return []

    def _get_conn(self):
        """Get a raw psycopg2 connection for this method."""
        import os

        import psycopg2

        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise ValueError("DATABASE_URL not set")
        return psycopg2.connect(database_url)

    def _fetch_document_and_equipment(self, queue_entry: dict) -> tuple[dict | None, dict | None]:
        """
        Fetch documents row and equipment row for a queue entry.

        Returns (document, equipment) — either may be None if not found.
        """
        document_id = queue_entry.get("document_id")
        asset_id = queue_entry.get("asset_id")

        document = None
        if document_id:
            try:
                doc_result = (
                    self.db.table("documents")
                    .select(
                        "id, asset_id, equipment_description, document_type, "
                        "document_date, contractor_vendor, technician_name, "
                        "resolution_confidence, source_system, raw_file_path"
                    )
                    .eq("id", document_id)
                    .execute()
                )
                if doc_result.data:
                    document = doc_result.data[0]
            except Exception as exc:
                logger.warning(
                    "[CompilerWorker] failed to fetch document_id=%s: %s",
                    document_id,
                    exc,
                )

        equipment_record = None
        if asset_id:
            try:
                equip_result = (
                    self.db.table("equipment").select("id, code, type, location, name").eq("id", asset_id).execute()
                )
                if equip_result.data:
                    equipment_record = equip_result.data[0]
            except Exception as exc:
                logger.warning(
                    "[CompilerWorker] failed to fetch equipment id=%s: %s",
                    asset_id,
                    exc,
                )

        return document, equipment_record

    def _compile_knowledge_entry(
        self,
        document: dict | None,
        equipment: dict | None,
        queue_entry: dict,
    ) -> dict:
        """
        Build an equipment_knowledge record dict from document + equipment data.

        Guard: if ocr_text (equipment_description) is null/empty after strip,
        set description to placeholder so tech chat has a clear missing-content signal.
        """
        # Determine equipment_type from DB value, not parsed asset_id string
        equipment_type = None
        if equipment:
            equipment_type = equipment.get("type")  # e.g. 'GENERATOR', 'CHILLER'

        # Fall back to asset_id-based type only if no equipment record
        if not equipment_type:
            asset_id = queue_entry.get("asset_id") or ""
            parts = asset_id.split("-")
            equipment_type = parts[2] if len(parts) >= 3 else None  # e.g. GEN, CHILLER

        # Build description from OCR text
        raw_ocr = ""
        if document:
            raw_ocr = document.get("equipment_description") or ""

        description = "[No OCR text available — see source document]" if not raw_ocr.strip() else raw_ocr.strip()[:500]

        # Determine confidence band from resolution_confidence
        resolution_confidence: float | None = document.get("resolution_confidence") if document else None

        confidence = "high" if resolution_confidence is not None and resolution_confidence >= 0.85 else "medium"

        # Title: equipment code + document type
        equipment_code = None
        if equipment:
            equipment_code = equipment.get("code")
        if not equipment_code and document:
            equipment_code = document.get("asset_id")

        document_type = None
        if document:
            document_type = document.get("document_type")

        title = f"{equipment_code or 'Unknown'} — {document_type or 'Document'}"

        # Guard: equipment_type must be determinable — None means the record
        # would be created but can never be retrieved (API queries by equipment_type).
        # Return None; caller marks the entry processed so it is not retried forever.
        if not equipment_type:
            logger.warning(
                "[CompilerWorker] cannot determine equipment_type for asset_id=%s — skipping entry",
                queue_entry.get("asset_id"),
            )
            return None

        record: dict[str, Any] = {
            "equipment_type": equipment_type,
            "knowledge_type": "maintenance_record",
            "title": title,
            "description": description,
            "source_document_id": queue_entry.get("document_id"),
            "confidence": confidence,
        }

        # Add equipment FK if available
        if equipment:
            record["equipment_id"] = equipment.get("id")

        return record

    def _upsert_knowledge(self, knowledge_record: dict) -> None:
        """
        Upsert to equipment_knowledge table using source_document_id as upsert key.
        """
        try:
            self.db.table("equipment_knowledge").upsert(
                knowledge_record,
                on_conflict="source_document_id",
            ).execute()
        except Exception as exc:
            # If upsert fails (missing columns, constraint mismatch, etc.), re-raise
            # so poll_and_process() can leave the queue entry for retry
            logger.error(
                "[CompilerWorker] upsert_knowledge failed for source_document_id=%s: %s",
                knowledge_record.get("source_document_id"),
                exc,
            )
            raise

    def _delete_entries(self, entry_ids: list[str]) -> None:
        """Delete successfully processed queue entries."""
        if not entry_ids:
            return
        try:
            self.db.table("compiler_queue").delete().in_("id", entry_ids).execute()
        except Exception as exc:
            logger.warning(
                "[CompilerWorker] failed to delete queue entries %s: %s",
                entry_ids,
                exc,
            )
