"""Overnight advisory email fallback service.

Sends a plain-text email when a high/critical advisory has been PENDING for
longer than OVERNIGHT_ADVISORY_FALLBACK_HOURS without being acknowledged via
Telegram. This is the fallback channel when the operator is not watching
Telegram — it does not replace the Telegram push, it supplements it.

Advisory only: SENTINEL does not act. The email informs; the operator decides.
BMS owns emergency response.

Transport: reuses notification_smtp_* settings (same credentials as work-order
email reply service, same mail.sentinel-ai.co.za relay).
"""

from __future__ import annotations

import logging
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import aiosmtplib

from app.config.settings import settings

logger = logging.getLogger("sentinel.alert_email")

SITE_NAMES: dict[str, str] = {
    "site-001": "Rosebank Towers",
    "site-002": "Sandton City Office Tower",
    "site-003": "Centurion Mall",
    "site-004": "V&A Waterfront Retail",
    "site-005": "Gateway Theatre of Shopping",
    "site-006": "Mediclinic Sandton",
    "site-007": "Mediclinic Constantiaberg",
    "site-008": "Standard Bank Centre",
    "site-009": "Standard Bank Rosebank",
    "site-010": "Standard Bank Durban Regional",
}

ADVISORY_LABELS: dict[str, str] = {
    "after_hours_zero_occupancy_hvac_load": "HVAC running in closed building",
    "closed_empty_building_hvac_running": "HVAC running in closed building",
    "fault_safety_gate": "Fault safety gate triggered",
}


def _recipient() -> str:
    return settings.overnight_advisory_email_recipient or settings.ai_alert_email or "info@sentinel-ai.co.za"


def _from_address() -> str:
    return settings.notification_smtp_username or "info@sentinel-ai.co.za"


def is_configured() -> bool:
    return bool(
        settings.notification_smtp_host and settings.notification_smtp_username and settings.notification_smtp_password
    )


def _build_message(
    rec: dict[str, Any],
    site_id: str,
    ts_sast: str,
) -> MIMEMultipart:
    equipment = rec.get("target_equipment") or "site"
    action_type = rec.get("action_type") or "advisory"
    label = ADVISORY_LABELS.get(action_type, action_type.replace("_", " "))
    site_name = SITE_NAMES.get(site_id, site_id.upper())
    reason = (rec.get("reason") or "").strip()

    subject = f"[SENTINEL Advisory] {label} — {site_name}"

    plain = "\n".join(
        [
            f"SENTINEL flagged at {ts_sast}",
            "",
            f"Building:   {site_name} ({site_id})",
            f"Equipment:  {equipment}",
            f"Condition:  {label}",
            "",
            reason,
            "",
            "Advisory only — BMS owns emergency response.",
            "Review in Cockpit or wait for the morning digest.",
            "",
            "— SENTINEL",
        ]
    )

    html = (
        "<html><body style='font-family:monospace;font-size:14px;'>"
        f"<p><strong>SENTINEL flagged at {ts_sast}</strong></p>"
        "<table style='border-collapse:collapse;'>"
        f"<tr><td style='padding:2px 12px 2px 0;color:#666'>Building</td>"
        f"<td>{site_name} ({site_id})</td></tr>"
        f"<tr><td style='padding:2px 12px 2px 0;color:#666'>Equipment</td>"
        f"<td><code>{equipment}</code></td></tr>"
        f"<tr><td style='padding:2px 12px 2px 0;color:#666'>Condition</td>"
        f"<td><strong>{label}</strong></td></tr>"
        "</table>"
        f"<p>{reason}</p>"
        "<hr style='margin:16px 0;border:none;border-top:1px solid #ddd;'>"
        "<p style='color:#888;font-size:12px;'>"
        "Advisory only — BMS owns emergency response. "
        "Review in Cockpit or wait for the morning digest."
        "</p></body></html>"
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"SENTINEL BMS <{_from_address()}>"
    msg["To"] = _recipient()
    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))
    return msg


async def send_overnight_advisory_email(
    rec: dict[str, Any],
    site_id: str,
) -> bool:
    """Send fallback email for one unacknowledged overnight advisory.

    Returns True if sent successfully, False otherwise.
    """
    if not is_configured():
        logger.debug("[AlertEmail] SMTP not configured — skipping overnight advisory email")
        return False

    from datetime import timedelta, timezone as tz

    sast = tz(timedelta(hours=2))
    ts_raw = rec.get("timestamp") or ""
    try:
        ts_dt = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
        ts_sast = ts_dt.astimezone(sast).strftime("%H:%M SAST, %a %d %b %Y")
    except Exception:
        ts_sast = ts_raw[:16]

    msg = _build_message(rec, site_id, ts_sast)
    to_addr = _recipient()

    host = settings.notification_smtp_host
    port = settings.notification_smtp_port
    username = settings.notification_smtp_username
    password = settings.notification_smtp_password
    use_tls = settings.notification_smtp_use_tls

    try:
        is_implicit_tls = port == 465
        await aiosmtplib.send(
            msg,
            hostname=host,
            port=port,
            username=username,
            password=password,
            use_tls=use_tls and is_implicit_tls,
            start_tls=use_tls and not is_implicit_tls,
        )
        logger.info(
            "[AlertEmail] Overnight advisory email sent for rec %s → %s",
            rec.get("id"),
            to_addr,
        )
        return True
    except Exception as exc:
        logger.warning(
            "[AlertEmail] Failed to send overnight advisory email for rec %s: %s",
            rec.get("id"),
            exc,
        )
        return False
