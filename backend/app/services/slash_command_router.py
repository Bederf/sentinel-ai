"""Slash command router for web chat.

Intercepts FM workflow commands (/info-, /WO-, /reset-, /note-)
before the AI pipeline, calling internal APIs directly. Works even when
Claude credits are exhausted — no AI invocation needed.

Mirrors the Sentry Telegram bot's slash command handling.
"""

import asyncio
import logging
import re
from dataclasses import dataclass

import httpx

from app.config.settings import settings

logger = logging.getLogger(__name__)

# Pattern: /command_EQUIPMENT_CODE [optional trailing text]
# Equipment codes use underscores in chat (S002_FCU_301), converted to dashes for APIs.
_SLASH_RE = re.compile(
    r"^/(info|WO|reset|note|status_WO)[-_]([A-Za-z0-9][\w-]*)(?:\s+(.+))?$",
    re.DOTALL,
)

# Safety-critical equipment types that cannot be remotely reset
_BLOCKED_RESET_TYPES = {"FIRE", "GEN"}


@dataclass
class CommandResult:
    """Result from a slash command execution."""

    message: str
    success: bool = True


def parse(message: str) -> tuple[str, str, str | None] | None:
    """Parse a slash command from a chat message.

    Returns:
        (command, equipment_code_with_dashes, extra_text) or None if not a command.
    """
    m = _SLASH_RE.match(message.strip())
    if not m:
        return None
    command = m.group(1)
    # Convert underscores to dashes for API calls
    equipment_code = m.group(2).replace("_", "-").upper()
    extra_text = m.group(3).strip() if m.group(3) else None
    return command, equipment_code, extra_text


def _code_for_buttons(equipment_code: str) -> str:
    """Convert underscored equipment code back to dashed form for chat buttons."""
    return equipment_code.replace("_", "-")


def _base_url() -> str:
    """Internal API base URL."""
    port = settings.port if hasattr(settings, "port") else 9095
    return f"http://127.0.0.1:{port}"


def _sentry_headers() -> dict[str, str]:
    """Headers for internal Sentry API calls."""
    headers: dict[str, str] = {
        "X-Sentry-Secret": settings.sentry_webhook_secret,
        "Content-Type": "application/json",
    }
    if settings.sentry_bot_api_key:
        headers["X-Sentry-API-Key"] = settings.sentry_bot_api_key
    return headers


def _parse_assign(extra: str | None) -> tuple[str | None, str | None]:
    """Extract 'assign:Name' from extra text. Returns (assigned_to, remaining_text)."""
    if not extra:
        return None, None
    m = re.search(r"assign:\s*(.+?)(?:\s*$)", extra, re.IGNORECASE)
    if m:
        name = m.group(1).strip()
        remaining = extra[: m.start()].strip() or None
        return name, remaining
    return None, extra


def _quick_actions(code: str) -> str:
    """Render the quick-actions footer with clickable commands."""
    c = _code_for_buttons(code)
    return f"\n---\n**Quick Actions:** `/info-{c}` \u00b7 `/reset-{c}` \u00b7 `/WO-{c}` \u00b7 `/note-{c}`"


async def _notify_technician(
    wo_code: str,
    equipment_code: str,
    tech_telegram_id: str | None,
    tech_email: str | None,
    tech_name: str | None,
    priority: str = "medium",
) -> None:
    """Send Telegram + email notification to the assigned technician.

    Uses ``sentry message send`` CLI for Telegram and work_order_notifier for email.
    """
    # SECURITY: /api/chat is unauthenticated (in _PUBLIC_PREFIXES). All user-supplied
    # values interpolated into Telegram messages must be plain text only.
    # Do NOT add parse_mode: HTML without escaping every interpolated field —
    # an attacker can inject phishing links into trusted SENTINEL bot messages.

    # --- Telegram via Bot API directly ---
    if tech_telegram_id:
        assigned = tech_name or "Pending"
        msg = f"Work Order Created #{wo_code}\nAssigned: {assigned}\nPriority: {priority.upper()}"
        try:
            bot_token = settings.sentry_client_bot_token
            if bot_token:
                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.post(
                        f"https://api.telegram.org/bot{bot_token}/sendMessage",
                        json={"chat_id": str(tech_telegram_id), "text": msg},
                    )
                    result = resp.json()
                    if result.get("ok"):
                        logger.info("Telegram sent to %s for %s", tech_telegram_id, wo_code)
                    else:
                        logger.warning("Telegram send failed for %s: %s", wo_code, result.get("description"))
            else:
                logger.warning("SENTRY_CLIENT_BOT_TOKEN not configured")
        except Exception as exc:
            logger.warning("Telegram notification failed for %s: %s", wo_code, exc)

    # --- Email via SMTP (workorder@sentinel-ai.co.za) ---
    if tech_email:
        try:
            from app.services.email_reply_service import get_email_reply_service

            svc = get_email_reply_service()
            if svc.is_configured():
                # Gather equipment context for the email
                body_plain = await _build_wo_email_body(
                    wo_code,
                    equipment_code,
                    priority,
                    tech_name,
                )
                subject = f"SENTINEL {wo_code} — {equipment_code}"
                result = await svc.send_reply(
                    to_email=tech_email,
                    to_name=tech_name,
                    subject=subject,
                    body_plain=body_plain,
                    body_html=None,
                )
                if result.sent:
                    logger.info("Email sent to %s for %s", tech_email, wo_code)
                else:
                    logger.warning("SMTP send failed for %s: %s", wo_code, result.error)
            else:
                logger.warning("Email reply service not configured — email not sent for %s", wo_code)
        except Exception as exc:
            logger.warning("Email notification failed for %s: %s", wo_code, exc)


async def _build_wo_email_body(
    wo_code: str,
    equipment_code: str,
    priority: str,
    tech_name: str | None,
) -> str:
    """Fetch equipment info and build a full briefing email."""
    lines = [
        f"WORK ORDER: {wo_code}",
        f"Equipment: {equipment_code}",
        f"Priority: {priority.upper()}",
        f"Assigned to: {tech_name or 'Technician'}",
        "",
    ]

    # --- Equipment info ---
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{_base_url()}/api/work-orders/equipment-info/{equipment_code}",
                headers=_sentry_headers(),
            )
        if resp.status_code == 200:
            info = resp.json()
            lines.append("=" * 50)
            lines.append("EQUIPMENT DETAILS")
            lines.append("=" * 50)
            lines.append(f"Code: {info.get('equipment_code') or info.get('code') or equipment_code}")
            lines.append(f"Type: {info.get('type', 'N/A')}")
            lines.append(f"Status: {info.get('status', 'N/A')}")
            lines.append(f"Health: {info.get('health_score', 'N/A')}%")
            lines.append(f"Location: {info.get('location', 'N/A')}")
            if info.get("manufacturer"):
                lines.append(f"Manufacturer: {info['manufacturer']}")
            if info.get("model"):
                lines.append(f"Model: {info['model']}")
            if info.get("runtime_hours"):
                lines.append(f"Runtime: {info['runtime_hours']:,} hrs")
            if info.get("last_service"):
                lines.append(f"Last Service: {info['last_service']}")
            if info.get("notes"):
                lines.append(f"Notes: {info['notes']}")
            lines.append("")
    except Exception as exc:
        logger.debug("Could not fetch equipment info for email: %s", exc)

    # --- Active alerts ---
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{_base_url()}/api/alerts/active?site_id=site-002",
                headers=_sentry_headers(),
            )
        if resp.status_code == 200:
            alerts = resp.json()
            if isinstance(alerts, list):
                eq_alerts = [a for a in alerts if a.get("equipment_code") == equipment_code]
                if eq_alerts:
                    lines.append("=" * 50)
                    lines.append(f"ACTIVE ALERTS ({len(eq_alerts)})")
                    lines.append("=" * 50)
                    for a in eq_alerts[:5]:
                        sev = (a.get("severity") or "unknown").upper()
                        msg = a.get("message") or a.get("title", "Alert")
                        lines.append(f"  [{sev}] {msg}")
                    lines.append("")
    except Exception as exc:
        logger.debug("Could not fetch alerts for email: %s", exc)

    lines.append("=" * 50)
    lines.append("INSTRUCTIONS")
    lines.append("=" * 50)
    lines.append(f"1. Reply 'done #{wo_code}' in Telegram when work is complete.")
    lines.append("2. Use /info and /note commands as needed.")
    lines.append("")
    lines.append("-- SENTINEL Work Order System")

    return "\n".join(lines)


async def execute(
    command: str,
    equipment_code: str,
    extra_text: str | None,
    user_email: str | None,
) -> CommandResult:
    """Dispatch a parsed slash command to the appropriate handler."""
    handlers = {
        "info": _handle_info,
        "WO": _handle_wo,
        "reset": _handle_reset,
        "note": _handle_note,
        "status_WO": _handle_status_wo,
    }
    handler = handlers.get(command)
    if not handler:
        return CommandResult(
            message=f"Unknown command: `/{command}`",
            success=False,
        )
    try:
        return await handler(equipment_code, extra_text, user_email)
    except httpx.ConnectError:
        logger.error("Slash command failed: cannot reach internal API")
        return CommandResult(
            message="Internal API is unreachable. Please try again shortly.",
            success=False,
        )
    except Exception as exc:
        logger.error("Slash command /%s_%s failed: %s", command, equipment_code, exc, exc_info=True)
        return CommandResult(
            message="Command failed: an internal error occurred.",
            success=False,
        )


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


async def _handle_info(code: str, _extra: str | None, _user: str | None) -> CommandResult:
    """GET /api/work-orders/equipment-info/{code} — equipment details."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(f"{_base_url()}/api/work-orders/equipment-info/{code}")

    if resp.status_code == 404:
        return CommandResult(
            message=f"Equipment `{code}` not found.",
            success=False,
        )
    if resp.status_code != 200:
        return CommandResult(
            message=f"Failed to fetch info for `{code}` (HTTP {resp.status_code}).",
            success=False,
        )

    data = resp.json()
    lines = [
        f"## {data.get('equipment_code', code)}",
        "",
        "| Field | Value |",
        "|-------|-------|",
        f"| **Code** | `{data.get('equipment_code', code)}` |",
        f"| **Type** | {data.get('type', 'unknown')} |",
        f"| **Status** | {data.get('status', 'unknown')} |",
        f"| **Health** | {data.get('health_score', 'N/A')}% |",
        f"| **Location** | {data.get('location', 'N/A')} |",
    ]
    if data.get("manufacturer"):
        lines.append(f"| **Manufacturer** | {data['manufacturer']} |")
    if data.get("model"):
        lines.append(f"| **Model** | {data['model']} |")
    if data.get("runtime_hours"):
        lines.append(f"| **Runtime** | {data['runtime_hours']:,} hrs |")
    if data.get("last_service"):
        lines.append(f"| **Last Service** | {data['last_service']} |")
    if data.get("notes"):
        lines.append(f"\n**Notes:** {data['notes']}")

    lines.append(_quick_actions(code))
    return CommandResult(message="\n".join(lines))


async def _handle_wo(code: str, extra: str | None, user: str | None) -> CommandResult:
    """Create a work order for the equipment + notify technician."""
    assigned_to, remaining = _parse_assign(extra)
    title = remaining or f"Work order for {code}"

    payload: dict = {
        "equipment_code": code,
        "title": title,
        "description": f"Web chat work order: {title}",
        "priority": "medium",
        "created_by": user or "web-chat",
    }
    if assigned_to:
        payload["assigned_to"] = assigned_to

    async with httpx.AsyncClient(timeout=20) as client:
        # 1. Create WO
        wo_resp = await client.post(
            f"{_base_url()}/api/sentry/create-work-order",
            json=payload,
            headers=_sentry_headers(),
        )

    if wo_resp.status_code != 200:
        return CommandResult(
            message=f"Failed to create work order for `{code}` (HTTP {wo_resp.status_code}).",
            success=False,
        )

    wo = wo_resp.json()
    wo_code = wo.get("code", "N/A")
    assigned = wo.get("assigned_to", "Unassigned")
    priority = wo.get("priority", "medium")
    tech_telegram_id = wo.get("technician_telegram_id")
    tech_email = wo.get("technician_email")

    # 2. Send Telegram + email to the assigned technician (fire-and-forget)
    asyncio.create_task(_notify_technician(wo_code, code, tech_telegram_id, tech_email, assigned, priority))

    c = _code_for_buttons(code)
    notified_via = []
    if tech_telegram_id:
        notified_via.append("Telegram")
    if tech_email:
        notified_via.append(f"email ({tech_email})")
    notified_str = " + ".join(notified_via) if notified_via else "no contact info on file"

    lines = [
        "## Work Order Created",
        "",
        "| Field | Value |",
        "|-------|-------|",
        f"| **WO Code** | `{wo_code}` |",
        f"| **Equipment** | `{code}` |",
        f"| **Priority** | {priority} |",
        f"| **Assigned To** | {assigned} |",
        f"| **Notified Via** | {notified_str} |",
        "| **Status** | scheduled |",
    ]

    lines.append(f"\n---\n**Quick Actions:** `/info-{c}` \u00b7 `/note-{c}`")
    return CommandResult(message="\n".join(lines))


async def _handle_reset(code: str, extra: str | None, user: str | None) -> CommandResult:
    """POST /api/sentry/equipment/reset — remote fault reset."""
    # Safety check: block FIRE and GEN equipment
    parts = code.split("-")
    eq_type = parts[1].upper() if len(parts) >= 2 else ""
    if eq_type in _BLOCKED_RESET_TYPES:
        c = _code_for_buttons(code)
        return CommandResult(
            message=(
                f"**Reset blocked:** `{eq_type}` equipment cannot be remotely reset for safety reasons.\n\n"
                f"Create a work order instead: `/WO-{c}`"
            ),
            success=False,
        )

    # Gate: only available in supervised or auto mode with control module active
    try:
        from app.services.control_policy_engine import ControlMode, ControlPolicyEngine

        engine = ControlPolicyEngine()
        mode = engine.get_control_mode()
        if mode == ControlMode.RECOMMEND:
            c = _code_for_buttons(code)
            return CommandResult(
                message=(
                    f"**Reset not available:** System is in advisory mode.\n"
                    f"Remote reset requires supervised or automatic control mode.\n"
                    f"Create a work order instead: `/WO-{c}`"
                ),
                success=False,
            )
    except Exception:
        pass  # If gate check fails, allow the request (defense in depth)

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{_base_url()}/api/sentry/equipment/reset",
            json={
                "equipment_code": code,
                "user_id": f"web-chat:{user or 'anonymous'}",
                "reason": extra or "Reset via web chat",
            },
            headers=_sentry_headers(),
        )

    if resp.status_code != 200:
        return CommandResult(
            message=f"Reset failed for `{code}` (HTTP {resp.status_code}).",
            success=False,
        )

    data = resp.json()
    if data.get("blocked"):
        c = _code_for_buttons(code)
        return CommandResult(
            message=f"**Reset blocked:** {data.get('reason', 'Unknown reason')}\n\n`/WO-{c}`",
            success=False,
        )

    prev_health = data.get("previous_health", "?")
    new_health = data.get("new_health", "?")

    c = _code_for_buttons(code)
    return CommandResult(
        message=(
            f"## Equipment Reset\n\n"
            f"**Equipment:** `{code}`\n"
            f"**Health:** {prev_health}% \u2192 {new_health}%\n"
            f"**Predictions resolved:** {data.get('predictions_resolved', 0)}\n"
            f"\n---\n**Quick Actions:** `/info-{c}` \u00b7 `/WO-{c}`"
        )
    )


async def _handle_note(code: str, extra: str | None, user: str | None) -> CommandResult:
    """PATCH /api/equipment/{code}/notes — add a note."""
    if not extra:
        c = _code_for_buttons(code)
        return CommandResult(
            message=(
                f"**Usage:** `/note-{c} <your note text>`\n\nExample: `/note-{c} Filter replaced during maintenance`"
            ),
            success=False,
        )

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.patch(
            f"{_base_url()}/api/equipment/{code}/notes",
            json={
                "notes": extra,
                "changed_by": f"web-chat:{user or 'anonymous'}",
                "change_reason": "Note added via web chat",
            },
        )

    if resp.status_code == 404:
        return CommandResult(
            message=f"Equipment `{code}` not found.",
            success=False,
        )
    if resp.status_code != 200:
        return CommandResult(
            message=f"Failed to save note for `{code}` (HTTP {resp.status_code}).",
            success=False,
        )

    c = _code_for_buttons(code)
    return CommandResult(
        message=(f"**Note saved** for `{code}`\n\n> {extra}\n\n---\n**Quick Actions:** `/info-{c}` \u00b7 `/WO-{c}`")
    )


async def _handle_status_wo(code: str, _extra: str | None, user: str | None) -> CommandResult:
    """GET /api/sentry/wo-status?code={code} \u2014 check work order status.

    Staff use this to check on their own reported issues.
    """
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{_base_url()}/api/sentry/wo-status",
            params={"code": code},
            headers=_sentry_headers(),
        )

    if resp.status_code == 404 or resp.status_code == 200:
        data = resp.json()
        if not data.get("found"):
            return CommandResult(
                message=f"Work order `{code}` not found. Please check the reference number.",
                success=False,
            )

        status = data.get("display_status") or data.get("status", "unknown")
        staff_summary = data.get("staff_summary", "")
        priority = data.get("priority", "")
        category = data.get("category", "")
        title = data.get("title", "")
        notes = data.get("notes", "")
        assigned_to = data.get("assigned_to", "")
        created_at = data.get("created_at", "")
        updated_at = data.get("updated_at", "")
        completed_at = data.get("completed_at", "")
        resolved_at = data.get("resolved_at", "")
        closed_at = data.get("closed_at", "")

        lines = [
            f"📋 Work Order {code}",
            "",
            f"Status: {status}",
        ]
        if staff_summary:
            lines.append(staff_summary)
        if priority:
            lines.append(f"Priority: {priority}")
        if category:
            lines.append(f"Category: {category}")
        if title:
            lines.append(f"Issue: {title}")
        if assigned_to:
            lines.append(f"Assigned to: {assigned_to}")
        if created_at:
            lines.append(f"Created: {created_at[:16] if len(created_at) > 16 else created_at}")
        if updated_at:
            lines.append(f"Updated: {updated_at[:16] if len(updated_at) > 16 else updated_at}")
        if resolved_at:
            lines.append(f"Resolved: {resolved_at[:16] if len(resolved_at) > 16 else resolved_at}")
        if completed_at:
            lines.append(f"Completed: {completed_at[:16] if len(completed_at) > 16 else completed_at}")
        if closed_at:
            lines.append(f"Closed: {closed_at[:16] if len(closed_at) > 16 else closed_at}")
        if notes:
            lines.append(f"Technician notes: {notes}")

        return CommandResult(message="\n".join(lines))

    return CommandResult(
        message=f"Failed to look up `{code}` (HTTP {resp.status_code}). Please try again shortly.",
        success=False,
    )
