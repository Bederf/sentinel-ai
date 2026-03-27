"""Repository for runtime equipment health configuration."""

from __future__ import annotations

from typing import Any

from app.database.supabase_client import get_supabase_client


class EquipmentHealthConfigRepository:
    """CRUD access to canonical equipment health configuration."""

    _COLUMNS = "equipment_type, expected_life_years, service_interval_days, weights, thresholds, fault_weights"

    def __init__(self) -> None:
        self.client = get_supabase_client()

    @staticmethod
    def _normalize_type(equipment_type: str) -> str:
        return equipment_type.strip().lower()

    def list_configs(self) -> dict[str, dict[str, Any]]:
        result = self.client.table("equipment_health_configs").select(self._COLUMNS).execute()
        rows = result.data or []
        return {row["equipment_type"]: dict(row) for row in rows}

    def get_config(self, equipment_type: str) -> dict[str, Any] | None:
        result = (
            self.client.table("equipment_health_configs")
            .select(self._COLUMNS)
            .eq("equipment_type", self._normalize_type(equipment_type))
            .limit(1)
            .execute()
        )
        if result.data:
            return dict(result.data[0])
        return None

    def upsert_config(self, config: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "equipment_type": self._normalize_type(config["equipment_type"]),
            "expected_life_years": config["expected_life_years"],
            "service_interval_days": config["service_interval_days"],
            "weights": config["weights"],
            "thresholds": config["thresholds"],
            "fault_weights": config.get("fault_weights"),
        }
        result = self.client.table("equipment_health_configs").upsert(payload, on_conflict="equipment_type").execute()
        if result.data:
            return dict(result.data[0])
        return payload

    def delete_config(self, equipment_type: str) -> bool:
        result = (
            self.client.table("equipment_health_configs")
            .delete()
            .eq("equipment_type", self._normalize_type(equipment_type))
            .execute()
        )
        return bool(result.data)
