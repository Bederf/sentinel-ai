"""Tests for webhook authentication — Phase 137-04.

Tests:
    - WhatsApp HMAC signature verification
    - WhatsApp replay protection (nonce)
    - Telegram secret token verification
    - Telegram monotonic update_id
    - Email domain allowlist
    - Email sender rate limiting
    - Attachment file type allowlist
    - Unknown sender quarantine
"""

import hashlib
import hmac
import json
from unittest.mock import AsyncMock

import pytest

from app.security.webhook_auth import (
    EMAIL_RATE_LIMIT_PER_HOUR,
    _check_telegram_update_id,
    _check_whatsapp_nonce,
    _reset_for_testing,
    _set_allowed_domains_for_testing,
    _set_telegram_secret_for_testing,
    _set_whatsapp_secret_for_testing,
    _verify_telegram_secret,
    _verify_whatsapp_signature,
    check_attachment_type_allowed,
    check_email_domain_allowed,
    check_email_sender_rate_limit,
    is_known_sender,
    verify_telegram_webhook,
    verify_whatsapp_webhook,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_TEST_WHATSAPP_SECRET = "test-whatsapp-secret-key"
_TEST_TELEGRAM_SECRET = "test-telegram-secret-token"


@pytest.fixture(autouse=True)
def clean_state():
    """Reset all nonce stores and secrets before each test."""
    _reset_for_testing()
    _set_whatsapp_secret_for_testing(_TEST_WHATSAPP_SECRET)
    _set_telegram_secret_for_testing(_TEST_TELEGRAM_SECRET)
    _set_allowed_domains_for_testing([])  # Open mode by default
    yield
    _reset_for_testing()
    _set_whatsapp_secret_for_testing("")
    _set_telegram_secret_for_testing("")
    _set_allowed_domains_for_testing([])


def _compute_whatsapp_signature(body: bytes, secret: str) -> str:
    """Compute X-Hub-Signature-256 header value."""
    sig = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={sig}"


# ---------------------------------------------------------------------------
# WhatsApp signature verification
# ---------------------------------------------------------------------------


class TestWhatsAppSignature:
    """Tests for WhatsApp HMAC-SHA256 signature verification."""

    def test_whatsapp_valid_signature_accepted(self):
        """Valid HMAC signature passes."""
        body = b'{"entry":[{"changes":[{"value":{"messages":[]}}]}]}'
        sig = _compute_whatsapp_signature(body, _TEST_WHATSAPP_SECRET)
        assert _verify_whatsapp_signature(body, sig) is True

    def test_whatsapp_invalid_signature_rejected(self):
        """Invalid HMAC signature fails."""
        body = b'{"entry":[{"changes":[{"value":{"messages":[]}}]}]}'
        assert _verify_whatsapp_signature(body, "sha256=invalid") is False

    def test_whatsapp_missing_signature_rejected(self):
        """Missing signature header fails."""
        body = b'{"test": true}'
        assert _verify_whatsapp_signature(body, "") is False

    def test_whatsapp_wrong_prefix_rejected(self):
        """Signature without sha256= prefix fails."""
        body = b'{"test": true}'
        sig = hmac.new(
            _TEST_WHATSAPP_SECRET.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()
        assert _verify_whatsapp_signature(body, sig) is False

    def test_whatsapp_tampered_body_rejected(self):
        """Signature of different body fails."""
        original = b'{"original": true}'
        tampered = b'{"tampered": true}'
        sig = _compute_whatsapp_signature(original, _TEST_WHATSAPP_SECRET)
        assert _verify_whatsapp_signature(tampered, sig) is False


# ---------------------------------------------------------------------------
# WhatsApp replay protection
# ---------------------------------------------------------------------------


class TestWhatsAppReplay:
    """Tests for WhatsApp nonce-based replay protection."""

    def test_whatsapp_first_message_accepted(self):
        """First occurrence of a message_id passes."""
        assert _check_whatsapp_nonce("msg-001") is True

    def test_whatsapp_replay_rejected(self):
        """Second occurrence of the same message_id is rejected."""
        assert _check_whatsapp_nonce("msg-002") is True
        assert _check_whatsapp_nonce("msg-002") is False

    def test_whatsapp_different_messages_accepted(self):
        """Different message_ids pass independently."""
        assert _check_whatsapp_nonce("msg-a") is True
        assert _check_whatsapp_nonce("msg-b") is True

    def test_whatsapp_empty_nonce_passes(self):
        """Empty/None message_id is not checked."""
        assert _check_whatsapp_nonce("") is True


# ---------------------------------------------------------------------------
# WhatsApp webhook dependency
# ---------------------------------------------------------------------------


class TestWhatsAppWebhookDependency:
    """Tests for the full verify_whatsapp_webhook dependency."""

    @pytest.mark.asyncio
    async def test_whatsapp_webhook_valid_request(self):
        """Valid signed request passes the dependency."""
        payload = {"entry": [{"changes": [{"value": {"messages": []}}]}]}
        body = json.dumps(payload).encode()
        sig = _compute_whatsapp_signature(body, _TEST_WHATSAPP_SECRET)

        mock_request = AsyncMock()
        mock_request.headers = {
            "content-type": "application/json",
            "X-Hub-Signature-256": sig,
        }
        mock_request.body = AsyncMock(return_value=body)
        mock_request.url.path = "/api/whatsapp/webhooks"

        result = await verify_whatsapp_webhook(mock_request)
        assert result == body

    @pytest.mark.asyncio
    async def test_whatsapp_webhook_wrong_content_type(self):
        """Non-JSON content type is rejected."""
        mock_request = AsyncMock()
        mock_request.headers = {"content-type": "text/plain"}

        with pytest.raises(Exception) as exc_info:
            await verify_whatsapp_webhook(mock_request)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_whatsapp_webhook_body_too_large(self):
        """Oversized body is rejected."""
        mock_request = AsyncMock()
        mock_request.headers = {"content-type": "application/json"}
        mock_request.body = AsyncMock(return_value=b"x" * (1024 * 1024 + 1))

        with pytest.raises(Exception) as exc_info:
            await verify_whatsapp_webhook(mock_request)
        assert exc_info.value.status_code == 413

    @pytest.mark.asyncio
    async def test_whatsapp_webhook_invalid_sig_rejected(self):
        """Invalid signature fails the dependency."""
        body = b'{"test": true}'

        mock_request = AsyncMock()
        mock_request.headers = {
            "content-type": "application/json",
            "X-Hub-Signature-256": "sha256=invalid",
        }
        mock_request.body = AsyncMock(return_value=body)
        mock_request.url.path = "/api/whatsapp/webhooks"

        with pytest.raises(Exception) as exc_info:
            await verify_whatsapp_webhook(mock_request)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_whatsapp_webhook_replay_rejected(self):
        """Replayed message_id is rejected with 409."""
        payload = {
            "entry": [{"changes": [{"value": {"messages": [{"id": "replay-msg-001", "from": "123", "type": "text"}]}}]}]
        }
        body = json.dumps(payload).encode()
        sig = _compute_whatsapp_signature(body, _TEST_WHATSAPP_SECRET)

        mock_request = AsyncMock()
        mock_request.headers = {
            "content-type": "application/json",
            "X-Hub-Signature-256": sig,
        }
        mock_request.body = AsyncMock(return_value=body)
        mock_request.url.path = "/api/whatsapp/webhooks"

        # First call should succeed
        result = await verify_whatsapp_webhook(mock_request)
        assert result == body

        # Second call with same message_id should fail
        mock_request2 = AsyncMock()
        mock_request2.headers = {
            "content-type": "application/json",
            "X-Hub-Signature-256": sig,
        }
        mock_request2.body = AsyncMock(return_value=body)
        mock_request2.url.path = "/api/whatsapp/webhooks"

        with pytest.raises(Exception) as exc_info:
            await verify_whatsapp_webhook(mock_request2)
        assert exc_info.value.status_code == 409


# ---------------------------------------------------------------------------
# Telegram verification
# ---------------------------------------------------------------------------


class TestTelegramVerification:
    """Tests for Telegram webhook verification."""

    def test_telegram_valid_secret_accepted(self):
        """Valid secret token passes."""
        assert _verify_telegram_secret(_TEST_TELEGRAM_SECRET) is True

    def test_telegram_invalid_secret_rejected(self):
        """Invalid secret token fails."""
        assert _verify_telegram_secret("wrong-secret") is False

    def test_telegram_empty_secret_rejected(self):
        """Empty secret token fails."""
        assert _verify_telegram_secret("") is False

    def test_telegram_stale_update_rejected(self):
        """Lower update_id than previously seen is rejected."""
        assert _check_telegram_update_id(chat_id=100, update_id=5) is True
        assert _check_telegram_update_id(chat_id=100, update_id=3) is False  # stale
        assert _check_telegram_update_id(chat_id=100, update_id=5) is False  # equal

    def test_telegram_monotonic_update_accepted(self):
        """Increasing update_ids pass."""
        assert _check_telegram_update_id(chat_id=200, update_id=1) is True
        assert _check_telegram_update_id(chat_id=200, update_id=2) is True
        assert _check_telegram_update_id(chat_id=200, update_id=3) is True

    def test_telegram_per_chat_tracking(self):
        """update_id tracking is per-chat, not global."""
        assert _check_telegram_update_id(chat_id=300, update_id=10) is True
        assert _check_telegram_update_id(chat_id=301, update_id=5) is True  # different chat
        assert _check_telegram_update_id(chat_id=300, update_id=11) is True


# ---------------------------------------------------------------------------
# Telegram webhook dependency
# ---------------------------------------------------------------------------


class TestTelegramWebhookDependency:
    """Tests for the verify_telegram_webhook dependency."""

    @pytest.mark.asyncio
    async def test_telegram_webhook_valid(self):
        """Valid Telegram webhook passes."""
        payload = {"update_id": 1, "message": {"chat": {"id": 42}, "text": "hello"}}
        body = json.dumps(payload).encode()

        mock_request = AsyncMock()
        mock_request.headers = {
            "X-Telegram-Bot-Api-Secret-Token": _TEST_TELEGRAM_SECRET,
        }
        mock_request.body = AsyncMock(return_value=body)

        result = await verify_telegram_webhook(mock_request)
        assert result == body

    @pytest.mark.asyncio
    async def test_telegram_webhook_invalid_secret(self):
        """Invalid Telegram secret is rejected."""
        body = b'{"update_id": 1}'

        mock_request = AsyncMock()
        mock_request.headers = {
            "X-Telegram-Bot-Api-Secret-Token": "wrong",
        }
        mock_request.body = AsyncMock(return_value=body)

        with pytest.raises(Exception) as exc_info:
            await verify_telegram_webhook(mock_request)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_telegram_webhook_stale_update(self):
        """Stale update_id is rejected with 409."""
        payload1 = {"update_id": 10, "message": {"chat": {"id": 42}}}
        body1 = json.dumps(payload1).encode()

        mock_request1 = AsyncMock()
        mock_request1.headers = {
            "X-Telegram-Bot-Api-Secret-Token": _TEST_TELEGRAM_SECRET,
        }
        mock_request1.body = AsyncMock(return_value=body1)

        await verify_telegram_webhook(mock_request1)

        # Now send stale update
        payload2 = {"update_id": 5, "message": {"chat": {"id": 42}}}
        body2 = json.dumps(payload2).encode()

        mock_request2 = AsyncMock()
        mock_request2.headers = {
            "X-Telegram-Bot-Api-Secret-Token": _TEST_TELEGRAM_SECRET,
        }
        mock_request2.body = AsyncMock(return_value=body2)

        with pytest.raises(Exception) as exc_info:
            await verify_telegram_webhook(mock_request2)
        assert exc_info.value.status_code == 409


# ---------------------------------------------------------------------------
# Email intake hardening
# ---------------------------------------------------------------------------


class TestEmailDomainAllowlist:
    """Tests for email domain allowlist."""

    def test_open_mode_allows_all(self):
        """With empty allowlist, all domains pass."""
        _set_allowed_domains_for_testing([])
        assert check_email_domain_allowed("user@random.com") is True

    def test_allowed_domain_passes(self):
        """Email from allowed domain passes."""
        _set_allowed_domains_for_testing(["example.com", "company.co.za"])
        assert check_email_domain_allowed("user@example.com") is True
        assert check_email_domain_allowed("admin@company.co.za") is True

    def test_disallowed_domain_blocked(self):
        """Email from non-allowed domain is blocked."""
        _set_allowed_domains_for_testing(["example.com"])
        assert check_email_domain_allowed("user@attacker.com") is False

    def test_invalid_email_blocked(self):
        """Invalid email addresses are blocked."""
        _set_allowed_domains_for_testing(["example.com"])
        assert check_email_domain_allowed("") is False
        assert check_email_domain_allowed("no-at-sign") is False

    def test_case_insensitive(self):
        """Domain check is case-insensitive."""
        _set_allowed_domains_for_testing(["Example.COM"])
        assert check_email_domain_allowed("user@example.com") is True


class TestEmailSenderRateLimit:
    """Tests for per-sender email rate limiting."""

    def test_within_limit_passes(self):
        """Emails within rate limit pass."""
        for i in range(EMAIL_RATE_LIMIT_PER_HOUR):
            assert check_email_sender_rate_limit(f"user{i}@test.com") is True

    def test_exceeds_limit_blocked(self):
        """Emails exceeding rate limit are blocked."""
        sender = "spammer@test.com"
        for _ in range(EMAIL_RATE_LIMIT_PER_HOUR):
            assert check_email_sender_rate_limit(sender) is True
        assert check_email_sender_rate_limit(sender) is False

    def test_different_senders_independent(self):
        """Rate limits are per-sender, not global."""
        for _ in range(EMAIL_RATE_LIMIT_PER_HOUR):
            check_email_sender_rate_limit("sender-a@test.com")
        # sender-a is now rate-limited
        assert check_email_sender_rate_limit("sender-a@test.com") is False
        # sender-b is not
        assert check_email_sender_rate_limit("sender-b@test.com") is True


class TestAttachmentTypeAllowlist:
    """Tests for attachment file type allowlist."""

    def test_allowed_types(self):
        """Allowed file extensions pass."""
        assert check_attachment_type_allowed("report.pdf") is True
        assert check_attachment_type_allowed("photo.jpg") is True
        assert check_attachment_type_allowed("image.jpeg") is True
        assert check_attachment_type_allowed("screenshot.png") is True

    def test_blocked_types(self):
        """Disallowed file extensions fail."""
        assert check_attachment_type_allowed("script.exe") is False
        assert check_attachment_type_allowed("document.docx") is False
        assert check_attachment_type_allowed("archive.zip") is False
        assert check_attachment_type_allowed("macro.xlsm") is False

    def test_case_insensitive(self):
        """Extension check is case-insensitive."""
        assert check_attachment_type_allowed("PHOTO.JPG") is True
        assert check_attachment_type_allowed("Report.PDF") is True

    def test_no_extension_blocked(self):
        """Files without extensions are blocked."""
        assert check_attachment_type_allowed("noext") is False
        assert check_attachment_type_allowed("") is False


class TestUnknownSenderQuarantine:
    """Tests for unknown sender quarantine."""

    def test_email_unknown_sender_quarantined(self):
        """Unknown sender (domain not in allowlist) is flagged for quarantine."""
        _set_allowed_domains_for_testing(["trusted.com"])
        assert is_known_sender("user@trusted.com") is True
        assert is_known_sender("user@unknown.com") is False

    def test_open_mode_all_known(self):
        """With empty allowlist, all senders are treated as known."""
        _set_allowed_domains_for_testing([])
        assert is_known_sender("anyone@anywhere.com") is True
