from __future__ import annotations

import asyncio
import json
import logging
import os
import time

import redis
import requests as http_requests

from app.adapters.residential import SUPPORTED_PLATFORMS, build_adapter
from app.config.settings import settings
from app.database.supabase_client import get_supabase_client
from app.services.encryption_service import get_encryption_service
from app.services.residential.bridge_scheduler import add_residential_polling_job
from app.services.residential.mqtt_provisioner import get_mqtt_provisioner
from app.services.sentry.conversation_state import ConversationStateManager

logger = logging.getLogger(__name__)

# ── Bot token ──────────────────────────────────────────────────────────────────

def _bot_token() -> str:
    path = os.path.expanduser("~/.sentry/gateway/sentry.json")
    with open(path) as f:
        return json.load(f)["channels"]["telegram"]["accounts"]["client"]["botToken"]


# ── Rate limiting (3 attempts / hour / chat_id) ────────────────────────────────

def _check_rate_limit(chat_id: int) -> tuple[bool, int]:
    """
    Returns (allowed, attempts_remaining).
    Uses Redis ZADD/ZCOUNT — same pattern as LoginAttemptTracker.
    """
    key = f"ratelimit:connect:{chat_id}"
    r = redis.from_url(settings.redis_url, decode_responses=True, socket_timeout=2)
    now = time.time()
    one_hour_ago = now - 3600
    r.zremrangebyscore(key, 0, one_hour_ago)  # cleanup old entries
    count = r.zcard(key)
    if count >= 3:
        oldest = r.zrange(key, 0, 0, withscores=True)
        if oldest:
            wait_secs = 3600 - (now - oldest[0][1])
            return False, max(0, int(wait_secs // 60))
        return False, 0
    return True, 3 - count


def _record_failure(chat_id: int) -> None:
    key = f"ratelimit:connect:{chat_id}"
    r = redis.from_url(settings.redis_url, decode_responses=True, socket_timeout=2)
    r.zadd(key, {str(time.time()): time.time()})
    r.expire(key, 3600)


def _reset_rate_limit(chat_id: int) -> None:
    key = f"ratelimit:connect:{chat_id}"
    r = redis.from_url(settings.redis_url, decode_responses=True, socket_timeout=2)
    r.delete(key)


# ── Telegram helpers ───────────────────────────────────────────────────────────

def _send(chat_id: int, text: str, reply_markup: dict | None = None, reply_to_message_id: int | None = None) -> dict | None:
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id
    try:
        r = http_requests.post(
            f"https://api.telegram.org/bot{_bot_token()}/sendMessage",
            json=payload,
            timeout=10,
        )
        r.raise_for_status()
        return r.json().get("result")
    except Exception as exc:
        logger.error("Telegram send failed: %s", exc)
        return None


def _delete(chat_id: int, message_id: int) -> None:
    """Fire-and-forget — never blocks the flow."""
    try:
        http_requests.post(
            f"https://api.telegram.org/bot{_bot_token()}/deleteMessage",
            json={"chat_id": chat_id, "message_id": message_id},
            timeout=5,
        )
    except Exception as exc:
        logger.warning("deleteMessage failed chat=%s msg=%s: %s", chat_id, message_id, exc)


def _answer_callback(callback_query_id: str) -> None:
    """Must be called FIRST on callback receipt to dismiss spinner."""
    try:
        http_requests.post(
            f"https://api.telegram.org/bot{_bot_token()}/answerCallbackQuery",
            json={"callback_query_id": callback_query_id},
            timeout=5,
        )
    except Exception as exc:
        logger.warning("answerCallbackQuery failed: %s", exc)


# ── Platform label ─────────────────────────────────────────────────────────────

def _platform_label(platform: str) -> str:
    return SUPPORTED_PLATFORMS.get(platform, {}).get("name", platform.title())


# ── State machine steps ─────────────────────────────────────────────────────────

AWAITING_PLATFORM = "awaiting_platform"
AWAITING_EMAIL = "awaiting_email"
AWAITING_PASSWORD = "awaiting_password"
DISCOVERING = "discovering"


# ── Service ─────────────────────────────────────────────────────────────────────

class ResidentialOnboardService:
    """
    Telegram-backed residential onboarding state machine.

    State key: conv:{chat_id}  (managed by ConversationStateManager)
    TTL: 600s — session expires mid-flow, user must re-start with /connect
    """

    def __init__(self) -> None:
        self._state = ConversationStateManager()

    def _new_state(self, flow: str, step: str, data: dict | None = None) -> ConversationStateManager.ConversationState:
        return ConversationStateManager.ConversationState(
            flow=flow,
            step=step,
            data=data or {},
            created_at="",
            updated_at="",
        )

    # ── Entry points ──────────────────────────────────────────────────────────

    def handle_connect(self, chat_id: int) -> str:
        """
        Called when user sends /connect.
        Returns the bot message text to send.
        """
        site_id = f"res-{chat_id}"

        # Check if already connected (active record in DB)
        try:
            supabase = get_supabase_client()
            existing = supabase.table("residential_sites").select("id,is_active").eq("site_id", site_id).execute()
            if existing.data and existing.data[0].get("is_active"):
                return (
                    "You're already connected to SENTINEL.\n\n"
                    "Send /disconnect first to reconnect with different credentials."
                )
        except Exception as exc:
            logger.warning("Could not check existing site for chat_id=%s: %s", chat_id, exc)

        state = self._new_state("residential_onboarding", AWAITING_PLATFORM, {"site_id": site_id})
        self._state.set(chat_id, state)

        keyboard = {
            "inline_keyboard": [[
                {"text": "☀️ SOLARMAN Smart", "callback_data": "platform:solarman"},
                {"text": "🔋 Victron VRM", "callback_data": "platform:victron"},
            ]]
        }
        _send(chat_id, "Which platform monitors your solar system?", reply_markup=keyboard)
        return "Starting /connect flow..."

    def handle_platform_callback(self, chat_id: int, callback_query_id: str, platform: str) -> None:
        """
        Called when user taps an inline keyboard platform button.
        FIRST action: dismiss spinner via answer_callback_query.
        """
        _answer_callback(callback_query_id)

        state = self._state.get(chat_id)
        if state is None or state.step != AWAITING_PLATFORM:
            _send(chat_id, "Your session timed out. Send /connect to start again.")
            return

        state.data["platform"] = platform
        state.step = AWAITING_EMAIL
        self._state.set(chat_id, state)

        platform_name = _platform_label(platform)
        _send(chat_id, f"Enter your {platform_name} account email:")

    def handle_email(self, chat_id: int, email: str) -> str:
        """
        Called when user sends email while step == awaiting_email.
        Returns the bot message text to send.
        """
        state = self._state.get(chat_id)
        if state is None or state.step != AWAITING_EMAIL:
            return "Send /connect to start the onboarding flow."

        email = email.strip()
        if "@" not in email or "." not in email:
            return "That doesn't look like an email address. Please try again."

        state.data["email"] = email
        state.step = AWAITING_PASSWORD
        self._state.set(chat_id, state)

        platform_name = _platform_label(state.data.get("platform", ""))
        return (
            f"Enter your {platform_name} password:\n\n"
            "⚠️ Your message will be deleted immediately after I receive it."
        )

    def handle_password(self, chat_id: int, message_id: int, password: str) -> str:
        """
        Called when user sends password while step == awaiting_password.
        DELETES the password message FIRST, then attempts auth.
        Returns the bot message text to send.
        """
        # Rate limit check FIRST
        allowed, wait_minutes = _check_rate_limit(chat_id)
        if not allowed:
            _delete(chat_id, message_id)
            return f"Too many failed attempts. Try again in {wait_minutes} minutes."

        state = self._state.get(chat_id)
        if state is None or state.step != AWAITING_PASSWORD:
            _delete(chat_id, message_id)
            return "Send /connect to start the onboarding flow."

        platform = state.data.get("platform", "")
        site_id = state.data.get("site_id", f"res-{chat_id}")
        email = state.data.get("email", "")

        # Delete password message IMMEDIATELY — fire-and-forget
        _delete(chat_id, message_id)

        # Build adapter
        try:
            adapter = build_adapter(platform, {"email": email, "password": password, "site_id": site_id})
        except Exception as exc:
            logger.warning("build_adapter failed for chat_id=%s: %s", chat_id, exc)
            _record_failure(chat_id)
            remaining = _check_rate_limit(chat_id)[1]
            return f"Authentication failed. Check your credentials and try again. ({remaining} attempts remaining)"

        # Authenticate (blocking — runs in APScheduler thread context)
        try:
            ok = asyncio.run(adapter.authenticate())
        except Exception as exc:
            logger.warning("authenticate failed for chat_id=%s: %s", chat_id, exc)
            _record_failure(chat_id)
            remaining = _check_rate_limit(chat_id)[1]
            return f"Authentication failed. Check your credentials and try again. ({remaining} attempts remaining)"

        if not ok:
            _record_failure(chat_id)
            remaining = _check_rate_limit(chat_id)[1]
            return f"Authentication failed. Check your credentials and try again. ({remaining} attempts remaining)"

        # Auth succeeded — reset rate limit
        _reset_rate_limit(chat_id)

        # Discover devices while we still have the credentials in memory
        try:
            manifests = asyncio.run(asyncio.wait_for(
                build_adapter(platform, {"email": email, "password": password, "site_id": site_id}).discover_devices(),
                timeout=30,
            ))
        except Exception as exc:
            logger.warning("device discovery failed for chat_id=%s: %s", chat_id, exc)
            return "Could not discover your devices. Please try again later."

        # Encrypt site_config BEFORE it enters Redis — password never in plaintext in Redis
        site_config = {"email": email, "password": password, "site_id": site_id, "chat_id": chat_id}
        encrypted_config = get_encryption_service().encrypt(json.dumps(site_config))

        # Password is still in memory here — advance state immediately so next call
        # does DB write and then password variable goes out of scope
        state.data.pop("password", None)  # never persist
        state.data["email"] = email
        state.data["site_id"] = site_id
        state.data["chat_id"] = chat_id
        state.data["encrypted_site_config"] = encrypted_config
        state.data["manifests"] = [{"device_id": m.device_id, "device_name": m.device_name,
                                     "device_type": m.device_type, "capabilities": m.capabilities} for m in manifests]
        state.step = DISCOVERING
        self._state.set(chat_id, state)

        # password variable now goes out of scope — cannot be recovered from state

        return "🔍 Discovering your installation..."

    def handle_discover_and_onboard(self, chat_id: int) -> str:
        """
        Called after handle_password advances to DISCOVERING step.
        All sensitive data (email/password) was passed directly from handle_password
        and is now stored ONLY as encrypted_site_config in Redis state.
        This method performs DB write + MQTT provisioning + state clear.
        """
        state = self._state.get(chat_id)
        if state is None or state.step != DISCOVERING:
            return "Session expired. Send /connect to start again."

        platform = state.data.get("platform", "")
        site_id = state.data.get("site_id", f"res-{chat_id}")
        email = state.data.get("email", "")
        encrypted_config = state.data.get("encrypted_site_config", "{}")
        manifest_dicts: list[dict] = state.data.get("manifests", [])

        supabase = get_supabase_client()

        site_row = {
            "site_id": site_id,
            "platform": platform,
            "deployment_tier": "cloud_only",
            "site_config": encrypted_config,
            "eskom_area_code": None,
            "tariff_type": None,
            "polling_interval_seconds": 300,
            "is_active": True,
            "chat_id": chat_id,
            "notification_channel": "telegram",
            "onboarding_method": "telegram_bot",
        }

        result = supabase.table("residential_sites").upsert(site_row, on_conflict="site_id").execute()
        if not result.data:
            return "Failed to save your site. Please contact support."

        residential_site_id = result.data[0]["id"]

        # Save devices (manifest_dicts are already plain dicts from state)
        device_rows = [
            {
                "residential_site_id": residential_site_id,
                **m,
            }
            for m in manifest_dicts
        ]
        if device_rows:
            supabase.table("residential_devices").insert(device_rows).execute()

        # Provision MQTT ACL
        try:
            get_mqtt_provisioner().provision_site(site_id)
        except Exception as exc:
            logger.warning("MQTT ACL provisioning failed for %s: %s", site_id, exc)

        # Schedule polling — use email from state, adapter reads password from site_config at poll time
        try:
            polling_config = {"email": email, "password": "", "site_id": site_id}
            adapter = build_adapter(platform, polling_config)
            add_residential_polling_job(site_id=site_id, adapter=adapter, interval_seconds=300)
        except Exception as exc:
            logger.warning("Failed to schedule residential polling for %s: %s", site_id, exc)

        # Clear state — onboarding complete. Email remains, encrypted config removed.
        self._state.clear(chat_id)

        device_count = len(manifest_dicts)
        plant_name = manifest_dicts[0].get("device_name", "your system") if manifest_dicts else "your system"

        return (
            f"✅ Connected: {plant_name}\n"
            f"[{device_count}] devices found.\n\n"
            "You'll receive alerts here when your system needs attention.\n"
            "SENTINEL monitors your system and sends advice via Telegram.\n\n"
            "To enable loadshedding alerts, send your Eskom area code.\n"
            "Find it at eskomsepush.co.za\n\n"
            "To disconnect at any time: /disconnect"
        )
