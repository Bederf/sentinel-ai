"""Alert notification service for Sentry Telegram bot.

Sends BMS alerts to facility managers via Telegram using sentrybot CLI.
"""

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Dict, Any
from datetime import datetime, timedelta

# Default alert commands when settings not configured
DEFAULT_ALERT_COMMANDS = {
    "reset": {"enabled": True, "label": "Remote reset"},
    "info": {"enabled": True, "label": "More info"},
    "note": {"enabled": True, "label": "Add note"},
    "wo": {"enabled": True, "label": "Create work order"},
}

# Settings file path
SETTINGS_FILE = Path(__file__).parent.parent.parent / "data" / "settings.json"


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
    """Send BMS alerts via sentrybot CLI."""

    def __init__(self):
        # Chat ID for FM team (your Telegram user ID)
        self.fm_chat_id = os.getenv("SENTRY_FM_CHAT_ID", "8359288792")
        # Track last alert time per equipment+severity to prevent spam
        self._last_alerts: Dict[str, datetime] = {}

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
        return re.sub(r'[;&|`$(){}[\]<>!#\\]', '', text)

    def format_alert_message(self, alert: Dict[str, Any]) -> str:
        """Format alert for Telegram with configurable command buttons."""
        severity_emoji = {
            "critical": "🚨",
            "warning": "⚠️",
            "info": "ℹ️"
        }

        emoji = severity_emoji.get(alert.get("severity", "info"), "📢")
        severity = alert.get("severity", "info").upper()

        # Format equipment type nicely (e.g., "fcu" → "FCU", "daylight_sensor" → "Daylight Sensor")
        eq_type = alert.get('equipment_type', 'equipment')
        eq_type_display = eq_type.upper() if len(eq_type) <= 4 else eq_type.replace('_', ' ').title()

        equipment_code = alert.get('equipment_code', '')
        # Replace dashes with underscores for Telegram command compatibility
        # Telegram commands end at hyphens, so FCU-L12-03 becomes FCU only
        command_code = equipment_code.replace('-', '_')

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

        # For warning/critical alerts, add inspection command at the top
        if alert.get("severity", "info").lower() in ["warning", "critical"]:
            enabled_commands.append(f"{command_map['inspect']} - Create Inspection Work Order")

        for key in ["reset", "info", "note", "wo"]:
            cmd_config = alert_commands.get(key, {})
            if cmd_config.get("enabled", True):
                label = cmd_config.get("label", key.title())
                enabled_commands.append(f"{command_map[key]} - {label}")

        if enabled_commands:
            commands_section = "\n━━━━━━━━━━━━━━━━━━\n" + "\n".join(enabled_commands)

        message = f"""{emoji} {severity} ALERT - {alert.get('building_name', 'Building')}

🏢 Zone: {alert.get('zone_name', 'Unknown')}
🔧 Equipment: {alert.get('equipment_name', 'Unknown')}
📋 Type: {eq_type_display}
🆔 Code: {equipment_code}

📝 {alert.get('message', '')}

⏰ Time: {datetime.now().strftime('%H:%M:%S')}{commands_section}"""

        return message

    async def send_alert(self, alert: Dict[str, Any]) -> bool:
        """Send alert to FM team via sentrybot (async wrapper)."""
        return self.send_alert_sync(alert)

    def _should_send_alert(self, alert: Dict[str, Any]) -> bool:
        """Check if alert should be sent (cooldown/dedup check).

        Allows immediate send if:
        - First alert for this equipment
        - Cooldown period has passed
        - Severity escalated (e.g., warning → critical)
        """
        equipment_code = alert.get('equipment_code', alert.get('equipment_id', 'unknown'))
        severity = alert.get('severity', 'info')

        # Severity ranking for escalation detection
        severity_rank = {'info': 1, 'warning': 2, 'critical': 3}
        current_rank = severity_rank.get(severity, 0)

        # Check if this is an escalation from a previous alert
        equipment_key_prefix = f"{equipment_code}:"
        previous_max_rank = 0
        for key in self._last_alerts.keys():
            if key.startswith(equipment_key_prefix):
                prev_severity = key.split(':')[1]
                prev_rank = severity_rank.get(prev_severity, 0)
                previous_max_rank = max(previous_max_rank, prev_rank)

        # Allow immediate send if severity escalated
        if current_rank > previous_max_rank and previous_max_rank > 0:
            print(f"🔺 Severity escalation for {equipment_code}: sending {severity} alert immediately")
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
                print(f"⏳ Alert throttled for {equipment_code} ({severity}) - {remaining:.1f}min cooldown remaining")
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
            # If module registry unavailable, default to sending (fail-open)
            return True

    def send_alert_sync(self, alert: Dict[str, Any]) -> bool:
        """Send alert via sentrybot CLI.

        Phase 58-04 H-5: Message is sanitised before passing to subprocess
        and arguments are always passed as a list (never shell=True).
        """
        # Check if notifications module is active
        if not self._is_notifications_module_active():
            return False  # Notifications module not active for this site

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
                    "sentrybot", "message", "send",
                    "--channel", "telegram",
                    "--target", sanitized_target,
                    "--message", sanitized_message,
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                print(f"✅ Alert sent via sentrybot: {alert.get('id', '')[:8]}")
                return True
            else:
                print(f"❌ sentrybot error: {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            print("❌ sentrybot timeout")
            return False
        except FileNotFoundError:
            print("❌ sentrybot not found in PATH")
            return False
        except Exception as e:
            print(f"❌ Failed to send alert: {e}")
            return False


# Singleton instance
alert_notifier = AlertNotifier()
