"""
MFA Approval Service — Telegram-based admin login approval.

When an admin with MFA enabled tries to log in, this service:
1. Sends a Telegram approval request to configured admin approvers
2. Tracks pending approvals with 5-minute TTL
3. Grants token when an approver replies YES via Telegram
"""

from __future__ import annotations

import asyncio
import logging
import os
import secrets
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

from app.config.settings import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory pending approval store with TTL
# ---------------------------------------------------------------------------


@dataclass
class PendingApproval:
    email: str
    approval_token: str
    created_at: datetime
    expires_at: datetime
    status: Literal["pending", "approved", "rejected"] = "pending"
    approver_id: str | None = None
    user_info: dict = field(default_factory=dict)


class _ApprovalStore:
    """Thread-safe in-memory store for pending MFA approvals."""

    def __init__(self):
        self._lock = threading.RLock()
        self._approvals: dict[str, PendingApproval] = {}
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._cleanup_thread.start()

    def _cleanup_loop(self):
        """Background thread: evict expired entries every 60 seconds."""
        while True:
            time.sleep(60)
            self._evict_expired()

    def _evict_expired(self):
        now = datetime.utcnow()
        with self._lock:
            expired = [k for k, v in self._approvals.items() if v.expires_at <= now]
            for k in expired:
                del self._approvals[k]
                logger.debug("Evicted expired approval for %s", k)

    def set(self, email: str, approval: PendingApproval) -> str:
        with self._lock:
            self._approvals[email.lower()] = approval
        return approval.approval_token

    def get(self, email: str) -> PendingApproval | None:
        with self._lock:
            entry = self._approvals.get(email.lower())
            if entry and entry.expires_at > datetime.utcnow():
                return entry
            elif entry:
                del self._approvals[email.lower()]
            return None

    def approve(self, email: str, approver_id: str) -> bool:
        with self._lock:
            entry = self._approvals.get(email.lower())
            if not entry or entry.expires_at <= datetime.utcnow():
                return False
            if entry.status != "pending":
                return False
            entry.status = "approved"
            entry.approver_id = approver_id
        return True

    def reject(self, email: str, approver_id: str) -> bool:
        with self._lock:
            entry = self._approvals.get(email.lower())
            if not entry or entry.expires_at <= datetime.utcnow():
                return False
            if entry.status != "pending":
                return False
            entry.status = "rejected"
            entry.approver_id = approver_id
        return True

    def get_status(self, email: str) -> PendingApproval | None:
        with self._lock:
            entry = self._approvals.get(email.lower())
            if not entry:
                return None
            if entry.expires_at <= datetime.utcnow():
                del self._approvals[email.lower()]
                return None
            return entry


_approval_store = _ApprovalStore()

APPROVAL_TTL_MINUTES = 5


def _get_approver_telegram_ids() -> list[str]:
    """Comma-separated admin Telegram IDs from settings or env."""
    raw = os.environ.get("MFA_APPROVER_TELEGRAM_IDS", "") or settings.mfa_approver_telegram_ids or ""
    if not raw:
        # Fall back to Sentry alert chat ID as approver
        sentry_chat = settings.telegram_alert_chat_id or ""
        if sentry_chat:
            return [sentry_chat]
        logger.warning("MFA_APPROVER_TELEGRAM_IDS not set and no telegram_alert_chat_id configured")
        return []
    return [tid.strip() for tid in raw.split(",") if tid.strip()]


def _send_telegram_message_sync(chat_id: str, message: str) -> bool:
    """Send a Telegram message via the Sentry bot CLI (synchronous subprocess call)."""
    sentry_cli = settings.sentry_bot_cli or "sentry"
    try:
        result = subprocess.run(
            [sentry_cli, "message", "send", "--channel", "telegram", "--target", chat_id, "--message", message],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            logger.info("Telegram MFA approval sent to %s", chat_id)
            return True
        else:
            logger.warning("Telegram MFA send failed: %s", result.stderr)
            return False
    except Exception as e:
        logger.error("Telegram MFA send error: %s", e)
        return False


def _format_approval_message(email: str, full_name: str, approval_token: str, requester_ip: str) -> str:
    return (
        f"🔐 *SENTINEL BMS — Login Approval Request*\n\n"
        f"*User*: {full_name} ({email})\n"
        f"*IP*: {requester_ip}\n"
        f"*Token*: `{approval_token}`\n\n"
        f"Reply with *YES {email}* to approve, *NO {email}* to reject."
    )


def send_approval_request(
    email: str,
    user_info: dict,
    source_ip: str,
) -> tuple[bool, str]:
    """
    Send a Telegram approval request to all configured approvers.

    Returns (success, approval_token).
    """
    approver_ids = _get_approver_telegram_ids()
    if not approver_ids:
        logger.error("No MFA approver Telegram IDs configured")
        return False, ""

    approval_token = secrets.token_hex(16)
    now = datetime.utcnow()
    expires_at = now + timedelta(minutes=APPROVAL_TTL_MINUTES)

    entry = PendingApproval(
        email=email,
        approval_token=approval_token,
        created_at=now,
        expires_at=expires_at,
        status="pending",
        user_info=user_info,
    )
    _approval_store.set(email, entry)

    full_name = user_info.get("full_name", email)
    message = _format_approval_message(email, full_name, approval_token, source_ip)

    # Send Telegram messages in thread pool to avoid blocking the async event loop
    def _sync_send_all() -> bool:
        results = [_send_telegram_message_sync(aid, message) for aid in approver_ids]
        return any(results)

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            success = loop.run_in_executor(None, _sync_send_all)
            # Don't block — fire and forget; Telegram is best-effort
        finally:
            loop.close()
    except Exception as e:
        logger.error("Failed to send MFA approval Telegram messages: %s", e)
        success = False

    return True, approval_token


def check_pending_approval(email: str) -> PendingApproval | None:
    """Check the current approval status for an email."""
    return _approval_store.get_status(email)


def grant_approval(email: str, approver_id: str) -> bool:
    """Mark an approval as granted (called when admin replies YES)."""
    return _approval_store.approve(email.lower(), approver_id)


def reject_approval(email: str, approver_id: str) -> bool:
    """Mark an approval as rejected (called when admin replies NO)."""
    return _approval_store.reject(email.lower(), approver_id)
