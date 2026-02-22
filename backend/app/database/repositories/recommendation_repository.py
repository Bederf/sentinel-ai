"""Repository for recommendation tracking operations.

Implements Supabase + JSON fallback pattern for storing and retrieving recommendations
through the approval and execution workflow.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config.settings import settings
from app.models.recommendation import Recommendation, RecommendationStatus

logger = logging.getLogger(__name__)

# Data directory for JSON fallback
DATA_DIR = Path(__file__).parent.parent.parent / "data"


class RecommendationRepository:
    """Repository for recommendation database operations.

    Manages recommendations with Supabase as primary storage and JSON files as fallback.
    Supports querying by status and site_id.
    """

    def __init__(self):
        """Initialize the repository."""
        self._client = None
        self._use_json = settings.use_json_storage
        self._recommendations: Dict[str, Dict[str, Any]] = {}

    @property
    def client(self):
        """Lazy load Supabase client."""
        if self._client is None and not self._use_json:
            try:
                from app.database.supabase_client import get_supabase_client

                self._client = get_supabase_client()
            except Exception as e:
                logger.warning(f"Failed to get Supabase client, using JSON fallback: {e}")
                self._use_json = True
        return self._client

    async def create(self, rec: Recommendation) -> Recommendation:
        """Create new recommendation.

        Args:
            rec: Recommendation to create

        Returns:
            Created recommendation

        Raises:
            Exception: If creation fails
        """
        try:
            rec_dict = rec.to_dict()

            if not self._use_json and self.client:
                # Save to Supabase
                result = await self._supabase_insert(rec_dict)
                if result:
                    return Recommendation.from_dict(result)

            # Fall back to JSON
            self._load_all()
            self._recommendations[rec.id] = rec_dict
            self._save_all()
            return rec

        except Exception as e:
            logger.error(f"Error creating recommendation {rec.id}: {e}")
            raise

    async def get(self, rec_id: str) -> Optional[Recommendation]:
        """Get recommendation by ID.

        Args:
            rec_id: Recommendation ID

        Returns:
            Recommendation or None if not found
        """
        try:
            if not self._use_json and self.client:
                # Query Supabase
                rec_dict = await self._supabase_get(rec_id)
                if rec_dict:
                    return Recommendation.from_dict(rec_dict)

            # Fall back to JSON
            self._load_all()
            if rec_id in self._recommendations:
                return Recommendation.from_dict(self._recommendations[rec_id])
            return None

        except Exception as e:
            logger.error(f"Error fetching recommendation {rec_id}: {e}")
            return None

    async def get_by_id(self, rec_id: str) -> Optional[Recommendation]:
        """Alias for get() for consistency with other repositories."""
        return await self.get(rec_id)

    async def get_by_status(
        self,
        site_id: str,
        status: RecommendationStatus,
        limit: int = 10,
    ) -> List[Recommendation]:
        """Get recommendations with status, newest first.

        Args:
            site_id: Building identifier
            status: Recommendation status
            limit: Maximum number to return

        Returns:
            List of recommendations matching status
        """
        try:
            if not self._use_json and self.client:
                # Query Supabase, fall through to JSON if empty/failed
                recs = await self._supabase_get_by_status(site_id, status, limit)
                if recs:
                    return [Recommendation.from_dict(rec) for rec in recs]

            # Fall back to JSON
            self._load_all()
            matching = [
                rec
                for rec in self._recommendations.values()
                if rec.get("site_id") == site_id and rec.get("status") == status.value
            ]
            # Sort by timestamp DESC (newest first)
            matching.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
            return [Recommendation.from_dict(rec) for rec in matching[:limit]]

        except Exception as e:
            logger.error(f"Error querying recommendations by status: {e}")
            return []

    async def get_history(
        self,
        site_id: str,
        status_filter: Optional[str] = None,
        risk_level_filter: Optional[str] = None,
        limit: int = 50,
    ) -> List[Recommendation]:
        """Get historical recommendations for a site with optional filters.

        Returns all non-pending recommendations (executed, rejected, auto_executed, failed).

        Args:
            site_id: Building identifier
            status_filter: Optional status to filter by (executed, rejected, auto_executed, failed)
            risk_level_filter: Optional risk level to filter by (low, medium, high, critical)
            limit: Maximum number to return (default 50)

        Returns:
            List of historical recommendations matching filters, newest first
        """
        try:
            if not self._use_json and self.client:
                # Query Supabase
                recs = await self._supabase_get_history(site_id, status_filter, risk_level_filter, limit)
                return [Recommendation.from_dict(rec) for rec in recs]

            # Fall back to JSON
            self._load_all()
            matching = [
                rec
                for rec in self._recommendations.values()
                if rec.get("site_id") == site_id
                # Exclude pending recommendations from history
                and rec.get("status") != "pending"
            ]

            # Apply status filter if provided
            if status_filter:
                matching = [rec for rec in matching if rec.get("status") == status_filter]

            # Apply risk level filter if provided
            if risk_level_filter:
                matching = [rec for rec in matching if rec.get("risk_level") == risk_level_filter]

            # Sort by timestamp DESC (newest first)
            matching.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
            return [Recommendation.from_dict(rec) for rec in matching[:limit]]

        except Exception as e:
            logger.error(f"Error querying recommendation history: {e}")
            return []

    async def update(self, rec_id: str, rec: Recommendation) -> Recommendation:
        """Update recommendation.

        Args:
            rec_id: Recommendation ID
            rec: Updated recommendation

        Returns:
            Updated recommendation

        Raises:
            Exception: If update fails
        """
        try:
            rec_dict = rec.to_dict()

            if not self._use_json and self.client:
                # Update in Supabase
                result = await self._supabase_update(rec_id, rec_dict)
                if result:
                    return Recommendation.from_dict(result)

            # Fall back to JSON
            self._load_all()
            self._recommendations[rec_id] = rec_dict
            self._save_all()
            return rec

        except Exception as e:
            logger.error(f"Error updating recommendation {rec_id}: {e}")
            raise

    async def upsert(self, rec: Recommendation) -> Recommendation:
        """Insert or update recommendation (upsert).

        If recommendation with given ID exists, updates it.
        Otherwise, creates a new one.

        Args:
            rec: Recommendation to insert/update

        Returns:
            The inserted/updated recommendation

        Raises:
            Exception: If operation fails
        """
        try:
            # Check if exists
            existing = await self.get(rec.id)

            if existing:
                # Update existing
                return await self.update(rec.id, rec)
            else:
                # Create new
                return await self.create(rec)

        except Exception as e:
            logger.error(f"Error in upsert for recommendation {rec.id}: {e}")
            raise

    # Tridonic DALI-2 handles these natively — filter out AI duplicates
    _TRIDONIC_NATIVE_PHRASES = frozenset(
        [
            "supplement lighting",
            "Tridonic harvesting",
            "increase artificial lighting",
            "full artificial lighting",
            "security lighting only",
            "Daylight harvesting - avg lux",
            "Zone unoccupied",
        ]
    )

    def _is_tridonic_native(self, rec: dict) -> bool:
        """Return True if this recommendation duplicates Tridonic native behaviour."""
        reason = rec.get("reason", "")
        action = rec.get("action", {})
        point = action.get("point", "") if isinstance(action, dict) else ""
        return point == "brightness_level" or any(phrase in reason for phrase in self._TRIDONIC_NATIVE_PHRASES)

    def _load_all(self) -> None:
        """Load all recommendations from JSON (fallback)."""
        filepath = DATA_DIR / "recommendations.json"
        if filepath.exists():
            try:
                with open(filepath) as f:
                    data = json.load(f)
                    raw = data.get("recommendations", {})
                    # Filter out DALI brightness recs — Tridonic handles natively
                    self._recommendations = {k: v for k, v in raw.items() if not self._is_tridonic_native(v)}
            except Exception as e:
                logger.error(f"Error loading recommendations.json: {e}")
                self._recommendations = {}
        else:
            self._recommendations = {}

    def _save_all(self) -> None:
        """Save all recommendations to JSON (fallback)."""
        filepath = DATA_DIR / "recommendations.json"
        try:
            filepath.parent.mkdir(parents=True, exist_ok=True)
            with open(filepath, "w") as f:
                json.dump({"recommendations": self._recommendations}, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving recommendations.json: {e}")

    async def _supabase_insert(self, rec_dict: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Insert recommendation to Supabase."""
        if not self.client:
            return None

        try:
            result = self.client.table("recommendations").insert(rec_dict).execute()
            if result.data and len(result.data) > 0:
                return result.data[0]
            return None
        except Exception as e:
            logger.error(f"Supabase insert failed: {e}")
            return None

    async def _supabase_get(self, rec_id: str) -> Optional[Dict[str, Any]]:
        """Get recommendation from Supabase."""
        if not self.client:
            return None

        try:
            result = self.client.table("recommendations").select("*").eq("id", rec_id).execute()
            if result.data and len(result.data) > 0:
                return result.data[0]
            return None
        except Exception as e:
            logger.error(f"Supabase get failed: {e}")
            return None

    async def _supabase_get_by_status(
        self,
        site_id: str,
        status: RecommendationStatus,
        limit: int,
    ) -> List[Dict[str, Any]]:
        """Query recommendations from Supabase by status."""
        if not self.client:
            return []

        try:
            result = (
                self.client.table("recommendations")
                .select("*")
                .eq("site_id", site_id)
                .eq("status", status.value)
                .order("timestamp", desc=True)
                .limit(limit)
                .execute()
            )
            return result.data or []
        except Exception as e:
            logger.error(f"Supabase query failed: {e}")
            return []

    async def _supabase_update(self, rec_id: str, rec_dict: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update recommendation in Supabase."""
        if not self.client:
            return None

        try:
            result = self.client.table("recommendations").update(rec_dict).eq("id", rec_id).execute()
            if result.data and len(result.data) > 0:
                return result.data[0]
            return None
        except Exception as e:
            logger.error(f"Supabase update failed: {e}")
            return None

    async def _supabase_get_history(
        self,
        site_id: str,
        status_filter: Optional[str],
        risk_level_filter: Optional[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        """Query historical recommendations from Supabase with filters.

        Args:
            site_id: Building identifier
            status_filter: Optional status filter
            risk_level_filter: Optional risk level filter
            limit: Maximum number to return

        Returns:
            List of recommendation dicts matching filters
        """
        if not self.client:
            return []

        try:
            query = (
                self.client.table("recommendations")
                .select("*")
                .eq("site_id", site_id)
                .neq("status", "pending")  # Exclude pending from history
                .order("timestamp", desc=True)
                .limit(limit)
            )

            # Apply optional filters
            if status_filter:
                query = query.eq("status", status_filter)
            if risk_level_filter:
                query = query.eq("risk_level", risk_level_filter)

            result = query.execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Supabase history query failed: {e}")
            return []


# Singleton instance
_repository: Optional[RecommendationRepository] = None


def get_recommendation_repository() -> RecommendationRepository:
    """Get or create RecommendationRepository singleton.

    Returns:
        RecommendationRepository instance
    """
    global _repository
    if _repository is None:
        _repository = RecommendationRepository()
    return _repository
