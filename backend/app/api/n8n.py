"""
n8n Workflow API Routes for SENTINEL.

Monitoring and management endpoints for n8n workflow automation.

Auth gating:
    - GET endpoints (status, health, workflows, executions): require_auth(AUTHENTICATED)
    - POST endpoints (activate, deactivate, trigger): require_module(INTEGRATIONS)
"""

import logging

from fastapi import APIRouter, Depends, Query

from app.middleware.auth_middleware import require_auth, require_module
from app.models.auth import AuthContext, AuthLevel
from app.models.module_registry import ModuleType
from app.services.n8n_service import get_n8n_service

logger = logging.getLogger("sentinel.api.n8n")

router = APIRouter(prefix="/api/n8n", tags=["n8n"])


# -----------------------------------------------------------------------
# Status & Health (read-only)
# -----------------------------------------------------------------------


@router.get("/status")
async def get_status(
    auth: AuthContext = Depends(require_auth(AuthLevel.AUTHENTICATED)),
):
    """Quick connection status for System Health badge."""
    service = get_n8n_service()
    if not service.is_configured:
        return service.status.to_dict()
    await service.check_connection()
    return service.status.to_dict()


@router.get("/health")
async def get_health_summary(
    auth: AuthContext = Depends(require_auth(AuthLevel.AUTHENTICATED)),
):
    """Detailed health summary for the System Health dashboard card.

    Shows: active/total workflows, failed executions (24h), recent failures.
    """
    service = get_n8n_service()
    return await service.get_health_summary()


# -----------------------------------------------------------------------
# Workflows (read-only)
# -----------------------------------------------------------------------


@router.get("/workflows")
async def list_workflows(
    active_only: bool = Query(False, description="Only show active workflows"),
    tag: str | None = Query(None, description="Filter by tag name"),
    auth: AuthContext = Depends(require_auth(AuthLevel.AUTHENTICATED)),
):
    """List all n8n workflows."""
    service = get_n8n_service()
    return await service.list_workflows(active_only=active_only, tag=tag)


@router.get("/workflows/{workflow_id}")
async def get_workflow(
    workflow_id: str,
    auth: AuthContext = Depends(require_auth(AuthLevel.AUTHENTICATED)),
):
    """Get detailed workflow info."""
    service = get_n8n_service()
    return await service.get_workflow(workflow_id)


# -----------------------------------------------------------------------
# Executions (read-only debugging)
# -----------------------------------------------------------------------


@router.get("/executions")
async def list_executions(
    workflow_id: str | None = Query(None, description="Filter by workflow"),
    status: str | None = Query(None, description="Filter: success, error, waiting"),
    limit: int = Query(20, ge=1, le=100),
    auth: AuthContext = Depends(require_auth(AuthLevel.AUTHENTICATED)),
):
    """List recent workflow executions."""
    service = get_n8n_service()
    return await service.list_executions(
        workflow_id=workflow_id,
        status=status,
        limit=limit,
    )


@router.get("/executions/{execution_id}")
async def get_execution(
    execution_id: str,
    auth: AuthContext = Depends(require_auth(AuthLevel.AUTHENTICATED)),
):
    """Get detailed execution info including per-node results.

    Used for debugging failed workflows.
    """
    service = get_n8n_service()
    return await service.get_execution(execution_id)


# -----------------------------------------------------------------------
# Workflow Control (requires INTEGRATIONS module)
# -----------------------------------------------------------------------


@router.post("/workflows/{workflow_id}/activate")
async def activate_workflow(
    workflow_id: str,
    auth: AuthContext = Depends(require_module(ModuleType.INTEGRATIONS)),
):
    """Activate a workflow. Requires Integrations module."""
    service = get_n8n_service()
    return await service.activate_workflow(workflow_id)


@router.post("/workflows/{workflow_id}/deactivate")
async def deactivate_workflow(
    workflow_id: str,
    auth: AuthContext = Depends(require_module(ModuleType.INTEGRATIONS)),
):
    """Deactivate a workflow. Requires Integrations module."""
    service = get_n8n_service()
    return await service.deactivate_workflow(workflow_id)


# -----------------------------------------------------------------------
# Webhook Triggers (requires INTEGRATIONS module)
# -----------------------------------------------------------------------


@router.post("/trigger/{webhook_path:path}")
async def trigger_webhook(
    webhook_path: str,
    payload: dict | None = None,
    test: bool = Query(False, description="Use test webhook URL"),
    auth: AuthContext = Depends(require_module(ModuleType.INTEGRATIONS)),
):
    """Trigger an n8n workflow via webhook.

    Used by the event bus to dispatch contractor notifications,
    email pipelines, etc. Requires Integrations module.
    """
    if payload is None:
        payload = {}
    service = get_n8n_service()
    return await service.trigger_webhook(webhook_path, payload, test=test)
