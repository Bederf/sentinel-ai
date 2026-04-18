"""Email Intake IMAP Poller — Phase 189.

Polls intelligence_intake_imap_* mailbox every 5 minutes via APScheduler.
Parses emails using email_intake_agent.process_email().
Writes records to Supabase email_intakes table.

NOT related to Space Concierge POC (booking confirmations on Windows machine).
"""

from __future__ import annotations

import email
import hashlib
import imaplib
import logging
from pathlib import Path
from typing import Any

from app.config.settings import settings
from app.database.repositories.email_intake_repository import (
    EmailIntakeRepository,
    get_email_intake_repository,
)
from app.services.email_intake_agent import EmailIntakeResult, process_email

logger = logging.getLogger(__name__)


class EmailIntakeService:
    """IMAP poller for the intelligence intake mailbox."""

    def __init__(self) -> None:
        self._repo: EmailIntakeRepository = get_email_intake_repository()
        self._last_uid_file = Path(__file__).parent.parent / "data" / "email_intake_last_uid.txt"

    def _is_configured(self) -> bool:
        return bool(settings.intelligence_intake_imap_host)

    def poll(self) -> list[EmailIntakeResult]:
        """Poll mailbox, process new emails, return results."""
        if not self._is_configured():
            logger.debug("[EmailIntake] IMAP not configured — skipping poll")
            return []

        try:
            return self._poll_impl()
        except Exception as e:
            logger.error(f"[EmailIntake] Poll failed: {e}")
            return []

    def _poll_impl(self) -> list[EmailIntakeResult]:
        # Connect
        mail = imaplib.IMAP4_SSL(
            host=settings.intelligence_intake_imap_host,
            port=settings.intelligence_intake_imap_port or 993,
        )
        mail.login(
            settings.intelligence_intake_imap_username,
            settings.intelligence_intake_imap_password,
        )
        mail.select(settings.intelligence_intake_imap_folder or "INBOX")

        # Find last seen UID
        last_uid = self._read_last_uid()

        # Search for new messages (UID > last_uid)
        status, messages = mail.search(None, f"UID {last_uid + 1}:*")
        if status != "OK":
            mail.logout()
            return []

        email_ids = messages[0].split()
        if not email_ids:
            mail.logout()
            return []

        results = []
        for email_id in email_ids:
            status, msg_data = mail.fetch(email_id, "(RFC822)")
            if status != "OK":
                continue

            raw_email_bytes = msg_data[0][1]
            msg = email.message_from_bytes(raw_email_bytes)

            # Parse
            parsed = self._parse_email(msg)
            if not parsed:
                continue

            # Skip duplicates (match on message_id hash)
            msg_hash = hashlib.sha256((parsed["message_id"] or "").encode()).hexdigest()
            if self._repo.email_exists_hash(msg_hash):
                logger.debug(f"[EmailIntake] Skipping duplicate: {parsed['message_id']}")
                # Still update last_uid so we don't re-check next poll
                uid = self._extract_uid(email_id)
                if uid:
                    self._write_last_uid(uid)
                continue

            # Process via LLM agent (sync wrapper)
            result = process_email(parsed)
            if not result:
                continue

            # Persist
            self._repo.upsert_email_intake(result, msg_hash=msg_hash)
            results.append(result)

            # Update last seen UID
            uid = self._extract_uid(email_id)
            if uid:
                self._write_last_uid(uid)

        mail.logout()
        return results

    def _parse_email(self, msg: email.message.Message) -> dict[str, Any] | None:
        try:
            message_id = msg.get("Message-ID", "")
            subject = msg.get("Subject", "(no subject)")
            sender = msg.get("From", "")
            date_str = msg.get("Date", "")

            # Extract body
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        payload = part.get_payload(decode=True)
                        if payload:
                            body = payload.decode(errors="replace")
                        break
            else:
                payload = msg.get_payload(decode=True)
                if payload:
                    body = payload.decode(errors="replace")

            return {
                "message_id": message_id,
                "subject": subject,
                "from": sender,
                "body": body,
                "date_str": date_str,
            }
        except Exception as e:
            logger.warning(f"[EmailIntake] Failed to parse email: {e}")
            return None

    def _extract_uid(self, email_id: bytes) -> int | None:
        # email_id format from search: b'1 2 3' or b'5'
        try:
            return int(email_id)
        except (ValueError, TypeError):
            return None

    def _read_last_uid(self) -> int:
        try:
            return int(self._last_uid_file.read_text().strip())
        except (FileNotFoundError, ValueError):
            return 0

    def _write_last_uid(self, uid: int) -> None:
        self._last_uid_file.parent.mkdir(parents=True, exist_ok=True)
        self._last_uid_file.write_text(str(uid))
