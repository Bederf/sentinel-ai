"""Visitor Email Service — sends confirmation emails with QR code + PIN.

Sends an HTML email to the visitor confirming their appointment details,
including an inline QR code image and their PIN for manual check-in fallback.

Env vars:
    SMTP_HOST     — SMTP server hostname
    SMTP_PORT     — SMTP port (default 587)
    SMTP_USER     — SMTP username
    SMTP_PASSWORD — SMTP password
    SMTP_FROM     — From address (e.g. reception@company.com)
    SMTP_FROM_NAME — Display name (default "Reception")
    SMTP_USE_TLS  — Use TLS (default true)
    DEV_EMAIL_LOG — If set, log email content instead of sending (dev mode)
"""

from __future__ import annotations

import logging
import os
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib

from app.database.repositories.visit_repository import BuildingMapRepository
from app.models.visit import Visit

logger = logging.getLogger(__name__)

# Default SMTP settings
DEFAULT_SMTP_PORT = 587
DEFAULT_SMTP_USE_TLS = True


def _smtp_config() -> dict:
    """Return SMTP configuration from environment variables."""
    return {
        "host": os.getenv("SMTP_HOST", "").strip(),
        "port": int(os.getenv("SMTP_PORT", str(DEFAULT_SMTP_PORT))),
        "username": os.getenv("SMTP_USER", "").strip(),
        "password": os.getenv("SMTP_PASSWORD", "").strip(),
        "from_addr": os.getenv("SMTP_FROM", "").strip(),
        "from_name": os.getenv("SMTP_FROM_NAME", "Reception").strip(),
        "use_tls": os.getenv("SMTP_USE_TLS", "true").lower() in ("true", "1", "yes"),
        "dev_log": bool(os.getenv("DEV_EMAIL_LOG", "").strip()),
    }


def _build_html_email(visit: Visit, building_name: str, host_name: str) -> str:
    """Build the HTML body for a visitor confirmation email."""
    date_str = visit.meeting_start.strftime("%A %d %B %Y")
    time_str = visit.meeting_start.strftime("%H:%M")
    end_time_str = visit.meeting_end.strftime("%H:%M")

    # PIN display box
    pin_display = (
        f'<div style="background:#f0f4ff;border:2px solid #1a73e8;'
        f'border-radius:8px;padding:16px 24px;display:inline-block;margin:16px 0">'
        f'<div style="font-size:12px;color:#555;margin-bottom:4px">YOUR ACCESS PIN</div>'
        f'<div style="font-size:32px;font-weight:700;color:#1a73e8;letter-spacing:4px">'
        f"{visit.pin}</div>"
        f"</div>"
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Your Visit to {building_name}</title>
</head>
<body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:24px;color:#222">
  <div style="background:#1a73e8;padding:24px;border-radius:8px 8px 0 0">
    <h1 style="color:#fff;margin:0;font-size:22px">
      &#x1F4EC; You are expected at {building_name}
    </h1>
  </div>

  <div style="background:#f8f9fa;padding:24px;border:1px solid #e0e0e0;border-top:none">
    <p style="margin:0 0 16px">
      <strong>{host_name}</strong> is expecting you.
    </p>

    <table style="width:100%;border-collapse:collapse;margin-bottom:16px">
      <tr>
        <td style="padding:8px 0;color:#555;font-size:14px">Building</td>
        <td style="padding:8px 0;font-weight:600">{building_name}</td>
      </tr>
      <tr>
        <td style="padding:8px 0;color:#555;font-size:14px">Date</td>
        <td style="padding:8px 0;font-weight:600">{date_str}</td>
      </tr>
      <tr>
        <td style="padding:8px 0;color:#555;font-size:14px">Time</td>
        <td style="padding:8px 0;font-weight:600">{time_str} - {end_time_str}</td>
      </tr>
      <tr>
        <td style="padding:8px 0;color:#555;font-size:14px">Host</td>
        <td style="padding:8px 0;font-weight:600">{host_name}</td>
      </tr>
    </table>

    <p style="font-size:13px;color:#555;margin-bottom:8px">
      Present the QR code below or enter your PIN at the reception kiosk on arrival.
    </p>

    {pin_display}

    <div style="margin-top:16px">
      <p style="font-size:12px;color:#999;margin:0">
        If you did not expect this invitation, please disregard this email.
      </p>
    </div>
  </div>
</body>
</html>"""
    return html


def _build_plain_email(visit: Visit, building_name: str, host_name: str) -> str:
    """Build the plain-text body for a visitor confirmation email."""
    date_str = visit.meeting_start.strftime("%A %d %B %Y")
    time_str = visit.meeting_start.strftime("%H:%M")
    end_time_str = visit.meeting_end.strftime("%H:%M")

    return (
        f"You are expected at {building_name}.\n\n"
        f"Host: {host_name}\n"
        f"Date: {date_str}\n"
        f"Time: {time_str} - {end_time_str}\n"
        f"\n"
        f"Your QR code and PIN are in the HTML version of this email.\n"
        f"Present them at reception on arrival.\n\n"
        f"Your PIN: {visit.pin}\n\n"
        f"If you did not expect this invitation, please disregard this email."
    )


class VisitorEmailService:
    """Sends visitor confirmation emails with QR code inline image and PIN."""

    def __init__(self) -> None:
        self._config = _smtp_config()
        self._building_map_repo = BuildingMapRepository()

    def _get_building_name(self, building_id: str) -> str:
        """Return a human-readable building name for a site_id."""
        try:
            maps = self._building_map_repo.list_building_maps()
            for bm in maps:
                if bm.site_id == building_id:
                    return bm.name
        except Exception:
            pass
        return building_id  # Fallback to raw site_id

    def _get_host_name(self, visit: Visit) -> str:
        """Return the host name, trying AD lookup if email is available."""
        if visit.host_name:
            return visit.host_name
        try:
            from app.services.active_directory_service import ActiveDirectoryService

            ad = ActiveDirectoryService()
            details = ad.get_host_details(visit.host_email)
            if details and details.get("name"):
                return details["name"]
        except Exception:
            pass
        return visit.host_email

    def send_visitor_confirmation(self, visit: Visit) -> bool:
        """Send a confirmation email to the visitor.

        Returns True if the email was sent (or logged in dev mode),
        False if it was skipped due to missing config.
        """
        to_email = visit.visitor_email
        if not to_email or "@" not in to_email:
            logger.warning("Cannot send email — no valid visitor email for visit %s", visit.id)
            return False

        building_name = self._get_building_name(visit.building_id)
        host_name = self._get_host_name(visit)

        subject = f"Your visit to {building_name} on {visit.meeting_start.strftime('%d %b')}"
        body_html = _build_html_email(visit, building_name, host_name)
        body_plain = _build_plain_email(visit, building_name, host_name)

        # Dev mode: log and skip sending
        if self._config["dev_log"]:
            logger.info(
                "[DEV EMAIL] To: %s | Subject: %s | Host: %s | Building: %s | Date: %s %s-%s | PIN: %s",
                to_email,
                subject,
                host_name,
                building_name,
                visit.meeting_start.strftime("%Y-%m-%d"),
                visit.meeting_start.strftime("%H:%M"),
                visit.meeting_end.strftime("%H:%M"),
                visit.pin,
            )
            return True

        # Check SMTP config
        if not self._config["host"]:
            logger.warning(
                "SMTP not configured — email to %s not sent (DEV_EMAIL_LOG not set). "
                "Set SMTP_HOST, SMTP_USER, SMTP_PASSWORD, SMTP_FROM to enable sending.",
                to_email,
            )
            return False

        return self._send_email(
            to_email=to_email,
            subject=subject,
            body_plain=body_plain,
            body_html=body_html,
            qr_code_base64=visit.qr_code,
        )

    def _send_email(
        self,
        to_email: str,
        subject: str,
        body_plain: str,
        body_html: str,
        qr_code_base64: str | None = None,
    ) -> bool:
        """Send an email via SMTP with optional inline QR code image."""
        from_addr = f"{self._config['from_name']} <{self._config['from_addr']}>"

        msg = MIMEMultipart("mixed")
        msg["From"] = from_addr
        msg["To"] = to_email
        msg["Subject"] = subject

        # Multipart alternative for plain + HTML
        alt = MIMEMultipart("alternative")
        alt.attach(MIMEText(body_plain, "plain"))
        alt.attach(MIMEText(body_html, "html"))
        msg.attach(alt)

        # Attach QR code as inline image
        if qr_code_base64:
            import base64

            try:
                # Remove data URI prefix if present
                data = qr_code_base64
                if "," in qr_code_base64:
                    data = qr_code_base64.split(",", 1)[1]
                image_bytes = base64.b64decode(data)
                img = MIMEImage(image_bytes, _subtype="png")
                img.add_header("Content-ID", "<visitor_qr_code>")
                img.add_header("Content-Disposition", "inline", filename="qr_code.png")
                msg.attach(img)
            except Exception as exc:
                logger.warning("Failed to attach QR code image: %s", exc)

        # Send
        try:
            import asyncio

            # Run synchronous send in a thread pool to avoid blocking
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(
                    aiosmtplib.send(
                        msg,
                        hostname=self._config["host"],
                        port=self._config["port"],
                        username=self._config["username"],
                        password=self._config["password"],
                        use_tls=self._config["use_tls"],
                        start_tls=self._config["use_tls"],
                    )
                )
            finally:
                loop.close()

            logger.info("Visitor email sent to %s", to_email)
            return True

        except Exception as exc:
            logger.error("Failed to send visitor email to %s: %s", to_email, exc)
            return False
