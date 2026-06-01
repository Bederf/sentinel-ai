from __future__ import annotations

import asyncio
import json
import logging
import time

import redis

from app.adapters.residential import SUPPORTED_PLATFORMS, build_adapter
from app.config.settings import settings
from app.database.supabase_client import get_supabase_client
from app.services.encryption_service import get_encryption_service
from app.services.residential.bridge_scheduler import add_residential_polling_job
from app.services.residential.mqtt_provisioner import get_mqtt_provisioner
from app.services.residential.wireguard_peer_manager import WireGuardPeerManager
from app.services.sentry.conversation_state import ConversationStateManager

logger = logging.getLogger(__name__)

# ── Telegram sender (home bot — never commercial) ─────────────────────────────

from app.services.residential.residential_telegram_sender import ResidentialTelegramSender  # noqa: E402

_sender = ResidentialTelegramSender()

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


# ── Telegram helpers (home bot only — never commercial) ───────────────────────


def _send(
    chat_id: int, text: str, reply_markup: dict | None = None, reply_to_message_id: int | None = None
) -> dict | None:
    """Send text via ResidentialTelegramSender. Returns result dict on success."""
    try:
        import asyncio

        result = asyncio.get_event_loop().run_until_complete(_sender.send_text(chat_id, text, reply_markup))
        return {"message_id": 0} if result else None
    except Exception as exc:
        logger.error("Telegram send failed: %s", exc)
        return None


def _delete(chat_id: int, message_id: int) -> None:
    """Fire-and-forget — never blocks the flow."""
    try:
        import asyncio

        asyncio.get_event_loop().run_until_complete(_sender.delete_message(chat_id, message_id))
    except Exception as exc:
        logger.warning("deleteMessage failed chat=%s msg=%s: %s", chat_id, message_id, exc)


def _answer_callback(callback_query_id: str) -> None:
    """Must be called FIRST on callback receipt to dismiss spinner."""
    try:
        import asyncio

        asyncio.get_event_loop().run_until_complete(_sender.answer_callback_query(callback_query_id))
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

# Home Assistant onboarding states
AWAITING_HA_PUBLIC_KEY = "awaiting_ha_public_key"
AWAITING_HA_TUNNEL_READY = "awaiting_ha_tunnel_ready"
MAPPING_HA_PV = "mapping_ha_pv"
MAPPING_HA_BATTERY = "mapping_ha_battery"
MAPPING_HA_GRID = "mapping_ha_grid"
MAPPING_HA_LOAD = "mapping_ha_load"
MAPPING_HA_GEYSER = "mapping_ha_geyser"
MAPPING_HA_EV = "mapping_ha_ev"
MAPPING_HA_COMPLETE = "mapping_ha_complete"


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
            "inline_keyboard": [
                [
                    {"text": "☀️ SOLARMAN Smart", "callback_data": "platform:solarman"},
                    {"text": "🔋 Victron VRM", "callback_data": "platform:victron"},
                ],
                [
                    {
                        {"text": "🏠 Home Assistant", "callback_data": "platform:home_assistant"},
                    }
                ],
            ]
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
        self._state.set(chat_id, state)

        if platform == "home_assistant":
            self._start_ha_onboarding(chat_id, state)
        else:
            state.step = AWAITING_EMAIL
            self._state.set(chat_id, state)
            platform_name = _platform_label(platform)
            _send(chat_id, f"Enter your {platform_name} account email:")

    def _start_ha_onboarding(self, chat_id: int, state) -> None:
        """Begin the Home Assistant WireGuard onboarding flow."""
        state.step = AWAITING_HA_PUBLIC_KEY
        state.data["entity_map"] = {}
        self._state.set(chat_id, state)
        _send(
            chat_id,
            "🏠 Home Assistant connects to SENTINEL via WireGuard VPN.\n\n"
            "Step 1: Install the WireGuard Add-on in Home Assistant\n"
            "(Settings → Add-ons → Store → search WireGuard → Install).\n\n"
            "Once installed, generate a key pair in the add-on\n"
            "and send me your Public Key:\n\n"
            "(Format: a 44-character string ending with =)",
        )

    def handle_ha_public_key(self, chat_id: int, public_key: str) -> str:
        """Handle WireGuard public key submission from HA onboarding."""
        state = self._state.get(chat_id)
        if state is None or state.step != AWAITING_HA_PUBLIC_KEY:
            return "Your session timed out. Send /connect to start again."

        public_key = public_key.strip()
        wg = WireGuardPeerManager()

        if not wg.validate_public_key(public_key):
            return (
                "That doesn't look like a valid WireGuard public key.\n\n"
                "In the HA WireGuard Add-on, tap 'Generate Keys' to create a new key pair,\n"
                "then send me the Public Key (the one shown, not the Private Key).\n\n"
                "Format: 44 characters ending with ="
            )

        site_id = state.data.get("site_id", f"res-{chat_id}")

        try:
            peer = wg.register_peer(site_id, public_key)
        except ValueError as exc:
            return f"Registration failed: {exc}"

        client_config = wg.generate_client_config(peer.assigned_ip)

        state.data["wireguard_peer_id"] = str(peer.id)
        state.data["assigned_ip"] = peer.assigned_ip
        state.data["public_key"] = public_key
        state.step = AWAITING_HA_TUNNEL_READY
        self._state.set(chat_id, state)

        return (
            "✅ Peer registered!\n\n"
            "Add this to your Home Assistant WireGuard Add-on config:\n\n"
            f"<code>{client_config}</code>\n\n"
            "Save the config and start the WireGuard Add-on,\n"
            "then send me <code>/hapeer_ready</code>\n\n"
            "(Your assigned VPN IP: <code>{}</code>)".format(peer.assigned_ip)
        )

    def handle_ha_tunnel_ready(self, chat_id: int) -> str:
        """Check WireGuard tunnel reachability after user sends /hapeer_ready."""
        state = self._state.get(chat_id)
        if state is None or state.step != AWAITING_HA_TUNNEL_READY:
            return "Your session timed out. Send /connect to start again."

        site_id = state.data.get("site_id", f"res-{chat_id}")
        wg = WireGuardPeerManager()

        # Check if peer is still pending (operator hasn't added to wg0.conf yet)
        peer = wg.get_peer(site_id)
        if peer is None:
            return "Peer not found. Send /connect to start again."
        if peer.status == "pending":
            return (
                "⏳ Tunnel not yet activated on the server side.\n\n"
                "This usually means the operator hasn't added your peer to the\n"
                "WireGuard configuration yet. Try /hapeer_ready again in a few minutes."
            )

        # Try reachability check
        reachable = wg.check_reachability(site_id)
        if not reachable:
            return (
                "🔍 Tunnel not detected.\n\n"
                "Check the WireGuard Add-on is running in Home Assistant\n"
                "and your config is correct, then try /hapeer_ready again."
            )

        # Tunnel is up — start entity mapping
        state.step = MAPPING_HA_PV
        self._state.set(chat_id, state)
        return (
            "✅ Tunnel connected!\n\n"
            "Now map your solar entities. Find entity IDs in\n"
            "Home Assistant → Developer Tools → States.\n\n"
            "Type 'skip' for any you don't have.\n\n"
            "PV Power entity ID:"
        )

    def _advance_ha_mapping(self, chat_id: int, state, field: str, entity_id: str) -> str:
        """Helper to advance through HA entity mapping steps."""
        entity_map = state.data.get("entity_map", {})

        if entity_id.strip().lower() == "skip":
            entity_map[field] = None
        else:
            entity_id = entity_id.strip()
            # Validate entity ID format (no wildcards)
            import re

            if not re.match(r"^[a-z0-9_\.]+$", entity_id) or len(entity_id) > 100:
                return f"Invalid entity ID format: '{entity_id}'\n\nUse only letters, numbers, dots, and underscores.\nMax 100 characters.\n\nTry again:"
            entity_map[field] = entity_id

        state.data["entity_map"] = entity_map
        self._state.set(chat_id, state)
        return None  # Signal: advance to next step

    def handle_ha_entity_input(self, chat_id: int, text: str) -> str:
        """Handle entity ID input during HA onboarding."""
        state = self._state.get(chat_id)
        if state is None:
            return "Your session timed out. Send /connect to start again."

        step = state.step
        mapping_steps = {
            MAPPING_HA_PV: ("pv_power_w", "Battery SOC entity ID:"),
            MAPPING_HA_BATTERY: ("battery_soc_pct", "Grid Power entity ID:"),
            MAPPING_HA_GRID: ("grid_power_w", "Load Power entity ID (or 'skip'):"),
            MAPPING_HA_LOAD: ("load_power_w", "Geyser switch entity ID (or 'skip'):"),
            MAPPING_HA_GEYSER: ("geyser_state", "EV Charger entity ID (or 'skip'):"),
        }

        if step not in mapping_steps:
            return "Session error. Send /connect to start again."

        field, next_prompt = mapping_steps[step]
        error = self._advance_ha_mapping(chat_id, state, field, text)
        if error:
            return error

        # Advance to next step
        state = self._state.get(chat_id)
        next_steps = {
            MAPPING_HA_PV: MAPPING_HA_BATTERY,
            MAPPING_HA_BATTERY: MAPPING_HA_GRID,
            MAPPING_HA_GRID: MAPPING_HA_LOAD,
            MAPPING_HA_LOAD: MAPPING_HA_GEYSER,
            MAPPING_HA_GEYSER: MAPPING_HA_EV,
        }
        state.step = next_steps.get(step, MAPPING_HA_EV)
        self._state.set(chat_id, state)

        if state.step == MAPPING_HA_EV:
            return next_prompt + "\n\n(EV Charger entity ID, or 'skip'):"

        return next_prompt

    def handle_ha_ev_input(self, chat_id: int, text: str) -> str:
        """Handle final EV charger entity input and trigger onboarding."""
        state = self._state.get(chat_id)
        if state is None or state.step != MAPPING_HA_EV:
            return "Your session timed out. Send /connect to start again."

        entity_map = state.data.get("entity_map", {})
        if text.strip().lower() != "skip":
            entity_id = text.strip()
            import re

            if not re.match(r"^[a-z0-9_\.]+$", entity_id) or len(entity_id) > 100:
                return "Invalid entity ID format.\n\nUse only letters, numbers, dots, and underscores.\nMax 100 characters.\n\nTry again:"
            entity_map["ev_charger_power_w"] = entity_id
        else:
            entity_map["ev_charger_power_w"] = None

        state.data["entity_map"] = entity_map
        state.step = MAPPING_HA_COMPLETE
        self._state.set(chat_id, state)

        # Perform the actual onboarding
        return self._complete_ha_onboarding(chat_id, state)

    def _complete_ha_onboarding(self, chat_id: int, state) -> str:
        """Write HA site to DB and start gateway subscription."""
        site_id = state.data.get("site_id", f"res-{chat_id}")
        entity_map = state.data.get("entity_map", {})
        platform = state.data.get("platform", "home_assistant")

        # Check for minimum mapping — warn but allow
        mapped_count = sum(1 for v in entity_map.values() if v)
        if mapped_count < 1:
            return (
                "⚠️ No entities mapped. At least one entity is recommended.\n\n"
                "You can re-configure by sending /connect again."
            )

        # Build site_config with entity_map
        site_config = {
            "entity_map": entity_map,
            "mqtt_broker": settings.wireguard_vps_endpoint.split(":")[0]
            if settings.wireguard_vps_endpoint
            else "localhost",
            "mqtt_port": 1883,
        }

        encrypted_config = get_encryption_service().encrypt(json.dumps(site_config))

        supabase = get_supabase_client()

        # Check for existing site (re-connect scenario)
        existing = supabase.table("residential_sites").select("eskom_area_code").eq("site_id", site_id).execute()
        has_existing_area = bool(existing.data and existing.data[0].get("eskom_area_code"))

        site_row = {
            "site_id": site_id,
            "platform": platform,
            "deployment_tier": "full_simbiot",
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
            return "Failed to save your site. Please try again later."

        # Clear state
        self._state.clear(chat_id)

        # Build mapped summary
        field_names = {
            "pv_power_w": "PV Power",
            "battery_soc_pct": "Battery SOC",
            "grid_power_w": "Grid Power",
            "load_power_w": "Load Power",
            "geyser_state": "Geyser",
            "ev_charger_power_w": "EV Charger",
        }
        lines = []
        for field, label in field_names.items():
            entity = entity_map.get(field)
            status = f"✅ {entity}" if entity else "⏭ skipped"
            lines.append(f"• {label}: {status}")

        msg = (
            "✅ Connected via Home Assistant.\n\n"
            "Mapped:\n" + "\n".join(lines) + "\n\n"
            "SENTINEL is now monitoring your system.\n"
            "Alerts will appear here when action is needed.\n\n"
        )

        if not has_existing_area:
            msg += "💡 Enable loadshedding alerts: /setarea\n"
        msg += "Disconnect: /disconnect"
        return msg

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
        return f"Enter your {platform_name} password:\n\n⚠️ Your message will be deleted immediately after I receive it."

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
            manifests = asyncio.run(
                asyncio.wait_for(
                    build_adapter(
                        platform, {"email": email, "password": password, "site_id": site_id}
                    ).discover_devices(),
                    timeout=30,
                )
            )
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
        state.data["manifests"] = [
            {
                "device_id": m.device_id,
                "device_name": m.device_name,
                "device_type": m.device_type,
                "capabilities": m.capabilities,
            }
            for m in manifests
        ]
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

        # Check if eskom_area_code already set (re-connect scenario)
        existing = supabase.table("residential_sites").select("eskom_area_code").eq("site_id", site_id).execute()
        has_existing_area = bool(existing.data and existing.data[0].get("eskom_area_code"))

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

        base_message = (
            f"✅ Connected: {plant_name}\n"
            f"[{device_count}] devices found.\n\n"
            "You'll receive alerts here when your system\n"
            "needs attention. All adjustments are made\n"
            "through your SOLARMAN app."
        )

        if not has_existing_area:
            area_prompt = (
                "\n\n"
                "💡 To enable loadshedding alerts, send:\n"
                "/setarea [your area code]\n"
                "Find your code at eskomsepush.co.za"
            )
        else:
            area_prompt = ""

        return base_message + area_prompt + "\n\nTo disconnect: /disconnect"
