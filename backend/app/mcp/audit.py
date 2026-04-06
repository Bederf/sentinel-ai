"""
MCP Tool Audit Logging with Redaction (P6) and Policy Decision Records.

Logs MCP tool invocations to the audit system with:
- Per-tool field allowlists (from tool_security_registry)
- Automatic PII redaction via ``_sanitize_log_data()``
- Duration tracking
- Structured ``policy_decision`` field for SIEM querying
"""

import logging
from typing import Any, Optional

from app.middleware.audit_middleware import _sanitize_log_data
from app.services.audit_logger import AuditLogger

logger = logging.getLogger(__name__)

# Fields always stripped (auth internals, secrets)
_ALWAYS_REDACTED: set[str] = {
    "token",
    "authorization",
    "password",
    "secret",
    "username",
    "api_key",
    "apikey",
    "credential",
    "_auth_context",
    "_transport",
    "_approval_token",
}


def _filter_args(tool_name: str, arguments: dict) -> dict:
    """Filter arguments to only include allowlisted fields."""
    from app.mcp.tool_security_registry import get_audit_fields

    allowed = get_audit_fields(tool_name)
    filtered = {}
    for k, v in arguments.items():
        if k in _ALWAYS_REDACTED:
            continue
        if k.startswith("_"):
            continue
        if k in allowed:
            filtered[k] = v
    return filtered


def build_policy_decision(
    tool_name: str,
    user_id: str,
    auth_method: str,
    site_id: Optional[str],
    result: str,
    reason_code: str = "",
) -> dict[str, Any]:
    """Build a structured policy decision record for SIEM querying.

    Args:
        tool_name: Name of the tool.
        user_id: Authenticated user ID.
        auth_method: Auth method used (jwt, mcp_token, api_key).
        site_id: Site/building code if determinable.
        result: "allow" or "deny".
        reason_code: Machine-readable reason (e.g. UNAUTHORIZED, FORBIDDEN,
                     RATE_LIMITED, INVALID_INPUT, APPROVAL_REQUIRED).

    Returns:
        Structured dict suitable for JSON serialization.
    """
    from app.mcp.tool_security_registry import get_profile, get_risk_tier

    profile = get_profile(tool_name)

    decision: dict[str, Any] = {
        "tool": tool_name,
        "risk_tier": get_risk_tier(tool_name),
        "auth_method": auth_method,
        "user": user_id,
        "site_id": site_id,
        "result": result,
    }

    if reason_code:
        decision["reason_code"] = reason_code

    if profile:
        if profile.min_role:
            decision["required_role"] = profile.min_role.value
        if profile.required_module:
            decision["required_module"] = profile.required_module.value
        decision["required_approval"] = profile.high_risk
    else:
        decision["required_approval"] = False

    return decision


def log_mcp_tool_call(
    tool_name: str,
    user_id: str,
    arguments: dict,
    result_code: str,
    duration_ms: float,
    site_id: Optional[str] = None,
    request_id: Optional[str] = None,
    auth_method: str = "unknown",
    policy_result: str = "allow",
    policy_reason: str = "",
) -> None:
    """Log an MCP tool call to the audit system.

    Args:
        tool_name: Name of the tool that was called.
        user_id: Authenticated user ID.
        arguments: Raw tool arguments (will be filtered + redacted).
        result_code: Result status (SUCCESS, UNAUTHORIZED, TIMEOUT, etc).
        duration_ms: Execution duration in milliseconds.
        site_id: Site/building code if determinable.
        request_id: Optional correlation ID.
        auth_method: Auth method used for this request.
        policy_result: "allow" or "deny".
        policy_reason: Machine-readable reason code if denied.
    """
    # 1. Filter to tool-specific allowlist
    safe_args = _filter_args(tool_name, arguments)

    # 2. Apply recursive PII/secret redaction
    safe_args = _sanitize_log_data(safe_args)

    # 3. Build policy decision record
    policy_decision = build_policy_decision(
        tool_name=tool_name,
        user_id=user_id,
        auth_method=auth_method,
        site_id=site_id,
        result=policy_result,
        reason_code=policy_reason,
    )

    metadata: dict[str, Any] = {
        "tool_name": tool_name,
        "result_code": result_code,
        "duration_ms": round(duration_ms, 1),
        "arguments": safe_args,
        "policy_decision": policy_decision,
    }
    if site_id:
        metadata["site_id"] = site_id
    if request_id:
        metadata["request_id"] = request_id

    try:
        audit = AuditLogger()
        audit.log_system_event(
            event_type="mcp_tool_call",
            user=user_id,
            metadata=metadata,
        )
    except Exception:
        # Audit failures must not break tool execution
        logger.exception("Failed to log MCP tool call audit: tool=%s", tool_name)
