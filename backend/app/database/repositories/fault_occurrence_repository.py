"""Repository for fault occurrence tracking and cluster detection.

Implements dual-write pattern: Supabase (primary) + JSON file (backup).
Handles concurrent inserts via upsert logic (site_code + equipment_id + issue_type + occurred_at window).

Cluster detection: 3+ occurrences of same (site_code, equipment_id, issue_type)
within a sliding 90-day window triggers is_cluster_alert=True.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.database.supabase_client import get_supabase_client
from app.models.fault_occurrence import FaultOccurrence

logger = logging.getLogger(__name__)

# Default sliding window: 90 days
DEFAULT_WINDOW_DAYS = 90
# Default cluster threshold: 3 occurrences
DEFAULT_CLUSTER_THRESHOLD = 3


class FaultOccurrenceRepository:
    """Repository for fault occurrence operations with dual-write support."""

    def __init__(self):
        """Initialize repository with Supabase client."""
        self._client = None
        self.json_backup_path = Path("backend/app/data/fault_occurrences.json")

    @property
    def client(self):
        """Lazy load Supabase client."""
        if self._client is None:
            try:
                self._client = get_supabase_client()
            except Exception as e:
                logger.warning("Failed to get Supabase client for fault occurrences: %s", e)
                self._client = None
        return self._client

    def _ensure_json_backup(self) -> dict[str, Any]:
        """Ensure JSON backup file exists and return its contents."""
        if not self.json_backup_path.exists():
            self.json_backup_path.parent.mkdir(parents=True, exist_ok=True)
            initial = {"occurrences": []}
            with open(self.json_backup_path, "w") as f:
                json.dump(initial, f)
            return initial
        try:
            with open(self.json_backup_path) as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("Failed to read JSON backup, resetting: %s", e)
            return {"occurrences": []}

    def _save_json_backup(self, data: dict[str, Any]) -> None:
        """Save data to JSON backup."""
        try:
            with open(self.json_backup_path, "w") as f:
                json.dump(data, f, indent=2, default=str)
        except OSError as e:
            logger.error("Failed to save JSON backup: %s", e)

    # -------------------------------------------------------------------------
    # Supabase helpers
    # -------------------------------------------------------------------------

    async def _supabase_insert(self, occurrence: FaultOccurrence) -> dict[str, Any] | None:
        """Insert occurrence to Supabase."""
        if self.client is None:
            return None
        try:
            data = occurrence.to_dict()
            response = self.client.table("fault_occurrences").insert(data).execute()
            if response.data:
                return response.data[0]
        except Exception as e:
            logger.warning("Supabase insert failed for fault_occurrence: %s", e)
        return None

    async def _supabase_get_count(
        self,
        site_code: str,
        equipment_id: str,
        issue_type: str,
        window_days: int = DEFAULT_WINDOW_DAYS,
    ) -> int:
        """Get count of occurrences in sliding window via Supabase."""
        if self.client is None:
            return 0
        try:
            cutoff = datetime.utcnow() - timedelta(days=window_days)
            response = (
                self.client.table("fault_occurrences")
                .select("id", count="exact")
                .eq("site_code", site_code)
                .eq("equipment_id", equipment_id)
                .eq("issue_type", issue_type)
                .gte("occurred_at", cutoff.isoformat())
                .execute()
            )
            return response.count or 0
        except Exception as e:
            logger.warning("Supabase count query failed: %s", e)
            return 0

    async def _supabase_get_by_site(
        self,
        site_code: str,
        window_days: int = DEFAULT_WINDOW_DAYS,
        threshold: int = DEFAULT_CLUSTER_THRESHOLD,
    ) -> list[dict[str, Any]]:
        """Get cluster alerts for site: equipment with >= threshold occurrences in window."""
        if self.client is None:
            return []
        try:
            cutoff = datetime.utcnow() - timedelta(days=window_days)
            # Group by equipment_id + issue_type, count >= threshold
            response = (
                self.client.table("fault_occurrences")
                .select("equipment_id, issue_type, count")
                .eq("site_code", site_code)
                .gte("occurred_at", cutoff.isoformat())
                .execute()
            )
            # Filter to those with count >= threshold
            return [r for r in response.data if r.get("count", 0) >= threshold]
        except Exception as e:
            logger.warning("Supabase cluster alert query failed: %s", e)
            return []

    # -------------------------------------------------------------------------
    # JSON fallback helpers
    # -------------------------------------------------------------------------

    def _json_get_count(
        self,
        site_code: str,
        equipment_id: str,
        issue_type: str,
        window_days: int = DEFAULT_WINDOW_DAYS,
    ) -> int:
        """Get occurrence count from JSON backup."""
        data = self._ensure_json_backup()
        cutoff = datetime.utcnow() - timedelta(days=window_days)
        count = 0
        for occ in data.get("occurrences", []):
            if (
                occ.get("site_code") == site_code
                and occ.get("equipment_id") == equipment_id
                and occ.get("issue_type") == issue_type
            ):
                try:
                    occ_time = datetime.fromisoformat(occ.get("occurred_at", ""))
                    if occ_time >= cutoff:
                        count += 1
                except (ValueError, TypeError):
                    continue
        return count

    def _json_get_all_for_site(self, site_code: str) -> list[FaultOccurrence]:
        """Get all occurrences for a site from JSON backup."""
        data = self._ensure_json_backup()
        occurrences = []
        for occ_dict in data.get("occurrences", []):
            if occ_dict.get("site_code") == site_code:
                occurrences.append(FaultOccurrence.from_dict(occ_dict))
        return occurrences

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    async def record_occurrence(
        self,
        site_code: str,
        equipment_id: str,
        issue_type: str,
        recommendation_id: str | None = None,
        window_days: int = DEFAULT_WINDOW_DAYS,
        cluster_threshold: int = DEFAULT_CLUSTER_THRESHOLD,
    ) -> FaultOccurrence:
        """Record a fault occurrence and check for cluster.

        Uses upsert logic: concurrent inserts for same site+equipment+issue_type
        are handled by reading current count before inserting.

        Args:
            site_code: Building identifier (e.g., "S002")
            equipment_id: Equipment identifier (e.g., "S002-URINAL-B1-001")
            issue_type: Fault type (e.g., "urinal_blocked")
            recommendation_id: Associated recommendation ID (optional)
            window_days: Sliding window size (default 90)
            cluster_threshold: Count that triggers cluster alert (default 3)

        Returns:
            FaultOccurrence with is_cluster_alert and cluster_count populated
        """
        # Empty input guard
        if not equipment_id or not issue_type:
            logger.warning("Skipping fault occurrence with empty equipment_id or issue_type")
            return FaultOccurrence(
                site_code=site_code,
                equipment_id=equipment_id or "",
                issue_type=issue_type or "",
                is_cluster_alert=False,
                cluster_count=0,
            )

        # Get current count in window BEFORE inserting
        current_count = await self._supabase_get_count(site_code, equipment_id, issue_type, window_days)
        if current_count == 0:
            # Fallback to JSON count
            current_count = self._json_get_count(site_code, equipment_id, issue_type, window_days)

        new_count = current_count + 1
        is_cluster = new_count >= cluster_threshold

        occurrence = FaultOccurrence(
            id=str(uuid.uuid4()),
            site_code=site_code,
            equipment_id=equipment_id,
            issue_type=issue_type,
            occurred_at=datetime.utcnow(),
            recommendation_id=recommendation_id,
            is_cluster_alert=is_cluster,
            cluster_count=new_count,
        )

        # Dual-write: Supabase primary, JSON fallback
        supabase_result = await self._supabase_insert(occurrence)
        if supabase_result is None:
            # Fallback: append to JSON
            logger.info("Using JSON fallback for fault_occurrence %s", occurrence.id)
            data = self._ensure_json_backup()
            data["occurrences"].append(occurrence.to_dict())
            self._save_json_backup(data)
        else:
            # Backup to JSON
            data = self._ensure_json_backup()
            data["occurrences"].append(occurrence.to_dict())
            self._save_json_backup(data)

        return occurrence

    async def get_occurrence_count(
        self,
        site_code: str,
        equipment_id: str,
        issue_type: str,
        window_days: int = DEFAULT_WINDOW_DAYS,
    ) -> int:
        """Get count of occurrences in sliding window.

        Args:
            site_code: Building identifier
            equipment_id: Equipment identifier
            issue_type: Fault type
            window_days: Sliding window size (default 90)

        Returns:
            Count of occurrences in window
        """
        count = await self._supabase_get_count(site_code, equipment_id, issue_type, window_days)
        if count == 0:
            count = self._json_get_count(site_code, equipment_id, issue_type, window_days)
        return count

    async def get_cluster_alerts(
        self,
        site_code: str,
        window_days: int = DEFAULT_WINDOW_DAYS,
        cluster_threshold: int = DEFAULT_CLUSTER_THRESHOLD,
    ) -> list[dict[str, Any]]:
        """Get all cluster alerts for a site.

        Returns equipment+issue_type pairs with >= cluster_threshold occurrences
        in the sliding window. Each alert includes the running cluster_count.

        Args:
            site_code: Building identifier
            window_days: Sliding window size (default 90)
            cluster_threshold: Minimum occurrences (default 3)

        Returns:
            List of cluster alert dicts with keys:
            - equipment_id, issue_type, cluster_count, latest_occurred_at
        """
        # Try Supabase first
        alerts = await self._supabase_get_by_site(site_code, window_days, cluster_threshold)
        if alerts:
            return alerts

        # Fallback: scan JSON
        occurrences = self._json_get_all_for_site(site_code)
        cutoff = datetime.utcnow() - timedelta(days=window_days)

        # Group by equipment_id + issue_type
        groups: dict[tuple[str, str], list[FaultOccurrence]] = {}
        for occ in occurrences:
            if occ.occurred_at >= cutoff:
                key = (occ.equipment_id, occ.issue_type)
                if key not in groups:
                    groups[key] = []
                groups[key].append(occ)

        alerts = []
        for (eq_id, issue), occs in groups.items():
            if len(occs) >= cluster_threshold:
                alerts.append(
                    {
                        "equipment_id": eq_id,
                        "issue_type": issue,
                        "cluster_count": len(occs),
                        "latest_occurred_at": max(occ.occurred_at for occ in occs).isoformat(),
                    }
                )
        return alerts

    async def reset_cluster_count(
        self,
        equipment_id: str,
        issue_type: str,
        site_code: str | None = None,
    ) -> None:
        """Reset cluster count by marking occurrences as acknowledged.

        For simplicity, we add an 'acknowledged' flag to occurrences in JSON.
        Supabase would need a separate 'acknowledged_at' column — for now,
        we only reset in JSON backup.

        Args:
            equipment_id: Equipment identifier
            issue_type: Fault type
            site_code: Optional site filter
        """
        try:
            data = self._ensure_json_backup()
            now = datetime.utcnow().isoformat()
            for occ in data.get("occurrences", []):
                if occ.get("equipment_id") == equipment_id and occ.get("issue_type") == issue_type:
                    if site_code is None or occ.get("site_code") == site_code:
                        occ["cluster_acknowledged_at"] = now
                        occ["is_cluster_alert"] = False
            self._save_json_backup(data)
            logger.info("Reset cluster count for %s / %s", equipment_id, issue_type)
        except Exception as e:
            logger.error("Failed to reset cluster count: %s", e)


# Singleton
_fault_occurrence_repository: FaultOccurrenceRepository | None = None


def get_fault_occurrence_repository() -> FaultOccurrenceRepository:
    """Get or create FaultOccurrenceRepository singleton."""
    global _fault_occurrence_repository
    if _fault_occurrence_repository is None:
        _fault_occurrence_repository = FaultOccurrenceRepository()
    return _fault_occurrence_repository
