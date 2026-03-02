"""
Tests for login endpoint — unknown emails must be rejected with 403.
"""

from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _create_login_app():
    """Create a minimal app with just the auth router for testing."""
    from app.api.auth import router

    app = FastAPI()
    app.include_router(router)
    return app


class TestLoginRejectsUnknownEmail:
    """POST /api/auth/login rejects unregistered emails."""

    def test_unknown_email_returns_403(self):
        """An email not in sentinel_users should get 403."""
        app = _create_login_app()
        client = TestClient(app)

        with patch("app.api.auth._user_repo") as mock_repo:
            mock_repo.get_user_by_email.return_value = None

            response = client.post("/api/auth/login?email=nobody@unknown.com")

            assert response.status_code == 403
            body = response.json()
            assert "not registered" in body["detail"].lower()

    def test_registered_email_succeeds(self):
        """A registered email should get a valid token response."""
        app = _create_login_app()
        client = TestClient(app)

        fake_user = {
            "user_id": "user-bederf",
            "email": "bederf@gmail.com",
            "full_name": "Bederf Admin",
            "role": "admin",
        }

        with (
            patch("app.api.auth._user_repo") as mock_repo,
            patch("app.api.auth.get_mfa_service") as mock_mfa_factory,
            patch("app.api.auth._create_jwt_token", return_value="fake.jwt.token"),
            patch("app.api.auth.validate_jwt_token", return_value={"jti": "abc"}),
            patch("app.api.auth.session_service") as mock_session,
        ):
            mock_repo.get_user_by_email.return_value = fake_user
            mock_mfa = MagicMock()
            mock_mfa.is_mfa_required.return_value = False
            mock_mfa.is_mfa_enrolled.return_value = False
            mock_mfa.is_mfa_enabled.return_value = False
            mock_mfa_factory.return_value = mock_mfa
            mock_session.create_session.return_value = "sess-123"

            response = client.post("/api/auth/login?email=bederf@gmail.com")

            assert response.status_code == 200
            body = response.json()
            assert body["access_token"] == "fake.jwt.token"
            assert body["user"]["email"] == "bederf@gmail.com"
            assert body["user"]["role"] == "admin"

    def test_mfa_complete_rejects_unknown_email(self):
        """complete_mfa_login rejects unregistered email."""
        app = _create_login_app()
        client = TestClient(app)

        with patch("app.api.auth._user_repo") as mock_repo:
            mock_repo.get_user_by_email.return_value = None

            response = client.post("/api/auth/login/mfa-complete?email=nobody@unknown.com&mfa_code=123456")

            assert response.status_code == 403
            body = response.json()
            assert "not registered" in body["detail"].lower()
