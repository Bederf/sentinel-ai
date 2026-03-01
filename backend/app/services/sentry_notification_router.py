"""
Sentry Notification Router for SENTINEL.

Importance-based notification delivery through Sentry (WhatsApp/Telegram).

Delivery logic:
    CRITICAL  -> Immediate push to ALL channels + escalation timer
    HIGH      -> Immediate push to primary channel + escalation timer
    MEDIUM    -> Batched into daily digest
    LOW       -> Weekly digest
    INFO      -> Log only, no notification

Configuration via environment variables:
    SENTRY_WEBHOOK_URL         - Sentry bot webhook endpoint
    SENTRY_ESCALATION_MINUTES  - Minutes before escalation (default: 15)
    SENTRY_DIGEST_HOUR         - Hour (UTC) to send daily digest (default: 8)
    SENTRY_WEEKLY_DAY           - Day for weekly digest 0=Mon (default: 0)
"""

import logging
import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set

import httpx

from app.services.event_bus import Importance, SentinelEvent, get_event_bus

logger = logging.getLogger("sentinel.sentry_router")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class SentryRouterConfig:
    webhook_url: str = ""
    escalation_minutes: int = 15
    digest_hour: int = 8
    weekly_day: int = 0

    @property
    def is_configured(self) -> bool:
        return bool(self.webhook_url)

    @classmethod
    def from_env(cls) -> "SentryRouterConfig":
        return cls(
            webhook_url=os.getenv("SENTRY_WEBHOOK_URL", ""),
            escalation_minutes=int(os.getenv("SENTRY_ESCALATION_MINUTES", "15")),
            digest_hour=int(os.getenv("SENTRY_DIGEST_HOUR", "8")),
            weekly_day=int(os.getenv("SENTRY_WEEKLY_DAY", "0")),
        )


# ---------------------------------------------------------------------------
# Delivery Channel & Mode
# ---------------------------------------------------------------------------


class DeliveryChannel(str, Enum):
    WHATSAPP = "whatsapp"
    TELEGRAM = "telegram"
    EMAIL = "email"
    SMS = "sms"


class DeliveryMode(str, Enum):
    IMMEDIATE = "immediate"
    DAILY_DIGEST = "daily"
    WEEKLY_DIGEST = "weekly"
    LOG_ONLY = "log_only"


# ---------------------------------------------------------------------------
# Recipient Model
# ---------------------------------------------------------------------------


@dataclass
class NotificationRecipient:
    """A person who receives notifications."""

    name: str
    role: str  # "technician", "supervisor", "manager", "admin"
    channels: List[DeliveryChannel]
    site_ids: Optional[Set[str]] = None  # None = all sites
    min_importance: Importance = Importance.MEDIUM
    whatsapp: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    email: Optional[str] = None

    def should_notify(self, event: SentinelEvent) -> bool:
        if event.importance < self.min_importance:
            return False
        if self.site_ids and event.site_id and event.site_id not in self.site_ids:
            return False
        return True


# ---------------------------------------------------------------------------
# Message Formatter
# ---------------------------------------------------------------------------


class MessageFormatter:
    """Format SentinelEvents into human-readable messages."""

    IMPORTANCE_EMOJI = {
        Importance.CRITICAL: "\U0001f6a8",  # 🚨
        Importance.HIGH: "\u26a0\ufe0f",  # ⚠️
        Importance.MEDIUM: "\U0001f4cb",  # 📋
        Importance.LOW: "\u2139\ufe0f",  # ℹ️
        Importance.INFO: "\U0001f4dd",  # 📝
    }

    DOMAIN_EMOJI = {
        "sensor": "\U0001f4e1",  # 📡
        "ai": "\U0001f916",  # 🤖
        "maintenance": "\U0001f527",  # 🔧
        "hvac": "\u2744\ufe0f",  # ❄️
        "energy": "\u26a1",  # ⚡
        "solar": "\u2600\ufe0f",  # ☀️
        "water": "\U0001f4a7",  # 💧
        "security": "\U0001f512",  # 🔒
        "system": "\U0001f4bb",  # 💻
        "sentry": "\U0001f4e8",  # 📨
    }

    @classmethod
    def format_push(cls, event: SentinelEvent) -> Dict[str, str]:
        """Format for immediate push notification."""
        emoji = cls.IMPORTANCE_EMOJI.get(event.importance, "\U0001f4cb")
        domain_emoji = cls.DOMAIN_EMOJI.get(event.domain, "\U0001f514")

        title = cls._event_title(event)
        lines = [f"{emoji} *{title}*", ""]

        if event.building_name:
            lines.append(f"\U0001f3e2 {event.building_name}")
        elif event.site_id:
            lines.append(f"\U0001f3e2 {event.site_id}")

        if event.equipment_id:
            lines.append(f"{domain_emoji} {event.equipment_id}")

        lines.append("")

        description = (
            event.payload.get("description")
            or event.payload.get("recommendation")
            or event.payload.get("message")
            or event.payload.get("short_description")
        )
        if description:
            lines.append(description)
            lines.append("")

        metric = event.payload.get("metric")
        value = event.payload.get("value")
        threshold = event.payload.get("threshold")
        if metric and value is not None:
            suffix = f" (threshold: {threshold})" if threshold else ""
            lines.append(f"\U0001f4ca {metric}: {value}{suffix}")

        priority = event.payload.get("priority")
        if priority:
            lines.append(f"Priority: {priority}")

        wo_id = event.payload.get("work_order_id")
        if wo_id:
            lines.append(f"\U0001f527 Work Order: {wo_id}")

        if event.payload.get("escalated"):
            lines.append("")
            reason = event.payload.get("escalation_reason", "repeated alerts")
            lines.append(f"\u2b06\ufe0f *ESCALATED* \u2014 {reason}")

        lines.append("")
        lines.append(f"\U0001f550 {cls._format_time(event.timestamp)}")

        message = "\n".join(lines)
        return {
            "whatsapp": message,
            "telegram": message,
            "plain": cls._strip_formatting(message),
        }

    @classmethod
    def format_digest(
        cls,
        events: List[SentinelEvent],
        period: str = "daily",
    ) -> Dict[str, str]:
        """Format a batch of events as a digest summary."""
        if not events:
            return {"whatsapp": "No events to report.", "telegram": "No events to report."}

        by_domain: Dict[str, List[SentinelEvent]] = defaultdict(list)
        for e in events:
            by_domain[e.domain].append(e)

        by_importance: Dict[str, int] = defaultdict(int)
        for e in events:
            by_importance[e.importance.name] += 1

        lines = [
            f"\U0001f4ca *SENTINEL {period.title()} Digest*",
            f"\U0001f4c5 {cls._format_time(datetime.utcnow().isoformat())}",
            f"Total events: {len(events)}",
            "",
        ]

        importance_parts = []
        for imp in [Importance.CRITICAL, Importance.HIGH, Importance.MEDIUM, Importance.LOW]:
            count = by_importance.get(imp.name, 0)
            if count:
                imp_emoji = cls.IMPORTANCE_EMOJI[imp]
                importance_parts.append(f"{imp_emoji} {imp.name}: {count}")
        if importance_parts:
            lines.append(" | ".join(importance_parts))
            lines.append("")

        for domain, domain_events in sorted(by_domain.items()):
            d_emoji = cls.DOMAIN_EMOJI.get(domain, "\U0001f514")
            lines.append(f"{d_emoji} *{domain.title()}* ({len(domain_events)})")
            for e in domain_events[:3]:
                t = cls._event_title(e)
                ie = cls.IMPORTANCE_EMOJI.get(e.importance, "")
                lines.append(f"  {ie} {t}")
                if e.equipment_id:
                    lines.append(f"    \u2514 {e.equipment_id}")
            if len(domain_events) > 3:
                lines.append(f"  ... and {len(domain_events) - 3} more")
            lines.append("")

        message = "\n".join(lines)
        return {
            "whatsapp": message,
            "telegram": message,
            "plain": cls._strip_formatting(message),
        }

    @staticmethod
    def _event_title(event: SentinelEvent) -> str:
        action = event.action.replace("_", " ").title()
        titles = {
            "sensor.anomaly_detected": "Sensor Anomaly Detected",
            "ai.diagnosis_complete": "AI Diagnosis Complete",
            "maintenance.work_order_created": "New Work Order",
            "maintenance.work_order_completed": "Work Order Completed",
            "sentry.escalation_triggered": "Escalation \u2014 No Response",
            "hvac.setpoint_changed": "HVAC Setpoint Changed",
            "energy.load_shedding_started": "Load Shedding Active",
            "solar.generation_anomaly": "Solar Generation Anomaly",
            "system.health_check_failed": "System Health Alert",
        }
        return titles.get(event.event_type, f"{event.domain.upper()}: {action}")

    @staticmethod
    def _format_time(iso_str: str) -> str:
        try:
            dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
            return dt.strftime("%H:%M %d %b %Y")
        except Exception:
            return iso_str

    @staticmethod
    def _strip_formatting(text: str) -> str:
        return text.replace("*", "").replace("_", "")


# ---------------------------------------------------------------------------
# Digest Accumulator
# ---------------------------------------------------------------------------


class DigestAccumulator:
    """Collects events for batched delivery (daily/weekly)."""

    def __init__(self):
        self._daily: Dict[str, List[SentinelEvent]] = defaultdict(list)
        self._weekly: Dict[str, List[SentinelEvent]] = defaultdict(list)

    def add_daily(self, recipient_key: str, event: SentinelEvent):
        self._daily[recipient_key].append(event)

    def add_weekly(self, recipient_key: str, event: SentinelEvent):
        self._weekly[recipient_key].append(event)

    def flush_daily(self) -> Dict[str, List[SentinelEvent]]:
        events = dict(self._daily)
        self._daily.clear()
        return events

    def flush_weekly(self) -> Dict[str, List[SentinelEvent]]:
        events = dict(self._weekly)
        self._weekly.clear()
        return events

    @property
    def daily_count(self) -> int:
        return sum(len(v) for v in self._daily.values())

    @property
    def weekly_count(self) -> int:
        return sum(len(v) for v in self._weekly.values())

    def get_stats(self) -> Dict[str, Any]:
        return {
            "daily_pending": self.daily_count,
            "daily_recipients": len(self._daily),
            "weekly_pending": self.weekly_count,
            "weekly_recipients": len(self._weekly),
        }


# ---------------------------------------------------------------------------
# Escalation Tracker
# ---------------------------------------------------------------------------


@dataclass
class EscalationEntry:
    event_id: str
    event: SentinelEvent
    sent_at: datetime
    escalation_deadline: datetime
    acknowledged: bool = False
    escalated: bool = False
    recipient: Optional[str] = None


class EscalationTracker:
    """Tracks unacknowledged notifications and triggers escalation."""

    def __init__(self, escalation_minutes: int = 15):
        self._entries: Dict[str, EscalationEntry] = {}
        self._escalation_window = timedelta(minutes=escalation_minutes)

    def track(self, event: SentinelEvent, recipient: Optional[str] = None):
        now = datetime.utcnow()
        self._entries[event.event_id] = EscalationEntry(
            event_id=event.event_id,
            event=event,
            sent_at=now,
            escalation_deadline=now + self._escalation_window,
            recipient=recipient,
        )

    def acknowledge(self, event_id: str) -> bool:
        if event_id in self._entries:
            self._entries[event_id].acknowledged = True
            return True
        return False

    async def check_escalations(self) -> List[SentinelEvent]:
        now = datetime.utcnow()
        escalations = []

        for entry in list(self._entries.values()):
            if entry.acknowledged or entry.escalated:
                continue

            if now >= entry.escalation_deadline:
                entry.escalated = True
                window_min = self._escalation_window.total_seconds() / 60

                escalation = entry.event.chain(
                    event_type="sentry.escalation_triggered",
                    source="escalation_tracker",
                    payload={
                        "original_event": entry.event.event_type,
                        "original_event_id": entry.event.event_id,
                        "sent_at": entry.sent_at.isoformat(),
                        "deadline": entry.escalation_deadline.isoformat(),
                        "recipient": entry.recipient,
                        "reason": f"No acknowledgement after {window_min:.0f} minutes",
                    },
                    importance=Importance.CRITICAL,
                )
                escalations.append(escalation)

                logger.info(
                    "[ESCALATION] %s for %s — no response from %s, escalating",
                    entry.event.event_type,
                    entry.event.equipment_id,
                    entry.recipient or "unknown",
                )

        # Cleanup old entries (>24h)
        cutoff = now - timedelta(hours=24)
        self._entries = {k: v for k, v in self._entries.items() if v.sent_at > cutoff}

        return escalations

    def get_pending(self) -> List[Dict[str, Any]]:
        now = datetime.utcnow()
        return [
            {
                "event_id": e.event_id,
                "event_type": e.event.event_type,
                "equipment_id": e.event.equipment_id,
                "site_id": e.event.site_id,
                "sent_at": e.sent_at.isoformat(),
                "deadline": e.escalation_deadline.isoformat(),
                "overdue": now >= e.escalation_deadline,
                "minutes_remaining": max(0, (e.escalation_deadline - now).total_seconds() / 60),
                "recipient": e.recipient,
            }
            for e in self._entries.values()
            if not e.acknowledged and not e.escalated
        ]

    def get_stats(self) -> Dict[str, Any]:
        return {
            "tracked": len(self._entries),
            "pending_acknowledgement": sum(1 for e in self._entries.values() if not e.acknowledged and not e.escalated),
            "acknowledged": sum(1 for e in self._entries.values() if e.acknowledged),
            "escalated": sum(1 for e in self._entries.values() if e.escalated),
        }


# ---------------------------------------------------------------------------
# Main Notification Router
# ---------------------------------------------------------------------------


class SentryNotificationRouter:
    """The intelligence layer between the event bus and Sentry bot.

    Decides:
        - WHEN to send (immediate, daily digest, weekly digest, never)
        - WHO to send to (recipient resolution by site + role)
        - WHAT format (push message, digest summary)
        - WHETHER to escalate (track acknowledgements)
    """

    def __init__(self, config: Optional[SentryRouterConfig] = None):
        self._config = config or SentryRouterConfig.from_env()
        self._formatter = MessageFormatter()
        self._digest = DigestAccumulator()
        self._escalation = EscalationTracker(
            escalation_minutes=self._config.escalation_minutes,
        )
        self._recipients: List[NotificationRecipient] = []
        self._metrics: Dict[str, int] = {
            "pushes_sent": 0,
            "digests_collected": 0,
            "escalations_triggered": 0,
            "delivery_errors": 0,
        }

    # -------------------------------------------------------------------
    # Recipient Management
    # -------------------------------------------------------------------

    def add_recipient(self, recipient: NotificationRecipient):
        self._recipients.append(recipient)
        logger.info("Registered recipient: %s (%s)", recipient.name, recipient.role)

    def get_recipients_for_event(self, event: SentinelEvent) -> List[NotificationRecipient]:
        return [r for r in self._recipients if r.should_notify(event)]

    # -------------------------------------------------------------------
    # Delivery Decision
    # -------------------------------------------------------------------

    def get_delivery_mode(self, event: SentinelEvent) -> DeliveryMode:
        if event.importance >= Importance.HIGH:
            return DeliveryMode.IMMEDIATE
        elif event.importance == Importance.MEDIUM:
            return DeliveryMode.DAILY_DIGEST
        elif event.importance == Importance.LOW:
            return DeliveryMode.WEEKLY_DIGEST
        else:
            return DeliveryMode.LOG_ONLY

    # -------------------------------------------------------------------
    # Route Event (main entry point)
    # -------------------------------------------------------------------

    async def route(self, event: SentinelEvent):
        """Route an event to the appropriate delivery mechanism."""
        mode = self.get_delivery_mode(event)
        recipients = self.get_recipients_for_event(event)

        if not recipients:
            logger.debug("No recipients for %s at %s", event.event_type, event.site_id)
            return

        if mode == DeliveryMode.IMMEDIATE:
            await self._deliver_push(event, recipients)
        elif mode == DeliveryMode.DAILY_DIGEST:
            self._collect_daily(event, recipients)
        elif mode == DeliveryMode.WEEKLY_DIGEST:
            self._collect_weekly(event, recipients)

    async def _deliver_push(
        self,
        event: SentinelEvent,
        recipients: List[NotificationRecipient],
    ):
        formatted = self._formatter.format_push(event)

        for recipient in recipients:
            for channel in recipient.channels:
                success = await self._send(
                    channel=channel,
                    recipient=recipient,
                    message=formatted.get(channel.value, formatted["plain"]),
                    event=event,
                )
                if success:
                    self._metrics["pushes_sent"] += 1
                    if event.importance >= Importance.HIGH:
                        self._escalation.track(event, recipient=recipient.name)
                    break  # Sent on first available channel
                else:
                    self._metrics["delivery_errors"] += 1

    def _collect_daily(
        self,
        event: SentinelEvent,
        recipients: List[NotificationRecipient],
    ):
        for r in recipients:
            self._digest.add_daily(r.name, event)
            self._metrics["digests_collected"] += 1

    def _collect_weekly(
        self,
        event: SentinelEvent,
        recipients: List[NotificationRecipient],
    ):
        for r in recipients:
            self._digest.add_weekly(r.name, event)
            self._metrics["digests_collected"] += 1

    # -------------------------------------------------------------------
    # Digest Delivery
    # -------------------------------------------------------------------

    async def send_daily_digests(self):
        pending = self._digest.flush_daily()

        for recipient_name, events in pending.items():
            recipient = next((r for r in self._recipients if r.name == recipient_name), None)
            if not recipient or not events:
                continue

            formatted = self._formatter.format_digest(events, period="daily")
            for channel in recipient.channels:
                success = await self._send(
                    channel=channel,
                    recipient=recipient,
                    message=formatted.get(channel.value, formatted["plain"]),
                )
                if success:
                    break

        logger.info(
            "Daily digests sent to %d recipients (%d events)",
            len(pending),
            sum(len(v) for v in pending.values()),
        )

    async def send_weekly_digests(self):
        pending = self._digest.flush_weekly()

        for recipient_name, events in pending.items():
            recipient = next((r for r in self._recipients if r.name == recipient_name), None)
            if not recipient or not events:
                continue

            formatted = self._formatter.format_digest(events, period="weekly")
            for channel in recipient.channels:
                success = await self._send(
                    channel=channel,
                    recipient=recipient,
                    message=formatted.get(channel.value, formatted["plain"]),
                )
                if success:
                    break

    # -------------------------------------------------------------------
    # Acknowledgement
    # -------------------------------------------------------------------

    def acknowledge(self, event_id: str) -> bool:
        return self._escalation.acknowledge(event_id)

    async def check_escalations(self) -> int:
        escalations = await self._escalation.check_escalations()
        bus = get_event_bus()
        for event in escalations:
            await bus.emit(event)
            self._metrics["escalations_triggered"] += 1
        return len(escalations)

    # -------------------------------------------------------------------
    # Delivery (actual send to Sentry webhook)
    # -------------------------------------------------------------------

    async def _send(
        self,
        channel: DeliveryChannel,
        recipient: NotificationRecipient,
        message: str,
        event: Optional[SentinelEvent] = None,
    ) -> bool:
        if not self._config.is_configured:
            logger.debug("Sentry webhook not configured — would send to %s", recipient.name)
            return True  # Don't block pipeline if unconfigured

        contact = None
        if channel == DeliveryChannel.WHATSAPP:
            contact = recipient.whatsapp
        elif channel == DeliveryChannel.TELEGRAM:
            contact = recipient.telegram_chat_id
        elif channel == DeliveryChannel.EMAIL:
            contact = recipient.email

        if not contact:
            logger.debug("No %s contact for %s", channel.value, recipient.name)
            return False

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    self._config.webhook_url,
                    json={
                        "channel": channel.value,
                        "recipient": contact,
                        "recipient_name": recipient.name,
                        "message": message,
                        "importance": event.importance.name if event else "MEDIUM",
                        "event_id": event.event_id if event else None,
                        "event_type": event.event_type if event else None,
                        "site_id": event.site_id if event else None,
                    },
                )

                if response.status_code in (200, 201, 204):
                    logger.info("[SENTRY] Sent %s to %s", channel.value, recipient.name)
                    return True
                else:
                    logger.error(
                        "[SENTRY] Failed %s to %s: HTTP %d",
                        channel.value,
                        recipient.name,
                        response.status_code,
                    )
                    return False

        except Exception as e:
            logger.error("[SENTRY] Send error: %s", e)
            return False

    # -------------------------------------------------------------------
    # Status & Metrics
    # -------------------------------------------------------------------

    def get_status(self) -> Dict[str, Any]:
        return {
            "configured": self._config.is_configured,
            "recipients": len(self._recipients),
            "metrics": dict(self._metrics),
            "digest": self._digest.get_stats(),
            "escalation": self._escalation.get_stats(),
            "pending_escalations": self._escalation.get_pending(),
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_router: Optional[SentryNotificationRouter] = None


def get_sentry_router() -> SentryNotificationRouter:
    global _router
    if _router is None:
        _router = SentryNotificationRouter()
    return _router
