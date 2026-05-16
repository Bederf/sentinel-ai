"""
Module Registry API - Bolt-on Module System Endpoints

Manages module activation, integration, and AI recommendations.
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from app.database.repositories.module_access_repository import get_module_access_repository
from app.database.repositories.recommendation_repository import get_recommendation_repository
from app.middleware.auth_middleware import require_auth
from app.models.auth import AuthContext, AuthLevel
from app.models.module_registry import AIRecommendation, ModuleType, RecommendationPriority, RecommendationType
from app.models.recommendation import RecommendationStatus
from app.services.module_registry_service import module_registry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/modules", tags=["modules"])


# ==================== Request/Response Models ====================


class ActivateModuleRequest(BaseModel):
    site_id: str
    site_name: str
    module_type: str
    config: dict | None = None


class ModuleResponse(BaseModel):
    instance_id: str
    site_id: str
    module_type: str
    status: str
    activated_at: str
    health_score: float
    last_telemetry: str | None = None


class ModuleDefinitionResponse(BaseModel):
    module_type: str
    name: str
    version: str
    description: str
    enabled: bool
    mandatory: bool
    capabilities: list[dict]
    integrates_with: list[str]
    telemetry_points: list[str]
    ai_features: list[str]


class RecommendationRequest(BaseModel):
    source_module: str
    recommendation_type: str
    priority: str
    title: str
    description: str
    confidence: float = 0.8
    related_modules: list[str] = []
    telemetry_context: dict = {}
    suggested_action: dict | None = None
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
    related_modules: list[str]
    auto_actionable: bool
    acknowledged: bool
    resolved: bool
    target_equipment: str = ""
    action_type: str = ""
    risk_level: str = "low"
    multi_objective_score: float = 0.0
    expected_impact: dict = {}


class IntegrationSummaryResponse(BaseModel):
    site_id: str
    site_name: str
    active_modules: list[dict]
    active_integrations: list[dict]
    potential_integrations: list[dict]
    ai_enabled: bool
    pending_recommendations: int


# ==================== Module Management Endpoints ====================


def _serialize_module_definition(module_def) -> ModuleDefinitionResponse:
    return ModuleDefinitionResponse(
        module_type=module_def.module_type.value,
        name=module_def.name,
        version=module_def.version,
        description=module_def.description,
        enabled=module_def.enabled,
        mandatory=module_def.mandatory,
        capabilities=[
            {"id": c.capability_id, "name": c.name, "description": c.description} for c in module_def.capabilities
        ],
        integrates_with=[t.value for t in module_def.integrates_with],
        telemetry_points=module_def.telemetry_points,
        ai_features=module_def.ai_features,
    )


@router.get("/registry", response_model=dict[str, ModuleDefinitionResponse])
async def get_module_registry():
    """Get the authoritative module registry payload."""
    return {
        module_type.value: _serialize_module_definition(module_def)
        for module_type, module_def in module_registry.get_module_registry().items()
    }


@router.get("/available", response_model=list[ModuleDefinitionResponse])
async def get_available_modules():
    """Get all available module definitions."""
    modules = module_registry.get_available_modules()
    return [_serialize_module_definition(module_def) for module_def in modules]


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

    return _serialize_module_definition(module_def)


@router.get("/site/{site_id}/active", response_model=list[ModuleResponse])
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
            last_telemetry=m.last_telemetry,
        )
        for m in modules
    ]


@router.get("/status/{site_id}", response_model=list[ModuleResponse])
async def get_modules_status(site_id: str, request: Request):
    """Get module status for a site (alias for /site/{site_id}/active)."""
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
            last_telemetry=m.last_telemetry,
        )
        for m in modules
    ]


@router.post("/activate", response_model=ModuleResponse)
async def activate_module(
    request: ActivateModuleRequest,
    auth: AuthContext = Depends(require_auth(AuthLevel.OPERATOR)),  # Allow operators to toggle modules
):
    """Activate a module for a site."""
    try:
        mt = ModuleType(request.module_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid module type: {request.module_type}")

    instance = module_registry.activate_module(
        site_id=request.site_id, site_name=request.site_name, module_type=mt, config=request.config
    )

    return ModuleResponse(
        instance_id=instance.instance_id,
        site_id=instance.site_id,
        module_type=instance.module_type.value,
        status=instance.status.value,
        activated_at=instance.activated_at,
        health_score=instance.health_score,
        last_telemetry=instance.last_telemetry,
    )


@router.post("/site/{site_id}/deactivate/{module_type}")
async def deactivate_module(
    site_id: str,
    module_type: str,
    auth: AuthContext = Depends(require_auth(AuthLevel.OPERATOR)),  # Allow operators to toggle modules
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
        return {"site_id": site_id, "telemetry": None}
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


@router.get("/site/{site_id}/recommendations", response_model=list[RecommendationResponse])
async def get_recommendations(
    site_id: str,
    modules: str | None = Query(None, description="Comma-separated module types to filter"),
    priorities: str | None = Query(None, description="Comma-separated priorities to filter"),
    limit: int = Query(50, ge=1, le=200),
):
    """Get AI recommendations for a site from the recommendations table.

    Source: recommendations table (AI-OPT operational recommendations).
    NOT predictions table (ML health assessments — those belong in the maintenance panel).
    """
    recommendations: list[RecommendationResponse] = []

    # Normalise site_id to match both formats (S002 and site-002)
    alt_id = None
    if site_id.startswith("site-"):
        num = site_id.split("-")[1]
        alt_id = f"S{num}"
    elif site_id.startswith("S"):
        alt_id = f"site-{site_id[1:].lower()}"

    # Fetch from recommendations table — try both formats
    try:
        rec_repo = get_recommendation_repository()
        recs = []
        for sid in {site_id, alt_id}:
            if not sid:
                continue
            try:
                batch = await rec_repo.get_by_status(
                    site_id=sid,
                    status=RecommendationStatus.PENDING,
                    limit=limit,
                )
                recs.extend(batch)
            except Exception:
                pass

        # Also fetch ai_optimization recs specifically (they get buried by maintenance)
        for sid in {site_id, alt_id}:
            if not sid:
                continue
            try:
                from app.database.supabase_client import get_supabase_client
                client = get_supabase_client()
                ai_batch = client.table("recommendations").select("*").eq("site_id", sid).eq("status", "pending").eq("action_type", "ai_optimization").order("timestamp", desc=True).limit(50).execute()
                from app.models.recommendation import Recommendation
                seen_ids = {r.id for r in recs}
                for row in ai_batch.data or []:
                    if row.get("id") not in seen_ids:
                        recs.append(Recommendation.from_dict(row))
                        seen_ids.add(row.get("id"))
            except Exception:
                pass

        for rec in recs:
            # Map risk_level → priority (AIRecommendationsPanel expects priority)
            risk = rec.risk_level.value if hasattr(rec.risk_level, "value") else str(rec.risk_level)
            priority_map = {"critical": "critical", "high": "high", "medium": "medium", "low": "low"}
            priority = priority_map.get(risk, "medium")

            # Apply module filter
            if modules:
                module_list = [m.strip().lower() for m in modules.split(",")]
                src = rec.source or ""
                if src not in module_list:
                    continue

            # Apply priority filter
            if priorities:
                priority_list = [p.strip().lower() for p in priorities.split(",")]
                if priority not in priority_list:
                    continue

            # Map source → source_module
            source = rec.source or "ai_optimizer"
            source_module_map = {
                "ai_optimizer": "hvac",
                "health_alert": "hvac",
                "financial_roi": "energy",
                "anomaly_detector": "hvac",
            }
            src_module = source_module_map.get(source, "hvac")

            # Title: use reason truncated, or fall back to target_equipment
            if rec.reason:
                title = rec.reason[:80]
                if len(rec.reason) > 80:
                    title = title[:77] + "..."
            else:
                title = f"Recommendation for {rec.target_equipment}"

            rec_type = rec.action_type or "optimization"

            rec_resp = RecommendationResponse(
                recommendation_id=rec.id,
                timestamp=rec.timestamp.isoformat() if isinstance(rec.timestamp, datetime) else str(rec.timestamp),
                source_module=src_module,
                recommendation_type=rec_type,
                priority=priority,
                title=title,
                description=rec.reason or "AI-generated recommendation",
                confidence=rec.get_numeric_confidence(),
                related_modules=[],
                auto_actionable=not rec.requires_approval,
                acknowledged=False,
                resolved=rec.status
                in (
                    RecommendationStatus.EXECUTED,
                    RecommendationStatus.REJECTED,
                    RecommendationStatus.EXPIRED,
                    RecommendationStatus.FAILED,
                    RecommendationStatus.AUTO_EXECUTED,
                    RecommendationStatus.ROLLED_BACK,
                ),
                target_equipment=rec.target_equipment or "",
                action_type=rec.action_type or "",
                risk_level=rec.risk_level or "low",
                multi_objective_score=rec.multi_objective_score or 0.0,
                expected_impact=rec.expected_impact or {},
            )
            recommendations.append(rec_resp)

    except Exception as e:
        logger.warning(f"Failed to fetch recommendations from Supabase: {e}")

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
        auto_actionable=request.auto_actionable,
    )

    module_registry.add_recommendation(site_id, recommendation)

    return {
        "status": "added",
        "recommendation_id": recommendation.recommendation_id,
        "timestamp": recommendation.timestamp,
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
