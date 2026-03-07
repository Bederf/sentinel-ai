"""Parser for Desigo BMS fault notification emails.

Converts raw email subject/body from noreply@fnb.co.za into structured
DesigoBuildingAlarm objects with severity classification and equipment
category enrichment.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime

from app.plant.models import AlarmSeverity, DesigoBuildingAlarm

logger = logging.getLogger(__name__)

# Equipment category mapping — case-insensitive substring match.
# Order matters: first match wins, so more specific patterns come first.
EQUIPMENT_CATEGORIES: dict[str, str] = {
    "fire damper": "fire_safety",
    "fd ": "fire_safety",
    "generator": "power",
    "gen ": "power",
    "ats": "power",
    "ups": "power",
    "ahu": "hvac",
    "fcu": "hvac",
    "fpu": "hvac",
    "fan": "hvac",
    "reheat": "hvac",
    "ohs": "hvac",
    "chiller": "hvac",
    "pump": "mechanical",
    "temperature": "monitoring",
    "humidity": "monitoring",
}

# Subject regex: equipment_description  alarm_type  (status)
_SUBJECT_RE = re.compile(r"^(.+?)\s+([\w\s]+?)\s+\((\w+)\)$")


def parse_desigo_email(
    subject: str,
    body: str,
    received_at: datetime | None = None,
    site_id: str = "FLN02",
) -> DesigoBuildingAlarm:
    """Parse a Desigo fault notification email into a structured alarm.

    Args:
        subject: Email subject line.
        body: Email body text.
        received_at: When the email was received. Defaults to now.
        site_id: Site identifier. Defaults to "FLN02".

    Returns:
        A DesigoBuildingAlarm with classified severity and equipment category.
    """
    if received_at is None:
        received_at = datetime.utcnow()

    # --- Extract fields from subject ---
    match = _SUBJECT_RE.match(subject.strip())
    if match:
        equipment_description = match.group(1).strip()
        alarm_type = match.group(2).strip()
        status = match.group(3).strip()
    else:
        # No parentheses — treat entire subject as description
        logger.warning("Subject missing parentheses, status unknown: %s", subject)
        equipment_description = subject.strip()
        alarm_type = ""
        status = "Unknown"

    # --- Extract severity word from body line 3 ---
    severity_word = _extract_severity_word(body)

    # --- Classify ---
    category = _detect_equipment_category(equipment_description)
    severity = _classify_severity(alarm_type, status, severity_word, category)

    # Set cleared flag based on severity
    cleared = severity == AlarmSeverity.CLEARED

    return DesigoBuildingAlarm(
        id=str(uuid.uuid4()),
        site_id=site_id,
        raw_subject=subject,
        raw_body=body,
        equipment_description=equipment_description,
        alarm_type=alarm_type,
        status=status,
        severity=severity,
        equipment_category=category,
        received_at=received_at,
        cleared=cleared,
        cleared_at=received_at if cleared else None,
    )


def _extract_severity_word(body: str) -> str:
    """Extract the severity word from body line 3 (last word).

    Returns empty string if body is empty or line 3 doesn't exist.
    """
    if not body or not body.strip():
        return ""

    lines = body.strip().splitlines()
    # Body line 3 (index 2) contains the alarm detail with severity as last word
    if len(lines) >= 3:
        line3 = lines[2].strip()
        if line3:
            return line3.split()[-1]

    # Fallback: try last non-empty line
    for line in reversed(lines):
        stripped = line.strip()
        if stripped:
            return stripped.split()[-1]

    return ""


def _classify_severity(
    alarm_type: str,
    status: str,
    severity_word: str,
    category: str,
) -> AlarmSeverity:
    """Classify alarm severity per Desigo rules.

    Rules (evaluated in order):
    1. cleared: status == "Normal" AND alarm_type contains "Fail"/"Fault"
    2. very_critical: category == "fire_safety" AND severity_word == "High"
    3. critical: severity_word == "High"
    4. non_critical: everything else

    Empty body (no severity_word) defaults to CRITICAL as a safe fallback.
    """
    alarm_type_lower = alarm_type.lower()

    # Rule 1: cleared
    if status == "Normal" and ("fail" in alarm_type_lower or "fault" in alarm_type_lower):
        return AlarmSeverity.CLEARED

    # Empty body → safe default
    if not severity_word:
        return AlarmSeverity.CRITICAL

    severity_upper = severity_word.capitalize()

    # Rule 2: fire_safety + High → very_critical
    if category == "fire_safety" and severity_upper == "High":
        return AlarmSeverity.VERY_CRITICAL

    # Rule 3: High → critical
    if severity_upper == "High":
        return AlarmSeverity.CRITICAL

    # Rule 4: everything else
    return AlarmSeverity.NON_CRITICAL


def _detect_equipment_category(description: str) -> str:
    """Detect equipment category from description via case-insensitive substring match.

    Returns:
        Category string or "unknown" if no match found.
    """
    desc_lower = description.lower()
    for pattern, category in EQUIPMENT_CATEGORIES.items():
        if pattern in desc_lower:
            return category
    return "unknown"
