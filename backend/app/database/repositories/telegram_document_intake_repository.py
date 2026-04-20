"""Repository for Telegram document intake persistence.

Follows the same lightweight Supabase -> JSON fallback approach used by other
intake pipelines in this repository.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
JSON_PATH = DATA_DIR / "telegram_document_intakes.json"


class TelegramDocumentIntakeRepository:
    """Persistence boundary for Telegram-assisted raw document intake."""

    def __init__(self) -> None:
        self.client = None
        try:
            self.client = get_supabase_client()
        except Exception as exc:  # pragma: no cover
            logger.warning("TelegramDocumentIntakeRepository: Supabase client unavailable: %s", exc)

    def create(self, record: dict[str, Any]) -> dict[str, Any]:
        """Create a new intake record."""
        if "id" not in record:
            record["id"] = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        record.setdefault("created_at", now)
        record.setdefault("updated_at", now)
        record.setdefault("intake_status", "metadata_pending")

        if self.client:
            try:
                result = self.client.table("telegram_document_intakes").insert(record).execute()
                if result.data:
                    return result.data[0]
            except Exception as exc:
                logger.error("TelegramDocumentIntakeRepository.create failed (Supabase): %s", exc)

        return self._create_json(record)

    def get_by_id(self, intake_id: str) -> dict[str, Any] | None:
        """Look up a single intake record."""
        if not intake_id:
            return None

        if self.client:
            try:
                result = (
                    self.client.table("telegram_document_intakes").select("*").eq("id", intake_id).limit(1).execute()
                )
                if result.data:
                    return result.data[0]
            except Exception as exc:
                logger.error("TelegramDocumentIntakeRepository.get_by_id failed: %s", exc)

        for row in self._load_json():
            if row.get("id") == intake_id:
                return row
        return None

    def update(self, intake_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        """Update an intake record with new status or save details."""
        payload = dict(updates)
        payload["updated_at"] = datetime.utcnow().isoformat()

        if self.client:
            try:
                result = self.client.table("telegram_document_intakes").update(payload).eq("id", intake_id).execute()
                if result.data:
                    return result.data[0]
            except Exception as exc:
                logger.error("TelegramDocumentIntakeRepository.update failed: %s", exc)

        return self._update_json(intake_id, payload)

    def _load_json(self) -> list[dict[str, Any]]:
        if not JSON_PATH.exists():
            return []
        try:
            return json.loads(JSON_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []

    def _save_json(self, rows: list[dict[str, Any]]) -> None:
        JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
        JSON_PATH.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    def _create_json(self, record: dict[str, Any]) -> dict[str, Any]:
        rows = self._load_json()
        rows.append(record)
        self._save_json(rows)
        return record

    def _update_json(self, intake_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        rows = self._load_json()
        for row in rows:
            if row.get("id") == intake_id:
                row.update(payload)
                self._save_json(rows)
                return row
        payload["id"] = intake_id
        rows.append(payload)
        self._save_json(rows)
        return payload


_repository: TelegramDocumentIntakeRepository | None = None


def get_telegram_document_intake_repository() -> TelegramDocumentIntakeRepository:
    global _repository
    if _repository is None:
        _repository = TelegramDocumentIntakeRepository()
    return _repository
