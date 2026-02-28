"""Security Health Check API endpoint.

Provides a monitoring endpoint that reports which security modules
are loaded and operational. ADMIN only (level 4).

Phase 137-09.
"""

import logging

from fastapi import APIRouter, Depends

from app.models.auth import AuthContext
from app.security.constants import (
    DIRECT_BLOCK_THRESHOLD,
    LOG_MAX_ENTRIES,
    MAX_CHAT_MESSAGE_LENGTH,
    MAX_UPLOAD_SIZE,
    ROLE_LEVELS,
    TRUST_LEVELS,
)
from app.security.pipeline import require_role

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/security")


@router.get("/health")
async def security_health_check(
    auth: AuthContext = Depends(require_role(4)),
) -> dict:
    """Get security module health status. Requires ADMIN (level 4).

    Returns which security modules are loaded and key configuration.
    """
    modules_status: dict[str, dict] = {}

    # Check each security module
    _check_module(modules_status, "prompt_guard", "app.security.prompt_guard", "score_prompt")
    _check_module(modules_status, "output_filter", "app.security.output_filter", "run_output_filter_pipeline")
    _check_module(modules_status, "document_scanner", "app.security.document_scanner", "validate_and_scan_upload")
    _check_module(modules_status, "tool_policy", "app.security.tool_policy", "get_tool_tier")
    _check_module(modules_status, "trust_levels", "app.security.trust_levels", "get_allowed_trust_levels")
    _check_module(modules_status, "step_up", "app.security.step_up", "require_step_up")
    _check_module(modules_status, "webhook_auth", "app.security.webhook_auth", "verify_whatsapp_webhook")
    _check_module(modules_status, "audit_events", "app.security.audit_events", "write_security_audit")
    _check_module(modules_status, "pipeline", "app.security.pipeline", "require_role")
    _check_module(modules_status, "sse_buffer", "app.security.sse_buffer", "SSESecurityBuffer")

    loaded = sum(1 for m in modules_status.values() if m["loaded"])
    total = len(modules_status)

    # Get last audit event count
    audit_stats = _get_audit_stats()

    return {
        "status": "healthy" if loaded == total else "degraded",
        "modules_loaded": loaded,
        "modules_total": total,
        "modules": modules_status,
        "config": {
            "prompt_guard_threshold": DIRECT_BLOCK_THRESHOLD,
            "max_chat_length": MAX_CHAT_MESSAGE_LENGTH,
            "max_upload_size": MAX_UPLOAD_SIZE,
            "audit_log_max_entries": LOG_MAX_ENTRIES,
            "role_levels": ROLE_LEVELS,
            "trust_levels": TRUST_LEVELS,
        },
        "audit": audit_stats,
    }


def _check_module(status: dict, name: str, module_path: str, key_export: str) -> None:
    """Check if a security module can be imported."""
    try:
        import importlib

        mod = importlib.import_module(module_path)
        has_export = hasattr(mod, key_export)
        status[name] = {"loaded": True, "has_key_export": has_export}
    except Exception as exc:
        status[name] = {"loaded": False, "error": str(exc)}


def _get_audit_stats() -> dict:
    """Get basic audit statistics."""
    try:
        from app.services.audit_logger import AuditLogger

        audit_logger = AuditLogger()
        stats = audit_logger.get_stats()
        return {
            "total_entries": stats.get("total_entries", 0),
            "recent_activity_count": stats.get("recent_activity_count", 0),
        }
    except Exception as exc:
        return {"error": str(exc)}
