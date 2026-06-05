"""Preference repository — Supabase-backed CRUD for user_preferences table."""

import logging
from datetime import UTC, datetime

from app.database.supabase_client import get_supabase_client
from app.models.preference import PreferenceType, UserPreference

logger = logging.getLogger(__name__)

_PREFERENCE_TABLE = "user_preferences"


class PreferenceRepository:
    """Supabase repository for FM preference storage and retrieval."""

    async def insert_preference(self, pref: UserPreference) -> UserPreference:
        """Insert or update a preference (upserts on site_id+user_id+preference_type)."""
        client = get_supabase_client()
        data = pref.model_dump(exclude={"id"}, exclude_none=True)
        if "created_at" not in data or data.get("created_at") is None:
            data["created_at"] = datetime.now(tz=UTC).isoformat()

        # Upsert: on conflict (site_id, user_id, preference_type) update the row
        result = client.table(_PREFERENCE_TABLE).upsert(data, on_conflict="site_id, user_id, preference_type").execute()
        if result.data:
            return UserPreference(**result.data[0])
        raise RuntimeError("Failed to insert preference")

    async def fetch_active_by_user(self, site_id: str, user_id: str) -> list[UserPreference]:
        """Fetch all preferences for a user at a site, ordered newest first."""
        client = get_supabase_client()
        result = (
            client.table(_PREFERENCE_TABLE)
            .select("*")
            .eq("site_id", site_id)
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )
        return [UserPreference(**row) for row in (result.data or [])]

    async def fetch_by_type(self, site_id: str, user_id: str, preference_type: PreferenceType) -> UserPreference | None:
        """Fetch a single preference by type for a user."""
        client = get_supabase_client()
        result = (
            client.table(_PREFERENCE_TABLE)
            .select("*")
            .eq("site_id", site_id)
            .eq("user_id", user_id)
            .eq("preference_type", preference_type.value)
            .limit(1)
            .execute()
        )
        if result.data:
            return UserPreference(**result.data[0])
        return None

    async def mark_stale(self, site_id: str, user_id: str, days_old: int = 180) -> int:
        """Mark preferences older than N days (for future Stage 04 consolidation).

        Returns count of marked rows.
        """
        client = get_supabase_client()
        cutoff = datetime.now(tz=UTC).isoformat()
        # Soft-delete: set confidence to 0 to indicate stale
        result = (
            client.table(_PREFERENCE_TABLE)
            .update({"confidence": 0.0})
            .eq("site_id", site_id)
            .eq("user_id", user_id)
            .lt("created_at", cutoff)
            .execute()
        )
        return len(result.data or [])


preference_repo = PreferenceRepository()
