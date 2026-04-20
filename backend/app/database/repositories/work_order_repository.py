"""
Work Order Repository - Database operations for work orders.
"""

import logging
from datetime import date, datetime
from typing import Any

from ..supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class WorkOrderRepository:
    """Repository for work order operations."""

    _LIST_COLUMNS = (
        "id, code, title, description, priority, status, "
        "assigned_to, assigned_team, equipment_id, site_id, "
        "scheduled_date, completed_at, created_at, created_by, "
        "estimated_duration_hours"
    )

    _DETAIL_COLUMNS = (
        "id, code, title, description, priority, status, "
        "assigned_to, assigned_team, equipment_id, site_id, "
        "scheduled_date, completed_at, created_at, created_by, "
        "estimated_duration_hours, actual_duration_hours, "
        "labour_cost_zar, parts_cost_zar, total_cost_zar, "
        "notes, resolution, category, updated_at, "
        "equipment(code, name, type), buildings(code, name)"
    )

    def __init__(self):
        self.client = get_supabase_client()

    async def create_work_order(self, work_order: dict[str, Any]) -> dict[str, Any] | None:
        """
        Create a new work order in Supabase.

        Args:
            work_order: Work order data including:
                - equipment_id or equipment_code
                - title
                - description
                - priority (low, medium, high, urgent)
                - assigned_to (technician name)
                - scheduled_date (optional)

        Returns:
            Created work order with generated code, or None on error
        """
        if not self.client:
            logger.warning("Supabase client not available")
            return None

        try:
            # If equipment_code provided, resolve to equipment_id and site_id
            equipment_id = work_order.get("equipment_id")
            site_id = work_order.get("site_id")

            if not equipment_id and work_order.get("equipment_code"):
                eq_result = (
                    self.client.table("equipment")
                    .select("id, site_id")
                    .eq("code", work_order["equipment_code"])
                    .execute()
                )

                if eq_result.data and len(eq_result.data) > 0:
                    equipment_id = eq_result.data[0]["id"]
                    site_id = eq_result.data[0]["site_id"]

            # Build insert payload
            payload = {
                "title": work_order.get("title", "Maintenance Required"),
                "description": work_order.get("description"),
                "priority": work_order.get("priority", "medium"),
                "status": work_order.get("status", "scheduled"),
                "assigned_to": work_order.get("assigned_to"),
                "assigned_team": work_order.get("assigned_team"),
                "scheduled_date": work_order.get("scheduled_date"),
                "estimated_duration_hours": work_order.get("estimated_duration_hours"),
                "created_by": work_order.get("created_by", "SENTINEL"),
            }

            if equipment_id:
                payload["equipment_id"] = equipment_id
            if site_id:
                payload["site_id"] = site_id

            # Insert with retry on duplicate code collision (DB trigger generates code)
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    result = self.client.table("work_orders").insert(payload).execute()

                    if result.data and len(result.data) > 0:
                        created = result.data[0]
                        logger.info(f"Created work order: {created.get('code')}")
                        return created

                    return None
                except Exception as insert_err:
                    err_msg = str(insert_err)
                    if "23505" in err_msg and "work_orders_code_key" in err_msg:
                        logger.warning(f"Work order code collision (attempt {attempt + 1}/{max_retries}), retrying...")
                        if attempt == max_retries - 1:
                            raise
                        continue
                    raise

            return None

        except Exception as e:
            logger.error(f"Error creating work order: {e}")
            return None

    async def get_work_order(self, work_order_id: str) -> dict[str, Any] | None:
        """Get a work order by ID."""
        if not self.client:
            return None

        try:
            result = self.client.table("work_orders").select(self._DETAIL_COLUMNS).eq("id", work_order_id).execute()

            if result.data and len(result.data) > 0:
                return result.data[0]
            return None

        except Exception as e:
            logger.error(f"Error getting work order {work_order_id}: {e}")
            return None

    async def get_work_order_by_id(self, work_order_id: str) -> dict[str, Any] | None:
        """Backward-compatible alias for get_work_order()."""
        return await self.get_work_order(work_order_id)

    async def get_work_order_by_code(self, code: str) -> dict[str, Any] | None:
        """Get a work order by its code (e.g., WO-2026-0001)."""
        if not self.client:
            return None

        try:
            result = self.client.table("work_orders").select(self._DETAIL_COLUMNS).eq("code", code).execute()

            if result.data and len(result.data) > 0:
                return result.data[0]
            return None

        except Exception as e:
            logger.error(f"Error getting work order by code {code}: {e}")
            return None

    async def get_work_orders_for_equipment(
        self, equipment_id: str, status: str | None = None, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Get work orders for a specific equipment."""
        if not self.client:
            return []

        try:
            query = (
                self.client.table("work_orders")
                .select(self._LIST_COLUMNS)
                .eq("equipment_id", equipment_id)
                .order("created_at", desc=True)
                .limit(limit)
            )

            if status:
                query = query.eq("status", status)

            result = query.execute()
            return result.data or []

        except Exception as e:
            logger.error(f"Error getting work orders for equipment {equipment_id}: {e}")
            return []

    async def update_work_order(self, work_order_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        """Update a work order."""
        if not self.client:
            return None

        try:
            result = self.client.table("work_orders").update(updates).eq("id", work_order_id).execute()

            if result.data and len(result.data) > 0:
                return result.data[0]
            return None

        except Exception as e:
            logger.error(f"Error updating work order {work_order_id}: {e}")
            return None

    async def get_work_orders_for_equipment_list(
        self,
        equipment_ids: list[str],
        start_date: datetime | date | None = None,
        end_date: datetime | date | None = None,
        status: str | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """Get work orders for a list of equipment IDs with optional date filter."""
        if not self.client or not equipment_ids:
            return []

        try:
            query = (
                self.client.table("work_orders")
                .select(self._LIST_COLUMNS)
                .in_("equipment_id", equipment_ids)
                .order("completed_at", desc=True)
                .limit(limit)
            )

            if status:
                query = query.eq("status", status)

            if start_date:
                start_iso = start_date.isoformat()
                query = query.gte("completed_at", start_iso)
            if end_date:
                end_iso = end_date.isoformat()
                query = query.lte("completed_at", end_iso)

            result = query.execute()
            return result.data or []

        except Exception as e:
            logger.error(f"Error getting work orders for equipment list: {e}")
            return []

    async def get_all_work_orders(self, limit: int = 100, status: str | None = None) -> list[dict[str, Any]]:
        """Get all work orders with optional status filter.

        Args:
            limit: Maximum number of work orders to return
            status: Optional filter by status (scheduled, assigned, in_progress, completed, cancelled)

        Returns:
            List of all work orders
        """
        if not self.client:
            return []

        try:
            query = (
                self.client.table("work_orders").select(self._LIST_COLUMNS).order("created_at", desc=True).limit(limit)
            )

            if status:
                query = query.eq("status", status)

            result = query.execute()
            return result.data or []

        except Exception as e:
            logger.error(f"Error getting all work orders: {e}")
            return []

    async def get_work_orders_by_source(
        self,
        source: str,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        """Get work orders created by a logical source.

        Current supported source values:
        - technician: records created by technician chat workflows
        """
        source_normalized = (source or "").strip().lower()
        if not source_normalized:
            return []

        orders = await self.get_all_work_orders(limit=limit)

        if source_normalized == "technician":
            filtered: list[dict[str, Any]] = []
            for order in orders:
                created_by = str(order.get("created_by") or "").lower()
                title = str(order.get("title") or "").lower()
                if created_by.startswith("technician:") or created_by == "technician_chat":
                    filtered.append(order)
                    continue
                if title.startswith("technician:"):
                    filtered.append(order)
            return filtered

        return [o for o in orders if str(o.get("created_by") or "").lower() == source_normalized]


# Singleton instance
_repository: WorkOrderRepository | None = None


def get_work_order_repository() -> WorkOrderRepository:
    """Get singleton work order repository."""
    global _repository
    if _repository is None:
        _repository = WorkOrderRepository()
    return _repository
