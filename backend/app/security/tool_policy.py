"""
Tool Authorization Policy.

Enforces per-tool security policies:
    - Three-tier classification: analysis, control, write
    - Default deny for unregistered tools
    - Control tools require step-up authentication
    - Tool result sanitization before context re-entry
    - Server-side raw result storage with reference IDs

Integrates with the existing role/module gating in chat_tools.py
and auth_middleware.py.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import os
import uuid
from typing import Any

from app.security.constants import (
    INDIRECT_BLOCK_THRESHOLD,
    MAX_TOOL_RESULT_CONTEXT_SIZE,
    MAX_TOOL_RESULT_SUMMARY_SIZE,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool Classification Sets
# ---------------------------------------------------------------------------

ANALYSIS_TOOLS: frozenset[str] = frozenset(
    {
        "list_devices",
        "get_device_details",
        "get_system_status",
        "get_optimization_recommendations",
        "get_equipment_health",
        "get_alerts_and_anomalies",
        "get_energy_analysis",
        "get_system_methodology",
        "lookup_desk",
        "diagnose_comfort_complaint",
        "handle_comfort_complaint",
        "review_point_mapping",
        "get_fire_system_status",
        "get_security_status",
        "get_solar_overview",
        "get_bess_status",
        "get_solar_savings",
        "get_solar_diagnostics",
        "get_solar_forecast",
        "get_floor_temperatures",
        "search_documents",
        "process_recommendation",
        # ServiceNow integration tools (Phase 138-02)
        "check_servicenow_status",
        "query_servicenow_incidents",
        "query_servicenow_work_orders",
        "get_servicenow_incident_summary",
        # Phase 183-01
        "get_equipment_service_history",
    }
)

CONTROL_TOOLS: frozenset[str] = frozenset(
    {
        "control_device",
        "adjust_setpoint",
        "reset_equipment_fault",
        "approve_recommendation",
        "reject_recommendation",
    }
)

WRITE_TOOLS: frozenset[str] = frozenset(
    {
        "create_work_order",
        "discover_niagara_points",
        "approve_point_mapping",
        "correct_point_classification",
    }
)

# Union of all registered tool names
REGISTERED_TOOLS: frozenset[str] = ANALYSIS_TOOLS | CONTROL_TOOLS | WRITE_TOOLS

# Tools whose full output is safe to echo into Claude's context
# (no secrets, no user-controlled injection surface)
SAFE_TO_ECHO_TOOLS: frozenset[str] = frozenset(
    {
        "list_devices",
        "get_device_details",
        "get_system_status",
        "get_equipment_health",
        "get_alerts_and_anomalies",
        "get_system_methodology",
        "lookup_desk",
        # ServiceNow tools — read-only data, no secrets (Phase 138-02)
        "check_servicenow_status",
        "query_servicenow_incidents",
        "query_servicenow_work_orders",
        "get_servicenow_incident_summary",
    }
)


# ---------------------------------------------------------------------------
# Server-side raw result store (in-memory, bounded)
# ---------------------------------------------------------------------------

_RAW_RESULT_STORE: dict[str, dict[str, Any]] = {}
_MAX_RAW_RESULTS = 500


def _store_raw_result(result_id: str, tool_name: str, result: Any) -> None:
    """Store raw tool result server-side for debugging/audit."""
    if len(_RAW_RESULT_STORE) >= _MAX_RAW_RESULTS:
        # Evict oldest entry
        oldest_key = next(iter(_RAW_RESULT_STORE))
        del _RAW_RESULT_STORE[oldest_key]
    _RAW_RESULT_STORE[result_id] = {
        "tool_name": tool_name,
        "result": result,
    }


def get_raw_result(result_id: str) -> dict[str, Any] | None:
    """Retrieve a raw result by reference ID (for debugging)."""
    return _RAW_RESULT_STORE.get(result_id)


# ---------------------------------------------------------------------------
# Tier Classification
# ---------------------------------------------------------------------------


def get_tool_tier(tool_name: str) -> str:
    """Return the security tier for a tool.

    Returns:
        "analysis" | "control" | "write" | "unknown"
    """
    if tool_name in ANALYSIS_TOOLS:
        return "analysis"
    if tool_name in CONTROL_TOOLS:
        return "control"
    if tool_name in WRITE_TOOLS:
        return "write"
    return "unknown"


# ---------------------------------------------------------------------------
# Tool Result Summary
# ---------------------------------------------------------------------------


def generate_tool_summary(result: Any, tool_name: str) -> str:
    """Generate a short summary of a tool result for non-safe tools.

    Returns a compact string with key counts, status, and reference info.
    Truncated to MAX_TOOL_RESULT_SUMMARY_SIZE.
    """
    if not isinstance(result, dict):
        return f"[{tool_name}] completed (non-dict result)"

    parts: list[str] = [f"[{tool_name}]"]

    # Status / success
    if "success" in result:
        parts.append(f"success={result['success']}")
    if "status" in result:
        parts.append(f"status={result['status']}")

    # Error
    if "error" in result:
        err = str(result["error"])[:100]
        parts.append(f"error={err}")

    # Counts
    if "count" in result:
        parts.append(f"count={result['count']}")

    # Key field names (without values)
    remaining_keys = [k for k in result.keys() if k not in {"success", "status", "error", "count"}]
    if remaining_keys:
        parts.append(f"fields=[{', '.join(remaining_keys[:10])}]")

    summary = " | ".join(parts)
    return summary[:MAX_TOOL_RESULT_SUMMARY_SIZE]


# ---------------------------------------------------------------------------
# Result Sanitization
# ---------------------------------------------------------------------------


def sanitize_tool_result(
    result: Any,
    tool_name: str,
    result_id: str | None = None,
) -> dict[str, Any]:
    """Sanitize a tool result before it re-enters Claude's context.

    Steps:
        1. Store raw result server-side with reference ID
        2. Scan for secrets (via scan_output_for_secrets)
        3. Scan for injection patterns (indirect source)
        4. SAFE_TO_ECHO_TOOLS: return full scanned result (truncated)
        5. All other tools: return summary only

    Args:
        result: The raw tool result.
        tool_name: Name of the tool that produced the result.
        result_id: Optional reference ID. Generated if not provided.

    Returns:
        Sanitized result dict with ``_result_id`` and optional ``_sanitized`` flag.
    """
    if result_id is None:
        result_id = str(uuid.uuid4())[:12]

    # 1. Store raw result server-side
    _store_raw_result(result_id, tool_name, result)

    # 2. Scan for secrets
    try:
        from app.mcp.schema_validator import scan_output_for_secrets

        scanned = scan_output_for_secrets(tool_name, result)
    except ImportError:
        logger.warning("scan_output_for_secrets not available; passing result through")
        scanned = result

    # 3. Scan for injection patterns in string values
    injection_flagged = False
    if isinstance(scanned, dict):
        try:
            from app.security.prompt_guard import score_prompt

            text_values = " ".join(str(v) for v in scanned.values() if isinstance(v, str))
            if text_values:
                guard_result = score_prompt(text_values, source="indirect")
                if guard_result.score >= INDIRECT_BLOCK_THRESHOLD:
                    injection_flagged = True
                    logger.warning(
                        "TOOL_POLICY: injection detected in %s result (score=%.2f), flagging",
                        tool_name,
                        guard_result.score,
                    )
        except ImportError:
            pass

    # 4/5. Decide output mode
    if tool_name in SAFE_TO_ECHO_TOOLS and not injection_flagged:
        # Full result (truncated to context size limit)
        output = _truncate_result(scanned, MAX_TOOL_RESULT_CONTEXT_SIZE)
        output = _ensure_dict(output)
        output["_result_id"] = result_id
        return output

    # Non-safe or injection-flagged: summary only
    summary = generate_tool_summary(scanned, tool_name)
    sanitized: dict[str, Any] = {
        "_result_id": result_id,
        "_sanitized": True,
        "summary": summary,
    }
    if injection_flagged:
        sanitized["_injection_flagged"] = True
    return sanitized


# ---------------------------------------------------------------------------
# SSRF Protection — BMS IP Validation
# ---------------------------------------------------------------------------

# Known BMS subnets (configurable via env var, comma-separated CIDR)
# Default: common BMS LAN subnets
_KNOWN_BMS_SUBNETS_RAW = os.getenv(
    "KNOWN_BMS_SUBNETS",
    "10.0.0.0/8,172.16.0.0/12,192.168.0.0/16",
)
KNOWN_BMS_SUBNETS: list[ipaddress.IPv4Network] = []
for _cidr in _KNOWN_BMS_SUBNETS_RAW.split(","):
    _cidr = _cidr.strip()
    if _cidr:
        try:
            KNOWN_BMS_SUBNETS.append(ipaddress.IPv4Network(_cidr, strict=False))
        except ValueError:
            logger.warning("Invalid CIDR in KNOWN_BMS_SUBNETS: %s", _cidr)


def validate_bms_ip(ip_str: str) -> tuple[bool, str]:
    """Validate an IP address for BMS device discovery (SSRF protection).

    Blocks:
        - Invalid IP addresses
        - Loopback addresses (127.x.x.x)
        - Link-local addresses (169.254.x.x)
        - Multicast addresses (224.0.0.0/4)
        - Broadcast (255.255.255.255)
        - RFC1918 addresses outside allowed subnets (if KNOWN_BMS_SUBNETS is restrictive)
        - Public IPs (non-private) are always blocked for BMS discovery

    Returns:
        (True, "") if valid, (False, reason) if blocked.
    """
    try:
        addr = ipaddress.IPv4Address(ip_str)
    except (ipaddress.AddressValueError, ValueError):
        return False, f"Invalid IP address: {ip_str}"

    # Block loopback
    if addr.is_loopback:
        return False, "Loopback addresses are not allowed for BMS discovery"

    # Block link-local
    if addr.is_link_local:
        return False, "Link-local addresses are not allowed for BMS discovery"

    # Block multicast
    if addr.is_multicast:
        return False, "Multicast addresses are not allowed for BMS discovery"

    # Block reserved/unspecified
    if addr.is_reserved or addr.is_unspecified:
        return False, "Reserved/unspecified addresses are not allowed for BMS discovery"

    # Block public IPs — BMS devices should only be on private networks
    if not addr.is_private:
        return False, "Public IP addresses are not allowed for BMS discovery"

    # Validate against known BMS subnets
    if KNOWN_BMS_SUBNETS:
        in_allowed_subnet = any(addr in subnet for subnet in KNOWN_BMS_SUBNETS)
        if not in_allowed_subnet:
            return False, f"IP {ip_str} is not in any known BMS subnet"

    return True, ""


# ---------------------------------------------------------------------------
# MCP Code Tools — Admin-Only Gate
# ---------------------------------------------------------------------------

# Tool names that require ADMIN role in MCP context
MCP_ADMIN_ONLY_TOOLS: frozenset[str] = frozenset(
    {
        "code_search",
        "code_fetch",
        "code_structure",
    }
)


def check_mcp_admin_tool_access(tool_name: str, auth_ctx: Any) -> tuple[bool, str]:
    """Check if an MCP tool requires ADMIN role and whether the user has it.

    Args:
        tool_name: The MCP tool being invoked.
        auth_ctx: AuthContext with .role attribute.

    Returns:
        (True, "") if allowed, (False, reason) if blocked.
    """
    if tool_name not in MCP_ADMIN_ONLY_TOOLS:
        return True, ""

    if auth_ctx is None:
        return False, f"Tool '{tool_name}' requires ADMIN role"

    try:
        from app.models.auth import SentinelRole

        if not auth_ctx.has_role(SentinelRole.ADMIN):
            return (
                False,
                f"Tool '{tool_name}' requires ADMIN role (current: {auth_ctx.role.value})",
            )
    except (ImportError, AttributeError):
        return False, f"Tool '{tool_name}' requires ADMIN role (role check unavailable)"

    return True, ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _truncate_result(result: Any, max_size: int) -> Any:
    """Truncate a result to fit within max_size characters when serialized."""
    if not isinstance(result, dict):
        text = str(result)
        return text[:max_size] if len(text) > max_size else result

    serialized = json.dumps(result, default=str)
    if len(serialized) <= max_size:
        return result

    # Truncate: keep structure but trim large values
    truncated = {}
    remaining = max_size
    for key, value in result.items():
        entry = json.dumps({key: value}, default=str)
        if len(entry) <= remaining:
            truncated[key] = value
            remaining -= len(entry)
        else:
            truncated[key] = "[truncated]"
            remaining -= 30
        if remaining <= 0:
            break

    return truncated


def _ensure_dict(value: Any) -> dict[str, Any]:
    """Ensure the value is a dict (wrap if needed)."""
    if isinstance(value, dict):
        return value
    return {"result": value}
