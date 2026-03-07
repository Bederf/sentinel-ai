"""Notification throttle and alarm flood protection.

Three protections against chatty BMS systems:
1. Dedup window (already in alarm_store.check_duplicate) — same subject within 1 hour
2. Alarm flood detection — >N alarms from same equipment in M minutes → suppress + summary
3. Notification rate limit — max N WhatsApp messages per hour regardless of volume

All state is in-memory (resets on restart). This is intentional — flood state
should not persist across restarts. Alarms are still saved to Supabase/JSON
regardless of throttle state.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum

from app.plant.models import DesigoBuildingAlarm

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration defaults (overridable via settings)
# ---------------------------------------------------------------------------

# Flood detection: >N alarms from same equipment in M minutes
FLOOD_THRESHOLD = 5  # alarms
FLOOD_WINDOW_MINUTES = 10  # minutes

# Notification rate limit: max N messages per hour
HOURLY_MESSAGE_LIMIT = 30


# ---------------------------------------------------------------------------
# Decision types (defined before NotificationThrottle which uses them)
# ---------------------------------------------------------------------------


class ThrottleAction(str, Enum):
    SEND = "send"
    SEND_FLOOD_SUMMARY = "send_flood_summary"
    SUPPRESS = "suppress"


@dataclass
class ThrottleDecision:
    action: ThrottleAction
    reason: str = ""
    flood_count: int = 0
    equipment: str = ""


@dataclass
class FloodState:
    """Tracks alarm frequency per equipment description."""

    timestamps: list[datetime] = field(default_factory=list)
    flood_active: bool = False
    flood_notified: bool = False  # Have we sent the flood summary?
    suppressed_count: int = 0


class NotificationThrottle:
    """In-memory notification throttle with flood detection and rate limiting."""

    def __init__(
        self,
        flood_threshold: int = FLOOD_THRESHOLD,
        flood_window_minutes: int = FLOOD_WINDOW_MINUTES,
        hourly_limit: int = HOURLY_MESSAGE_LIMIT,
    ):
        self.flood_threshold = flood_threshold
        self.flood_window_minutes = flood_window_minutes
        self.hourly_limit = hourly_limit

        # Per-equipment flood tracking: equipment_description -> FloodState
        self._flood_states: dict[str, FloodState] = defaultdict(FloodState)

        # Global rate limit: list of send timestamps in current hour
        self._send_timestamps: list[datetime] = []

    def _prune_flood_window(self, state: FloodState, now: datetime) -> None:
        """Remove timestamps outside the flood detection window."""
        cutoff = now - timedelta(minutes=self.flood_window_minutes)
        state.timestamps = [t for t in state.timestamps if t >= cutoff]

    def _prune_rate_window(self, now: datetime) -> None:
        """Remove send timestamps older than 1 hour."""
        cutoff = now - timedelta(hours=1)
        self._send_timestamps = [t for t in self._send_timestamps if t >= cutoff]

    def check_alarm(self, alarm: DesigoBuildingAlarm) -> ThrottleDecision:
        """Evaluate whether a notification should be sent for this alarm.

        Returns a ThrottleDecision indicating:
        - SEND: Normal delivery
        - SEND_FLOOD_SUMMARY: Send a flood summary instead of individual alert
        - SUPPRESS: Do not send any notification
        """
        now = datetime.now(UTC)
        equip = alarm.equipment_description

        # --- Flood detection ---
        state = self._flood_states[equip]
        state.timestamps.append(now)
        self._prune_flood_window(state, now)

        if len(state.timestamps) >= self.flood_threshold:
            if not state.flood_active:
                # Flood just started
                state.flood_active = True
                state.flood_notified = False
                state.suppressed_count = 0
                logger.warning(
                    "Alarm flood detected: %s — %d alarms in %d minutes",
                    equip,
                    len(state.timestamps),
                    self.flood_window_minutes,
                )

            if not state.flood_notified:
                # Send one flood summary notification
                state.flood_notified = True
                return ThrottleDecision(
                    action=ThrottleAction.SEND_FLOOD_SUMMARY,
                    reason=f"Flood: {len(state.timestamps)} alarms from '{equip}' in {self.flood_window_minutes}min",
                    flood_count=len(state.timestamps),
                    equipment=equip,
                )
            else:
                state.suppressed_count += 1
                return ThrottleDecision(
                    action=ThrottleAction.SUPPRESS,
                    reason=f"Flood active: '{equip}' — {state.suppressed_count} suppressed",
                )
        else:
            # Below threshold — clear flood if it was active
            if state.flood_active:
                logger.info(
                    "Alarm flood cleared for %s — %d alarms suppressed during flood",
                    equip,
                    state.suppressed_count,
                )
                state.flood_active = False
                state.flood_notified = False
                state.suppressed_count = 0

        # --- Rate limit ---
        self._prune_rate_window(now)
        if len(self._send_timestamps) >= self.hourly_limit:
            return ThrottleDecision(
                action=ThrottleAction.SUPPRESS,
                reason=f"Rate limit: {self.hourly_limit} messages/hour reached",
            )

        return ThrottleDecision(action=ThrottleAction.SEND)

    def record_send(self) -> None:
        """Record that a notification was actually sent (for rate limiting)."""
        self._send_timestamps.append(datetime.now(UTC))

    def get_flood_status(self) -> dict[str, dict]:
        """Return current flood state for all tracked equipment (for API/monitoring)."""
        now = datetime.now(UTC)
        result = {}
        for equip, state in self._flood_states.items():
            self._prune_flood_window(state, now)
            if state.timestamps:  # Only include equipment with recent activity
                result[equip] = {
                    "recent_alarms": len(state.timestamps),
                    "flood_active": state.flood_active,
                    "suppressed_count": state.suppressed_count,
                    "window_minutes": self.flood_window_minutes,
                    "threshold": self.flood_threshold,
                }
        return result

    def get_rate_status(self) -> dict:
        """Return current rate limit status (for API/monitoring)."""
        now = datetime.now(UTC)
        self._prune_rate_window(now)
        return {
            "messages_this_hour": len(self._send_timestamps),
            "hourly_limit": self.hourly_limit,
            "remaining": max(0, self.hourly_limit - len(self._send_timestamps)),
        }


# ---------------------------------------------------------------------------
# Flood summary message formatter
# ---------------------------------------------------------------------------


def format_flood_summary(equipment: str, count: int, window_minutes: int) -> str:
    """Format a flood detection summary message for WhatsApp."""
    return (
        "\u26a0\ufe0f *SENTINEL \u2014 ALARM FLOOD DETECTED*\n"
        "\n"
        f"*{equipment}* \u2014 {count} alarms in {window_minutes} minutes\n"
        "\n"
        "Possible sensor fault. Single notification only until resolved.\n"
        "Individual alerts suppressed to prevent message flooding."
    )


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_throttle: NotificationThrottle | None = None


def get_throttle() -> NotificationThrottle:
    """Return the singleton throttle instance."""
    global _throttle
    if _throttle is None:
        _throttle = NotificationThrottle()
    return _throttle


def reset_throttle() -> None:
    """Reset the singleton (for testing)."""
    global _throttle
    _throttle = None
