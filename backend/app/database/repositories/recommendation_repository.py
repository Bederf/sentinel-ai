"""Repository for recommendation tracking operations."""

import logging
from typing import Any

from app.database.repositories.base import SupabaseRepository
from app.models.recommendation import Recommendation, RecommendationStatus
from app.services.cache_service import cache

logger = logging.getLogger(__name__)


class RecommendationRepository(SupabaseRepository):
    """Repository for recommendation database operations."""

    _COLUMNS = (
        "id, site_id, timestamp, action_type, risk_level, target_equipment, "
        "action, reason, expected_impact, confidence, confidence_score, profile, "
        "multi_objective_score, status, requires_approval, approval_status, "
        "approved_by, approved_at, approval_reason, executed_at, execution_result, "
        "rejection_reason, source, source_type, point_resolution"
    )
    _WRITE_COLUMNS = {
        "id",
        "site_id",
        "timestamp",
        "action_type",
        "risk_level",
        "target_equipment",
        "action",
        "reason",
        "expected_impact",
        "confidence",
        "confidence_score",
        "profile",
        "multi_objective_score",
        "status",
        "requires_approval",
        "approval_status",
        "approved_by",
        "approved_at",
        "approval_reason",
        "executed_at",
        "execution_result",
        "rejection_reason",
        "shadow_mode",
        "source",
        "source_type",
        "point_resolution",
    }

    def _filter_supabase_payload(self, rec_dict: dict[str, Any]) -> dict[str, Any]:
        """Drop model-only keys that do not exist in the live recommendations table."""
        return {key: value for key, value in rec_dict.items() if key in self._WRITE_COLUMNS}

    async def create(self, rec: Recommendation) -> Recommendation:
        """Create new recommendation in the canonical DB store."""
        rec_dict = rec.to_dict()
        result = await self._supabase_insert(rec_dict)
        if result:
            return Recommendation.from_dict(result)
        logger.error("Error creating recommendation %s: canonical DB write failed", rec.id)
        raise RuntimeError("Failed to persist recommendation to canonical DB store")

    async def get(self, rec_id: str) -> Recommendation | None:
        """Get recommendation by ID."""
        rec_dict = await self._supabase_get(rec_id)
        return Recommendation.from_dict(rec_dict) if rec_dict else None

    async def get_by_id(self, rec_id: str) -> Recommendation | None:
        """Alias for get() for consistency with other repositories."""
        return await self.get(rec_id)

    async def get_by_status(
        self,
        site_id: str,
        status: RecommendationStatus,
        limit: int = 10,
    ) -> list[Recommendation]:
        """Get recommendations with status, newest first."""
        recs = await self._supabase_get_by_status(site_id, status, limit)
        return [Recommendation.from_dict(rec) for rec in recs]

    async def get_history(
        self,
        site_id: str,
        status_filter: str | None = None,
        risk_level_filter: str | None = None,
        limit: int = 50,
    ) -> list[Recommendation]:
        """Get historical recommendations for a site with optional filters."""
        recs = await self._supabase_get_history(site_id, status_filter, risk_level_filter, limit)
        return [Recommendation.from_dict(rec) for rec in recs]

    async def update(self, rec_id: str, rec: Recommendation) -> Recommendation:
        """Update recommendation."""
        rec_dict = rec.to_dict()
        result = await self._supabase_update(rec_id, rec_dict)
        if result:
            return Recommendation.from_dict(result)
        logger.error("Error updating recommendation %s: canonical DB write failed", rec_id)
        raise RuntimeError("Failed to update recommendation in canonical DB store")

    async def upsert(self, rec: Recommendation) -> Recommendation:
        """Insert or update recommendation (upsert)."""
        existing = await self.get(rec.id)
        if existing:
            return await self.update(rec.id, rec)
        return await self.create(rec)

    async def resolve_id_prefix(self, token: str) -> str:
        """Resolve a full recommendation ID from either a full ID or short prefix."""
        if not token:
            return ""

        exact = await self.get(token)
        if exact:
            return token

        client = await self.get_client()
        if not client:
            return ""

        try:
            result = await (
                client.table("recommendations")
                .select("id,timestamp")
                .order("timestamp", desc=True)
                .limit(1000)
                .execute()
            )
            matches = [row["id"] for row in (result.data or []) if str(row.get("id", "")).startswith(token)]
            if len(matches) == 1:
                return matches[0]
        except Exception as e:
            logger.error("Recommendation prefix resolution failed: %s", e)

        return ""

    async def _supabase_insert(self, rec_dict: dict[str, Any]) -> dict[str, Any] | None:
        """Insert recommendation to Supabase."""
        client = await self.get_client()
        if not client:
            return None
        try:
            payload = self._filter_supabase_payload(rec_dict)
            result = await client.table("recommendations").insert(payload).execute()
            if result.data and len(result.data) > 0:
                cache.delete_pattern("recommendations:*")
                return result.data[0]
            return None
        except Exception as e:
            logger.error("Supabase insert failed: %s", e)
            return None

    async def _supabase_get(self, rec_id: str) -> dict[str, Any] | None:
        """Get recommendation from Supabase."""
        client = await self.get_client()
        if not client:
            return None
        try:
            result = await client.table("recommendations").select(self._COLUMNS).eq("id", rec_id).execute()
            if result.data and len(result.data) > 0:
                return result.data[0]
            return None
        except Exception as e:
            logger.error("Supabase get failed: %s", e)
            return None

    async def _supabase_get_by_status(
        self,
        site_id: str,
        status: RecommendationStatus,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Query recommendations from Supabase by status."""
        client = await self.get_client()
        if not client:
            return []
        try:
            result = await (
                client.table("recommendations")
                .select("*")
                .eq("site_id", site_id)
                .eq("status", status.value)
                .eq("action_type", "ai_optimization")
                .eq("shadow_mode", False)
                .order("risk_level", desc=True)
                .order("timestamp", desc=True)
                .limit(limit)
                .execute()
            )
            return result.data or []
        except Exception as e:
            logger.error("Supabase query failed: %s", e)
            return []

    async def expire_superseded_setpoints(self, site_id: str, target_equipment: str, point_name: str) -> int:
        """Expire all pending setpoint recs for equipment+point, superseded by a new one.

        Called before creating a new ai_optimization rec so stale Telegram advisories
        can't be approved after the value has already been updated.
        """
        client = await self.get_client()
        if not client:
            return 0
        try:
            result = await (
                client.table("recommendations")
                .update({"status": "expired"})
                .eq("site_id", site_id)
                .eq("target_equipment", target_equipment)
                .eq("status", "pending")
                .filter("action->>point", "eq", point_name)
                .execute()
            )
            count = len(result.data or [])
            if count:
                cache.delete_pattern("recommendations:*")
                logger.info(
                    "[REC-SUPERSEDE] Expired %d stale pending recs for %s/%s",
                    count,
                    target_equipment,
                    point_name,
                )
            return count
        except Exception as e:
            logger.warning("expire_superseded_setpoints failed for %s/%s: %s", target_equipment, point_name, e)
            return 0

    async def _supabase_update(self, rec_id: str, rec_dict: dict[str, Any]) -> dict[str, Any] | None:
        """Update recommendation in Supabase."""
        client = await self.get_client()
        if not client:
            return None
        try:
            payload = self._filter_supabase_payload(rec_dict)
            result = await client.table("recommendations").update(payload).eq("id", rec_id).execute()
            if result.data and len(result.data) > 0:
                cache.delete_pattern("recommendations:*")
                return result.data[0]
            return None
        except Exception as e:
            logger.error("Supabase update failed: %s", e)
            return None

    async def _supabase_get_history(
        self,
        site_id: str,
        status_filter: str | None,
        risk_level_filter: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Query historical recommendations from Supabase with filters."""
        client = await self.get_client()
        if not client:
            return []
        try:
            query = (
                client.table("recommendations")
                .select("*")
                .eq("site_id", site_id)
                .eq("action_type", "ai_optimization")
                .neq("status", "pending")
                .eq("shadow_mode", False)
                .order("timestamp", desc=True)
                .limit(limit)
            )
            if status_filter:
                query = query.eq("status", status_filter)
            if risk_level_filter:
                query = query.eq("risk_level", risk_level_filter)
            result = await query.execute()
            return result.data or []
        except Exception as e:
            logger.error("Supabase history query failed: %s", e)
            return []


_repository: RecommendationRepository | None = None


def get_recommendation_repository() -> RecommendationRepository:
    """Get or create RecommendationRepository singleton."""
    global _repository
    if _repository is None:
        _repository = RecommendationRepository()
    return _repository
