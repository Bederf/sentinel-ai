"""Backend SMTP Reply Service — Phase 131.2b.

Sends threaded email replies with proper RFC 822 headers (In-Reply-To,
References, Message-ID) so replies appear in the same conversation thread
in Gmail, Outlook, and other mail clients.

Feature-flagged: only active when ``email_reply_enabled=true``.
Reuses existing ``notification_smtp_*`` settings for SMTP transport.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib

from app.config.settings import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class ReplyResult:
    """Outcome of an attempted email reply."""

    sent: bool = False
    message_id: str | None = None
    references: str | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class EmailReplyService:
    """Async SMTP service for sending threaded email replies."""

    def is_configured(self) -> bool:
        """Return True if SMTP credentials and feature flag are set."""
        return bool(
            settings.email_reply_enabled
            and settings.notification_smtp_host
            and settings.notification_smtp_username
            and settings.notification_smtp_password
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def send_reply(
        self,
        *,
        to_email: str,
        to_name: str | None,
        subject: str,
        body_plain: str,
        body_html: str | None,
        in_reply_to: str | None = None,
        references: str | None = None,
    ) -> ReplyResult:
        """Send a threaded reply via SMTP.

        Args:
            to_email: Recipient address.
            to_name: Recipient display name (optional).
            subject: Reply subject (should already include "Re: " prefix).
            body_plain: Plain-text body.
            body_html: HTML body (optional, creates multipart/alternative).
            in_reply_to: The inbound Message-ID we are replying to.
            references: The inbound References header chain.

        Returns:
            ReplyResult with sent status, outbound Message-ID, and any error.
        """
        if not self.is_configured():
            return ReplyResult(error="Email reply service not configured")

        try:
            msg = self._build_message(
                to_email=to_email,
                to_name=to_name,
                subject=subject,
                body_plain=body_plain,
                body_html=body_html,
                in_reply_to=in_reply_to,
                references=references,
            )

            outbound_message_id = msg["Message-ID"]
            outbound_references = msg.get("References")

            # Port 587 uses STARTTLS (upgrade from plain); port 465 uses implicit TLS
            is_implicit_tls = settings.notification_smtp_port == 465
            await aiosmtplib.send(
                msg,
                hostname=settings.notification_smtp_host,
                port=settings.notification_smtp_port,
                username=settings.notification_smtp_username,
                password=settings.notification_smtp_password,
                use_tls=settings.notification_smtp_use_tls and is_implicit_tls,
                start_tls=settings.notification_smtp_use_tls and not is_implicit_tls,
            )

            logger.info(
                "Threaded reply sent to %s (Message-ID: %s)",
                to_email,
                outbound_message_id,
            )
            return ReplyResult(
                sent=True,
                message_id=outbound_message_id,
                references=outbound_references,
            )

        except Exception as exc:
            logger.error("Failed to send threaded reply to %s: %s", to_email, exc)
            return ReplyResult(error=str(exc))

    # ------------------------------------------------------------------
    # Message building
    # ------------------------------------------------------------------

    def _build_message(
        self,
        *,
        to_email: str,
        to_name: str | None,
        subject: str,
        body_plain: str,
        body_html: str | None,
        in_reply_to: str | None,
        references: str | None,
    ) -> MIMEMultipart:
        """Build a multipart/alternative MIME message with threading headers."""
        msg = MIMEMultipart("alternative")

        # Addressing
        from_addr = f"{settings.email_reply_from_name} <{settings.email_reply_from_address}>"
        to_addr = f"{to_name} <{to_email}>" if to_name else to_email

        msg["From"] = from_addr
        msg["To"] = to_addr
        msg["Subject"] = subject
        msg["Date"] = datetime.now(UTC).strftime("%a, %d %b %Y %H:%M:%S +0000")

        # Unique Message-ID for the outbound reply
        msg["Message-ID"] = self._generate_message_id()

        # RFC 822 threading headers
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
        msg["References"] = self._build_references_chain(in_reply_to, references)

        # Auto-reply marker (RFC 3834) — tells receiving MTA this is automated
        msg["Auto-Submitted"] = "auto-replied"
        msg["X-Auto-Response-Suppress"] = "OOF, DR, AutoReply"

        # Attach bodies (plain first, then HTML — mail clients pick the last they support)
        msg.attach(MIMEText(body_plain, "plain", "utf-8"))
        if body_html:
            msg.attach(MIMEText(body_html, "html", "utf-8"))

        return msg

    # ------------------------------------------------------------------
    # Threading helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_message_id() -> str:
        """Generate a globally unique Message-ID."""
        domain = (
            settings.email_reply_from_address.split("@")[-1]
            if "@" in settings.email_reply_from_address
            else "sentinel-ai.co.za"
        )
        return f"<sentinel-{uuid.uuid4().hex[:16]}@{domain}>"

    @staticmethod
    def _build_references_chain(
        in_reply_to: str | None,
        existing_references: str | None,
    ) -> str:
        """Build the References header per RFC 2822 Section 3.6.4.

        The References header should contain the Message-IDs of the entire
        thread in order. We append the in_reply_to to the existing chain.
        """
        refs: list[str] = []

        # Parse existing References header (space or newline-separated Message-IDs)
        if existing_references:
            for token in existing_references.split():
                token = token.strip()
                if token.startswith("<") and token.endswith(">") and token not in refs:
                    refs.append(token)

        # Append the Message-ID we are replying to (if not already present)
        if in_reply_to:
            clean = in_reply_to.strip()
            if clean and clean not in refs:
                refs.append(clean)

        return " ".join(refs)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_service: EmailReplyService | None = None


def get_email_reply_service() -> EmailReplyService:
    """Get singleton EmailReplyService."""
    global _service
    if _service is None:
        _service = EmailReplyService()
    return _service
