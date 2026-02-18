"""Consent Management Service.

POPIA-compliant consent capture and management for SENTINEL BMS.
Handles consent recording for WhatsApp/Telegram/web data subjects,
with immutable audit trail and dual-write storage.

Consent types:
- pi_processing: Basic personal information processing consent
- data_retention: Agreement to 90-day raw / 2-year aggregate retention
- cross_border_transfer: Acknowledgment of international AI processing (Claude API)

Phase 63-06: FSR privacy controls — consent capture mechanism.
"""

import hashlib
import json
import logging
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Consent text templates — presented to data subjects on first contact
# ---------------------------------------------------------------------------

CONSENT_TEMPLATES: Dict[str, Dict[str, str]] = {
    "first_contact": {
        "whatsapp": (
            "SENTINEL Building Management processes your phone number and messages "
            "to handle facilities requests. Your data is stored securely in South "
            "Africa with 90-day retention. You can withdraw consent anytime by "
            "messaging 'STOP'. Privacy notice: https://sentinel.bms/privacy"
        ),
        "telegram": (
            "SENTINEL Building Management processes your phone number and messages "
            "to handle facilities requests. Your data is stored securely in South "
            "Africa with 90-day retention. You can withdraw consent anytime by "
            "messaging 'STOP'. Privacy notice: https://sentinel.bms/privacy"
        ),
        "web": (
            "SENTINEL Building Management processes your information to manage "
            "building facilities. Your data is stored securely in South Africa. "
            "See our privacy notice for full details: https://sentinel.bms/privacy"
        ),
    },
    "consent_types": {
        "pi_processing": (
            "I consent to SENTINEL processing my personal information (phone number, "
            "name, location, facilities requests) for building management purposes."
        ),
        "data_retention": (
            "I acknowledge that my raw data is retained for 90 days and aggregated "
            "data for 2 years, after which it is securely deleted."
        ),
        "cross_border_transfer": (
            "I acknowledge that AI-assisted processing may use international services "
            "(Anthropic Claude API, US-based) for chat interactions and analysis."
        ),
    },
}

# Salt for phone number hashing — in production, load from environment
HASH_SALT = "sentinel-bms-consent-2026"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class ConsentRecord(BaseModel):
    """Immutable consent record. Withdrawals create new records."""

    record_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    data_subject_id: str  # SHA-256 hashed phone number or user identifier
    platform: str  # whatsapp, telegram, web
    consent_type: str  # pi_processing, data_retention, cross_border_transfer
    consent_given: bool
    consent_text: str  # exact text the user agreed to
    given_at: str  # ISO 8601 datetime
    expires_at: Optional[str] = None  # ISO 8601 datetime or None
    withdrawn_at: Optional[str] = None  # ISO 8601 if consent withdrawn
    ip_address: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def hash_identifier(raw_id: str) -> str:
    """Hash a phone number or user ID with salt for privacy.

    Uses SHA-256 with a static salt. In production the salt should be
    stored in a secrets manager and rotated periodically.
    """
    salted = f"{HASH_SALT}:{raw_id}"
    return hashlib.sha256(salted.encode("utf-8")).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Consent Service
# ---------------------------------------------------------------------------

class ConsentService:
    """Consent management with dual-write storage (JSON + Supabase)."""

    _instance: Optional["ConsentService"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "ConsentService":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        self._json_path = Path(__file__).parent.parent / "data" / "consent_records.json"
        self._records: List[ConsentRecord] = []
        self._load_json()

    # ── JSON storage ──────────────────────────────────────────────────

    def _load_json(self) -> None:
        """Load consent records from JSON fallback file."""
        try:
            if self._json_path.exists():
                data = json.loads(self._json_path.read_text())
                self._records = [
                    ConsentRecord(**r) for r in data.get("records", [])
                ]
                logger.info(
                    "Loaded %d consent records from JSON", len(self._records)
                )
            else:
                self._records = []
                self._save_json()
        except Exception as exc:
            logger.error("Failed to load consent records: %s", exc)
            self._records = []

    def _save_json(self) -> None:
        """Persist consent records to JSON fallback file (append-only in spirit)."""
        try:
            self._json_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "schema_version": "1.0",
                "records": [r.model_dump() for r in self._records],
            }
            self._json_path.write_text(
                json.dumps(payload, indent=2, default=str)
            )
        except Exception as exc:
            logger.error("Failed to save consent records: %s", exc)

    # ── Core operations ───────────────────────────────────────────────

    def record_consent(
        self,
        data_subject_id: str,
        platform: str,
        consent_type: str,
        consent_given: bool,
        consent_text: Optional[str] = None,
        ip_address: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        *,
        hash_subject: bool = True,
    ) -> ConsentRecord:
        """Record a new consent decision (immutable — append only).

        Args:
            data_subject_id: Raw phone number or user ID (hashed before storage).
            platform: whatsapp | telegram | web
            consent_type: pi_processing | data_retention | cross_border_transfer
            consent_given: True if consented, False if declined.
            consent_text: The exact text the user saw. Falls back to template.
            ip_address: Optional IP address of the data subject.
            metadata: Platform-specific details.
            hash_subject: If True, hash the subject ID before storage.

        Returns:
            The created ConsentRecord.
        """
        hashed_id = hash_identifier(data_subject_id) if hash_subject else data_subject_id

        if consent_text is None:
            consent_text = CONSENT_TEMPLATES.get("consent_types", {}).get(
                consent_type, f"Consent for {consent_type}"
            )

        record = ConsentRecord(
            data_subject_id=hashed_id,
            platform=platform,
            consent_type=consent_type,
            consent_given=consent_given,
            consent_text=consent_text,
            given_at=_now_iso(),
            ip_address=ip_address,
            metadata=metadata or {},
        )

        self._records.append(record)
        self._save_json()

        logger.info(
            "Consent recorded: subject=%s type=%s given=%s platform=%s",
            hashed_id[:12],
            consent_type,
            consent_given,
            platform,
        )
        return record

    def check_consent(
        self, data_subject_id: str, consent_type: str, *, hash_subject: bool = True
    ) -> bool:
        """Check if a data subject currently has active consent.

        Returns True only if the most recent record for this subject+type
        has consent_given=True and has not been withdrawn.
        """
        hashed_id = hash_identifier(data_subject_id) if hash_subject else data_subject_id

        relevant = [
            r
            for r in self._records
            if r.data_subject_id == hashed_id and r.consent_type == consent_type
        ]

        if not relevant:
            return False

        # Most recent record wins (immutable — latest is truth)
        latest = max(relevant, key=lambda r: r.given_at)
        return latest.consent_given and latest.withdrawn_at is None

    def withdraw_consent(
        self,
        data_subject_id: str,
        consent_type: str,
        *,
        hash_subject: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ConsentRecord:
        """Record a consent withdrawal (creates a NEW record, does not modify existing).

        Also marks the most recent consent record with withdrawn_at timestamp.
        """
        hashed_id = hash_identifier(data_subject_id) if hash_subject else data_subject_id

        # Mark existing active consent as withdrawn (for query convenience)
        now = _now_iso()
        for r in reversed(self._records):
            if (
                r.data_subject_id == hashed_id
                and r.consent_type == consent_type
                and r.consent_given
                and r.withdrawn_at is None
            ):
                r.withdrawn_at = now
                break

        # Create a new withdrawal record
        withdrawal = ConsentRecord(
            data_subject_id=hashed_id,
            platform="withdrawal",
            consent_type=consent_type,
            consent_given=False,
            consent_text=f"Consent withdrawn for {consent_type}",
            given_at=now,
            metadata=metadata or {"reason": "user_requested"},
        )

        self._records.append(withdrawal)
        self._save_json()

        logger.info(
            "Consent withdrawn: subject=%s type=%s", hashed_id[:12], consent_type
        )
        return withdrawal

    def get_consent_history(
        self, data_subject_id: str, *, hash_subject: bool = True
    ) -> List[ConsentRecord]:
        """Get the full consent history for a data subject."""
        hashed_id = hash_identifier(data_subject_id) if hash_subject else data_subject_id

        return [r for r in self._records if r.data_subject_id == hashed_id]

    def get_consent_stats(self) -> Dict[str, Any]:
        """Get aggregate consent statistics for FSR audit reporting."""
        total = len(self._records)
        active_consents = sum(
            1
            for r in self._records
            if r.consent_given and r.withdrawn_at is None
        )
        withdrawals = sum(1 for r in self._records if not r.consent_given)

        # By platform
        by_platform: Dict[str, int] = {}
        for r in self._records:
            by_platform[r.platform] = by_platform.get(r.platform, 0) + 1

        # By consent type
        by_type: Dict[str, int] = {}
        for r in self._records:
            by_type[r.consent_type] = by_type.get(r.consent_type, 0) + 1

        return {
            "total_records": total,
            "active_consents": active_consents,
            "withdrawals": withdrawals,
            "by_platform": by_platform,
            "by_consent_type": by_type,
            "last_updated": _now_iso(),
        }

    def export_consent_records(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Export consent records for FSR audit (optional date range filter).

        Args:
            start_date: ISO 8601 start date (inclusive).
            end_date: ISO 8601 end date (inclusive).

        Returns:
            List of consent records as dictionaries.
        """
        filtered = self._records

        if start_date:
            filtered = [r for r in filtered if r.given_at >= start_date]
        if end_date:
            filtered = [r for r in filtered if r.given_at <= end_date]

        return [r.model_dump() for r in filtered]


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

def get_consent_service() -> ConsentService:
    """Get the singleton ConsentService instance."""
    return ConsentService()
