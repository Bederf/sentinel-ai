"""Regression tests for autonomous.py security fixes.

C-2: Autonomous decision endpoints must require operator-level role.

Verifies that all POST handlers in autonomous.py reject callers whose
JWT has an insufficient role (auditor/viewer). The test patches
request.state.auth directly to simulate the middleware setting the
auth context, bypassing the TESTING bypass.
"""

import os
from unittest.mock import patch

os.environ.setdefault("DEMO_MODE", "true")
os.environ.setdefault("TESTING", "true")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-jwt-secret-for-ci-at-least-32-chars")

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.autonomous import router
from app.models.auth import AuthContext, SentinelRole

# ---------------------------------------------------------------------------
# Minimal test app — mounts only the autonomous router so the global
# middleware does NOT auto-inject OPERATOR bypass on these requests.
# ---------------------------------------------------------------------------


def _make_app_with_auth(role: SentinelRole) -> FastAPI:
    """Create a minimal FastAPI app that injects a fixed auth context."""
    test_app = FastAPI()

    auth_ctx = AuthContext(
        user_id="test-user",
        role=role,
        auth_method="jwt",
        source_ip="127.0.0.1",
        email="test@sentinel.local",
    )

    async def _inject_auth(request, call_next):
        request.state.auth = auth_ctx
        return await call_next(request)

    from starlette.middleware.base import BaseHTTPMiddleware

    test_app.add_middleware(BaseHTTPMiddleware, dispatch=_inject_auth)
    test_app.include_router(router)
    return test_app


# ---------------------------------------------------------------------------
# POST endpoints that must require operator (level 2)
# ---------------------------------------------------------------------------

POST_ENDPOINTS = [
    "/api/autonomous/enable",
    "/api/autonomous/disable",
    "/api/autonomous/test",
    "/api/autonomous/boundaries/update",
    "/api/autonomous/decisions/some-decision-id/approve",
]


@pytest.mark.asyncio
async def test_viewer_role_rejected_on_all_post_endpoints():
    """C-2: Auditor (viewer-equivalent) must receive 403 on all POST handlers."""
    app = _make_app_with_auth(SentinelRole.AUDITOR)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for endpoint in POST_ENDPOINTS:
            resp = await client.post(endpoint, json={})
            assert resp.status_code == 403, f"Expected 403 for auditor on {endpoint}, got {resp.status_code}"


@pytest.mark.asyncio
async def test_operator_role_passes_role_guard():
    """C-2: Operator must pass the role guard (may still get 404/500 from missing data)."""
    app = _make_app_with_auth(SentinelRole.OPERATOR)

    # Only test enable/disable which don't need DB/device fixtures.
    # We patch the engine so it doesn't crash.
    with (
        patch("app.api.autonomous.autonomous_decision_engine._initialized", True),
        patch(
            "app.api.autonomous.autonomous_decision_engine.enable_autonomous_mode",
            return_value={"success": True, "message": "enabled"},
        ),
        patch(
            "app.api.autonomous.autonomous_decision_engine.disable_autonomous_mode",
            return_value={"success": True, "message": "disabled"},
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/autonomous/enable")
            # 200 means role guard passed; any other non-403 is acceptable too
            assert resp.status_code != 403, f"Operator should not get 403 on /enable, got {resp.status_code}"

            resp = await client.post("/api/autonomous/disable")
            assert resp.status_code != 403, f"Operator should not get 403 on /disable, got {resp.status_code}"
