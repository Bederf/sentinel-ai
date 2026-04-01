"""Token service for visit management.

Generates:
- UUID tokens (QR payload)
- 6-digit zero-padded PINs (manual fallback)
- QR codes (base64 PNG of UUID string only)
"""

from __future__ import annotations

import base64
import io
import random
import uuid
from datetime import datetime, timezone
from typing import Optional, Tuple

import qrcode

from app.database.repositories.visit_repository import VisitRepository
from app.models.visit import Visit, VisitStatus


class VisitTokenService:
    """Service for generating and validating visit tokens, PINs, and QR codes."""

    PIN_MIN = 0
    PIN_MAX = 999999

    def __init__(self, repo: Optional[VisitRepository] = None) -> None:
        self._repo = repo or VisitRepository()

    # -------------------------------------------------------------------------
    # Generation
    # -------------------------------------------------------------------------

    def generate_token(self) -> uuid.UUID:
        """Generate a new UUID4 token (used as the QR payload)."""
        return uuid.uuid4()

    def generate_pin(self) -> str:
        """Generate a 6-digit zero-padded PIN string.

        Pins are randomly generated. In production, collision is
        astronomically unlikely (1 in 1_000_000). The repository
        enforces uniqueness at storage time.
        """
        return f"{random.randint(self.PIN_MIN, self.PIN_MAX):06d}"

    def generate_qr_code(self, token: uuid.UUID) -> str:
        """Generate a base64 PNG QR code encoding only the raw UUID string.

        Per spec: QR contains NO other visitor data — just the token UUID.
        Returns a base64-encoded PNG string (data URI prefix optional).
        """
        qr = qrcode.QRCode(version=1, box_size=10, border=2)
        qr.add_data(str(token))
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return base64.b64encode(buf.read()).decode("utf-8")

    def create_visit_token(
        self,
        visitor_email: str,
        host_email: str,
        building_id: str,
        meeting_start: datetime,
        meeting_end: datetime,
        host_name: Optional[str] = None,
        host_mobile: Optional[str] = None,
        visitor_name: Optional[str] = None,
        visitor_vehicle: Optional[str] = None,
    ) -> Tuple[Visit, str]:
        """Create a new Visit record with token + PIN + QR code.

        Returns:
            Tuple of (Visit model, qr_code_base64 string)
        """
        now = datetime.now(timezone.utc)
        token = self.generate_token()
        pin = self.generate_pin()
        qr_code = self.generate_qr_code(token)

        visit = Visit(
            id=uuid.uuid4(),
            token=token,
            pin=pin,
            visitor_email=visitor_email,
            visitor_name=visitor_name,
            host_email=host_email,
            host_name=host_name,
            host_mobile=host_mobile,
            building_id=building_id,
            meeting_start=meeting_start,
            meeting_end=meeting_end,
            status=VisitStatus.CREATED,
            qr_code=qr_code,
            created_at=now,
            updated_at=now,
        )

        self._repo.create_visit(visit)
        return visit, qr_code

    # -------------------------------------------------------------------------
    # Validation
    # -------------------------------------------------------------------------

    def validate_token(self, token: uuid.UUID) -> Optional[Visit]:
        """Validate a token lookup.

        Returns the Visit if found, regardless of time window.
        Returns None if token is not found.
        """
        return self._repo.get_visit_by_token(token)

    def validate_pin(self, pin: str) -> Optional[Visit]:
        """Validate a PIN lookup (scan PIN fallback).

        Returns the Visit if found, regardless of time window.
        Returns None if pin is not found.
        """
        return self._repo.get_visit_by_pin(pin)

    def is_valid_time_window(self, visit: Visit) -> bool:
        """Check if current time is within the valid visit window.

        Valid window: meeting_start - 30 minutes <= now <= meeting_end + 60 minutes.
        This allows early arrivals and late departures.
        """
        now = datetime.now(timezone.utc)

        # meeting_start is timezone-aware or naive
        meeting_start = visit.meeting_start
        if meeting_start.tzinfo is None:
            meeting_start = meeting_start.replace(tzinfo=timezone.utc)

        # meeting_end is timezone-aware or naive
        meeting_end = visit.meeting_end
        if meeting_end.tzinfo is None:
            meeting_end = meeting_end.replace(tzinfo=timezone.utc)

        window_start = meeting_start
        window_end = meeting_end

        # Allow 30 min early arrival
        from datetime import timedelta

        window_start = meeting_start - timedelta(minutes=30)
        # Allow 60 min grace after meeting_end
        window_end = meeting_end + timedelta(minutes=60)

        return window_start <= now <= window_end
