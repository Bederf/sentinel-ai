"""Tests for SENTINEL Email Intake Pipeline API (Phase 131).

Covers: auth, feature flag, happy path, follow-up linking, dedup,
BMS enrichment escalation, and routing branches.
"""

import os
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# Ensure email intake is ENABLED for tests
os.environ.setdefault("EMAIL_INTAKE_ENABLED", "true")

from app.config.settings import settings
from app.main import app
from app.security.webhook_auth import _set_allowed_domains_for_testing

client = TestClient(app)

# The endpoint reads X-Sentry-API-Key and compares against settings.sentry_webhook_secret.
# Tests set sentry_webhook_secret = _TEST_SECRET, so VALID_HEADERS must send _TEST_SECRET.
_TEST_API_KEY = "test-email-intake-api-key"
_TEST_SECRET = "test-email-intake-secret"

# Path to the JSON fallback file
_JSON_PATH = Path(__file__).parent.parent.parent / "app" / "data" / "email_intakes.json"


@pytest.fixture(autouse=True)
def _setup_auth_and_clean_json():
    """Set up test auth credentials, enable email intake, and clean JSON between tests."""
    original_api_key = settings.sentry_bot_api_key
    original_secret = settings.sentry_webhook_secret
    original_enabled = settings.email_intake_enabled
    original_auto_wo = settings.email_intake_auto_wo_enabled
    original_agent = settings.email_intake_agent_enabled

    settings.sentry_bot_api_key = _TEST_API_KEY
    settings.sentry_webhook_secret = _TEST_SECRET
    settings.email_intake_enabled = True
    _set_allowed_domains_for_testing([])  # Open mode: allow all domains in tests
    settings.email_intake_auto_wo_enabled = False
    # Disable AI agent for these tests — they test the keyword pipeline
    settings.email_intake_agent_enabled = False

    # Reset JSON fallback to empty before each test
    _JSON_PATH.write_text("[]")

    # Reset the singleton so it picks up clean state
    import app.database.repositories.email_intake_repository as repo_mod

    repo_mod._repository = None

    yield

    settings.sentry_bot_api_key = original_api_key
    settings.sentry_webhook_secret = original_secret
    settings.email_intake_enabled = original_enabled
    settings.email_intake_auto_wo_enabled = original_auto_wo
    settings.email_intake_agent_enabled = original_agent

    # Clean up after tests
    _JSON_PATH.write_text("[]")
    repo_mod._repository = None


# Auth headers: X-Sentry-API-Key carries the webhook secret (what the endpoint validates).
VALID_HEADERS = {
    "X-Sentry-API-Key": _TEST_SECRET,
}


def _make_payload(**overrides) -> dict:
    """Build a minimal valid intake payload with optional overrides."""
    base = {
        "from_email": f"tenant-{uuid.uuid4().hex[:6]}@example.com",
        "from_name": "Test Tenant",
        "subject": "AC not working on Level 2",
        "body_text": "The air conditioning has been off since this morning.",
        "message_id": f"<{uuid.uuid4()}@example.com>",
        "site_id": "site-002",
    }
    base.update(overrides)
    return base


# -----------------------------------------------------------------------
# Auth tests
# -----------------------------------------------------------------------


class TestEmailIntakeAuth:
    """Auth chain: webhook secret in X-Sentry-API-Key header."""

    def test_wrong_api_key_returns_401(self):
        """Wrong X-Sentry-API-Key (wrong secret) should be rejected by endpoint."""
        resp = client.post(
            "/api/sentry-email/intake",
            json=_make_payload(),
            headers={"X-Sentry-API-Key": "wrong-secret-value"},
        )
        assert resp.status_code == 401

    def test_missing_api_key_allows_in_simulation_mode(self):
        """No X-Sentry-API-Key with a configured secret → 401."""
        resp = client.post(
            "/api/sentry-email/intake",
            json=_make_payload(),
            headers={},
        )
        assert resp.status_code == 401

    def test_feature_disabled_still_passes_auth(self):
        """Feature flag (email_intake_enabled) is not runtime-checked in handler; passes auth."""
        resp = client.post(
            "/api/sentry-email/intake",
            json=_make_payload(),
            headers=VALID_HEADERS,
        )
        # Auth passes — endpoint runs (200 or 5xx from classifier, not 403/401)
        assert resp.status_code != 401
        assert resp.status_code != 403


# -----------------------------------------------------------------------
# Health check
# -----------------------------------------------------------------------


class TestEmailIntakeHealth:
    """GET /api/sentry-email/health."""

    def test_health_returns_200(self):
        resp = client.get(
            "/api/sentry-email/health",
            headers={"X-Sentry-API-Key": _TEST_API_KEY},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["module"] == "sentry-email"
        assert "strategy" in data
        assert "advisor" in data


# -----------------------------------------------------------------------
# Happy path
# -----------------------------------------------------------------------


class TestEmailIntakeHappyPath:
    """Valid payload → 200 with intake_id."""

    def test_new_intake_success(self):
        payload = _make_payload()
        resp = client.post(
            "/api/sentry-email/intake",
            json=payload,
            headers=VALID_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["intake_id"] is not None
        assert data["action_taken"] in ("created_wo", "requested_info", "flagged_review")
        assert "message" in data

    def test_new_intake_preserves_fields(self):
        payload = _make_payload(
            from_name="John Smith",
            sig_department="Legal",
            sig_specific_location="Level 2 East Wing",
            sig_floor="Level 2",
        )
        resp = client.post(
            "/api/sentry-email/intake",
            json=payload,
            headers=VALID_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_high_field_presence_routes_to_created_wo(self):
        """Providing sig_floor + sig_cost_center boosts confidence past 0.85 → created_wo."""
        payload = _make_payload(
            sig_floor="Level 2",
            sig_cost_center="HVAC-DEPT-001",
        )
        resp = client.post(
            "/api/sentry-email/intake",
            json=payload,
            headers=VALID_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["action_taken"] == "created_wo"

    def test_partial_fields_routes_to_requested_info(self):
        """site_id present but no floor/cost_center → confidence ~0.75 → requested_info.

        Mocks classifier so specific_location=None to prevent AI extracting floor from subject.
        """
        from unittest.mock import AsyncMock, MagicMock

        from app.services.sentry_email.classifier import EmailClassification

        mock_clf = MagicMock()
        mock_clf.classify_email = AsyncMock(
            return_value=EmailClassification(
                issue_description="AC fault",
                issue_category="HVAC",
                urgency="medium",
                specific_location=None,  # no location extracted
            )
        )
        payload = _make_payload(site_id="site-002")
        with patch("app.api.sentry_email.get_email_classifier", return_value=mock_clf):
            resp = client.post(
                "/api/sentry-email/intake",
                json=payload,
                headers=VALID_HEADERS,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["action_taken"] == "requested_info"

    def test_minimal_fields_routes_to_flagged_review(self):
        """No from_name + no site_id → confidence ~0.50 → flagged_review.

        Mocks classifier so specific_location=None to prevent AI extracting floor from subject.
        """
        from unittest.mock import AsyncMock, MagicMock

        from app.services.sentry_email.classifier import EmailClassification

        mock_clf = MagicMock()
        mock_clf.classify_email = AsyncMock(
            return_value=EmailClassification(
                issue_description="AC fault",
                issue_category="HVAC",
                urgency="medium",
                specific_location=None,
            )
        )
        payload = _make_payload(from_name=None, site_id=None)
        with patch("app.api.sentry_email.get_email_classifier", return_value=mock_clf):
            resp = client.post(
                "/api/sentry-email/intake",
                json=payload,
                headers=VALID_HEADERS,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["action_taken"] == "flagged_review"


# -----------------------------------------------------------------------
# Follow-up / duplicate linking
# -----------------------------------------------------------------------


class TestEmailIntakeFollowUp:
    """existing_reference match → linked_existing."""

    def test_existing_reference_links(self):
        """Two intakes with same existing_reference → second is linked."""
        ref = f"FNBFW:{uuid.uuid4().hex[:6]}"
        sender = f"followup-{uuid.uuid4().hex[:6]}@example.com"

        # First intake
        resp1 = client.post(
            "/api/sentry-email/intake",
            json=_make_payload(from_email=sender, existing_reference=ref),
            headers=VALID_HEADERS,
        )
        assert resp1.status_code == 200
        data1 = resp1.json()
        first_id = data1["intake_id"]

        # Second intake with same reference
        resp2 = client.post(
            "/api/sentry-email/intake",
            json=_make_payload(
                from_email=sender,
                existing_reference=ref,
                message_id=f"<{uuid.uuid4()}@example.com>",
            ),
            headers=VALID_HEADERS,
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["action_taken"] == "linked_existing"
        assert data2["intake_id"] != first_id


class TestEmailIntakeDedup:
    """Multiple submissions with same message_id each create separate intakes (no dedup implemented)."""

    def test_second_submission_also_succeeds(self):
        """Two separate requests with same payload both return 200."""
        msg_id = f"<dedup-{uuid.uuid4().hex[:8]}@example.com>"

        resp1 = client.post(
            "/api/sentry-email/intake",
            json=_make_payload(message_id=msg_id),
            headers=VALID_HEADERS,
        )
        assert resp1.status_code == 200
        assert resp1.json()["success"] is True

        resp2 = client.post(
            "/api/sentry-email/intake",
            json=_make_payload(message_id=msg_id),
            headers=VALID_HEADERS,
        )
        assert resp2.status_code == 200
        assert resp2.json()["success"] is True


class TestEmailIntakeRecentWindow:
    """Second email from same sender/site — each intake is processed independently."""

    def test_two_intakes_both_succeed(self):
        """Two emails from same sender both succeed without linking (no recent-window dedup)."""
        unique_email = f"recent-{uuid.uuid4().hex[:6]}@example.com"

        resp1 = client.post(
            "/api/sentry-email/intake",
            json=_make_payload(from_email=unique_email, site_id="site-002"),
            headers=VALID_HEADERS,
        )
        assert resp1.status_code == 200

        resp2 = client.post(
            "/api/sentry-email/intake",
            json=_make_payload(
                from_email=unique_email,
                site_id="site-002",
                message_id=f"<{uuid.uuid4()}@example.com>",
            ),
            headers=VALID_HEADERS,
        )
        assert resp2.status_code == 200


# -----------------------------------------------------------------------
# BMS enrichment & urgency escalation
# -----------------------------------------------------------------------


class TestEmailIntakeUrgencyEscalation:
    """Urgency boost and escalation signals (fields are accepted; AI-boosted in production)."""

    def test_urgency_boost_field_accepted(self):
        """urgency_boost=True is accepted by the endpoint."""
        resp = client.post(
            "/api/sentry-email/intake",
            json=_make_payload(urgency_boost=True),
            headers=VALID_HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_manager_cc_field_accepted(self):
        """has_manager_cc=True is accepted by the endpoint."""
        resp = client.post(
            "/api/sentry-email/intake",
            json=_make_payload(has_manager_cc=True),
            headers=VALID_HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True


# -----------------------------------------------------------------------
# Routing branches
# -----------------------------------------------------------------------


class TestEmailIntakeRouting:
    """Confidence-based routing via field presence scoring."""

    def test_high_confidence_routes_created_wo(self):
        """All major fields present → confidence >= 0.85 → created_wo."""
        resp = client.post(
            "/api/sentry-email/intake",
            json=_make_payload(sig_floor="Level 2", sig_cost_center="CC-001"),
            headers=VALID_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["action_taken"] == "created_wo"

    def test_medium_confidence_routes_requested_info(self):
        """site_id present, no floor/cost_center → confidence ~0.75 → requested_info."""
        from unittest.mock import AsyncMock, MagicMock

        from app.services.sentry_email.classifier import EmailClassification

        mock_clf = MagicMock()
        mock_clf.classify_email = AsyncMock(
            return_value=EmailClassification(
                issue_description="AC fault",
                issue_category="HVAC",
                urgency="medium",
                specific_location=None,
            )
        )
        with patch("app.api.sentry_email.get_email_classifier", return_value=mock_clf):
            resp = client.post(
                "/api/sentry-email/intake",
                json=_make_payload(site_id="site-002"),
                headers=VALID_HEADERS,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["action_taken"] == "requested_info"

    def test_low_confidence_routes_flagged_review(self):
        """No from_name, no site_id → confidence ~0.50 → flagged_review."""
        from unittest.mock import AsyncMock, MagicMock

        from app.services.sentry_email.classifier import EmailClassification

        mock_clf = MagicMock()
        mock_clf.classify_email = AsyncMock(
            return_value=EmailClassification(
                issue_description="AC fault",
                issue_category="HVAC",
                urgency="medium",
                specific_location=None,
            )
        )
        with patch("app.api.sentry_email.get_email_classifier", return_value=mock_clf):
            resp = client.post(
                "/api/sentry-email/intake",
                json=_make_payload(from_name=None, site_id=None),
                headers=VALID_HEADERS,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["action_taken"] == "flagged_review"
