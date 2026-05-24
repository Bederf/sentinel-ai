"""BOLA (Broken Object Level Authorization) integration tests.

Tests that API endpoints properly enforce object-level authorization
via require_site_access() and require_equipment_access() dependencies.

Strategy:
- Inject test demo configs with different site restrictions per user
- Override the TESTING middleware bypass to set email from our JWT token
- User A (owner, admin) has access to site-002
- User B (attacker, operator) has access to site-003 ONLY
- Verify User B gets 403 when accessing site-002 resources
- Verify User A can access site-002 resources (not 403)

This prevents OWASP API Security #1: Broken Object Level Authorization.
"""

import os
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("DEMO_MODE", "true")
os.environ.setdefault("TESTING", "true")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-jwt-secret-for-ci-at-least-32-chars")

from app.config.demo_configs import USER_DEMO_CONFIGS, DemoConfig
from app.main import app
from app.models.auth import AuthContext, SentinelRole

# ---------------------------------------------------------------------------
# Test user configuration
# ---------------------------------------------------------------------------

OWNER_EMAIL = "bola-owner@sentinel.bms"
OWNER_USER_ID = "bola-owner-001"

ATTACKER_EMAIL = "bola-attacker@sentinel.bms"
ATTACKER_USER_ID = "bola-attacker-001"

OWNER_DEMO_CONFIG: DemoConfig = {
    "companyName": "BOLA Test Owner",
    "demoFocus": "testing",
    "allowedModules": [
        "dashboard",
        "hvac",
        "solar",
        "control",
        "settings",
        "integrations",
        "lighting",
        "maintenance",
        "ml",
        "kpi",
    ],
    "allowedSites": ["site-002"],
    "defaultView": "dashboard",
    "viewMode": "admin",
    "description": "BOLA test owner — site-002 access",
}

ATTACKER_DEMO_CONFIG: DemoConfig = {
    "companyName": "BOLA Test Attacker",
    "demoFocus": "testing",
    "allowedModules": [
        "dashboard",
        "hvac",
        "solar",
        "control",
        "settings",
        "integrations",
        "lighting",
        "maintenance",
        "ml",
        "kpi",
    ],
    "allowedSites": ["site-003"],
    "defaultView": "dashboard",
    "viewMode": "operator",
    "description": "BOLA test attacker — site-003 only, NO site-002",
}


def _make_auth_context(email: str, role: SentinelRole, user_id: str) -> AuthContext:
    """Build an AuthContext for test injection."""
    return AuthContext(
        user_id=user_id,
        role=role,
        auth_method="bearer_token",
        source_ip="127.0.0.1",
        email=email,
    )


OWNER_AUTH = _make_auth_context(OWNER_EMAIL, SentinelRole.ADMIN, OWNER_USER_ID)
ATTACKER_AUTH = _make_auth_context(ATTACKER_EMAIL, SentinelRole.OPERATOR, ATTACKER_USER_ID)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _inject_bola_demo_configs(monkeypatch):
    """Inject test demo configs so require_site_access enforces site boundaries."""
    patched = {
        **USER_DEMO_CONFIGS,
        OWNER_EMAIL: OWNER_DEMO_CONFIG,
        ATTACKER_EMAIL: ATTACKER_DEMO_CONFIG,
    }
    monkeypatch.setattr("app.config.demo_configs.USER_DEMO_CONFIGS", patched)


def _make_middleware_that_injects_auth(auth_ctx: AuthContext | None):
    """Create a replacement for the enforce_authentication middleware.

    Instead of the real middleware (which bypasses auth in TESTING mode),
    this injects a specific AuthContext into request.state so that
    require_site_access/require_equipment_access can check it.
    """

    async def fake_middleware(request, call_next):
        if auth_ctx is not None:
            request.state.auth = auth_ctx
        # Don't set request.state.auth if None — let the dependency raise 401
        return await call_next(request)

    return fake_middleware


# We need to replace the TESTING middleware bypass. Since the middleware is
# registered at import time and checks os.environ at request time, we
# patch os.environ["TESTING"] to "false" AND patch _authenticate_request
# to return our controlled auth context.


def _fake_auth_for(auth_ctx: AuthContext | None):
    """Return an async function that acts as _authenticate_request."""

    async def _fake(request):
        return auth_ctx

    return _fake


@pytest.fixture
async def owner_client():
    """Async client that authenticates as the owner (admin, site-002 access)."""
    transport = ASGITransport(app=app)
    _fake = _fake_auth_for(OWNER_AUTH)
    with patch.dict(os.environ, {"TESTING": "false"}):
        with patch("app.startup.middleware._authenticate_request", new=_fake):
            with patch("app.middleware.auth_middleware._authenticate_request", new=_fake):
                async with AsyncClient(transport=transport, base_url="http://test") as c:
                    yield c


@pytest.fixture
async def attacker_client():
    """Async client that authenticates as the attacker (operator, site-003 only)."""
    transport = ASGITransport(app=app)
    _fake = _fake_auth_for(ATTACKER_AUTH)
    with patch.dict(os.environ, {"TESTING": "false"}):
        with patch("app.startup.middleware._authenticate_request", new=_fake):
            with patch("app.middleware.auth_middleware._authenticate_request", new=_fake):
                async with AsyncClient(transport=transport, base_url="http://test") as c:
                    yield c


@pytest.fixture
async def anon_client():
    """Async client with no authentication (should get 401)."""
    transport = ASGITransport(app=app)
    _fake = _fake_auth_for(None)
    with patch.dict(os.environ, {"TESTING": "false"}):
        with patch("app.startup.middleware._authenticate_request", new=_fake):
            with patch("app.middleware.auth_middleware._authenticate_request", new=_fake):
                async with AsyncClient(transport=transport, base_url="http://test") as c:
                    yield c


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def assert_blocked(resp, path: str):
    """Assert the response indicates the request was blocked (401 or 403)."""
    assert resp.status_code in (401, 403), (
        f"BOLA VULNERABILITY: {path} returned {resp.status_code} "
        f"instead of 401/403 for unauthorized user. Body: {resp.text[:300]}"
    )


def assert_not_blocked(resp, path: str):
    """Assert the response is NOT a 401/403 (owner should have access)."""
    assert resp.status_code not in (401, 403), (
        f"Owner unexpectedly blocked from {path}: {resp.status_code}. Body: {resp.text[:300]}"
    )


# ---------------------------------------------------------------------------
# SITE-LEVEL BOLA TESTS
# ---------------------------------------------------------------------------


class TestSiteEndpointBola:
    """Test require_site_access blocks cross-site access."""

    # --- Buildings API ---

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_building_detail_blocked(self, attacker_client):
        resp = await attacker_client.get("/api/buildings/site-002")
        assert_blocked(resp, "GET /api/buildings/site-002")

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_building_equipment_blocked(self, attacker_client):
        resp = await attacker_client.get("/api/buildings/site-002/equipment")
        assert_blocked(resp, "GET /api/buildings/site-002/equipment")

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_building_equipment_allowed(self, owner_client):
        resp = await owner_client.get("/api/buildings/site-002/equipment")
        assert_not_blocked(resp, "GET /api/buildings/site-002/equipment")

    # --- Desks API ---

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_desks_list_blocked(self, attacker_client):
        resp = await attacker_client.get("/api/buildings/site-002/desks")
        assert_blocked(resp, "GET /api/buildings/site-002/desks")

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_desk_stats_blocked(self, attacker_client):
        resp = await attacker_client.get("/api/buildings/site-002/desks/stats")
        assert_blocked(resp, "GET /api/buildings/site-002/desks/stats")

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_desk_centroids_blocked(self, attacker_client):
        resp = await attacker_client.get("/api/buildings/site-002/desks/centroids")
        assert_blocked(resp, "GET /api/buildings/site-002/desks/centroids")

    # --- Sustainability API ---

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_sustainability_summary_blocked(self, attacker_client):
        resp = await attacker_client.get("/api/sustainability/site-002/summary")
        assert_blocked(resp, "GET /api/sustainability/site-002/summary")

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_sustainability_emissions_blocked(self, attacker_client):
        resp = await attacker_client.get("/api/sustainability/site-002/emissions")
        assert_blocked(resp, "GET /api/sustainability/site-002/emissions")

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_sustainability_efficiency_blocked(self, attacker_client):
        resp = await attacker_client.get("/api/sustainability/site-002/efficiency")
        assert_blocked(resp, "GET /api/sustainability/site-002/efficiency")

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_sustainability_config_blocked(self, attacker_client):
        resp = await attacker_client.get("/api/sustainability/site-002/config")
        assert_blocked(resp, "GET /api/sustainability/site-002/config")

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_buildings_sustainability_emissions_blocked(self, attacker_client):
        resp = await attacker_client.get("/api/sustainability/buildings/site-002/emissions/summary")
        assert_blocked(resp, "GET /api/sustainability/buildings/site-002/emissions/summary")

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_buildings_sustainability_esg_blocked(self, attacker_client):
        resp = await attacker_client.get("/api/sustainability/buildings/site-002/esg-metrics")
        assert_blocked(resp, "GET /api/sustainability/buildings/site-002/esg-metrics")

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_buildings_sustainability_certifications_blocked(self, attacker_client):
        resp = await attacker_client.get("/api/sustainability/buildings/site-002/certifications")
        assert_blocked(resp, "GET /api/sustainability/buildings/site-002/certifications")

    # --- Peak Demand API ---

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_demand_status_blocked(self, attacker_client):
        resp = await attacker_client.get("/api/peak-demand/site-002/status")
        assert_blocked(resp, "GET /api/peak-demand/site-002/status")

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_demand_forecast_blocked(self, attacker_client):
        resp = await attacker_client.get("/api/peak-demand/site-002/forecast-24h")
        assert_blocked(resp, "GET /api/peak-demand/site-002/forecast-24h")

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_demand_summary_blocked(self, attacker_client):
        resp = await attacker_client.get("/api/peak-demand/site-002/summary")
        assert_blocked(resp, "GET /api/peak-demand/site-002/summary")

    # --- Load Forecast API ---

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_load_forecast_blocked(self, attacker_client):
        resp = await attacker_client.get("/api/load-forecast/site-002")
        assert_blocked(resp, "GET /api/load-forecast/site-002")

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_load_forecast_allowed(self, owner_client):
        resp = await owner_client.get("/api/load-forecast/site-002")
        assert_not_blocked(resp, "GET /api/load-forecast/site-002")

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_load_forecast_accuracy_blocked(self, attacker_client):
        resp = await attacker_client.get("/api/load-forecast/site-002/accuracy")
        assert_blocked(resp, "GET /api/load-forecast/site-002/accuracy")

    # --- Dispatch Optimizer API ---

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_dispatch_schedule_blocked(self, attacker_client):
        resp = await attacker_client.get("/api/dispatch-optimizer/site-002/schedule")
        assert_blocked(resp, "GET /api/dispatch-optimizer/site-002/schedule")

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_dispatch_compare_blocked(self, attacker_client):
        resp = await attacker_client.get("/api/dispatch-optimizer/site-002/compare")
        assert_blocked(resp, "GET /api/dispatch-optimizer/site-002/compare")

    # --- Recommendations API ---

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_recommendations_list_blocked(self, attacker_client):
        resp = await attacker_client.get("/api/recommendations/site-002")
        assert_blocked(resp, "GET /api/recommendations/site-002")

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_recommendations_history_blocked(self, attacker_client):
        resp = await attacker_client.post("/api/recommendations/history/site-002")
        assert_blocked(resp, "POST /api/recommendations/history/site-002")

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_recommendations_process_blocked(self, attacker_client):
        resp = await attacker_client.post("/api/recommendations/site-002/process-pending")
        assert_blocked(resp, "POST /api/recommendations/site-002/process-pending")

    # --- Solar Annual API ---
    # NOTE: /api/solar/annual/* endpoints do not exist in the solar router.
    # The solar router uses /solar/sites/{site_id}/* patterns instead.
    # These tests are removed to avoid false negatives.

    # --- 3D Config API ---

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_3d_config_blocked(self, attacker_client):
        resp = await attacker_client.get("/api/buildings/site-002/config")
        assert_blocked(resp, "GET /api/buildings/site-002/config")

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_3d_viewer_data_blocked(self, attacker_client):
        resp = await attacker_client.get("/api/buildings/site-002/viewer-data")
        assert_blocked(resp, "GET /api/buildings/site-002/viewer-data")

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_3d_equipment_positions_blocked(self, attacker_client):
        resp = await attacker_client.get("/api/buildings/site-002/equipment-positions")
        assert_blocked(resp, "GET /api/buildings/site-002/equipment-positions")

    # --- Zone Ingestion API ---

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_zone_centroids_blocked(self, attacker_client):
        resp = await attacker_client.get("/api/buildings/site-002/zone-ingestion/centroids")
        assert_blocked(resp, "GET /api/buildings/site-002/zone-ingestion/centroids")

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_zone_validate_blocked(self, attacker_client):
        resp = await attacker_client.get("/api/buildings/site-002/zone-ingestion/validate")
        assert_blocked(resp, "GET /api/buildings/site-002/zone-ingestion/validate")


# ---------------------------------------------------------------------------
# EQUIPMENT-LEVEL BOLA TESTS
# ---------------------------------------------------------------------------


class TestEquipmentEndpointBola:
    """Test require_equipment_access blocks cross-site equipment access.

    Equipment codes like S002-AHU-B1-001 derive to site-002.
    Attacker has site-003 access only, so should be blocked.
    """

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_device_validate_blocked(self, attacker_client):
        resp = await attacker_client.post(
            "/api/device-controls/S002-AHU-B1-001/validate",
            params={"point": "setpoint", "value": "22"},
        )
        assert_blocked(resp, "POST /api/device-controls/S002-AHU-B1-001/validate")

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_device_recommend_blocked(self, attacker_client):
        resp = await attacker_client.post(
            "/api/device-controls/S002-AHU-B1-001/recommend",
        )
        assert_blocked(resp, "POST /api/device-controls/S002-AHU-B1-001/recommend")

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_device_execute_blocked(self, attacker_client):
        resp = await attacker_client.post(
            "/api/device-controls/S002-AHU-B1-001/execute",
            json={"point": "setpoint", "value": 22},
        )
        assert_blocked(resp, "POST /api/device-controls/S002-AHU-B1-001/execute")

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_baseline_active_blocked(self, attacker_client):
        resp = await attacker_client.get("/api/equipment/baseline/S002-AHU-B1-001")
        assert_blocked(resp, "GET /api/equipment/baseline/S002-AHU-B1-001")

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_baseline_report_blocked(self, attacker_client):
        resp = await attacker_client.get("/api/equipment/baseline/S002-AHU-B1-001/report")
        assert_blocked(resp, "GET /api/equipment/baseline/S002-AHU-B1-001/report")

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_baseline_summary_blocked(self, attacker_client):
        resp = await attacker_client.get("/api/equipment/baseline/S002-AHU-B1-001/summary")
        assert_blocked(resp, "GET /api/equipment/baseline/S002-AHU-B1-001/summary")

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_baseline_history_blocked(self, attacker_client):
        resp = await attacker_client.get("/api/equipment/baseline/S002-AHU-B1-001/history")
        assert_blocked(resp, "GET /api/equipment/baseline/S002-AHU-B1-001/history")


# ---------------------------------------------------------------------------
# MUTATING ENDPOINT BOLA TESTS (higher risk)
# ---------------------------------------------------------------------------


class TestMutatingEndpointBola:
    """Test BOLA on POST/PATCH/DELETE endpoints."""

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_zone_ingestion_post_blocked(self, attacker_client):
        resp = await attacker_client.post(
            "/api/buildings/site-002/zone-ingestion/zones",
            json={"zones": []},
        )
        assert_blocked(resp, "POST /api/buildings/site-002/zone-ingestion/zones")

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_desk_ingestion_post_blocked(self, attacker_client):
        resp = await attacker_client.post(
            "/api/buildings/site-002/zone-ingestion/desks",
            json={"desks": []},
        )
        assert_blocked(resp, "POST /api/buildings/site-002/zone-ingestion/desks")

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_3d_config_post_blocked(self, attacker_client):
        resp = await attacker_client.post(
            "/api/buildings/site-002/config",
            json={
                "site_structure": {
                    "name": "Hacked",
                    "numberOfFloors": 1,
                    "floors": [{"level": "G", "height": 3.0, "width": 10.0, "depth": 10.0, "label": "Ground"}],
                },
                "equipment_positions": [],
            },
        )
        assert_blocked(resp, "POST /api/buildings/site-002/config")

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_3d_config_delete_blocked(self, attacker_client):
        resp = await attacker_client.delete("/api/buildings/site-002/config")
        assert_blocked(resp, "DELETE /api/buildings/site-002/config")

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_equipment_position_patch_blocked(self, attacker_client):
        resp = await attacker_client.patch(
            "/api/buildings/site-002/equipment-positions/S002-AHU-B1-001",
            json={"equipment_id": "S002-AHU-B1-001", "floor": "G", "x": 5.0, "y": 5.0},
        )
        assert_blocked(resp, "PATCH /api/buildings/site-002/equipment-positions/S002-AHU-B1-001")

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_sustainability_config_put_blocked(self, attacker_client):
        resp = await attacker_client.put(
            "/api/sustainability/site-002/config",
            json={"carbon_factor": 0.5},
        )
        assert_blocked(resp, "PUT /api/sustainability/site-002/config")

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_load_forecast_retrain_blocked(self, attacker_client):
        resp = await attacker_client.post("/api/load-forecast/site-002/retrain")
        assert_blocked(resp, "POST /api/load-forecast/site-002/retrain")

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_dispatch_solve_blocked(self, attacker_client):
        resp = await attacker_client.post(
            "/api/dispatch-optimizer/site-002/solve",
            json={},
        )
        assert_blocked(resp, "POST /api/dispatch-optimizer/site-002/solve")

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_baseline_capture_blocked(self, attacker_client):
        resp = await attacker_client.post(
            "/api/equipment/baseline/S002-AHU-B1-001",
            json={"name": "hacked-baseline"},
        )
        assert_blocked(resp, "POST /api/equipment/baseline/S002-AHU-B1-001")

    # NOTE: /api/solar/annual/* endpoints do not exist in the solar router.
    # POST /solar/sites/{site_id}/simulate would need checking if it exists.
    # test_solar_simulate_blocked removed to avoid false negatives.

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_demand_approve_blocked(self, attacker_client):
        resp = await attacker_client.post(
            "/api/peak-demand/site-002/approve-recommendation",
            json={"recommendation_id": "fake-id"},
        )
        assert_blocked(resp, "POST /api/peak-demand/site-002/approve-recommendation")


# ---------------------------------------------------------------------------
# CROSS-SITE ALLOWED (attacker accesses their own site)
# ---------------------------------------------------------------------------


class TestCrossSiteAllowed:
    """Verify attacker CAN access their own site (site-003) — not over-blocking."""

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_attacker_own_site_not_403(self, attacker_client):
        """Attacker with site-003 access should not get 403 for site-003.

        NOTE: site-003 is not an active registered site in this environment
        (only site-002 exists). The attacker's allowedSites=['site-003'] profile
        is valid but the site has no DB entry, so has_access_to_site_code returns
        False. This is an environmental constraint, not an auth bug.
        This test is skipped until site-003 is activated.
        """
        pytest.skip("site-003 not active in this environment")


# ---------------------------------------------------------------------------
# NO-TOKEN TESTS
# ---------------------------------------------------------------------------


class TestUnauthenticatedAccess:
    """Verify endpoints reject requests with no auth token."""

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_no_token_buildings(self, anon_client):
        resp = await anon_client.get("/api/buildings/site-002")
        assert resp.status_code in (401, 403), f"Unauthenticated access returned {resp.status_code}"

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_no_token_sustainability(self, anon_client):
        resp = await anon_client.get("/api/sustainability/site-002/summary")
        assert resp.status_code in (401, 403), f"Unauthenticated access returned {resp.status_code}"

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_no_token_device_controls(self, anon_client):
        resp = await anon_client.post(
            "/api/device-controls/S002-AHU-B1-001/validate",
            params={"point": "setpoint", "value": "22"},
        )
        assert resp.status_code in (401, 403), f"Unauthenticated access returned {resp.status_code}"

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_no_token_peak_demand(self, anon_client):
        resp = await anon_client.get("/api/peak-demand/site-002/status")
        assert resp.status_code in (401, 403), f"Unauthenticated access returned {resp.status_code}"

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_no_token_3d_config(self, anon_client):
        resp = await anon_client.get("/api/buildings/site-002/config")
        assert resp.status_code in (401, 403), f"Unauthenticated access returned {resp.status_code}"

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_no_token_baselines(self, anon_client):
        resp = await anon_client.get("/api/equipment/baseline/S002-AHU-B1-001")
        assert resp.status_code in (401, 403), f"Unauthenticated access returned {resp.status_code}"


# ---------------------------------------------------------------------------
# ADMIN BYPASS TESTS
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Phase 2: List Endpoint / Filter Tampering BOLA Tests
# ---------------------------------------------------------------------------
#
# These test the "list endpoint leakage" attack: an attacker calls a
# collection endpoint with ?site_id=foreign-site and gets cross-tenant data.
# The attacker IS authenticated (as operator for site-003) but should NOT
# see site-002 data.
#
# Expected behavior: either 403 or response contains ZERO rows from site-002.
# ---------------------------------------------------------------------------


def _response_leaks_site(resp, forbidden_site: str = "site-002") -> bool:
    """Check if a JSON response body contains references to a forbidden site.

    Scans top-level list fields for site_id/site/building_id values, and also
    does a brute-force text scan of the response body for the site identifier.
    """
    if resp.status_code != 200:
        return False
    try:
        body = resp.json()
    except Exception:
        return False

    text = resp.text
    # Heuristic: if the forbidden site code appears anywhere in the response
    # body AND the response has data rows, that's a leak.
    if forbidden_site in text:
        # Check it's not just in an error message or empty context
        # Look for common list wrapper keys
        for key in (
            "equipment",
            "alerts",
            "anomalies",
            "generators",
            "centres",
            "ats_units",
            "mv_incomers",
            "transformers",
            "switchboards",
            "meters",
            "pfc_banks",
            "ups_systems",
            "feeders",
            "groups",
            "data",
            "items",
            "results",
            "work_orders",
            "contracts",
            "events",
            "records",
            "zones",
        ):
            items = body.get(key, [])
            if isinstance(items, list) and len(items) > 0:
                return True
        # Also check if body itself is a list
        if isinstance(body, list) and len(body) > 0:
            return True
    return False


@pytest.mark.security
class TestBOLAFilterTampering:
    """Verify that list endpoints with ?site_id= filter cannot leak cross-tenant data.

    Attack: operator with site-003 access calls GET /endpoint?site_id=site-002.
    Expected: 403, empty result, or only site-003 data.
    """

    # --- Equipment ---

    @pytest.mark.asyncio
    async def test_equipment_list_filter_tampering(self, attacker_client):
        resp = await attacker_client.get("/api/equipment", params={"site_id": "site-002"})
        assert resp.status_code == 403 or not _response_leaks_site(resp), (
            f"GET /equipment?site_id=site-002 leaked cross-tenant data: {resp.status_code}"
        )

    @pytest.mark.asyncio
    async def test_equipment_list_unfiltered(self, attacker_client):
        """Unfiltered list should only return attacker's own site data."""
        resp = await attacker_client.get("/api/equipment")
        assert not _response_leaks_site(resp), "GET /equipment (unfiltered) leaked site-002 data to site-003 user"

    @pytest.mark.asyncio
    async def test_equipment_stats_filter_tampering(self, attacker_client):
        resp = await attacker_client.get("/api/equipment-stats", params={"site_id": "site-002"})
        assert resp.status_code == 403 or not _response_leaks_site(resp), (
            f"GET /equipment-stats?site_id=site-002 leaked data: {resp.status_code}"
        )

    # --- Alerts ---

    @pytest.mark.asyncio
    async def test_alerts_filter_tampering(self, attacker_client):
        resp = await attacker_client.get("/api/alerts", params={"site_id": "site-002"})
        assert resp.status_code == 403 or not _response_leaks_site(resp), (
            f"GET /alerts?site_id=site-002 leaked data: {resp.status_code}"
        )

    @pytest.mark.asyncio
    async def test_anomalies_filter_tampering(self, attacker_client):
        resp = await attacker_client.get("/api/anomalies", params={"site_id": "site-002"})
        assert resp.status_code == 403 or not _response_leaks_site(resp), (
            f"GET /anomalies?site_id=site-002 leaked data: {resp.status_code}"
        )

    # --- Energy Centre ---

    @pytest.mark.asyncio
    async def test_energy_centre_filter_tampering(self, attacker_client):
        resp = await attacker_client.get("/api/energy-centre", params={"site_id": "site-002"})
        assert resp.status_code == 403 or not _response_leaks_site(resp), (
            f"GET /energy-centre?site_id=site-002 leaked data: {resp.status_code}"
        )

    @pytest.mark.asyncio
    async def test_energy_centre_ats_filter_tampering(self, attacker_client):
        resp = await attacker_client.get("/api/energy-centre/ats", params={"site_id": "site-002"})
        assert resp.status_code == 403 or not _response_leaks_site(resp), (
            f"GET /energy-centre/ats?site_id=site-002 leaked data: {resp.status_code}"
        )

    @pytest.mark.asyncio
    async def test_energy_centre_transformers_filter_tampering(self, attacker_client):
        resp = await attacker_client.get("/api/energy-centre/transformers", params={"site_id": "site-002"})
        assert resp.status_code == 403 or not _response_leaks_site(resp), (
            f"GET /energy-centre/transformers?site_id=site-002 leaked data: {resp.status_code}"
        )

    @pytest.mark.asyncio
    async def test_energy_centre_meters_filter_tampering(self, attacker_client):
        resp = await attacker_client.get("/api/energy-centre/meters", params={"site_id": "site-002"})
        assert resp.status_code == 403 or not _response_leaks_site(resp), (
            f"GET /energy-centre/meters?site_id=site-002 leaked data: {resp.status_code}"
        )

    @pytest.mark.asyncio
    async def test_energy_centre_ups_filter_tampering(self, attacker_client):
        resp = await attacker_client.get("/api/energy-centre/ups", params={"site_id": "site-002"})
        assert resp.status_code == 403 or not _response_leaks_site(resp), (
            f"GET /energy-centre/ups?site_id=site-002 leaked data: {resp.status_code}"
        )

    @pytest.mark.asyncio
    async def test_energy_centre_switchboards_filter_tampering(self, attacker_client):
        resp = await attacker_client.get("/api/energy-centre/switchboards", params={"site_id": "site-002"})
        assert resp.status_code == 403 or not _response_leaks_site(resp), (
            f"GET /energy-centre/switchboards?site_id=site-002 leaked data: {resp.status_code}"
        )

    @pytest.mark.asyncio
    async def test_energy_centre_feeders_filter_tampering(self, attacker_client):
        resp = await attacker_client.get("/api/energy-centre/feeders", params={"site_id": "site-002"})
        assert resp.status_code == 403 or not _response_leaks_site(resp), (
            f"GET /energy-centre/feeders?site_id=site-002 leaked data: {resp.status_code}"
        )

    @pytest.mark.asyncio
    async def test_energy_centre_pfc_filter_tampering(self, attacker_client):
        resp = await attacker_client.get("/api/energy-centre/pfc", params={"site_id": "site-002"})
        assert resp.status_code == 403 or not _response_leaks_site(resp), (
            f"GET /energy-centre/pfc?site_id=site-002 leaked data: {resp.status_code}"
        )

    @pytest.mark.asyncio
    async def test_energy_centre_mv_incomers_filter_tampering(self, attacker_client):
        resp = await attacker_client.get("/api/energy-centre/mv-incomers", params={"site_id": "site-002"})
        assert resp.status_code == 403 or not _response_leaks_site(resp), (
            f"GET /energy-centre/mv-incomers?site_id=site-002 leaked data: {resp.status_code}"
        )

    # --- Generators ---

    @pytest.mark.asyncio
    async def test_generators_filter_tampering(self, attacker_client):
        resp = await attacker_client.get("/api/generators", params={"site_id": "site-002"})
        assert resp.status_code == 403 or not _response_leaks_site(resp), (
            f"GET /generators?site_id=site-002 leaked data: {resp.status_code}"
        )

    @pytest.mark.asyncio
    async def test_generator_groups_filter_tampering(self, attacker_client):
        resp = await attacker_client.get("/api/generators/groups/list", params={"site_id": "site-002"})
        assert resp.status_code == 403 or not _response_leaks_site(resp), (
            f"GET /generators/groups/list?site_id=site-002 leaked data: {resp.status_code}"
        )

    # --- Work Orders ---

    @pytest.mark.asyncio
    async def test_work_orders_filter_tampering(self, attacker_client):
        resp = await attacker_client.get("/api/work-orders", params={"site_id": "site-002"})
        assert resp.status_code == 403 or not _response_leaks_site(resp), (
            f"GET /work-orders?site_id=site-002 leaked data: {resp.status_code}"
        )

    # --- Events ---

    @pytest.mark.asyncio
    async def test_events_active_filter_tampering(self, attacker_client):
        resp = await attacker_client.get("/api/events/active", params={"site_id": "site-002"})
        assert resp.status_code == 403 or not _response_leaks_site(resp), (
            f"GET /events/active?site_id=site-002 leaked data: {resp.status_code}"
        )

    @pytest.mark.asyncio
    async def test_events_history_filter_tampering(self, attacker_client):
        resp = await attacker_client.get("/api/events/history", params={"site_id": "site-002"})
        assert resp.status_code == 403 or not _response_leaks_site(resp), (
            f"GET /events/history?site_id=site-002 leaked data: {resp.status_code}"
        )

    # --- Occupancy Analytics ---

    @pytest.mark.asyncio
    async def test_occupancy_hourly_filter_tampering(self, attacker_client):
        resp = await attacker_client.get("/api/occupancy/analytics/hourly-trend", params={"site_id": "site-002"})
        assert resp.status_code == 403 or not _response_leaks_site(resp), (
            f"GET /occupancy/analytics/hourly-trend?site_id=site-002 leaked data: {resp.status_code}"
        )

    @pytest.mark.asyncio
    async def test_occupancy_utilization_filter_tampering(self, attacker_client):
        resp = await attacker_client.get("/api/occupancy/analytics/zone-utilization", params={"site_id": "site-002"})
        assert resp.status_code == 403 or not _response_leaks_site(resp), (
            f"GET /occupancy/analytics/zone-utilization?site_id=site-002 leaked data: {resp.status_code}"
        )

    # --- Contracts ---

    @pytest.mark.asyncio
    async def test_contracts_filter_tampering(self, attacker_client):
        resp = await attacker_client.get("/api/contracts/", params={"site_id": "site-002"})
        assert resp.status_code == 403 or not _response_leaks_site(resp), (
            f"GET /contracts/?site_id=site-002 leaked data: {resp.status_code}"
        )


class TestAdminBypass:
    """Verify admin role bypasses site restrictions (intended behavior)."""

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_admin_accesses_own_site(self, owner_client):
        resp = await owner_client.get("/api/buildings/site-002/equipment")
        assert_not_blocked(resp, "GET /api/buildings/site-002/equipment (admin)")

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_admin_accesses_other_site(self, owner_client):
        """Admin should also access site-003 despite demo config saying site-002 only."""
        resp = await owner_client.get("/api/buildings/site-003")
        assert_not_blocked(resp, "GET /api/buildings/site-003 (admin bypass)")
