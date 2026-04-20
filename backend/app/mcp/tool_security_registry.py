"""
MCP Tool Security Registry — Canonical Security Classification.

Single source of truth for every MCP tool's security posture.
All other modules (tool_permissions.py, audit.py, rate_limiter.py)
derive their behavior from this registry.

Each tool is tagged with:
  - auth_required: bool — whether SSE transport requires auth (all by default)
  - mutating: bool — modifies state (requires role + module gating)
  - high_risk: bool — requires explicit approval token
  - rate_class: "read" | "mutate" | "search" — rate limit bucket
  - min_role: SentinelRole | None — minimum role for mutating tools
  - required_module: ModuleType | None — module that must be active
  - audit_fields: set[str] — argument fields safe to include in audit logs
  - output_allowed_fields: set[str] | None — output field allowlist (None = no filter)
  - secret_zero_risk: bool — True if tool accepts or returns credentials
"""

from dataclasses import dataclass, field

from app.models.auth import SentinelRole
from app.models.module_registry import ModuleType


@dataclass(frozen=True)
class ToolSecurityProfile:
    """Security classification for a single MCP tool."""

    name: str
    auth_required: bool = True
    mutating: bool = False
    high_risk: bool = False
    rate_class: str = "read"  # "read", "mutate", "search"
    min_role: SentinelRole | None = None
    required_module: ModuleType | None = None
    audit_fields: frozenset = field(default_factory=lambda: frozenset({"site_id", "device_id", "asset_id"}))
    output_allowed_fields: frozenset | None = None  # None = no output filter
    secret_zero_risk: bool = False


# ============================================================================
# Registry — every MCP tool, classified
# ============================================================================

TOOL_REGISTRY: dict[str, ToolSecurityProfile] = {}


def _r(profile: ToolSecurityProfile) -> None:
    """Register a tool profile."""
    TOOL_REGISTRY[profile.name] = profile


# ---------------------------------------------------------------------------
# Read tools — auth required for SSE, no mutation, rate_class="read"
# ---------------------------------------------------------------------------

_r(
    ToolSecurityProfile(
        name="get_sites",
        audit_fields=frozenset({"status_filter", "region"}),
    )
)

_r(
    ToolSecurityProfile(
        name="get_assets",
        audit_fields=frozenset({"site_id", "asset_type", "criticality"}),
    )
)

_r(
    ToolSecurityProfile(
        name="get_asset_detail",
        audit_fields=frozenset({"asset_id", "include"}),
    )
)

_r(
    ToolSecurityProfile(
        name="get_devices",
        audit_fields=frozenset({"site_id", "device_type"}),
    )
)

_r(
    ToolSecurityProfile(
        name="read_device_point",
        audit_fields=frozenset({"device_id", "point_name"}),
    )
)

_r(
    ToolSecurityProfile(
        name="get_alarms",
        audit_fields=frozenset({"site_id", "asset_id", "severity", "state", "limit"}),
    )
)

_r(
    ToolSecurityProfile(
        name="get_trends",
        audit_fields=frozenset({"asset_id", "parameter", "interval"}),
    )
)

_r(
    ToolSecurityProfile(
        name="get_health_score",
        audit_fields=frozenset({"asset_id", "site_id"}),
    )
)

_r(
    ToolSecurityProfile(
        name="get_work_orders",
        audit_fields=frozenset({"site_id", "asset_id", "status", "limit"}),
    )
)

_r(
    ToolSecurityProfile(
        name="list_managed_sites",
        audit_fields=frozenset(),
    )
)

_r(
    ToolSecurityProfile(
        name="get_site_config",
        audit_fields=frozenset({"site_id"}),
    )
)

_r(
    ToolSecurityProfile(
        name="get_asset_metrics_template",
        audit_fields=frozenset({"site_id", "equipment_types"}),
    )
)

# Solar read tools
_r(
    ToolSecurityProfile(
        name="get_solar_overview",
        audit_fields=frozenset({"site_id"}),
    )
)

_r(
    ToolSecurityProfile(
        name="get_bess_status",
        audit_fields=frozenset({"site_id"}),
    )
)

_r(
    ToolSecurityProfile(
        name="get_solar_savings",
        audit_fields=frozenset({"site_id", "period"}),
    )
)

_r(
    ToolSecurityProfile(
        name="get_solar_forecast",
        audit_fields=frozenset({"site_id", "hours"}),
    )
)

_r(
    ToolSecurityProfile(
        name="get_solar_diagnostics",
        audit_fields=frozenset({"site_id"}),
    )
)

# Contract read tools
_r(
    ToolSecurityProfile(
        name="get_contracts",
        audit_fields=frozenset({"site_id", "organization_code", "status"}),
    )
)

_r(
    ToolSecurityProfile(
        name="get_contract_profitability",
        audit_fields=frozenset({"site_code", "year", "month"}),
    )
)

# Utility read tools
_r(
    ToolSecurityProfile(
        name="get_utility_costs",
        audit_fields=frozenset({"site_id", "period_start", "period_end"}),
    )
)

# ---------------------------------------------------------------------------
# Search tools — auth required, rate_class="search"
# ---------------------------------------------------------------------------

_r(
    ToolSecurityProfile(
        name="search_alarms",
        rate_class="search",
        audit_fields=frozenset({"query", "site_id", "limit"}),
    )
)

_r(
    ToolSecurityProfile(
        name="code_search",
        rate_class="search",
        audit_fields=frozenset({"query", "search_type", "base_path"}),
    )
)

# ---------------------------------------------------------------------------
# Code tools — read-only but sensitive (source code access)
# ---------------------------------------------------------------------------

_r(
    ToolSecurityProfile(
        name="code_fetch",
        audit_fields=frozenset({"path"}),
    )
)

_r(
    ToolSecurityProfile(
        name="code_structure",
        audit_fields=frozenset({"path", "depth"}),
    )
)

# ---------------------------------------------------------------------------
# Mutating tools — require auth, role, module
# ---------------------------------------------------------------------------

_r(
    ToolSecurityProfile(
        name="write_device_point",
        mutating=True,
        high_risk=True,
        rate_class="mutate",
        min_role=SentinelRole.OPERATOR,
        required_module=ModuleType.HVAC_CONTROL,
        audit_fields=frozenset({"device_id", "point_name", "priority"}),
    )
)

_r(
    ToolSecurityProfile(
        name="create_work_order",
        mutating=True,
        rate_class="mutate",
        min_role=SentinelRole.OPERATOR,
        required_module=ModuleType.MAINTENANCE,
        audit_fields=frozenset({"site_id", "equipment_id", "priority", "description"}),
    )
)

_r(
    ToolSecurityProfile(
        name="create_site",
        mutating=True,
        high_risk=True,
        rate_class="mutate",
        min_role=SentinelRole.ADMIN,
        required_module=ModuleType.SIMBIOT,
        audit_fields=frozenset({"site_id", "name"}),
    )
)

_r(
    ToolSecurityProfile(
        name="activate_site",
        mutating=True,
        high_risk=True,
        rate_class="mutate",
        min_role=SentinelRole.ADMIN,
        required_module=ModuleType.SIMBIOT,
        audit_fields=frozenset({"site_id"}),
    )
)

_r(
    ToolSecurityProfile(
        name="add_site_zones",
        mutating=True,
        rate_class="mutate",
        min_role=SentinelRole.ADMIN,
        required_module=ModuleType.SIMBIOT,
        audit_fields=frozenset({"site_id"}),
    )
)

_r(
    ToolSecurityProfile(
        name="add_site_desks",
        mutating=True,
        rate_class="mutate",
        min_role=SentinelRole.ADMIN,
        required_module=ModuleType.SIMBIOT,
        audit_fields=frozenset({"site_id"}),
    )
)

_r(
    ToolSecurityProfile(
        name="add_site_devices",
        mutating=True,
        rate_class="mutate",
        min_role=SentinelRole.ADMIN,
        required_module=ModuleType.SIMBIOT,
        audit_fields=frozenset({"site_id"}),
    )
)

_r(
    ToolSecurityProfile(
        name="import_point_list",
        mutating=True,
        rate_class="mutate",
        min_role=SentinelRole.ADMIN,
        required_module=ModuleType.SIMBIOT,
        audit_fields=frozenset({"site_id"}),
    )
)

_r(
    ToolSecurityProfile(
        name="import_controller_list",
        mutating=True,
        rate_class="mutate",
        min_role=SentinelRole.ADMIN,
        required_module=ModuleType.SIMBIOT,
        audit_fields=frozenset({"site_id"}),
    )
)

_r(
    ToolSecurityProfile(
        name="control_dali_device",
        mutating=True,
        rate_class="mutate",
        min_role=SentinelRole.OPERATOR,
        required_module=ModuleType.SIMBIOT,
        audit_fields=frozenset({"equipment_code", "action", "value", "reason", "priority"}),
    )
)

_r(
    ToolSecurityProfile(
        name="discover_tridonic_gateway",
        mutating=True,
        rate_class="mutate",
        min_role=SentinelRole.OPERATOR,
        required_module=ModuleType.SIMBIOT,
        secret_zero_risk=True,  # Accepts username/password for gateway auth
        audit_fields=frozenset({"site_id", "gateway_ip", "gateway_type"}),
        # NEVER log username/password — handled by _ALWAYS_REDACTED in audit.py
    )
)

_r(
    ToolSecurityProfile(
        name="configure_asset_metrics",
        mutating=True,
        rate_class="mutate",
        min_role=SentinelRole.OPERATOR,
        required_module=ModuleType.ASSETS,
        audit_fields=frozenset({"site_id"}),
    )
)

_r(
    ToolSecurityProfile(
        name="add_site_contract",
        mutating=True,
        rate_class="mutate",
        min_role=SentinelRole.ADMIN,
        required_module=ModuleType.FINANCIAL,
        audit_fields=frozenset({"site_code", "contract_type"}),
    )
)

_r(
    ToolSecurityProfile(
        name="process_municipal_bill",
        mutating=True,
        rate_class="mutate",
        min_role=SentinelRole.OPERATOR,
        required_module=ModuleType.ENERGY,
        audit_fields=frozenset({"site_id", "municipality", "utility_type"}),
    )
)


# ============================================================================
# Accessor helpers
# ============================================================================


def get_profile(tool_name: str) -> ToolSecurityProfile | None:
    """Get the security profile for a tool, or None if unregistered."""
    return TOOL_REGISTRY.get(tool_name)


def get_risk_tier(tool_name: str) -> str:
    """Return the risk tier label for a tool.

    Returns:
        "high_risk", "mutating", "search", or "read"
    """
    profile = TOOL_REGISTRY.get(tool_name)
    if not profile:
        return "read"
    if profile.high_risk:
        return "high_risk"
    if profile.mutating:
        return "mutating"
    if profile.rate_class == "search":
        return "search"
    return "read"


def get_audit_fields(tool_name: str) -> set[str]:
    """Get the audit-safe argument fields for a tool."""
    profile = TOOL_REGISTRY.get(tool_name)
    if profile:
        return set(profile.audit_fields)
    return {"site_id", "device_id", "asset_id"}


def is_secret_zero_risk(tool_name: str) -> bool:
    """True if this tool accepts or returns credential-like data."""
    profile = TOOL_REGISTRY.get(tool_name)
    return profile.secret_zero_risk if profile else False
