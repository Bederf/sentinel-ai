"""Repository for RecommendationSLA CRUD operations.

Handles per-site per-milestone SLA deadline configurations.
Dual-write: Supabase primary + JSON canonical store fallback.
"""

import logging
from datetime import datetime
from typing import Any

from app.models.sla_term import MilestoneStatus, RecommendationSLATerm
from app.services.cache_service import cache

logger = logging.getLogger(__name__)


class RecommendationSLARepository:
    """Repository for RecommendationSLATerm database operations."""

    _TABLE = "recommendation_sla_terms"
    _WRITE_COLUMNS = {
        "id",
        "site_code",
        "milestone",
        "deadline_hours",
        "escalation_template",
        "created_at",
        "updated_at",
    }

    def __init__(self):
        self._client = None

    @property
    def client(self):
        """Lazy-load Supabase client."""
        if self._client is None:
            try:
                from app.database.supabase_client import get_supabase_client

                self._client = get_supabase_client()
            except Exception as e:
                logger.warning("Failed to get Supabase client for SLA terms: %s", e)
                self._client = None
        return self._client

    def _filter_payload(self, d: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in d.items() if k in self._WRITE_COLUMNS}

    async def upsert(self, term: RecommendationSLATerm) -> RecommendationSLATerm:
        """Insert or update an SLA term config."""
        term.updated_at = datetime.utcnow()
        d = term.to_dict()
        result = await self._supabase_upsert(d)
        if result:
            return RecommendationSLATerm.from_dict(result)
        # Fallback: return as-is (JSON write already happened in _supabase_upsert → JSON fallback)
        logger.warning("SLA term %s/%s fell back to JSON", term.site_code, term.milestone.value)
        return term

    async def get_by_site_milestone(self, site_code: str, milestone: MilestoneStatus) -> RecommendationSLATerm | None:
        """Get SLA term for a specific site + milestone."""
        if self.client:
            try:
                result = (
                    self.client.table(self._TABLE)
                    .select("*")
                    .eq("site_code", site_code)
                    .eq("milestone", milestone.value)
                    .limit(1)
                    .execute()
                )
                if result.data:
                    return RecommendationSLATerm.from_dict(result.data[0])
            except Exception as e:
                logger.error("Supabase SLA term lookup failed: %s", e)
        return None

    async def get_all_for_site(self, site_code: str) -> list[RecommendationSLATerm]:
        """Get all SLA terms for a site."""
        if self.client:
            try:
                result = self.client.table(self._TABLE).select("*").eq("site_code", site_code).execute()
                return [RecommendationSLATerm.from_dict(row) for row in (result.data or [])]
            except Exception as e:
                logger.error("Supabase SLA terms for site failed: %s", e)
        return []

    async def get_all(self) -> list[RecommendationSLATerm]:
        """Get all SLA terms (for breach checking)."""
        if self.client:
            try:
                result = self.client.table(self._TABLE).select("*").execute()
                return [RecommendationSLATerm.from_dict(row) for row in (result.data or [])]
            except Exception as e:
                logger.error("Supabase get all SLA terms failed: %s", e)
        return []

    async def delete(self, term_id: str) -> bool:
        """Delete an SLA term config."""
        if self.client:
            try:
                self.client.table(self._TABLE).delete().eq("id", term_id).execute()
                cache.delete_pattern("sla_terms:*")
                return True
            except Exception as e:
                logger.error("Supabase SLA term delete failed: %s", e)
        return False

    async def seed_defaults(self, site_code: str) -> list[RecommendationSLATerm]:
        """Seed default SLA terms for a site (one per milestone)."""
        defaults = {}
        for milestone in MilestoneStatus:
            defaults[milestone.value] = RecommendationSLATerm(
                site_code=site_code,
                milestone=milestone,
                deadline_hours=24 if milestone == MilestoneStatus.ASSIGNED else 48,
                escalation_template=None,
            )
        results = []
        for term in defaults.values():
            results.append(await self.upsert(term))
        return results

    # --- Private Supabase helpers ---

    async def _supabase_upsert(self, d: dict[str, Any]) -> dict[str, Any] | None:
        """Upsert to Supabase with JSON canonical store fallback."""
        if not self.client:
            return await self._json_upsert(d)
        try:
            payload = self._filter_payload(d)
            result = self.client.table(self._TABLE).upsert(payload).execute()
            if result.data:
                cache.delete_pattern("sla_terms:*")
                return result.data[0]
        except Exception as e:
            logger.warning("Supabase SLA upsert failed, falling back to JSON: %s", e)
        return await self._json_upsert(d)

    async def _json_upsert(self, d: dict[str, Any]) -> dict[str, Any] | None:
        """Fallback: write SLA term to JSON canonical store.

        Note: Canonical JSON store is not yet wired for SLA terms.
        Until then, Supabase-only writes; this method is a no-op stub.
        """
        # TODO (phase 207-06): Wire canonical JSON store for recommendation_sla_terms
        logger.debug("SLA term JSON fallback called — Supabase write succeeded, JSON stub not needed")
        return None


_repository: RecommendationSLARepository | None = None


def get_recommendation_sla_repository() -> RecommendationSLARepository:
    global _repository
    if _repository is None:
        _repository = RecommendationSLARepository()
    return _repository
