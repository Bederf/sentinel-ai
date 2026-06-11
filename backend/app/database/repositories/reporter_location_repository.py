"""Repository for call-log reporter location memory.

Stores the last confirmed location per reporter identity so mobile intake
flows can suggest a known desk/location on subsequent reports.

Fallback pattern: Supabase table (if available) -> JSON file.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent.parent / "data"
JSON_PATH = DATA_DIR / "reporter_location_memory.json"


class ReporterLocationRepository:
    """Persistence for reporter -> last confirmed location memory."""

    def __init__(self) -> None:
        self.client = None
        try:
            self.client = get_supabase_client()
        except Exception as exc:  # pragma: no cover
            logger.warning("ReporterLocationRepository: Supabase client unavailable: %s", exc)

    @staticmethod
    def normalize_phone(phone: str | None) -> str:
        """Normalize phone number to a stable matching format.

        Keeps digits and optional leading plus sign.
        """
        if not phone:
            return ""

        raw = phone.strip()
        if not raw:
            return ""

        has_plus = raw.startswith("+")
        digits = re.sub(r"\D", "", raw)
        if not digits:
            return ""

        return f"+{digits}" if has_plus else digits

    def get_latest(
        self,
        *,
        reporter_phone: str | None = None,
        reporter_telegram_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Get latest memory row by phone and/or telegram reporter identity."""
        norm_phone = self.normalize_phone(reporter_phone)
        telegram_id = (reporter_telegram_id or "").strip()

        if not norm_phone and not telegram_id:
            return None

        if self.client:
            try:
                query = self.client.table("reporter_location_memory").select("*")
                if norm_phone and telegram_id:
                    import re

                    safe_phone = re.sub(r"[,.()\s]", "", norm_phone)
                    safe_tg = re.sub(r"[,.()\s]", "", telegram_id)
                    query = query.or_(f"reporter_phone.eq.{safe_phone},reporter_telegram_id.eq.{safe_tg}")
                elif norm_phone:
                    query = query.eq("reporter_phone", norm_phone)
                else:
                    query = query.eq("reporter_telegram_id", telegram_id)

                result = query.order("updated_at", desc=True).limit(1).execute()
                if result.data:
                    return result.data[0]
                return None  # Supabase has no record — don't fall back to stale JSON
            except Exception as exc:
                logger.debug("ReporterLocationRepository.get_latest Supabase failed: %s", exc)
                return self._get_latest_json(norm_phone=norm_phone, telegram_id=telegram_id)

        return None

    def upsert(self, record: dict[str, Any]) -> dict[str, Any] | None:
        """Create/update latest memory by identity."""
        norm_phone = self.normalize_phone(record.get("reporter_phone"))
        telegram_id = (record.get("reporter_telegram_id") or "").strip()

        if not norm_phone and not telegram_id:
            return None

        now = datetime.utcnow().isoformat()
        payload = {
            "reporter_phone": norm_phone or None,
            "reporter_telegram_id": telegram_id or None,
            "reporter_name": record.get("reporter_name") or None,
            "site_id": record.get("site_id") or None,
            "zone_id": record.get("zone_id") or None,
            "floor": record.get("floor") or None,
            "desk_id": record.get("desk_id") or None,
            "location_text": record.get("location_text") or None,
            "last_work_order_code": record.get("last_work_order_code") or None,
            "last_confirmed_at": record.get("last_confirmed_at") or now,
            "channel": record.get("channel") or "unknown",
            "source": record.get("source") or "call_log",
            "updated_at": now,
        }

        existing = self.get_latest(reporter_phone=norm_phone, reporter_telegram_id=telegram_id)

        if self.client:
            try:
                if existing and existing.get("id"):
                    result = (
                        self.client.table("reporter_location_memory").update(payload).eq("id", existing["id"]).execute()
                    )
                    if result.data:
                        return result.data[0]
                else:
                    payload["id"] = str(uuid.uuid4())
                    payload["created_at"] = now
                    result = self.client.table("reporter_location_memory").insert(payload).execute()
                    if result.data:
                        return result.data[0]
            except Exception as exc:
                logger.debug("ReporterLocationRepository.upsert Supabase failed: %s", exc)

        return self._upsert_json(payload, existing_id=(existing or {}).get("id"))

    # ------------------------------------------------------------------
    # JSON fallback
    # ------------------------------------------------------------------

    def _load_json(self) -> list[dict[str, Any]]:
        if JSON_PATH.exists():
            try:
                with open(JSON_PATH) as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                return []
        return []

    def _save_json(self, data: list[dict[str, Any]]) -> None:
        JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(JSON_PATH, "w") as f:
            json.dump(data, f, indent=2, default=str)

    def _get_latest_json(self, *, norm_phone: str, telegram_id: str) -> dict[str, Any] | None:
        rows = self._load_json()
        matches: list[dict[str, Any]] = []
        for row in rows:
            if norm_phone and row.get("reporter_phone") == norm_phone:
                matches.append(row)
                continue
            if telegram_id and row.get("reporter_telegram_id") == telegram_id:
                matches.append(row)

        if not matches:
            return None

        matches.sort(key=lambda r: r.get("updated_at", ""), reverse=True)
        return matches[0]

    def _upsert_json(self, payload: dict[str, Any], *, existing_id: str | None) -> dict[str, Any]:
        rows = self._load_json()

        if existing_id:
            for idx, row in enumerate(rows):
                if row.get("id") == existing_id:
                    payload["id"] = existing_id
                    payload.setdefault("created_at", row.get("created_at") or payload["updated_at"])
                    rows[idx] = payload
                    self._save_json(rows)
                    return payload

        payload.setdefault("id", str(uuid.uuid4()))
        payload.setdefault("created_at", payload["updated_at"])
        rows.append(payload)
        self._save_json(rows)
        return payload


_repo: ReporterLocationRepository | None = None


def get_reporter_location_repository() -> ReporterLocationRepository:
    """Get singleton reporter location repository."""
    global _repo
    if _repo is None:
        _repo = ReporterLocationRepository()
    return _repo
