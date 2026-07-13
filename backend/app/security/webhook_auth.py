"""
Webhook Authentication and Replay Protection.

Verifies incoming webhook requests from external systems:
    - WhatsApp: HMAC-SHA256 signature verification, nonce-based replay protection
    - Telegram: Secret token header verification, monotonic update_id per chat
    - Email intake: Domain allowlist, per-sender rate limit, file type allowlist

Applies to email intake (n8n), WhatsApp webhooks, Telegram webhooks,
and any future external integrations.

Phase 137-04.
"""

import hashlib
import hmac
import logging
import os
import time
from collections import defaultdict

from fastapi import HTTPException, Request, status

from app.security.constants import MAX_WEBHOOK_BODY_SIZE

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration from environment
# ---------------------------------------------------------------------------

WHATSAPP_APP_SECRET: str = os.environ.get("WHATSAPP_APP_SECRET", "")
TELEGRAM_WEBHOOK_SECRET: str = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")

# Email intake domain allowlist (comma-separated)
ALLOWED_EMAIL_DOMAINS: list[str] = [
    d.strip().lower() for d in os.environ.get("ALLOWED_EMAIL_DOMAINS", "").split(",") if d.strip()
]

# Allowed attachment file extensions for email intake
ALLOWED_ATTACHMENT_TYPES: set[str] = {".pdf", ".jpg", ".jpeg", ".png"}

# ---------------------------------------------------------------------------
# Nonce store for replay protection
#
# WhatsApp: message_id -> expiry timestamp (10-min TTL)
# Telegram: chat_id -> last seen update_id (monotonic)
# ---------------------------------------------------------------------------

_NONCE_TTL_SECONDS = 10 * 60  # 10 minutes

_whatsapp_nonces: dict[str, float] = {}  # message_id -> expiry
_telegram_update_ids: dict[int, int] = {}  # chat_id -> last update_id

# Per-sender email rate limiting: sender_email -> list of timestamps
_email_sender_timestamps: dict[str, list[float]] = defaultdict(list)
EMAIL_RATE_LIMIT_PER_HOUR = 10

# Timestamp tolerance for WhatsApp (5 minutes)
_TIMESTAMP_TOLERANCE_SECONDS = 5 * 60


# ---------------------------------------------------------------------------
# Nonce cleanup
# ---------------------------------------------------------------------------


def _cleanup_expired_nonces() -> None:
    """Remove expired nonces from the WhatsApp store."""
    now = time.time()
    expired = [k for k, exp in _whatsapp_nonces.items() if exp <= now]
    for k in expired:
        del _whatsapp_nonces[k]


# ---------------------------------------------------------------------------
# WhatsApp webhook verification
# ---------------------------------------------------------------------------


def _verify_whatsapp_signature(body: bytes, signature_header: str) -> bool:
    """Verify HMAC-SHA256 signature of WhatsApp webhook payload.

    Args:
        body: Raw request body bytes.
        signature_header: Value of X-Hub-Signature-256 header (sha256=...).

    Returns:
        True if signature is valid.
    """
    if not WHATSAPP_APP_SECRET:
        logger.warning("WHATSAPP_APP_SECRET not configured, skipping signature check")
        return True  # Graceful degradation: allow if not configured

    if not signature_header:
        return False

    # Header format: "sha256=<hex_digest>"
    if not signature_header.startswith("sha256="):
        return False

    expected_sig = signature_header[7:]

    computed = hmac.new(
        WHATSAPP_APP_SECRET.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(computed, expected_sig)


def _check_whatsapp_nonce(message_id: str) -> bool:
    """Check if a WhatsApp message_id has been seen (replay protection).

    Args:
        message_id: WhatsApp message ID.

    Returns:
        True if this is a new (not replayed) message.
    """
    if not message_id:
        return True  # No nonce to check

    _cleanup_expired_nonces()

    if message_id in _whatsapp_nonces:
        logger.warning("WhatsApp replay detected: message_id=%s", message_id)
        return False

    # Record nonce with TTL
    _whatsapp_nonces[message_id] = time.time() + _NONCE_TTL_SECONDS
    return True


async def verify_whatsapp_webhook(request: Request) -> bytes:
    """FastAPI dependency to verify WhatsApp webhook requests.

    Checks:
        1. Content-Type is application/json
        2. Body size is within MAX_WEBHOOK_BODY_SIZE
        3. X-Hub-Signature-256 header is valid (HMAC-SHA256)
        4. message_id nonce not replayed (10-min TTL)

    Args:
        request: FastAPI request object.

    Returns:
        Raw request body bytes (for downstream processing).

    Raises:
        HTTPException 400 if Content-Type wrong.
        HTTPException 403 if signature invalid.
        HTTPException 409 if replay detected.
        HTTPException 413 if body too large.
    """
    # Check Content-Type
    content_type = request.headers.get("content-type", "")
    if "application/json" not in content_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Content-Type must be application/json",
        )

    # Read body with size cap
    body = await request.body()
    if len(body) > MAX_WEBHOOK_BODY_SIZE:
        logger.warning(
            "WhatsApp webhook body too large: %d bytes (max %d)",
            len(body),
            MAX_WEBHOOK_BODY_SIZE,
        )
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Request body too large",
        )

    # Verify HMAC signature
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not _verify_whatsapp_signature(body, signature):
        logger.warning(
            "WhatsApp webhook signature verification failed: path=%s",
            request.url.path,
        )
        # Audit: WEBHOOK_SUSPICIOUS (Phase 137-09)
        try:
            from app.security.audit_events import audit_webhook_suspicious

            _source_ip = request.client.host if request.client else None
            audit_webhook_suspicious("whatsapp", "signature_verification_failed", source_ip=_source_ip)
        except Exception:
            logger.warning("Failed to audit suspicious WhatsApp webhook", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid webhook signature",
        )

    # Extract message_id for replay protection
    import json

    try:
        payload = json.loads(body)
        entry = payload.get("entry", [{}])[0]
        changes = entry.get("changes", [{}])[0]
        value = changes.get("value", {})
        messages = value.get("messages", [])
        if messages:
            message_id = messages[0].get("id", "")
            if message_id and not _check_whatsapp_nonce(message_id):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Duplicate message (replay detected)",
                )
    except (json.JSONDecodeError, IndexError, KeyError):
        pass  # Non-message webhooks (status updates etc.) don't have message_id

    return body


# ---------------------------------------------------------------------------
# Telegram webhook verification
# ---------------------------------------------------------------------------


def _verify_telegram_secret(secret_header: str) -> bool:
    """Verify X-Telegram-Bot-Api-Secret-Token header.

    Args:
        secret_header: Value of the secret token header.

    Returns:
        True if valid.
    """
    if not TELEGRAM_WEBHOOK_SECRET:
        logger.warning("TELEGRAM_WEBHOOK_SECRET not configured, skipping check")
        return True  # Graceful degradation

    if not secret_header:
        return False

    return hmac.compare_digest(secret_header, TELEGRAM_WEBHOOK_SECRET)


def _check_telegram_update_id(chat_id: int, update_id: int) -> bool:
    """Check that update_id is monotonically increasing per chat_id.

    Args:
        chat_id: Telegram chat ID.
        update_id: Telegram update ID.

    Returns:
        True if update_id is newer than the last seen for this chat.
    """
    last_seen = _telegram_update_ids.get(chat_id, -1)
    if update_id <= last_seen:
        logger.warning(
            "Telegram stale update: chat_id=%d update_id=%d last_seen=%d",
            chat_id,
            update_id,
            last_seen,
        )
        return False

    _telegram_update_ids[chat_id] = update_id
    return True


async def verify_telegram_webhook(request: Request) -> bytes:
    """FastAPI dependency to verify Telegram webhook requests.

    Checks:
        1. Body size within MAX_WEBHOOK_BODY_SIZE
        2. X-Telegram-Bot-Api-Secret-Token header matches
        3. update_id is monotonically increasing per chat_id

    Args:
        request: FastAPI request object.

    Returns:
        Raw request body bytes.

    Raises:
        HTTPException 403 if secret invalid.
        HTTPException 409 if stale update_id.
        HTTPException 413 if body too large.
    """
    # Read body with size cap
    body = await request.body()
    if len(body) > MAX_WEBHOOK_BODY_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Request body too large",
        )

    # Verify secret token
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not _verify_telegram_secret(secret):
        logger.warning("Telegram webhook secret verification failed")
        # Audit: WEBHOOK_SUSPICIOUS (Phase 137-09)
        try:
            from app.security.audit_events import audit_webhook_suspicious

            _source_ip = request.client.host if request.client else None
            audit_webhook_suspicious("telegram", "secret_verification_failed", source_ip=_source_ip)
        except Exception:
            logger.warning("Failed to audit suspicious Telegram webhook", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid webhook secret",
        )

    # Check update_id monotonicity
    import json

    try:
        payload = json.loads(body)
        update_id = payload.get("update_id")
        message = payload.get("message", {})
        chat_id = message.get("chat", {}).get("id")

        if update_id is not None and chat_id is not None and not _check_telegram_update_id(chat_id, update_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Stale update (replay detected)",
            )
    except (json.JSONDecodeError, KeyError):
        pass

    return body


# ---------------------------------------------------------------------------
# Email intake hardening helpers
# ---------------------------------------------------------------------------


def check_email_domain_allowed(sender_email: str) -> bool:
    """Check if sender's email domain is in the allowlist.

    If ALLOWED_EMAIL_DOMAINS is empty, all domains are allowed (open mode).

    Args:
        sender_email: Sender email address.

    Returns:
        True if domain is allowed.
    """
    if not ALLOWED_EMAIL_DOMAINS:
        return True  # Open mode: no domain restriction

    if not sender_email or "@" not in sender_email:
        return False

    domain = sender_email.rsplit("@", 1)[1].lower()
    return domain in ALLOWED_EMAIL_DOMAINS


def check_email_sender_rate_limit(sender_email: str) -> bool:
    """Check if sender has exceeded the per-sender rate limit.

    Args:
        sender_email: Sender email address.

    Returns:
        True if within rate limit.
    """
    now = time.time()
    cutoff = now - 3600  # 1 hour window
    key = sender_email.lower()

    # Prune old entries
    recent = [t for t in _email_sender_timestamps[key] if t > cutoff]
    _email_sender_timestamps[key] = recent

    if len(recent) >= EMAIL_RATE_LIMIT_PER_HOUR:
        logger.warning(
            "Email sender rate limit exceeded: sender=%s count=%d",
            sender_email,
            len(recent),
        )
        return False

    _email_sender_timestamps[key].append(now)
    return True


def check_attachment_type_allowed(filename: str) -> bool:
    """Check if attachment file type is in the allowlist.

    Args:
        filename: Original filename of the attachment.

    Returns:
        True if file extension is allowed.
    """
    if not filename:
        return False

    # Extract extension (case-insensitive)
    dot_idx = filename.rfind(".")
    if dot_idx == -1:
        return False

    ext = filename[dot_idx:].lower()
    return ext in ALLOWED_ATTACHMENT_TYPES


def is_known_sender(sender_email: str) -> bool:
    """Check if sender is a known/trusted email address.

    For now, known senders are those in the allowed domains.
    Unknown senders should be quarantined.

    Args:
        sender_email: Sender email address.

    Returns:
        True if sender is from a known domain.
    """
    if not ALLOWED_EMAIL_DOMAINS:
        return True  # If no allowlist, treat all as known

    return check_email_domain_allowed(sender_email)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _reset_for_testing() -> None:
    """Clear all nonce stores and rate limits. For testing only."""
    _whatsapp_nonces.clear()
    _telegram_update_ids.clear()
    _email_sender_timestamps.clear()


def _set_whatsapp_secret_for_testing(secret: str) -> None:
    """Override WhatsApp app secret for testing."""
    global WHATSAPP_APP_SECRET
    WHATSAPP_APP_SECRET = secret


def _set_telegram_secret_for_testing(secret: str) -> None:
    """Override Telegram webhook secret for testing."""
    global TELEGRAM_WEBHOOK_SECRET
    TELEGRAM_WEBHOOK_SECRET = secret


def _set_allowed_domains_for_testing(domains: list[str]) -> None:
    """Override allowed email domains for testing."""
    global ALLOWED_EMAIL_DOMAINS
    ALLOWED_EMAIL_DOMAINS = [d.lower() for d in domains]
