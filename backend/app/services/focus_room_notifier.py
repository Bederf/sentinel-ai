"""Focus room overstay notifier.

Sends operator alerts when a focus room exceeds the allowed occupancy window.
WhatsApp via OpenClaw gateway message send.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from app.config.settings import settings

logger = logging.getLogger(__name__)

# In-memory mapping of WhatsApp message IDs to focus room codes
# Populated when alerts are sent, used to match swipe-replies
_focus_alert_messages: dict[str, str] = {}


def _resolve_site_label(site_id: str) -> str:
    """Return human-readable site/building label for alerts."""
    try:
        from app.core.site_resolver import get_registered_sites

        for site in get_registered_sites():
            if site.get("code") == site_id:
                return site.get("name") or site_id
    except Exception:
        pass
    return site_id


async def send_focus_overstay_alert(
    *,
    site_id: str,
    room_code: str,
    max_allowed_minutes: int,
    cooldown_minutes: int,
) -> dict:
    """Dispatch a focus overstay alert via WhatsApp to concierge."""
    # Check if focus room notifications are enabled
    try:
        from app.api.space_settings import _load_space_settings
        space_settings = _load_space_settings()
        if not space_settings.get("focus_room_notifications_enabled", True):
            logger.info("Focus room alerts disabled by space_settings toggle — skipping")
            return {"success": False, "skipped": True}
    except Exception:
        pass

    site_label = _resolve_site_label(site_id)

    try:
        whatsapp_ok = False
        whatsapp_result: dict = {}
        try:
            from app.services.space_booking_simulator import get_block_booking_config
            from app.services.concierge_store import find_all_concierges_for_room

            config = get_block_booking_config(site_id)
            concierges = find_all_concierges_for_room(site_id, room_code.split("-")[0] if "-" in room_code else site_id)
            whatsapp_targets = []
            if concierges:
                for c in concierges:
                    if c.mobile and c.mobile.strip():
                        num = c.mobile.strip()
                        if not num.startswith("+"):
                            num = "+27" + num.lstrip("0")
                        whatsapp_targets.append(num)
            if not whatsapp_targets and config and config.concierge_whatsapp:
                whatsapp_targets.append(config.concierge_whatsapp.replace("whatsapp:", ""))
            if whatsapp_targets:
                import subprocess

                body = (
                    f"⚠️ Focus Room Overstay Alert\n"
                    f"Site: {site_label}\n"
                    f"Room: {room_code}\n"
                    f"Occupancy exceeded {max_allowed_minutes} min.\n\n"
                    f"Is the room currently occupied?\n"
                    f"Reply YES to confirm — session will continue.\n"
                    f"Reply NO to end the session and release the room."
                )
                sent_any = False
                import shutil
                cli = shutil.which("openclaw") or "/home/bederf/.local/bin/openclaw"
                for target in whatsapp_targets:
                    try:
                        env = os.environ.copy()
                        env["SENTRY_CONFIG_DIR"] = "/home/bederf/.sentry/gateway"
                        result = subprocess.run(
                            [cli, "message", "send", "--channel", "whatsapp", "--target", target, "--message", body],
                            capture_output=True, text=True, timeout=90, env=env,
                        )
                        if result.returncode == 0:
                            sent_any = True
                            if result.stdout:
                                import json
                                try:
                                    msg_data = json.loads(result.stdout)
                                    msg_id = msg_data.get("message_id") or msg_data.get("id") or ""
                                    if msg_id:
                                        _focus_alert_messages[msg_id] = room_code
                                except Exception:
                                    pass
                    except Exception as e:
                        logger.warning("Focus overstay WhatsApp send to %s failed: %s", target, e)
                whatsapp_ok = sent_any
                whatsapp_result = {"success": sent_any, "sent_to": len(whatsapp_targets)}
            else:
                whatsapp_result = {"success": False, "error": "whatsapp_not_configured"}
        except Exception as wa_exc:
            logger.warning("Focus overstay WhatsApp send failed: %s", wa_exc)
            whatsapp_result = {"success": False, "error": str(wa_exc)}

        result = {
            "success": whatsapp_ok,
            "whatsapp_sent": whatsapp_ok,
            "whatsapp_result": whatsapp_result,
        }
        if whatsapp_ok:
            logger.info("Focus overstay alert sent: site=%s room=%s result=%s", site_id, room_code, result)
        else:
            logger.warning("Focus overstay alert failed: site=%s room=%s result=%s", site_id, room_code, result)
        return result
    except Exception as exc:
        logger.warning("Focus overstay notifier exception: site=%s room=%s err=%s", site_id, room_code, exc)
        return {"success": False, "error": str(exc)}


async def process_focus_room_whatsapp_reply(
    from_number: str,
    content: str,
    *,
    reply_to_message_id: str | None = None,
    message_id: str | None = None,
) -> dict[str, Any]:
    """Handle concierge yes/no reply for a focus room overstay alert via WhatsApp."""
    reply = (content or "").strip().lower()
    if reply not in {"yes", "no"}:
        return {"handled": False}

    from app.services import occupancy_store

    # Try to match by replied-to message ID first
    room_code = ""
    site_id = "site-002"
    if reply_to_message_id and reply_to_message_id in _focus_alert_messages:
        room_code = _focus_alert_messages[reply_to_message_id]

    # Fallback: find active sessions
    if not room_code:
        all_sessions = []
        try:
            from app.database.supabase_client import get_supabase_client
            sb = get_supabase_client()
            if sb:
                result = sb.table("space_focus_room_sessions").select("*").is_("end_time", None).execute()
                all_sessions = result.data or []
        except Exception:
            pass

        if not all_sessions:
            return {"handled": True, "response_message": "No active focus room sessions found."}

        if len(all_sessions) > 1:
            rooms = [s.get("room_code", "?") for s in all_sessions]
            return {
                "handled": True,
                "response_message": f"Multiple active focus rooms: {', '.join(rooms)}. Please reply with the room code."
            }

        room_code = all_sessions[0].get("room_code", "")
        site_id = all_sessions[0].get("site_id", "site-002")

    active = occupancy_store.get_active_session(room_code) if room_code else None
    if not active:
        return {"handled": True, "response_message": f"No active session for {room_code}."}

    session_id = active.session_id

    from datetime import datetime

    if reply == "yes":
        occupancy_store.extend_overstay_grace(session_id, 10)
        from app.services.focus_room_relay_service import sync_focus_room_relay
        sync_focus_room_relay(site_id=site_id, room_code=room_code)
        logger.info("Focus overstay confirmed occupied — grace +10min via WhatsApp: room=%s", room_code)
        return {
            "handled": True,
            "response_message": f"{room_code} — confirmed occupied. Grace period added. Red light released.",
        }
    else:
        occupancy_store.close_session(session_id, datetime.utcnow())
        from app.services.focus_room_relay_service import sync_focus_room_relay
        sync_focus_room_relay(site_id=site_id, room_code=room_code)
        logger.info("Focus session reset via WhatsApp (room vacant): room=%s", room_code)
        return {
            "handled": True,
            "response_message": f"{room_code} — recorded vacant. Session ended, relay reset.",
        }
