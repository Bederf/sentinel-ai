"""
WikiCompilerService — consumes compiler_queue entries and produces wiki markdown pages.

Downstream of asset_resolution_service._enqueue_compiler: when a document's asset_id
is resolved (phase 179-181), a compiler_queue entry is created. This service polls
that queue, compiles a technician-readable markdown page for each asset, and writes
it to wiki/S002/{asset_id}.md.

Phase 182-01: initial implementation.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _get_supabase():
    from app.database.supabase_client import get_supabase_client

    return get_supabase_client()


class WikiCompilerService:
    """
    Consumes compiler_queue entries and compiles wiki markdown pages for assets.

    Wiki pages aggregate all documents for an asset into a clean, technician-readable
    markdown page. Written to wiki/{site_id}/{asset_id}.md.
    """

    def __init__(self, db: Any = None, wiki_root: str | Path = "wiki") -> None:
        self.db = db or _get_supabase()
        self.wiki_root = Path(wiki_root)

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    async def process_queue(self, limit: int = 50) -> dict:
        """
        Poll compiler_queue for unprocessed entries and compile wiki pages.

        Graceful degradation: if compiler_queue table doesn't exist or
        processed_at column is missing, return {"skipped": True, "reason": ...}.

        Returns {"processed": N, "failed": M, "skipped": False, "errors": [...]}.
        """
        # Check table/column existence first (graceful degradation)
        if not await self._compiler_queue_available():
            return {
                "skipped": True,
                "reason": "compiler_queue table or processed_at column missing",
                "processed": 0,
                "failed": 0,
                "errors": [],
            }

        # Fetch unprocessed entries
        result = self.db.table("compiler_queue").select(
            "id, asset_id, document_id, queued_at"
        ).is_("processed_at", None).order("queued_at").limit(limit).execute()

        if not result.data:
            return {"skipped": False, "processed": 0, "failed": 0, "errors": []}

        processed = failed = 0
        errors: list[str] = []

        for entry in result.data:
            try:
                doc_result = self.db.table("documents").select(
                    "id, asset_id, equipment_description, document_date, "
                    "document_type, contractor_vendor, technician_name, "
                    "source_system, source_document_id, source_url, raw_file_path, "
                    "tech_notes"
                ).eq("id", entry["document_id"]).execute()

                if not doc_result.data:
                    # Document gone — mark processed, no file written
                    self._mark_processed(entry["id"])
                    processed += 1
                    logger.info(
                        "[WikiCompiler] document %s not found; queue entry %s marked processed",
                        entry["document_id"],
                        entry["id"],
                    )
                    continue

                doc = doc_result.data[0]
                asset_id = entry["asset_id"] or doc.get("asset_id")

                if not asset_id:
                    asset_id = f"unassigned-{entry['document_id'][:8]}"

                # Compile wiki for this asset
                wiki_path = await self.compile_asset_wiki(
                    asset_id=asset_id,
                    site_id="S002",
                )

                self._mark_processed(entry["id"])
                processed += 1
                logger.info(
                    "[WikiCompiler] compiled wiki for asset %s -> %s",
                    asset_id,
                    wiki_path,
                )

            except Exception as exc:
                failed += 1
                errors.append(str(exc))
                logger.error(
                    "[WikiCompiler] failed to process queue entry %s: %s",
                    entry["id"],
                    exc,
                )

        return {"skipped": False, "processed": processed, "failed": failed, "errors": errors}

    async def compile_asset_wiki(
        self, asset_id: str, site_id: str = "S002"
    ) -> str | None:
        """
        Force-compile a specific asset's wiki page.

        Called by API endpoint to manually trigger compilation.
        Returns path of compiled file, or None if no documents found.
        """
        docs_result = self.db.table("documents").select(
            "id, asset_id, equipment_description, document_date, "
            "document_type, contractor_vendor, technician_name, "
            "source_system, source_document_id, source_url, raw_file_path, "
            "tech_notes, sub_class"
        ).eq("asset_id", asset_id).order("document_date", desc=True).execute()

        if not docs_result.data:
            return None

        all_docs = docs_result.data
        primary_doc = all_docs[0]

        wiki_content = self._compile_wiki(primary_doc, all_docs)

        wiki_path = self._get_wiki_path(site_id, asset_id)
        wiki_path.parent.mkdir(parents=True, exist_ok=True)
        wiki_path.write_text(wiki_content, encoding="utf-8")

        return str(wiki_path)

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def _get_wiki_path(self, site_id: str, asset_id: str) -> Path:
        """Return wiki/{site_id}/{asset_id}.md path."""
        return self.wiki_root / site_id / f"{asset_id}.md"

    def _compile_wiki(self, doc: dict, all_asset_docs: list[dict]) -> str:
        """
        Compile a Jinja2-free markdown wiki page for an asset.

        Sections:
        # {asset_id} — {equipment_description or "Unknown Equipment"}

        ## Equipment
        ## Document Summary
        ## Service History
        ## References
        """
        asset_id = doc.get("asset_id") or "Unknown"
        equipment_desc = doc.get("equipment_description") or "Unknown Equipment"

        lines: list[str] = []

        # Header
        lines.append(f"# {asset_id} — {equipment_desc}\n")

        # Equipment table
        lines.append("## Equipment\n")
        lines.append("| Field | Value |")
        lines.append("|-------|-------|")
        lines.append(f"| Asset ID | {asset_id} |")
        lines.append(f"| Site | {doc.get('site_id', 'S002')} |")
        sub_class = doc.get("sub_class") or doc.get("document_type") or "—"
        lines.append(f"| Equipment Type | {sub_class} |")
        lines.append(f"| Description | {equipment_desc} |")
        lines.append("")

        # Document Summary (first/current doc)
        lines.append("## Document Summary\n")
        lines.append("| Date | Type | Contractor | Technician | Source |")
        lines.append("|------|------|-----------|------------|--------|")
        doc_date = doc.get("document_date") or "—"
        doc_type = doc.get("document_type") or "—"
        contractor = doc.get("contractor_vendor") or "—"
        tech = doc.get("technician_name") or "—"
        source_system = doc.get("source_system") or "—"
        lines.append(f"| {doc_date} | {doc_type} | {contractor} | {tech} | {source_system} |")
        lines.append("")

        # Service History
        lines.append("## Service History\n")
        for d in sorted(
            all_asset_docs,
            key=lambda x: x.get("document_date") or "",
            reverse=True,
        ):
            doc_date = d.get("document_date") or "Unknown date"
            doc_type = d.get("document_type") or "—"
            lines.append(f"### {doc_date} — {doc_type}\n")
            lines.append(f"- **Contractor:** {d.get('contractor_vendor') or '—'}")
            lines.append(f"- **Technician:** {d.get('technician_name') or '—'}")
            source_sys = d.get("source_system") or "—"
            src_doc_id = d.get("source_document_id") or "—"
            lines.append(f"- **Source:** {source_sys} / {src_doc_id}")
            lines.append(f"- **Notes:** {d.get('tech_notes') or '—'}")
            raw_path = d.get("raw_file_path") or d.get("source_url") or "—"
            lines.append(f"- **File:** {raw_path}")
            lines.append("")

        # References
        lines.append("## References\n")
        for d in all_asset_docs:
            src_doc_id = d.get("source_document_id") or "—"
            src_url = d.get("source_url") or d.get("raw_file_path") or "—"
            doc_type = d.get("document_type") or "—"
            doc_date = d.get("document_date") or "—"
            lines.append(f"- [{src_doc_id}]({src_url}) — {doc_type}, {doc_date}")

        return "\n".join(lines)

    async def _compiler_queue_available(self) -> bool:
        """
        Check if compiler_queue table and processed_at column exist.
        Graceful degradation: returns False if either is missing.
        """
        try:
            result = self.db.table("information_schema.columns").select(
                "column_name"
            ).eq("table_name", "compiler_queue").execute()

            if not result.data:
                logger.warning(
                    "[WikiCompiler] compiler_queue table not found in information_schema"
                )
                return False

            existing_cols = {r["column_name"] for r in result.data}
            required = {"asset_id", "document_id", "processed_at"}
            if not required.issubset(existing_cols):
                missing = required - existing_cols
                logger.warning(
                    "[WikiCompiler] compiler_queue missing columns: %s",
                    missing,
                )
                return False

            return True

        except Exception as exc:
            logger.warning(
                "[WikiCompiler] _compiler_queue_available failed: %s",
                exc,
            )
            return False

    def _mark_processed(self, entry_id: str) -> None:
        """Mark a compiler_queue entry as processed."""
        try:
            self.db.table("compiler_queue").update(
                {"processed_at": datetime.utcnow().isoformat()}
            ).eq("id", entry_id).execute()
        except Exception as exc:
            logger.warning(
                "[WikiCompiler] failed to mark entry %s processed: %s",
                entry_id,
                exc,
            )