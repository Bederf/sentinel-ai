"""Background sensor health monitor.

Runs every 60 seconds to detect sensors that have gone offline
(no heartbeat within SENSOR_OFFLINE_THRESHOLD_SECONDS).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from app.space import space_repository as repo
from app.space.room_state_engine import SENSOR_OFFLINE_THRESHOLD_SECONDS

logger = logging.getLogger("sentinel.space.monitor")


async def check_sensor_health(site_id: str = "FLN02") -> dict:
    """Check all registered sensors and flag any that have gone offline.

    Returns:
        Summary dict with counts of checked, offline_detected, recovered.
    """
    devices = await repo.get_all_devices(site_id=site_id)
    now = datetime.now(UTC)

    checked = 0
    offline_detected = 0
    recovered = 0

    for device in devices:
        if not device.get("enabled", True):
            continue
        checked += 1
        sensor_id = device.get("sensor_id", "")
        room_code = device.get("room_code", "")

        last_seen_raw = device.get("last_seen_at")
        if not last_seen_raw:
            # Device never reported — skip (could be newly provisioned)
            continue

        if isinstance(last_seen_raw, str):
            try:
                last_seen = datetime.fromisoformat(last_seen_raw.replace("Z", "+00:00"))
            except ValueError:
                continue
        else:
            last_seen = last_seen_raw

        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=UTC)

        elapsed = (now - last_seen).total_seconds()
        current_state = await repo.get_room_current_state(room_code)
        was_online = True
        if current_state:
            was_online = current_state.get("sensor_online", True)

        if elapsed > SENSOR_OFFLINE_THRESHOLD_SECONDS and was_online:
            # Mark offline
            logger.warning(
                "Sensor %s offline: last seen %.0fs ago (threshold %ds)",
                sensor_id,
                elapsed,
                SENSOR_OFFLINE_THRESHOLD_SECONDS,
            )
            if current_state:
                current_state["sensor_online"] = False
                current_state["updated_at"] = now.isoformat()
                await repo.upsert_room_current_state(current_state)

            await repo.insert_finding(
                {
                    "room_code": room_code,
                    "site_id": site_id,
                    "finding_type": "sensor_offline",
                    "detail": f"No heartbeat for {int(elapsed)}s",
                    "detected_at": now.isoformat(),
                    "resolved": False,
                }
            )
            offline_detected += 1

        elif elapsed <= SENSOR_OFFLINE_THRESHOLD_SECONDS and not was_online:
            # Sensor recovered (new event arrived between checks)
            logger.info("Sensor %s recovered (was offline)", sensor_id)
            if current_state:
                current_state["sensor_online"] = True
                current_state["updated_at"] = now.isoformat()
                await repo.upsert_room_current_state(current_state)

            await repo.resolve_finding(room_code, "sensor_offline")
            recovered += 1

    summary = {
        "checked": checked,
        "offline_detected": offline_detected,
        "recovered": recovered,
        "timestamp": now.isoformat(),
    }
    if offline_detected or recovered:
        logger.info("Sensor health check: %s", summary)
    return summary
