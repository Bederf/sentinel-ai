"""
Module Registry API - Bolt-on Module System Endpoints

Manages module activation, integration, and AI recommendations.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from app.services.module_registry_service import module_registry
from app.models.module_registry import (
    ModuleType, ModuleStatus, RecommendationPriority, RecommendationType,
    AIRecommendation, MODULE_DEFINITIONS
)

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
async def get_active_modules(site_id: str):
    """Get all active modules for a site."""
    modules = module_registry.get_active_modules(site_id)
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
async def activate_module(request: ActivateModuleRequest):
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
async def deactivate_module(site_id: str, module_type: str):
    """Deactivate a module for a site."""
    try:
        mt = ModuleType(module_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid module type: {module_type}")

    success = module_registry.deactivate_module(site_id, mt)
    if not success:
        raise HTTPException(status_code=404, detail="Module not found or not active")

    return {"status": "deactivated", "module_type": module_type, "site_id": site_id}


@router.get("/site/{site_id}/check/{module_type}")
async def check_module_active(site_id: str, module_type: str):
    """Check if a specific module is active for a site."""
    try:
        mt = ModuleType(module_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid module type: {module_type}")

    is_active = module_registry.is_module_active(site_id, mt)
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
    health_score: float = Query(..., ge=0, le=100)
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
    """Get AI recommendations for a site."""
    module_filter = None
    if modules:
        try:
            module_filter = [ModuleType(m.strip()) for m in modules.split(",")]
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid module type: {e}")

    priority_filter = None
    if priorities:
        try:
            priority_filter = [RecommendationPriority(p.strip()) for p in priorities.split(",")]
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid priority: {e}")

    recs = module_registry.get_recommendations(
        site_id=site_id,
        module_filter=module_filter,
        priority_filter=priority_filter,
        include_resolved=include_resolved,
        limit=limit
    )

    return [
        RecommendationResponse(
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
        )
        for r in recs
    ]


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
