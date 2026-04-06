"""
Channel-Specific Response Formatters
======================================
Formats complaint diagnosis results for different channels.

Each formatter takes a ComplaintDiagnosis + optional history summary
and returns a string formatted for the target channel.

Enhanced to parse structured diagnosis text from ZoneAssessmentService
and render equipment health tables, contextual factors, and control-gated suggestions.
"""

import re
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


def _health_bar(score: int) -> str:
    """ASCII health bar 0-100."""
    filled = round(score / 10)
    return f"[{'#' * filled}{'-' * (10 - filled)}] {score}%"


def _parse_diagnosis_text(diagnosis_text: str) -> dict:
    """
    Parse the structured diagnosis string from ZoneAssessmentService
    into a dict for rendering.

    Handles two formats:
    1. Structured (pipe-separated from ZoneAssessmentService):
       "Zone Z12-2A: 24.5°C (setpoint 22.0°C, +2.5C above). Status: running. | Equipment: ..."
    2. Free-text (backward-compatible fallback):
       "FCU running, 2.5C above setpoint"

    Returns:
        dict with keys: zone_temp, zone_setpoint, zone_status, zone_delta_str,
        equipment (list of {name, status, health, alerts, predictions}),
        vav (dict of {vav_id, damper, airflow, discharge, reheat}),
        outdoor_temp, outdoor_extreme,
        contextual_factors (list of strings),
        is_no_issues (bool)
    """
    result = {
        "zone_temp": None,
        "zone_setpoint": None,
        "zone_status": None,
        "zone_delta_str": "",
        "equipment": [],
        "vav": {},
        "outdoor_temp": None,
        "outdoor_extreme": False,
        "contextual_factors": [],
        "is_no_issues": False,
    }

    if not diagnosis_text:
        return result

    # No issues detection (check early)
    if "no issues detected" in diagnosis_text.lower() or "no issues found" in diagnosis_text.lower():
        result["is_no_issues"] = True

    # Check if structured (pipe-separated)
    if "|" in diagnosis_text:
        parts = [p.strip() for p in diagnosis_text.split("|")]

        # Part 0: Zone temperature + status
        zone_part = parts[0]
        # Use non-greedy approach: match the LAST temperature before "(setpoint"
        temp_candidates = re.findall(r"(\d+\.\d+)\s*°?C", zone_part)
        sp_candidates = re.findall(r"setpoint\s+(\d+\.\d+)", zone_part)
        status_match = re.search(r"Status:\s*(\w+)", zone_part)

        # Take the first temp candidate (zone temp, not delta) — skip delta values
        if temp_candidates:
            result["zone_temp"] = float(temp_candidates[0])
        if sp_candidates:
            result["zone_setpoint"] = float(sp_candidates[0])
        if status_match:
            result["zone_status"] = status_match.group(1)

        if result["zone_temp"] is not None and result["zone_setpoint"] is not None:
            delta = result["zone_temp"] - result["zone_setpoint"]
            if abs(delta) < 0.1:
                result["zone_delta_str"] = "at setpoint"
            else:
                sign = "+" if delta > 0 else ""
                result["zone_delta_str"] = f"{sign}{delta:.1f}C {'above' if delta > 0 else 'below'}"

        # Part 1: Equipment (if present)
        if len(parts) > 1 and "Equipment:" in parts[1]:
            eq_part = parts[1].replace("Equipment:", "").strip()
            eq_pattern = re.compile(r"([^:]+):\s*(\w+)\s*\((\d+)%\)([^;]*)?")
            for match in eq_pattern.finditer(eq_part):
                name = match.group(1).strip()
                status = match.group(2).strip()
                health = int(match.group(3))
                extra = match.group(4) or ""
                alerts = []
                predictions = []
                alert_m = re.search(r"(\d+)\s*alert", extra)
                pred_m = re.search(r"(\d+)\s*prediction", extra)
                if alert_m:
                    alerts = [None] * int(alert_m.group(1))
                if pred_m:
                    predictions = [None] * int(pred_m.group(1))
                result["equipment"].append({
                    "name": name,
                    "status": status,
                    "health": health,
                    "alerts": alerts,
                    "predictions": predictions,
                })

        # Part 2: VAV readings (if present)
        if len(parts) > 2 and "VAV" in parts[2]:
            vav_part = parts[2]
            vav_id_m = re.search(r"VAV\s+([^\s:]+)", vav_part)
            damper_m = re.search(r"damper\s*(\d+\.?\d*)%", vav_part)
            airflow_m = re.search(r"airflow\s*(\d+\.?\d*)\s*L/s", vav_part)
            discharge_m = re.search(r"discharge\s*(\d+\.?\d*)\s*°?C", vav_part)
            reheat_m = re.search(r"reheat\s*(\d+\.?\d*)%", vav_part)

            if vav_id_m:
                result["vav"]["vav_id"] = vav_id_m.group(1)
            if damper_m:
                result["vav"]["damper"] = float(damper_m.group(1))
            if airflow_m:
                result["vav"]["airflow"] = float(airflow_m.group(1))
            if discharge_m:
                result["vav"]["discharge"] = float(discharge_m.group(1))
            if reheat_m:
                result["vav"]["reheat"] = float(reheat_m.group(1))

        # Part 3+: Outdoor temp and contextual factors
        remaining = "|".join(parts[3:])

        outdoor_m = re.search(r"Outdoor temp:\s*(\d+\.?\d*)\s*°?C", remaining)
        if outdoor_m:
            result["outdoor_temp"] = float(outdoor_m.group(1))
            result["outdoor_extreme"] = "(extreme heat)" in remaining or "(extreme cold)" in remaining

        # Contextual factors
        solar_map = {
            "morning_sun": "Morning sun (east-facing windows) heating area",
            "afternoon_sun": "Afternoon sun (west-facing windows) heating area",
            "north_facing": "Direct sunlight (north-facing) — HVAC unable to fully offset",
        }
        for key, label in solar_map.items():
            if key.lower() in remaining.lower():
                result["contextual_factors"].append(label)

        if "Low zone occupancy" in remaining:
            occ_m = re.search(r"Low zone occupancy \((\d+)%\)", remaining)
            result["contextual_factors"].append(
                f"Low zone occupancy ({occ_m.group(1)}%)" if occ_m else "Low zone occupancy"
            )

        if "High lighting heat load" in remaining:
            light_m = re.search(r"High lighting heat load \((\d+)%\)", remaining)
            result["contextual_factors"].append(
                f"High lighting heat load ({light_m.group(1)}%)" if light_m else "High lighting heat load"
            )
    else:
        # Free-text fallback (plain English diagnosis) — extract what we can
        delta_m = re.search(r"(\d+\.?\d*)\s*[Cc]\s+above\s+setpoint", diagnosis_text)
        if delta_m:
            result["zone_delta_str"] = f"+{delta_m.group(1)}C above"
        if "solar" in diagnosis_text.lower() or "sun" in diagnosis_text.lower():
            result["contextual_factors"].append("Solar heat gain")
        if "low occupancy" in diagnosis_text.lower():
            result["contextual_factors"].append("Low zone occupancy")
        if "lighting" in diagnosis_text.lower():
            result["contextual_factors"].append("High lighting heat load")

    return result


def format_for_chat(
    diagnosis: ComplaintDiagnosis,
    history: Optional[dict] = None,
) -> str:
    """
    Format diagnosis for Chat UI (markdown).

    Renders structured ZoneAssessment data:
    - Equipment health table with health bars
    - VAV live readings
    - Outdoor temperature (with extreme flag)
    - Contextual factors
    - Control-gated suggestion tags ([auto], [approval required])
    """
    desk = diagnosis.desk
    zone = diagnosis.zone

    parsed = _parse_diagnosis_text(diagnosis.diagnosis)

    lines = [
        f"## Desk {desk.desk_id} — {zone.zone_name or zone.zone_id}",
        "",
        f"**Floor:** {desk.floor} | **Zone:** {zone.zone_id}",
        "",
    ]

    # --- Equipment section ---
    if parsed["equipment"]:
        lines.append("### Equipment")
        # Header
        lines.append("| Equipment | Status | Health |")
        lines.append("|---|---|---|")
        for eq in parsed["equipment"]:
            health_bar_str = _health_bar(eq["health"])
            status_emoji = ""
            if eq["status"] in ("fault", "critical"):
                status_emoji = " 🔴"
            elif eq["status"] == "warning":
                status_emoji = " 🟡"
            else:
                status_emoji = " 🟢"
            alerts_str = f" · {len(eq['alerts'])} alert(s)" if eq["alerts"] else ""
            preds_str = f" · {len(eq['predictions'])} prediction(s)" if eq["predictions"] else ""
            lines.append(
                f"| {eq['name']}{status_emoji} | {eq['status']} | {health_bar_str}{alerts_str}{preds_str} |"
            )
        lines.append("")

    # --- Environment section ---
    env_parts = []
    # Prefer parsed values from ZoneAssessment text; fall back to zone object
    disp_temp = parsed["zone_temp"] if parsed["zone_temp"] is not None else zone.current_temp
    disp_setpoint = parsed["zone_setpoint"] if parsed["zone_setpoint"] is not None else zone.setpoint
    if disp_temp is not None:
        if disp_setpoint is not None and parsed["zone_delta_str"]:
            temp_str = f"Temperature: **{disp_temp}°C** (setpoint {disp_setpoint}°C, {parsed['zone_delta_str']})"
        else:
            delta = _temp_delta_str(disp_temp, disp_setpoint) if disp_setpoint is not None else ""
            temp_str = f"Temperature: **{disp_temp}°C** (setpoint {disp_setpoint}°C, {delta})" if disp_setpoint else f"Temperature: **{disp_temp}°C**"
        env_parts.append(temp_str)
        env_parts.append(temp_str)

    if parsed["zone_status"]:
        status_label = parsed["zone_status"].replace("_", " ").title()
        env_parts.append(f"Zone status: {status_label}")

    # VAV readings
    if parsed["vav"]:
        vav_parts = []
        vav = parsed["vav"]
        if vav.get("damper") is not None:
            vav_parts.append(f"damper {vav['damper']:.0f}%")
        if vav.get("airflow") is not None:
            vav_parts.append(f"airflow {vav['airflow']:.0f} L/s")
        if vav.get("discharge") is not None:
            vav_parts.append(f"discharge {vav['discharge']:.1f}°C")
        if vav.get("reheat") is not None:
            vav_parts.append(f"reheat {vav['reheat']:.0f}%")
        if vav_parts and vav.get("vav_id"):
            env_parts.append(f"VAV `{vav['vav_id']}`: {', '.join(vav_parts)}")

    # Desk context
    if desk.near_window:
        orient = f" ({desk.orientation}-facing)" if desk.orientation else ""
        env_parts.append(f"Near window{orient}")

    if parsed["outdoor_temp"] is not None:
        extreme_note = " 🔥" if parsed["outdoor_extreme"] else ""
        env_parts.append(f"Outdoor: {parsed['outdoor_temp']:.0f}°C{extreme_note}")

    if env_parts:
        lines.append("### Environment")
        for part in env_parts:
            lines.append(f"- {part}")
        lines.append("")

    # --- No issues header ---
    no_issues = (
        parsed["is_no_issues"]
        or (
            diagnosis.diagnosis
            and "no issues" in diagnosis.diagnosis.lower()
        )
        or (
            not parsed["equipment"]
            and not parsed["contextual_factors"]
            and parsed["zone_status"] in ("running", "normal", None)
        )
    )
    if no_issues:
        lines.append("### Diagnosis")
        lines.append("✅ **No equipment issues detected** — all systems operating within parameters.")
        if diagnosis.root_cause and diagnosis.root_cause not in ("no_issues", "unknown"):
            lines.append(f"**Root cause:** {diagnosis.root_cause}")
        if parsed["contextual_factors"]:
            lines.append("")
            lines.append("**Contributing factors:**")
            for cf in parsed["contextual_factors"]:
                lines.append(f"- {cf}")
        lines.append("")

    # --- Contextual factors (no equipment issues) ---
    elif parsed["contextual_factors"] and not parsed["equipment"]:
        lines.append("### Contributing Factors")
        for cf in parsed["contextual_factors"]:
            lines.append(f"- {cf}")
        lines.append("")

    # --- History context ---
    if history and history.get("count", 0) > 0:
        lines.extend([
            "### Complaint History",
            f"{history['count']} in last 7 days",
        ])
        if history.get("escalation_recommended"):
            lines.append("⚠️ **Escalation recommended** — recurring issue.")
        lines.append("")

    # --- Suggestions ---
    if diagnosis.suggestions:
        lines.append("### Suggested Actions")
        for i, suggestion in enumerate(diagnosis.suggestions, 1):
            lines.append(f"{i}. {suggestion}")

        if diagnosis.needs_dispatch:
            lines.extend([
                "",
                "> A technician dispatch is recommended for this issue.",
            ])

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
    parsed = _parse_diagnosis_text(diagnosis.diagnosis)

    # Temperature emoji
    if parsed["zone_temp"] is not None and parsed["zone_setpoint"] is not None:
        delta = parsed["zone_temp"] - parsed["zone_setpoint"]
    else:
        delta = zone.current_temp - zone.setpoint

    if delta > 1.5:
        temp_emoji = "🌡️"
    elif delta < -1.5:
        temp_emoji = "❄️"
    else:
        temp_emoji = "✅"

    lines = [
        f"{temp_emoji} *Desk {desk.desk_id}* — {zone.zone_name or zone.zone_id}",
        "",
    ]

    # Temp
    if parsed["zone_temp"] is not None and parsed["zone_setpoint"] is not None:
        lines.append(
            f"Current: {parsed['zone_temp']:.1f}°C | Target: {parsed['zone_setpoint']:.1f}°C "
            f"| *{parsed['zone_delta_str']}*"
        )
    else:
        lines.append(
            f"Current: {zone.current_temp}°C | Target: {zone.setpoint}°C "
            f"| *{_temp_delta_str(zone.current_temp, zone.setpoint)}*"
        )

    # Equipment summary
    if parsed["equipment"]:
        eq_parts = []
        for eq in parsed["equipment"]:
            health_icon = "🟢" if eq["status"] in ("normal", "running") and eq["health"] >= 70 else \
                          "🟡" if eq["status"] in ("warning") else "🔴"
            eq_parts.append(f"{eq['name']} {health_icon}{eq['health']}%")
        lines.append(" | ".join(eq_parts))
    else:
        fcu_icon = "\u2705" if zone.status != "fault" else "\u274c"
        lines.append(f"{zone.fcu_id} {fcu_icon}")

    # Outdoor temp
    if parsed["outdoor_temp"] is not None:
        extreme = " \U0001f525" if parsed["outdoor_extreme"] else ""
        lines.append(f"Outdoor: {parsed['outdoor_temp']:.0f}°C{extreme}")

    # Contextual factors
    if parsed["contextual_factors"]:
        for cf in parsed["contextual_factors"]:
            lines.append(f"\u2796 {cf}")

    # No issues
    if parsed["is_no_issues"]:
        lines.append("")
        lines.append("\U0001f7e2 *All systems operating within parameters*")

    # History
    if history and history.get("count", 0) > 0:
        lines.extend([
            "",
            f"\u26a0\ufe0f {history['count']} similar complaint"
            f"{'s' if history['count'] > 1 else ''} this week at this desk.",
        ])

    # Root cause
    if diagnosis.root_cause and diagnosis.root_cause not in ("no_issues", "unknown"):
        lines.extend([
            "",
            f"*Probable cause:* {diagnosis.root_cause}",
        ])

    # Suggestions
    if diagnosis.suggestions:
        lines.append("")
        lines.append("*Actions:*")
        for i, suggestion in enumerate(diagnosis.suggestions, 1):
            lines.append(f"{i}. {suggestion}")

    if diagnosis.needs_dispatch or (history and history.get("escalation_recommended")):
        lines.extend([
            "",
            "Given repeat complaints, a work order may be warranted.",
            "Reply *WO* to create one.",
        ])

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
    parsed = _parse_diagnosis_text(diagnosis.diagnosis)

    lines = [
        f"*Desk Comfort Report - {desk.desk_id}*",
        f"Zone: {zone.zone_name or zone.zone_id} | Floor: {desk.floor}",
        "",
    ]

    # Temperature
    if parsed["zone_temp"] is not None and parsed["zone_setpoint"] is not None:
        lines.append(
            f"Temp: {parsed['zone_temp']:.1f}°C (setpoint {parsed['zone_setpoint']}°C, "
            f"delta {parsed['zone_temp'] - parsed['zone_setpoint']:+.1f}°C)"
        )
    else:
        delta = zone.current_temp - zone.setpoint
        lines.append(
            f"Temp: {zone.current_temp}°C (setpoint {zone.setpoint}°C, delta {delta:+.1f}°C)"
        )

    # Equipment
    if parsed["equipment"]:
        for eq in parsed["equipment"]:
            status_icon = "✅" if eq["status"] in ("normal", "running") else \
                          "⚠️" if eq["status"] == "warning" else "🚨"
            alerts_str = f" · {len(eq['alerts'])}alerts" if eq["alerts"] else ""
            preds_str = f" · {len(eq['predictions'])}preds" if eq["predictions"] else ""
            lines.append(f"  {status_icon} {eq['name']}: {eq['status']} ({eq['health']}%){alerts_str}{preds_str}")
    else:
        lines.append(f"FCU: `{zone.fcu_id}` - {zone.status}")

    # VAV
    if parsed["vav"]:
        vav_parts = []
        if parsed["vav"].get("damper") is not None:
            vav_parts.append(f"damper {parsed['vav']['damper']:.0f}%")
        if parsed["vav"].get("airflow") is not None:
            vav_parts.append(f"airflow {parsed['vav']['airflow']:.0f} L/s")
        if parsed["vav"].get("discharge") is not None:
            vav_parts.append(f"discharge {parsed['vav']['discharge']:.1f}°C")
        if vav_parts:
            lines.append(f"  VAV `{parsed['vav'].get('vav_id', zone.vav_id or '?')}`: {', '.join(vav_parts)}")

    # Outdoor
    if parsed["outdoor_temp"] is not None:
        extreme = " [EXTREME]" if parsed["outdoor_extreme"] else ""
        lines.append(f"  Outdoor: {parsed['outdoor_temp']:.0f}°C{extreme}")

    # Contextual factors
    if parsed["contextual_factors"]:
        for cf in parsed["contextual_factors"]:
            lines.append(f"  \u2796 {cf}")

    # No issues
    if parsed["is_no_issues"]:
        lines.append("")
        lines.append("\U0001f7e2 *No equipment issues detected — all systems OK*")

    # History
    if history and history.get("count", 0) > 0:
        lines.append(f"\nHistory: {history['count']} complaints in 7 days")
        if history.get("escalation_recommended"):
            lines.append("*ESCALATION RECOMMENDED*")

    # Root cause + suggestions
    if diagnosis.root_cause and diagnosis.root_cause not in ("no_issues", "unknown"):
        lines.extend([
            "",
            f"Root cause: {diagnosis.root_cause}",
            f"Confidence: {diagnosis.confidence}",
        ])

    if diagnosis.suggestions:
        lines.append("")
        lines.append("Actions:")
        for i, suggestion in enumerate(diagnosis.suggestions, 1):
            lines.append(f"  {i}. {suggestion}")

    if diagnosis.needs_dispatch:
        lines.append("\n*Technician dispatch recommended.*")

    return "\n".join(lines)
