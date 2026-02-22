"""Repository for rejection record tracking operations.

Implements Supabase + JSON fallback pattern for storing and retrieving rejection records
for rejection pattern analysis.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta

from app.config.settings import settings

logger = logging.getLogger(__name__)

# Data directory for JSON fallback
DATA_DIR = Path(__file__).parent.parent.parent / "data"


class RejectionRepository:
    """Repository for rejection record database operations.

    Manages rejection records with Supabase as primary storage and JSON files as fallback.
    Supports querying by site_id, action_type, and time range for pattern detection.
    """

    def __init__(self):
        """Initialize the repository."""
        self._client = None
        self._use_json = settings.use_json_storage
        self._rejections: Dict[str, Dict[str, Any]] = {}
        self._load_json_data()

    def _load_json_data(self) -> None:
        """Load rejections from JSON file for fallback storage."""
        try:
            rejection_file = DATA_DIR / "rejections.json"
            if rejection_file.exists():
                with open(rejection_file, "r") as f:
                    data = json.load(f)
                    self._rejections = data.get("rejections", {})
                    logger.info(f"Loaded {len(self._rejections)} rejections from JSON")
            else:
                logger.info("No existing rejections.json file found")
        except Exception as e:
            logger.warning(f"Error loading rejections from JSON: {e}")
            self._rejections = {}

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

    async def create(self, rejection) -> None:
        """Create new rejection record.

        Args:
            rejection: RejectionRecord object to store

        Raises:
            Exception: If storage fails
        """
        try:
            if self._use_json or not self.client:
                self._create_json(rejection)
            else:
                await self._create_supabase(rejection)
        except Exception as e:
            logger.error(f"Error creating rejection record: {e}")
            # Fall back to JSON
            self._create_json(rejection)

    def _create_json(self, rejection) -> None:
        """Store rejection in JSON."""
        try:
            self._rejections[rejection.recommendation_id] = rejection.to_dict()
            self._save_json()
            logger.debug(f"Stored rejection in JSON for {rejection.recommendation_id}")
        except Exception as e:
            logger.error(f"Error storing rejection in JSON: {e}")
            raise

    async def _create_supabase(self, rejection) -> None:
        """Store rejection in Supabase."""
        try:
            self.client.table("rejections").insert(rejection.to_dict()).execute()
            logger.debug(f"Stored rejection in Supabase for {rejection.recommendation_id}")
        except Exception as e:
            logger.error(f"Error storing rejection in Supabase: {e}")
            raise

    async def get_recent(self, site_id: str, action_type: str, days: int = 30) -> List:
        """Get recent rejections for pattern detection.

        Args:
            site_id: Site ID
            action_type: Action type to filter
            days: Look back window (default 30 days)

        Returns:
            List of RejectionRecord objects matching criteria
        """
        try:
            if self._use_json or not self.client:
                return self._get_recent_json(site_id, action_type, days)
            else:
                return await self._get_recent_supabase(site_id, action_type, days)
        except Exception as e:
            logger.error(f"Error retrieving recent rejections: {e}")
            return []

    def _get_recent_json(self, site_id: str, action_type: str, days: int = 30) -> List:
        """Get recent rejections from JSON."""
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            results = []

            for rec_id, data in self._rejections.items():
                if data.get("site_id") == site_id and data.get("action_type") == action_type:
                    # Parse timestamp
                    rejected_at = data.get("rejected_at")
                    if isinstance(rejected_at, str):
                        try:
                            rejected_at = datetime.fromisoformat(rejected_at)
                        except (ValueError, TypeError):
                            rejected_at = datetime.utcnow()

                    if rejected_at >= cutoff_date:
                        # Import here to avoid circular dependency
                        from app.services.rejection_learning_service import (
                            RejectionRecord,
                        )

                        results.append(RejectionRecord.from_dict(data))

            return results

        except Exception as e:
            logger.error(f"Error retrieving recent rejections from JSON: {e}")
            return []

    async def _get_recent_supabase(self, site_id: str, action_type: str, days: int = 30) -> List:
        """Get recent rejections from Supabase."""
        try:
            cutoff_date = (datetime.utcnow() - timedelta(days=days)).isoformat()

            result = (
                self.client.table("rejections")
                .select("*")
                .eq("site_id", site_id)
                .eq("action_type", action_type)
                .gte("rejected_at", cutoff_date)
                .execute()
            )

            if result.data:
                from app.services.rejection_learning_service import (
                    RejectionRecord,
                )

                return [RejectionRecord.from_dict(r) for r in result.data]

            return []

        except Exception as e:
            logger.error(f"Error retrieving recent rejections from Supabase: {e}")
            return []

    def _save_json(self) -> None:
        """Persist rejections to JSON file."""
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            rejection_file = DATA_DIR / "rejections.json"

            with open(rejection_file, "w") as f:
                json.dump({"rejections": self._rejections}, f, indent=2)

            logger.debug("Rejections saved to JSON")
        except Exception as e:
            logger.error(f"Error saving rejections to JSON: {e}")


# Singleton instance
_rejection_repo: Optional[RejectionRepository] = None


def get_rejection_repository() -> RejectionRepository:
    """Get or create RejectionRepository singleton.

    Returns:
        RejectionRepository instance
    """
    global _rejection_repo
    if _rejection_repo is None:
        _rejection_repo = RejectionRepository()
    return _rejection_repo
