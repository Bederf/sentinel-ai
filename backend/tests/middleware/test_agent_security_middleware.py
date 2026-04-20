"""Integration tests for Phase 120-05: Agent Security Middleware.

Tests the full agent security pipeline: path resolution, permission matrix
enforcement, rate limiting, circuit breaker, confirmation flow, and bypass paths.

Uses a minimal FastAPI app with AgentSecurityMiddleware to test the middleware
in isolation from the main application.
"""

import os

os.environ.setdefault("DEMO_MODE", "true")
os.environ.setdefault("LIGHTWEIGHT_APP", "1")

import time
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from starlette.middleware.base import BaseHTTPMiddleware

from app.middleware.agent_security.circuit_breaker import (
    AgentRateLimiter,
    CircuitBreaker,
    QuotaTier,
)
from app.middleware.agent_security.middleware import (
    AgentSecurityMiddleware,
    _resolve_tool,
)
from app.middleware.agent_security.models import AgentToolName
from app.middleware.agent_security.policy_engine import (
    ToolPolicyEngine,
)
from app.models.auth import AuthContext, SentinelRole

# ---------------------------------------------------------------------------
# Test app factory — builds a minimal FastAPI with agent security middleware
# ---------------------------------------------------------------------------


def _create_test_app(
    *,
    policy_engine_instance: ToolPolicyEngine | None = None,
    rate_limiter_instance: AgentRateLimiter | None = None,
    circuit_breaker_instance: CircuitBreaker | None = None,
) -> FastAPI:
    """Create a minimal FastAPI app with agent security middleware and stub routes."""
    app = FastAPI()

    # Stub routes that match PATH_TOOL_MAP entries
    @app.get("/api/equipment/search")
    async def equipment_search():
        return {"status": "ok", "data": []}

    @app.post("/api/devices/control")
    async def devices_control():
        return {"status": "ok"}

    @app.post("/api/work-orders")
    async def create_work_order():
        return {"status": "ok", "id": "WO-001"}

    @app.post("/api/ml/execute")
    async def ml_execute():
        return {"status": "ok"}

    @app.get("/api/health")
    async def health():
        return {"status": "healthy"}

    @app.post("/api/notifications/email")
    async def send_email():
        return {"status": "sent"}

    @app.get("/api/buildings")
    async def get_buildings():
        return {"status": "ok", "data": []}

    @app.get("/api/alerts")
    async def get_alerts():
        return {"status": "ok", "data": []}

    @app.get("/api/unknown/path")
    async def unknown_path():
        return {"status": "ok"}

    # Register agent security middleware
    app.add_middleware(AgentSecurityMiddleware)

    return app


def _bot_auth_context(user_id: str = "bot-test-1") -> AuthContext:
    """Create a BOT_AGENT auth context for testing."""
    return AuthContext(
        user_id=user_id,
        role=SentinelRole.BOT_AGENT,
        auth_method="api_key",
        source_ip="127.0.0.1",
        is_bot_agent=True,
    )


def _operator_auth_context(user_id: str = "operator-1") -> AuthContext:
    """Create an OPERATOR auth context (non-bot) for testing."""
    return AuthContext(
        user_id=user_id,
        role=SentinelRole.OPERATOR,
        auth_method="bearer_token",
        source_ip="127.0.0.1",
        is_bot_agent=False,
    )


def _admin_auth_context(user_id: str = "admin-1") -> AuthContext:
    """Create an ADMIN auth context for testing."""
    return AuthContext(
        user_id=user_id,
        role=SentinelRole.ADMIN,
        auth_method="bearer_token",
        source_ip="127.0.0.1",
        is_bot_agent=True,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fresh_policy_engine() -> ToolPolicyEngine:
    """Fresh policy engine per test to avoid cross-test contamination."""
    return ToolPolicyEngine()


@pytest.fixture
def fresh_rate_limiter() -> AgentRateLimiter:
    """Fresh rate limiter per test."""
    return AgentRateLimiter()


@pytest.fixture
def fresh_circuit_breaker() -> CircuitBreaker:
    """Fresh circuit breaker per test."""
    return CircuitBreaker()


@pytest.fixture
def test_app() -> FastAPI:
    """Minimal test app with agent security middleware."""
    return _create_test_app()


# ---------------------------------------------------------------------------
# Helper: inject auth context into request via middleware
# ---------------------------------------------------------------------------


def _make_auth_injector_app(auth_context: AuthContext | None) -> FastAPI:
    """Create a test app that injects auth context before AgentSecurityMiddleware runs.

    Middleware execution order (outermost to innermost):
      inject_auth (sets request.state.auth)  →  AgentSecurityMiddleware  →  route handler

    In Starlette, the LAST middleware added via add_middleware is outermost.
    So we register AgentSecurityMiddleware first, then the auth injector.
    """
    app = FastAPI()

    # Stub routes
    @app.get("/api/equipment/search")
    async def equipment_search():
        return {"status": "ok", "data": []}

    @app.post("/api/devices/control")
    async def devices_control():
        return {"status": "ok"}

    @app.post("/api/work-orders")
    async def create_work_order():
        return {"status": "ok", "id": "WO-001"}

    @app.post("/api/ml/execute")
    async def ml_execute():
        return {"status": "ok"}

    @app.get("/api/health")
    async def health():
        return {"status": "healthy"}

    @app.post("/api/notifications/email")
    async def send_email():
        return {"status": "sent"}

    @app.get("/api/buildings")
    async def get_buildings():
        return {"status": "ok", "data": []}

    @app.get("/api/alerts")
    async def get_alerts():
        return {"status": "ok", "data": []}

    @app.get("/api/unknown/path")
    async def unknown_path():
        return {"status": "ok"}

    # Register agent security middleware FIRST (will be inner)
    app.add_middleware(AgentSecurityMiddleware)

    # Register auth injector SECOND (will be outer — runs first in request path)
    # This simulates enforce_authentication setting request.state.auth
    class _AuthInjectorMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            if auth_context is not None:
                request.state.auth = auth_context
            return await call_next(request)

    app.add_middleware(_AuthInjectorMiddleware)

    return app


# ---------------------------------------------------------------------------
# Ensure fresh singletons per test to avoid cross-test pollution
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset the module-level singletons before each test."""
    from app.middleware.agent_security.circuit_breaker import (
        circuit_breaker as cb_singleton,
    )
    from app.middleware.agent_security.circuit_breaker import (
        rate_limiter as rl_singleton,
    )
    from app.middleware.agent_security.policy_engine import (
        policy_engine as pe_singleton,
    )

    # Reset circuit breaker state
    cb_singleton._states.clear()
    cb_singleton._opened_at.clear()
    cb_singleton._failure_timestamps.clear()
    cb_singleton._retry_counts.clear()
    cb_singleton._call_timestamps.clear()
    cb_singleton._trip_reasons.clear()

    # Reset rate limiter state
    rl_singleton._windows.clear()
    rl_singleton._token_windows.clear()
    rl_singleton._concurrent.clear()

    # Reset policy engine state
    pe_singleton._pending_confirmations.clear()
    pe_singleton._audit_log.clear()

    yield


# ---------------------------------------------------------------------------
# Permission Matrix Tests (5)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bot_agent_bms_read_allowed():
    """1. Bot with BMS_READ tool (GET /api/equipment/search) is allowed (READ_ONLY → GET = ALLOW)."""
    app = _make_auth_injector_app(_bot_auth_context())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/equipment/search")
        # BOT_AGENT has READ_ONLY for BMS_READ, GET is allowed
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_bot_agent_equipment_control_denied():
    """2. Bot with EQUIPMENT_CONTROL tool → 403 DENY."""
    app = _make_auth_injector_app(_bot_auth_context())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/devices/control")
        assert resp.status_code == 403
        assert "Denied" in resp.json()["detail"] or "denied" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_bot_agent_work_order_allowed():
    """3. Bot with WORK_ORDERS tool → allowed (ALLOW)."""
    app = _make_auth_injector_app(_bot_auth_context())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/work-orders")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_bot_agent_shell_denied():
    """4. Bot with SHELL tool → 403 DENY (PERMISSION_MATRIX: DENY for BOT_AGENT)."""
    app = _make_auth_injector_app(_bot_auth_context())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Shell is also caught by rate limiter (limit=0 for PER_BOT),
        # so we might get 429 from the rate limiter before policy engine runs.
        resp = await client.post("/api/ml/execute")
        assert resp.status_code in (403, 429)


@pytest.mark.asyncio
async def test_non_bot_passes_through():
    """5. Regular OPERATOR request passes without agent security checks."""
    app = _make_auth_injector_app(_operator_auth_context())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/devices/control")
        # Non-bot should pass through middleware entirely
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Rate Limiting Tests (3)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bot_rate_limit_blocks_excess():
    """6. Exceed tool call quota → 429.

    Note: The circuit breaker loop detection trips after >10 calls in 10s
    to the same endpoint. We use the rate limiter directly to test the
    tool call quota since the middleware also trips the breaker.
    """
    from app.middleware.agent_security.circuit_breaker import rate_limiter as rl

    agent_id = "bot-rate-direct-1"
    tier = QuotaTier.PER_BOT  # 120 calls per minute

    # Exhaust the quota via direct rate limiter calls
    for i in range(120):
        result = rl.check_tool_call(agent_id, tier)
        assert result.allowed, f"Call {i + 1} should be allowed"

    # 121st should be blocked
    result = rl.check_tool_call(agent_id, tier)
    assert not result.allowed
    assert result.retry_after_seconds is not None


@pytest.mark.asyncio
async def test_bot_shell_always_denied():
    """7. Shell check denied for bot tier (limit=0)."""
    app = _make_auth_injector_app(_bot_auth_context(user_id="bot-shell-1"))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/ml/execute")
        # Shell denied either by rate limiter (limit=0) or policy engine (DENY)
        assert resp.status_code in (403, 429)
        body = resp.json()
        assert "detail" in body


@pytest.mark.asyncio
async def test_rate_limit_retry_after_header():
    """8. 429 from rate limiter includes Retry-After header.

    We pre-exhaust the rate limiter quota directly, then verify the middleware
    returns a 429 with Retry-After on the next request. We use a fresh agent_id
    to avoid circuit breaker contamination.
    """
    from app.middleware.agent_security.circuit_breaker import rate_limiter as rl

    agent_id = "bot-retry-hdr-1"
    tier = QuotaTier.PER_BOT

    # Pre-exhaust quota via direct rate limiter calls
    for _ in range(120):
        rl.check_tool_call(agent_id, tier)

    app = _make_auth_injector_app(_bot_auth_context(user_id=agent_id))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/equipment/search")
        assert resp.status_code == 429
        assert "retry-after" in resp.headers


# ---------------------------------------------------------------------------
# Circuit Breaker Tests (3)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_circuit_breaker_trips_after_failures():
    """9. 5 failures → subsequent request gets 429."""
    from app.middleware.agent_security.circuit_breaker import circuit_breaker as cb

    agent_id = "bot-cb-fail-1"
    # Manually record 5 failures
    for _ in range(5):
        cb.record_failure(agent_id)

    app = _make_auth_injector_app(_bot_auth_context(user_id=agent_id))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/equipment/search")
        assert resp.status_code == 429
        assert "Circuit breaker open" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_circuit_breaker_force_reset_endpoint():
    """10. Admin POST reset → bot can proceed."""
    from app.middleware.agent_security.circuit_breaker import circuit_breaker as cb

    agent_id = "bot-cb-reset-1"
    # Trip the breaker
    for _ in range(5):
        cb.record_failure(agent_id)

    # Force reset
    cb.force_reset(agent_id)

    app = _make_auth_injector_app(_bot_auth_context(user_id=agent_id))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/equipment/search")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_circuit_breaker_half_open_recovery():
    """11. After cooldown → one success closes the breaker."""
    from app.middleware.agent_security.circuit_breaker import circuit_breaker as cb

    agent_id = "bot-cb-recovery-1"
    current_time = time.time()

    # Trip the breaker
    for _ in range(5):
        cb.record_failure(agent_id)

    # Fast-forward past cooldown (300s)
    with patch("app.middleware.agent_security.circuit_breaker.time") as mock_time:
        mock_time.time.return_value = current_time + 301
        result = cb.check(agent_id)
        assert result.allowed
        assert result.state.value == "half_open"

    # Record success → should close
    cb.record_success(agent_id)
    result = cb.check(agent_id)
    assert result.allowed
    assert result.state.value == "closed"


# ---------------------------------------------------------------------------
# Confirmation Flow Tests (3)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_equipment_control_returns_confirmation():
    """12. Admin bot POST equipment control → needs confirmation (202)."""
    app = _make_auth_injector_app(_admin_auth_context(user_id="admin-bot-1"))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/devices/control")
        # ADMIN + EQUIPMENT_CONTROL → REQUIRE_CONFIRMATION → 202
        assert resp.status_code == 202
        body = resp.json()
        assert "confirmation_token_hint" in body
        assert "session_id" in body
        assert body["confirmation_token_hint"] != ""


@pytest.mark.asyncio
async def test_confirm_action_valid_token():
    """13. POST /api/agent/confirm with correct token → 200."""
    from app.middleware.agent_security.models import AgentSession, AgentToolName
    from app.middleware.agent_security.policy_engine import policy_engine as pe

    # Create a pending confirmation directly
    session = AgentSession(
        owner_id="admin-confirm-1",
        role="admin",
        tenant_id="default",
    )
    result = pe.evaluate(
        session=session,
        tool=AgentToolName.EQUIPMENT_CONTROL,
        action="POST",
        target="/api/devices/control",
    )
    assert result.needs_confirmation
    token_value = result.confirmation_token.token

    # Now confirm it
    confirm_result = pe.confirm_action(
        session_id=session.session_id,
        user_token=token_value,
    )
    assert confirm_result.is_allowed


@pytest.mark.asyncio
async def test_confirm_action_expired_token():
    """14. Confirm after 60s → DENY (expired)."""
    from app.middleware.agent_security.models import AgentSession, AgentToolName
    from app.middleware.agent_security.policy_engine import policy_engine as pe

    session = AgentSession(
        owner_id="admin-expire-1",
        role="admin",
        tenant_id="default",
    )
    result = pe.evaluate(
        session=session,
        tool=AgentToolName.EQUIPMENT_CONTROL,
        action="POST",
        target="/api/devices/control",
    )
    assert result.needs_confirmation
    token_value = result.confirmation_token.token

    # Expire the token by manipulating its expires_at
    pending = pe._pending_confirmations.get(session.session_id)
    assert pending is not None
    pending.expires_at = datetime.utcnow() - timedelta(seconds=1)

    # Confirm should fail
    confirm_result = pe.confirm_action(
        session_id=session.session_id,
        user_token=token_value,
    )
    assert not confirm_result.is_allowed
    assert "expired" in confirm_result.reason.lower()


# ---------------------------------------------------------------------------
# Bypass Test (1)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_endpoint_bypasses():
    """15. /api/health always passes regardless of auth context."""
    app = _make_auth_injector_app(_bot_auth_context())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"


# ---------------------------------------------------------------------------
# Path resolution unit tests (bonus — validates _resolve_tool directly)
# ---------------------------------------------------------------------------


def test_resolve_tool_work_orders():
    """_resolve_tool maps /api/work-orders to WORK_ORDERS."""
    assert _resolve_tool("/api/work-orders") == AgentToolName.WORK_ORDERS


def test_resolve_tool_equipment_search():
    """_resolve_tool maps /api/equipment/search to BMS_READ."""
    assert _resolve_tool("/api/equipment/search") == AgentToolName.BMS_READ


def test_resolve_tool_devices_control():
    """_resolve_tool maps /api/devices/control to EQUIPMENT_CONTROL."""
    assert _resolve_tool("/api/devices/control") == AgentToolName.EQUIPMENT_CONTROL


def test_resolve_tool_bypass_auth():
    """_resolve_tool returns None for bypass paths."""
    assert _resolve_tool("/api/auth/login") is None


def test_resolve_tool_unknown():
    """_resolve_tool returns None for unmapped paths."""
    assert _resolve_tool("/api/unknown/path") is None
