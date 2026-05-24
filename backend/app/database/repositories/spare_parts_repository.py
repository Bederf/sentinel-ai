"""Repository for spare parts catalog and inventory operations."""

import logging
from datetime import datetime
from typing import Any

from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class SparePartsRepository:
    """Repository for spare_parts and spare_parts_inventory tables."""

    def __init__(self):
        self.client = get_supabase_client()

    def get_parts_for_equipment(self, equipment_id: str) -> list[dict[str, Any]]:
        """Get spare parts linked to a specific equipment instance."""
        response = (
            self.client.table("spare_parts")
            .select("*, spare_parts_inventory!left(*)")
            .eq("equipment_id", equipment_id)
            .eq("is_active", True)
            .execute()
        )
        return response.data or []

    def get_parts_for_type(
        self,
        equipment_type: str,
        manufacturer: str | None = None,
        model: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get spare parts by equipment type with optional manufacturer/model filter.

        Matches in order of specificity:
        1. Exact manufacturer + model match
        2. Manufacturer-only match (model-agnostic parts)
        3. Equipment-type fallback (generic parts for this type)
        """
        base = (
            self.client.table("spare_parts")
            .select("*, spare_parts_inventory!left(*)")
            .eq("equipment_type", equipment_type)
            .eq("is_active", True)
        )

        if manufacturer and model:
            exact = base.eq("manufacturer", manufacturer).eq("model", model).execute()
            if exact.data:
                return exact.data

        if manufacturer:
            mfr = base.eq("manufacturer", manufacturer).is_("model", "null").execute()
            if mfr.data:
                return mfr.data

        generic = base.is_("manufacturer", "null").is_("model", "null").execute()
        return generic.data or []

    def get_part_by_id(self, part_id: str) -> dict[str, Any] | None:
        """Get single part by UUID with inventory."""
        response = (
            self.client.table("spare_parts")
            .select("*, spare_parts_inventory!left(*)")
            .eq("id", part_id)
            .execute()
        )
        return response.data[0] if response.data else None

    def create_part(self, part_data: dict[str, Any]) -> dict[str, Any] | None:
        """Create a new spare part entry. Returns created record."""
        part_data["updated_at"] = datetime.now().isoformat()
        response = self.client.table("spare_parts").insert(part_data).execute()
        if not response.data:
            return None
        part = response.data[0]

        inventory_entry = {
            "part_id": part["id"],
            "quantity_on_hand": part_data.get("initial_stock", 0),
            "min_threshold": part_data.get("min_threshold", 2),
            "max_threshold": part_data.get("max_threshold", 10),
            "location": part_data.get("location", ""),
        }
        self.client.table("spare_parts_inventory").insert(inventory_entry).execute()

        return self.get_part_by_id(part["id"])

    def update_part(self, part_id: str, part_data: dict[str, Any]) -> dict[str, Any] | None:
        """Update spare part fields."""
        part_data["updated_at"] = datetime.now().isoformat()
        response = (
            self.client.table("spare_parts")
            .update(part_data)
            .eq("id", part_id)
            .execute()
        )
        return response.data[0] if response.data else None

    def update_inventory(
        self, part_id: str, quantity_on_hand: int, location: str | None = None
    ) -> dict[str, Any] | None:
        """Update stock quantity for a spare part."""
        inv = (
            self.client.table("spare_parts_inventory")
            .update({
                "quantity_on_hand": quantity_on_hand,
                "updated_at": datetime.now().isoformat(),
                **({"location": location} if location else {}),
            })
            .eq("part_id", part_id)
            .execute()
        )
        return inv.data[0] if inv.data else None

    def decrement_stock(self, part_id: str, quantity: int = 1) -> dict[str, Any] | None:
        """Decrement inventory quantity (after part used in work order)."""
        current = (
            self.client.table("spare_parts_inventory")
            .select("quantity_on_hand")
            .eq("part_id", part_id)
            .execute()
        )
        if not current.data:
            return None
        current_qty = current.data[0]["quantity_on_hand"]
        new_qty = max(0, current_qty - quantity)
        return self.update_inventory(part_id, new_qty)

    def search_parts(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """Search parts by name or part number."""
        response = (
            self.client.table("spare_parts")
            .select("*, spare_parts_inventory!left(*)")
            .or_(
                f"part_name.ilike.%{query}%,"
                f"part_number.ilike.%{query}%"
            )
            .eq("is_active", True)
            .limit(limit)
            .execute()
        )
        return response.data or []

    def get_low_stock_parts(self, site_id: str | None = None) -> list[dict[str, Any]]:
        """Get parts where quantity_on_hand <= min_threshold."""
        query = (
            self.client.table("spare_parts")
            .select("*, spare_parts_inventory!left(*)")
            .eq("is_active", True)
        )
        response = query.execute()
        parts = response.data or []
        low = []
        for p in parts:
            inv = p.get("spare_parts_inventory")
            if isinstance(inv, list):
                inv = inv[0] if inv else {}
            if isinstance(inv, dict) and inv.get("quantity_on_hand", 0) <= inv.get("min_threshold", 2):
                low.append(p)
        return low

    def link_to_equipment(self, part_id: str, equipment_id: str) -> dict[str, Any] | None:
        """Link a generic part to a specific equipment instance."""
        return self.update_part(part_id, {"equipment_id": equipment_id})
