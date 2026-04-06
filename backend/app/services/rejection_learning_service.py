"""Rejection learning service for learning from rejected recommendations.

Detects patterns in rejected recommendations and creates equipment constraints
to prevent similar future rejections.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.database.repositories.rejection_repository import RejectionRepository
from app.models.recommendation import Recommendation
from app.services.profile_service import get_profile_service
from app.services.recommendation_service import get_recommendation_service

logger = logging.getLogger(__name__)


@dataclass
class RejectionRecord:
    """Record of a rejected recommendation.

    Fields:
        recommendation_id: ID of rejected recommendation
        site_id: Building identifier
        action_type: Type of action that was rejected
        target_equipment: Equipment ID that was targeted
        reason: Reason operator provided for rejection
        rejected_at: Timestamp of rejection
    """

    recommendation_id: str
    site_id: str
    action_type: str
    target_equipment: str
    reason: str
    rejected_at: datetime

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for JSON storage."""
        return {
            "recommendation_id": self.recommendation_id,
            "site_id": self.site_id,
            "action_type": self.action_type,
            "target_equipment": self.target_equipment,
            "reason": self.reason,
            "rejected_at": self.rejected_at.isoformat() if isinstance(self.rejected_at, datetime) else self.rejected_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RejectionRecord":
        """Deserialize from dictionary."""
        rejected_at = data.get("rejected_at")
        if isinstance(rejected_at, str):
            try:
                rejected_at = datetime.fromisoformat(rejected_at)
            except (ValueError, TypeError):
                rejected_at = datetime.utcnow()
        else:
            rejected_at = datetime.utcnow()

        return cls(
            recommendation_id=data.get("recommendation_id", ""),
            site_id=data.get("site_id", ""),
            action_type=data.get("action_type", ""),
            target_equipment=data.get("target_equipment", ""),
            reason=data.get("reason", ""),
            rejected_at=rejected_at,
        )


@dataclass
class EquipmentConstraint:
    """Constraint learned from rejection patterns.

    Prevents similar rejected actions from being recommended again.

    Fields:
        site_id: Building identifier
        zone_id: Zone or equipment group (e.g., "Floor 3", "all")
        constraint_type: Type of constraint (min_setpoint, max_power, etc.)
        value: Constraint value
        reason: Why constraint was created
        created_at: Timestamp of constraint creation
    """

    site_id: str
    zone_id: str
    constraint_type: str
    value: float
    reason: str
    created_at: datetime

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for JSON storage."""
        return {
            "site_id": self.site_id,
            "zone_id": self.zone_id,
            "constraint_type": self.constraint_type,
            "value": self.value,
            "reason": self.reason,
            "created_at": self.created_at.isoformat() if isinstance(self.created_at, datetime) else self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EquipmentConstraint":
        """Deserialize from dictionary."""
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            try:
                created_at = datetime.fromisoformat(created_at)
            except (ValueError, TypeError):
                created_at = datetime.utcnow()
        else:
            created_at = datetime.utcnow()

        return cls(
            site_id=data.get("site_id", ""),
            zone_id=data.get("zone_id", ""),
            constraint_type=data.get("constraint_type", ""),
            value=float(data.get("value", 0.0)),
            reason=data.get("reason", ""),
            created_at=created_at,
        )


class RejectionLearningService:
    """Learn from rejected recommendations to improve constraints.

    Detects patterns when same type of recommendation is rejected 3+ times,
    then creates equipment constraints to prevent similar future recommendations.
    """

    def __init__(self):
        """Initialize RejectionLearningService."""
        self.profile_service = get_profile_service()
        self.recommendation_service = get_recommendation_service()
        self.repo = RejectionRepository()

    async def process_rejection(self, rec: Recommendation, reason: str) -> None:
        """Learn from rejected recommendation.

        Pattern detection: 3+ rejections of same type in 30 days
        → Add zone constraint to prevent similar recommendations

        Args:
            rec: Rejected recommendation
            reason: Reason for rejection
        """
        try:
            # Record rejection
            rejection = RejectionRecord(
                recommendation_id=rec.id,
                site_id=rec.site_id,
                action_type=rec.action_type,
                target_equipment=rec.target_equipment,
                reason=reason,
                rejected_at=datetime.utcnow(),
            )

            await self.repo.create(rejection)

            logger.info(f"Recorded rejection for {rec.action_type} on {rec.target_equipment}: {reason}")

            # Check for pattern: 3+ rejections in 30 days
            recent_rejections = await self.repo.get_recent(rec.site_id, rec.action_type, days=30)

            logger.info(f"Found {len(recent_rejections)} rejections for {rec.action_type} in past 30 days")

            if len(recent_rejections) >= 3:
                logger.info(f"Pattern detected! Adding constraint after {len(recent_rejections)} rejections")
                # Pattern detected - add constraint
                await self._add_action_constraint(rec, recent_rejections)

        except Exception as e:
            logger.error(f"Error processing rejection: {e}")

    async def _add_action_constraint(self, rec: Recommendation, recent_rejections: list[RejectionRecord]) -> None:
        """Add constraint to prevent similar rejected actions.

        Example: 3 rejections of "lower setpoint below 22°C on Floor 3"
        → Add constraint: min_setpoint = 22.0 on Floor 3

        Args:
            rec: Current rejected recommendation
            recent_rejections: List of recent rejection records for same action type
        """
        try:
            site_id = rec.site_id

            # Parse rejection patterns
            if "setpoint" in rec.action_type.lower():
                # Extract zone from target equipment
                zone_id = rec.target_equipment.split(":")[0] if ":" in rec.target_equipment else "all"

                # Find the setpoint value being rejected
                rejected_value = rec.action.get("value")

                # Add constraint: don't recommend values at or below this
                constraint = EquipmentConstraint(
                    site_id=site_id,
                    zone_id=zone_id,
                    constraint_type="min_setpoint",
                    value=rejected_value,
                    reason=f"Operator rejected {len(recent_rejections)} similar actions",
                    created_at=datetime.utcnow(),
                )

                await self._save_constraint(site_id, constraint)

                logger.info(
                    f"Added constraint: min_setpoint={rejected_value} for {zone_id} "
                    f"({len(recent_rejections)} rejections)"
                )

        except Exception as e:
            logger.error(f"Error adding action constraint: {e}")

    async def _save_constraint(self, site_id: str, constraint: EquipmentConstraint) -> None:
        """Save constraint to site profile.

        Args:
            site_id: Site ID
            constraint: Equipment constraint to save
        """
        try:
            config = self.profile_service.load_site_profile_config(site_id)

            if not config:
                logger.warning(f"No profile config found for site {site_id}")
                return

            if not hasattr(config, "constraints") or not config.constraints:
                config.constraints = []

            config.constraints.append(constraint)

            await self.profile_service.save_site_profile_config(site_id, config)

            logger.info(f"Saved constraint to profile for site {site_id}")

        except Exception as e:
            logger.error(f"Error saving constraint: {e}")


# Singleton instance
_rejection_learning_service: RejectionLearningService | None = None


def get_rejection_learning_service() -> RejectionLearningService:
    """Get or create RejectionLearningService singleton.

    Returns:
        RejectionLearningService instance
    """
    global _rejection_learning_service
    if _rejection_learning_service is None:
        _rejection_learning_service = RejectionLearningService()
    return _rejection_learning_service
