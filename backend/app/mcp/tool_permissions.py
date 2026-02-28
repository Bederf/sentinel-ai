"""
MCP Tool Permission Mapping and Access Control.

Maps mutating MCP tools to their required module types and minimum
auth levels. Mirrors the pattern used in chat_tools.py for consistency.

Usage:
    from app.mcp.tool_permissions import (
        MUTATING_TOOLS,
        check_mcp_tool_access,
        extract_site_id_from_args,
    )
"""

import logging

from app.models.auth import AuthContext, SentinelRole
from app.models.module_registry import ModuleType

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool → Module requirement mapping
# ---------------------------------------------------------------------------

MCP_TOOL_MODULE_REQUIREMENTS: dict[str, ModuleType] = {
    "write_device_point": ModuleType.HVAC_CONTROL,
    "create_work_order": ModuleType.MAINTENANCE,
    "create_building": ModuleType.SIMBIOT,
    "activate_building": ModuleType.SIMBIOT,
    "add_building_zones": ModuleType.SIMBIOT,
    "add_building_desks": ModuleType.SIMBIOT,
    "add_building_devices": ModuleType.SIMBIOT,
    "import_point_list": ModuleType.SIMBIOT,
    "import_controller_list": ModuleType.SIMBIOT,
    "control_dali_device": ModuleType.SIMBIOT,
    "discover_tridonic_gateway": ModuleType.SIMBIOT,
    "configure_asset_metrics": ModuleType.ASSETS,
    "add_building_contract": ModuleType.FINANCIAL,
    "process_municipal_bill": ModuleType.ENERGY,
}

# ---------------------------------------------------------------------------
# Tool → Minimum role requirement
# ---------------------------------------------------------------------------

MCP_TOOL_MIN_ROLE: dict[str, SentinelRole] = {
    "write_device_point": SentinelRole.OPERATOR,
    "create_work_order": SentinelRole.OPERATOR,
    "create_building": SentinelRole.ADMIN,
    "activate_building": SentinelRole.ADMIN,
    "add_building_zones": SentinelRole.ADMIN,
    "add_building_desks": SentinelRole.ADMIN,
    "add_building_devices": SentinelRole.ADMIN,
    "import_point_list": SentinelRole.ADMIN,
    "import_controller_list": SentinelRole.ADMIN,
    "control_dali_device": SentinelRole.OPERATOR,
    "discover_tridonic_gateway": SentinelRole.OPERATOR,
    "configure_asset_metrics": SentinelRole.OPERATOR,
    "add_building_contract": SentinelRole.ADMIN,
    "process_municipal_bill": SentinelRole.OPERATOR,
}

# ---------------------------------------------------------------------------
# Convenience set of all mutating tools
# ---------------------------------------------------------------------------

MUTATING_TOOLS: set[str] = set(MCP_TOOL_MODULE_REQUIREMENTS.keys())

# ---------------------------------------------------------------------------
# Public tools (no auth required even over remote SSE transport)
# Empty = all tools gated for remote transports by default
# ---------------------------------------------------------------------------

PUBLIC_TOOLS: set[str] = set()

# ---------------------------------------------------------------------------
# High-risk tools requiring explicit approval (P8)
# ---------------------------------------------------------------------------

HIGH_RISK_TOOLS: set[str] = {
    "write_device_point",
    "create_building",
    "activate_building",
}


def require_auth_for_tool(tool_name: str) -> bool:
    """Return True if the tool requires auth. All tools gated by default."""
    return tool_name not in PUBLIC_TOOLS


def extract_site_id_from_args(tool_name: str, kwargs: dict) -> str | None:
    """Extract a site/building identifier from tool arguments.

    Tries common parameter names and falls back to extracting the site prefix
    from device/equipment IDs (e.g. ``S002-CHILLER-B1-001`` → ``S002``).

    Returns:
        Site code string or None if not determinable.
    """
    # Direct building/site identifiers
    for key in ("building_id", "building_code", "site_id", "site_code"):
        val = kwargs.get(key)
        if val:
            return str(val)

    # Extract site prefix from device_id / asset_id
    for key in ("device_id", "asset_id", "equipment_id"):
        val = kwargs.get(key)
        if val and "-" in str(val):
            return str(val).split("-", 1)[0]

    return None


def check_mcp_tool_access(
    tool_name: str,
    auth_ctx: AuthContext,
    site_id: str | None,
) -> tuple[bool, str]:
    """Check whether the authenticated user may invoke a mutating MCP tool.

    Performs two checks:
      1. **Role check** — user must meet the tool's minimum role.
      2. **Module check** — the required module must be active for the site
         *and* the user must have access to that module.

    Returns:
        ``(True, "")`` on success, ``(False, reason)`` on denial.
    """
    # 1. Role check
    min_role = MCP_TOOL_MIN_ROLE.get(tool_name)
    if min_role and not auth_ctx.has_role(min_role):
        reason = f"Insufficient role for tool '{tool_name}': requires {min_role.value}, user has {auth_ctx.role.value}"
        logger.warning("MCP access denied: %s user=%s", reason, auth_ctx.user_id)
        return False, reason

    # 2. Module check
    required_module = MCP_TOOL_MODULE_REQUIREMENTS.get(tool_name)
    if required_module and site_id:
        from app.services.module_registry_service import module_registry

        if not module_registry.is_module_active(site_id, required_module):
            reason = f"Module '{required_module.value}' is not active for site '{site_id}' — tool '{tool_name}' blocked"
            logger.warning("MCP access denied: %s user=%s", reason, auth_ctx.user_id)
            return False, reason

        # User-level module access check
        if auth_ctx.email and auth_ctx.role != SentinelRole.ADMIN:
            from app.database.repositories.module_access_repository import (
                get_module_access_repository,
            )

            repo = get_module_access_repository()
            if not repo.has_module_access(
                user_email=auth_ctx.email,
                user_role=auth_ctx.role,
                site_code=site_id,
                module_type=required_module,
            ):
                reason = (
                    f"User '{auth_ctx.email}' does not have access to "
                    f"module '{required_module.value}' on site '{site_id}'"
                )
                logger.warning("MCP access denied: %s", reason)
                return False, reason

    return True, ""
