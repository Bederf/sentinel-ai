"""Recommendation Agent Channel Formatters
==========================================
Channel-specific formatting for recommendation agent outputs.
Follows the same pattern as desk complaint formatters.

Channels:
  - system: Structured log / dashboard markdown
  - chat: Dashboard markdown with headers
  - whatsapp: Bold/emoji, compact with approve/reject CTA
  - telegram: Telegram markdown (*bold*, `code`)

LLM usage: Zero. All formatting is pure Python string building.
"""

from typing import Any


def _equipment_label(equipment_code: str) -> str:
    """Convert equipment code to human-readable label.

    Examples:
        S002-FCU-201 -> FCU-201 (Level 2, Zone A)
        S002-CHILLER-B1-001 -> CHILLER-B1-001 (Basement 1)
    """
    parts = equipment_code.split("-") if equipment_code else []
    if len(parts) < 3:
        return equipment_code

    # Remove site prefix for display
    short = "-".join(parts[1:])

    # Try to decode zone from the last numeric segment
    zone_part = parts[-1] if parts[-1].isdigit() else ""
    if zone_part:
        zone_num = int(zone_part)
        if zone_num < 100:
            level = "Ground Floor"
        elif zone_num < 200:
            level = "Level 1"
        elif zone_num < 300:
            level = "Level 2"
        elif zone_num < 400:
            level = "Level 3"
        else:
            level = f"Zone {zone_num}"
        return f"{short} ({level})"

    return short


def _risk_emoji(risk: str) -> str:
    """Map risk level to emoji."""
    return {
        "low": "",
        "medium": "",
        "high": "",
        "critical": "",
    }.get(risk, "")


def _tier_label(tier: str) -> str:
    """Map tier to human-readable label."""
    return {
        "tier1": "Advisory (Tier 1)",
        "tier2": "Approval Required (Tier 2)",
        "tier3": "Auto-Execute (Tier 3)",
    }.get(tier, tier)


# ---------------------------------------------------------------------------
# Advisory format (Tier 1) — logged to dashboard
# ---------------------------------------------------------------------------


def format_advisory_for_chat(
    rec: dict[str, Any],
    impact: dict[str, Any],
    tier_result: dict[str, Any] | None = None,
) -> str:
    """Format Tier 1 advisory for dashboard/chat display.

    Returns markdown suitable for the BMS dashboard.
    """
    equipment = _equipment_label(rec.get("target_equipment", ""))
    action_type = rec.get("action_type", "").replace("_", " ").title()
    reason = rec.get("reason", "")
    confidence = rec.get("confidence_score", 0.0)
    risk = rec.get("risk_level", "medium")

    cost = impact.get("cost_zar", 0)
    energy = impact.get("energy_kwh", 0)
    comfort = impact.get("comfort_delta", 0)

    lines = [
        f"### Advisory: {action_type}",
        f"**Equipment:** {equipment}",
        f"**Reason:** {reason}",
        f"**Confidence:** {confidence:.0%} | **Risk:** {risk.upper()}",
        "",
    ]

    if cost or energy or comfort:
        lines.append("**Estimated Impact:**")
        if cost:
            lines.append(f"- Cost: R{cost:.2f}/hour saving")
        if energy:
            lines.append(f"- Energy: {energy:.1f} kWh")
        if comfort:
            lines.append(f"- Comfort: {comfort:+.1f} C")

    if tier_result:
        lines.append("")
        lines.append(f"*Routed to {_tier_label(tier_result.get('tier', ''))}*")

    return "\n".join(lines)


def format_advisory_for_system(
    rec: dict[str, Any],
    impact: dict[str, Any],
    tier_result: dict[str, Any] | None = None,
) -> str:
    """Format Tier 1 advisory for system log.

    Returns compact single-line summary for log output.
    """
    equipment = rec.get("target_equipment", "")
    action_type = rec.get("action_type", "")
    confidence = rec.get("confidence_score", 0.0)
    cost = impact.get("cost_zar", 0)

    parts = [
        f"[ADVISORY] {equipment}: {action_type}",
        f"confidence={confidence:.2f}",
    ]
    if cost:
        parts.append(f"est_saving=R{cost:.2f}/hr")

    return " | ".join(parts)


# ---------------------------------------------------------------------------
# Approval request format (Tier 2) — sent to technician
# ---------------------------------------------------------------------------


def format_approval_request_whatsapp(
    rec: dict[str, Any],
    impact: dict[str, Any],
    tier_result: dict[str, Any] | None = None,
) -> str:
    """Format Tier 2 approval request for WhatsApp.

    Uses bold, emoji, and compact layout. Includes approve/reject CTA.
    """
    equipment = _equipment_label(rec.get("target_equipment", ""))
    action = rec.get("action", {})
    point = action.get("point", "")
    value = action.get("value", "")
    reason = rec.get("reason", "")
    confidence = rec.get("confidence_score", 0.0)
    risk = rec.get("risk_level", "medium")
    rec_id = rec.get("id", "")

    cost = impact.get("cost_zar", 0)
    comfort = impact.get("comfort_delta", 0)

    lines = [
        f"{_risk_emoji(risk)} *Approval Required*",
        "",
        f"*Equipment:* {equipment}",
        f"*Action:* Set {point} to {value}",
        f"*Reason:* {reason}",
        f"*Confidence:* {confidence:.0%} | *Risk:* {risk.upper()}",
    ]

    if cost or comfort:
        lines.append("")
        if cost:
            lines.append(f"Estimated saving: R{cost:.2f}/hour")
        if comfort:
            lines.append(f"Comfort impact: {comfort:+.1f} C")

    lines.extend(
        [
            "",
            f"Reply: *APPROVE {rec_id[:8]}* or *REJECT {rec_id[:8]}* (with reason)",
        ]
    )

    return "\n".join(lines)


def format_approval_request_telegram(
    rec: dict[str, Any],
    impact: dict[str, Any],
    tier_result: dict[str, Any] | None = None,
) -> str:
    """Format Tier 2 approval request for Telegram.

    Uses Telegram markdown (*bold*, `code`).
    """
    equipment = _equipment_label(rec.get("target_equipment", ""))
    action = rec.get("action", {})
    point = action.get("point", "")
    value = action.get("value", "")
    reason = rec.get("reason", "")
    confidence = rec.get("confidence_score", 0.0)
    risk = rec.get("risk_level", "medium")
    rec_id = rec.get("id", "")

    cost = impact.get("cost_zar", 0)
    comfort = impact.get("comfort_delta", 0)

    lines = [
        f"{_risk_emoji(risk)} *Approval Required*",
        "",
        f"*Equipment:* `{equipment}`",
        f"*Action:* Set `{point}` to `{value}`",
        f"*Reason:* {reason}",
        f"*Confidence:* {confidence:.0%} | *Risk:* {risk.upper()}",
    ]

    if cost or comfort:
        lines.append("")
        if cost:
            lines.append(f"Estimated saving: R{cost:.2f}/hour")
        if comfort:
            lines.append(f"Comfort impact: {comfort:+.1f} C")

    lines.extend(
        [
            "",
            f"Reply: `/approve {rec_id[:8]}` or `/reject {rec_id[:8]} <reason>`",
        ]
    )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Execution result format (Tier 3 or post-approval)
# ---------------------------------------------------------------------------


def format_execution_result(
    rec: dict[str, Any],
    result: dict[str, Any],
    channel: str = "system",
) -> str:
    """Format execution result for any channel.

    Args:
        rec: Recommendation dict
        result: ApprovalResult dict from execution
        channel: Target channel ("system", "chat", "whatsapp", "telegram")

    Returns:
        Formatted string for the channel
    """
    equipment = _equipment_label(rec.get("target_equipment", ""))
    action = rec.get("action", {})
    point = action.get("point", "")
    value = action.get("value", "")
    success = result.get("success", False)
    cov = result.get("cov_verified", False)
    status = result.get("status", "unknown")

    if channel == "system":
        return _format_exec_system(equipment, point, value, success, cov, status, result)
    elif channel == "whatsapp":
        return _format_exec_whatsapp(equipment, point, value, success, cov, status)
    elif channel == "telegram":
        return _format_exec_telegram(equipment, point, value, success, cov, status)
    else:
        return _format_exec_chat(equipment, point, value, success, cov, status, result)


def _format_exec_system(
    equipment: str,
    point: str,
    value: str,
    success: bool,
    cov: bool,
    status: str,
    result: dict[str, Any],
) -> str:
    icon = "OK" if success else "FAIL"
    cov_str = "COV_OK" if cov else "COV_FAIL"
    return f"[{icon}] {equipment}: {point}={value} status={status} {cov_str}"


def _format_exec_whatsapp(
    equipment: str,
    point: str,
    value: str,
    success: bool,
    cov: bool,
    status: str,
) -> str:
    icon = "done" if success else "failed"
    cov_str = " COV confirmed." if cov else " COV not confirmed."
    return f"*{icon.upper()}* {equipment} {point} set to {value}.{cov_str}"


def _format_exec_telegram(
    equipment: str,
    point: str,
    value: str,
    success: bool,
    cov: bool,
    status: str,
) -> str:
    icon = "Done" if success else "Failed"
    cov_str = " COV confirmed." if cov else " COV not confirmed."
    return f"*{icon}* `{equipment}` `{point}` set to `{value}`.{cov_str}"


def _format_exec_chat(
    equipment: str,
    point: str,
    value: str,
    success: bool,
    cov: bool,
    status: str,
    result: dict[str, Any],
) -> str:
    icon = "Success" if success else "Failed"
    lines = [
        f"### {icon}: {equipment}",
        f"**Action:** {point} set to {value}",
        f"**Status:** {status}",
        f"**COV Verified:** {'Yes' if cov else 'No'}",
    ]
    error = result.get("error_message")
    if error:
        lines.append(f"**Error:** {error}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Batch / summary format
# ---------------------------------------------------------------------------


def format_batch_summary(
    results: list[dict[str, Any]],
    channel: str = "system",
) -> str:
    """Format a batch processing summary.

    Args:
        results: List of per-recommendation result dicts
        channel: Target channel

    Returns:
        Formatted summary string
    """
    total = len(results)
    if total == 0:
        return "No pending recommendations to process."

    executed = sum(1 for r in results if r.get("status") in ("executed", "auto_executed"))
    advised = sum(1 for r in results if r.get("tier") == "tier1")
    pending_approval = sum(1 for r in results if r.get("needs_input", False))
    expired = sum(1 for r in results if r.get("status") == "expired")
    deferred = sum(1 for r in results if r.get("status") == "deferred")

    if channel in ("whatsapp", "telegram"):
        lines = [f"*Processed {total} recommendation(s):*"]
        if executed:
            lines.append(f"  Auto-executed: {executed}")
        if advised:
            lines.append(f"  Advisory logged: {advised}")
        if pending_approval:
            lines.append(f"  Awaiting approval: {pending_approval}")
        if expired:
            lines.append(f"  Expired: {expired}")
        if deferred:
            lines.append(f"  Deferred (schedule conflict): {deferred}")
        return "\n".join(lines)
    else:
        parts = [f"Processed {total} recommendation(s):"]
        if executed:
            parts.append(f"{executed} auto-executed")
        if advised:
            parts.append(f"{advised} advisory")
        if pending_approval:
            parts.append(f"{pending_approval} awaiting approval")
        if expired:
            parts.append(f"{expired} expired")
        if deferred:
            parts.append(f"{deferred} deferred")
        return " | ".join(parts)
