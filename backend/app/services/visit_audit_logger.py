"""Visit Audit Logger — records all visit lifecycle events to JSON.

Event types:
- SCAN: visitor scanned QR/PIN at reception
- REGISTER: visitor name/photo captured by reception
- APPROVE: host approved via WhatsApp YES
- DENY: host denied via WhatsApp NO
- ACCESS_ISSUED: access card issued to visitor
- ACCESS_REVOKED: access revoked
- EXPIRED: visit window elapsed
"""

from __future__ import annotations

import json
import logging
import shutil
import tempfile
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from filelock import FileLock

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent.parent / "data"
AUDIT_LOG_PATH = DATA_DIR / "visit_audit_log.json"
AUDIT_LOCK_PATH = DATA_DIR / "visit_audit_log.lock"


class VisitEventType(StrEnum):
    """All recordable visit lifecycle events."""

    SCAN = "SCAN"
    REGISTER = "REGISTER"
    APPROVE = "APPROVE"
    DENY = "DENY"
    ACCESS_ISSUED = "ACCESS_ISSUED"
    ACCESS_REVOKED = "ACCESS_REVOKED"
    EXPIRED = "EXPIRED"


class VisitAuditLogger:
    """Append-only audit log for visit events.

    Thread-safe using FileLock. JSON file rotation via temp file + rename.
    """

    def __init__(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)

    def _read_log(self) -> dict:
        """Read the audit log, returning an empty structure if missing."""
        if not AUDIT_LOG_PATH.exists():
            return {"events": []}
        try:
            with open(AUDIT_LOG_PATH) as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to read visit_audit_log.json: %s", exc)
            return {"events": []}

    def _write_log(self, data: dict) -> None:
        """Atomically write the audit log using temp file + rename."""
        dirname = AUDIT_LOG_PATH.parent
        with tempfile.NamedTemporaryFile(mode="w", dir=dirname, delete=False) as tmp:
            json.dump(data, tmp, indent=2, default=str)
            tmp_path = Path(tmp.name)
        shutil.move(str(tmp_path), str(AUDIT_LOG_PATH))

    def _with_lock(self, func):
        """Execute func while holding a FileLock."""
        lock = FileLock(AUDIT_LOCK_PATH, timeout=10)
        with lock:
            return func()

    def log_event(
        self,
        event_type: VisitEventType,
        visit_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Record an audit event.

        Args:
            event_type: The type of visit event (SCAN, REGISTER, APPROVE, etc.)
            visit_id: UUID of the related visit (if applicable)
            details: Additional structured data about the event
        """
        event = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event_type": event_type.value,
            "visit_id": str(visit_id) if visit_id else None,
            "details": details or {},
        }

        def _append():
            data = self._read_log()
            data["events"].append(event)
            self._write_log(data)
            logger.info(f"[VisitAudit] {event_type.value} @ {event['timestamp']} (visit={visit_id or 'N/A'})")

        try:
            self._with_lock(_append)
        except Exception as e:
            logger.error("Failed to write visit audit event: %s", e)
            raise  # Surface failure — audit writes must not be silently swallowed
