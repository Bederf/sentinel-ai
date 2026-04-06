"""Concept raw document storage adapter for Telegram document intake.

The upload request path writes the raw file and minimal metadata only.
Later ingestion jobs are responsible for OCR, classification refinement,
and search indexing.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

from app.config.settings import settings
from app.database.supabase_client import get_supabase_client
from app.security.document_scanner import validate_and_scan_upload

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DEFAULT_RAW_ROOT = DATA_DIR / "concept_raw_documents"
DEFAULT_INDEX_PATH = DATA_DIR / "concept_raw_documents_index.json"


class ConceptRawDocumentSaveError(RuntimeError):
    """Raised when a raw document cannot be saved."""


@dataclass(slots=True)
class DownloadedTelegramFile:
    file_bytes: bytes
    file_extension: str
    telegram_file_path: str
    mime_type: str | None = None


class ConceptRawDocumentService:
    """Persist raw Telegram-uploaded files into the Concept raw-document store."""

    def __init__(
        self,
        *,
        raw_root: Path | str = DEFAULT_RAW_ROOT,
        index_path: Path | str = DEFAULT_INDEX_PATH,
    ) -> None:
        self.raw_root = Path(raw_root)
        self.index_path = Path(index_path)

    async def save_telegram_document(
        self,
        *,
        site_id: str,
        site_name: str,
        equipment_type: str,
        document_type: str,
        telegram_file_id: str,
        telegram_user_id: str,
        telegram_chat_id: str,
        received_at: str,
        equipment_id: str | None = None,
        work_order_id: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        downloaded = await self._download_telegram_file(telegram_file_id)

        received_dt = self._parse_timestamp(received_at)
        concept_document_id = f"concept_raw_{uuid4().hex[:12]}"

        file_name = self._build_filename(
            site_name=site_name,
            equipment_type=equipment_type,
            document_type=document_type,
            received_at=received_dt,
            file_extension=downloaded.file_extension,
        )
        scan_result = await validate_and_scan_upload(
            file_content=downloaded.file_bytes,
            filename=Path(downloaded.telegram_file_path).name,
            user_id=telegram_user_id,
            user_role="operator",
            site_id=site_id,
        )
        if not scan_result.allowed:
            raise ConceptRawDocumentSaveError(scan_result.rejection_reason or "Telegram upload was rejected")
        if scan_result.trust_level == "QUARANTINED":
            raise ConceptRawDocumentSaveError("Telegram upload was quarantined by the document scanner")

        concept_path = self._build_concept_path(
            site_name=site_name,
            equipment_type=equipment_type,
            document_type=document_type,
        )

        target_dir = self.raw_root / self._slug(site_name) / self._slug(equipment_type) / self._slug(document_type)
        target_dir.mkdir(parents=True, exist_ok=True)
        stored_path = target_dir / file_name
        stored_path.write_bytes(downloaded.file_bytes)

        record = {
            "concept_document_id": concept_document_id,
            "source": "telegram_sentry",
            "site_id": site_id,
            "site_name": site_name,
            "equipment_type": equipment_type,
            "document_type": document_type,
            "notes": notes or "",
            "telegram_file_id": telegram_file_id,
            "telegram_file_path": downloaded.telegram_file_path,
            "telegram_user_id": telegram_user_id,
            "telegram_chat_id": telegram_chat_id,
            "equipment_id": equipment_id,
            "work_order_id": work_order_id,
            "received_at": received_at,
            "saved_at": datetime.utcnow().isoformat() + "Z",
            "file_name": file_name,
            "file_extension": downloaded.file_extension,
            "mime_type": downloaded.mime_type,
            "file_hash": scan_result.file_hash,
            "scan_detected_type": scan_result.detected_type,
            "scan_trust_level": scan_result.trust_level,
            "concept_path": concept_path,
            "stored_path": str(stored_path),
            "storage_mode": "filesystem",
        }
        self._append_index_record(record)
        supabase_document_id = self._persist_supabase_document_row(
            title=f"{self._title(document_type)} - {self._title(equipment_type)}",
            site_id=site_id,
            file_name=file_name,
            stored_path=str(stored_path),
            equipment_id=equipment_id,
            work_order_id=work_order_id,
            equipment_type=equipment_type,
            document_type=document_type,
            notes=notes or "",
        )

        logger.info(
            "Saved raw Concept intake document %s for site=%s equipment_type=%s document_type=%s",
            concept_document_id,
            site_id,
            equipment_type,
            document_type,
        )

        return {
            "status": "saved",
            "concept_document_id": concept_document_id,
            "supabase_document_id": supabase_document_id,
            "site_id": site_id,
            "site_name": site_name,
            "concept_path": concept_path,
            "file_name": file_name,
            "file_hash": scan_result.file_hash,
            "scan_detected_type": scan_result.detected_type,
            "scan_trust_level": scan_result.trust_level,
            "stored_path": str(stored_path),
        }

    def _persist_supabase_document_row(
        self,
        *,
        title: str,
        site_id: str,
        file_name: str,
        stored_path: str,
        equipment_id: str | None,
        work_order_id: str | None,
        equipment_type: str,
        document_type: str,
        notes: str,
    ) -> str | None:
        """Persist Telegram intake metadata into documents table for equipment linkage."""
        try:
            client = get_supabase_client()
            payload = {
                "site_id": site_id,
                "title": title,
                "document_type": "service_report",
                "source": "telegram_sentry",
                "storage_path": stored_path,
                "indexing_status": "embedded",
                "keywords": [
                    f"equipment_type:{equipment_type}",
                    f"document_type:{document_type}",
                    f"equipment_id:{equipment_id or ''}",
                    f"work_order_id:{work_order_id or ''}",
                    f"file_name:{file_name}",
                    f"notes:{notes}" if notes else "notes:",
                ],
            }
            result = client.table("documents").insert(payload).execute()
            if result.data:
                return result.data[0].get("id")
        except Exception as exc:
            logger.warning("Failed to persist telegram intake document row in Supabase: %s", exc)
        return None

    async def _download_telegram_file(self, telegram_file_id: str) -> DownloadedTelegramFile:
        token = (settings.telegram_bot_token or "").strip()
        if not token:
            raise ConceptRawDocumentSaveError("telegram_bot_token is not configured")

        base_url = f"https://api.telegram.org/bot{token}"
        file_url_root = f"https://api.telegram.org/file/bot{token}"

        try:
            async with httpx.AsyncClient(timeout=20) as client:
                metadata_response = await client.get(f"{base_url}/getFile", params={"file_id": telegram_file_id})
                metadata_response.raise_for_status()
                metadata_payload = metadata_response.json()
                if not metadata_payload.get("ok") or not metadata_payload.get("result", {}).get("file_path"):
                    raise ConceptRawDocumentSaveError("Telegram did not return a file path")

                telegram_file_path = metadata_payload["result"]["file_path"]
                content_response = await client.get(f"{file_url_root}/{telegram_file_path}")
                content_response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ConceptRawDocumentSaveError(f"Failed to download Telegram file: {exc}") from exc

        file_extension = Path(telegram_file_path).suffix.lower() or ".jpg"
        return DownloadedTelegramFile(
            file_bytes=content_response.content,
            file_extension=file_extension,
            telegram_file_path=telegram_file_path,
            mime_type=content_response.headers.get("content-type"),
        )

    def _append_index_record(self, record: dict[str, Any]) -> None:
        rows: list[dict[str, Any]]
        if self.index_path.exists():
            try:
                rows = json.loads(self.index_path.read_text(encoding="utf-8"))
                if not isinstance(rows, list):
                    rows = []
            except json.JSONDecodeError:
                rows = []
        else:
            rows = []

        rows.append(record)
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    def _build_filename(
        self,
        *,
        site_name: str,
        equipment_type: str,
        document_type: str,
        received_at: datetime,
        file_extension: str,
    ) -> str:
        date_part = received_at.date().isoformat()
        return (
            f"{self._file_token(site_name)}_"
            f"{self._file_token(equipment_type)}_"
            f"{self._file_token(document_type)}_"
            f"{date_part}{file_extension}"
        )

    def _build_concept_path(self, *, site_name: str, equipment_type: str, document_type: str) -> str:
        return f"{self._title(site_name)}/{self._title(equipment_type)}/{self._title(document_type)}"

    def _parse_timestamp(self, value: str) -> datetime:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ConceptRawDocumentSaveError(f"Invalid received_at timestamp: {value}") from exc

    def _file_token(self, value: str) -> str:
        token = re.sub(r"[^A-Za-z0-9]+", "-", value.strip()).strip("-")
        return token.upper() or "DOCUMENT"

    def _slug(self, value: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
        return slug or "document"

    def _title(self, value: str) -> str:
        return value.replace("_", " ").strip().title()


_concept_raw_document_service: ConceptRawDocumentService | None = None


def get_concept_raw_document_service() -> ConceptRawDocumentService:
    global _concept_raw_document_service
    if _concept_raw_document_service is None:
        _concept_raw_document_service = ConceptRawDocumentService()
    return _concept_raw_document_service
