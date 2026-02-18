"""Solar Grid Compliance API — NRS 097-2-3 monitoring and load shedding.

Endpoints for real-time grid compliance status, violation history, load shedding
stages, frequency/voltage trending, and compliance reports.

Pattern follows solar.py and devices.py routers.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from app.middleware.rate_limiter import limiter

from app.api.dependencies.module_access import require_active_module
from app.models.module_registry import ModuleType
from app.services.grid_parameters import get_grid_parameters_service
from app.services.grid_compliance_service import (
    get_load_shed_scheduler,
)
from app.database.supabase_client import get_supabase_client

router = APIRouter(
    dependencies=[
        Depends(
            require_active_module(
                ModuleType.SOLAR,
                site_keys=("site_id", "site"),
                default_site_id="site-002",
            )
        )
    ]
)


# === Grid Compliance Status Endpoints ===


@limiter.limit("30/minute")
@router.get("/solar/grid/status/{system_id}")
async def get_grid_status(request: Request, system_id: str):
    """Get current grid compliance status for a solar system.

    Returns:
        {
            compliant: bool,
            active_violations: [...],
            frequency_hz: float,
            voltage_v: float,
            last_check: datetime,
            next_check: datetime
        }
    """
    try:
        svc = get_grid_parameters_service()
        status_dict = await svc.check_compliance(system_id.split("-")[0])  # Extract site_id

        return {
            "system_id": system_id,
            "compliant": status_dict.get("compliant", True),
            "active_violations": status_dict.get("active_violations", []),
            "frequency_hz": status_dict["measurements"]["frequency_hz"],
            "voltage_v": status_dict["measurements"]["voltage_v"],
            "last_check": status_dict["last_check"],
            "next_check": status_dict["next_check"],
            "timestamp": status_dict["last_check"],
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get grid status: {str(e)}")


@limiter.limit("30/minute")
@router.get("/solar/grid/violations")
async def get_violations(
    request: Request,
    system_id: Optional[str] = Query(None),
    hours: int = Query(24, ge=1, le=720),
    severity: Optional[str] = Query(None),
):
    """Get compliance violations for a time window.

    Query params:
        system_id: Filter by system (optional, all systems if not provided)
        hours: Time window in hours (1-720, default 24)
        severity: Filter by severity (critical, warning, info)

    Returns:
        {
            violations: [...],
            total_count: int,
            critical_count: int,
            warning_count: int
        }
    """
    try:
        from datetime import datetime, timedelta, timezone

        supabase = get_supabase_client()
        if supabase is None:
            return {
                "violations": [],
                "total_count": 0,
                "critical_count": 0,
                "warning_count": 0,
                "message": "Supabase unavailable, no violations available",
            }

        # Query compliance_log table
        query = supabase.table("compliance_log").select(
            "timestamp, system_id, parameter, measured_value, limit_value, "
            "violation_type, severity, auto_action, resolved"
        )

        # Apply filters
        if system_id:
            query = query.eq("system_id", system_id)

        # Time window filter
        cutoff_time = (
            datetime.now(timezone.utc) - timedelta(hours=hours)
        ).isoformat()
        query = query.gte("timestamp", cutoff_time)

        if severity:
            query = query.eq("severity", severity)

        # Sort by timestamp descending
        query = query.order("timestamp", desc=True)

        response = query.limit(1000).execute()
        violations = response.data if response.data else []

        # Count severities
        critical_count = len([v for v in violations if v["severity"] == "critical"])
        warning_count = len([v for v in violations if v["severity"] == "warning"])

        return {
            "violations": violations,
            "total_count": len(violations),
            "critical_count": critical_count,
            "warning_count": warning_count,
            "time_window_hours": hours,
            "query_time": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get violations: {str(e)}")


@limiter.limit("30/minute")
@router.get("/solar/grid/load-shedding/stage")
async def get_load_shedding_stage(request: Request):
    """Get current load shedding stage and active actions.

    Returns:
        {
            current_stage: int (0-8),
            frequency_hz: float,
            triggered_at: datetime,
            active_actions: str,
            previous_stage: int,
            expected_reduction_kw: float
        }
    """
    try:
        svc = get_grid_parameters_service()
        scheduler = get_load_shed_scheduler()

        # Get current frequency
        params = await svc.get_grid_parameters()

        # Detect stage (without transition if no change)
        stage = scheduler.get_current_stage()
        last_event = scheduler.get_last_transition()

        return {
            "current_stage": stage,
            "frequency_hz": params.frequency_hz,
            "triggered_at": last_event.timestamp if last_event else None,
            "active_actions": last_event.dispatch_action if last_event else "none",
            "previous_stage": last_event.previous_stage if last_event else 0,
            "expected_reduction_kw": last_event.expected_reduction_kw if last_event else 0.0,
            "load_shed_threshold_hz": {
                "stage_1": 50.5,
                "stage_2": 50.4,
                "stage_3": 50.3,
                "stage_4": 50.2,
                "stage_5": 50.0,
                "stage_6": 49.5,
                "stage_7": 49.0,
                "stage_8": 47.5,
            },
            "timestamp": params.timestamp,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get load shedding stage: {str(e)}")


@limiter.limit("30/minute")
@router.get("/solar/grid/frequency-trend")
async def get_frequency_trend(
    request: Request,
    window: str = Query("1h", regex="^(5m|1h|24h)$"),
):
    """Get frequency trend over a time window with band overlays.

    Query params:
        window: Time window (5m, 1h, 24h)

    Returns:
        {
            readings: [...],
            band_limits: {normal, recovery, emergency},
            violations: int,
            trend: "stable|rising|falling"
        }
    """
    try:
        svc = get_grid_parameters_service()

        # Map window to minutes
        window_map = {"5m": 5, "1h": 60, "24h": 1440}
        minutes = window_map.get(window, 60)

        # Get trend data
        trend_data = await svc.get_frequency_trend(minutes)

        # Calculate statistics
        if trend_data:
            freqs = [r["frequency_hz"] for r in trend_data]
            min_freq = min(freqs)
            max_freq = max(freqs)
            avg_freq = sum(freqs) / len(freqs)

            # Determine trend
            if len(freqs) > 1:
                if freqs[-1] > freqs[0] + 0.05:
                    trend = "rising"
                elif freqs[-1] < freqs[0] - 0.05:
                    trend = "falling"
                else:
                    trend = "stable"
            else:
                trend = "stable"
        else:
            min_freq = max_freq = avg_freq = 50.0
            trend = "stable"

        # Count violations
        violations = len([f for f in (trend_data or []) if f["frequency_hz"] < 49.5 or f["frequency_hz"] > 50.5])

        return {
            "window": window,
            "readings": trend_data,
            "statistics": {
                "min_hz": round(min_freq, 3),
                "max_hz": round(max_freq, 3),
                "average_hz": round(avg_freq, 3),
                "violations_count": violations,
                "trend": trend,
            },
            "band_limits": {
                "normal": {"min": 49.5, "max": 50.5},
                "recovery": {"min": 49.5, "max": 50.5},
                "emergency": {"min": 47.5, "max": 52.0},
                "trip": {"min": 47.5, "max": 52.0},
            },
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get frequency trend: {str(e)}")


@limiter.limit("30/minute")
@router.get("/solar/grid/voltage-trend")
async def get_voltage_trend(
    request: Request,
    window: str = Query("1h", regex="^(5m|1h|24h)$"),
):
    """Get voltage trend over a time window with band overlays.

    Query params:
        window: Time window (5m, 1h, 24h)

    Returns:
        {
            readings: [...],
            band_limits: {normal, recovery, emergency},
            violations: int
        }
    """
    try:
        svc = get_grid_parameters_service()

        # Map window to minutes
        window_map = {"5m": 5, "1h": 60, "24h": 1440}
        minutes = window_map.get(window, 60)

        # Get trend data
        trend_data = await svc.get_voltage_trend(minutes)

        # Calculate statistics
        if trend_data:
            volts = [r["voltage_v"] for r in trend_data]
            min_volt = min(volts)
            max_volt = max(volts)
            avg_volt = sum(volts) / len(volts)
        else:
            min_volt = max_volt = avg_volt = 400.0

        # Count violations (±10% of 400V nominal = 360-440V)
        violations = len([v for v in (trend_data or []) if v["voltage_v"] < 360 or v["voltage_v"] > 440])

        return {
            "window": window,
            "readings": trend_data,
            "statistics": {
                "min_v": round(min_volt, 2),
                "max_v": round(max_volt, 2),
                "average_v": round(avg_volt, 2),
                "violations_count": violations,
            },
            "band_limits": {
                "normal": {"min": 360, "max": 440},  # ±10%
                "recovery": {"min": 376, "max": 424},  # ±6%
                "emergency": {"min": 340, "max": 460},  # ±15%
            },
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get voltage trend: {str(e)}")


@limiter.limit("30/minute")
@router.get("/solar/grid/compliance-report")
async def get_compliance_report(
    request: Request,
    system_id: Optional[str] = Query(None),
    month: Optional[str] = Query(None),  # Format: YYYY-MM
):
    """Get detailed compliance report for a system and time period.

    Query params:
        system_id: System to report on
        month: Month in YYYY-MM format (default: current month)

    Returns:
        {
            period: str,
            total_violations: int,
            critical_violations: int,
            resolution_rate: float,
            violations_by_parameter: {...},
            most_common_actions: {...},
            compliance_score: float (0-100)
        }
    """
    try:
        from datetime import datetime, timezone

        # Default to current month
        if not month:
            now = datetime.now(timezone.utc)
            month = now.strftime("%Y-%m")

        # Calculate date range
        month_parts = month.split("-")
        if len(month_parts) != 2:
            raise HTTPException(status_code=400, detail="Month must be in YYYY-MM format")

        year, month_num = int(month_parts[0]), int(month_parts[1])
        start_date = datetime(year, month_num, 1, tzinfo=timezone.utc)

        if month_num == 12:
            end_date = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            end_date = datetime(year, month_num + 1, 1, tzinfo=timezone.utc)

        supabase = get_supabase_client()
        if supabase is None:
            return {
                "period": month,
                "total_violations": 0,
                "critical_violations": 0,
                "message": "Supabase unavailable",
            }

        # Query compliance_log
        query = supabase.table("compliance_log").select(
            "severity, parameter, auto_action, resolved, timestamp"
        )

        if system_id:
            query = query.eq("system_id", system_id)

        query = query.gte("timestamp", start_date.isoformat())
        query = query.lt("timestamp", end_date.isoformat())

        response = query.limit(10000).execute()
        violations = response.data if response.data else []

        # Calculate metrics
        total_violations = len(violations)
        critical_violations = len([v for v in violations if v["severity"] == "critical"])
        resolved_violations = len([v for v in violations if v.get("resolved")])

        resolution_rate = (
            (resolved_violations / total_violations * 100)
            if total_violations > 0
            else 100.0
        )

        # Count by parameter
        violations_by_parameter = {}
        for v in violations:
            param = v.get("parameter", "unknown")
            violations_by_parameter[param] = violations_by_parameter.get(param, 0) + 1

        # Most common actions
        actions_count = {}
        for v in violations:
            action = v.get("auto_action", "none")
            actions_count[action] = actions_count.get(action, 0) + 1

        most_common_actions = sorted(
            actions_count.items(), key=lambda x: x[1], reverse=True
        )[:5]

        # Compliance score: 100 - (critical% * 20 + unresolved% * 10)
        critical_pct = (critical_violations / total_violations * 100) if total_violations > 0 else 0
        unresolved_pct = ((total_violations - resolved_violations) / total_violations * 100) if total_violations > 0 else 0
        compliance_score = max(
            0, 100 - (critical_pct * 0.2 + unresolved_pct * 0.1)
        )

        return {
            "period": month,
            "period_start": start_date.isoformat(),
            "period_end": end_date.isoformat(),
            "system_id": system_id or "all_systems",
            "total_violations": total_violations,
            "critical_violations": critical_violations,
            "warning_violations": len([v for v in violations if v["severity"] == "warning"]),
            "resolved_violations": resolved_violations,
            "resolution_rate_pct": round(resolution_rate, 2),
            "violations_by_parameter": violations_by_parameter,
            "most_common_actions": dict(most_common_actions),
            "compliance_score": round(compliance_score, 2),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate report: {str(e)}")


@limiter.limit("30/minute")
@router.post("/solar/grid/auto-response/override")
async def override_auto_response(
    request: Request,
    system_id: str = Query(...),
    action: str = Query(...),  # "curtailment_50pct", "standby", "ramp_up", etc.
    duration_seconds: int = Query(300),  # How long to maintain override
):
    """Manual override for emergency situations (e.g., during grid events).

    Query params:
        system_id: System to override
        action: Override action to take
        duration_seconds: Duration of override (default 300s)

    Returns:
        {
            status: "override_active",
            action: str,
            system_id: str,
            expires_at: datetime
        }
    """
    try:
        from datetime import datetime, timedelta, timezone

        # Log override event
        supabase = get_supabase_client()
        if supabase:
            expires_at = (
                datetime.now(timezone.utc) + timedelta(seconds=duration_seconds)
            ).isoformat()

            try:
                await supabase.table("grid_overrides").insert({
                    "system_id": system_id,
                    "action": action,
                    "initiated_at": datetime.now(timezone.utc).isoformat(),
                    "expires_at": expires_at,
                    "manual_override": True,
                }).execute()
            except Exception as e:
                # Table might not exist, just log the override in memory
                logger.warning(f"Could not persist override to Supabase: {e}")

        return {
            "status": "override_active",
            "action": action,
            "system_id": system_id,
            "duration_seconds": duration_seconds,
            "expires_at": (
                datetime.now(timezone.utc) + timedelta(seconds=duration_seconds)
            ).isoformat(),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to apply override: {str(e)}")


# Logging imports at the end
import logging
logger = logging.getLogger(__name__)
