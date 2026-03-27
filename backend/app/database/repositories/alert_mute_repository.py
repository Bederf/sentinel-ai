"""Repository for alert mute runtime state."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.database.supabase_client import get_supabase_client


class AlertMuteRepository:
    """CRUD access to active alert mutes."""

    _COLUMNS = "id, equipment_code, reason, duration_hours, muted_at, muted_until, muted_by, created_at"

    def __init__(self) -> None:
        self.client = get_supabase_client()

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(UTC).isoformat()

    def list_active(self) -> list[dict[str, Any]]:
        result = (
            self.client.table("alert_mutes")
            .select(self._COLUMNS)
            .gt("muted_until", self._now_iso())
            .order("muted_until")
            .execute()
        )
        return [dict(row) for row in (result.data or [])]

    def get_active_for_equipment(self, equipment_code: str) -> dict[str, Any] | None:
        result = (
            self.client.table("alert_mutes")
            .select(self._COLUMNS)
            .eq("equipment_code", equipment_code)
            .gt("muted_until", self._now_iso())
            .limit(1)
            .execute()
        )
        if result.data:
            return dict(result.data[0])
        return None

    def create_mute(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = self.client.table("alert_mutes").insert(payload).execute()
        if result.data:
            return dict(result.data[0])
        return payload

    def delete_active_for_equipment(self, equipment_code: str) -> bool:
        result = self.client.table("alert_mutes").delete().eq("equipment_code", equipment_code).execute()
        return bool(result.data)
