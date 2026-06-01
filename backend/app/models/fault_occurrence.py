"""FaultOccurrence model for tracking repeated faults and cluster detection.

Tracks equipment fault occurrences within a sliding window to detect systemic
issues (cluster alerts) when the same fault happens 3+ times in 90 days.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class FaultOccurrence:
    """Records a single fault occurrence on equipment.

    Used for cluster detection — when the same equipment has 3+ occurrences
    of the same issue_type within a sliding window, a cluster alert is raised.

    Fields:
        id: Unique identifier (UUID)
        site_code: Building identifier (e.g., "S002")
        equipment_id: Equipment identifier (e.g., "S002-URINAL-B1-001")
        issue_type: Fault type (e.g., "urinal_blocked", "light_flicker")
        occurred_at: When the fault occurred (UTC)
        recommendation_id: Associated recommendation (if created)
        is_cluster_alert: True if this occurrence triggered cluster detection
        cluster_count: Running count of occurrences in the current window
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    site_code: str = ""
    equipment_id: str = ""
    issue_type: str = ""
    occurred_at: datetime = field(default_factory=datetime.utcnow)
    recommendation_id: str | None = None
    is_cluster_alert: bool = False
    cluster_count: int = 1

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for JSON storage."""
        return {
            "id": self.id,
            "site_code": self.site_code,
            "equipment_id": self.equipment_id,
            "issue_type": self.issue_type,
            "occurred_at": (
                self.occurred_at.isoformat() if isinstance(self.occurred_at, datetime) else self.occurred_at
            ),
            "recommendation_id": self.recommendation_id,
            "is_cluster_alert": self.is_cluster_alert,
            "cluster_count": self.cluster_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FaultOccurrence:
        """Deserialize from dict."""
        occurred_at = data.get("occurred_at", "")
        if isinstance(occurred_at, str) and occurred_at:
            try:
                occurred_at = datetime.fromisoformat(occurred_at)
            except (ValueError, TypeError):
                occurred_at = datetime.utcnow()
        else:
            occurred_at = datetime.utcnow()

        return cls(
            id=data.get("id", str(uuid.uuid4())),
            site_code=data.get("site_code", ""),
            equipment_id=data.get("equipment_id", ""),
            issue_type=data.get("issue_type", ""),
            occurred_at=occurred_at,
            recommendation_id=data.get("recommendation_id"),
            is_cluster_alert=data.get("is_cluster_alert", False),
            cluster_count=data.get("cluster_count", 1),
        )
