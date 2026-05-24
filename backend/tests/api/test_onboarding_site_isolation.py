"""
Onboarding API site isolation tests (BOLA).

Validates that /api/onboarding/* endpoints enforce site-level authorization.
"""
import os
import pytest
from unittest.mock import patch
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("DEMO_MODE", "true")
os.environ.setdefault("TESTING", "true")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-bola-testing-32chars")

from app.config.demo_configs import USER_DEMO_CONFIGS
from app.main import app
from app.models.auth import AuthContext, SentinelRole


OWNER_EMAIL = "onboarding-owner@sentinel.bms"
OWNER_USER_ID = "onboarding-owner-001"

ATTACKER_EMAIL = "onboarding-attacker@sentinel.bms"
ATTACKER_USER_ID = "onboarding-attacker-001"


def _make_auth_context(email: str, role: SentinelRole, user_id: str) -> AuthContext:
    return AuthContext(
        user_id=user_id,
        role=role,
        auth_method="bearer_token",
        source_ip="127.0.0.1",
        email=email,
    )


OWNER_AUTH = _make_auth_context(OWNER_EMAIL, SentinelRole.ADMIN, OWNER_USER_ID)
ATTACKER_AUTH = _make_auth_context(ATTACKER_EMAIL, SentinelRole.OPERATOR, ATTACKER_USER_ID)


def _fake_auth_for(auth_ctx: AuthContext | None):
    async def _fake(request):
        return auth_ctx
    return _fake


@pytest.fixture(autouse=True)
def _inject_onboarding_bola_configs(monkeypatch):
    """Patch get_access_profile_for_email to return our test profiles."""
    owner_profile = {
        "companyName": "Onboarding BOLA Test Owner",
        "profileFocus": "testing",
        "allowedModules": ["dashboard", "hvac", "solar", "control", "settings"],
        "allowedSites": ["site-002"],
        "defaultView": "dashboard",
        "viewMode": "admin",
        "description": "Onboarding BOLA test owner — site-002 access",
    }
    attacker_profile = {
        "companyName": "Onboarding BOLA Test Attacker",
        "profileFocus": "testing",
        "allowedModules": ["dashboard", "hvac", "solar", "control", "settings"],
        "allowedSites": ["site-003"],
        "defaultView": "dashboard",
        "viewMode": "operator",
        "description": "Onboarding BOLA test attacker — site-003 only, NO site-002",
    }

    def _fake_get_profile(email: str):
        if email == OWNER_EMAIL:
            return owner_profile
        if email == ATTACKER_EMAIL:
            return attacker_profile
        return None

    monkeypatch.setattr("app.config.access_profiles.get_access_profile_for_email", _fake_get_profile)


@pytest.fixture
async def owner_client():
    """Async client that authenticates as the owner (admin, site-002 access)."""
    transport = ASGITransport(app=app)
    _fake = _fake_auth_for(OWNER_AUTH)

    async def _fake_middleware(self, request, call_next):
        request.state.auth = OWNER_AUTH
        return await call_next(request)

    with patch.dict(os.environ, {"TESTING": "false"}):
        with patch("app.startup.middleware._authenticate_request", new=_fake):
            with patch("app.middleware.auth_middleware._authenticate_request", new=_fake):
                with patch("app.middleware.audit_middleware.AuditMiddleware.dispatch", _fake_middleware):
                    async with AsyncClient(transport=transport, base_url="http://test") as c:
                        yield c


@pytest.fixture
async def attacker_client():
    """Async client that authenticates as the attacker (operator, site-003 only)."""
    transport = ASGITransport(app=app)
    _fake = _fake_auth_for(ATTACKER_AUTH)

    async def _fake_middleware(self, request, call_next):
        request.state.auth = ATTACKER_AUTH
        return await call_next(request)

    with patch.dict(os.environ, {"TESTING": "false"}):
        with patch("app.startup.middleware._authenticate_request", new=_fake):
            with patch("app.middleware.auth_middleware._authenticate_request", new=_fake):
                with patch("app.middleware.audit_middleware.AuditMiddleware.dispatch", _fake_middleware):
                    async with AsyncClient(transport=transport, base_url="http://test") as c:
                        yield c


# ---------------------------------------------------------------------------
# BOLA: baseline-eligibility
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_baseline_eligibility_site_002_blocked(attacker_client: AsyncClient):
    """Attacker on site-003 cannot query baseline-eligibility for site-002."""
    response = await attacker_client.get("/api/onboarding/baseline-eligibility?site_id=site-002")
    assert response.status_code in (403, 404), (
        f"BOLA vulnerability: attacker got {response.status_code} for site-002; "
        f"expected 403/404. Body: {response.text[:200]}"
    )


@pytest.mark.asyncio
async def test_baseline_eligibility_site_002_allowed(owner_client: AsyncClient):
    """Owner on site-002 can query their own baseline-eligibility."""
    response = await owner_client.get("/api/onboarding/baseline-eligibility?site_id=site-002")
    assert response.status_code in (200, 404), (
        f"Owner got {response.status_code} for own site; expected 200/404. "
        f"Body: {response.text[:200]}"
    )


# ---------------------------------------------------------------------------
# BOLA: seed-baselines
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_seed_baselines_site_002_blocked(attacker_client: AsyncClient):
    """Attacker on site-003 cannot seed baselines for site-002."""
    response = await attacker_client.post(
        "/api/onboarding/seed-baselines?site_id=site-002",
        json={"equipment_ids": []},
    )
    assert response.status_code in (403, 404), (
        f"BOLA vulnerability: attacker got {response.status_code} seeding site-002; "
        f"expected 403/404. Body: {response.text[:200]}"
    )


@pytest.mark.asyncio
async def test_seed_baselines_site_002_allowed(owner_client: AsyncClient):
    """Owner on site-002 can seed their own baselines."""
    response = await owner_client.post(
        "/api/onboarding/seed-baselines?site_id=site-002",
        json={"equipment_ids": []},
    )
    assert response.status_code in (200, 404, 422), (
        f"Owner got {response.status_code} for own site; expected 200/404/422. "
        f"Body: {response.text[:200]}"
    )


# ---------------------------------------------------------------------------
# Authorization: owner still gets their own site
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_own_site_still_accessible(owner_client: AsyncClient):
    """Sanity-check: owner can hit their own site endpoint."""
    response = await owner_client.get("/api/onboarding/baseline-eligibility?site_id=site-002")
    assert response.status_code != 401


# ---------------------------------------------------------------------------
# Filter tampering: ensure no cross-site data leakage
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_seed_baselines_rejects_foreign_site_id(owner_client: AsyncClient):
    """Owner cannot use their token to seed baselines for a different site."""
    response = await owner_client.post(
        "/api/onboarding/seed-baselines?site_id=site-003",
        json={"equipment_ids": []},
    )
    assert response.status_code in (403, 404), (
        f"Filter tamper: owner got {response.status_code} when specifying site-003; "
        f"expected 403/404. Body: {response.text[:200]}"
    )
