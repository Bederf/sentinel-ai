"""Tests for SENTINEL Email Intake Pipeline API (Phase 131).

Covers: auth, feature flag, happy path, follow-up linking, dedup,
BMS enrichment escalation, and routing branches.
"""

import os
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Ensure email intake is ENABLED for tests
os.environ.setdefault("EMAIL_INTAKE_ENABLED", "true")

from app.main import app  # noqa: E402
from app.config.settings import settings  # noqa: E402
from app.security.webhook_auth import _set_allowed_domains_for_testing  # noqa: E402

client = TestClient(app)

# Set up test credentials on the settings object (must match headers)
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


# Auth headers that pass the middleware + endpoint check
VALID_HEADERS = {
    "X-Sentry-API-Key": _TEST_API_KEY,
    "X-Sentry-Secret": _TEST_SECRET,
}


def _make_payload(**overrides) -> dict:
    """Build a minimal valid intake payload with optional overrides."""
    base = {
        "from_email": f"tenant-{uuid.uuid4().hex[:6]}@example.com",
        "from_name": "Test Tenant",
        "subject": "AC not working on Level 2",
        "body_plain": "The air conditioning has been off since this morning.",
        "message_id": f"<{uuid.uuid4()}@example.com>",
        "site_id": "site-002",
        "issue_category": "hvac",
        "issue_summary": "AC not working on Level 2",
        "urgency": "normal",
        "extraction_confidence": 0.75,
        "extraction_model": "gpt-4.1-nano",
    }
    base.update(overrides)
    return base


# -----------------------------------------------------------------------
# Auth tests
# -----------------------------------------------------------------------


class TestEmailIntakeAuth:
    """Auth chain: API key (middleware) + webhook secret (endpoint)."""

    def test_wrong_api_key_returns_401(self):
        """Wrong X-Sentry-API-Key should be rejected by middleware."""
        resp = client.post(
            "/api/sentry/email/intake",
            json=_make_payload(),
            headers={
                "X-Sentry-API-Key": "wrong-key",
                "X-Sentry-Secret": _TEST_SECRET,
            },
        )
        assert resp.status_code == 401

    def test_wrong_secret_returns_401(self):
        """Wrong X-Sentry-Secret should return 401."""
        resp = client.post(
            "/api/sentry/email/intake",
            json=_make_payload(),
            headers={
                "X-Sentry-API-Key": _TEST_API_KEY,
                "X-Sentry-Secret": "wrong-secret",
            },
        )
        assert resp.status_code == 401

    def test_feature_disabled_returns_503(self):
        """Feature flag off should return 503."""
        settings.email_intake_enabled = False
        resp = client.post(
            "/api/sentry/email/intake",
            json=_make_payload(),
            headers=VALID_HEADERS,
        )
        assert resp.status_code == 503
        assert "disabled" in resp.json()["detail"].lower()
        settings.email_intake_enabled = True


# -----------------------------------------------------------------------
# Health check
# -----------------------------------------------------------------------


class TestEmailIntakeHealth:
    """GET /api/sentry/email/health."""

    def test_health_returns_200(self):
        resp = client.get(
            "/api/sentry/email/health",
            headers={"X-Sentry-API-Key": _TEST_API_KEY},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "enabled" in data
        assert "pipeline_version" in data


# -----------------------------------------------------------------------
# Happy path
# -----------------------------------------------------------------------


class TestEmailIntakeHappyPath:
    """Valid payload → 200 with intake_id."""

    def test_new_intake_success(self):
        payload = _make_payload()
        resp = client.post(
            "/api/sentry/email/intake",
            json=payload,
            headers=VALID_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["intake_id"] is not None
        assert data["action_taken"] in ("new_intake", "auto_submit", "request_info", "manual_review")
        assert data["urgency"] in ("low", "normal", "high", "critical")
        assert data["reply_template"] is not None

    def test_new_intake_preserves_fields(self):
        payload = _make_payload(
            from_name="John Smith",
            from_department="Legal",
            zone_hint="Level 2 East Wing",
            floor_hint="Level 2",
        )
        resp = client.post(
            "/api/sentry/email/intake",
            json=payload,
            headers=VALID_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True


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
            "/api/sentry/email/intake",
            json=_make_payload(from_email=sender, existing_reference=ref),
            headers=VALID_HEADERS,
        )
        assert resp1.status_code == 200
        data1 = resp1.json()
        first_id = data1["intake_id"]

        # Second intake with same reference
        resp2 = client.post(
            "/api/sentry/email/intake",
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
    """Exact message_id dedup."""

    def test_duplicate_message_id(self):
        """Same message_id → returns existing intake without creating dup."""
        msg_id = f"<dedup-{uuid.uuid4().hex[:8]}@example.com>"

        # First
        resp1 = client.post(
            "/api/sentry/email/intake",
            json=_make_payload(message_id=msg_id),
            headers=VALID_HEADERS,
        )
        assert resp1.status_code == 200
        first_id = resp1.json()["intake_id"]

        # Second with same message_id
        resp2 = client.post(
            "/api/sentry/email/intake",
            json=_make_payload(message_id=msg_id),
            headers=VALID_HEADERS,
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["action_taken"] == "duplicate"
        assert data2["intake_id"] == first_id


class TestEmailIntakeRecentWindow:
    """Heuristic dedup: same sender + site + category within 24h."""

    def test_recent_window_links(self):
        """Second email from same sender/site/category → linked."""
        unique_email = f"recent-{uuid.uuid4().hex[:6]}@example.com"

        # Use subject that matches hvac category (default _make_payload subject
        # triggers hvac taxonomy override, so use hvac as issue_category)
        # First
        resp1 = client.post(
            "/api/sentry/email/intake",
            json=_make_payload(
                from_email=unique_email,
                site_id="site-002",
                issue_category="hvac",
            ),
            headers=VALID_HEADERS,
        )
        assert resp1.status_code == 200

        # Second from same sender, same site, same category
        resp2 = client.post(
            "/api/sentry/email/intake",
            json=_make_payload(
                from_email=unique_email,
                site_id="site-002",
                issue_category="hvac",
                message_id=f"<{uuid.uuid4()}@example.com>",
            ),
            headers=VALID_HEADERS,
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["action_taken"] == "linked_existing"


# -----------------------------------------------------------------------
# BMS enrichment & urgency escalation
# -----------------------------------------------------------------------


class TestEmailIntakeUrgencyEscalation:
    """Urgency boost and escalation signals."""

    def test_urgency_boost_escalates(self):
        """urgency_boost=True escalates normal → high."""
        resp = client.post(
            "/api/sentry/email/intake",
            json=_make_payload(
                urgency="normal",
                urgency_boost=True,
            ),
            headers=VALID_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["urgency"] in ("high", "critical")

    def test_manager_cc_escalates(self):
        """has_manager_cc=True escalates normal → high."""
        resp = client.post(
            "/api/sentry/email/intake",
            json=_make_payload(
                urgency="normal",
                has_manager_cc=True,
            ),
            headers=VALID_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["urgency"] in ("high", "critical")


# -----------------------------------------------------------------------
# Routing branches
# -----------------------------------------------------------------------


class TestEmailIntakeRouting:
    """Confidence-based routing: auto_submit / request_info / manual_review."""

    def test_high_confidence_routes_auto(self):
        """extraction_confidence >= 0.85 → auto_submit."""
        resp = client.post(
            "/api/sentry/email/intake",
            json=_make_payload(extraction_confidence=0.92),
            headers=VALID_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["action_taken"] == "auto_submit"

    def test_medium_confidence_routes_request_info(self):
        """extraction_confidence in request_info range → request_info."""
        # Base 0.50 + site_id boost (0.05) + category boost (0.05) + name (0.03)
        # + taxonomy boost (0.10) = 0.73 → request_info range [0.60, 0.85)
        resp = client.post(
            "/api/sentry/email/intake",
            json=_make_payload(
                extraction_confidence=0.50,
                site_id="site-002",
                zone_hint=None,
                issue_category="hvac",
            ),
            headers=VALID_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["action_taken"] == "request_info"

    def test_low_confidence_routes_manual(self):
        """extraction_confidence < 0.60 → manual_review."""
        resp = client.post(
            "/api/sentry/email/intake",
            json=_make_payload(
                extraction_confidence=0.30,
                site_id=None,
                zone_hint=None,
                issue_category="general",
            ),
            headers=VALID_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["action_taken"] == "manual_review"
