"""Per-site per-milestone SLA deadline configuration.

Stores the SLA hour budget for each milestone of each site.
Used by RecommendationMilestoneService to compute sla_deadline_at on advance.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class MilestoneStatus(StrEnum):
    """4-milestone SLA lifecycle for Fairlands maintenance tickets."""

    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    VERIFIED = "verified"


@dataclass
class RecommendationSLATerm:
    """SLA deadline configuration for a site + milestone combination.

    Defines how many hours are allowed for each milestone before escalation fires.
    Stored in the canonical JSON store (Supabase primary, JSON fallback).
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    site_code: str = ""  # e.g. "site-002" (Fairlands)
    milestone: MilestoneStatus = MilestoneStatus.ASSIGNED
    deadline_hours: int = 24  # Hours allowed for this milestone
    escalation_template: str | None = None  # Template name for breach escalation
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "site_code": self.site_code,
            "milestone": self.milestone.value if isinstance(self.milestone, MilestoneStatus) else self.milestone,
            "deadline_hours": self.deadline_hours,
            "escalation_template": self.escalation_template,
            "created_at": self.created_at.isoformat() if isinstance(self.created_at, datetime) else self.created_at,
            "updated_at": self.updated_at.isoformat() if isinstance(self.updated_at, datetime) else self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RecommendationSLATerm":
        milestone = data.get("milestone", "assigned")
        if isinstance(milestone, str):
            try:
                milestone = MilestoneStatus(milestone)
            except ValueError:
                milestone = MilestoneStatus.ASSIGNED

        def _parse_ts(key: str) -> datetime | None:
            val = data.get(key)
            if isinstance(val, str) and val:
                try:
                    return datetime.fromisoformat(val)
                except (ValueError, TypeError):
                    return None
            return val

        return cls(
            id=data.get("id", str(uuid.uuid4())),
            site_code=data.get("site_code", ""),
            milestone=milestone,
            deadline_hours=int(data.get("deadline_hours", 24)),
            escalation_template=data.get("escalation_template"),
            created_at=_parse_ts("created_at") or datetime.utcnow(),
            updated_at=_parse_ts("updated_at") or datetime.utcnow(),
        )
