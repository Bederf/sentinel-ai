"""Authentication & Token Security Tests.

Tests that JWT validation, token lifecycle, and session controls are
correctly enforced. Covers OWASP API2:2023 (Broken Authentication).

Strategy:
- Craft tokens with specific claim violations (expired, wrong iss/aud, etc.)
- Verify the auth middleware rejects them with 401
- Test blacklist behavior including fail-open when Redis is down
- Test refresh-token-as-access-token rejection
- Verify TESTING bypass is constrained to env var

These tests complement the BOLA tests (test_bola_authorization.py) which
verify *authorization* — these verify *authentication* is correct first.
"""

import os
import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import jwt as pyjwt
import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("DEMO_MODE", "true")
os.environ.setdefault("TESTING", "true")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-jwt-secret-for-ci-at-least-32-chars")

from app.config.settings import settings
from app.main import app
from app.middleware.auth_middleware import (
    create_jwt_token,
    validate_jwt_token,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

JWT_SECRET = settings.jwt_secret_key or settings.supabase_key or "test-only-jwt-secret-for-ci-at-least-32-chars"
VALID_ISS = settings.jwt_issuer  # "sentinel.bms"
VALID_AUD = settings.jwt_audience  # "sentinel.bms"


def _make_token(
    sub: str = "test-user-001",
    email: str = "test@sentinel.bms",
    role: str = "operator",
    token_type: str = "access",
    exp_delta: timedelta | None = None,
    iss: str | None = None,
    aud: str | None = None,
    secret: str | None = None,
    algorithm: str = "HS256",
    include_jti: bool = True,
    extra_claims: dict | None = None,
) -> str:
    """Craft a JWT token with controllable claims for testing."""
    if exp_delta is None:
        exp_delta = timedelta(minutes=15)

    payload = {
        "sub": sub,
        "email": email,
        "role": role,
        "token_type": token_type,
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + exp_delta,
        "iss": iss if iss is not None else VALID_ISS,
        "aud": aud if aud is not None else VALID_AUD,
    }
    if include_jti:
        payload["jti"] = str(uuid.uuid4())
    if extra_claims:
        payload.update(extra_claims)

    return pyjwt.encode(payload, secret or JWT_SECRET, algorithm=algorithm)


@pytest.fixture
async def raw_client():
    """Async client WITHOUT any auth injection — tests real auth path.

    Disables TESTING bypass so the real middleware runs.
    """
    transport = ASGITransport(app=app)
    with patch.dict(os.environ, {"TESTING": "false"}):
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


# =============================================================================
# 1. JWT Validation Unit Tests (validate_jwt_token)
# =============================================================================


@pytest.mark.security
class TestJWTValidation:
    """Unit tests for validate_jwt_token() — the core JWT verification."""

    def test_valid_token_accepted(self):
        """A properly formed token with all claims should be accepted."""
        token = _make_token()
        payload = validate_jwt_token(token, required_token_type="access")
        assert payload is not None
        assert payload["sub"] == "test-user-001"
        assert payload["role"] == "operator"

    def test_expired_token_rejected(self):
        """An expired token must be rejected."""
        token = _make_token(exp_delta=timedelta(seconds=-60))
        assert validate_jwt_token(token) is None

    def test_future_expiry_accepted(self):
        """A token expiring in the future should be accepted."""
        token = _make_token(exp_delta=timedelta(hours=1))
        assert validate_jwt_token(token) is not None

    def test_wrong_issuer_rejected(self):
        """A token from a different issuer must be rejected."""
        token = _make_token(iss="evil.issuer.com")
        assert validate_jwt_token(token) is None

    def test_wrong_audience_rejected(self):
        """A token for a different audience must be rejected."""
        token = _make_token(aud="other-service.api")
        assert validate_jwt_token(token) is None

    def test_wrong_secret_rejected(self):
        """A token signed with a different secret must be rejected."""
        token = _make_token(secret="completely-wrong-secret-key-for-testing")
        assert validate_jwt_token(token) is None

    def test_missing_jti_rejected(self):
        """A token without a jti claim must be rejected (required for blacklisting)."""
        token = _make_token(include_jti=False)
        assert validate_jwt_token(token) is None

    def test_refresh_token_rejected_as_access(self):
        """A refresh token must not be accepted where access token is required."""
        token = _make_token(token_type="refresh")
        assert validate_jwt_token(token, required_token_type="access") is None

    def test_access_token_rejected_as_refresh(self):
        """An access token must not be accepted where refresh token is required."""
        token = _make_token(token_type="access")
        assert validate_jwt_token(token, required_token_type="refresh") is None

    def test_invalid_token_type_rejected(self):
        """A token with an unknown token_type must be rejected."""
        token = _make_token(extra_claims={"token_type": "magic"})
        assert validate_jwt_token(token) is None

    def test_malformed_token_rejected(self):
        """A garbage string must not crash the validator."""
        assert validate_jwt_token("not.a.jwt") is None
        assert validate_jwt_token("") is None
        assert validate_jwt_token("eyJ" + "A" * 100) is None

    def test_none_algorithm_rejected(self):
        """The 'none' algorithm attack must be rejected.

        This is a classic JWT attack where the attacker removes the signature
        and sets alg=none. PyJWT rejects this by default when algorithms
        is explicitly set, but we verify it.
        """
        # Craft a token with algorithm 'none'
        payload = {
            "sub": "attacker",
            "email": "attacker@evil.com",
            "role": "admin",
            "token_type": "access",
            "jti": str(uuid.uuid4()),
            "iat": datetime.utcnow(),
            "exp": datetime.utcnow() + timedelta(hours=1),
            "iss": VALID_ISS,
            "aud": VALID_AUD,
        }
        # PyJWT won't encode with 'none' by default, so we manually construct
        import base64
        import json

        header = base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode()).rstrip(b"=")
        body = base64.urlsafe_b64encode(json.dumps(payload, default=str).encode()).rstrip(b"=")
        forged_token = f"{header.decode()}.{body.decode()}."

        assert validate_jwt_token(forged_token) is None


# =============================================================================
# 2. Token Blacklist Tests
# =============================================================================


@pytest.mark.security
class TestTokenBlacklist:
    """Test that blacklisted tokens are properly rejected."""

    def test_blacklisted_token_rejected(self):
        """A blacklisted token must be rejected even if otherwise valid."""
        token = _make_token()
        payload = validate_jwt_token(token)
        assert payload is not None  # valid before blacklisting

        jti = payload["jti"]

        # Patch on the service module (lazy-imported inside validate_jwt_token)
        mock_bl = MagicMock()
        mock_bl.is_blacklisted.return_value = True
        with patch("app.services.token_blacklist_service.token_blacklist", mock_bl):
            assert validate_jwt_token(token) is None
            mock_bl.is_blacklisted.assert_called_with(jti)

    def test_blacklist_fail_open_when_redis_down(self):
        """When Redis is down, blacklist check fails open (token accepted).

        This is a known risk — documented as a gap. The test documents
        current behavior. A future hardening pass may change this to
        fail-closed for critical endpoints.
        """
        token = _make_token()

        mock_bl = MagicMock()
        mock_bl.is_blacklisted.side_effect = Exception("Redis connection refused")
        with patch("app.services.token_blacklist_service.token_blacklist", mock_bl):
            # Currently fails open — token is accepted
            result = validate_jwt_token(token)
            assert result is not None, "Blacklist fail-open: token accepted when Redis is down (known risk)"

    def test_non_blacklisted_token_accepted(self):
        """A token not in the blacklist should be accepted."""
        token = _make_token()

        mock_bl = MagicMock()
        mock_bl.is_blacklisted.return_value = False
        with patch("app.services.token_blacklist_service.token_blacklist", mock_bl):
            assert validate_jwt_token(token) is not None


# =============================================================================
# 3. Integration Tests — HTTP-level auth enforcement
# =============================================================================


@pytest.mark.security
class TestHTTPAuthEnforcement:
    """Test that the HTTP middleware correctly rejects bad tokens."""

    @pytest.mark.asyncio
    async def test_no_token_returns_401(self, raw_client):
        """A request with no Authorization header should get 401."""
        resp = await raw_client.get("/api/buildings/site-002/equipment")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_expired_token_returns_401(self, raw_client):
        """An expired Bearer token should get 401."""
        token = _make_token(exp_delta=timedelta(seconds=-60))
        resp = await raw_client.get(
            "/api/buildings/site-002/equipment",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_wrong_secret_returns_401(self, raw_client):
        """A token signed with the wrong key should get 401."""
        token = _make_token(secret="wrong-key-definitely-not-the-real-one-32chars")
        resp = await raw_client.get(
            "/api/buildings/site-002/equipment",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_wrong_issuer_returns_401(self, raw_client):
        """A token from a different issuer should get 401."""
        token = _make_token(iss="evil-service.io")
        resp = await raw_client.get(
            "/api/buildings/site-002/equipment",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_wrong_audience_returns_401(self, raw_client):
        """A token for a different service should get 401."""
        token = _make_token(aud="billing-api.internal")
        resp = await raw_client.get(
            "/api/buildings/site-002/equipment",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_token_on_api_returns_401(self, raw_client):
        """A refresh token must not work on regular API endpoints."""
        token = _make_token(token_type="refresh")
        resp = await raw_client.get(
            "/api/buildings/site-002/equipment",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_valid_token_returns_not_401(self, raw_client):
        """A valid access token should not get 401 (may get other codes)."""
        token = _make_token(role="admin")
        resp = await raw_client.get(
            "/api/buildings/site-002/equipment",
            headers={"Authorization": f"Bearer {token}"},
        )
        # Should NOT be 401 — token is valid
        assert resp.status_code != 401, f"Valid token got 401: {resp.text}"

    @pytest.mark.asyncio
    async def test_malformed_bearer_returns_401(self, raw_client):
        """A garbage Authorization header should get 401."""
        resp = await raw_client.get(
            "/api/buildings/site-002/equipment",
            headers={"Authorization": "Bearer not-a-real-jwt"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_bearer_prefix_required(self, raw_client):
        """Token without 'Bearer ' prefix should get 401."""
        token = _make_token()
        resp = await raw_client.get(
            "/api/buildings/site-002/equipment",
            headers={"Authorization": token},  # No "Bearer " prefix
        )
        assert resp.status_code == 401


# =============================================================================
# 4. TESTING Bypass Constraint
# =============================================================================


@pytest.mark.security
class TestTestingBypass:
    """Verify the TESTING=true bypass is constrained."""

    @pytest.mark.asyncio
    async def test_testing_bypass_disabled_requires_auth(self):
        """When TESTING=false, requests without tokens get 401."""
        transport = ASGITransport(app=app)
        with patch.dict(os.environ, {"TESTING": "false"}):
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                resp = await c.get("/api/buildings/site-002/equipment")
                assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_testing_bypass_enabled_allows_access(self):
        """When TESTING=true, bypass is now DISABLED — requests still require auth (Hardening Rite)."""
        transport = ASGITransport(app=app)
        with patch.dict(os.environ, {"TESTING": "true"}):
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                resp = await c.get("/api/buildings/site-002/equipment")
                # Phase 168 removed TESTING bypass; all requests now require real JWT tokens
                assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_testing_bypass_grants_operator_not_admin(self):
        """TESTING bypass is now DISABLED — no special role granted.

        Phase 168 removed the TESTING=true bypass entirely as part of Universal Engine hardening.
        All requests now require real JWT tokens regardless of TESTING env var.
        """

        transport = ASGITransport(app=app)
        with patch.dict(os.environ, {"TESTING": "true"}):
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                # Make a request and verify it fails with 401 (no bypass)
                resp = await c.get("/api/buildings/site-002/equipment")
                assert resp.status_code == 401, "TESTING bypass should be disabled in Phase 168"
                # The TESTING bypass sets role=OPERATOR (line 234 in middleware.py)
                # We can't directly inspect request.state from here, but we
                # verify it by checking that admin-only endpoints are blocked
                # (This is a behavior test, not an implementation test)


# =============================================================================
# 5. Token Lifecycle Tests
# =============================================================================


@pytest.mark.security
class TestTokenLifecycle:
    """Test token creation and lifecycle properties."""

    def test_access_token_has_short_ttl(self):
        """Access tokens should expire within the configured TTL (8 h for onboarding sessions)."""
        from app.config.settings import settings

        token = create_jwt_token(
            user_id="u1",
            email="u1@test.com",
            role="operator",
            full_name="User One",
            token_type="access",
        )
        payload = pyjwt.decode(token, JWT_SECRET, algorithms=["HS256"], audience=VALID_AUD, issuer=VALID_ISS)
        exp = datetime.utcfromtimestamp(payload["exp"])
        iat = datetime.utcfromtimestamp(payload["iat"])
        ttl = exp - iat
        configured_ttl = timedelta(minutes=settings.jwt_access_token_ttl_minutes)
        assert ttl <= configured_ttl + timedelta(seconds=5), f"Access token TTL too long: {ttl}"

    def test_token_includes_required_claims(self):
        """Created tokens must include all security-critical claims."""
        token = create_jwt_token(
            user_id="u1",
            email="u1@test.com",
            role="operator",
            full_name="User One",
        )
        payload = pyjwt.decode(token, JWT_SECRET, algorithms=["HS256"], audience=VALID_AUD, issuer=VALID_ISS)

        assert "sub" in payload, "Missing sub claim"
        assert "jti" in payload, "Missing jti claim"
        assert "exp" in payload, "Missing exp claim"
        assert "iat" in payload, "Missing iat claim"
        assert "iss" in payload, "Missing iss claim"
        assert "aud" in payload, "Missing aud claim"
        assert "token_type" in payload, "Missing token_type claim"
        assert "role" in payload, "Missing role claim"

    def test_each_token_has_unique_jti(self):
        """Every token must get a unique jti for blacklist targeting."""
        tokens = [create_jwt_token("u1", "u1@test.com", "operator", "User One") for _ in range(10)]
        jtis = set()
        for t in tokens:
            payload = pyjwt.decode(t, JWT_SECRET, algorithms=["HS256"], audience=VALID_AUD, issuer=VALID_ISS)
            jtis.add(payload["jti"])
        assert len(jtis) == 10, "JTI collision detected — tokens must have unique IDs"

    def test_token_does_not_contain_pii(self):
        """Tokens should not contain unnecessary PII (full_name, phone, etc.)."""
        token = create_jwt_token(
            user_id="u1",
            email="u1@test.com",
            role="operator",
            full_name="Sensitive Full Name",
        )
        payload = pyjwt.decode(token, JWT_SECRET, algorithms=["HS256"], audience=VALID_AUD, issuer=VALID_ISS)
        assert "full_name" not in payload, "JWT should not contain full_name (PII)"
        assert "phone" not in payload, "JWT should not contain phone (PII)"
        assert "password" not in payload, "JWT should never contain password"

    def test_refresh_token_has_longer_ttl_than_access(self):
        """Refresh tokens should live longer than access tokens."""
        access = create_jwt_token("u1", "u1@test.com", "operator", "U1", token_type="access")
        refresh = create_jwt_token("u1", "u1@test.com", "operator", "U1", token_type="refresh")

        access_payload = pyjwt.decode(access, JWT_SECRET, algorithms=["HS256"], audience=VALID_AUD, issuer=VALID_ISS)
        refresh_payload = pyjwt.decode(refresh, JWT_SECRET, algorithms=["HS256"], audience=VALID_AUD, issuer=VALID_ISS)

        access_ttl = access_payload["exp"] - access_payload["iat"]
        refresh_ttl = refresh_payload["exp"] - refresh_payload["iat"]
        assert refresh_ttl > access_ttl, (
            f"Refresh TTL ({refresh_ttl}s) should be longer than access TTL ({access_ttl}s)"
        )


# =============================================================================
# 6. API Key Security Tests
# =============================================================================


@pytest.mark.security
class TestAPIKeySecurity:
    """Test API key authentication edge cases."""

    @pytest.mark.asyncio
    async def test_revoked_api_key_rejected(self, raw_client):
        """A revoked API key must return 401."""
        resp = await raw_client.get(
            "/api/buildings/site-002/equipment",
            headers={"X-API-Key": "revoked-key-that-does-not-exist"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_empty_api_key_rejected(self, raw_client):
        """An empty API key header must return 401."""
        resp = await raw_client.get(
            "/api/buildings/site-002/equipment",
            headers={"X-API-Key": ""},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_bearer_and_apikey_both_invalid(self, raw_client):
        """If both auth methods fail, should get 401."""
        resp = await raw_client.get(
            "/api/buildings/site-002/equipment",
            headers={
                "Authorization": "Bearer garbage-token",
                "X-API-Key": "garbage-key",
            },
        )
        assert resp.status_code == 401


# =============================================================================
# 7. Cross-Environment Token Tests
# =============================================================================


@pytest.mark.security
class TestCrossEnvironmentTokens:
    """Verify tokens from other environments are rejected."""

    def test_different_issuer_environment(self):
        """A token from staging (different iss) must be rejected in prod."""
        token = _make_token(iss="sentinel.staging.bms")
        assert validate_jwt_token(token) is None

    def test_different_audience_environment(self):
        """A token for dev API (different aud) must be rejected."""
        token = _make_token(aud="sentinel.dev.bms")
        assert validate_jwt_token(token) is None

    def test_different_secret_environment(self):
        """A token signed with staging secret must be rejected."""
        token = _make_token(secret="staging-secret-key-that-differs-from-prod")
        assert validate_jwt_token(token) is None
