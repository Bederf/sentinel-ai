"""Notification configuration for escalation alerts.

Configure email settings, Slack webhooks, and notification thresholds
for the escalation system.
"""

import os
from typing import Dict, Any, List

# Email Configuration
EMAIL_CONFIG = {
    "host": os.getenv("SMTP_HOST", "smtp.gmail.com"),
    "port": int(os.getenv("SMTP_PORT", "587")),
    "username": os.getenv("SMTP_USERNAME", "sentinel@facility.com"),
    "password": os.getenv("SMTP_PASSWORD", ""),  # Use environment variable for security
    "use_tls": os.getenv("SMTP_USE_TLS", "true").lower() == "true",
    "from_email": os.getenv("FROM_EMAIL", "sentinel@facility.com"),
    "from_name": os.getenv("FROM_NAME", "SENTINEL BMS"),
}

# Email Recipients - Update these for your facility
EMAIL_RECIPIENTS = [
    "facility.operator@company.com",
    "facilities.manager@company.com",
    # Add more recipients as needed
]

# Slack Configuration
SLACK_CONFIG = {
    "webhooks": {
        "critical": os.getenv("SLACK_CRITICAL_WEBHOOK", ""),
        "emergency": os.getenv("SLACK_EMERGENCY_WEBHOOK", ""),
    },
    "channel": os.getenv("SLACK_CHANNEL", "#facilities-alerts"),
    "username": os.getenv("SLACK_USERNAME", "SENTINEL"),
    "icon_emoji": os.getenv("SLACK_ICON", ":rotating_light:"),
}

# SMS Configuration (optional - requires third-party service)
SMS_CONFIG = {
    "enabled": os.getenv("SMS_ENABLED", "false").lower() == "true",
    "provider": os.getenv("SMS_PROVIDER", "twilio"),  # twilio, aws-sns, etc.
    "from_number": os.getenv("SMS_FROM_NUMBER", ""),
    "recipients": [
        # Add phone numbers in E.164 format: +1234567890
    ],
}

# Emergency Contacts
EMERGENCY_CONTACTS = [
    {
        "name": "Facilities Manager",
        "phone": "+1234567890",
        "email": "facilities.manager@company.com",
        "sms_enabled": True,
    },
    {
        "name": "Building Operator",
        "phone": "+1234567891",
        "email": "operator@company.com",
        "sms_enabled": True,
    },
]

# Notification Templates
NOTIFICATION_TEMPLATES = {
    "escalation_alert": {
        "subject": "[SENTINEL] {level} Alert - {device_name}",
        "body": """
SENTINEL Building Management System - Escalation Alert
{'='*50}

Severity: {level}
Device: {device_name} ({device_id})
Point: {point_name}
Current Value: {current_value}

Boundaries:
  Minimum: {boundary_min}
  Maximum: {boundary_max}
  Approach: {approach_percentage:.1f}%

Warnings:
{warnings}

Event ID: {event_id}
Timestamp: {timestamp}

Please review and take appropriate action.

---
This is an automated alert from the SENTINEL Autonomous Building Management System.
        """.strip(),
    },
    "emergency_stop": {
        "subject": "[SENTINEL] EMERGENCY STOP ACTIVATED",
        "body": """
⚠️ EMERGENCY STOP ACTIVATED ⚠️

The SENTINEL autonomous system has been stopped due to an emergency condition.

Details:
{details}

All autonomous operations have been halted.
Devices have been restored to safe operating states.

This requires immediate attention.

---
SENTINEL Building Management System
        """.strip(),
    },
}

# Escalation Thresholds (in percentage of boundary approach)
ESCALATION_THRESHOLDS = {
    "warning": 75,    # 75% approach - Just log
    "alert": 85,      # 85% approach - Email notification
    "critical": 95,   # 95% approach - Slack + Dashboard + SMS
    "emergency": 100, # 100% approach - Stop autonomous + All channels
}

# Notification Cooldown (minimum time between notifications of same type)
NOTIFICATION_COOLDOWN_MINUTES = {
    "warning": 5,    # 5 minutes
    "alert": 10,     # 10 minutes
    "critical": 1,   # 1 minute (immediate for critical)
    "emergency": 0,  # No cooldown for emergencies
}

# Rate Limiting
RATE_LIMITS = {
    "email": {
        "max_per_hour": 10,  # Max 10 emails per hour
        "burst": 2,          # Allow short bursts
    },
    "slack": {
        "max_per_minute": 5, # Max 5 Slack messages per minute
        "burst": 1,
    },
    "sms": {
        "max_per_day": 5,    # Max 5 SMS per day (cost management)
        "burst": 1,
    },
}

def get_notification_config() -> Dict[str, Any]:
    """Get complete notification configuration."""
    return {
        "email": {
            **EMAIL_CONFIG,
            "recipients": EMAIL_RECIPIENTS,
        },
        "slack": SLACK_CONFIG,
        "sms": SMS_CONFIG,
        "emergency_contacts": EMERGENCY_CONTACTS,
        "thresholds": ESCALATION_THRESHOLDS,
        "cooldown_minutes": NOTIFICATION_COOLDOWN_MINUTES,
        "rate_limits": RATE_LIMITS,
        "enabled": {
            "email": len(EMAIL_RECIPIENTS) > 0 and bool(EMAIL_CONFIG["password"]),
            "slack": bool(SLACK_CONFIG["webhooks"]["critical"]),
            "sms": SMS_CONFIG["enabled"] and len(SMS_CONFIG["recipients"]) > 0,
        }
    }
