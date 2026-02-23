"""Unit tests for POPIA retention enforcement service."""

from datetime import datetime, timedelta, timezone
import json

import pytest

from app.services.popia_retention_service import POPIARetentionService, RetentionRule


def _iso_days_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


@pytest.mark.unit
def test_retention_enforcement_deletes_overdue_records(tmp_path):
    """Retention enforcement should delete records older than configured cutoff."""
    source_file = tmp_path / "consent_records.json"
    runs_file = tmp_path / "runs.json"
    source_file.write_text(
        json.dumps(
            {
                "records": [
                    {"record_id": "old", "given_at": _iso_days_ago(3650)},
                    {"record_id": "new", "given_at": _iso_days_ago(2)},
                ]
            }
        )
    )

    service = POPIARetentionService()
    service._rules = [
        RetentionRule(
            category="consent_records",
            file_path=source_file,
            list_key="records",
            timestamp_field="given_at",
            retention_days=365,
        )
    ]
    service._runs_path = runs_file

    summary = service.enforce_policies(dry_run=False)
    assert summary["total_deleted"] == 1
    assert summary["total_reviewed"] == 2

    payload = json.loads(source_file.read_text())
    assert len(payload["records"]) == 1
    assert payload["records"][0]["record_id"] == "new"


@pytest.mark.unit
def test_retention_status_reports_overdue_counts(tmp_path):
    """Status should include overdue count for monitored categories."""
    source_file = tmp_path / "privacy_requests.json"
    source_file.write_text(
        json.dumps(
            {
                "requests": [
                    {"request_id": "r1", "status": "fulfilled", "closed_at": _iso_days_ago(800)},
                    {"request_id": "r2", "status": "in_progress", "created_at": _iso_days_ago(1)},
                ]
            }
        )
    )

    service = POPIARetentionService()
    service._rules = [
        RetentionRule(
            category="privacy_requests",
            file_path=source_file,
            list_key="requests",
            timestamp_field="created_at",
            retention_days=365,
            require_closed=True,
            use_closed_at_field="closed_at",
        )
    ]
    service._runs_path = tmp_path / "runs.json"

    status = service.get_retention_status()
    assert status["records_overdue"] == 1
    assert status["records_reviewed"] == 1
