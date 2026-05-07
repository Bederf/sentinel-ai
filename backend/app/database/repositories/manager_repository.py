"""
Manager Repository - Database operations for site managers.
"""

import logging
from typing import Any

from ..supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class ManagerRepository:
    """Repository for manager operations."""

    def __init__(self):
        self.client = get_supabase_client()

    async def get_managers(self, site_id: str | None = None, active_only: bool = True) -> list[dict[str, Any]]:
        """Get all managers, optionally filtered by site."""
        if not self.client:
            logger.warning("Supabase client not available")
            return []

        try:
            query = self.client.table("managers").select("*")
            if active_only:
                query = query.eq("active", True)
            if site_id:
                query = query.eq("site_id", site_id)
            result = query.execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Error fetching managers: {e}")
            return []

    async def get_manager_by_id(self, manager_id: str) -> dict[str, Any] | None:
        """Get a single manager by ID."""
        if not self.client:
            return None
        try:
            result = self.client.table("managers").select("*").eq("id", manager_id).limit(1).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Error fetching manager {manager_id}: {e}")
            return None

    async def get_manager_by_telegram_id(self, telegram_id: str) -> dict[str, Any] | None:
        """Get the manager with this Telegram ID (for alert routing)."""
        if not self.client:
            return None
        try:
            result = (
                self.client.table("managers")
                .select("*")
                .eq("telegram_id", telegram_id)
                .eq("active", True)
                .limit(1)
                .execute()
            )
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Error fetching manager by telegram_id {telegram_id}: {e}")
            return None

    async def create_manager(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new manager record."""
        if not self.client:
            raise RuntimeError("Supabase client not available")

        required = ["name", "email"]
        for field in required:
            if not data.get(field):
                raise ValueError(f"Missing required field: {field}")

        result = self.client.table("managers").insert(data).execute()
        if not result.data:
            raise RuntimeError("Failed to insert manager")
        return result.data[0]

    async def update_manager(self, manager_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
        """Update an existing manager."""
        if not self.client:
            return None
        try:
            # Only include non-None values
            update_data = {k: v for k, v in data.items() if v is not None}
            if not update_data:
                return await self.get_manager_by_id(manager_id)

            result = self.client.table("managers").update(update_data).eq("id", manager_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Error updating manager {manager_id}: {e}")
            return None

    async def deactivate_manager(self, manager_id: str) -> bool:
        """Soft-delete a manager by setting active=False."""
        if not self.client:
            return False
        try:
            result = self.client.table("managers").update({"active": False}).eq("id", manager_id).execute()
            return bool(result.data)
        except Exception as e:
            logger.error(f"Error deactivating manager {manager_id}: {e}")
            return False


_manager_repo: ManagerRepository | None = None


def get_manager_repository() -> ManagerRepository:
    global _manager_repo
    if _manager_repo is None:
        _manager_repo = ManagerRepository()
    return _manager_repo
