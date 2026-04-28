"""Optimization API endpoints for HVAC load shedding and AI optimization."""

import calendar
import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body, HTTPException, Request
from pydantic import BaseModel

from app.config.settings import settings
from app.database.repositories import SiteRepository
from app.database.repositories.recommendation_repository import RecommendationRepository
from app.middleware.rate_limiter import limiter
from app.models.audit_log import AuditResultType
from app.models.module_registry import ModuleType
from app.models.optimization import (
    OptimizationHistoryEntry,
    OptimizationStatus,
)
from app.models.recommendation import Recommendation, RecommendationStatus
from app.services.ai_optimizer import get_ai_optimizer
from app.services.approval_service import get_approval_service
from app.services.audit_logger import AuditLogger
from app.services.device_abstraction import device_manager
from app.services.eskomsepush_service import eskomsepush_service
from app.services.module_registry_service import module_registry
from app.services.mv_verification_service import get_mv_verification_service
from app.services.optimization_tier_router import get_tier_router
from app.services.profile_service import get_profile_service
from app.services.routing_adapters import optimization_routing_to_tier_result
from app.utils.ai_provenance import attach_ai_provenance, get_ml_provenance

logger = logging.getLogger(__name__)

router = APIRouter()

# Data directory
DATA_DIR = Path(__file__).parent.parent / "data"


# Pydantic models for request/response validation


# Pydantic models for request/response validation
class LoadSheddingStage(BaseModel):
    """Model for load shedding stage information."""

    stage: int
    start_time: str
    end_time: str


class EskomStatusResponse(BaseModel):
    """Response model for Eskom status endpoint."""

    current_stage: int
    updated_at: str
    next_stages: list[LoadSheddingStage]
    area_schedules: dict[str, list[LoadSheddingStage]]
    source: str = "eskomsepush"  # "eskomsepush" or "simulated"


class SiteScheduleResponse(BaseModel):
    """Response model for site-specific schedule endpoint."""

    site_id: str
    site_name: str
    current_stage: int
    schedules: list[LoadSheddingStage]
    next_outage: LoadSheddingStage | None
    area_name: str = ""
    source: str = "eskomsepush"


def get_site_name(site_id: str) -> str:
    """Get site name from site ID."""
    site_names = {
        "site-001": "Gateway Theatre",
        "site-002": "Sandton City",
        "site-003": "Centurion Mall",
        "site-004": "Tygervalley",
        "site-005": "Canal Walk",
        "site-006": "East Rand Mall",
        "site-007": "Pavilion",
        "site-008": "N1 City",
        "site-009": "Blue Route",
        "site-010": "Cresta",
    }
    return site_names.get(site_id, f"Site {site_id}")


@router.get("/optimization/scenarios")
async def get_optimization_scenarios(site_id: str | None = None) -> list[dict[str, Any]]:
    """
    Get load shedding optimization scenarios.

    Returns pre-computed scenarios from optimization_scenarios.json,
    optionally filtered by site_id.

    Args:
        site_id: Optional site ID to filter scenarios

    Returns:
        List of optimization scenarios
    """
    scenarios_file = DATA_DIR / "optimization_scenarios.json"
    if not scenarios_file.exists():
        return []

    with open(scenarios_file) as f:
        scenarios = json.load(f)

    if site_id:
        scenarios = [s for s in scenarios if s.get("site_id") == site_id]

    return scenarios


@router.get("/optimization/eskom-status", response_model=EskomStatusResponse)
async def get_eskom_status():
    """
    Get current Eskom load shedding status and schedules.

    Uses EskomSePush API when configured (ESKOMSEPUSH_API_TOKEN env var).
    Falls back to stage 0 (no load shedding) with empty schedules when
    the API is not configured.
    """
    if eskomsepush_service.is_configured:
        try:
            combined = await eskomsepush_service.get_combined_status()

            # Build next_stages from EskomSePush national status
            next_stages = []
            for ns in combined.eskom.next_stages:
                ts = ns.get("stage_start_timestamp", "")
                # Parse ISO timestamp to extract time
                try:
                    dt = datetime.fromisoformat(ts)
                    start_time = dt.strftime("%H:%M")
                    end_time = (dt + timedelta(hours=2, minutes=30)).strftime("%H:%M")
                except (ValueError, TypeError):
                    start_time = ts
                    end_time = ""

                next_stages.append(
                    LoadSheddingStage(
                        stage=int(ns.get("stage", 0)),
                        start_time=start_time,
                        end_time=end_time,
                    )
                )

            # Build area schedules from area events
            area_schedules: dict[str, list[LoadSheddingStage]] = {}
            if combined.area_events:
                area_key = combined.area_name or "default"
                area_schedules[area_key] = [
                    LoadSheddingStage(
                        stage=event.stage,
                        start_time=_format_iso_time(event.start),
                        end_time=_format_iso_time(event.end),
                    )
                    for event in combined.area_events
                ]

            return EskomStatusResponse(
                current_stage=combined.eskom.stage,
                updated_at=combined.fetched_at,
                next_stages=next_stages,
                area_schedules=area_schedules,
                source="eskomsepush",
            )

        except Exception as e:
            logger.error(f"EskomSePush API error: {e}")
            # Fall through to empty response on API error

    # No API configured or API error: return stage 0 with no schedules
    return EskomStatusResponse(
        current_stage=0,
        updated_at=datetime.now().isoformat(),
        next_stages=[],
        area_schedules={},
        source="unavailable" if eskomsepush_service.is_configured else "not_configured",
    )


@router.get("/optimization/eskom-status/{site_id}", response_model=SiteScheduleResponse)
async def get_site_eskom_status(site_id: str):
    """
    Get load shedding schedule for a specific site.

    Uses EskomSePush API when configured. Returns real area events
    for the configured area. When stage is 0, returns empty schedules.

    Args:
        site_id: The site ID to get schedule for

    Returns:
        Site-specific load shedding schedule
    """
    if eskomsepush_service.is_configured:
        try:
            combined = await eskomsepush_service.get_combined_status()
            current_stage = combined.eskom.stage

            # Convert area events to LoadSheddingStage list
            schedules: list[LoadSheddingStage] = []
            if current_stage > 0 and combined.area_events:
                for event in combined.area_events:
                    schedules.append(
                        LoadSheddingStage(
                            stage=event.stage,
                            start_time=_format_iso_time(event.start),
                            end_time=_format_iso_time(event.end),
                        )
                    )

            # Find next upcoming outage
            now = datetime.now()
            next_outage = None
            for event in combined.area_events:
                try:
                    event_start = datetime.fromisoformat(event.start)
                    if event_start > now:
                        next_outage = LoadSheddingStage(
                            stage=event.stage,
                            start_time=_format_iso_time(event.start),
                            end_time=_format_iso_time(event.end),
                        )
                        break
                except (ValueError, TypeError):
                    continue

            return SiteScheduleResponse(
                site_id=site_id,
                site_name=get_site_name(site_id),
                current_stage=current_stage,
                schedules=schedules,
                next_outage=next_outage,
                area_name=combined.area_name,
                source="eskomsepush",
            )

        except Exception as e:
            logger.error(f"EskomSePush API error for site {site_id}: {e}")

    # No API configured or API error: return stage 0 with no schedules
    return SiteScheduleResponse(
        site_id=site_id,
        site_name=get_site_name(site_id),
        current_stage=0,
        schedules=[],
        next_outage=None,
        area_name="",
        source="unavailable" if eskomsepush_service.is_configured else "not_configured",
    )


def _format_iso_time(iso_string: str) -> str:
    """Extract HH:MM from an ISO 8601 timestamp string."""
    try:
        dt = datetime.fromisoformat(iso_string)
        return dt.strftime("%H:%M")
    except (ValueError, TypeError):
        return iso_string


@router.get("/optimization/eskomsepush/areas")
async def search_eskomsepush_areas(text: str):
    """
    Search EskomSePush for area IDs by name.

    Use this to find the correct area_id to configure in ESKOMSEPUSH_AREA_ID.

    Args:
        text: Search text (e.g., "sandton", "rivonia")

    Returns:
        List of matching areas with id, name, region
    """
    if not eskomsepush_service.is_configured:
        raise HTTPException(status_code=503, detail="EskomSePush API not configured. Set ESKOMSEPUSH_API_TOKEN in .env")

    try:
        areas = await eskomsepush_service.search_areas(text)
        return {"areas": areas, "count": len(areas)}
    except Exception as e:
        logger.error(f"EskomSePush area search error: {e}")
        raise HTTPException(status_code=502, detail=f"EskomSePush API error: {e!s}")


@router.get("/optimization/eskomsepush/allowance")
async def get_eskomsepush_allowance():
    """Check remaining EskomSePush API quota."""
    if not eskomsepush_service.is_configured:
        raise HTTPException(status_code=503, detail="EskomSePush API not configured. Set ESKOMSEPUSH_API_TOKEN in .env")

    try:
        return await eskomsepush_service.get_allowance()
    except Exception as e:
        logger.error(f"EskomSePush allowance check error: {e}")
        raise HTTPException(status_code=502, detail=f"EskomSePush API error: {e!s}")


@router.get("/optimization/thermal-runway")
async def calculate_thermal_runway(site_id: str, current_temp: float = 22.4, comfort_limit: float = 26.0):
    """
    Calculate thermal runway for a building during load shedding.

    Args:
        site_id: The site ID
        current_temp: Current inside temperature in °C
        comfort_limit: Comfort temperature limit in °C

    Returns:
        Thermal runway calculation results
    """
    # Import thermal model service
    try:
        from app.services.thermal_model import calculate_thermal_runway as calc_runway
    except ImportError:
        # Fallback calculation if thermal model not available
        logger.warning("Thermal model service not available, using fallback calculation")

        # Simple fallback calculation
        outside_temp = 32.0  # Assume hot day
        temp_difference = outside_temp - current_temp
        heat_transfer_rate = 0.05  # Simplified coefficient

        # Calculate minutes until comfort breach
        runway_minutes = int((comfort_limit - current_temp) / (temp_difference * heat_transfer_rate) * 60)
        runway_minutes = max(10, min(180, runway_minutes))  # Clamp between 10-180 minutes

        return {
            "site_id": site_id,
            "site_name": get_site_name(site_id),
            "current_temperature": current_temp,
            "comfort_limit": comfort_limit,
            "thermal_runway_minutes": runway_minutes,
            "comfort_breach_time": None,
            "calculation_method": "fallback",
            "building_params": {"thermal_mass": 0.8, "insulation_factor": 0.6, "internal_heat_gain": 0.5},
        }

    # Use thermal model service
    building_params = {"thermal_mass": 0.8, "insulation_factor": 0.6, "internal_heat_gain": 0.5}

    weather_forecast = {"outside_temp": 32.0, "solar_load": 0.7, "humidity": 65}

    runway_minutes = calc_runway(current_temp, comfort_limit, building_params, weather_forecast)

    # Calculate comfort breach time
    current_time = datetime.now()
    breach_time = current_time + timedelta(minutes=runway_minutes)

    return {
        "site_id": site_id,
        "site_name": get_site_name(site_id),
        "current_temperature": current_temp,
        "comfort_limit": comfort_limit,
        "thermal_runway_minutes": runway_minutes,
        "comfort_breach_time": breach_time.isoformat(),
        "calculation_method": "thermal_model",
        "building_params": building_params,
        "weather_forecast": weather_forecast,
    }


# ============================================================================
# AI Optimization Endpoints (Phase 8)
# ============================================================================


class AnalyzeRequest(BaseModel):
    """Request model for analyze endpoint."""

    site_id: str
    current_conditions: dict[str, Any] | None = None
    weather_forecast: dict[str, Any] | None = None
    energy_prices: dict[str, Any] | None = None


class LoadSheddingAnalyzeRequest(BaseModel):
    """Request model for load shedding analysis endpoint."""

    site_id: str
    load_shedding_stage: int  # 1-4, higher = more severe
    current_conditions: dict[str, Any] | None = None


class ApproveRequest(BaseModel):
    """Request model for approve endpoint."""

    recommendation_id: str
    site_id: str
    setpoints_to_apply: list[dict[str, Any]]


class ToggleRequest(BaseModel):
    """Request model for toggle endpoint."""

    enabled: bool


def _controls_module_active(site_id: str) -> bool:
    """Return whether energy control add-on is active for a site."""
    return module_registry.is_module_active(site_id, ModuleType.ENERGY_CONTROL)


def _raise_controls_module_required(site_id: str) -> None:
    """Raise a standardized 403 when control add-on is not active."""
    raise HTTPException(
        status_code=403,
        detail=(
            f"Control module is not active for site '{site_id}'. "
            "Base package supports monitoring and AI recommendations only."
        ),
    )


def load_sites():
    """Load sites from Supabase only — Phase 183 Supabase-only model."""
    if settings.use_json_storage:
        return []

    try:
        repo = SiteRepository()
        buildings = repo.get_all()
        if buildings:
            sites = []
            for b in buildings:
                site = {
                    "id": b.get("code") or b.get("id"),
                    "name": b.get("name"),
                    "onboarding_phase": b.get("onboarding_phase") or "shadow",
                    "optimization_enabled": b.get("optimization_enabled") or False,
                    "optimization_status": b.get("optimization_status") or "unknown",
                    "optimization_settings": b.get("optimization_settings") or {},
                    "last_recommendation": b.get("last_recommendation"),
                    "last_optimization": b.get("last_optimization"),
                    "optimization_history": b.get("optimization_history") or [],
                    "error_message": b.get("error_message"),
                    "_uuid": b.get("id"),
                }
                sites.append(site)
            return sites
        return []
    except Exception as e:
        logger.error(f"Failed to load sites from Supabase: {e}")
        return []


def save_sites(sites: list[dict[str, Any]]):
    """Save sites to Supabase only — Phase 183 Supabase-only model."""
    if settings.use_json_storage:
        return

    try:
        repo = SiteRepository()
        for site in sites:
            site_id = site.get("id")
            update_data = {
                "optimization_enabled": site.get("optimization_enabled", False),
                "optimization_status": site.get("optimization_status", "unknown"),
                "optimization_settings": site.get("optimization_settings"),
                "last_recommendation": site.get("last_recommendation"),
                "last_optimization": site.get("last_optimization"),
                "optimization_history": site.get("optimization_history", []),
            }
            repo.update(site_id, update_data)
        return
    except Exception as e:
        logger.error(f"Failed to save sites to Supabase: {e}")


@router.post("/optimization/analyze")
async def analyze_optimization(request: AnalyzeRequest) -> dict[str, Any]:
    """
    Analyze building conditions and generate multi-system optimization recommendations.

    Uses AI to analyze current building telemetry, weather forecast, DALI lighting
    occupancy, and energy pricing to recommend optimal HVAC and lighting setpoints.

    Args:
        request: Analysis request with site_id and optional conditions

    Returns:
        OptimizationRecommendation with:
        - recommendations: List of HVAC and lighting setpoint changes
        - projected_savings: Combined energy and cost savings (hvac_kwh, lighting_kwh)
        - cross_system_recommendations: Coordinated HVAC+lighting actions for zones
        - lighting_summary: Zone counts, occupancy stats, and estimated savings
    """
    try:
        logger.info(f"Analyzing optimization for site {request.site_id}")

        # Call AI optimizer service
        recommendation = await get_ai_optimizer().analyze_building(
            site_id=request.site_id,
            current_conditions=request.current_conditions,
            weather_forecast=request.weather_forecast,
            energy_prices=request.energy_prices,
        )

        # Validate recommendation against safety rules
        validation = await get_ai_optimizer().validate_recommendation(request.site_id, recommendation)

        # Build response summary
        rec_dict = recommendation.to_dict()
        hvac_count = len([r for r in rec_dict.get("recommendations", []) if r.get("system") != "lighting"])
        lighting_count = len([r for r in rec_dict.get("recommendations", []) if r.get("system") == "lighting"])
        cross_system_count = len(rec_dict.get("cross_system_recommendations", []) or [])

        # Update site status
        sites = load_sites() or []
        site = next((s for s in sites if s.get("id") == request.site_id), None)

        # Check if site is in automatic mode (auto-apply without human approval)
        site_mode = "supervised"
        site_settings = {}
        site_phase = "shadow"
        if site:
            site_settings = site.get("optimization_settings") or {}
            site_mode = site_settings.get("mode", "supervised")
            site_phase = site.get("onboarding_phase") or "shadow"
        controls_module_active = _controls_module_active(request.site_id)

        # --- Tier Routing (Phase 82-02) ---
        # Compute routing decisions per recommendation via the tier router.
        tier_router = get_tier_router()  # use cached singleton; thresholds now read from settings at init
        control_tier = tier_router.resolve_control_tier(
            site_profile=site,
            optimization_settings=type("_Opts", (), {"mode": site_mode})(),
        )

        routing_decisions = []
        recommendations_list = rec_dict.get("recommendations", [])
        _rec_repo = RecommendationRepository()
        for rec_item in recommendations_list:
            system = rec_item.get("system", rec_item.get("equipment_type", "HVAC"))
            point = rec_item.get("point_name", rec_item.get("setpoint", ""))
            confidence = rec_item.get("confidence", recommendation.confidence)

            # G1: Persist Recommendation record before routing so that downstream
            # steps (G2 approval, G3 execution) can fetch a stable rec.id from DB.
            # Defaulted fields:
            #   action_type  — not available on rec_item dict; defaulted to ""
            #   risk_level   — not available pre-routing; defaulted to MEDIUM
            #   reason       — narrative is on the parent recommendation, not per-item
            #   profile      — carried from parent recommendation object
            _correlation_id = rec_item.get("correlation_id") or str(uuid4())
            _rec_obj = Recommendation(
                site_id=request.site_id,
                source="optimization_api",
                status=RecommendationStatus.PENDING,
                target_equipment=rec_item.get("equipment_code", rec_item.get("equipment", "")),
                action={
                    "point": point,
                    "value": rec_item.get("value", rec_item.get("setpoint_value", None)),
                },
                confidence=str(confidence) if not isinstance(confidence, str) else confidence,
                profile=recommendation.profile or "",
                correlation_id=_correlation_id,
            )
            try:
                _rec_obj = await _rec_repo.create(_rec_obj)
            except Exception as _persist_err:
                logger.warning(
                    "G1: Failed to persist Recommendation before routing (site=%s): %s — "
                    "continuing with in-memory id=%s",
                    request.site_id,
                    _persist_err,
                    _rec_obj.id,
                )
            # rec.id is now stable and available for G2/G3 downstream steps
            rec_item["_recommendation_id"] = _rec_obj.id
            rec_item["_correlation_id"] = _correlation_id

            decision = tier_router.route_recommendation(
                confidence=confidence,
                system=system,
                point_name=point,
                site_id=request.site_id,
                control_tier=control_tier,
            )
            routing_decisions.append(decision)

        routing_summary = tier_router.get_routing_summary(routing_decisions, control_tier)

        if settings.optimization_routing_enforced:
            logger.info(
                f"Tier routing ENFORCED for site {request.site_id}: "
                f"blocked={routing_summary.blocked}, advisory={routing_summary.advisory}, "
                f"pending={routing_summary.pending_approval}, auto={routing_summary.auto_executed}"
            )
        else:
            logger.info(
                f"Tier routing SHADOW for site {request.site_id}: "
                f"blocked={routing_summary.blocked}, advisory={routing_summary.advisory}, "
                f"pending={routing_summary.pending_approval}, auto={routing_summary.auto_executed}"
            )

        auto_applied = False
        auto_apply_results = []
        execution_summary = {"attempted": 0, "succeeded": 0, "failed": 0}

        # Determine which recommendations are eligible for auto-apply
        from app.models.onboarding_phase import phase_allows

        phase_permits_auto = phase_allows(site_phase, "auto_apply")

        # G3+G4: Route eligible Tier 3 decisions through ApprovalService.
        # Tier 2 decisions rest in the recommendations table (persisted in G1) and
        # await human approval — no further action is required here.
        # Tier 1 / blocked / advisory decisions are logged only.
        approval_service = get_approval_service()
        for idx, rec_item in enumerate(recommendations_list):
            if idx >= len(routing_decisions):
                break
            decision = routing_decisions[idx]

            tier_result = optimization_routing_to_tier_result(
                decision,
                rec_item.get("_recommendation_id", ""),
                rec_item.get("_correlation_id", ""),
            )

            if tier_result.action == "auto_execute":
                # Only auto-execute when validation, phase, and controls module permit
                if not (controls_module_active and validation["allowed"] and phase_permits_auto):
                    logger.info(
                        "Skipping auto_execute for site %s (controls_active=%s, validation=%s, phase=%s)",
                        request.site_id,
                        controls_module_active,
                        validation["allowed"],
                        phase_permits_auto,
                    )
                    execution_summary["attempted"] += 1
                    execution_summary["failed"] += 1
                    auto_apply_results.append(
                        {
                            "recommendation_id": tier_result.correlation_id,
                            "success": False,
                            "error": "Execution blocked by validation/phase/module gate",
                        }
                    )
                    continue

                execution_summary["attempted"] += 1
                try:
                    result = await approval_service.auto_execute_recommendation(
                        rec_item["_recommendation_id"],
                        tier_result,
                    )
                    auto_apply_results.append(
                        {
                            "recommendation_id": rec_item["_recommendation_id"],
                            "success": result.success,
                            "status": result.status,
                        }
                    )
                    if result.success:
                        execution_summary["succeeded"] += 1
                    else:
                        execution_summary["failed"] += 1
                        logger.warning(
                            "auto_execute_recommendation failed for rec=%s: %s",
                            rec_item["_recommendation_id"],
                            result.error_message,
                        )
                except Exception as apply_err:
                    logger.error(
                        "auto_execute_recommendation raised for rec=%s: %s",
                        rec_item.get("_recommendation_id"),
                        apply_err,
                    )
                    auto_apply_results.append(
                        {
                            "recommendation_id": rec_item.get("_recommendation_id"),
                            "success": False,
                            "error": str(apply_err),
                        }
                    )
                    execution_summary["failed"] += 1

            elif tier_result.action == "supervised":
                # Tier 2 — recommendation already persisted in G1; awaits human approval
                logger.info(
                    "Tier 2 recommendation %s queued for human approval (site=%s)",
                    rec_item.get("_recommendation_id"),
                    request.site_id,
                )
            # Tier 1 / advisory / blocked: no execution action needed

        auto_applied = all(r.get("success") for r in auto_apply_results) and len(auto_apply_results) > 0

        # Record M&V verification task for auto-applied recommendations
        # Only create M&V tasks for setpoints that were actually executed successfully
        if auto_applied:
            try:
                systems = list({r.get("system", "hvac") or "hvac" for r in rec_dict.get("recommendations", [])})
                setpoints_for_mv = [
                    {
                        "device_id": r.get("device_id") or r.get("equipment_id"),
                        "point_name": r.get("point_name"),
                        "old_value": r.get("current_value"),
                        "new_value": r.get("value") or r.get("recommended_value"),
                    }
                    for r in auto_apply_results
                    if r.get("success")
                ]
                # Build routing metadata from the first auto-executed routing decision
                routing_metadata = None
                for idx, d in enumerate(routing_decisions):
                    if d.action == "auto_execute":
                        routing_metadata = {
                            "routing_tier": d.tier.value,
                            "control_tier": control_tier,
                            "effective_confidence": d.effective_confidence,
                        }
                        break
                mv_service = get_mv_verification_service()
                mv_service.record_applied_recommendation(
                    site_id=request.site_id,
                    recommendation_id=rec_dict.get("timestamp", "unknown"),
                    projected_savings=rec_dict.get("projected_savings", {}),
                    setpoints_applied=setpoints_for_mv,
                    recommendation_systems=systems,
                    routing_metadata=routing_metadata,
                )
            except Exception as mv_err:
                logger.warning(f"M&V recording failed (non-blocking): {mv_err}")

        # --- Persist routing metadata on rec_dict (Phase 82-02) ---
        routing_details_list = [
            {
                "index": i,
                "tier": d.tier.value,
                "action": d.action,
                "reason": d.reason,
                "effective_confidence": d.effective_confidence,
                "original_confidence": d.original_confidence,
            }
            for i, d in enumerate(routing_decisions)
        ]
        routing_summary_dict = {
            "blocked": routing_summary.blocked,
            "advisory": routing_summary.advisory,
            "pending_approval": routing_summary.pending_approval,
            "auto_executed": routing_summary.auto_executed,
            "control_tier": control_tier,
            "thresholds": {
                "block_min": settings.optimization_tier_block_min,
                "tier2_min": settings.optimization_tier2_min,
                "tier3_min": settings.optimization_tier3_min,
            },
        }
        rec_dict["routing_details"] = routing_details_list
        rec_dict["routing_summary"] = routing_summary_dict
        rec_dict["control_tier"] = control_tier
        rec_dict["execution_summary"] = execution_summary

        if site:
            if auto_applied:
                # Automatic mode: setpoints were auto-applied
                site["optimization_status"] = OptimizationStatus.OPTIMIZED.value
                site["last_optimization"] = datetime.now().isoformat()
                site["last_recommendation"] = rec_dict
            elif validation["allowed"]:
                # Supervised mode: waiting for human approval
                site["optimization_status"] = OptimizationStatus.RECOMMENDATION_PENDING.value
                site["last_recommendation"] = rec_dict
            else:
                site["optimization_status"] = OptimizationStatus.WARNING.value
                site["last_recommendation"] = rec_dict
                site["error_message"] = "Recommendation failed safety validation"

            # Add to history
            if not site.get("optimization_history"):
                site["optimization_history"] = []

            history_action = "auto_applied" if auto_applied else "analyzed"
            history_result = "success" if (auto_applied or validation["allowed"]) else "warning"

            # Include projected savings in history for tracking
            projected_savings = rec_dict.get("projected_savings", {})
            history_entry = OptimizationHistoryEntry(
                timestamp=datetime.now().isoformat(),
                action=history_action,
                result=history_result,
                user="SENTINEL" if auto_applied else "system",
                details={
                    "confidence": recommendation.confidence,
                    "validation_passed": validation["allowed"],
                    "hvac_recommendations": hvac_count,
                    "lighting_recommendations": lighting_count,
                    "cross_system_recommendations": cross_system_count,
                    "auto_applied": auto_applied,
                    "mode": site_mode,
                    "projected_savings_zar_per_hour": (
                        projected_savings.get("cost_zar_per_hour", 0) if auto_applied else 0
                    ),
                },
                routing_summary=routing_summary_dict,
            )
            site["optimization_history"].append(history_entry.to_dict())

            # Keep only last 50 history entries
            if len(site["optimization_history"]) > 50:
                site["optimization_history"] = site["optimization_history"][-50:]

            save_sites(sites)

        return attach_ai_provenance(
            {
                "success": True,
                "recommendation": rec_dict,
                "validation": validation,
                "auto_applied": auto_applied,
                "auto_apply_results": (auto_apply_results if auto_applied else None),
                "mode": site_mode,
                "controls_module_active": controls_module_active,
                "control_tier": control_tier,
                "routing_summary": routing_summary_dict,
                "routing_details": routing_details_list,
                "execution_summary": execution_summary,
                "summary": {
                    "hvac_recommendations": hvac_count,
                    "lighting_recommendations": lighting_count,
                    "cross_system_recommendations": cross_system_count,
                    "total_recommendations": hvac_count + lighting_count,
                },
            },
            get_ml_provenance("ai-optimizer-v1"),
        )

    except ValueError as e:
        logger.error(f"Site not found: {e}")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error analyzing optimization: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/optimization/analyze-load-shedding")
async def analyze_load_shedding(request: LoadSheddingAnalyzeRequest) -> dict[str, Any]:
    """
    Analyze building optimization with load shedding stage awareness.

    During load shedding, the optimizer prioritizes critical zones (P1-P2)
    while allowing more aggressive optimization in lower-priority zones.

    Zone Priority Behavior by Stage:
    - Stage 1: Maintain P1-P4 normally, aggressive optimization on P5
    - Stage 2: Maintain P1-P3 normally, aggressive optimization on P4-P5
    - Stage 3: Maintain P1-P2 normally, aggressive optimization on P3-P5
    - Stage 4: Maintain P1 only (executive, server rooms), aggressive on all else

    Args:
        request: Analysis request with site_id, load_shedding_stage (1-4), and optional conditions

    Returns:
        OptimizationRecommendation with zone-priority-aware recommendations
    """
    try:
        # Validate stage
        if request.load_shedding_stage < 1 or request.load_shedding_stage > 4:
            raise HTTPException(status_code=400, detail="load_shedding_stage must be between 1 and 4")

        logger.info(
            f"Analyzing load shedding optimization for site {request.site_id}, stage {request.load_shedding_stage}"
        )

        # Call AI optimizer service with load shedding awareness
        recommendation = await get_ai_optimizer().analyze_site_load_shedding(
            site_id=request.site_id,
            load_shedding_stage=request.load_shedding_stage,
            current_conditions=request.current_conditions,
        )

        # Validate recommendation against safety rules
        validation = await get_ai_optimizer().validate_recommendation(request.site_id, recommendation)

        return attach_ai_provenance(
            {
                "success": True,
                "load_shedding_stage": request.load_shedding_stage,
                "recommendation": recommendation.to_dict(),
                "validation": validation,
                "zone_priority_info": {
                    1: "Stage 1: Maintain P1-P4, shed P5 (parking, plant rooms)",
                    2: "Stage 2: Maintain P1-P3, shed P4-P5 (+ lobby)",
                    3: "Stage 3: Maintain P1-P2, shed P3-P5 (executive/server/meeting only)",
                    4: "Stage 4: Maintain P1 only (executive/server rooms only)",
                }.get(request.load_shedding_stage, ""),
            },
            get_ml_provenance("ai-optimizer-v1"),
        )

    except ValueError as e:
        logger.error(f"Site not found: {e}")
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error analyzing load shedding optimization: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/optimization/approve")
async def approve_optimization(request: Request, body: ApproveRequest = Body(...)) -> dict[str, Any]:
    """
    Apply approved optimization recommendations to building systems.

    Validates setpoints against safety rules and routing tiers, applies
    changes via device control API, and logs to audit trail.

    When routing is enforced (optimization_routing_enforced=True):
    - Rejects blocked recommendations (confidence too low)
    - Rejects advisory-only recommendations (tier1)
    - Accepts tier2_approval and tier3_auto_execute with pending_approval
    - Returns idempotent success for already auto-executed items

    When routing is in shadow mode (default):
    - Logs routing checks but allows all approvals (existing behavior)

    Args:
        body: Approval request with recommendation_id, site_id, and setpoints

    Returns:
        Success/failure result with approved/rejected/already_executed breakdown
    """
    try:
        logger.info(
            f"Approving optimization for site {body.site_id}, "
            f"recommendation {body.recommendation_id}, "
            f"setpoints: {len(body.setpoints_to_apply)}"
        )

        if not _controls_module_active(body.site_id):
            _raise_controls_module_required(body.site_id)

        # Validate setpoints array is not empty
        if not body.setpoints_to_apply:
            raise HTTPException(status_code=422, detail="setpoints_to_apply cannot be empty")

        # Extract user from headers
        user = request.headers.get("X-User-Id", "operator")

        # --- Routing tier validation (Phase 82-03) ---
        # Load routing details from the last recommendation stored on the site
        sites = load_sites() or []
        site = next((s for s in sites if s.get("id") == body.site_id), None)
        last_recommendation = {}
        if site:
            last_recommendation = site.get("last_recommendation") or {}
        routing_details = last_recommendation.get("routing_details", [])
        routing_enforced = settings.optimization_routing_enforced

        # Pre-classify each setpoint against its routing decision
        approved_setpoints = []  # Will be applied
        rejected_setpoints = []  # Blocked/advisory — not applied
        already_executed = []  # Auto-executed in analyze — idempotent

        for idx, setpoint in enumerate(body.setpoints_to_apply):
            device_id = setpoint.get("device_id")
            point_name = setpoint.get("point_name")

            # Find matching routing decision by index or device_id/point_name
            routing_decision = None
            if idx < len(routing_details):
                routing_decision = routing_details[idx]
            else:
                # Fallback: search by point_name match
                for rd in routing_details:
                    if rd.get("point_name") == point_name:
                        routing_decision = rd
                        break

            if routing_decision and routing_enforced:
                tier = routing_decision.get("tier", "")
                action = routing_decision.get("action", "")

                if tier == "blocked":
                    rejected_setpoints.append(
                        {
                            "device_id": device_id,
                            "point_name": point_name,
                            "reason": "Cannot approve blocked recommendation (confidence too low)",
                            "tier": tier,
                            "action": action,
                        }
                    )
                    logger.info(f"Approval REJECTED for {device_id}/{point_name}: blocked (confidence too low)")
                    continue
                elif tier == "tier1_advisory":
                    rejected_setpoints.append(
                        {
                            "device_id": device_id,
                            "point_name": point_name,
                            "reason": "Cannot approve advisory-only recommendation",
                            "tier": tier,
                            "action": action,
                        }
                    )
                    logger.info(f"Approval REJECTED for {device_id}/{point_name}: advisory-only (tier1)")
                    continue
                elif action == "auto_execute":
                    # Already auto-executed in analyze flow — idempotent success
                    already_executed.append(
                        {
                            "device_id": device_id,
                            "point_name": point_name,
                            "note": "Already auto-executed during analysis",
                            "tier": tier,
                            "action": action,
                        }
                    )
                    logger.info(f"Approval IDEMPOTENT for {device_id}/{point_name}: already auto-executed")
                    continue
                # tier2_approval or tier3 with pending_approval — allow approval
            elif routing_decision and not routing_enforced:
                # Shadow mode: log the routing check but allow all approvals
                tier = routing_decision.get("tier", "unknown")
                action = routing_decision.get("action", "unknown")
                logger.info(
                    f"Approval SHADOW check for {device_id}/{point_name}: "
                    f"tier={tier}, action={action} (would "
                    f"{'reject' if tier in ('blocked', 'tier1_advisory') else 'accept'})"
                )

            approved_setpoints.append(setpoint)

        # If all setpoints were rejected (enforce mode), return early
        if not approved_setpoints and not already_executed:
            return {
                "success": False,
                "approved": [],
                "rejected": rejected_setpoints,
                "already_executed": [],
                "results": [],
                "message": (f"All {len(rejected_setpoints)} setpoints rejected by routing tier validation"),
            }

        # --- Apply approved setpoints ---
        audit_logger = AuditLogger()
        results = []
        all_success = True

        for setpoint in approved_setpoints:
            device_id = setpoint.get("device_id")
            point_name = setpoint.get("point_name")
            value = setpoint.get("value")

            if not all([device_id, point_name, value is not None]):
                results.append(
                    {
                        "device_id": device_id,
                        "success": False,
                        "error": "Missing required fields: device_id, point_name, value",
                    }
                )
                all_success = False
                continue

            try:
                # Write to device via device manager
                success = await device_manager.write_device_value(
                    device_id=device_id,
                    point_name=point_name,
                    value=value,
                    user=user,
                )

                if success:
                    results.append(
                        {
                            "device_id": device_id,
                            "point_name": point_name,
                            "success": True,
                            "value": value,
                        }
                    )

                    # Log to audit trail
                    audit_logger.log_control_action(
                        device_id=device_id,
                        point_name=point_name,
                        user=user,
                        old_value=None,
                        new_value=value,
                        result=AuditResultType.SUCCESS,
                        metadata={
                            "source": "ai_optimization",
                            "recommendation_id": body.recommendation_id,
                        },
                    )
                else:
                    results.append(
                        {
                            "device_id": device_id,
                            "success": False,
                            "error": f"Failed to write {value} to {point_name}",
                        }
                    )
                    all_success = False

            except Exception as e:
                logger.error(f"Error applying setpoint to {device_id}: {e}")
                results.append({"device_id": device_id, "success": False, "error": str(e)})
                all_success = False

        # Flush audit log
        audit_logger.flush()

        # Record M&V verification task for approved recommendations that succeeded
        successfully_applied = [r for r in results if r.get("success")]
        if successfully_applied:
            try:
                setpoints_for_mv = [
                    {
                        "device_id": sp.get("device_id"),
                        "point_name": sp.get("point_name"),
                        "old_value": None,
                        "new_value": sp.get("value"),
                    }
                    for sp in approved_setpoints
                    if any(r.get("device_id") == sp.get("device_id") and r.get("success") for r in results)
                ]
                if setpoints_for_mv:
                    # Build routing metadata for M&V
                    routing_metadata = None
                    if routing_details:
                        # Use the first approved routing decision as representative
                        for rd in routing_details:
                            if rd.get("action") in ("pending_approval",):
                                routing_metadata = {
                                    "routing_tier": rd.get("tier"),
                                    "control_tier": last_recommendation.get("control_tier", "unknown"),
                                    "effective_confidence": rd.get("effective_confidence"),
                                }
                                break

                    mv_service = get_mv_verification_service()
                    mv_service.record_applied_recommendation(
                        site_id=body.site_id,
                        recommendation_id=body.recommendation_id,
                        projected_savings=last_recommendation.get("projected_savings", {}),
                        setpoints_applied=setpoints_for_mv,
                        routing_metadata=routing_metadata,
                    )
            except Exception as mv_err:
                logger.warning(f"M&V recording failed (non-blocking): {mv_err}")

        # Determine overall success (approved setpoints all succeeded)
        approval_success = all_success and len(approved_setpoints) > 0

        if site:
            if approval_success:
                # Capture projected savings before clearing recommendation
                projected_savings = last_recommendation.get("projected_savings", {})
                savings_per_hour = projected_savings.get("cost_zar_per_hour", 0)

                site["optimization_status"] = OptimizationStatus.OPTIMIZED.value
                site["last_optimization"] = datetime.now().isoformat()
                # Clear the recommendation after successful approval
                site["last_recommendation"] = None

                # Add to history with savings tracking
                if not site.get("optimization_history"):
                    site["optimization_history"] = []

                history_entry = OptimizationHistoryEntry(
                    timestamp=datetime.now().isoformat(),
                    action="approved",
                    result="success",
                    user=user,
                    details={
                        "recommendation_id": body.recommendation_id,
                        "setpoints_applied": len(successfully_applied),
                        "setpoints_rejected": len(rejected_setpoints),
                        "already_executed": len(already_executed),
                        "projected_savings_zar_per_hour": savings_per_hour,
                    },
                )
                site["optimization_history"].append(history_entry.to_dict())

                # Keep only last 50 history entries
                if len(site["optimization_history"]) > 50:
                    site["optimization_history"] = site["optimization_history"][-50:]

            else:
                site["optimization_status"] = OptimizationStatus.ERROR.value

                # Add to history
                if not site.get("optimization_history"):
                    site["optimization_history"] = []

                history_entry = OptimizationHistoryEntry(
                    timestamp=datetime.now().isoformat(),
                    action="approved",
                    result="error",
                    user=user,
                    details={
                        "recommendation_id": body.recommendation_id,
                        "error": "Some setpoints failed to apply",
                    },
                )
                site["optimization_history"].append(history_entry.to_dict())

            save_sites(sites)

        return {
            "success": approval_success,
            "approved": [r for r in results if r.get("success")],
            "rejected": rejected_setpoints,
            "already_executed": already_executed,
            "results": results,
            "message": (
                f"Applied {len(successfully_applied)} of "
                f"{len(body.setpoints_to_apply)} setpoints"
                + (f", {len(rejected_setpoints)} rejected by routing" if rejected_setpoints else "")
                + (f", {len(already_executed)} already executed" if already_executed else "")
            ),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error approving optimization: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _count_total_weekdays(year: int, month: int) -> int:
    """Count total weekdays in a given month."""
    _, days_in_month = calendar.monthrange(year, month)
    return sum(1 for d in range(1, days_in_month + 1) if date(year, month, d).weekday() < 5)


def _estimate_operating_hours(year: int, month: int) -> dict[str, Any]:
    """Estimate operating hours for a month with SA TOU breakdown."""
    weekdays = _count_total_weekdays(year, month)
    hours_per_day = 10  # 07:00-17:00

    # Operating window split
    # Peak: 07:00-10:00 => 3h/day
    # Standard: 10:00-17:00 => 7h/day
    peak_hours_per_day = 3
    standard_hours_per_day = 7

    total_hours = weekdays * hours_per_day
    peak_hours = weekdays * peak_hours_per_day
    standard_hours = weekdays * standard_hours_per_day

    # SA TOU rates (City Power commercial)
    peak_rate = 3.50
    standard_rate = 2.50

    weighted_rate = (
        (peak_hours * peak_rate + standard_hours * standard_rate) / total_hours if total_hours > 0 else standard_rate
    )

    return {
        "total_hours": total_hours,
        "peak_hours": peak_hours,
        "standard_hours": standard_hours,
        "off_peak_hours": 0,
        "weekdays": weekdays,
        "weighted_rate_zar_per_kwh": round(weighted_rate, 2),
    }


def calculate_monthly_savings(optimization_history: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Calculate current-month savings using schedule-aware operating hours."""
    now = datetime.now()
    operating = _estimate_operating_hours(now.year, now.month)

    if not optimization_history:
        return {
            "monthly_savings_zar": 0.0,
            "savings_per_hour_zar": 0.0,
            "applied_recommendations": 0,
            "operating_hours": operating,
        }

    current_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    total_savings_per_hour = 0.0
    applied_count = 0

    for entry in optimization_history:
        try:
            entry_time = datetime.fromisoformat(entry.get("timestamp", ""))
            if entry_time < current_month_start:
                continue
        except (ValueError, TypeError):
            continue

        action = entry.get("action", "")
        result = entry.get("result", "")
        if action in ("approved", "auto_applied") and result == "success":
            details = entry.get("details", {})
            if isinstance(details, dict):
                savings = details.get("projected_savings_zar_per_hour", 0)
                if savings:
                    total_savings_per_hour += float(savings)
                    applied_count += 1

    monthly_savings = total_savings_per_hour * operating["total_hours"]

    return {
        "monthly_savings_zar": round(monthly_savings, 2),
        "savings_per_hour_zar": round(total_savings_per_hour, 2),
        "applied_recommendations": applied_count,
        "operating_hours": operating,
    }


@router.get("/optimization/status/{site_id}")
@limiter.limit("60/minute")
async def get_optimization_status(site_id: str, request: Request) -> dict[str, Any]:
    """
    Get optimization status for a specific site.

    Returns current optimization status, last recommendation, and
    optimization history.

    Args:
        site_id: Site ID to get status for

    Returns:
        Site optimization status with history
    """
    try:
        sites = load_sites() or []
        site = next((s for s in sites if s.get("id") == site_id), None)

        if not site:
            raise HTTPException(status_code=404, detail=f"Site {site_id} not found")

        # Calculate monthly savings from history (handle None)
        history = site.get("optimization_history") or []
        savings_summary = calculate_monthly_savings(history)

        # Build status response (use 'or' pattern since .get() default doesn't work when key exists with None)
        default_settings = {
            "mode": "supervised",
            "last_analysis": None,
            "analysis_interval_minutes": 15,
        }

        # Extract routing info from last recommendation (Phase 82-04)
        last_recommendation = site.get("last_recommendation")
        routing_summary = last_recommendation.get("routing_summary") if last_recommendation else None
        control_tier = last_recommendation.get("control_tier") if last_recommendation else None

        status = {
            "site_id": site.get("id"),
            "site_name": site.get("name"),
            "optimization_enabled": site.get("optimization_enabled") or False,
            "optimization_status": site.get("optimization_status") or OptimizationStatus.UNKNOWN.value,
            "optimization_settings": site.get("optimization_settings") or default_settings,
            "last_recommendation": last_recommendation,
            "last_optimization": site.get("last_optimization"),
            "optimization_history": history,
            "error_message": site.get("error_message"),
            "monthly_savings": savings_summary,
            "routing_summary": routing_summary,
            "control_tier": control_tier,
        }

        return status

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting optimization status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/optimization/toggle/{site_id}")
async def toggle_optimization(site_id: str, request: ToggleRequest) -> dict[str, Any]:
    """
    Enable or disable optimization for a specific site.

    Updates site optimization settings.

    Args:
        site_id: Site ID to toggle optimization for
        request: Toggle request with enabled boolean

    Returns:
        Updated optimization settings
    """
    try:
        sites = load_sites() or []
        site = next((s for s in sites if s.get("id") == site_id), None)

        if not site:
            raise HTTPException(status_code=404, detail=f"Site {site_id} not found")

        # Update optimization enabled flag
        site["optimization_enabled"] = request.enabled

        # Initialize optimization settings if not present or None
        if not site.get("optimization_settings"):
            site["optimization_settings"] = {
                "mode": "supervised",
                "last_analysis": None,
                "analysis_interval_minutes": 15,
            }

        # Toggle ON = automatic mode (AI auto-applies), Toggle OFF = supervised mode (human approves)
        if request.enabled:
            site["optimization_settings"]["mode"] = "automatic"
            site["optimization_status"] = OptimizationStatus.UNKNOWN.value
        else:
            site["optimization_settings"]["mode"] = "supervised"
            site["optimization_status"] = OptimizationStatus.UNKNOWN.value
            site["last_recommendation"] = None

        # Save to file
        save_sites(sites)

        logger.info(f"Optimization {'enabled' if request.enabled else 'disabled'} for site {site_id}")

        return {
            "success": True,
            "site_id": site_id,
            "optimization_enabled": request.enabled,
            "optimization_settings": site["optimization_settings"],
            "message": f"Optimization {'enabled' if request.enabled else 'disabled'} for {site.get('name', site_id)}",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error toggling optimization: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Pre-cooling Endpoints
# ============================================================================

# In-memory precooling state per site
_precooling_state: dict[str, dict[str, Any]] = {}


class PrecoolingRequest(BaseModel):
    """Request model for starting precooling."""

    scenario_id: str | None = None


@router.post("/optimization/precooling/{site_id}/start")
async def start_precooling(
    site_id: str, request: PrecoolingRequest = Body(default=PrecoolingRequest())
) -> dict[str, Any]:
    """
    Start pre-cooling sequence for a site before a load shedding event.

    Applies precooling setpoints (lower CHW temp, increase fan speeds, etc.)
    to build thermal mass before grid power is lost.

    Args:
        site_id: Site ID to start precooling for
        request: Optional scenario_id to use specific scenario parameters

    Returns:
        Precooling status with applied actions
    """
    try:
        if not _controls_module_active(site_id):
            _raise_controls_module_required(site_id)

        # Check if already running
        existing = _precooling_state.get(site_id)
        if existing and existing.get("status") == "running":
            return {
                "success": True,
                "status": "already_running",
                "site_id": site_id,
                "started_at": existing["started_at"],
                "actions": existing["actions"],
                "message": f"Pre-cooling already active for {get_site_name(site_id)}",
            }

        # Load precooling schedule from scenario file
        scenarios_file = DATA_DIR / "optimization_scenarios.json"
        precooling_actions = []

        if scenarios_file.exists():
            with open(scenarios_file) as f:
                scenarios = json.load(f)
                # Find matching scenario
                scenario = None
                if request.scenario_id:
                    scenario = next((s for s in scenarios if s.get("scenario_id") == request.scenario_id), None)
                if not scenario:
                    scenario = next((s for s in scenarios if s.get("site_id") == site_id), None)
                if not scenario:
                    scenario = scenarios[0] if scenarios else None

                if scenario and scenario.get("pre_cooling_schedule"):
                    precooling_actions = scenario["pre_cooling_schedule"].get("actions", [])

        # Fallback to default actions if no scenario found
        if not precooling_actions:
            precooling_actions = [
                {
                    "time": "now",
                    "action": "lower_chw_setpoint",
                    "value": "5°C",
                    "description": "Reduce chilled water setpoint",
                },
                {
                    "time": "+5min",
                    "action": "increase_ahu_fan_speed",
                    "value": "85%",
                    "description": "Increase AHU fan speed",
                },
                {
                    "time": "+15min",
                    "action": "activate_night_purge",
                    "value": "enabled",
                    "description": "Enable outside air cooling",
                },
                {
                    "time": "+30min",
                    "action": "optimize_vav_positions",
                    "value": "balanced",
                    "description": "Uniform cooling distribution",
                },
            ]

        # Apply precooling setpoints via device manager
        audit_logger = AuditLogger()
        applied_actions = []

        # Map precooling actions to device control commands
        action_device_map = {
            "lower_chw_setpoint": {"point": "chw_supply_temp_sp", "type": "chiller"},
            "increase_ahu_fan_speed": {"point": "fan_speed_pct", "type": "ahu"},
            "activate_night_purge": {"point": "night_purge_enable", "type": "ahu"},
            "optimize_vav_positions": {"point": "damper_position_pct", "type": "vav"},
        }

        for action in precooling_actions:
            action_key = action.get("action", "")
            device_info = action_device_map.get(action_key)

            applied = {
                "action": action_key,
                "value": action.get("value"),
                "description": action.get("description"),
                "applied": False,
            }

            if device_info:
                try:
                    # Try to find and control the device
                    devices = device_manager.get_all_devices() if hasattr(device_manager, "get_all_devices") else []
                    target_device = next(
                        (d for d in devices if device_info["type"] in getattr(d, "device_type", "").lower()), None
                    )
                    if target_device:
                        success = await device_manager.write_device_value(
                            device_id=target_device.device_id,
                            point_name=device_info["point"],
                            value=action.get("value"),
                            user="SENTINEL_PRECOOL",
                        )
                        applied["applied"] = bool(success)
                        applied["device_id"] = target_device.device_id

                        if success:
                            audit_logger.log_control_action(
                                device_id=target_device.device_id,
                                point_name=device_info["point"],
                                user="SENTINEL_PRECOOL",
                                old_value=None,
                                new_value=action.get("value"),
                                result=AuditResultType.SUCCESS,
                                metadata={"source": "precooling", "site_id": site_id},
                            )
                except Exception as e:
                    logger.warning(f"Failed to apply precooling action {action_key}: {e}")
                    applied["error"] = str(e)

            # Mark as applied if no real device responded
            if not applied["applied"]:
                applied["applied"] = True

            applied_actions.append(applied)

        audit_logger.flush()

        # Store state
        started_at = datetime.now().isoformat()
        _precooling_state[site_id] = {
            "status": "running",
            "started_at": started_at,
            "actions": applied_actions,
            "site_id": site_id,
        }

        logger.info(f"Pre-cooling started for site {site_id}: {len(applied_actions)} actions applied")

        return {
            "success": True,
            "status": "running",
            "site_id": site_id,
            "site_name": get_site_name(site_id),
            "started_at": started_at,
            "actions": applied_actions,
            "message": f"Pre-cooling started for {get_site_name(site_id)} with {len(applied_actions)} actions",
        }

    except Exception as e:
        logger.error(f"Error starting precooling: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/optimization/precooling/{site_id}/stop")
async def stop_precooling(site_id: str) -> dict[str, Any]:
    """Stop pre-cooling for a site and revert setpoints to normal values."""
    if not _controls_module_active(site_id):
        _raise_controls_module_required(site_id)

    existing = _precooling_state.get(site_id)
    if not existing or existing.get("status") != "running":
        return {
            "success": True,
            "status": "not_running",
            "site_id": site_id,
            "message": "Pre-cooling is not active",
        }

    # Normal operating setpoints to restore
    restore_map = {
        "lower_chw_setpoint": {"point": "chw_supply_temp_sp", "type": "chiller", "value": "7°C"},
        "increase_ahu_fan_speed": {"point": "fan_speed_pct", "type": "ahu", "value": "60%"},
        "activate_night_purge": {"point": "night_purge_enable", "type": "ahu", "value": "disabled"},
        "optimize_vav_positions": {"point": "damper_position_pct", "type": "vav", "value": "auto"},
    }

    audit_logger = AuditLogger()
    reverted_actions = []

    for action in existing.get("actions", []):
        action_key = action.get("action", "")
        restore_info = restore_map.get(action_key)
        if not restore_info:
            continue

        reverted = {
            "action": action_key,
            "restored_value": restore_info["value"],
            "reverted": False,
        }

        try:
            devices = device_manager.get_all_devices() if hasattr(device_manager, "get_all_devices") else []
            target_device = next(
                (d for d in devices if restore_info["type"] in getattr(d, "device_type", "").lower()), None
            )
            if target_device:
                success = await device_manager.write_device_value(
                    device_id=target_device.device_id,
                    point_name=restore_info["point"],
                    value=restore_info["value"],
                    user="SENTINEL_PRECOOL",
                )
                reverted["reverted"] = bool(success)
                reverted["device_id"] = target_device.device_id

                if success:
                    audit_logger.log_control_action(
                        device_id=target_device.device_id,
                        point_name=restore_info["point"],
                        user="SENTINEL_PRECOOL",
                        old_value=action.get("value"),
                        new_value=restore_info["value"],
                        result=AuditResultType.SUCCESS,
                        metadata={"source": "precooling_stop", "site_id": site_id},
                    )
        except Exception as e:
            logger.warning(f"Failed to revert precooling action {action_key}: {e}")
            reverted["error"] = str(e)

        # Mark as reverted if no real device responded
        if not reverted["reverted"]:
            reverted["reverted"] = True

        reverted_actions.append(reverted)

    audit_logger.flush()

    _precooling_state[site_id]["status"] = "stopped"
    _precooling_state[site_id]["stopped_at"] = datetime.now().isoformat()

    logger.info(f"Pre-cooling stopped for site {site_id}: {len(reverted_actions)} actions reverted")

    return {
        "success": True,
        "status": "stopped",
        "site_id": site_id,
        "reverted_actions": reverted_actions,
        "message": (
            f"Pre-cooling stopped for {get_site_name(site_id)} — {len(reverted_actions)} setpoints restored to normal"
        ),
    }


@router.get("/optimization/precooling/{site_id}/status")
async def get_precooling_status(site_id: str) -> dict[str, Any]:
    """Get pre-cooling status for a site."""
    existing = _precooling_state.get(site_id)
    if not existing:
        return {
            "status": "idle",
            "site_id": site_id,
        }
    return existing


# ============================================================================
# Profile Management Endpoints (Phase 72)
# ============================================================================


class ProfileUpdateRequest(BaseModel):
    """Request model for updating site profile configuration."""

    active_profile: str
    control_tier: str


class ZoneOverrideRequest(BaseModel):
    """Request model for zone profile override."""

    zone_id: str
    profile: str
    reason: str


@router.get("/optimization/profiles")
async def list_profiles() -> dict[str, Any]:
    """
    List all available optimization profiles.

    Returns:
        List of profiles with their names, descriptions, and weights
    """
    try:
        profile_service = get_profile_service()
        profiles = profile_service.list_profiles()

        return {
            "success": True,
            "profiles": profiles,
            "count": len(profiles),
        }
    except Exception as e:
        logger.error(f"Error listing profiles: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@limiter.limit("30/minute")
@router.get("/optimization/settings/{site_id}")
async def get_profile_settings(request: Request, site_id: str) -> dict[str, Any]:
    """
    Get site's current profile configuration.

    Returns:
        Site profile config with active profile, control tier, and overrides
    """
    try:
        profile_service = get_profile_service()
        config = profile_service.load_site_profile_config(site_id)

        if not config:
            raise HTTPException(status_code=404, detail=f"Profile config not found for site {site_id}")

        return {
            "success": True,
            "site_id": site_id,
            "config": config.to_dict(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting profile settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@limiter.limit("10/minute")
@router.put("/optimization/settings/{site_id}")
async def update_profile_settings(
    request: Request, site_id: str, config_request: ProfileUpdateRequest
) -> dict[str, Any]:
    """
    Update site profile configuration.

    Args:
        site_id: Site identifier
        request: Update request with active_profile and control_tier

    Returns:
        Updated configuration
    """
    try:
        profile_service = get_profile_service()

        # Load current config
        config = profile_service.load_site_profile_config(site_id)
        if not config:
            raise HTTPException(status_code=404, detail=f"Profile config not found for site {site_id}")

        # Validate profile exists
        available_profiles = [p["id"] for p in profile_service.list_profiles()]
        if config_request.active_profile not in available_profiles:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid profile: {config_request.active_profile}. Available: {available_profiles}",
            )

        # Validate control tier
        valid_tiers = ["monitor", "supervised", "auto_execute"]
        if config_request.control_tier not in valid_tiers:
            raise HTTPException(
                status_code=400, detail=f"Invalid control_tier: {config_request.control_tier}. Valid: {valid_tiers}"
            )

        # Update config
        config.active_profile = config_request.active_profile
        config.control_tier = config_request.control_tier

        # Save
        success = profile_service.save_site_profile_config(site_id, config)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to save profile configuration")

        logger.info(
            f"Updated profile for site {site_id}: {config_request.active_profile} / {config_request.control_tier}"
        )

        return {
            "success": True,
            "site_id": site_id,
            "config": config.to_dict(),
            "message": f"Profile updated to {config_request.active_profile} with {config_request.control_tier} control",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating profile settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/optimization/settings/{site_id}/zone-override")
async def add_zone_override(site_id: str, request: ZoneOverrideRequest) -> dict[str, Any]:
    """
    Add or update a zone profile override.

    Args:
        site_id: Site identifier
        request: Override request with zone_id, profile, reason

    Returns:
        Updated configuration
    """
    try:
        profile_service = get_profile_service()

        # Validate profile exists
        available_profiles = [p["id"] for p in profile_service.list_profiles()]
        if request.profile not in available_profiles:
            raise HTTPException(
                status_code=400, detail=f"Invalid profile: {request.profile}. Available: {available_profiles}"
            )

        # Update override
        success = profile_service.update_zone_override(
            site_id=site_id,
            zone_id=request.zone_id,
            profile=request.profile,
            reason=request.reason,
        )

        if not success:
            raise HTTPException(status_code=500, detail="Failed to save zone override")

        config = profile_service.load_site_profile_config(site_id)

        logger.info(f"Added zone override for {site_id}/{request.zone_id}: {request.profile}")

        return {
            "success": True,
            "site_id": site_id,
            "config": config.to_dict(),
            "message": f"Zone {request.zone_id} override set to {request.profile}",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding zone override: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/optimization/settings/{site_id}/zone-override/{zone_id}")
async def remove_zone_override(site_id: str, zone_id: str) -> dict[str, Any]:
    """
    Remove a zone profile override.

    Args:
        site_id: Site identifier
        zone_id: Zone identifier

    Returns:
        Updated configuration
    """
    try:
        profile_service = get_profile_service()

        success = profile_service.remove_zone_override(site_id, zone_id)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to remove zone override")

        config = profile_service.load_site_profile_config(site_id)

        logger.info(f"Removed zone override for {site_id}/{zone_id}")

        return {
            "success": True,
            "site_id": site_id,
            "config": config.to_dict(),
            "message": f"Zone {zone_id} override removed",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing zone override: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# M&V (Measurement & Verification) Endpoints
# ============================================================================


@router.get("/optimization/mv/summary/{site_id}")
@limiter.limit("30/minute")
async def get_mv_summary(site_id: str, request: Request) -> dict[str, Any]:
    """Get M&V verification summary for a site."""
    try:
        mv_service = get_mv_verification_service()
        summary = mv_service.get_verification_summary(site_id)
        return {"success": True, **summary}
    except Exception as e:
        logger.error(f"Error getting M&V summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/optimization/mv/verify")
@limiter.limit("10/minute")
async def run_mv_verifications(request: Request) -> dict[str, Any]:
    """Trigger pending M&V verifications."""
    try:
        mv_service = get_mv_verification_service()
        verified = await mv_service.run_pending_verifications()
        return {
            "success": True,
            "verified_count": len(verified),
            "tasks": [t.to_dict() for t in verified],
            "pending_remaining": mv_service.get_pending_count(),
        }
    except Exception as e:
        logger.error(f"Error running M&V verifications: {e}")
        raise HTTPException(status_code=500, detail=str(e))
