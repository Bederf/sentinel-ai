"""POPIA data subject request workflow service."""

from __future__ import annotations

import json
import logging
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.config.settings import settings
from app.services.consent_service import hash_identifier

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _utc_iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


@dataclass(frozen=True)
class RequestStatus:
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    FULFILLED = "fulfilled"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    EXPIRED = "expired"

    CLOSED_STATES = {FULFILLED, REJECTED, CANCELLED, EXPIRED}


class PrivacyRequest(BaseModel):
    """Single POPIA data-subject request entry."""

    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    data_subject_hash: str
    request_type: str
    channel: str
    status: str = RequestStatus.PENDING
    details: str = ""
    requested_by: str
    assigned_to: str | None = None
    created_at: str
    due_at: str
    closed_at: str | None = None
    outcome_summary: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PrivacyRequestService:
    """JSON-backed POPIA request workflow with SLA tracking."""

    _instance: PrivacyRequestService | None = None
    _instance_lock = threading.Lock()

    def __new__(cls) -> PrivacyRequestService:
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        self._lock = threading.Lock()
        self._path = Path(__file__).parent.parent / "data" / "privacy_requests.json"
        self._requests: list[PrivacyRequest] = []
        self._load()

    def _load(self) -> None:
        try:
            if self._path.exists():
                payload = json.loads(self._path.read_text())
                self._requests = [PrivacyRequest(**item) for item in payload.get("requests", [])]
            else:
                self._requests = []
                self._save()
        except Exception as exc:
            logger.error("Failed loading privacy requests: %s", exc)
            self._requests = []

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": "1.0",
            "updated_at": _utc_iso(_utc_now()),
            "requests": [item.model_dump() for item in self._requests],
        }
        self._path.write_text(json.dumps(payload, indent=2))

    def _refresh_expired(self) -> None:
        now = _utc_now()
        changed = False
        for item in self._requests:
            if item.status in RequestStatus.CLOSED_STATES:
                continue
            due_at = _parse_iso(item.due_at)
            if due_at and due_at < now:
                item.status = RequestStatus.EXPIRED
                item.closed_at = _utc_iso(now)
                if not item.outcome_summary:
                    item.outcome_summary = "Automatically marked expired due to SLA breach"
                changed = True
        if changed:
            self._save()

    def submit_request(
        self,
        *,
        data_subject_id: str,
        request_type: str,
        channel: str,
        details: str,
        requested_by: str,
        metadata: dict[str, Any] | None = None,
        due_days: int | None = None,
    ) -> PrivacyRequest:
        with self._lock:
            now = _utc_now()
            due_delta = timedelta(days=due_days or settings.popia_dsr_sla_days)
            request = PrivacyRequest(
                data_subject_hash=hash_identifier(data_subject_id),
                request_type=request_type,
                channel=channel,
                details=details.strip(),
                requested_by=requested_by,
                created_at=_utc_iso(now),
                due_at=_utc_iso(now + due_delta),
                metadata=metadata or {},
            )
            self._requests.append(request)
            self._save()
            logger.info(
                "Privacy request created: request_id=%s type=%s due_at=%s",
                request.request_id,
                request.request_type,
                request.due_at,
            )
            return request

    def get_request(self, request_id: str) -> PrivacyRequest | None:
        self._refresh_expired()
        for item in self._requests:
            if item.request_id == request_id:
                return item
        return None

    def list_requests(
        self,
        *,
        status: str | None = None,
        include_closed: bool = True,
        overdue_only: bool = False,
    ) -> list[PrivacyRequest]:
        self._refresh_expired()
        now = _utc_now()
        filtered = list(self._requests)

        if status:
            filtered = [item for item in filtered if item.status == status]
        if not include_closed:
            filtered = [item for item in filtered if item.status not in RequestStatus.CLOSED_STATES]
        if overdue_only:
            overdue: list[PrivacyRequest] = []
            for item in filtered:
                due_at = _parse_iso(item.due_at)
                if due_at and due_at < now and item.status not in RequestStatus.CLOSED_STATES:
                    overdue.append(item)
            filtered = overdue

        return sorted(filtered, key=lambda item: item.created_at, reverse=True)

    def update_request(
        self,
        request_id: str,
        *,
        status: str,
        assigned_to: str | None = None,
        outcome_summary: str | None = None,
        evidence_refs: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> PrivacyRequest | None:
        with self._lock:
            request = self.get_request(request_id)
            if not request:
                return None

            request.status = status
            if assigned_to is not None:
                request.assigned_to = assigned_to
            if outcome_summary is not None:
                request.outcome_summary = outcome_summary
            if evidence_refs is not None:
                request.evidence_refs = evidence_refs
            if metadata:
                request.metadata.update(metadata)

            if status in RequestStatus.CLOSED_STATES:
                request.closed_at = _utc_iso(_utc_now())
            else:
                request.closed_at = None

            self._save()
            logger.info("Privacy request updated: request_id=%s status=%s", request_id, status)
            return request

    def get_metrics(self) -> dict[str, Any]:
        self._refresh_expired()
        now = _utc_now()

        total = len(self._requests)
        open_requests = [item for item in self._requests if item.status not in RequestStatus.CLOSED_STATES]
        overdue_count = 0
        closed_within_sla = 0
        closed_total = 0

        for item in self._requests:
            due_at = _parse_iso(item.due_at)
            if due_at and item.status not in RequestStatus.CLOSED_STATES and due_at < now:
                overdue_count += 1

            if item.status in RequestStatus.CLOSED_STATES and item.closed_at:
                closed_total += 1
                closed_at = _parse_iso(item.closed_at)
                if due_at and closed_at and closed_at <= due_at:
                    closed_within_sla += 1

        sla_percent = round((closed_within_sla / closed_total) * 100, 2) if closed_total else 100.0

        by_status: dict[str, int] = {}
        by_type: dict[str, int] = {}
        for item in self._requests:
            by_status[item.status] = by_status.get(item.status, 0) + 1
            by_type[item.request_type] = by_type.get(item.request_type, 0) + 1

        return {
            "total_requests": total,
            "open_requests": len(open_requests),
            "overdue_requests": overdue_count,
            "closed_requests": closed_total,
            "closed_within_sla": closed_within_sla,
            "sla_compliance_percent": sla_percent,
            "by_status": by_status,
            "by_type": by_type,
            "updated_at": _utc_iso(now),
        }


def get_privacy_request_service() -> PrivacyRequestService:
    """Return singleton privacy request service."""
    return PrivacyRequestService()
