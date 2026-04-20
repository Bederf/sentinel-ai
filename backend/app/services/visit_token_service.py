"""Token service for visit management.

Generates:
- UUID tokens (QR payload)
- 6-digit zero-padded PINs (manual fallback)
- QR codes (base64 PNG of UUID string + SENTINEL logo overlay)
"""

from __future__ import annotations

import base64
import io
import random
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import qrcode
from PIL import Image, ImageDraw
from qrcode.constants import ERROR_CORRECT_H

from app.database.repositories.visit_repository import VisitRepository
from app.models.visit import Visit, VisitStatus

_LOGO_PATH = Path(__file__).parent.parent.parent / "assets" / "sentinel-logo.png"
_QR_DARK = "#0a0f1e"  # SENTINEL navy
_QR_LIGHT = "#ffffff"
_LOGO_RATIO = 0.25  # logo occupies 25% of QR width


class VisitTokenService:
    """Service for generating and validating visit tokens, PINs, and QR codes."""

    PIN_MIN = 0
    PIN_MAX = 999999
    QR_ERROR_CORRECTION = ERROR_CORRECT_H

    def __init__(self, repo: VisitRepository | None = None) -> None:
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
        """Generate a branded base64 PNG QR code with SENTINEL logo overlay.

        Uses ERROR_CORRECT_H (30% recovery) so the logo cutout doesn't break
        scannability. Logo is centred in a white circular badge.
        Returns a base64-encoded PNG string.
        """
        qr = qrcode.QRCode(
            version=1,
            error_correction=self.QR_ERROR_CORRECTION,
            box_size=10,
            border=2,
        )
        qr.add_data(str(token))
        qr.make(fit=True)
        img = qr.make_image(fill_color=_QR_DARK, back_color=_QR_LIGHT).convert("RGBA")

        # Overlay logo if available
        if _LOGO_PATH.exists():
            qr_size = img.size[0]
            logo_size = int(qr_size * _LOGO_RATIO)

            logo = Image.open(_LOGO_PATH).convert("RGBA")
            logo = logo.resize((logo_size, logo_size), Image.LANCZOS)

            # White circular badge behind logo
            badge_size = int(logo_size * 1.3)
            badge = Image.new("RGBA", (badge_size, badge_size), (0, 0, 0, 0))
            draw = ImageDraw.Draw(badge)
            draw.ellipse((0, 0, badge_size, badge_size), fill=(255, 255, 255, 255))

            # Centre logo on badge
            logo_offset = (badge_size - logo_size) // 2
            badge.paste(logo, (logo_offset, logo_offset), logo)

            # Centre badge on QR
            pos = ((qr_size - badge_size) // 2, (qr_size - badge_size) // 2)
            img.paste(badge, pos, badge)

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
        host_name: str | None = None,
        host_mobile: str | None = None,
        visitor_name: str | None = None,
        visitor_vehicle: str | None = None,
        status: VisitStatus = VisitStatus.CREATED,
    ) -> tuple[Visit, str]:
        """Create a new Visit record with token + PIN + QR code.

        Args:
            status: Initial visit status. Use PENDING for invites awaiting visitor acceptance.

        Returns:
            Tuple of (Visit model, qr_code_base64 string)
        """
        now = datetime.now(UTC)
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
            status=status,
            qr_code=qr_code,
            created_at=now,
            updated_at=now,
        )

        self._repo.create_visit(visit)
        return visit, qr_code

    # -------------------------------------------------------------------------
    # Validation
    # -------------------------------------------------------------------------

    def validate_token(self, token: uuid.UUID) -> Visit | None:
        """Validate a token lookup.

        Returns the Visit if found, regardless of time window.
        Returns None if token is not found.
        """
        return self._repo.get_visit_by_token(token)

    def validate_pin(self, pin: str) -> Visit | None:
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
        now = datetime.now(UTC)

        meeting_start = visit.meeting_start
        if meeting_start.tzinfo is None:
            meeting_start = meeting_start.replace(tzinfo=UTC)

        meeting_end = visit.meeting_end
        if meeting_end.tzinfo is None:
            meeting_end = meeting_end.replace(tzinfo=UTC)

        window_start = meeting_start - timedelta(minutes=30)
        window_end = meeting_end + timedelta(minutes=60)

        return window_start <= now <= window_end
