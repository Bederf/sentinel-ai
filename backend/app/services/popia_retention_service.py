"""POPIA retention enforcement service."""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.config.settings import settings

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


@dataclass(frozen=True)
class RetentionRule:
    """Retention rule configuration for one dataset."""

    category: str
    file_path: Path
    list_key: str
    timestamp_field: str
    retention_days: int
    require_closed: bool = False
    closed_statuses: tuple[str, ...] = ("fulfilled", "rejected", "cancelled", "expired")
    closed_field: str = "status"
    use_closed_at_field: str | None = None


class POPIARetentionService:
    """File-based POPIA retention enforcement with run logs."""

    def __init__(self) -> None:
        data_dir = Path(__file__).parent.parent / "data"
        self._lock = threading.Lock()
        self._runs_path = data_dir / "popia_retention_runs.json"
        self._rules = [
            RetentionRule(
                category="consent_records",
                file_path=data_dir / "consent_records.json",
                list_key="records",
                timestamp_field="given_at",
                retention_days=settings.popia_retention_consent_days,
            ),
            RetentionRule(
                category="privacy_requests",
                file_path=data_dir / "privacy_requests.json",
                list_key="requests",
                timestamp_field="created_at",
                retention_days=settings.popia_retention_request_days,
                require_closed=True,
                use_closed_at_field="closed_at",
            ),
            RetentionRule(
                category="audit_logs",
                file_path=data_dir / "audit_log.json",
                list_key="entries",
                timestamp_field="timestamp",
                retention_days=settings.popia_retention_audit_days,
            ),
        ]

    def _load_json(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text())
        except Exception as exc:
            logger.error("Failed reading retention file %s: %s", path, exc)
            return {}

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2))

    def _load_runs(self) -> list[dict[str, Any]]:
        payload = self._load_json(self._runs_path)
        return payload.get("runs", [])

    def _append_run(self, summary: dict[str, Any]) -> None:
        runs = self._load_runs()
        runs.append(summary)
        payload = {"schema_version": "1.0", "updated_at": _iso(_utc_now()), "runs": runs[-200:]}
        self._write_json(self._runs_path, payload)

    @staticmethod
    def _is_closed(record: dict[str, Any], rule: RetentionRule) -> bool:
        status = str(record.get(rule.closed_field, "")).lower()
        return status in set(rule.closed_statuses)

    def _record_timestamp(self, record: dict[str, Any], rule: RetentionRule) -> datetime | None:
        if rule.use_closed_at_field and record.get(rule.use_closed_at_field):
            return _parse_iso(record.get(rule.use_closed_at_field))
        return _parse_iso(record.get(rule.timestamp_field))

    def get_retention_status(self) -> dict[str, Any]:
        """Return overdue counts and last run snapshot."""
        now = _utc_now()
        categories: list[dict[str, Any]] = []
        overdue_total = 0
        reviewed_total = 0

        for rule in self._rules:
            payload = self._load_json(rule.file_path)
            records = payload.get(rule.list_key, [])
            reviewed = 0
            overdue = 0
            cutoff = now - timedelta(days=rule.retention_days)

            for record in records:
                if rule.require_closed and not self._is_closed(record, rule):
                    continue
                reviewed += 1
                timestamp = self._record_timestamp(record, rule)
                if timestamp and timestamp < cutoff:
                    overdue += 1

            categories.append(
                {
                    "category": rule.category,
                    "retention_days": rule.retention_days,
                    "records_reviewed": reviewed,
                    "records_overdue": overdue,
                    "file_path": str(rule.file_path),
                }
            )
            overdue_total += overdue
            reviewed_total += reviewed

        runs = self._load_runs()
        last_run = runs[-1] if runs else None
        return {
            "categories": categories,
            "records_reviewed": reviewed_total,
            "records_overdue": overdue_total,
            "last_run": last_run,
            "updated_at": _iso(now),
        }

    def enforce_policies(self, *, dry_run: bool = True) -> dict[str, Any]:
        """Enforce retention policies across configured datasets."""
        with self._lock:
            now = _utc_now()
            summary = {
                "executed_at": _iso(now),
                "dry_run": dry_run,
                "categories": [],
                "total_reviewed": 0,
                "total_deleted": 0,
                "errors": [],
            }

            for rule in self._rules:
                try:
                    payload = self._load_json(rule.file_path)
                    records = payload.get(rule.list_key, [])
                    if not isinstance(records, list):
                        raise ValueError(f"{rule.file_path} does not contain a list at key '{rule.list_key}'")

                    kept: list[dict[str, Any]] = []
                    reviewed = 0
                    deleted = 0
                    cutoff = now - timedelta(days=rule.retention_days)

                    for record in records:
                        if rule.require_closed and not self._is_closed(record, rule):
                            kept.append(record)
                            continue

                        reviewed += 1
                        timestamp = self._record_timestamp(record, rule)
                        if timestamp and timestamp < cutoff:
                            deleted += 1
                        else:
                            kept.append(record)

                    if not dry_run:
                        payload[rule.list_key] = kept
                        payload["retention_last_enforced_at"] = _iso(now)
                        payload["retention_last_deleted_count"] = deleted
                        self._write_json(rule.file_path, payload)

                    category_summary = {
                        "category": rule.category,
                        "file_path": str(rule.file_path),
                        "reviewed": reviewed,
                        "deleted": deleted,
                        "retention_days": rule.retention_days,
                    }
                    summary["categories"].append(category_summary)
                    summary["total_reviewed"] += reviewed
                    summary["total_deleted"] += deleted
                except Exception as exc:
                    logger.error("Retention enforcement failed for %s: %s", rule.category, exc)
                    summary["errors"].append({"category": rule.category, "error": str(exc)})

            self._append_run(summary)
            logger.info(
                "POPIA retention run complete: dry_run=%s reviewed=%s deleted=%s errors=%s",
                dry_run,
                summary["total_reviewed"],
                summary["total_deleted"],
                len(summary["errors"]),
            )
            return summary


def get_popia_retention_service() -> POPIARetentionService:
    """Build retention service instance."""
    return POPIARetentionService()
