"""Repository for alert routing rules."""

from __future__ import annotations

from typing import Any

from app.database.supabase_client import get_supabase_client


class AlertRoutingRuleRepository:
    """CRUD access to canonical alert routing rules."""

    _COLUMNS = (
        "id, name, enabled, severity, equipment_types, site_ids, channels, "
        "recipient_roles, recipient_ids, escalation_minutes, escalation_to_roles, "
        "created_at, updated_at, created_by, updated_by"
    )

    def __init__(self) -> None:
        self.client = get_supabase_client()

    def list_rules(self) -> list[dict[str, Any]]:
        result = self.client.table("alert_routing_rules").select(self._COLUMNS).order("created_at").execute()
        return [dict(row) for row in (result.data or [])]

    def create_rule(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = self.client.table("alert_routing_rules").insert(payload).execute()
        if result.data:
            return dict(result.data[0])
        return payload

    def update_rule(self, rule_id: str, update_data: dict[str, Any]) -> dict[str, Any] | None:
        result = self.client.table("alert_routing_rules").update(update_data).eq("id", rule_id).execute()
        if result.data:
            return dict(result.data[0])
        return None

    def delete_rule(self, rule_id: str) -> bool:
        result = self.client.table("alert_routing_rules").delete().eq("id", rule_id).execute()
        return bool(result.data)
