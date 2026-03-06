"""Indoor Air Quality API endpoints.

Provides IAQ scores per zone, site-wide overviews, alerts,
and compliance reports for WELL/ESG certification.
"""

import logging

from fastapi import APIRouter, HTTPException, Query

from app.services.iaq_service import get_iaq_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/iaq", tags=["iaq"])


@router.get("/zones/{site_id}")
async def get_site_iaq(site_id: str):
    """Get IAQ scores for all zones in a site.

    Returns overall site IAQ score, per-zone breakdown, and active alerts.
    """
    svc = get_iaq_service()
    overview = svc.get_site_iaq(site_id)
    if overview.total_zones == 0:
        raise HTTPException(status_code=404, detail=f"No zones found for site {site_id}")
    return overview.model_dump()


@router.get("/zones/{site_id}/{zone_id}")
async def get_zone_iaq(site_id: str, zone_id: str):
    """Get detailed IAQ score for a specific zone.

    Returns component scores (CO2, humidity, temperature, VOC, PM2.5),
    composite IAQ score, and any active alerts.
    """
    svc = get_iaq_service()
    result = svc.get_zone_iaq(site_id, zone_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Zone {zone_id} not found in site {site_id}")
    return result.model_dump()


@router.get("/alerts/{site_id}")
async def get_iaq_alerts(site_id: str):
    """Get active IAQ alerts for a site.

    Returns alerts for CO2, humidity, temperature deviation,
    VOC, and PM2.5 threshold breaches.
    """
    svc = get_iaq_service()
    alerts = svc.get_alerts(site_id)
    return {
        "site_id": site_id,
        "total_alerts": len(alerts),
        "critical": sum(1 for a in alerts if a.severity == "critical"),
        "warning": sum(1 for a in alerts if a.severity == "warning"),
        "alerts": [a.model_dump() for a in alerts],
    }


@router.get("/compliance/{site_id}")
async def get_iaq_compliance(
    site_id: str,
    report_type: str = Query("well", description="Report type: 'well' or 'esg'"),
):
    """Get IAQ compliance report for WELL or ESG certification.

    WELL report checks against WELL v2 Air concept thresholds.
    ESG report provides sustainability metrics for corporate reporting.
    """
    if report_type not in ("well", "esg"):
        raise HTTPException(status_code=400, detail="report_type must be 'well' or 'esg'")
    svc = get_iaq_service()
    report = svc.get_compliance_report(site_id, report_type)
    return report.model_dump()
