"""4-milestone SLA service for recommendation workflow.

Handles milestone advancement, deadline computation, breach detection,
and escalation triggering for Fairlands maintenance tickets.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from app.database.repositories.recommendation_repository import get_recommendation_repository
from app.database.repositories.recommendation_sla_repository import get_recommendation_sla_repository
from app.models.recommendation import MilestoneStatus, Recommendation

logger = logging.getLogger(__name__)


# Default SLA hours per milestone when no per-site config exists
DEFAULT_SLA_HOURS: dict[str, int] = {
    "assigned": 24,
    "in_progress": 48,
    "resolved": 72,
    "verified": 168,
}

# Escalation thresholds (% of SLA elapsed before alert fires)
ESCALATION_THRESHOLDS = [0.50, 0.75, 0.90, 1.0]


class RecommendationMilestoneService:
    """Service for managing recommendation 4-milestone SLA lifecycle."""

    def __init__(self):
        self._sla_repo = None
        self._rec_repo = None

    @property
    def sla_repo(self):
        if self._sla_repo is None:
            self._sla_repo = get_recommendation_sla_repository()
        return self._sla_repo

    @property
    def rec_repo(self):
        if self._rec_repo is None:
            self._rec_repo = get_recommendation_repository()
        return self._rec_repo

    # --- Milestone advancement ---

    async def advance_milestone(
        self,
        recommendation_id: str,
        new_status: MilestoneStatus,
        *,
        by_user: str | None = None,
    ) -> Recommendation:
        """Advance a recommendation to the next milestone.

        Updates milestone_status, sets the corresponding timestamp,
        and recalculates sla_deadline_at from the SLA config.
        """
        rec = await self.rec_repo.get(recommendation_id)
        if not rec:
            raise ValueError(f"Recommendation {recommendation_id} not found")

        now = datetime.now(UTC)
        prev_status = rec.milestone_status

        # Update status and timestamp
        rec.milestone_status = new_status
        if new_status == MilestoneStatus.IN_PROGRESS:
            rec.in_progress_at = now
        elif new_status == MilestoneStatus.RESOLVED:
            rec.resolved_at = now
        elif new_status == MilestoneStatus.VERIFIED:
            rec.verified_at = now

        # Compute new sla_deadline_at from SLA term config
        sla_deadline = await self._compute_deadline(rec)
        rec.sla_deadline_at = sla_deadline

        updated = await self.rec_repo.update(recommendation_id, rec)
        logger.info(
            "Milestone advanced for %s: %s → %s (deadline=%s)",
            recommendation_id,
            prev_status.value,
            new_status.value,
            sla_deadline,
        )
        return updated

    async def _compute_deadline(self, rec: Recommendation) -> datetime | None:
        """Compute sla_deadline_at based on current milestone + SLA config.

        Uses per-site per-milestone deadline_hours from RecommendationSLATerm.
        Falls back to DEFAULT_SLA_HOURS if no config exists.
        """
        milestone_key = rec.milestone_status.value
        if rec.milestone_status == MilestoneStatus.VERIFIED:
            return None  # No deadline for verified (complete) milestone

        # Get milestone start time (timestamp when this milestone began)
        milestone_start = self._get_milestone_start(rec)
        if not milestone_start:
            milestone_start = datetime.now(UTC)

        # Look up SLA hours for this site + milestone
        hours = DEFAULT_SLA_HOURS.get(milestone_key, 24)
        try:
            sla_term = await self.sla_repo.get_by_site_milestone(rec.site_id, rec.milestone_status)
            if sla_term:
                hours = sla_term.deadline_hours
        except Exception as e:
            logger.debug("No SLA term found for %s/%s, using default %dh: %s", rec.site_id, milestone_key, hours, e)

        deadline = milestone_start + timedelta(hours=hours)
        return deadline

    def _get_milestone_start(self, rec: Recommendation) -> datetime | None:
        """Return the timestamp when the current milestone began."""
        if rec.milestone_status == MilestoneStatus.ASSIGNED:
            return rec.assigned_at
        if rec.milestone_status == MilestoneStatus.IN_PROGRESS:
            return rec.in_progress_at
        if rec.milestone_status == MilestoneStatus.RESOLVED:
            return rec.resolved_at
        if rec.milestone_status == MilestoneStatus.VERIFIED:
            return rec.verified_at
        return rec.assigned_at

    # --- Breach detection ---

    async def check_breaches(self) -> list[dict[str, Any]]:
        """Find all recommendations past their SLA deadline.

        Returns list of dicts with recommendation + breach details.
        Used by BackgroundScheduler every 5 minutes.
        """
        now = datetime.now(UTC)
        breached = []

        try:
            # Fetch recommendations with past sla_deadline_at that aren't verified
            recs = await self._get_active_recommendations()
            for rec in recs:
                if rec.sla_deadline_at and rec.sla_deadline_at < now:
                    if rec.milestone_status != MilestoneStatus.VERIFIED:
                        pct = self._elapsed_pct(rec)
                        breached.append(
                            {
                                "recommendation": rec,
                                "breach_minutes": int((now - rec.sla_deadline_at).total_seconds() / 60),
                                "elapsed_pct": round(pct, 3),
                                "milestone": rec.milestone_status.value,
                            }
                        )
        except Exception as e:
            logger.error("Breach check failed: %s", e)

        return breached

    async def _get_active_recommendations(self) -> list[Recommendation]:
        """Fetch all non-verified recommendations for breach checking."""
        # We filter in-memory for now; Supabase index on sla_deadline_at makes this efficient
        if not self.rec_repo.client:
            return []
        try:
            result = (
                self.rec_repo.client.table("recommendations")
                .select("*")
                .neq("milestone_status", "verified")
                .not_.is_("sla_deadline_at", "null")
                .execute()
            )
            return [Recommendation.from_dict(row) for row in (result.data or [])]
        except Exception as e:
            logger.error("Active recommendations fetch failed: %s", e)
            return []

    def _elapsed_pct(self, rec: Recommendation) -> float:
        """Compute % of SLA time elapsed for the current milestone."""
        start = self._get_milestone_start(rec)
        if not start or not rec.sla_deadline_at:
            return 0.0
        total = (rec.sla_deadline_at - start).total_seconds()
        if total <= 0:
            return 1.0
        elapsed = (datetime.now(UTC) - start).total_seconds()
        return min(elapsed / total, 2.0)  # Cap at 200%

    # --- Escalation ---

    async def escalate_breach(self, recommendation_id: str, breach_info: dict[str, Any]) -> None:
        """Trigger escalation for a breached recommendation.

        Checks 50/75/90% thresholds and fires Sentry alerts via existing
        notifier infrastructure (SystemNotifier → Telegram dispatch).
        """
        rec = breach_info.get("recommendation")
        if not rec:
            rec = await self.rec_repo.get(recommendation_id)
        if not rec:
            return

        pct = breach_info.get("elapsed_pct", self._elapsed_pct(rec))

        # Determine escalation tier
        tier = self._escalation_tier(pct)
        if not tier:
            return  # Already escalated at this tier

        logger.warning(
            "SLA breach: rec=%s milestone=%s elapsed=%.0f%% tier=%s",
            recommendation_id,
            rec.milestone_status.value,
            pct * 100,
            tier,
        )

        # Fire escalation via Sentry
        try:
            await self._send_sentry_alert(rec, pct, tier)
        except Exception as e:
            logger.error("Sentry escalation failed for %s: %s", recommendation_id, e)

    def _escalation_tier(self, elapsed_pct: float) -> str | None:
        """Map elapsed % to escalation tier name."""
        if elapsed_pct >= 1.0:
            return "breach"
        if elapsed_pct >= 0.90:
            return "critical"
        if elapsed_pct >= 0.75:
            return "warning"
        if elapsed_pct >= 0.50:
            return "notice"
        return None

    async def _send_sentry_alert(self, rec: Recommendation, elapsed_pct: float, tier: str) -> None:
        """Send Sentry alert via SystemNotifier Telegram dispatch."""
        try:
            from app.services.system_notifier import SystemNotifier

            notifier = SystemNotifier()
            site_label = rec.site_id or "unknown"
            milestone = rec.milestone_status.value
            msg = (
                f"[{tier.upper()}] SLA {milestone} breached — "
                f"{site_label} | rec={rec.id[:8]} | {elapsed_pct * 100:.0f}% elapsed"
            )
            await notifier.send_telegram_alert(
                message=msg,
                alert_type="sla_breach",
                site_code=site_label,
            )
        except Exception as e:
            logger.debug("Telegram notifier unavailable: %s", e)

    # --- Convenience helpers ---

    async def get_sla_status(self, recommendation_id: str) -> dict[str, Any]:
        """Return SLA status summary for a recommendation."""
        rec = await self.rec_repo.get(recommendation_id)
        if not rec:
            return {}

        pct = self._elapsed_pct(rec) if rec.sla_deadline_at else 0.0
        return {
            "id": rec.id,
            "milestone_status": rec.milestone_status.value,
            "sla_deadline_at": rec.sla_deadline_at.isoformat() if rec.sla_deadline_at else None,
            "elapsed_pct": round(pct, 3),
            "is_breached": rec.sla_deadline_at and rec.sla_deadline_at < datetime.now(UTC),
            "is_verified": rec.milestone_status == MilestoneStatus.VERIFIED,
        }


_service: RecommendationMilestoneService | None = None


def get_recommendation_milestone_service() -> RecommendationMilestoneService:
    global _service
    if _service is None:
        _service = RecommendationMilestoneService()
    return _service
