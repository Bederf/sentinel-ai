"""Repository for PARASITE decision tracking operations.

Implements Supabase + JSON fallback pattern for storing and retrieving autonomous
PARASITE decisions through the complete audit trail lifecycle: decision creation,
execution, COV verification, outcome measurement, and rollback tracking.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config.settings import settings

logger = logging.getLogger(__name__)

# Data directory for JSON fallback
DATA_DIR = Path(__file__).parent.parent.parent / "data"


class ParasiteDecisionRepository:
    """Repository for PARASITE decision database operations.

    Manages autonomous decision records with Supabase as primary storage and
    JSON files as fallback. Supports querying by site, equipment, tier, and time.
    """

    def __init__(self):
        """Initialize the repository."""
        self._client = None
        self._use_json = settings.use_json_storage
        self._decisions: Dict[str, Dict[str, Any]] = {}

    @property
    def client(self):
        """Lazy load Supabase client."""
        if self._client is None and not self._use_json:
            try:
                from app.database.supabase_client import get_supabase_client

                self._client = get_supabase_client()
            except Exception as e:
                logger.warning(
                    f"Failed to get Supabase client, using JSON fallback: {e}"
                )
                self._use_json = True
        return self._client

    async def record_decision(self, decision: Dict) -> Dict:
        """Insert new decision record.

        Args:
            decision: Decision dictionary with keys: recommendation_id, site_id, equipment_code,
                     decision_type, tier, confidence_score, contributing_factors, decision_details,
                     control_point, original_value, target_value

        Returns:
            Created decision record with id and timestamps

        Raises:
            Exception: If creation fails
        """
        try:
            # Ensure id and created_at
            if "id" not in decision:
                import uuid
                decision["id"] = str(uuid.uuid4())
            if "created_at" not in decision:
                decision["created_at"] = datetime.utcnow().isoformat()
            if "updated_at" not in decision:
                decision["updated_at"] = datetime.utcnow().isoformat()

            if not self._use_json and self.client:
                # Save to Supabase
                result = await self._supabase_insert(decision)
                if result:
                    return result if isinstance(result, dict) else result[0]

            # Fall back to JSON
            self._load_all()
            self._decisions[decision["id"]] = decision
            self._save_all()
            return decision

        except Exception as e:
            logger.error(f"Error recording PARASITE decision: {e}")
            raise

    async def update_outcome(
        self, decision_id: str, outcome: Dict, matched: bool
    ) -> Dict:
        """Update decision with measured outcome.

        Args:
            decision_id: Decision ID
            outcome: Outcome measurements dictionary
            matched: Whether outcome matched prediction

        Returns:
            Updated decision record

        Raises:
            Exception: If update fails
        """
        try:
            update_data = {
                "outcome": outcome,
                "outcome_matched_prediction": matched,
                "outcome_measured_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            }

            if not self._use_json and self.client:
                result = await self._supabase_update(decision_id, update_data)
                if result:
                    return result if isinstance(result, dict) else result[0]

            # Fall back to JSON
            self._load_all()
            if decision_id in self._decisions:
                self._decisions[decision_id].update(update_data)
                self._save_all()
                return self._decisions[decision_id]
            raise KeyError(f"Decision {decision_id} not found")

        except Exception as e:
            logger.error(f"Error updating outcome for decision {decision_id}: {e}")
            raise

    async def mark_rolled_back(self, decision_id: str, reason: str) -> Dict:
        """Mark decision as rolled back.

        Args:
            decision_id: Decision ID
            reason: Reason for rollback

        Returns:
            Updated decision record

        Raises:
            Exception: If update fails
        """
        try:
            update_data = {
                "rolled_back": True,
                "rollback_reason": reason,
                "rollback_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            }

            if not self._use_json and self.client:
                result = await self._supabase_update(decision_id, update_data)
                if result:
                    return result if isinstance(result, dict) else result[0]

            # Fall back to JSON
            self._load_all()
            if decision_id in self._decisions:
                self._decisions[decision_id].update(update_data)
                self._save_all()
                return self._decisions[decision_id]
            raise KeyError(f"Decision {decision_id} not found")

        except Exception as e:
            logger.error(f"Error marking decision as rolled back: {e}")
            raise

    async def update_cov_status(
        self, decision_id: str, verified: bool, actual_value: str
    ) -> Dict:
        """Update COV verification result.

        Args:
            decision_id: Decision ID
            verified: Whether COV was verified
            actual_value: Actual value read back from device

        Returns:
            Updated decision record

        Raises:
            Exception: If update fails
        """
        try:
            update_data = {
                "cov_verified": verified,
                "actual_value": actual_value,
                "updated_at": datetime.utcnow().isoformat(),
            }

            if not self._use_json and self.client:
                result = await self._supabase_update(decision_id, update_data)
                if result:
                    return result if isinstance(result, dict) else result[0]

            # Fall back to JSON
            self._load_all()
            if decision_id in self._decisions:
                self._decisions[decision_id].update(update_data)
                self._save_all()
                return self._decisions[decision_id]
            raise KeyError(f"Decision {decision_id} not found")

        except Exception as e:
            logger.error(f"Error updating COV status for decision {decision_id}: {e}")
            raise

    async def get_decisions_for_equipment(
        self, equipment_code: str, limit: int = 50
    ) -> List[Dict]:
        """Query decisions by equipment.

        Args:
            equipment_code: Equipment identifier
            limit: Maximum number to return

        Returns:
            List of decisions for equipment, newest first
        """
        try:
            if not self._use_json and self.client:
                recs = await self._supabase_query(
                    filters={"equipment_code": equipment_code}, limit=limit
                )
                return recs

            # Fall back to JSON
            self._load_all()
            matching = [
                dec
                for dec in self._decisions.values()
                if dec.get("equipment_code") == equipment_code
            ]
            # Sort by created_at DESC (newest first)
            matching.sort(key=lambda d: d.get("created_at", ""), reverse=True)
            return matching[:limit]

        except Exception as e:
            logger.error(
                f"Error querying decisions for equipment {equipment_code}: {e}"
            )
            return []

    async def get_decisions_for_site(
        self, site_id: str, limit: int = 50
    ) -> List[Dict]:
        """Query decisions by site.

        Args:
            site_id: Site identifier
            limit: Maximum number to return

        Returns:
            List of decisions for site, newest first
        """
        try:
            if not self._use_json and self.client:
                recs = await self._supabase_query(
                    filters={"site_id": site_id}, limit=limit
                )
                return recs

            # Fall back to JSON
            self._load_all()
            matching = [
                dec
                for dec in self._decisions.values()
                if dec.get("site_id") == site_id
            ]
            # Sort by created_at DESC (newest first)
            matching.sort(key=lambda d: d.get("created_at", ""), reverse=True)
            return matching[:limit]

        except Exception as e:
            logger.error(f"Error querying decisions for site {site_id}: {e}")
            return []

    async def get_decisions_by_tier(
        self, tier: str, limit: int = 50
    ) -> List[Dict]:
        """Query decisions by tier.

        Args:
            tier: Tier level (tier1, tier2, tier3)
            limit: Maximum number to return

        Returns:
            List of decisions in tier, newest first
        """
        try:
            if not self._use_json and self.client:
                recs = await self._supabase_query(
                    filters={"tier": tier}, limit=limit
                )
                return recs

            # Fall back to JSON
            self._load_all()
            matching = [
                dec
                for dec in self._decisions.values()
                if dec.get("tier") == tier
            ]
            # Sort by created_at DESC (newest first)
            matching.sort(key=lambda d: d.get("created_at", ""), reverse=True)
            return matching[:limit]

        except Exception as e:
            logger.error(f"Error querying decisions by tier {tier}: {e}")
            return []

    async def get_recent_decisions(self, limit: int = 100) -> List[Dict]:
        """Get most recent decisions across all sites.

        Args:
            limit: Maximum number to return

        Returns:
            List of most recent decisions
        """
        try:
            if not self._use_json and self.client:
                recs = await self._supabase_query(limit=limit)
                return recs

            # Fall back to JSON
            self._load_all()
            decisions = list(self._decisions.values())
            # Sort by created_at DESC (newest first)
            decisions.sort(key=lambda d: d.get("created_at", ""), reverse=True)
            return decisions[:limit]

        except Exception as e:
            logger.error(f"Error querying recent decisions: {e}")
            return []

    async def get_decision_stats(self, site_id: str) -> Dict:
        """Get aggregated decision statistics for a site.

        Args:
            site_id: Site identifier

        Returns:
            Dictionary with stats: count_by_tier, rollback_rate, cov_success_rate
        """
        try:
            decisions = await self.get_decisions_for_site(site_id, limit=1000)

            # Count by tier
            tier_counts = {"tier1": 0, "tier2": 0, "tier3": 0}
            for dec in decisions:
                tier = dec.get("tier")
                if tier in tier_counts:
                    tier_counts[tier] += 1

            # Calculate rollback rate
            rolled_back = sum(
                1 for dec in decisions if dec.get("rolled_back", False)
            )
            rollback_rate = (
                (rolled_back / len(decisions)) if decisions else 0
            )

            # Calculate COV success rate
            cov_verified = sum(
                1 for dec in decisions if dec.get("cov_verified", False)
            )
            cov_success_rate = (
                (cov_verified / len(decisions)) if decisions else 0
            )

            return {
                "total_decisions": len(decisions),
                "count_by_tier": tier_counts,
                "rollback_rate": round(rollback_rate, 3),
                "cov_success_rate": round(cov_success_rate, 3),
            }

        except Exception as e:
            logger.error(f"Error calculating decision stats for site {site_id}: {e}")
            return {}

    async def _supabase_insert(self, decision: Dict) -> Optional[Dict]:
        """Insert decision to Supabase."""
        try:
            if not self.client:
                return None
            result = self.client.table("parasite_decisions").insert(decision).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Supabase insert failed: {e}")
            return None

    async def _supabase_update(
        self, decision_id: str, update_data: Dict
    ) -> Optional[Dict]:
        """Update decision in Supabase."""
        try:
            if not self.client:
                return None
            result = (
                self.client.table("parasite_decisions")
                .update(update_data)
                .eq("id", decision_id)
                .execute()
            )
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Supabase update failed: {e}")
            return None

    async def _supabase_query(
        self, filters: Optional[Dict] = None, limit: int = 50
    ) -> List[Dict]:
        """Query decisions from Supabase."""
        try:
            if not self.client:
                return []
            query = (
                self.client.table("parasite_decisions")
                .select("*")
                .order("created_at", desc=True)
                .limit(limit)
            )

            # Apply filters if provided
            if filters:
                for key, value in filters.items():
                    query = query.eq(key, value)

            result = query.execute()
            return result.data if result.data else []
        except Exception as e:
            logger.error(f"Supabase query failed: {e}")
            return []

    def _load_all(self) -> None:
        """Load all decisions from JSON (fallback)."""
        filepath = DATA_DIR / "parasite_decisions.json"
        if filepath.exists():
            try:
                with open(filepath) as f:
                    data = json.load(f)
                    self._decisions = data if isinstance(data, dict) else {}
            except Exception as e:
                logger.warning(f"Failed to load parasite_decisions.json: {e}")
                self._decisions = {}
        else:
            self._decisions = {}

    def _save_all(self) -> None:
        """Save all decisions to JSON (fallback)."""
        filepath = DATA_DIR / "parasite_decisions.json"
        try:
            filepath.parent.mkdir(parents=True, exist_ok=True)
            with open(filepath, "w") as f:
                json.dump(self._decisions, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Failed to save parasite_decisions.json: {e}")


# Singleton pattern
_instance: Optional[ParasiteDecisionRepository] = None


def get_parasite_decision_repository() -> ParasiteDecisionRepository:
    """Get or create the ParasiteDecisionRepository singleton."""
    global _instance
    if _instance is None:
        _instance = ParasiteDecisionRepository()
    return _instance
