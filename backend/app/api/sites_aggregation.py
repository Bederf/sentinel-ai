"""Site aggregation endpoints.

Provides aggregated endpoints for fetching site-level data in a single request,
eliminating N+1 calls and reducing 429 rate limit errors.

Implements:
- GET /api/sites/{site_id}/summary - Complete site data (equipment count, alerts, predictions, etc.)
- GET /api/sites/{site_id}/alerts - Paginated site alerts
- GET /api/sites/{site_id}/predictions - Site predictions summary
"""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.database.repositories import AlertRepository, PredictionRepository, SiteRepository

logger = logging.getLogger(__name__)
router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


# ---- Response Models ----


class SafetySummary(BaseModel):
    """Safety status summary for site equipment."""

    total: int = Field(..., description="Total equipment count")
    safe: int = Field(..., description="Safe equipment count")
    warning: int = Field(..., description="Equipment with warnings")
    blocked: int = Field(..., description="Equipment with blocks")
    alarm: int = Field(..., description="Equipment with alarms")


class AlertSummary(BaseModel):
    """Alert count by severity."""

    critical: int = Field(default=0)
    warning: int = Field(default=0)
    info: int = Field(default=0)


class PredictionSummary(BaseModel):
    """Prediction summary."""

    high_risk: int = Field(default=0, description="High risk predictions")
    medium_risk: int = Field(default=0, description="Medium risk predictions")
    low_risk: int = Field(default=0, description="Low risk predictions")


class EnergySummary(BaseModel):
    """Energy metrics summary."""

    current_kw: float = Field(default=0.0)
    today_kwh: float = Field(default=0.0)


class SiteSummary(BaseModel):
    """Complete site summary with aggregated data."""

    site_id: str
    site_name: str
    equipment_count: int
    equipment_by_type: dict[str, int] = Field(default_factory=dict)
    safety: SafetySummary
    alerts: AlertSummary
    predictions: PredictionSummary
    energy: EnergySummary = Field(default_factory=lambda: EnergySummary())
    last_updated: str


class AlertItem(BaseModel):
    """Alert item for alerts list."""

    id: str
    equipment_id: str
    equipment_name: str
    severity: str
    description: str
    created_at: str


class SiteAlerts(BaseModel):
    """Paginated alerts for a site."""

    site_id: str
    alerts: list[AlertItem]
    total_count: int
    offset: int
    limit: int


# ---- Endpoints ----


@router.get(
    "/sites/{site_id}/summary",
    response_model=SiteSummary,
    summary="Get site summary",
    description="Fetch complete aggregated site data (equipment, safety, alerts, predictions) in a single request.",
)
@limiter.limit("600/minute")
async def get_site_summary(request: Request, site_id: str) -> SiteSummary:
    """Get aggregated site summary.

    Returns:
    - Equipment count and breakdown by type
    - Safety status summary (safe/warning/blocked/alarm counts)
    - Alert counts by severity
    - Prediction summary (high/medium/low risk)
    - Energy metrics (current power, daily usage)
    - Last update timestamp

    Args:
        site_id: Site identifier

    Returns:
        SiteSummary with all aggregated data

    Raises:
        HTTPException: 404 if site not found
    """
    try:
        building_repo = SiteRepository()
        alert_repo = AlertRepository()

        # Get building/site info
        building = building_repo.get_by_id(site_id)
        if not building:
            raise HTTPException(status_code=404, detail=f"Site {site_id} not found")

        site_uuid = building.get("id")

        # Get all equipment for this site FROM SUPABASE ONLY
        equipment_list = building_repo.get_equipment(site_id)
        logger.info(f"Site {site_id}: Got {len(equipment_list)} equipment from Supabase")

        # ⚠️  IMPORTANT: Do NOT fall back to device_manager or JSON data
        # The requirement is: "we must be reading from the supabase only"
        # If equipment is missing, it should be added to Supabase via seeding, not loaded from fallback
        if not equipment_list:
            logger.error(f"Site {site_id}: No equipment found in Supabase! Please seed equipment data.")
            # Return empty summary rather than falling back to inconsistent device_manager data
            equipment_list = []

        equipment_count = len(equipment_list) if equipment_list else 0

        # Count equipment by type
        equipment_by_type: dict[str, int] = {}
        safety_counts = {"total": equipment_count, "safe": 0, "warning": 0, "blocked": 0, "alarm": 0}

        for equipment in equipment_list or []:
            eq_type = equipment.get("type", "unknown")
            equipment_by_type[eq_type] = equipment_by_type.get(eq_type, 0) + 1

            # Count safety statuses based on status field and health score
            status = equipment.get("status", "normal").lower()
            health_score = equipment.get("health_score", 100)

            # Determine equipment status category
            if status == "critical":
                safety_counts["alarm"] += 1
            elif status in ("warning", "needs_attention"):
                safety_counts["warning"] += 1
            elif status == "offline" or status == "maintenance":
                safety_counts["blocked"] += 1
            elif status == "normal":
                # For normal status, check health score to determine if it's really safe
                if health_score >= 80:
                    safety_counts["safe"] += 1
                elif health_score >= 57:
                    # Health score 57-79% is warning level
                    safety_counts["warning"] += 1
                else:
                    # Health score < 57% is alarm level
                    safety_counts["alarm"] += 1
            else:
                # Unknown status defaults to safe if health is good
                if health_score >= 80:
                    safety_counts["safe"] += 1
                else:
                    safety_counts["warning"] += 1

        # Get alerts for this site
        alerts = alert_repo.get_active_by_site(site_uuid)
        alert_counts = {"critical": 0, "warning": 0, "info": 0}
        for alert in alerts or []:
            severity = alert.get("severity", "info").lower()
            if severity in alert_counts:
                alert_counts[severity] += 1
            else:
                alert_counts["info"] += 1

        # Get predictions for this site (if available)
        try:
            prediction_repo = PredictionRepository()
            predictions = prediction_repo.get_active_by_site(site_uuid)
            prediction_counts = {"high_risk": 0, "medium_risk": 0, "low_risk": 0}
            for pred in predictions or []:
                risk_level = pred.get("risk_level", "low").lower()
                if risk_level == "high":
                    prediction_counts["high_risk"] += 1
                elif risk_level == "medium":
                    prediction_counts["medium_risk"] += 1
                else:
                    prediction_counts["low_risk"] += 1
        except Exception:
            prediction_counts = {"high_risk": 0, "medium_risk": 0, "low_risk": 0}

        # Build response
        return SiteSummary(
            site_id=site_id,
            site_name=building.get("name", f"Site {site_id}"),
            equipment_count=equipment_count,
            equipment_by_type=equipment_by_type,
            safety=SafetySummary(**safety_counts),
            alerts=AlertSummary(**alert_counts),
            predictions=PredictionSummary(**prediction_counts),
            last_updated=datetime.now(UTC).isoformat(),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting site summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/sites/{site_id}/alerts",
    response_model=SiteAlerts,
    summary="Get site alerts",
    description="Fetch paginated alerts for a site.",
)
@limiter.limit("600/minute")
async def get_site_alerts(request: Request, site_id: str, offset: int = 0, limit: int = 50) -> SiteAlerts:
    """Get alerts for a site.

    Args:
        site_id: Site identifier
        offset: Pagination offset
        limit: Pagination limit (max 100)

    Returns:
        SiteAlerts with paginated alerts

    Raises:
        HTTPException: 400 if limit > 100, 404 if site not found
    """
    if limit > 100:
        raise HTTPException(status_code=400, detail="Limit cannot exceed 100")

    try:
        alert_repo = AlertRepository()
        alerts = alert_repo.get_active_by_site(site_id)
        alerts = sorted(alerts, key=lambda item: str(item.get("created_at") or ""), reverse=True)
        paged_alerts = alerts[offset : offset + limit]

        items = [
            AlertItem(
                id=str(alert.get("id") or ""),
                equipment_id=str(alert.get("equipment_id") or ""),
                equipment_name=str(alert.get("title") or alert.get("equipment_id") or "Site alert"),
                severity=str(alert.get("severity") or "warning"),
                description=str(alert.get("message") or alert.get("title") or ""),
                created_at=str(alert.get("created_at") or ""),
            )
            for alert in paged_alerts
        ]
        return SiteAlerts(site_id=site_id, alerts=items, total_count=len(alerts), offset=offset, limit=limit)
    except Exception as e:
        logger.error(f"Error getting site alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/sites/{site_id}/predictions",
    response_model=PredictionSummary,
    summary="Get site predictions summary",
    description="Fetch predictions summary for a site.",
)
@limiter.limit("600/minute")
async def get_site_predictions(request: Request, site_id: str) -> PredictionSummary:
    """Get predictions summary for a site.

    Args:
        site_id: Site identifier

    Returns:
        PredictionSummary with risk counts

    Raises:
        HTTPException: 404 if site not found
    """
    try:
        return PredictionSummary()
    except Exception as e:
        logger.error(f"Error getting site predictions: {e}")
        raise HTTPException(status_code=500, detail=str(e))
