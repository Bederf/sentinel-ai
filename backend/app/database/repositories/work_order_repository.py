"""
Work Order Repository - Database operations for work orders.
"""

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

from ..supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class WorkOrderRepository:
    """Repository for work order operations."""

    _LIST_COLUMNS = (
        "id, code, title, description, priority, status, "
        "assigned_to, assigned_team, equipment_id, site_id, "
        "scheduled_date, completed_at, created_at, created_by, "
        "estimated_duration_hours, milestone_status, sla_hours, sla_deadline_at"
    )

    _DETAIL_COLUMNS = (
        "id, code, title, description, priority, status, "
        "assigned_to, assigned_team, equipment_id, site_id, "
        "scheduled_date, completed_at, created_at, created_by, "
        "estimated_duration_hours, actual_duration_hours, "
        "labour_cost_zar, parts_cost_zar, total_cost_zar, "
        "notes, resolution, category, updated_at, "
        "milestone_status, assigned_at, in_progress_at, resolved_at, verified_at, "
        "sla_hours, sla_deadline_at, "
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
                "milestone_status": work_order.get("milestone_status", "assigned"),
                "sla_hours": work_order.get("sla_hours", {"assigned": 24, "in_progress": 48, "resolved": 72, "verified": 168}),
            }

            if equipment_id:
                payload["equipment_id"] = equipment_id
            if site_id:
                payload["site_id"] = site_id

            # New fields for recommendation-based WOs (dedup support)
            if work_order.get("action_point"):
                payload["action_point"] = work_order["action_point"]
            if work_order.get("action_value") is not None:
                payload["action_value"] = str(work_order["action_value"])
            if work_order.get("recommendation_id"):
                payload["recommendation_id"] = work_order["recommendation_id"]

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

    async def advance_work_order_milestone(
        self,
        work_order_id: str,
        new_milestone: str,
        by_user: str | None = None,
    ) -> dict[str, Any] | None:
        """Advance a work order to the next milestone, updating timestamp and recalculating SLA deadline.

        Args:
            work_order_id: UUID of the work order
            new_milestone: One of 'assigned', 'in_progress', 'resolved', 'verified'
            by_user: User advancing the milestone (for audit)

        Returns:
            Updated work order dict, or None on error
        """
        if not self.client:
            return None

        from datetime import UTC, datetime, timedelta
        SAST = timezone(timedelta(hours=2))
        from app.database.repositories.recommendation_sla_repository import get_recommendation_sla_repository

        # Get current work order
        wo = await self.get_work_order(work_order_id)
        if not wo:
            logger.warning(f"Work order {work_order_id} not found for milestone advance")
            return None

        now = datetime.now(SAST)
        updates: dict[str, Any] = {
            "milestone_status": new_milestone,
        }

        # Sync legacy status with milestone_status
        status_map = {
            "assigned": "scheduled",
            "in_progress": "in_progress",
            "resolved": "in_progress",
            "verified": "completed",
        }
        if new_milestone in status_map:
            updates["status"] = status_map[new_milestone]

        # Set per-milestone timestamp
        if new_milestone == "in_progress":
            updates["in_progress_at"] = now.isoformat()
        elif new_milestone == "resolved":
            updates["resolved_at"] = now.isoformat()
        elif new_milestone == "verified":
            updates["verified_at"] = now.isoformat()

        # Compute new sla_deadline_at
        sla_hours = wo.get("sla_hours", {})
        milestone_hours = sla_hours.get(new_milestone, 24)

        # Get milestone start time
        if new_milestone == "in_progress":
            milestone_start = wo.get("in_progress_at") or wo.get("assigned_at") or now
        elif new_milestone == "resolved":
            milestone_start = wo.get("resolved_at") or wo.get("in_progress_at") or now
        elif new_milestone == "verified":
            milestone_start = wo.get("verified_at") or wo.get("resolved_at") or now
        else:
            milestone_start = wo.get("assigned_at") or now

        if isinstance(milestone_start, str):
            milestone_start = datetime.fromisoformat(milestone_start.replace("Z", "+00:00"))
        if milestone_start.tzinfo is None:
            milestone_start = milestone_start.replace(tzinfo=SAST)

        # Override with per-site SLA config if available
        try:
            site_id = wo.get("site_id")
            sla_repo = get_recommendation_sla_repository()
            sla_term = await sla_repo.get_by_site_milestone(site_id, new_milestone)
            if sla_term:
                milestone_hours = sla_term.deadline_hours
        except Exception:
            pass

        if new_milestone != "verified":
            deadline = milestone_start + timedelta(hours=milestone_hours)
            updates["sla_deadline_at"] = deadline.isoformat()
        else:
            updates["sla_deadline_at"] = None

        logger.info(
            f"Advancing WO {wo.get('code')} milestone to {new_milestone} "
            f"(deadline={updates.get('sla_deadline_at')}, by={by_user})"
        )

        return await self.update_work_order(work_order_id, updates)

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

    async def get_open_work_orders_for_equipment(self, equipment_code: str) -> list[dict[str, Any]]:
        """Get open (non-completed, non-cancelled) work orders for equipment by code.

        Args:
            equipment_code: Equipment code (e.g., "S002-FCU-201")

        Returns:
            List of open work orders for the equipment
        """
        if not self.client:
            return []

        try:
            # Resolve equipment_code → equipment_id (UUID)
            eq_result = (
                self.client.table("equipment")
                .select("id")
                .eq("code", equipment_code)
                .limit(1)
                .execute()
            )
            if not eq_result.data:
                return []
            equipment_id = eq_result.data[0]["id"]

            result = (
                self.client.table("work_orders")
                .select(self._LIST_COLUMNS)
                .eq("equipment_id", equipment_id)
                .in_("status", ["open", "scheduled", "assigned", "in_progress", "pending"])
                .order("created_at", desc=True)
                .limit(10)
                .execute()
            )
            return result.data or []

        except Exception as e:
            logger.error(f"Error getting open work orders for {equipment_code}: {e}")
            return []

    async def get_open_urgent_work_orders(self, site_id: str) -> list[dict[str, Any]]:
        """Get all open urgent/critical work orders for a site.

        Used by AI optimizer to prevent recommending operational adjustments
        on equipment that already has an active fault condition.

        Args:
            site_id: Site code (e.g., "site-002")

        Returns:
            List of open work orders with priority urgent/critical
        """
        if not self.client:
            return []

        try:
            # Resolve site code → UUID (same pattern used throughout the codebase)
            site_resp = self.client.table("sites").select("id").eq("code", site_id).execute()
            if not site_resp.data:
                return []
            site_uuid = site_resp.data[0]["id"]

            result = (
                self.client.table("work_orders")
                .select(self._LIST_COLUMNS)
                .eq("site_id", site_uuid)
                .in_("status", ["open", "scheduled", "assigned", "in_progress", "pending"])
                .in_("priority", ["urgent", "critical"])
                .order("created_at", desc=True)
                .limit(50)
                .execute()
            )
            wos = result.data or []

            # Resolve equipment_id → code via equipment table lookup
            if wos:
                eq_ids = list(set(wo["equipment_id"] for wo in wos if wo.get("equipment_id")))
                if eq_ids:
                    eq_resp = self.client.table("equipment").select("id, code").in_("id", eq_ids).execute()
                    eq_map = {e["id"]: e["code"] for e in (eq_resp.data or [])}
                    for wo in wos:
                        if wo.get("equipment_id") in eq_map:
                            wo["equipment_code"] = eq_map[wo["equipment_id"]]

            return wos

        except Exception as e:
            logger.error(f"Error getting urgent work orders for {site_id}: {e}")
            return []

    async def get_open_for_equipment_action(
        self,
        equipment_code: str,
        action_point: str,
        action_value: str,
    ) -> dict[str, Any] | None:
        """Get open WO for exact equipment + point + value combination.

        Used to prevent duplicate WOs for identical recommendations.
        Only matches open/scheduled/in_progress/pending WOs.
        """
        if not self.client:
            return None

        try:
            # Resolve equipment_code → equipment_id (UUID)
            eq_result = (
                self.client.table("equipment")
                .select("id")
                .eq("code", equipment_code)
                .limit(1)
                .execute()
            )
            if not eq_result.data:
                return None
            equipment_id = eq_result.data[0]["id"]

            result = (
                self.client.table("work_orders")
                .select("id, code, title, status, action_point, action_value, created_at")
                .eq("equipment_id", equipment_id)
                .eq("action_point", action_point)
                .eq("action_value", action_value)
                .in_("status", ["open", "scheduled", "assigned", "in_progress", "pending"])
                .limit(1)
                .execute()
            )
            return result.data[0] if result.data else None

        except Exception as e:
            logger.error(f"Error getting exact WO match for {equipment_code}/{action_point}/{action_value}: {e}")
            return None


# Singleton instance
_repository: WorkOrderRepository | None = None


def get_work_order_repository() -> WorkOrderRepository:
    """Get singleton work order repository."""
    global _repository
    if _repository is None:
        _repository = WorkOrderRepository()
    return _repository
