"""
Channel-Specific Response Formatters
======================================
Formats complaint diagnosis results for different channels.

Each formatter takes a ComplaintDiagnosis + optional history summary
and returns a string formatted for the target channel.
"""

from typing import Optional

from app.models.complaint import ComplaintDiagnosis


def _temp_delta_str(current: float, setpoint: float) -> str:
    """Format temperature delta as human-readable string."""
    delta = current - setpoint
    if abs(delta) < 0.1:
        return "at setpoint"
    sign = "+" if delta > 0 else ""
    return f"{sign}{delta:.1f}C {'above' if delta > 0 else 'below'}"


def _equipment_status_icon(status: str) -> str:
    """Return status icon for equipment."""
    if status == "fault":
        return "FAULT"
    elif status == "off":
        return "OFF"
    return "OK"


def format_for_chat(
    diagnosis: ComplaintDiagnosis,
    history: Optional[dict] = None,
) -> str:
    """
    Format diagnosis for Chat UI (markdown).

    Uses headers, code blocks, and bullet points.
    """
    desk = diagnosis.desk
    zone = diagnosis.zone
    delta = _temp_delta_str(zone.current_temp, zone.setpoint)

    lines = [
        f"## Desk {desk.desk_id} - {zone.zone_name or zone.zone_id}",
        "",
        f"**Floor:** {desk.floor} | **Zone:** {zone.zone_id}",
        "",
        "### Environment",
        f"- Temperature: {zone.current_temp}C (setpoint {zone.setpoint}C, {delta})",
        f"- FCU: `{zone.fcu_id}` [{_equipment_status_icon(zone.status)}]",
    ]

    if zone.vav_id:
        lines.append(f"- VAV: `{zone.vav_id}`")

    if desk.near_window:
        orient = f" ({desk.orientation}-facing)" if desk.orientation else ""
        lines.append(f"- Near window{orient}")

    # History context
    if history and history.get("count", 0) > 0:
        lines.extend(
            [
                "",
                f"### Complaint History ({history['count']} in last 7 days)",
            ]
        )
        if history.get("escalation_recommended"):
            lines.append("**Escalation recommended** - recurring issue at this desk.")

    # Diagnosis
    lines.extend(
        [
            "",
            "### Diagnosis",
            f"**Root cause:** {diagnosis.root_cause}",
            f"**Confidence:** {diagnosis.confidence}",
            "",
            "### Suggested Actions",
        ]
    )

    for i, suggestion in enumerate(diagnosis.suggestions, 1):
        lines.append(f"{i}. {suggestion}")

    if diagnosis.needs_dispatch:
        lines.extend(
            [
                "",
                "> A technician dispatch is recommended for this issue.",
            ]
        )

    return "\n".join(lines)


def format_for_whatsapp(
    diagnosis: ComplaintDiagnosis,
    history: Optional[dict] = None,
) -> str:
    """
    Format diagnosis for WhatsApp.

    Uses bold text, emoji indicators, compact layout.
    WhatsApp markdown: *bold*, _italic_, ~strikethrough~
    """
    desk = diagnosis.desk
    zone = diagnosis.zone
    delta = zone.current_temp - zone.setpoint

    # Temperature emoji
    if delta > 1.5:
        temp_emoji = "\U0001f321\ufe0f"  # thermometer
    elif delta < -1.5:
        temp_emoji = "\u2744\ufe0f"  # snowflake
    else:
        temp_emoji = "\u2705"  # checkmark

    # Equipment status
    fcu_icon = "\u2705" if zone.status != "fault" else "\u274c"
    vav_icon = "\u2705" if zone.vav_id else ""

    lines = [
        f"{temp_emoji} *Desk {desk.desk_id}* \u2014 {zone.zone_name or zone.zone_id}",
        "",
        f"Current: {zone.current_temp}\u00b0C | Target: {zone.setpoint}\u00b0C | "
        f"*{'+' if delta > 0 else ''}{delta:.1f}\u00b0C {'above' if delta > 0 else 'below'}*",
        f"{zone.fcu_id} {fcu_icon}",
    ]

    if zone.vav_id:
        lines[-1] += f" | {zone.vav_id} {vav_icon}"

    # History
    if history and history.get("count", 0) > 0:
        lines.extend(
            [
                "",
                f"\u26a0\ufe0f {history['count']} similar complaint"
                f"{'s' if history['count'] > 1 else ''} this week at this desk.",
            ]
        )

    # Root cause
    lines.extend(
        [
            "",
            f"*Probable cause:* {diagnosis.root_cause}",
            "",
            "*Suggested actions:*",
        ]
    )

    for i, suggestion in enumerate(diagnosis.suggestions, 1):
        lines.append(f"{i}. {suggestion}")

    if diagnosis.needs_dispatch or (history and history.get("escalation_recommended")):
        lines.extend(
            [
                "",
                "Given repeat complaints, a work order may be warranted.",
                "Reply *WO* to create one.",
            ]
        )

    return "\n".join(lines)


def format_for_telegram(
    diagnosis: ComplaintDiagnosis,
    history: Optional[dict] = None,
) -> str:
    """
    Format diagnosis for Telegram (Sentry/Sentry bot).

    Uses Telegram markdown: *bold*, `code`, simple structure.
    Matches existing Sentry formatting patterns.
    """
    desk = diagnosis.desk
    zone = diagnosis.zone
    delta = zone.current_temp - zone.setpoint

    lines = [
        f"*Desk Comfort Report - {desk.desk_id}*",
        f"Zone: {zone.zone_name or zone.zone_id} | Floor: {desk.floor}",
        "",
        f"Temp: {zone.current_temp}C (setpoint {zone.setpoint}C, delta {delta:+.1f}C)",
        f"FCU: `{zone.fcu_id}` - {zone.status}",
    ]

    if zone.vav_id:
        lines.append(f"VAV: `{zone.vav_id}`")

    if history and history.get("count", 0) > 0:
        lines.append(f"\nHistory: {history['count']} complaints in 7 days")
        if history.get("escalation_recommended"):
            lines.append("*ESCALATION RECOMMENDED*")

    lines.extend(
        [
            "",
            f"Root cause: {diagnosis.root_cause}",
            f"Confidence: {diagnosis.confidence}",
            "",
            "Actions:",
        ]
    )

    for i, suggestion in enumerate(diagnosis.suggestions, 1):
        lines.append(f"  {i}. {suggestion}")

    if diagnosis.needs_dispatch:
        lines.append("\n*Technician dispatch recommended.*")

    return "\n".join(lines)
