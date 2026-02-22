"""Shared Sentry integration configuration helpers."""

from __future__ import annotations

import hmac
from typing import Optional

from app.config.settings import settings


def get_sentry_bot_cli() -> str:
    """Resolve sentry bot CLI command with safe fallback."""
    cli = (settings.sentry_bot_cli or "").strip()
    return cli or "sentrybot"


def get_sentry_webhook_secret() -> str:
    """Return configured Sentry webhook secret (may be empty)."""
    return (settings.sentry_webhook_secret or "").strip()


def is_sentry_secret_valid(provided_secret: Optional[str]) -> bool:
    """Validate a provided secret against configured Sentry secret."""
    configured_secret = get_sentry_webhook_secret()
    if not configured_secret or not provided_secret:
        return False
    return hmac.compare_digest(provided_secret, configured_secret)
