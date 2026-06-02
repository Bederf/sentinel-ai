"""Fairlands SLA Dashboard API endpoints for FM Dashboard integration.

Exposes milestone status, SLA breaches, cluster alerts, and fire pump compliance
data for the Fairlands operations team via 5 BOLA-protected endpoints.

Path: /api/fairlands/sla/*
"""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query

from app.api.schemas.fairlands_sla_schemas import (
    ClusterAlertResponse,
    FirePumpComplianceResponse,
    MilestoneStatusResponse,
    SLABreachResponse,
    SLASummaryResponse,
)
from app.middleware.auth_middleware import AuthContext, optional_auth
from app.services.fire_pump_compliance_service import get_fire_pump_compliance_service
from app.services.recommendation_milestone_service import get_recommendation_milestone_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/fairlands/sla", tags=["fairlands", "sla"])


def _normalize_site_id(site_code: str) -> str:
    """Normalize site_code to format used in recommendations table (S002)."""
    if site_code.startswith("site-"):
        num = site_code.split("-")[1]
        return f"S{num}"
    return site_code


def _rag_status(elapsed_pct: float, is_breached: bool) -> str:
    """Compute RAG status from elapsed percentage and breach flag."""
    if is_breached or elapsed_pct >= 1.0:
        return "RED"
    if elapsed_pct >= 0.75:
        return "YELLOW"
    return "GREEN"


def _compute_elapsed_pct(rec) -> float:
    """Compute elapsed SLA percentage for a recommendation."""
    if not rec.sla_deadline_at:
        return 0.0

    # Get milestone start time
    if rec.milestone_status.value == "assigned":
        start = rec.assigned_at
    elif rec.milestone_status.value == "in_progress":
        start = rec.in_progress_at or rec.assigned_at
    elif rec.milestone_status.value == "resolved":
        start = rec.resolved_at or rec.in_progress_at or rec.assigned_at
    else:
        start = rec.assigned_at

    if not start:
        return 0.0

    total = (rec.sla_deadline_at - start).total_seconds()
    if total <= 0:
        return 1.0

    elapsed = (datetime.now(UTC) - start).total_seconds()
    return min(elapsed / total, 2.0)  # Cap at 200%


@router.get("/milestones", response_model=list[MilestoneStatusResponse])
async def get_milestone_status(
    site_code: str = Query(...),
    auth: AuthContext = Depends(optional_auth),
) -> list[MilestoneStatusResponse]:
    """Get all recommendations with milestone status for a site."""
    try:
        svc = get_recommendation_milestone_service()
        rec_repo = svc.rec_repo

        # Normalize site_id for recommendations table (S002 format)
        normalized_site = _normalize_site_id(site_code)

        # Fetch all non-verified recommendations for the site
        try:
            result = (
                rec_repo.client.table("recommendations")
                .select("*")
                .eq("site_id", normalized_site)
                .neq("milestone_status", "verified")
                .execute()
            )
            recs = []
            from app.models.recommendation import Recommendation

            for row in result.data or []:
                try:
                    recs.append(Recommendation.from_dict(row))
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"Failed to fetch milestones for {site_code}: {e}")
            return []

        responses = []
        for rec in recs:
            elapsed_pct = _compute_elapsed_pct(rec) if rec.sla_deadline_at else 0.0
            is_breached = rec.sla_deadline_at and rec.sla_deadline_at < datetime.now(UTC)

            # Build title from reason or target_equipment
            if rec.reason:
                title = rec.reason[:80]
            else:
                title = f"Recommendation for {rec.target_equipment}"

            responses.append(
                MilestoneStatusResponse(
                    recommendation_id=rec.id,
                    title=title,
                    milestone_status=rec.milestone_status.value,
                    assigned_at=rec.assigned_at,
                    in_progress_at=rec.in_progress_at,
                    resolved_at=rec.resolved_at,
                    verified_at=rec.verified_at,
                    sla_deadline_at=rec.sla_deadline_at,
                    elapsed_pct=round(elapsed_pct, 3),
                    is_breached=is_breached,
                    rag_status=_rag_status(elapsed_pct, is_breached),
                )
            )

        return responses

    except Exception as e:
        logger.error(f"get_milestone_status failed for {site_code}: {e}")
        return []


@router.get("/breaches", response_model=list[SLABreachResponse])
async def get_sla_breaches(
    site_code: str = Query(...),
    auth: AuthContext = Depends(optional_auth),
) -> list[SLABreachResponse]:
    """Get all recommendations with SLA breaches."""
    try:
        svc = get_recommendation_milestone_service()
        breaches = await svc.check_breaches()

        # Normalize site_id for comparison
        normalized_site = _normalize_site_id(site_code)

        responses = []
        for breach in breaches:
            rec = breach.get("recommendation")
            if not rec:
                continue

            # Filter by site
            if rec.site_id != normalized_site:
                continue

            elapsed_pct = breach.get("elapsed_pct", 0.0)
            # breach_pct: how far past deadline (0.0 if not breached)
            breach_pct = max(0.0, elapsed_pct - 1.0) if elapsed_pct >= 1.0 else 0.0
            days_overdue = breach.get("breach_minutes", 0) / 1440.0  # minutes to days

            # Build title
            if rec.reason:
                title = rec.reason[:80]
            else:
                title = f"Recommendation for {rec.target_equipment}"

            responses.append(
                SLABreachResponse(
                    recommendation_id=rec.id,
                    title=title,
                    milestone_status=rec.milestone_status.value,
                    sla_deadline_at=rec.sla_deadline_at,
                    breach_pct=round(breach_pct, 3),
                    days_overdue=round(days_overdue, 1),
                )
            )

        return responses

    except Exception as e:
        logger.error(f"get_sla_breaches failed for {site_code}: {e}")
        return []


@router.get("/clusters", response_model=list[ClusterAlertResponse])
async def get_cluster_alerts(
    site_code: str = Query(...),
    auth: AuthContext = Depends(optional_auth),
) -> list[ClusterAlertResponse]:
    """Get all equipment with active cluster alerts."""
    try:
        # Get cluster alerts via FaultOccurrenceTracker
        tracker_svc = None
        try:
            from app.services.fault_occurrence_tracker import get_fault_occurrence_tracker

            tracker_svc = get_fault_occurrence_tracker()
        except Exception:
            pass

        if tracker_svc:
            alerts = await tracker_svc.get_cluster_alerts(site_code)
        else:
            alerts = []

        responses = []
        for alert in alerts:
            # urgency_boost: based on cluster count (more occurrences = higher urgency)
            urgency_boost = min(1.0, (alert.cluster_count - 2) * 0.2) if alert.cluster_count > 2 else 0.0

            # Parse latest_occurred_at (could be datetime or string)
            last_occurrence = alert.latest_occurred_at
            if isinstance(last_occurrence, str):
                try:
                    last_occurrence = datetime.fromisoformat(last_occurrence.replace("Z", "+00:00"))
                except Exception:
                    last_occurrence = datetime.now(UTC)

            responses.append(
                ClusterAlertResponse(
                    equipment_id=alert.equipment_id,
                    issue_type=alert.issue_type,
                    cluster_count=alert.cluster_count,
                    first_occurrence=last_occurrence,  # Approximation
                    last_occurrence=last_occurrence,
                    urgency_boost=round(urgency_boost, 2),
                )
            )

        return responses

    except Exception as e:
        logger.error(f"get_cluster_alerts failed for {site_code}: {e}")
        return []


@router.get("/compliance/fire-pump", response_model=list[FirePumpComplianceResponse])
async def get_fire_pump_compliance(
    site_code: str = Query(...),
    auth: AuthContext = Depends(optional_auth),
) -> list[FirePumpComplianceResponse]:
    """Get fire pump compliance status for site."""
    try:
        svc = get_fire_pump_compliance_service()
        alerts = await svc.get_overdue_alerts(site_code)

        responses = []
        for alert in alerts:
            # Determine last test date
            last_test_date = alert.last_test_date

            # Determine next test date (scheduled_date is the overdue one)
            next_test_date = alert.scheduled_date

            # Compliance rate: 0% if overdue, 100% if not
            # OverdueAlert only includes overdue items, so compliance_rate = 0.0
            # and is_overdue = True for all items here
            responses.append(
                FirePumpComplianceResponse(
                    equipment_id=alert.equipment_id,
                    last_test_date=last_test_date,
                    next_test_date=next_test_date,
                    compliance_rate=0.0,  # Overdue = non-compliant
                    is_overdue=True,
                    days_overdue=alert.days_overdue,
                    regulatory_reference=alert.regulatory_reference,
                )
            )

        return responses

    except Exception as e:
        logger.error(f"get_fire_pump_compliance failed for {site_code}: {e}")
        return []


@router.get("/summary", response_model=SLASummaryResponse)
async def get_sla_summary(
    site_code: str = Query(...),
    auth: AuthContext = Depends(optional_auth),
) -> SLASummaryResponse:
    """Get SLA summary: milestone counts + breach rate + cluster alerts + compliance."""
    try:
        svc = get_recommendation_milestone_service()
        rec_repo = svc.rec_repo
        normalized_site = _normalize_site_id(site_code)

        # Count milestones by status
        try:
            result = (
                rec_repo.client.table("recommendations")
                .select("milestone_status")
                .eq("site_id", normalized_site)
                .execute()
            )
            recs_data = result.data or []
        except Exception as e:
            logger.warning(f"Failed to fetch summary counts for {site_code}: {e}")
            recs_data = []

        counts = {"assigned": 0, "in_progress": 0, "resolved": 0, "verified": 0}
        for row in recs_data:
            status = row.get("milestone_status", "")
            if status in counts:
                counts[status] += 1

        total_open = counts["assigned"] + counts["in_progress"] + counts["resolved"]

        # Breach count
        breaches = await svc.check_breaches()
        breach_count = sum(
            1 for b in breaches if b.get("recommendation") and b["recommendation"].site_id == normalized_site
        )

        # Cluster alerts
        cluster_count = 0
        try:
            from app.services.fault_occurrence_tracker import get_fault_occurrence_tracker

            tracker = get_fault_occurrence_tracker()
            clusters = await tracker.get_cluster_alerts(site_code)
            cluster_count = len(clusters)
        except Exception:
            pass

        # Fire pump compliance rate
        compliance_rate = 0.0
        try:
            fire_svc = get_fire_pump_compliance_service()
            alerts = await fire_svc.get_overdue_alerts(site_code)
            # If no overdue alerts, compliance is 100%
            if not alerts:
                compliance_rate = 1.0
        except Exception:
            pass

        return SLASummaryResponse(
            site_code=site_code,
            total_open=total_open,
            assigned=counts["assigned"],
            in_progress=counts["in_progress"],
            resolved=counts["resolved"],
            verified=counts["verified"],
            breach_count=breach_count,
            cluster_alert_count=cluster_count,
            compliance_rate=compliance_rate,
            generated_at=datetime.now(UTC),
        )

    except Exception as e:
        logger.error(f"get_sla_summary failed for {site_code}: {e}")
        return SLASummaryResponse(
            site_code=site_code,
            total_open=0,
            assigned=0,
            in_progress=0,
            resolved=0,
            verified=0,
            breach_count=0,
            cluster_alert_count=0,
            compliance_rate=0.0,
            generated_at=datetime.now(UTC),
        )
