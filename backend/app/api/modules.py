"""
Module Registry API - Bolt-on Module System Endpoints

Manages module activation, integration, and AI recommendations.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from app.services.module_registry_service import module_registry
from app.database.repositories.module_access_repository import get_module_access_repository
from app.models.module_registry import (
    ModuleType, ModuleStatus, RecommendationPriority, RecommendationType,
    AIRecommendation, MODULE_DEFINITIONS
)
from app.middleware.auth_middleware import require_auth
from app.models.auth import AuthContext, AuthLevel
from app.database.supabase_client import get_supabase_client
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/modules", tags=["modules"])


# ==================== Request/Response Models ====================

class ActivateModuleRequest(BaseModel):
    site_id: str
    site_name: str
    module_type: str
    config: Optional[dict] = None


class ModuleResponse(BaseModel):
    instance_id: str
    site_id: str
    module_type: str
    status: str
    activated_at: str
    health_score: float
    last_telemetry: Optional[str] = None


class ModuleDefinitionResponse(BaseModel):
    module_type: str
    name: str
    version: str
    description: str
    capabilities: List[dict]
    integrates_with: List[str]
    ai_features: List[str]


class RecommendationRequest(BaseModel):
    source_module: str
    recommendation_type: str
    priority: str
    title: str
    description: str
    confidence: float = 0.8
    related_modules: List[str] = []
    telemetry_context: dict = {}
    suggested_action: Optional[dict] = None
    auto_actionable: bool = False


class RecommendationResponse(BaseModel):
    recommendation_id: str
    timestamp: str
    source_module: str
    recommendation_type: str
    priority: str
    title: str
    description: str
    confidence: float
    related_modules: List[str]
    auto_actionable: bool
    acknowledged: bool
    resolved: bool


class IntegrationSummaryResponse(BaseModel):
    site_id: str
    site_name: str
    active_modules: List[dict]
    active_integrations: List[dict]
    potential_integrations: List[dict]
    ai_enabled: bool
    pending_recommendations: int


# ==================== Module Management Endpoints ====================

@router.get("/available", response_model=List[ModuleDefinitionResponse])
async def get_available_modules():
    """Get all available module definitions."""
    modules = module_registry.get_available_modules()
    return [
        ModuleDefinitionResponse(
            module_type=m.module_type.value,
            name=m.name,
            version=m.version,
            description=m.description,
            capabilities=[
                {"id": c.capability_id, "name": c.name, "description": c.description}
                for c in m.capabilities
            ],
            integrates_with=[t.value for t in m.integrates_with],
            ai_features=m.ai_features
        )
        for m in modules
    ]


@router.get("/definition/{module_type}", response_model=ModuleDefinitionResponse)
async def get_module_definition(module_type: str):
    """Get definition for a specific module type."""
    try:
        mt = ModuleType(module_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid module type: {module_type}")

    module_def = module_registry.get_module_definition(mt)
    if not module_def:
        raise HTTPException(status_code=404, detail="Module definition not found")

    return ModuleDefinitionResponse(
        module_type=module_def.module_type.value,
        name=module_def.name,
        version=module_def.version,
        description=module_def.description,
        capabilities=[
            {"id": c.capability_id, "name": c.name, "description": c.description}
            for c in module_def.capabilities
        ],
        integrates_with=[t.value for t in module_def.integrates_with],
        ai_features=module_def.ai_features
    )


@router.get("/site/{site_id}/active", response_model=List[ModuleResponse])
async def get_active_modules(site_id: str, request: Request):
    """Get all active modules for a site."""
    modules = module_registry.get_active_modules(site_id)
    auth_ctx = getattr(request.state, "auth", None)
    if auth_ctx and getattr(auth_ctx, "email", None):
        repo = get_module_access_repository()
        modules = [
            module
            for module in modules
            if repo.has_module_access(
                user_email=auth_ctx.email,
                user_role=auth_ctx.role,
                site_code=site_id,
                module_type=module.module_type,
            )
        ]
    return [
        ModuleResponse(
            instance_id=m.instance_id,
            site_id=m.site_id,
            module_type=m.module_type.value,
            status=m.status.value,
            activated_at=m.activated_at,
            health_score=m.health_score,
            last_telemetry=m.last_telemetry
        )
        for m in modules
    ]


@router.post("/activate", response_model=ModuleResponse)
async def activate_module(
    request: ActivateModuleRequest,
    auth: AuthContext = Depends(require_auth(AuthLevel.ADMIN)),
):
    """Activate a module for a site."""
    try:
        mt = ModuleType(request.module_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid module type: {request.module_type}")

    instance = module_registry.activate_module(
        site_id=request.site_id,
        site_name=request.site_name,
        module_type=mt,
        config=request.config
    )

    return ModuleResponse(
        instance_id=instance.instance_id,
        site_id=instance.site_id,
        module_type=instance.module_type.value,
        status=instance.status.value,
        activated_at=instance.activated_at,
        health_score=instance.health_score,
        last_telemetry=instance.last_telemetry
    )


@router.post("/site/{site_id}/deactivate/{module_type}")
async def deactivate_module(
    site_id: str,
    module_type: str,
    auth: AuthContext = Depends(require_auth(AuthLevel.ADMIN)),
):
    """Deactivate a module for a site."""
    try:
        mt = ModuleType(module_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid module type: {module_type}")

    try:
        success = module_registry.deactivate_module(site_id, mt)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    if not success:
        raise HTTPException(status_code=404, detail="Module not found or not active")

    return {"status": "deactivated", "module_type": module_type, "site_id": site_id}


@router.get("/site/{site_id}/check/{module_type}")
async def check_module_active(site_id: str, module_type: str, request: Request):
    """Check if a specific module is active for a site."""
    try:
        mt = ModuleType(module_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid module type: {module_type}")

    is_active = module_registry.is_module_active(site_id, mt)
    if is_active:
        auth_ctx = getattr(request.state, "auth", None)
        if auth_ctx and getattr(auth_ctx, "email", None):
            repo = get_module_access_repository()
            is_active = repo.has_module_access(
                user_email=auth_ctx.email,
                user_role=auth_ctx.role,
                site_code=site_id,
                module_type=mt,
            )
    return {"site_id": site_id, "module_type": module_type, "active": is_active}


# ==================== Integration Endpoints ====================

@router.get("/site/{site_id}/integration", response_model=IntegrationSummaryResponse)
async def get_integration_summary(site_id: str):
    """Get module integration summary for a site."""
    summary = module_registry.get_integration_summary(site_id)
    if "error" in summary:
        raise HTTPException(status_code=404, detail=summary["error"])
    return IntegrationSummaryResponse(**summary)


@router.get("/site/{site_id}/telemetry")
async def get_unified_telemetry(site_id: str):
    """Get unified telemetry from all active modules."""
    telemetry = module_registry.get_unified_telemetry(site_id)
    if not telemetry:
        raise HTTPException(status_code=404, detail="Site not configured")
    return telemetry


@router.post("/site/{site_id}/health/{module_type}")
async def update_module_health(
    site_id: str,
    module_type: str,
    health_score: float = Query(..., ge=0, le=100),
    auth: AuthContext = Depends(require_auth(AuthLevel.ADMIN)),
):
    """Update health score for a module."""
    try:
        mt = ModuleType(module_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid module type: {module_type}")

    module_registry.update_module_health(site_id, mt, health_score)
    return {"status": "updated", "module_type": module_type, "health_score": health_score}


# ==================== AI Recommendations Endpoints ====================

@router.get("/site/{site_id}/recommendations", response_model=List[RecommendationResponse])
async def get_recommendations(
    site_id: str,
    modules: Optional[str] = Query(None, description="Comma-separated module types to filter"),
    priorities: Optional[str] = Query(None, description="Comma-separated priorities to filter"),
    include_resolved: bool = False,
    limit: int = Query(50, ge=1, le=200)
):
    """Get AI recommendations for a site from Supabase predictions."""

    # Fetch from Supabase predictions table
    recommendations = []
    try:
        client = get_supabase_client()
        if not client:
            logger.warning("Supabase client not available, skipping predictions fetch")
        else:
            # Get building ID from site code
            building_response = client.table("buildings").select("id").eq("code", site_id).limit(1).execute()
            if not building_response.data:
                # Try with 'sandton' mapping for legacy support
                if site_id == "site-002":
                    building_response = client.table("buildings").select("id").ilike("name", "%sandton%").limit(1).execute()

            if building_response.data:
                building_id = building_response.data[0]["id"]

                # Query predictions with active status
                query = client.table("predictions").select(
                    "id, code, equipment_id, prediction_type, probability_percent, "
                    "recommended_action, urgency, severity, status, created_at, "
                    "evidence, contributing_factors"
                ).eq("building_id", building_id)

                if not include_resolved:
                    query = query.eq("status", "active")

                query = query.order("probability_percent", desc=True).limit(limit)

                pred_response = query.execute()

                # Get equipment names
                equipment_ids = [p["equipment_id"] for p in pred_response.data if p.get("equipment_id")]
                equipment_names = {}
                if equipment_ids:
                    eq_response = client.table("equipment").select("id, name, type").in_("id", equipment_ids).execute()
                    equipment_names = {e["id"]: e for e in eq_response.data}

                # Convert predictions to recommendations
                for pred in pred_response.data:
                    eq_info = equipment_names.get(pred.get("equipment_id"), {})
                    eq_name = eq_info.get("name", "Unknown Equipment")
                    eq_type = eq_info.get("type", "").lower()

                    # Map urgency to priority
                    urgency = pred.get("urgency", "routine")
                    if urgency == "immediate" or pred.get("severity") == "critical":
                        priority = "critical"
                    elif urgency == "soon" or pred.get("severity") == "warning":
                        priority = "high"
                    elif urgency == "scheduled":
                        priority = "medium"
                    else:
                        priority = "low"

                    # Map equipment type to module
                    if eq_type in ["chiller", "ahu", "fcu", "vav", "pump"]:
                        source_module = "hvac"
                    elif eq_type in ["luminaire", "lighting", "dali"]:
                        source_module = "lighting"
                    elif eq_type in ["generator", "ups", "transformer", "meter"]:
                        source_module = "energy"
                    else:
                        source_module = "hvac"  # Default

                    # Apply filters
                    if modules:
                        module_list = [m.strip().lower() for m in modules.split(",")]
                        if source_module not in module_list:
                            continue

                    if priorities:
                        priority_list = [p.strip().lower() for p in priorities.split(",")]
                        if priority not in priority_list:
                            continue

                    recommendations.append(RecommendationResponse(
                        recommendation_id=pred["code"],
                        timestamp=pred.get("created_at", datetime.now().isoformat()),
                        source_module=source_module,
                        recommendation_type="maintenance",
                        priority=priority,
                        title=f"{eq_name}: {pred.get('prediction_type', 'Issue Detected')}",
                        description=pred.get("recommended_action", "Review equipment status"),
                        confidence=min(pred.get("probability_percent", 50) / 100, 1.0),
                        related_modules=[],
                        auto_actionable=False,
                        acknowledged=False,
                        resolved=pred.get("status") == "resolved"
                    ))

    except Exception as e:
        logger.warning(f"Failed to fetch recommendations from Supabase: {e}")

    # Also try module registry for any additional recommendations
    try:
        module_filter = None
        if modules:
            try:
                module_filter = [ModuleType(m.strip()) for m in modules.split(",")]
            except ValueError:
                pass

        priority_filter = None
        if priorities:
            try:
                priority_filter = [RecommendationPriority(p.strip()) for p in priorities.split(",")]
            except ValueError:
                pass

        registry_recs = module_registry.get_recommendations(
            site_id=site_id,
            module_filter=module_filter,
            priority_filter=priority_filter,
            include_resolved=include_resolved,
            limit=limit
        )

        for r in registry_recs:
            # Avoid duplicates
            if not any(rec.recommendation_id == r.recommendation_id for rec in recommendations):
                recommendations.append(RecommendationResponse(
                    recommendation_id=r.recommendation_id,
                    timestamp=r.timestamp,
                    source_module=r.source_module.value,
                    recommendation_type=r.recommendation_type.value,
                    priority=r.priority.value,
                    title=r.title,
                    description=r.description,
                    confidence=r.confidence,
                    related_modules=[m.value for m in r.related_modules],
                    auto_actionable=r.auto_actionable,
                    acknowledged=r.acknowledged,
                    resolved=r.resolved
                ))
    except Exception as e:
        logger.warning(f"Failed to fetch recommendations from module registry: {e}")

    return recommendations[:limit]


@router.post("/site/{site_id}/recommendations")
async def add_recommendation(site_id: str, request: RecommendationRequest):
    """Add an AI recommendation for a site."""
    try:
        source_module = ModuleType(request.source_module)
        rec_type = RecommendationType(request.recommendation_type)
        priority = RecommendationPriority(request.priority)
        related = [ModuleType(m) for m in request.related_modules]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid enum value: {e}")

    import uuid
    recommendation = AIRecommendation(
        recommendation_id=f"rec-{uuid.uuid4().hex[:8]}",
        timestamp=datetime.utcnow().isoformat(),
        source_module=source_module,
        recommendation_type=rec_type,
        priority=priority,
        title=request.title,
        description=request.description,
        confidence=request.confidence,
        related_modules=related,
        telemetry_context=request.telemetry_context,
        suggested_action=request.suggested_action,
        auto_actionable=request.auto_actionable
    )

    module_registry.add_recommendation(site_id, recommendation)

    return {
        "status": "added",
        "recommendation_id": recommendation.recommendation_id,
        "timestamp": recommendation.timestamp
    }


@router.post("/site/{site_id}/recommendations/{recommendation_id}/acknowledge")
async def acknowledge_recommendation(site_id: str, recommendation_id: str):
    """Acknowledge a recommendation."""
    success = module_registry.acknowledge_recommendation(site_id, recommendation_id)
    if not success:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    return {"status": "acknowledged", "recommendation_id": recommendation_id}


@router.post("/site/{site_id}/recommendations/{recommendation_id}/resolve")
async def resolve_recommendation(site_id: str, recommendation_id: str):
    """Resolve a recommendation."""
    success = module_registry.resolve_recommendation(site_id, recommendation_id)
    if not success:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    return {"status": "resolved", "recommendation_id": recommendation_id}
