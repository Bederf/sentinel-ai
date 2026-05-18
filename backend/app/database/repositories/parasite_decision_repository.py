"""Repository for PARASITE decision tracking operations.

Implements Supabase + JSON fallback pattern for storing and retrieving autonomous
PARASITE decisions through the complete audit trail lifecycle: decision creation,
execution, COV verification, outcome measurement, and rollback tracking.

Schema: see app.models.parasite_decision.ParasiteDecision for full field list.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config.settings import settings
from app.models.parasite_decision import WriteStatus, _safe_json_value

logger = logging.getLogger(__name__)

# Data directory for JSON fallback
DATA_DIR = Path(__file__).parent.parent.parent / "data"


class ParasiteDecisionRepository:
    """Repository for PARASITE decision database operations.

    Manages autonomous decision records with Supabase as primary storage and
    JSON files as fallback. Supports querying by site, equipment, tier, and time.

    All records are validated for JSON-serializability before persistence.
    """

    def __init__(self, json_path: Path | None = None):
        """Initialize the repository.

        Args:
            json_path: Override path for JSON storage. Used by tests to
                      avoid writing to the shared production file.
        """
        self._client = None
        self._use_json = settings.use_json_storage
        self._decisions: dict[str, dict[str, Any]] = {}
        self._json_path = json_path  # None = use default DATA_DIR path

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

    def _validate_record(self, decision: dict) -> None:
        """Validate that all values in a decision record are JSON-serializable.

        Raises TypeError if any value would corrupt the store (coroutines,
        mocks, non-serializable objects).
        """
        for key in ("original_value", "target_value", "actual_value", "cov_tolerance"):
            if key in decision:
                _safe_json_value(decision[key])

    def _normalize_point_name(self, decision: dict) -> None:
        """Ensure point_name is canonical, control_point is alias.

        point_name is the canonical field name. control_point is kept
        for backward compatibility but always mirrors point_name.
        """
        pn = decision.get("point_name")
        cp = decision.get("control_point")
        if pn is None and cp is not None:
            decision["point_name"] = cp
        elif cp is None and pn is not None:
            decision["control_point"] = pn

    async def record_decision(self, decision: dict) -> dict:
        """Insert new decision record.

        Accepts both legacy dicts (from existing call sites) and new-format
        dicts with mode/gate/safety context fields. Missing fields are stored
        as null — callers add context incrementally.

        Args:
            decision: Decision dictionary. See ParasiteDecision for full field list.

        Returns:
            Created decision record with id and timestamps.

        Raises:
            TypeError: If any value is not JSON-serializable (coroutine, mock, etc.)
            Exception: If creation fails.
        """
        try:
            # Validate serialization safety
            self._validate_record(decision)

            # Normalize point_name / control_point
            self._normalize_point_name(decision)

            # Ensure id and timestamps
            if "id" not in decision:
                import uuid

                decision["id"] = str(uuid.uuid4())
            if "created_at" not in decision:
                decision["created_at"] = datetime.utcnow().isoformat()
            if "updated_at" not in decision:
                decision["updated_at"] = datetime.utcnow().isoformat()

            # Set initial write_status for intent records (NOT actual BACnet writes)
            if "write_status" not in decision:
                decision["write_status"] = WriteStatus.INTENT_LOGGED.value

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

        except TypeError:
            # Re-raise serialization errors without wrapping
            raise
        except Exception as e:
            logger.error(f"Error recording PARASITE decision: {e}")
            raise

    async def update_outcome(
        self,
        decision_id: str,
        outcome: dict,
        matched: bool,
        measured_impact: dict[str, Any] | None = None,
    ) -> dict:
        """Update decision with measured outcome.

        Args:
            decision_id: Decision ID
            outcome: Outcome measurements dictionary
            matched: Whether outcome matched prediction
            measured_impact: Optional structured impact measurements
                           (energy_kwh, comfort_delta, runtime_delta, cost)

        Returns:
            Updated decision record.
        """
        try:
            update_data = {
                "outcome": outcome,
                "outcome_matched_prediction": matched,
                "outcome_measured_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            }
            if measured_impact is not None:
                update_data["measured_impact"] = measured_impact

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

    async def mark_rolled_back(self, decision_id: str, reason: str) -> dict:
        """Mark decision as rolled back.

        Args:
            decision_id: Decision ID
            reason: Reason for rollback

        Returns:
            Updated decision record.
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

    async def record_bacnet_write_dispatched(
        self,
        decision_id: str,
        write_succeeded: bool | None = None,
    ) -> dict:
        """Record that an actual BACnet write was dispatched (NOT just intent logged).

        This is called by ApprovalService ONLY when write_device_value() is actually
        invoked. The initial parasite_decision record is created with write_status='intent_logged'
        by TierRoutingEngine - that is NOT an actual write attempt.

        Args:
            decision_id: Decision ID
            write_succeeded: True if write succeeded, False if failed, None if pending

        Returns:
            Updated decision record.
        """
        try:
            # Determine write status based on result
            if write_succeeded is None:
                status = WriteStatus.DISPATCHED.value
            elif write_succeeded:
                status = WriteStatus.SUCCEEDED.value
            else:
                status = WriteStatus.FAILED.value

            update_data = {
                "bacnet_write_dispatched": True,
                "write_status": status,
                "write_attempt_count": 1,  # Actual BACnet write attempt
                "bacnet_write_succeeded": write_succeeded,
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
            logger.error(f"Error recording BACnet write dispatch for decision {decision_id}: {e}")
            raise

    async def update_cov_status(
        self,
        decision_id: str,
        verified: bool,
        actual_value: Any,
        cov_latency_ms: int | None = None,
        cov_tolerance: Any = None,
    ) -> dict:
        """Update COV verification result.

        Args:
            decision_id: Decision ID
            verified: Whether COV was verified
            actual_value: Actual value read back from device
            cov_latency_ms: Time taken for COV verification in milliseconds
            cov_tolerance: Tolerance used for COV comparison

        Returns:
            Updated decision record.
        """
        try:
            _safe_json_value(actual_value)
            _safe_json_value(cov_tolerance)

            update_data: dict[str, Any] = {
                "cov_verified": verified,
                "actual_value": actual_value,
                "updated_at": datetime.utcnow().isoformat(),
            }
            if cov_latency_ms is not None:
                update_data["cov_latency_ms"] = cov_latency_ms
            if cov_tolerance is not None:
                update_data["cov_tolerance"] = cov_tolerance

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

    async def get_decision_by_id(self, decision_id: str) -> dict | None:
        """Get a single decision by its ID.

        Args:
            decision_id: Decision UUID

        Returns:
            Decision dict or None if not found.
        """
        try:
            if not self._use_json and self.client:
                result = self.client.table("parasite_decisions").select("*").eq("id", decision_id).limit(1).execute()
                return result.data[0] if result.data else None

            # JSON fallback
            self._load_all()
            return self._decisions.get(decision_id)

        except Exception as e:
            logger.error(f"Error getting decision {decision_id}: {e}")
            return None

    async def count_pending_measurements(self) -> int:
        """Count decisions awaiting outcome measurement.

        Returns decisions where write_status is 'success' or 'blocked'
        but outcome_measured_at is still null.
        """
        try:
            if not self._use_json and self.client:
                result = (
                    self.client.table("parasite_decisions")
                    .select("id", count="exact")
                    .in_("write_status", [WriteStatus.SUCCEEDED.value, WriteStatus.BLOCKED_BY_GATE.value])
                    .is_("outcome_measured_at", "null")
                    .execute()
                )
                return result.count if result.count is not None else 0

            # JSON fallback
            self._load_all()
            return sum(
                1
                for d in self._decisions.values()
                if d.get("write_status") in (WriteStatus.SUCCEEDED.value, WriteStatus.BLOCKED_BY_GATE.value)
                and d.get("outcome_measured_at") is None
            )

        except Exception as e:
            logger.error(f"Error counting pending measurements: {e}")
            return 0

    async def get_decisions_since(self, since_iso: str, limit: int = 500) -> list[dict]:
        """Get decisions created after a given ISO timestamp.

        Args:
            since_iso: ISO 8601 timestamp lower bound (exclusive)
            limit: Maximum number to return

        Returns:
            List of decisions newer than since_iso, newest first.
        """
        try:
            if not self._use_json and self.client:
                result = (
                    self.client.table("parasite_decisions")
                    .select("*")
                    .gt("created_at", since_iso)
                    .order("created_at", desc=True)
                    .limit(limit)
                    .execute()
                )
                return result.data if result.data else []

            # JSON fallback
            self._load_all()
            matching = [d for d in self._decisions.values() if d.get("created_at", "") > since_iso]
            matching.sort(key=lambda d: d.get("created_at", ""), reverse=True)
            return matching[:limit]

        except Exception as e:
            logger.error(f"Error getting decisions since {since_iso}: {e}")
            return []

    async def get_decisions_by_site(self, site_id: str, since: str | None = None, limit: int = 1000) -> list[dict]:
        """Query decisions by site with optional time filter.

        Like get_decisions_for_site but accepts an optional `since` kwarg
        to restrict to decisions created after a given ISO timestamp.

        Args:
            site_id: Site identifier
            since: Optional ISO 8601 lower bound (exclusive)
            limit: Maximum number to return

        Returns:
            List of decisions for site, newest first.
        """
        try:
            if not self._use_json and self.client:
                query = self.client.table("parasite_decisions").select("*").eq("site_id", site_id)
                if since:
                    query = query.gt("created_at", since)
                query = query.order("created_at", desc=True).limit(limit)
                result = query.execute()
                return result.data if result.data else []

            # JSON fallback
            self._load_all()
            matching = [d for d in self._decisions.values() if d.get("site_id") == site_id]
            if since:
                matching = [d for d in matching if d.get("created_at", "") > since]
            matching.sort(key=lambda d: d.get("created_at", ""), reverse=True)
            return matching[:limit]

        except Exception as e:
            logger.error(f"Error querying decisions by site {site_id}: {e}")
            return []

    async def get_decisions_for_equipment(self, equipment_code: str, limit: int = 50) -> list[dict]:
        """Query decisions by equipment.

        Args:
            equipment_code: Equipment identifier
            limit: Maximum number to return

        Returns:
            List of decisions for equipment, newest first.
        """
        try:
            if not self._use_json and self.client:
                recs = await self._supabase_query(filters={"equipment_code": equipment_code}, limit=limit)
                return recs

            # Fall back to JSON
            self._load_all()
            matching = [dec for dec in self._decisions.values() if dec.get("equipment_code") == equipment_code]
            matching.sort(key=lambda d: d.get("created_at", ""), reverse=True)
            return matching[:limit]

        except Exception as e:
            logger.error(f"Error querying decisions for equipment {equipment_code}: {e}")
            return []

    async def get_decisions_for_site(self, site_id: str, limit: int = 50) -> list[dict]:
        """Query decisions by site.

        Args:
            site_id: Site identifier
            limit: Maximum number to return

        Returns:
            List of decisions for site, newest first.
        """
        try:
            if not self._use_json and self.client:
                recs = await self._supabase_query(filters={"site_id": site_id}, limit=limit)
                return recs

            # Fall back to JSON
            self._load_all()
            matching = [dec for dec in self._decisions.values() if dec.get("site_id") == site_id]
            matching.sort(key=lambda d: d.get("created_at", ""), reverse=True)
            return matching[:limit]

        except Exception as e:
            logger.error(f"Error querying decisions for site {site_id}: {e}")
            return []

    async def get_decisions_by_tier(self, tier: str, limit: int = 50) -> list[dict]:
        """Query decisions by tier.

        Args:
            tier: Tier level (tier1, tier2, tier3)
            limit: Maximum number to return

        Returns:
            List of decisions in tier, newest first.
        """
        try:
            if not self._use_json and self.client:
                recs = await self._supabase_query(filters={"tier": tier}, limit=limit)
                return recs

            # Fall back to JSON
            self._load_all()
            matching = [dec for dec in self._decisions.values() if dec.get("tier") == tier]
            matching.sort(key=lambda d: d.get("created_at", ""), reverse=True)
            return matching[:limit]

        except Exception as e:
            logger.error(f"Error querying decisions by tier {tier}: {e}")
            return []

    async def get_recent_decisions(self, limit: int = 100) -> list[dict]:
        """Get most recent decisions across all sites.

        Args:
            limit: Maximum number to return

        Returns:
            List of most recent decisions.
        """
        try:
            if not self._use_json and self.client:
                recs = await self._supabase_query(limit=limit)
                return recs

            # Fall back to JSON
            self._load_all()
            decisions = list(self._decisions.values())
            decisions.sort(key=lambda d: d.get("created_at", ""), reverse=True)
            return decisions[:limit]

        except Exception as e:
            logger.error(f"Error querying recent decisions: {e}")
            return []

    async def get_decision_stats(self, site_id: str) -> dict:
        """Get aggregated decision statistics for a site.

        Args:
            site_id: Site identifier

        Returns:
            Dictionary with stats: count_by_tier, rollback_rate, cov_success_rate.
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
            rolled_back = sum(1 for dec in decisions if dec.get("rolled_back", False))
            rollback_rate = (rolled_back / len(decisions)) if decisions else 0

            # Calculate COV success rate
            cov_verified = sum(1 for dec in decisions if dec.get("cov_verified", False))
            cov_success_rate = (cov_verified / len(decisions)) if decisions else 0

            return {
                "total_decisions": len(decisions),
                "count_by_tier": tier_counts,
                "rollback_rate": round(rollback_rate, 3),
                "cov_success_rate": round(cov_success_rate, 3),
            }

        except Exception as e:
            logger.error(f"Error calculating decision stats for site {site_id}: {e}")
            return {}

    async def _supabase_insert(self, decision: dict) -> dict | None:
        """Insert decision to Supabase."""
        try:
            if not self.client:
                return None
            result = self.client.table("parasite_decisions").insert(decision).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Supabase insert failed: {e}")
            return None

    async def _supabase_update(self, decision_id: str, update_data: dict) -> dict | None:
        """Update decision in Supabase."""
        try:
            if not self.client:
                return None
            result = self.client.table("parasite_decisions").update(update_data).eq("id", decision_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Supabase update failed: {e}")
            return None

    async def _supabase_query(self, filters: dict | None = None, limit: int = 50) -> list[dict]:
        """Query decisions from Supabase."""
        try:
            if not self.client:
                return []
            query = self.client.table("parasite_decisions").select("*").order("created_at", desc=True).limit(limit)

            # Apply filters if provided
            if filters:
                for key, value in filters.items():
                    query = query.eq(key, value)

            result = query.execute()
            return result.data if result.data else []
        except Exception as e:
            logger.error(f"Supabase query failed: {e}")
            return []

    def _get_json_path(self) -> Path:
        """Get the JSON file path, supporting test overrides."""
        if self._json_path is not None:
            return self._json_path
        return DATA_DIR / "parasite_decisions.json"

    def _load_all(self) -> None:
        """Load all decisions from JSON (fallback)."""
        filepath = self._get_json_path()
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
        filepath = self._get_json_path()
        try:
            filepath.parent.mkdir(parents=True, exist_ok=True)
            with open(filepath, "w") as f:
                json.dump(self._decisions, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Failed to save parasite_decisions.json: {e}")


# Singleton pattern
_instance: ParasiteDecisionRepository | None = None


def get_parasite_decision_repository() -> ParasiteDecisionRepository:
    """Get or create the ParasiteDecisionRepository singleton."""
    global _instance
    if _instance is None:
        _instance = ParasiteDecisionRepository()
    return _instance
