"""Synchronize zone-level equipment pointers across zone registries.

The onboarding pipeline already resolves zone→equipment relationships into
``equipment_zone_relationships`` and canonical equipment records.  Several
runtime paths still read ``zones.fcu_id`` / ``vav_id`` / ``ahu_id`` / ``lighting_id``
directly, so this helper keeps those denormalized fields in sync with the
canonical equipment inventory.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

ZONE_EQUIPMENT_COLUMNS = {
    "fcu": "fcu_id",
    "vav": "vav_id",
    "ahu": "ahu_id",
    "dali": "lighting_id",
    "lum": "lighting_id",
    "lighting": "lighting_id",
    "lighting_panel": "lighting_id",
    "zone": "lighting_id",
}


@dataclass(frozen=True)
class ZoneEquipmentSyncResult:
    zones_considered: int
    zones_updated: int
    assignments_applied: int


class ZoneEquipmentSyncService:
    """Backfill zone tables from equipment and relationship mappings."""

    def __init__(self, client: Any | None = None):
        if client is None:
            from app.database.supabase_client import get_supabase_client

            client = get_supabase_client()
        self.client = client

    def sync_site(self, site_uuid: str) -> ZoneEquipmentSyncResult:
        equipment_rows = self._load_equipment(site_uuid)
        relationship_rows = self._load_relationships(site_uuid)
        assignments = self._build_assignments(equipment_rows, relationship_rows)
        if not assignments:
            return ZoneEquipmentSyncResult(zones_considered=0, zones_updated=0, assignments_applied=0)

        zones_updated = 0
        for table in ("zones", "hvac_zones"):
            zones_updated += self._apply_assignments(table, site_uuid, assignments)

        return ZoneEquipmentSyncResult(
            zones_considered=len(assignments),
            zones_updated=zones_updated,
            assignments_applied=sum(len(values) for values in assignments.values()),
        )

    def _load_equipment(self, site_uuid: str) -> list[dict[str, Any]]:
        response = (
            self.client.table("equipment")
            .select("id, code, canonical_code, raw_code, type, zone_key, canonical_zone_id")
            .eq("site_id", site_uuid)
            .execute()
        )
        return response.data or []

    def _load_relationships(self, site_uuid: str) -> list[dict[str, Any]]:
        response = (
            self.client.table("equipment_zone_relationships")
            .select("equipment_id, zone_id, relationship_type, review_status")
            .eq("site_id", site_uuid)
            .execute()
        )
        return [row for row in response.data or [] if str(row.get("review_status") or "").lower() != "rejected"]

    def _build_assignments(
        self,
        equipment_rows: list[dict[str, Any]],
        relationship_rows: list[dict[str, Any]],
    ) -> dict[str, dict[str, str]]:
        equipment_by_id = {str(row.get("id")): row for row in equipment_rows if row.get("id")}
        assignments: dict[str, dict[str, str]] = defaultdict(dict)

        for row in equipment_rows:
            zone_id = self._zone_id_from_equipment_row(row)
            column = self._column_for_equipment(row)
            equipment_code = self._preferred_equipment_code(row)
            if zone_id and column and equipment_code:
                assignments[zone_id].setdefault(column, equipment_code)

        for row in relationship_rows:
            zone_id = str(row.get("zone_id") or "").strip()
            equipment = equipment_by_id.get(str(row.get("equipment_id") or ""))
            if not zone_id or not equipment:
                continue
            column = self._column_for_equipment(equipment)
            equipment_code = self._preferred_equipment_code(equipment)
            if zone_id and column and equipment_code:
                assignments[zone_id].setdefault(column, equipment_code)

        return dict(assignments)

    def _apply_assignments(
        self,
        table_name: str,
        site_uuid: str,
        assignments: dict[str, dict[str, str]],
    ) -> int:
        updated = 0
        for zone_id, values in assignments.items():
            payload = {column: code for column, code in values.items() if code}
            if not payload:
                continue
            response = (
                self.client.table(table_name).update(payload).eq("site_id", site_uuid).eq("zone_id", zone_id).execute()
            )
            if response.data:
                updated += 1
        return updated

    def _zone_id_from_equipment_row(self, row: dict[str, Any]) -> str | None:
        for key in ("zone_key", "canonical_zone_id"):
            value = row.get(key)
            if value and str(value).strip():
                return str(value).strip()
        return None

    def _column_for_equipment(self, row: dict[str, Any]) -> str | None:
        equipment_type = _normalize_equipment_type(row.get("type") or row.get("code") or row.get("canonical_code"))
        if not equipment_type:
            return None
        return ZONE_EQUIPMENT_COLUMNS.get(equipment_type)

    def _preferred_equipment_code(self, row: dict[str, Any]) -> str | None:
        for key in ("canonical_code", "code", "raw_code"):
            value = row.get(key)
            if value and str(value).strip():
                return str(value).strip()
        return None


def _normalize_equipment_type(value: Any) -> str | None:
    raw = str(value or "").strip().lower()
    if not raw:
        return None
    if raw in {"lighting", "lighting_panel", "luminaire", "lum", "dali", "dali_controller", "zone", "zone_controller"}:
        if raw in {"lighting", "lighting_panel", "luminaire", "lum"}:
            return "lighting"
        if raw == "dali_controller":
            return "dali"
        return "zone" if raw in {"zone", "zone_controller"} else raw
    if raw == "dali_controller":
        return "dali"
    if raw == "zone_controller":
        return "zone"
    code_match = re.fullmatch(r"s\d{3}-([a-z0-9_]+)-.+", raw)
    if code_match:
        return _normalize_equipment_type(code_match.group(1))
    return raw
