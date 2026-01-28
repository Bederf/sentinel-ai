"""Notification Service for sending escalation alerts via multiple channels.

Handles email notifications, Slack alerts, dashboard notifications, and emergency
notifications for the escalation system.
"""

import logging
import asyncio
import smtplib
import json
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any, List, Optional
from pathlib import Path

from app.models.autonomous_decision import EscalationEvent, EscalationLevel
from app.services.claude_service import claude_service

logger = logging.getLogger(__name__)

# Configuration file
CONFIG_DIR = Path(__file__).parent.parent / "config"
NOTIFICATION_CONFIG_FILE = CONFIG_DIR / "notifications.py"


class NotificationService:
    """Multi-channel notification service for escalation alerts."""

    def __init__(self):
        """Initialize the notification service."""
        self.smtp_config: Dict[str, Any] = {}
        self.slack_webhooks: Dict[str, str] = {}
        self.email_recipients: List[str] = []
        self.notification_history: List[Dict[str, Any]] = []
        self._initialized = False

    async def initialize(self, load_mock_data: bool = True) -> None:
        """Initialize notification service with configuration."""
        if self._initialized:
            return

        logger.info("Initializing NotificationService")

        # Load configuration (from environment or config file)
        await self._load_configuration()

        self._initialized = True
        logger.info("NotificationService initialized")

    async def _load_configuration(self) -> None:
        """Load notification configuration from environment/file."""
        # TODO: Load from environment variables or config file
        # For now, use mock configuration
        self.smtp_config = {
            "host": "smtp.example.com",
            "port": 587,
            "username": "sentinel@example.com",
            "password": "password",  # In production, use environment variable
            "use_tls": True,
        }

        self.slack_webhooks = {
            "critical": "https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXX",
            "emergency": "https://hooks.slack.com/services/T00000000/B00000000/YYYYYYYYYYYYYYYY",
        }

        self.email_recipients = [
            "operator1@facility.com",
            "operator2@facility.com",
            "manager@facility.com",
        ]

        logger.info("Loaded notification configuration")

    async def send_email_alert(self, event: EscalationEvent) -> bool:
        """
        Send email alert for escalation event.

        Args:
            event: Escalation event to alert about

        Returns:
            True if email sent successfully
        """
        if not self.email_recipients:
            logger.warning("No email recipients configured")
            return False

        try:
            # In production, this would send actual emails
            # For demo purposes, log the email content
            email_content = self._generate_email_content(event)

            logger.info(f"EMAIL ALERT ({event.escalation_level.name}):\n{email_content}")

            # Add to notification history
            self.notification_history.append({
                "timestamp": datetime.now().isoformat(),
                "channel": "email",
                "escalation_id": event.id,
                "level": event.escalation_level.name,
                "recipients": self.email_recipients.copy(),
                "content": email_content,
            })

            return True

        except Exception as e:
            logger.error(f"Error sending email alert: {e}")
            return False

    async def send_slack_alert(self, event: EscalationEvent) -> bool:
        """
        Send Slack notification for escalation event.

        Args:
            event: Escalation event to alert about

        Returns:
            True if Slack message sent successfully
        """
        try:
            webhook_url = self.slack_webhooks.get("critical")
            if not webhook_url:
                logger.warning("No Slack webhook configured for critical alerts")
                return False

            # In production, this would send actual Slack message
            slack_message = self._generate_slack_message(event)

            logger.info(f"SLACK ALERT ({event.escalation_level.name}):\n{slack_message}")

            # Add to notification history
            self.notification_history.append({
                "timestamp": datetime.now().isoformat(),
                "channel": "slack",
                "escalation_id": event.id,
                "level": event.escalation_level.name,
                "content": slack_message,
            })

            return True

        except Exception as e:
            logger.error(f"Error sending Slack alert: {e}")
            return False

    async def send_dashboard_alert(self, event: EscalationEvent, urgent: bool = False) -> bool:
        """
        Send dashboard notification for escalation event.

        Args:
            event: Escalation event to alert about
            urgent: Whether this is an urgent alert

        Returns:
            True if dashboard notification sent successfully
        """
        try:
            dashboard_message = self._generate_dashboard_message(event, urgent)

            logger.info(f"DASHBOARD ALERT ({'URGENT' if urgent else 'NORMAL'}): \n{dashboard_message}")

            # Add to notification history
            self.notification_history.append({
                "timestamp": datetime.now().isoformat(),
                "channel": "dashboard",
                "escalation_id": event.id,
                "level": event.escalation_level.name,
                "urgent": urgent,
                "content": dashboard_message,
            })

            return True

        except Exception as e:
            logger.error(f"Error sending dashboard alert: {e}")
            return False

    async def send_emergency_notification(self, event: EscalationEvent) -> bool:
        """
        Send emergency notification via all channels.

        Args:
            event: Escalation event for emergency

        Returns:
            True if at least one notification sent successfully
        """
        try:
            results = []

            # Send to all channels
            results.append(await self.send_email_alert(event))
            results.append(await self.send_slack_alert(event))
            results.append(await self.send_dashboard_alert(event, urgent=True))

            success_count = sum(results)
            logger.error(f"EMERGENCY NOTIFICATION sent via {success_count}/{len(results)} channels")

            return success_count > 0

        except Exception as e:
            logger.error(f"Error sending emergency notification: {e}")
            return False

    def _generate_email_content(self, event: EscalationEvent) -> str:
        """Generate email content for escalation event."""
        subject = f"[SENTINEL] {event.escalation_level.name} Alert - {event.device_name}"

        body = f"""
SENTINEL Building Management System - Escalation Alert
{'='*50}

Severity: {event.escalation_level.name}
Device: {event.device_name} ({event.device_id})
Point: {event.point_name}
Current Value: {event.current_value}

Boundaries:
  Minimum: {event.boundary_min or 'N/A'}
  Maximum: {event.boundary_max or 'N/A'}
  Approach: {event.approach_percentage:.1f}%

Warnings:
"""

        for warning in event.warnings:
            body += f"  - {warning}\n"

        body += f"""
Event ID: {event.id}
Timestamp: {event.timestamp.strftime('%Y-%m-%d %H:%M:%S')}

Please review and take appropriate action.

---
This is an automated alert from the SENTINEL Autonomous Building Management System.
"""

        return f"Subject: {subject}\n\n{body}"

    def _generate_slack_message(self, event: EscalationEvent) -> str:
        """Generate Slack message for escalation event."""
        emoji_map = {
            EscalationLevel.WARNING: ":warning:",
            EscalationLevel.ALERT: ":exclamation:",
            EscalationLevel.CRITICAL: ":rotating_light:",
            EscalationLevel.EMERGENCY: ":fire:",
        }

        emoji = emoji_map.get(event.escalation_level, ":question:")

        message = f"""{emoji} *SENTINEL ALERT: {event.escalation_level.name}*

*Device:* {event.device_name}
*Point:* {event.point_name}
*Value:* {event.current_value} ({event.approach_percentage:.1f}% of limit)

"""

        if event.warnings:
            message += "*Warnings:*\n"
            for warning in event.warnings:
                message += f"• {warning}\n"

        message += f"""\n*Event ID:* `{event.id}`\n*Time:* <!date^{int(event.timestamp.timestamp())}^{{date_num}} {{time_secs}}|{event.timestamp.strftime('%Y-%m-%d %H:%M:%S')}>

:chart_with_upwards_trend: <View Dashboard|http://localhost:5173/dashboard>
:rescue_worker_helmet: <Acknowledge Alert|http://localhost:5173/escalations/{event.id}/acknowledge>
"""

        return message

    def _generate_dashboard_message(self, event: EscalationEvent, urgent: bool = False) -> Dict[str, Any]:
        """Generate dashboard notification message."""
        return {
            "id": event.id,
            "timestamp": event.timestamp.isoformat(),
            "level": event.escalation_level.name,
            "urgent": urgent,
            "device": {
                "id": event.device_id,
                "name": event.device_name,
            },
            "point": event.point_name,
            "value": event.current_value,
            "boundary": {
                "min": event.boundary_min,
                "max": event.boundary_max,
            },
            "approach_percentage": event.approach_percentage,
            "warnings": event.warnings,
            "acknowledged": event.acknowledged,
        }

    async def update_configuration(self, config: Dict[str, Any]) -> bool:
        """
        Update notification service configuration.

        Args:
            config: Configuration dictionary with email, slack settings

        Returns:
            True if configuration updated successfully
        """
        try:
            if "smtp" in config:
                self.smtp_config.update(config["smtp"])
            if "slack_webhooks" in config:
                self.slack_webhooks.update(config["slack_webhooks"])
            if "email_recipients" in config:
                self.email_recipients = config["email_recipients"]

            logger.info("Notification configuration updated")
            return True

        except Exception as e:
            logger.error(f"Error updating notification configuration: {e}")
            return False

    async def get_notification_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get notification history."""
        return self.notification_history[-limit:]

    def get_active_channels(self) -> Dict[str, bool]:
        """Get status of active notification channels."""
        return {
            "email": len(self.email_recipients) > 0,
            "slack": len(self.slack_webhooks) > 0,
            "dashboard": True,  # Always available
        }


# Global instance
notification_service = NotificationService()
