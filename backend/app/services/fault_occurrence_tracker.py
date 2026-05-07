"""FaultOccurrenceTracker service for cluster detection at 3rd occurrence.

Tracks fault occurrences per equipment and detects systemic issues when
the same fault occurs 3+ times within a 90-day sliding window.

This is the integration point called by recommendation_service when
a fault becomes a recommendation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.database.repositories.fault_occurrence_repository import (
    DEFAULT_CLUSTER_THRESHOLD,
    DEFAULT_WINDOW_DAYS,
    FaultOccurrenceRepository,
    get_fault_occurrence_repository,
)
from app.models.fault_occurrence import FaultOccurrence

logger = logging.getLogger(__name__)


@dataclass
class ClusterAlert:
    """Cluster alert for systemic fault detection."""

    site_code: str
    equipment_id: str
    issue_type: str
    cluster_count: int
    latest_occurred_at: str


class FaultOccurrenceTracker:
    """Tracks fault occurrences and detects clusters.

    Uses a sliding window (default 90 days) and cluster threshold (default 3)
    to detect when the same fault becomes systemic rather than isolated.
    """

    def __init__(
        self,
        repository: FaultOccurrenceRepository | None = None,
        window_days: int = DEFAULT_WINDOW_DAYS,
        cluster_threshold: int = DEFAULT_CLUSTER_THRESHOLD,
    ):
        """Initialize tracker.

        Args:
            repository: Optional injected repository (default: singleton)
            window_days: Sliding window size (default 90)
            cluster_threshold: Occurrences that trigger cluster alert (default 3)
        """
        self._repo = repository or get_fault_occurrence_repository()
        self._window_days = window_days
        self._cluster_threshold = cluster_threshold

    async def track_fault(
        self,
        site_code: str,
        equipment_id: str,
        issue_type: str,
        recommendation_id: str | None = None,
    ) -> FaultOccurrence:
        """Record a fault occurrence and check for cluster.

        Called when a fault becomes a recommendation in recommendation_service.
        Non-blocking: if tracking fails, logs warning and returns occurrence
        with is_cluster_alert=False.

        Args:
            site_code: Building identifier (e.g., "S002")
            equipment_id: Equipment identifier (e.g., "S002-URINAL-B1-001")
            issue_type: Fault type (e.g., "urinal_blocked", "light_flicker")
            recommendation_id: Associated recommendation ID (optional)

        Returns:
            FaultOccurrence with is_cluster_alert and cluster_count populated
        """
        try:
            occurrence = await self._repo.record_occurrence(
                site_code=site_code,
                equipment_id=equipment_id,
                issue_type=issue_type,
                recommendation_id=recommendation_id,
                window_days=self._window_days,
                cluster_threshold=self._cluster_threshold,
            )
            if occurrence.is_cluster_alert:
                logger.info(
                    "CLUSTER ALERT: %s / %s / %s has %d occurrences (threshold=%d)",
                    site_code,
                    equipment_id,
                    issue_type,
                    occurrence.cluster_count,
                    self._cluster_threshold,
                )
            return occurrence
        except Exception as e:
            logger.warning(
                "Non-blocking fault tracking failed for %s/%s/%s: %s — proceeding without cluster flag",
                site_code,
                equipment_id,
                issue_type,
                e,
            )
            # Return a non-cluster occurrence so pipeline continues
            return FaultOccurrence(
                site_code=site_code,
                equipment_id=equipment_id,
                issue_type=issue_type,
                is_cluster_alert=False,
                cluster_count=0,
            )

    async def check_cluster(
        self,
        site_code: str,
        equipment_id: str,
        issue_type: str,
    ) -> bool:
        """Check if an equipment fault is currently in cluster state.

        Returns True if the equipment has >= cluster_threshold occurrences
        in the sliding window (i.e., cluster alert is active).

        Args:
            site_code: Building identifier
            equipment_id: Equipment identifier
            issue_type: Fault type

        Returns:
            True if cluster alert is active
        """
        try:
            count = await self._repo.get_occurrence_count(
                site_code=site_code,
                equipment_id=equipment_id,
                issue_type=issue_type,
                window_days=self._window_days,
            )
            return count >= self._cluster_threshold
        except Exception as e:
            logger.warning("Cluster check failed for %s/%s/%s: %s", site_code, equipment_id, issue_type, e)
            return False

    async def get_cluster_alerts(self, site_code: str) -> list[ClusterAlert]:
        """Get all active cluster alerts for a site.

        Returns equipment+issue_type pairs with active cluster alerts,
        including the running count and most recent occurrence time.

        Args:
            site_code: Building identifier

        Returns:
            List of ClusterAlert objects
        """
        try:
            alerts = await self._repo.get_cluster_alerts(
                site_code=site_code,
                window_days=self._window_days,
                cluster_threshold=self._cluster_threshold,
            )
            return [
                ClusterAlert(
                    site_code=site_code,
                    equipment_id=a["equipment_id"],
                    issue_type=a["issue_type"],
                    cluster_count=a["cluster_count"],
                    latest_occurred_at=a["latest_occurred_at"],
                )
                for a in alerts
            ]
        except Exception as e:
            logger.error("Failed to get cluster alerts for %s: %s", site_code, e)
            return []

    async def reset_cluster(
        self,
        equipment_id: str,
        issue_type: str,
        site_code: str | None = None,
    ) -> None:
        """Reset cluster alert after it has been acknowledged.

        Args:
            equipment_id: Equipment identifier
            issue_type: Fault type
            site_code: Optional site filter
        """
        try:
            await self._repo.reset_cluster_count(equipment_id, issue_type, site_code)
        except Exception as e:
            logger.error("Failed to reset cluster for %s/%s: %s", equipment_id, issue_type, e)


# Singleton
_fault_occurrence_tracker: FaultOccurrenceTracker | None = None


def get_fault_occurrence_tracker() -> FaultOccurrenceTracker:
    """Get or create FaultOccurrenceTracker singleton."""
    global _fault_occurrence_tracker
    if _fault_occurrence_tracker is None:
        _fault_occurrence_tracker = FaultOccurrenceTracker()
    return _fault_occurrence_tracker
