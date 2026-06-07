"""Tests for Visit Service, Policy Engine, and Reception API — Phase 176-04."""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.models.visit import Visit, VisitStatus
from app.services.visit_policy_engine import VisitPolicyEngine
from app.services.visit_token_service import VisitTokenService

# ---------------------------------------------------------------------------
# Auth — required for all API tests
# ---------------------------------------------------------------------------

os.environ.setdefault("JWT_SECRET_KEY", "test-only-jwt-secret-for-ci-at-least-32-chars")


def _make_token(role: str = "operator") -> str:
    """Create a JWT token for API tests."""
    from app.middleware.auth_middleware import create_jwt_token

    return create_jwt_token(
        user_id=f"test-user-{role}",
        email=f"test@{role}.sentinel.bms",
        role=role,
        full_name=f"Test {role.title()}",
    )


def _auth_headers(role: str = "operator") -> dict:
    return {"Authorization": f"Bearer {_make_token(role)}"}


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

TEST_VISIT_STORE = {"visits": []}


@pytest.fixture
def mock_visit_store(tmp_path: Path) -> Generator[None, None, None]:
    """Create a temporary visit store and patch all file paths."""
    visit_store = tmp_path / "visit_store.json"
    lock_file = tmp_path / "visit_store.lock"
    visit_store.write_text(json.dumps({"visits": []}))

    with patch("app.database.repositories.visit_repository.DATA_DIR", tmp_path):
        yield


@pytest.fixture
def sample_visit() -> Visit:
    """Create a sample visit in CREATED status."""
    now = datetime.now(UTC)
    return Visit(
        id=uuid.uuid4(),
        token=uuid.uuid4(),
        pin="123456",
        visitor_email="visitor@example.com",
        visitor_name="John Visitor",
        host_email="host@fnb.co.za",
        host_name="Jane Host",
        building_id="site-001",
        meeting_start=now + timedelta(minutes=15),
        meeting_end=now + timedelta(hours=1),
        status=VisitStatus.CREATED,
        qr_code=None,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def arrived_visit(sample_visit: Visit) -> Visit:
    """Visit that has been scanned at reception."""
    return sample_visit.model_copy(update={"status": VisitStatus.ARRIVED})


@pytest.fixture
def registered_visit(arrived_visit: Visit) -> Visit:
    """Visit that has been registered at reception."""
    return arrived_visit.model_copy(
        update={
            "status": VisitStatus.REGISTERED,
            "visitor_name": "John Visitor",
            "visitor_photo": "base64photodata",
        }
    )


# ---------------------------------------------------------------------------
# TestVisitTokenService
# ---------------------------------------------------------------------------


class TestVisitTokenService:
    """Tests for VisitTokenService token/PIN/QR generation."""

    def test_generate_token_is_uuid(self, mock_visit_store: None) -> None:
        """Token should be a valid UUID4."""
        service = VisitTokenService()
        token = service.generate_token()
        assert isinstance(token, uuid.UUID)
        assert token.version == 4

    def test_generate_pin_is_6_digits(self, mock_visit_store: None) -> None:
        """PIN should be a zero-padded 6-digit string."""
        service = VisitTokenService()
        for _ in range(100):
            pin = service.generate_pin()
            assert isinstance(pin, str)
            assert len(pin) == 6
            assert pin.isdigit()

    def test_generate_pin_in_range(self, mock_visit_store: None) -> None:
        """PIN numeric value should be between 0 and 999999."""
        service = VisitTokenService()
        for _ in range(100):
            pin = service.generate_pin()
            assert 0 <= int(pin) <= 999999

    def test_generate_qr_code_is_base64_png(self, mock_visit_store: None) -> None:
        """QR code should be a base64-encoded PNG string."""
        import base64

        service = VisitTokenService()
        token = uuid.uuid4()
        qr_code = service.generate_qr_code(token)

        assert isinstance(qr_code, str)
        assert len(qr_code) > 0
        # Decode and check PNG magic bytes
        decoded = base64.b64decode(qr_code)
        assert decoded[:4] == b"\x89PNG"

    def test_create_visit_token_returns_visit_with_token_and_pin(self, mock_visit_store: None) -> None:
        """create_visit_token should return a Visit with token, pin, and qr_code."""
        service = VisitTokenService()
        now = datetime.now(UTC)
        visit, qr_code = service.create_visit_token(
            visitor_email="visitor@example.com",
            host_email="host@fnb.co.za",
            building_id="site-001",
            meeting_start=now + timedelta(minutes=15),
            meeting_end=now + timedelta(hours=1),
            visitor_name="John Visitor",
        )
        assert isinstance(visit, Visit)
        assert isinstance(visit.token, uuid.UUID)
        assert isinstance(visit.pin, str)
        assert len(visit.pin) == 6
        assert isinstance(qr_code, str)
        assert visit.status == VisitStatus.CREATED
        assert visit.visitor_email == "visitor@example.com"
        assert visit.visitor_name == "John Visitor"

    def test_validate_token_returns_visit(self, mock_visit_store: None) -> None:
        """validate_token should return the Visit for a known token."""
        service = VisitTokenService()
        now = datetime.now(UTC)
        visit, _ = service.create_visit_token(
            visitor_email="visitor@example.com",
            host_email="host@fnb.co.za",
            building_id="site-001",
            meeting_start=now + timedelta(minutes=15),
            meeting_end=now + timedelta(hours=1),
        )
        found = service.validate_token(visit.token)
        assert found is not None
        assert found.token == visit.token

    def test_validate_token_returns_none_for_nonexistent(self, mock_visit_store: None) -> None:
        """validate_token should return None for an unknown token."""
        service = VisitTokenService()
        found = service.validate_token(uuid.uuid4())
        assert found is None

    def test_validate_pin_returns_visit(self, mock_visit_store: None) -> None:
        """validate_pin should return the Visit for a known PIN."""
        service = VisitTokenService()
        now = datetime.now(UTC)
        visit, _ = service.create_visit_token(
            visitor_email="visitor@example.com",
            host_email="host@fnb.co.za",
            building_id="site-001",
            meeting_start=now + timedelta(minutes=15),
            meeting_end=now + timedelta(hours=1),
        )
        found = service.validate_pin(visit.pin)
        assert found is not None
        assert found.pin == visit.pin

    def test_is_valid_time_window_within_range(self, sample_visit: Visit) -> None:
        """Visit within window should be valid."""
        # sample_visit has meeting_start in 15 min, meeting_end in 1 hour
        service = VisitTokenService()
        result = service.is_valid_time_window(sample_visit)
        assert result is True

    def test_is_valid_time_window_too_early(self, sample_visit: Visit) -> None:
        """Visit with meeting_start too far in future should be invalid."""
        sample_visit.meeting_start = datetime.now(UTC) + timedelta(hours=2)
        sample_visit.meeting_end = datetime.now(UTC) + timedelta(hours=3)
        service = VisitTokenService()
        result = service.is_valid_time_window(sample_visit)
        assert result is False

    def test_is_valid_time_window_expired(self, sample_visit: Visit) -> None:
        """Visit past meeting_end + 60 min grace should be expired."""
        sample_visit.meeting_start = datetime.now(UTC) - timedelta(hours=3)
        sample_visit.meeting_end = datetime.now(UTC) - timedelta(hours=2)
        service = VisitTokenService()
        result = service.is_valid_time_window(sample_visit)
        assert result is False


# ---------------------------------------------------------------------------
# TestVisitPolicyEngine
# ---------------------------------------------------------------------------


class TestVisitPolicyEngine:
    """Tests for VisitPolicyEngine scan/registration/access policy checks."""

    def _make_engine(self, mock_repo: MagicMock) -> VisitPolicyEngine:
        return VisitPolicyEngine(repo=mock_repo)

    def test_scan_requires_token_or_pin(self, mock_visit_store: None) -> None:
        """Scan without token or PIN should be rejected."""
        mock_repo = MagicMock()
        engine = self._make_engine(mock_repo)
        result = engine.check_scan_policy()
        assert result.allowed is False
        assert result.reason == "no credentials"
        assert result.status_code == 401

    def test_scan_rejects_nonexistent_token(self, mock_visit_store: None) -> None:
        """Scan with unknown token should return 404."""
        mock_repo = MagicMock()
        mock_repo.get_visit_by_token.return_value = None
        engine = self._make_engine(mock_repo)
        result = engine.check_scan_policy(token=uuid.uuid4())
        assert result.allowed is False
        assert result.reason == "visit not found"
        assert result.status_code == 404

    def test_scan_rejects_expired_visit(self, sample_visit: Visit) -> None:
        """Scan for a visit past meeting_end + 60 min should be rejected."""
        mock_repo = MagicMock()
        past = datetime.now(UTC) - timedelta(hours=3)
        expired_visit = sample_visit.model_copy(
            update={
                "meeting_start": past - timedelta(hours=1),
                "meeting_end": past,
            }
        )
        mock_repo.get_visit_by_token.return_value = expired_visit
        engine = self._make_engine(mock_repo)
        result = engine.check_scan_policy(token=expired_visit.token)
        assert result.allowed is False
        assert result.reason == "visit expired"
        assert result.status_code == 410

    def test_scan_rejects_cancelled_visit(self, sample_visit: Visit) -> None:
        """Scan for a CANCELLED visit should be rejected."""
        mock_repo = MagicMock()
        cancelled = sample_visit.model_copy(update={"status": VisitStatus.CANCELLED})
        mock_repo.get_visit_by_token.return_value = cancelled
        engine = self._make_engine(mock_repo)
        result = engine.check_scan_policy(token=cancelled.token)
        assert result.allowed is False
        assert result.reason == "visit cancelled"
        assert result.status_code == 410

    def test_scan_rejects_denied_visit(self, sample_visit: Visit) -> None:
        """Scan for a DENIED visit should be rejected."""
        mock_repo = MagicMock()
        denied = sample_visit.model_copy(update={"status": VisitStatus.DENIED})
        mock_repo.get_visit_by_token.return_value = denied
        engine = self._make_engine(mock_repo)
        result = engine.check_scan_policy(token=denied.token)
        assert result.allowed is False
        assert result.reason == "host denied access"
        assert result.status_code == 403

    def test_scan_rejects_too_early(self, sample_visit: Visit) -> None:
        """Scan more than 30 min before meeting_start should be rejected."""
        mock_repo = MagicMock()
        early = sample_visit.model_copy(
            update={
                "meeting_start": datetime.now(UTC) + timedelta(hours=2),
                "meeting_end": datetime.now(UTC) + timedelta(hours=3),
            }
        )
        mock_repo.get_visit_by_token.return_value = early
        engine = self._make_engine(mock_repo)
        result = engine.check_scan_policy(token=early.token)
        assert result.allowed is False
        assert result.reason == "too early"
        assert result.status_code == 403

    def test_scan_accepts_valid_visit(self, sample_visit: Visit) -> None:
        """Valid visit within time window should be allowed."""
        mock_repo = MagicMock()
        now = datetime.now(UTC)
        valid = sample_visit.model_copy(
            update={
                "meeting_start": now + timedelta(minutes=10),
                "meeting_end": now + timedelta(hours=1),
            }
        )
        mock_repo.get_visit_by_token.return_value = valid
        engine = self._make_engine(mock_repo)
        result = engine.check_scan_policy(token=valid.token)
        assert result.allowed is True
        assert result.reason == "allowed"
        assert result.status_code == 200
        assert result.visit is not None

    def test_registration_rejects_expired(self, sample_visit: Visit) -> None:
        """Registration for EXPIRED visit should be rejected."""
        mock_repo = MagicMock()
        expired = sample_visit.model_copy(update={"status": VisitStatus.EXPIRED})
        engine = self._make_engine(mock_repo)
        result = engine.check_registration_policy(expired)
        assert result.allowed is False
        assert result.reason == "visit expired"
        assert result.status_code == 410

    def test_registration_rejects_already_active(self, registered_visit: Visit) -> None:
        """Registration for already-ACTIVE visit should be rejected (409)."""
        mock_repo = MagicMock()
        active = registered_visit.model_copy(update={"status": VisitStatus.ACTIVE, "access_card_id": "CARD-001"})
        engine = self._make_engine(mock_repo)
        result = engine.check_registration_policy(active)
        assert result.allowed is False
        assert result.reason == "already active"
        assert result.status_code == 409

    def test_access_issue_requires_registered_status(self, arrived_visit: Visit) -> None:
        """Access card issue should require REGISTERED or APPROVED status."""
        mock_repo = MagicMock()
        engine = self._make_engine(mock_repo)
        result = engine.check_access_issue_policy(arrived_visit)
        assert result.allowed is False
        assert result.reason == "visitor not registered"
        assert result.status_code == 400

    def test_access_issue_rejects_denied(self, sample_visit: Visit) -> None:
        """Access card issue for DENIED visit should be rejected."""
        mock_repo = MagicMock()
        denied = sample_visit.model_copy(update={"status": VisitStatus.DENIED})
        engine = self._make_engine(mock_repo)
        result = engine.check_access_issue_policy(denied)
        # DENIED is caught by "not in (REGISTERED, APPROVED)" check first
        assert result.allowed is False
        assert result.reason == "visitor not registered"
        assert result.status_code == 400

    def test_access_issue_rejects_expired(self, sample_visit: Visit) -> None:
        """Access card issue for EXPIRED visit should be rejected."""
        mock_repo = MagicMock()
        expired = sample_visit.model_copy(update={"status": VisitStatus.EXPIRED})
        engine = self._make_engine(mock_repo)
        result = engine.check_access_issue_policy(expired)
        # EXPIRED is caught by "not in (REGISTERED, APPROVED)" check first
        assert result.allowed is False
        assert result.reason == "visitor not registered"
        assert result.status_code == 400

    def test_access_issue_accepts_registered(self, registered_visit: Visit) -> None:
        """Access card issue for REGISTERED visit should be allowed."""
        mock_repo = MagicMock()
        engine = self._make_engine(mock_repo)
        result = engine.check_access_issue_policy(registered_visit)
        assert result.allowed is True
        assert result.reason == "allowed"
        assert result.status_code == 200

    def test_access_issue_accepts_approved(self, sample_visit: Visit) -> None:
        """Access card issue for APPROVED (host-whatsapp) visit should be allowed."""
        mock_repo = MagicMock()
        approved = sample_visit.model_copy(update={"status": VisitStatus.APPROVED})
        engine = self._make_engine(mock_repo)
        result = engine.check_access_issue_policy(approved)
        assert result.allowed is True
        assert result.reason == "allowed"
        assert result.status_code == 200


# ---------------------------------------------------------------------------
# TestReceptionAPI — call route functions directly (avoids HTTP import-order issues)
# ---------------------------------------------------------------------------


class TestReceptionAPI:
    """Tests for Reception API route functions called directly.

    These tests call the FastAPI route functions directly as Python functions,
    bypassing HTTP to allow clean mocking of VisitService.
    """

    def test_scan_with_token_returns_visit(self, sample_visit: Visit) -> None:
        """scan_visit route function returns visit for valid token."""
        arrived = sample_visit.model_copy(update={"status": VisitStatus.ARRIVED})
        mock_service = MagicMock()
        mock_service.arrive_visit.return_value = arrived
        mock_service.get_building_name.return_value = "Fairlands Head Office"

        from app.services.visit_policy_engine import PolicyResult

        mock_policy = MagicMock()
        mock_policy.check_scan_policy.return_value = PolicyResult(
            allowed=True,
            reason="",
            status_code=200,
            visit=sample_visit,
        )

        with (
            patch("app.api.reception.VisitService", return_value=mock_service),
            patch("app.api.reception.VisitPolicyEngine", return_value=mock_policy),
        ):
            from app.api.reception import scan_visit
            from app.schemas.visit import ScanRequest

            request = ScanRequest(token=sample_visit.token)
            response = scan_visit(request)

        mock_policy.check_scan_policy.assert_called_once()
        assert response.visit.token == sample_visit.token
        assert response.visit.status == VisitStatus.ARRIVED.value
        assert response.time_window_valid is True

    def test_scan_with_pin_returns_visit(self, sample_visit: Visit) -> None:
        """scan_visit route function returns visit for valid PIN."""
        arrived = sample_visit.model_copy(update={"status": VisitStatus.ARRIVED})
        mock_service = MagicMock()
        mock_service.arrive_visit.return_value = arrived
        mock_service.get_building_name.return_value = "Fairlands Head Office"

        from app.services.visit_policy_engine import PolicyResult

        mock_policy = MagicMock()
        mock_policy.check_scan_policy.return_value = PolicyResult(
            allowed=True,
            reason="",
            status_code=200,
            visit=sample_visit,
        )

        with (
            patch("app.api.reception.VisitService", return_value=mock_service),
            patch("app.api.reception.VisitPolicyEngine", return_value=mock_policy),
        ):
            from app.api.reception import scan_visit
            from app.schemas.visit import ScanRequest

            request = ScanRequest(pin=sample_visit.pin)
            response = scan_visit(request)

        mock_policy.check_scan_policy.assert_called_once()
        assert response.visit.token == sample_visit.token

    def test_scan_not_found_returns_404(self) -> None:
        """scan_visit raises HTTPException 404 for unknown token."""
        from app.services.visit_policy_engine import PolicyResult

        mock_policy = MagicMock()
        mock_policy.check_scan_policy.return_value = PolicyResult(
            allowed=False,
            reason="visit not found",
            status_code=404,
            visit=None,
        )

        with patch("app.api.reception.VisitPolicyEngine", return_value=mock_policy):
            from fastapi import HTTPException

            from app.api.reception import scan_visit
            from app.schemas.visit import ScanRequest

            request = ScanRequest(token=uuid.uuid4())
            with pytest.raises(HTTPException) as exc_info:
                scan_visit(request)
            assert exc_info.value.status_code == 404

    def test_register_updates_existing_visit(self, arrived_visit: Visit, registered_visit: Visit) -> None:
        """register_visit route function updates visit and returns RegisterResponse."""
        mock_service = MagicMock()
        mock_service.scan_visit.return_value = arrived_visit
        mock_service.register_visit.return_value = registered_visit

        with (
            patch("app.api.reception.VisitService", return_value=mock_service),
            patch("app.api.reception.get_notification_service") as mock_notify,
        ):
            mock_notify.return_value = MagicMock()
            from app.api.reception import register_visit
            from app.schemas.visit import RegisterRequest

            request = RegisterRequest(
                token=arrived_visit.token,
                visitor_name="John Visitor",
                photo="base64photodata",
            )
            response = register_visit(request)

        mock_service.register_visit.assert_called_once()
        assert response.visit.status == VisitStatus.REGISTERED.value

    def test_register_rejects_nonexistent_token(self) -> None:
        """register_visit raises HTTPException 404 for unknown token."""
        mock_service = MagicMock()
        mock_service.scan_visit.return_value = None

        with patch("app.api.reception.VisitService", return_value=mock_service):
            from fastapi import HTTPException

            from app.api.reception import register_visit
            from app.schemas.visit import RegisterRequest

            request = RegisterRequest(
                token=uuid.uuid4(),
                visitor_name="John Visitor",
                photo="base64photodata",
            )
            with pytest.raises(HTTPException) as exc_info:
                register_visit(request)
            assert exc_info.value.status_code == 404

    def test_register_rejects_already_registered(self, registered_visit: Visit) -> None:
        """register_visit raises HTTPException 409 for already-registered visit."""
        mock_service = MagicMock()
        mock_service.scan_visit.return_value = registered_visit

        with patch("app.api.reception.VisitService", return_value=mock_service):
            from fastapi import HTTPException

            from app.api.reception import register_visit
            from app.schemas.visit import RegisterRequest

            request = RegisterRequest(
                token=registered_visit.token,
                visitor_name="John Visitor",
                photo="base64photodata",
            )
            with pytest.raises(HTTPException) as exc_info:
                register_visit(request)
            assert exc_info.value.status_code == 409

    def test_issue_card_requires_registration(self, arrived_visit: Visit) -> None:
        """issue_card raises HTTPException 400 when visit is not REGISTERED."""
        mock_service = MagicMock()
        mock_service.scan_visit.return_value = arrived_visit

        with patch("app.api.reception.VisitService", return_value=mock_service):
            from fastapi import HTTPException

            from app.api.reception import issue_card
            from app.schemas.visit import IssueCardRequest

            request = IssueCardRequest(
                token=arrived_visit.token,
                access_card_id="CARD-001",
            )
            with pytest.raises(HTTPException) as exc_info:
                issue_card(request)
            assert exc_info.value.status_code == 400

    def test_issue_card_updates_status_to_active(self, registered_visit: Visit) -> None:
        """issue_card transitions REGISTERED visit to ACTIVE and returns IssueCardResponse."""
        active_visit = registered_visit.model_copy(update={"status": VisitStatus.ACTIVE, "access_card_id": "CARD-001"})
        mock_service = MagicMock()
        mock_service.scan_visit.return_value = registered_visit
        mock_service.issue_card.return_value = active_visit

        with patch("app.api.reception.VisitService", return_value=mock_service):
            from app.api.reception import issue_card
            from app.schemas.visit import IssueCardRequest

            request = IssueCardRequest(
                token=registered_visit.token,
                access_card_id="CARD-001",
            )
            response = issue_card(request)

        assert response.status == "active"
        assert response.access_card_id == "CARD-001"


# ---------------------------------------------------------------------------
# TestVisitPolicyEngine — additional scan scenarios
# ---------------------------------------------------------------------------


class TestVisitPolicyEngineEdgeCases:
    """Edge case tests for VisitPolicyEngine beyond the plan's core list."""

    def test_scan_with_pin_lookup(self, sample_visit: Visit) -> None:
        """Scan policy should use PIN lookup when token is None."""
        mock_repo = MagicMock()
        mock_repo.get_visit_by_pin.return_value = sample_visit
        engine = VisitPolicyEngine(repo=mock_repo)
        result = engine.check_scan_policy(pin="123456")
        mock_repo.get_visit_by_pin.assert_called_once_with("123456")
        assert result.allowed is True  # sample_visit is within window

    def test_scan_denied_overrides_other_rules(self, sample_visit: Visit) -> None:
        """DENIED status should take precedence even if within time window."""
        mock_repo = MagicMock()
        denied = sample_visit.model_copy(update={"status": VisitStatus.DENIED})
        mock_repo.get_visit_by_token.return_value = denied
        engine = VisitPolicyEngine(repo=mock_repo)
        result = engine.check_scan_policy(token=denied.token)
        assert result.allowed is False
        assert result.reason == "host denied access"
        assert result.status_code == 403

    def test_scan_cancelled_overrides_other_rules(self, sample_visit: Visit) -> None:
        """CANCELLED status should take precedence even if within time window."""
        mock_repo = MagicMock()
        cancelled = sample_visit.model_copy(update={"status": VisitStatus.CANCELLED})
        mock_repo.get_visit_by_token.return_value = cancelled
        engine = VisitPolicyEngine(repo=mock_repo)
        result = engine.check_scan_policy(token=cancelled.token)
        assert result.allowed is False
        assert result.reason == "visit cancelled"
        assert result.status_code == 410
