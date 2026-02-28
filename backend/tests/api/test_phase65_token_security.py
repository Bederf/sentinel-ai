from datetime import datetime, timedelta

import jwt as pyjwt
import pytest
from starlette.requests import Request

from app.api import auth as auth_api
from app.config.settings import settings
from app.startup.middleware import _admin_requests_by_ip, _check_admin_rate_limit
from app.middleware.auth_middleware import validate_jwt_token


def _make_request(path: str = "/api/auth/refresh") -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": path,
        "headers": [],
        "query_string": b"",
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "scheme": "http",
        "http_version": "1.1",
    }
    return Request(scope)


def test_validate_jwt_token_rejects_missing_jti():
    secret = settings.jwt_secret_key or settings.supabase_key or "test-only-jwt-secret"
    payload = {
        "sub": "user-1",
        "email": "user@example.com",
        "role": "auditor",
        "full_name": "User One",
        "token_type": "access",
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(minutes=5),
        "iss": "sentinel.bms",
    }
    token = pyjwt.encode(payload, secret, algorithm="HS256")
    assert validate_jwt_token(token) is None


@pytest.mark.asyncio
async def test_refresh_rotation_blacklists_old_refresh_token(monkeypatch):
    future_exp = int((datetime.utcnow() + timedelta(minutes=10)).timestamp())
    payload = {
        "sub": "user-1",
        "email": "user@example.com",
        "full_name": "User One",
        "role": "auditor",
        "token_type": "refresh",
        "jti": "old-refresh-jti",
        "exp": future_exp,
    }

    blacklisted: list[tuple[str, int]] = []
    minted: list[str] = []

    monkeypatch.setattr(
        auth_api,
        "validate_jwt_token",
        lambda token, **kwargs: payload,
    )
    monkeypatch.setattr(
        auth_api.token_blacklist,
        "blacklist_token",
        lambda jti, ttl_seconds: blacklisted.append((jti, ttl_seconds)) or True,
    )
    monkeypatch.setattr(
        auth_api,
        "_create_jwt_token",
        lambda user_info, token_type="access": minted.append(f"{token_type}-token-{len(minted)}") or minted[-1],
    )

    body = auth_api.RefreshTokenRequest(refresh_token="old-refresh-token")
    result = await auth_api.refresh_access_token(_make_request(), body)

    assert result["access_token"].startswith("access-token-")
    assert result["refresh_token"].startswith("refresh-token-")
    assert blacklisted
    assert blacklisted[0][0] == "old-refresh-jti"
    assert blacklisted[0][1] > 0


@pytest.mark.asyncio
async def test_logout_blacklists_access_and_refresh(monkeypatch):
    access_payload = {
        "jti": "access-jti",
        "exp": int((datetime.utcnow() + timedelta(minutes=5)).timestamp()),
        "token_type": "access",
    }
    refresh_payload = {
        "jti": "refresh-jti",
        "exp": int((datetime.utcnow() + timedelta(days=1)).timestamp()),
        "token_type": "refresh",
    }

    calls: list[tuple[str, int]] = []

    def fake_validate(token: str, **kwargs):
        if token == "access-token":
            return access_payload
        if token == "refresh-token":
            return refresh_payload
        return None

    monkeypatch.setattr(auth_api, "validate_jwt_token", fake_validate)
    monkeypatch.setattr(
        auth_api.token_blacklist,
        "blacklist_token",
        lambda jti, ttl_seconds: calls.append((jti, ttl_seconds)) or True,
    )

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/auth/logout",
            "headers": [(b"authorization", b"Bearer access-token")],
            "query_string": b"",
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
            "scheme": "http",
            "http_version": "1.1",
        }
    )

    result = await auth_api.logout(request, refresh_token="refresh-token")

    assert result["message"] == "Logged out successfully"
    assert len(calls) == 2
    assert {call[0] for call in calls} == {"access-jti", "refresh-jti"}


def test_admin_rate_limit_blocks_31st_request():
    ip = "203.0.113.10"
    _admin_requests_by_ip[ip] = []

    for _ in range(30):
        assert _check_admin_rate_limit(ip) is None

    blocked = _check_admin_rate_limit(ip)
    assert blocked is not None
    assert blocked.status_code == 429
