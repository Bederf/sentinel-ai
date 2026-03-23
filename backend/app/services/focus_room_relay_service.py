"""Focus room relay/light control for 2-hour overstay policy.

Publishes MQTT relay commands for focus rooms:
  - ON when session exceeds focus_extended_use_seconds (default 2h)
  - ON during cooldown window after overstay ends (default 5 min)
  - OFF otherwise
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

from app.config.settings import settings
from app.core.site_resolver import get_registered_site_ids
from app.services import occupancy_store
from app.services.focus_room_session_service import describe_focus_session_state
from app.services.space_mqtt_listener import get_node_room_mapping

logger = logging.getLogger(__name__)

_last_command_state: dict[str, bool] = {}


def _resolve_node_for_room(room_code: str) -> str | None:
    mapping = get_node_room_mapping()
    for node_id, node in mapping.items():
        if node.get("room_code") == room_code:
            return node_id
    return None


def _latest_session_for_room(site_id: str, room_code: str):
    sessions = occupancy_store.get_sessions_for_room(room_code)
    sessions = [s for s in sessions if s.site_id == site_id]
    if not sessions:
        return None
    return max(sessions, key=lambda s: s.start_time)


def _desired_relay_state(site_id: str, room_code: str, now: datetime | None = None) -> tuple[bool, str]:
    latest = _latest_session_for_room(site_id, room_code)
    if latest is None:
        return False, "no_session"

    state = describe_focus_session_state(latest, now=now)
    relay_on = bool(state.get("red_light_on", False))
    reason = "overstay_or_cooldown" if relay_on else "within_limit"
    return relay_on, reason


def _publish_relay_command(node_id: str, room_code: str, relay_on: bool, reason: str) -> bool:
    if not settings.focus_relay_enabled:
        return False
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        logger.warning("Focus relay command skipped: paho-mqtt not installed")
        return False

    topic = settings.focus_relay_topic_template.format(node_id=node_id)
    payload = {
        "node_id": node_id,
        "room_code": room_code,
        "relay_on": relay_on,
        "reason": reason,
        "ts": datetime.utcnow().isoformat(),
    }

    client = mqtt.Client(client_id=f"sentinel-focus-relay-{node_id}")
    if settings.space_mqtt_username:
        client.username_pw_set(settings.space_mqtt_username, settings.space_mqtt_password)

    try:
        client.connect(settings.space_mqtt_broker, settings.space_mqtt_port, keepalive=10)
        info = client.publish(topic, json.dumps(payload), qos=1, retain=False)
        info.wait_for_publish(timeout=2.0)
        client.disconnect()
        logger.info("Focus relay command: node=%s room=%s relay_on=%s topic=%s", node_id, room_code, relay_on, topic)
        return True
    except Exception as exc:
        logger.warning("Focus relay publish failed for node=%s room=%s: %s", node_id, room_code, exc)
        return False


def sync_focus_room_relay(site_id: str, room_code: str, now: datetime | None = None) -> dict[str, object]:
    """Recompute desired relay state for one focus room and publish if changed."""
    node_id = _resolve_node_for_room(room_code)
    if not node_id:
        return {"success": False, "reason": "node_not_mapped", "room_code": room_code}

    desired, reason = _desired_relay_state(site_id, room_code, now=now)
    previous = _last_command_state.get(node_id)
    if previous is not None and previous == desired:
        return {
            "success": True,
            "node_id": node_id,
            "room_code": room_code,
            "relay_on": desired,
            "changed": False,
            "reason": reason,
        }

    published = _publish_relay_command(node_id, room_code, desired, reason)
    if published:
        _last_command_state[node_id] = desired
    return {
        "success": published,
        "node_id": node_id,
        "room_code": room_code,
        "relay_on": desired,
        "changed": True,
        "reason": reason,
    }


def scan_all_focus_relays(now: datetime | None = None) -> dict[str, int]:
    """Periodic reconciliation for cooldown expiry and missed transitions."""
    mapping = get_node_room_mapping()
    now = now or datetime.utcnow()
    scanned = 0
    changed = 0

    site_ids = set(get_registered_site_ids())
    for node_id, node in mapping.items():
        room_type = (node.get("room_type") or "meeting").lower()
        if room_type != "focus":
            continue

        room_code = node.get("room_code")
        site_id = node.get("site_id")
        if not room_code or not site_id or site_id not in site_ids:
            continue

        scanned += 1
        result = sync_focus_room_relay(site_id=site_id, room_code=room_code, now=now)
        if result.get("changed") and result.get("success"):
            changed += 1

    return {"scanned": scanned, "changed": changed}
