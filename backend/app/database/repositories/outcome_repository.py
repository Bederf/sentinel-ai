"""Repository for outcome tracking operations.

Implements Supabase + JSON fallback pattern for storing and retrieving outcomes
for recommendation verification.
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.config.settings import settings
from app.models.outcome import Outcome

logger = logging.getLogger(__name__)

# Data directory for JSON fallback
DATA_DIR = Path(__file__).parent.parent.parent / "data"


class OutcomeRepository:
    """Repository for outcome tracking database operations.

    Manages outcomes with Supabase as primary storage and JSON files as fallback.
    Supports querying by recommendation ID and action type.
    """

    def __init__(self):
        """Initialize the repository."""
        self._client = None
        self._use_json = settings.use_json_storage
        self._outcomes: dict[str, dict[str, Any]] = {}
        self._load_json_data()

    def _load_json_data(self) -> None:
        """Load outcomes from JSON file for fallback storage."""
        try:
            outcome_file = DATA_DIR / "outcomes.json"
            if outcome_file.exists():
                with open(outcome_file) as f:
                    data = json.load(f)
                    self._outcomes = data.get("outcomes", {})
                    logger.info(f"Loaded {len(self._outcomes)} outcomes from JSON")
            else:
                logger.info("No existing outcomes.json file found")
        except Exception as e:
            logger.warning(f"Error loading outcomes from JSON: {e}")
            self._outcomes = {}

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

    async def create(self, outcome: Outcome) -> Outcome:
        """Create new outcome record.

        Args:
            outcome: Outcome object to store

        Returns:
            Created Outcome

        Raises:
            Exception: If storage fails
        """
        try:
            if self._use_json or not self.client:
                return self._create_json(outcome)
            else:
                return await self._create_supabase(outcome)
        except Exception as e:
            logger.error(f"Error creating outcome: {e}")
            # Fall back to JSON
            return self._create_json(outcome)

    def _create_json(self, outcome: Outcome) -> Outcome:
        """Store outcome in JSON."""
        try:
            self._outcomes[outcome.recommendation_id] = outcome.to_dict()
            self._save_json()
            logger.debug(f"Stored outcome in JSON for {outcome.recommendation_id}")
            return outcome
        except Exception as e:
            logger.error(f"Error storing outcome in JSON: {e}")
            raise

    async def _create_supabase(self, outcome: Outcome) -> Outcome:
        """Store outcome in Supabase."""
        try:
            self.client.table("outcomes").insert(outcome.to_dict()).execute()
            logger.debug(f"Stored outcome in Supabase for {outcome.recommendation_id}")
            return outcome
        except Exception as e:
            logger.error(f"Error storing outcome in Supabase: {e}")
            raise

    async def get_by_recommendation(self, rec_id: str) -> Outcome | None:
        """Retrieve outcome for a recommendation.

        Args:
            rec_id: Recommendation ID

        Returns:
            Outcome object or None if not found
        """
        try:
            if self._use_json or not self.client:
                return self._get_by_recommendation_json(rec_id)
            else:
                return await self._get_by_recommendation_supabase(rec_id)
        except Exception as e:
            logger.error(f"Error retrieving outcome: {e}")
            return None

    def _get_by_recommendation_json(self, rec_id: str) -> Outcome | None:
        """Get outcome from JSON."""
        try:
            data = self._outcomes.get(rec_id)
            if data:
                return Outcome.from_dict(data)
            return None
        except Exception as e:
            logger.error(f"Error retrieving outcome from JSON: {e}")
            return None

    async def _get_by_recommendation_supabase(self, rec_id: str) -> Outcome | None:
        """Get outcome from Supabase."""
        try:
            result = self.client.table("outcomes").select("*").eq("recommendation_id", rec_id).execute()
            if result.data and len(result.data) > 0:
                return Outcome.from_dict(result.data[0])
            return None
        except Exception as e:
            logger.error(f"Error retrieving outcome from Supabase: {e}")
            return None

    async def get_accuracy_for_action_type(self, action_type: str, site_id: str, days: int = 30) -> float:
        """Get average accuracy for action type over time period.

        Queries all outcomes for this action type and calculates average accuracy.

        Args:
            action_type: Type of action (e.g., hvac_setpoint_change)
            site_id: Site ID
            days: Look back window (default 30 days)

        Returns:
            Average accuracy score 0.0-1.0, or 0.0 if no outcomes found
        """
        try:
            if self._use_json or not self.client:
                return self._get_accuracy_json(action_type, site_id, days)
            else:
                return await self._get_accuracy_supabase(action_type, site_id, days)
        except Exception as e:
            logger.error(f"Error getting accuracy for action type: {e}")
            return 0.0

    def _get_accuracy_json(self, action_type: str, site_id: str, days: int = 30) -> float:
        """Get average accuracy from JSON data."""
        try:
            _cutoff_date = datetime.utcnow() - timedelta(days=days)
            _accuracies = []

            # Note: JSON outcomes don't have action_type/site_id directly
            # In real implementation, would need to join with recommendations table
            # For now, return 0.0 as placeholder
            logger.debug("Average accuracy calculation requires database implementation")
            return 0.0

        except Exception as e:
            logger.error(f"Error calculating accuracy from JSON: {e}")
            return 0.0

    async def _get_accuracy_supabase(self, action_type: str, site_id: str, days: int = 30) -> float:
        """Get average accuracy from Supabase."""
        try:
            cutoff_date = (datetime.utcnow() - timedelta(days=days)).isoformat()

            # Query outcomes joined with recommendations to filter by action_type/site_id
            result = self.client.rpc(
                "get_action_accuracy",
                {
                    "p_action_type": action_type,
                    "p_site_id": site_id,
                    "p_cutoff_date": cutoff_date,
                },
            ).execute()

            if result.data and len(result.data) > 0:
                return float(result.data[0].get("average_accuracy", 0.0))

            return 0.0

        except Exception as e:
            logger.error(f"Error getting accuracy from Supabase: {e}")
            return 0.0

    def _save_json(self) -> None:
        """Persist outcomes to JSON file."""
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            outcome_file = DATA_DIR / "outcomes.json"

            with open(outcome_file, "w") as f:
                json.dump({"outcomes": self._outcomes}, f, indent=2)

            logger.debug("Outcomes saved to JSON")
        except Exception as e:
            logger.error(f"Error saving outcomes to JSON: {e}")


# Singleton instance
_outcome_repo: OutcomeRepository | None = None


def get_outcome_repository() -> OutcomeRepository:
    """Get or create OutcomeRepository singleton.

    Returns:
        OutcomeRepository instance
    """
    global _outcome_repo
    if _outcome_repo is None:
        _outcome_repo = OutcomeRepository()
    return _outcome_repo
