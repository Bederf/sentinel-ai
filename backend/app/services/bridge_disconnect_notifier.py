"""Bridge disconnect notifier.

Fires a CRITICAL Telegram alert when a site's bridge connection has failed
for 3+ consecutive poll cycles (typically 15–30 min of silence).
Sends a recovery notification when polling resumes after a failure streak.

Throttle: re-alerts every 60 min while a site remains disconnected to avoid
flooding, but always sends the first alert and the recovery.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

logger = logging.getLogger(__name__)

# --- module-level state (survives across poll cycles in same process) ---

# site_id → count of consecutive polls where ALL telemetry endpoints returned errors
_consecutive_failures: dict[str, int] = {}

# site_id → datetime of the first failure in the current streak
_failure_started_at: dict[str, datetime] = {}

# site_id → datetime of the most recent alert send (for throttle)
_last_alert_sent_at: dict[str, datetime] = {}

# site_id → True once we've sent the initial "down" alert (cleared on recovery)
_alert_active: dict[str, bool] = {}

FAILURE_THRESHOLD = 3          # consecutive failures before alerting
THROTTLE_MINUTES = 60          # re-alert interval while still down
RECOVERY_MIN_FAILURES = 1      # must have had at least this many failures to send recovery msg


def record_poll_result(site_id: str, *, has_errors: bool, site_name: str | None = None) -> None:
    """Call once per poll cycle.  has_errors=True means all telemetry failed."""
    if has_errors:
        _consecutive_failures[site_id] = _consecutive_failures.get(site_id, 0) + 1
        if site_id not in _failure_started_at:
            _failure_started_at[site_id] = datetime.now(UTC)
    else:
        # Poll succeeded — check if we need to send a recovery notification
        prev_failures = _consecutive_failures.get(site_id, 0)
        _consecutive_failures[site_id] = 0

        if prev_failures >= RECOVERY_MIN_FAILURES and _alert_active.get(site_id):
            _alert_active[site_id] = False
            _failure_started_at.pop(site_id, None)
            _last_alert_sent_at.pop(site_id, None)
            import asyncio

            label = site_name or site_id
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(_send_recovery_alert(site_id, label, prev_failures))
                else:
                    loop.run_until_complete(_send_recovery_alert(site_id, label, prev_failures))
            except RuntimeError:
                asyncio.run(_send_recovery_alert(site_id, label, prev_failures))


def check_and_alert(site_id: str, *, site_name: str | None = None) -> None:
    """Call after record_poll_result to fire alert if threshold crossed."""
    failures = _consecutive_failures.get(site_id, 0)
    if failures < FAILURE_THRESHOLD:
        return

    now = datetime.now(UTC)
    last_sent = _last_alert_sent_at.get(site_id)

    # Throttle: skip if we already alerted recently
    if last_sent and (now - last_sent) < timedelta(minutes=THROTTLE_MINUTES):
        return

    started_at = _failure_started_at.get(site_id, now)
    down_minutes = int((now - started_at).total_seconds() / 60)
    label = site_name or site_id

    import asyncio

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(_send_down_alert(site_id, label, failures, down_minutes))
        else:
            loop.run_until_complete(_send_down_alert(site_id, label, failures, down_minutes))
    except RuntimeError:
        asyncio.run(_send_down_alert(site_id, label, failures, down_minutes))

    _last_alert_sent_at[site_id] = now
    _alert_active[site_id] = True


async def _send_down_alert(
    site_id: str, site_label: str, failure_count: int, down_minutes: int
) -> None:
    try:
        from app.models.notification import AlertLevel
        from app.services.notification_service import notification_service

        title = f"🔴 Bridge Disconnected — {site_label}"
        body = (
            f"Site: {site_label} ({site_id})\n"
            f"Status: Bridge connection FAILED\n"
            f"Duration: ~{down_minutes} min ({failure_count} consecutive poll failures)\n"
            f"Impact: No telemetry, recommendations, or control signals.\n"
            f"Action: Check WireGuard tunnel + bridge service on VPS."
        )
        result = await notification_service.send_alert_direct(
            title=title, body=body, alert_level=AlertLevel.CRITICAL
        )
        if result.get("success"):
            logger.warning("[BRIDGE-ALERT] Sent disconnect alert for %s (%d failures)", site_id, failure_count)
        else:
            logger.error("[BRIDGE-ALERT] Failed to send disconnect alert for %s: %s", site_id, result.get("error"))
    except Exception as exc:
        logger.error("[BRIDGE-ALERT] Exception sending disconnect alert for %s: %s", site_id, exc)


async def _send_recovery_alert(site_id: str, site_label: str, prev_failure_count: int) -> None:
    try:
        from app.models.notification import AlertLevel
        from app.services.notification_service import notification_service

        title = f"✅ Bridge Restored — {site_label}"
        body = (
            f"Site: {site_label} ({site_id})\n"
            f"Status: Bridge connection RESTORED\n"
            f"Previous failures: {prev_failure_count} consecutive polls\n"
            f"Telemetry is flowing again."
        )
        result = await notification_service.send_alert_direct(
            title=title, body=body, alert_level=AlertLevel.INFO
        )
        if result.get("success"):
            logger.info("[BRIDGE-ALERT] Sent recovery alert for %s", site_id)
        else:
            logger.error("[BRIDGE-ALERT] Failed to send recovery alert for %s: %s", site_id, result.get("error"))
    except Exception as exc:
        logger.error("[BRIDGE-ALERT] Exception sending recovery alert for %s: %s", site_id, exc)
