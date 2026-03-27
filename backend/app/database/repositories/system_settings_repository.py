"""Repository for canonical runtime system settings stored in Supabase."""

from __future__ import annotations

import copy
import logging
from typing import Any

from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class SystemSettingsRepository:
    """Repository for global runtime settings in `system_settings`."""

    def __init__(self) -> None:
        self.client = get_supabase_client()

    def get_value(self, key: str, default: Any = None) -> Any:
        """Return a setting value or the provided default if missing/unavailable."""
        try:
            result = self.client.table("system_settings").select("value").eq("key", key).limit(1).execute()
            if result.data:
                return result.data[0].get("value")
        except Exception as exc:
            logger.warning("Failed to load system setting %s: %s", key, exc)
        return copy.deepcopy(default)

    def get_values(self, keys: list[str]) -> dict[str, Any]:
        """Return a mapping of key -> value for the provided setting keys."""
        try:
            result = self.client.table("system_settings").select("key,value").in_("key", keys).execute()
            return {row["key"]: row.get("value") for row in (result.data or [])}
        except Exception as exc:
            logger.warning("Failed to load system settings %s: %s", keys, exc)
            return {}

    def upsert_value(
        self,
        *,
        key: str,
        value: Any,
        category: str,
        description: str,
        data_type: str,
        is_public: bool = False,
        is_editable: bool = True,
        updated_by: str | None = None,
    ) -> Any:
        """Create or update a system setting and return the stored value."""
        payload = {
            "key": key,
            "value": value,
            "category": category,
            "description": description,
            "data_type": data_type,
            "is_public": is_public,
            "is_editable": is_editable,
            "updated_by": updated_by,
        }
        result = self.client.table("system_settings").upsert(payload, on_conflict="key").execute()
        if result.data:
            return result.data[0].get("value", value)
        return value
