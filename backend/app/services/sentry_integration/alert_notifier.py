"""Alert notification service for Sentry Telegram bot."""

import asyncio
import json
import logging
import os
import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict
from uuid import uuid4

from app.config.settings import settings
from app.database.repositories.notification_repository import (
    NotificationRepository,
    SYSTEM_NOTIFIER_TECHNICIAN_ID,
)
from app.models.notification import ChannelType, NotificationDeliveryLog, NotificationStatus
from app.services.sentry_integration.config import get_sentry_bot_cli

# Default alert commands when settings not configured
DEFAULT_ALERT_COMMANDS = {
    "reset": {"enabled": True, "label": "Remote reset"},
    "info": {"enabled": True, "label": "More info"},
    "note": {"enabled": True, "label": "Add note"},
    "wo": {"enabled": True, "label": "Create work order"},
}

# Settings file path
SETTINGS_FILE = Path(__file__).parent.parent.parent / "data" / "settings.json"
logger = logging.getLogger(__name__)


def _load_notification_settings() -> Dict[str, Any]:
    """Load notification settings from settings.json."""
    try:
        if SETTINGS_FILE.exists():
            with open(SETTINGS_FILE, "r") as f:
                settings = json.load(f)
            return settings.get("notifications", {})
    except Exception:
        pass
    return {}


class AlertNotifier:
    """Send BMS alerts via sentry CLI."""

    def __init__(self):
        self.fm_chat_id = (
            (os.getenv("SENTRY_FM_CHAT_ID", "") or "").strip()
            or str(getattr(settings, "sentry_fm_chat_id", "") or "").strip()
            or str(getattr(settings, "telegram_alert_chat_id", "") or "").strip()
        )
        self._cli_command = get_sentry_bot_cli()
        # Track last alert time per equipment+severity to prevent spam
        self._last_alerts: Dict[str, datetime] = {}
        self._notification_repo = NotificationRepository()

    @property
    def ALERT_COOLDOWN_MINUTES(self) -> int:
        """Get cooldown from settings, defaulting to 5 minutes."""
        settings = _load_notification_settings()
        return settings.get("alertCooldownMinutes", 5)

    @staticmethod
    def _sanitize_for_shell(text: str) -> str:
        """Remove shell metacharacters from text to prevent command injection.

        Phase 58-04 H-5: Strips characters that could be interpreted by a
        shell even though we already pass args as a list (defence in depth).
        """
        return re.sub(r"[;&|`$(){}[\]<>!#\\]", "", text)

    def format_alert_message(self, alert: Dict[str, Any]) -> str:
        """Format alert for Telegram with configurable command buttons."""
        severity_emoji = {"critical": "🚨", "warning": "⚠️", "info": "ℹ️"}

        emoji = severity_emoji.get(alert.get("severity", "info"), "📢")
        severity = alert.get("severity", "info").upper()

        # Format equipment type nicely (e.g., "fcu" → "FCU", "daylight_sensor" → "Daylight Sensor")
        eq_type = alert.get("equipment_type", "equipment")
        eq_type_display = eq_type.upper() if len(eq_type) <= 4 else eq_type.replace("_", " ").title()

        equipment_code = alert.get("equipment_code", "")
        # Replace dashes with underscores for Telegram command compatibility
        # Telegram commands end at hyphens, so FCU-L12-03 becomes FCU only
        command_code = equipment_code.replace("-", "_")

        # Build dynamic command section from settings
        settings = _load_notification_settings()
        alert_commands = settings.get("alertCommands", DEFAULT_ALERT_COMMANDS)

        # Map command keys to their Telegram command format
        command_map = {
            "reset": f"/reset_{command_code}",
            "info": f"/info_{command_code}",
            "note": f"/note_{command_code}",
            "wo": f"/WO_{command_code}",
            "inspect": f"/inspect_{command_code}",
        }

        commands_section = ""
        enabled_commands = []

        # Alert messages show all commands: info first (FM needs context), then actions
        alert_command_order = [
            ("info", "More info"),
            ("reset", "Remote reset"),
            ("inspect", "Send technician"),
            ("wo", "Raise work order"),
            ("note", "Add note"),
        ]

        for key, default_label in alert_command_order:
            cmd_config = alert_commands.get(key, {})
            if cmd_config.get("enabled", True):
                label = cmd_config.get("label", default_label)
                enabled_commands.append(f"{command_map[key]} - {label}")

        if enabled_commands:
            commands_section = "\n━━━━━━━━━━━━━━━━━━\n" + "\n".join(enabled_commands)

        message = f"""{emoji} {severity} ALERT - {alert.get("site_name", "Building")}

🏢 Zone: {alert.get("zone_name", "Unknown")}
🔧 Equipment: {alert.get("equipment_name", "Unknown")}
📋 Type: {eq_type_display}
🆔 Code: {equipment_code}

📝 {alert.get("message", "")}

⏰ Time: {datetime.now().strftime("%H:%M:%S")}{commands_section}"""

        return message

    async def send_alert(self, alert: Dict[str, Any]) -> bool:
        """Send alert to FM team via sentry CLI (async wrapper)."""
        return self.send_alert_sync(alert)

    @staticmethod
    def _title_from_alert(alert: Dict[str, Any]) -> str:
        severity = str(alert.get("severity", "info")).upper()
        equipment_code = alert.get("equipment_code", "UNKNOWN")
        return f"{severity} ALERT - {equipment_code}"

    def _log_delivery(
        self,
        *,
        alert: Dict[str, Any],
        message: str,
        status: NotificationStatus,
        error_code: str | None = None,
        error_message: str | None = None,
        provider_response: Dict[str, Any] | None = None,
    ) -> None:
        """Persist alert send attempt into notification delivery log."""
        delivery_log = NotificationDeliveryLog(
            id=uuid4(),
            technician_id=SYSTEM_NOTIFIER_TECHNICIAN_ID,
            notification_type="alert",
            title=self._title_from_alert(alert),
            body=message,
            channel_type=ChannelType.TELEGRAM,
            recipient_identifier=self.fm_chat_id or "UNCONFIGURED",
            status=status,
            error_code=error_code,
            error_message=error_message,
            provider="sentry",
            provider_response=provider_response or {},
            sent_at=datetime.utcnow() if status == NotificationStatus.SENT else None,
        )

        coro = self._notification_repo.create_delivery_log(delivery_log)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            try:
                asyncio.run(coro)
            except Exception as exc:
                logger.warning("Failed to write alert delivery log: %s", exc)
            return

        loop.create_task(coro)

    def _has_delivery_target(self) -> bool:
        if self.fm_chat_id:
            return True
        if settings.is_live_mode:
            logger.error("SENTRY_FM_CHAT_ID is missing in live mode; alert notification is blocked")
        else:
            logger.warning("SENTRY_FM_CHAT_ID is not configured; skipping FM Telegram alert")
        return False

    def _should_send_alert(self, alert: Dict[str, Any]) -> bool:
        """Check if alert should be sent (cooldown/dedup check).

        Allows immediate send if:
        - First alert for this equipment
        - Cooldown period has passed
        - Severity escalated (e.g., warning → critical)
        """
        equipment_code = alert.get("equipment_code", alert.get("equipment_id", "unknown"))
        severity = alert.get("severity", "info")

        # Severity ranking for escalation detection
        severity_rank = {"info": 1, "warning": 2, "critical": 3}
        current_rank = severity_rank.get(severity, 0)

        # Check if this is an escalation from a previous alert
        equipment_key_prefix = f"{equipment_code}:"
        previous_max_rank = 0
        for key in self._last_alerts.keys():
            if key.startswith(equipment_key_prefix):
                prev_severity = key.split(":")[1]
                prev_rank = severity_rank.get(prev_severity, 0)
                previous_max_rank = max(previous_max_rank, prev_rank)

        # Allow immediate send if severity escalated
        if current_rank > previous_max_rank and previous_max_rank > 0:
            logger.info("Severity escalation for %s: sending %s alert immediately", equipment_code, severity)
            self._last_alerts[f"{equipment_code}:{severity}"] = datetime.now()
            return True

        # Standard cooldown check
        alert_key = f"{equipment_code}:{severity}"
        now = datetime.now()
        last_sent = self._last_alerts.get(alert_key)

        if last_sent:
            elapsed = now - last_sent
            if elapsed < timedelta(minutes=self.ALERT_COOLDOWN_MINUTES):
                remaining = self.ALERT_COOLDOWN_MINUTES - (elapsed.total_seconds() / 60)
                logger.info(
                    "Alert throttled for %s (%s): %.1fmin cooldown remaining",
                    equipment_code,
                    severity,
                    remaining,
                )
                return False

        # Update last alert time
        self._last_alerts[alert_key] = now
        return True

    def _is_notifications_module_active(self) -> bool:
        """Check if the notifications module is active for the site."""
        try:
            from app.services.module_registry_service import ModuleRegistryService

            registry = ModuleRegistryService()
            # Check all configured sites for an active notifications module
            for site_id in registry._site_configs:
                if registry.is_module_active(site_id, "notifications"):
                    return True
            return False
        except Exception:
            # Fail closed in live modes so an unavailable registry cannot bypass controls.
            if settings.is_live_mode:
                logger.error("Module registry unavailable in live mode; blocking Sentry notifications")
                return False
            return True

    def send_alert_sync(self, alert: Dict[str, Any]) -> bool:
        """Send alert via sentry CLI.

        Phase 58-04 H-5: Message is sanitised before passing to subprocess
        and arguments are always passed as a list (never shell=True).
        """
        # Check if notifications module is active
        if not self._is_notifications_module_active():
            return False  # Notifications module not active for this site

        if not self._has_delivery_target():
            self._log_delivery(
                alert=alert,
                message=self.format_alert_message(alert),
                status=NotificationStatus.FAILED,
                error_code="missing_target",
                error_message="SENTRY_FM_CHAT_ID is not configured",
            )
            return False

        # Check cooldown before sending
        if not self._should_send_alert(alert):
            return False  # Throttled, but not an error

        message = self.format_alert_message(alert)
        # Sanitize message to strip shell metacharacters (defence in depth)
        sanitized_message = self._sanitize_for_shell(message)
        # Sanitize the chat ID as well (should be numeric, but be safe)
        sanitized_target = self._sanitize_for_shell(self.fm_chat_id)

        try:
            result = subprocess.run(
                [
                    self._cli_command,
                    "message",
                    "send",
                    "--channel",
                    "telegram",
                    "--target",
                    sanitized_target,
                    "--message",
                    sanitized_message,
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                self._log_delivery(
                    alert=alert,
                    message=message,
                    status=NotificationStatus.SENT,
                    provider_response={"stdout": result.stdout},
                )
                logger.info("Alert sent via sentry: %s", alert.get("id", "")[:8])
                return True
            else:
                self._log_delivery(
                    alert=alert,
                    message=message,
                    status=NotificationStatus.FAILED,
                    error_code="send_failed",
                    error_message=result.stderr or "Unknown sentry CLI error",
                    provider_response={"stderr": result.stderr},
                )
                logger.error("sentry CLI error: %s", result.stderr)
                return False

        except subprocess.TimeoutExpired:
            self._log_delivery(
                alert=alert,
                message=message,
                status=NotificationStatus.FAILED,
                error_code="timeout",
                error_message="sentry request timed out after 30 seconds",
            )
            logger.error("sentry CLI timeout")
            return False
        except FileNotFoundError:
            self._log_delivery(
                alert=alert,
                message=message,
                status=NotificationStatus.FAILED,
                error_code="not_found",
                error_message=f"{self._cli_command} CLI not found in PATH",
            )
            logger.error("%s not found in PATH", self._cli_command)
            return False
        except Exception as e:
            self._log_delivery(
                alert=alert,
                message=message,
                status=NotificationStatus.FAILED,
                error_code="exception",
                error_message=str(e),
            )
            logger.error("Failed to send alert: %s", e)
            return False


# Singleton instance
alert_notifier = AlertNotifier()
