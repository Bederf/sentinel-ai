"""Agent Security Middleware — Phase 120-05: Unified Pipeline.

Connects all agent security components (policy engine, rate limiter,
circuit breaker, verification runner) into a single FastAPI middleware.

Pipeline for bot agent requests:
  auth → breaker check → rate limit → policy evaluate → execute → audit → verify

Non-bot requests pass through unchanged.
"""

import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.middleware.agent_security.circuit_breaker import (
    QuotaTier,
    circuit_breaker,
    rate_limiter,
)
from app.middleware.agent_security.models import (
    AgentSession,
    AgentToolName,
)
from app.middleware.agent_security.policy_engine import (
    PolicyDecision,
    policy_engine,
)
from app.middleware.agent_security.verification import verification_runner
from app.models.auth import SentinelRole

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Path → Tool mapping
# ---------------------------------------------------------------------------

PATH_TOOL_MAP: list[tuple[str, AgentToolName]] = [
    # BMS_READ — read-only telemetry and building data
    ("/api/equipment/search", AgentToolName.BMS_READ),
    ("/api/equipment/telemetry", AgentToolName.BMS_READ),
    ("/api/alerts", AgentToolName.BMS_READ),
    ("/api/predictions", AgentToolName.BMS_READ),
    ("/api/buildings", AgentToolName.BMS_READ),
    # WORK_ORDERS
    ("/api/work-orders", AgentToolName.WORK_ORDERS),
    ("/api/sentry/work-order", AgentToolName.WORK_ORDERS),
    # EQUIPMENT_CONTROL — setpoints, resets, dispatch
    ("/api/devices/control", AgentToolName.EQUIPMENT_CONTROL),
    ("/api/equipment/reset", AgentToolName.EQUIPMENT_CONTROL),
    ("/api/equipment/setpoint", AgentToolName.EQUIPMENT_CONTROL),
    ("/api/dispatch-optimizer", AgentToolName.EQUIPMENT_CONTROL),
    # TELEGRAM_BOT
    ("/api/sentry", AgentToolName.TELEGRAM_BOT),
    ("/api/telegram", AgentToolName.TELEGRAM_BOT),
    # EMAIL_SMTP
    ("/api/notifications/email", AgentToolName.EMAIL_SMTP),
    ("/api/reports/email", AgentToolName.EMAIL_SMTP),
    # SHELL
    ("/api/ml/execute", AgentToolName.SHELL),
    # DATABASE_WRITE
    ("/api/data/write", AgentToolName.DATABASE_WRITE),
    ("/api/predictions/write", AgentToolName.DATABASE_WRITE),
    # MCP_EXPOSE
    ("/api/mcp", AgentToolName.MCP_EXPOSE),
]

# Paths that bypass agent security entirely
BYPASS_PREFIXES: tuple[str, ...] = (
    "/api/auth/",
    "/api/health",
    "/api/buildings",
    "/api/work-orders",
    "/api/chat",
    "/health",
    "/docs",
    "/openapi.json",
    "/redoc",
)

# Agent-sensitive prefixes for startup route cross-check
AGENT_SENSITIVE_PREFIXES: tuple[str, ...] = (
    "/api/equipment/",
    "/api/work-orders/",
    "/api/devices/",
    "/api/sentry/",
    "/api/mcp/",
    "/api/dispatch-optimizer/",
)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _resolve_tool(path: str) -> AgentToolName | None:
    """Map a request path to an AgentToolName via prefix matching.

    Returns None for bypass paths or paths not in PATH_TOOL_MAP.
    """
    # Check bypass first
    if path.startswith(BYPASS_PREFIXES):
        return None

    # Longest-prefix match: PATH_TOOL_MAP entries are ordered from most
    # specific to least specific within each tool group, so first match wins.
    for prefix, tool in PATH_TOOL_MAP:
        if path.startswith(prefix):
            return tool

    return None


def _resolve_quota_tier(role) -> QuotaTier:
    """Map a SentinelRole to a QuotaTier for rate limiting."""
    if role == SentinelRole.BOT_AGENT or role == SentinelRole.BOT_AGENT.value:
        return QuotaTier.PER_BOT
    if role in (SentinelRole.ADMIN, SentinelRole.ADMIN.value, SentinelRole.OPERATOR, SentinelRole.OPERATOR.value):
        return QuotaTier.PER_USER
    return QuotaTier.PER_AGENT


def _build_session(auth_context, site_id: str | None = None) -> AgentSession:
    """Build an AgentSession from an AuthContext."""
    site_ids = []
    if site_id:
        site_ids = [site_id]

    return AgentSession(
        owner_id=auth_context.user_id,
        role=auth_context.role.value if hasattr(auth_context.role, "value") else str(auth_context.role),
        tenant_id=getattr(auth_context, "metadata", {}).get("tenant_id", "default"),
        site_ids=site_ids,
    )


def _extract_site_id(request: Request) -> str | None:
    """Try to extract a site_id from path params or query string."""
    # Check query parameters
    site_id = request.query_params.get("site_id")
    if site_id:
        return site_id

    # Check path for common patterns like /api/buildings/{id}/...
    path_parts = request.url.path.strip("/").split("/")
    if "sites" in path_parts:
        idx = path_parts.index("sites")
        if idx + 1 < len(path_parts):
            return path_parts[idx + 1]

    return None


# ---------------------------------------------------------------------------
# Startup route cross-check
# ---------------------------------------------------------------------------


def check_unmapped_routes(app) -> None:
    """Log warnings for agent-sensitive routes not covered by PATH_TOOL_MAP.

    Iterates all registered FastAPI routes and checks whether routes matching
    AGENT_SENSITIVE_PREFIXES are covered by at least one PATH_TOOL_MAP entry.
    """
    tool_prefixes = [prefix for prefix, _tool in PATH_TOOL_MAP]

    for route in app.routes:
        path = getattr(route, "path", None)
        if not path:
            continue

        # Only check routes matching agent-sensitive prefixes
        is_sensitive = any(path.startswith(p) for p in AGENT_SENSITIVE_PREFIXES)
        if not is_sensitive:
            continue

        # Check if covered by PATH_TOOL_MAP
        covered = any(path.startswith(tp) for tp in tool_prefixes)
        if not covered:
            logger.warning(
                "Unmapped agent-sensitive route: %s — bypasses policy gate",
                path,
            )


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


class AgentSecurityMiddleware(BaseHTTPMiddleware):
    """Unified agent security pipeline.

    Only gates requests from bot agents (is_bot_agent=True in AuthContext).
    Human users pass through unchanged.

    Pipeline:
    1. Skip bypass paths
    2. Resolve tool from path
    3. Check auth context — non-bot passes through
    4. Circuit breaker check
    5. Rate limiter check (tool calls + tool-specific quotas)
    6. Policy engine evaluate
    7. Execute request
    8. Record success/failure for circuit breaker
    9. Post-action verification (alert-only, no blocking)
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Step a: Skip bypass paths
        if path.startswith(BYPASS_PREFIXES):
            return await call_next(request)

        # Step b: Resolve tool from path
        tool = _resolve_tool(path)

        # Step c: Extract auth context — may not exist
        auth_context = getattr(request.state, "auth", None)

        # Step d: Non-bot requests pass through
        if auth_context is None or not getattr(auth_context, "is_bot_agent", False):
            return await call_next(request)

        # --- From here, request is from a bot agent ---
        agent_id = auth_context.user_id
        action = request.method

        # Step e: Circuit breaker check
        breaker_result = circuit_breaker.check(agent_id)
        if not breaker_result.allowed:
            logger.warning(
                "agent_security.breaker_open agent_id=%s reason=%s",
                agent_id,
                breaker_result.reason,
            )
            return JSONResponse(
                status_code=429,
                content={
                    "detail": f"Circuit breaker open: {breaker_result.reason}",
                    "state": breaker_result.state.value,
                },
            )

        # Step f: Rate limiter — tool call quota
        tier = _resolve_quota_tier(auth_context.role)
        rate_result = rate_limiter.check_tool_call(agent_id, tier)
        if not rate_result.allowed:
            logger.warning(
                "agent_security.rate_limit agent_id=%s reason=%s",
                agent_id,
                rate_result.reason,
            )
            headers = {}
            if rate_result.retry_after_seconds is not None:
                headers["Retry-After"] = str(int(rate_result.retry_after_seconds) + 1)
            return JSONResponse(
                status_code=429,
                content={"detail": rate_result.reason},
                headers=headers,
            )

        # Step g: Tool-specific rate checks
        if tool == AgentToolName.EMAIL_SMTP:
            email_result = rate_limiter.check_email(agent_id, tier)
            if not email_result.allowed:
                headers = {}
                if email_result.retry_after_seconds is not None:
                    headers["Retry-After"] = str(int(email_result.retry_after_seconds) + 1)
                return JSONResponse(
                    status_code=429,
                    content={"detail": email_result.reason},
                    headers=headers,
                )

        if tool == AgentToolName.SHELL:
            shell_result = rate_limiter.check_shell(agent_id, tier)
            if not shell_result.allowed:
                return JSONResponse(
                    status_code=429,
                    content={"detail": shell_result.reason},
                )

        # If tool is None (path not in map), pass through for bot agents
        # that hit unmapped paths — the policy engine only runs for mapped tools
        if tool is None:
            return await call_next(request)

        # Step h: Build AgentSession
        site_id = _extract_site_id(request)
        session = _build_session(auth_context, site_id)

        # Step i: Policy engine evaluate
        policy_result = policy_engine.evaluate(
            session=session,
            tool=tool,
            action=action,
            target=path,
            site_id=site_id,
        )

        if policy_result.decision == PolicyDecision.DENY:
            logger.warning(
                "agent_security.deny agent_id=%s tool=%s reason=%s",
                agent_id,
                tool.value,
                policy_result.reason,
            )
            return JSONResponse(
                status_code=403,
                content={"detail": policy_result.reason},
            )

        if policy_result.decision == PolicyDecision.REQUIRE_CONFIRMATION:
            token_hint = ""
            if policy_result.confirmation_token:
                token_hint = policy_result.confirmation_token.token
            logger.info(
                "agent_security.confirm_required agent_id=%s tool=%s",
                agent_id,
                tool.value,
            )
            return JSONResponse(
                status_code=202,
                content={
                    "detail": policy_result.reason,
                    "session_id": session.session_id,
                    "confirmation_token_hint": token_hint,
                    "action": "POST /api/agent/confirm with session_id and token",
                },
            )

        # Step j: Record call for loop detection
        tool_call_key = f"{tool.value}:{path}"
        circuit_breaker.record_call(agent_id, tool_call_key)

        # Step k: Execute request
        response = await call_next(request)

        # Step l: Record success/failure for circuit breaker
        if response.status_code >= 500:
            circuit_breaker.record_failure(agent_id)
        else:
            circuit_breaker.record_success(agent_id)

        # Step m: Post-action verification (alert-only)
        if response.status_code < 500 and tool is not None:
            tool_args = getattr(request.state, "tool_args", None) or {}
            try:
                verification_result = await verification_runner.verify(
                    tool=tool.value,
                    action=action,
                    args=tool_args,
                )
                if not verification_result.all_passed:
                    logger.warning(
                        "agent_security.verification_failed agent_id=%s tool=%s summary=%s",
                        agent_id,
                        tool.value,
                        verification_result.summary,
                    )
                else:
                    logger.debug(
                        "agent_security.verification_passed agent_id=%s tool=%s",
                        agent_id,
                        tool.value,
                    )
            except Exception as exc:
                logger.error(
                    "agent_security.verification_error agent_id=%s tool=%s error=%s",
                    agent_id,
                    tool.value,
                    exc,
                )

        # Step n: Return response
        return response
