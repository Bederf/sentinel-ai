from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.services.cockpit_issue_fusion import CockpitIssueFusionService


class _NoOpRepo:
    def __init__(self) -> None:
        self.client = None

    def get_active_by_site(self, site_id: str | None = None) -> list[dict[str, Any]]:
        return []

    def get_all(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return []


def _now() -> datetime:
    return datetime.now(UTC)


def test_dedupe_prefers_bms_alert_over_intake():
    service = CockpitIssueFusionService(
        alert_repo=_NoOpRepo(),
        email_repo=_NoOpRepo(),
        work_order_repo=_NoOpRepo(),
        audit_repo=_NoOpRepo(),
    )
    timestamp = _now()
    bms_entry = {
        "id": "alert-1",
        "site_id": "S002",
        "equipment_id": "S002-CHILLER-B1-001",
        "type": "fault",
        "title": "Chiller fault",
        "summary": "BMS alert summary",
        "severity": "critical",
        "status": "active",
        "updated_at": timestamp.isoformat(),
        "created_at": timestamp.isoformat(),
    }
    intake_entry = {
        "id": "intake-1",
        "site_id": "S002",
        "equipment_id": "S002-CHILLER-B1-001",
        "type": "fault",
        "title": "Email fault",
        "summary": "Intake summary",
        "severity": "low",
        "status": "new",
        "updated_at": timestamp.isoformat(),
        "created_at": timestamp.isoformat(),
    }

    issues, _, _, _ = service.aggregate(
        "S002",
        alert_entries=[bms_entry],
        intake_entries=[intake_entry],
        work_order_entries=[],
    )

    assert len(issues) == 1
    assert issues[0].source == "bms"
    assert issues[0].title == "Chiller fault"


def test_dedupe_runs_against_zone_when_equipment_missing():
    service = CockpitIssueFusionService(
        alert_repo=_NoOpRepo(),
        email_repo=_NoOpRepo(),
        work_order_repo=_NoOpRepo(),
        audit_repo=_NoOpRepo(),
    )
    timestamp = _now()
    bms_entry = {
        "id": "alert-2",
        "site_id": "S002",
        "zone_id": "Zone-L4-Boardroom-A",
        "type": "thermal",
        "title": "Zone drift",
        "summary": "Zone drift summary",
        "severity": "high",
        "status": "active",
        "updated_at": timestamp.isoformat(),
        "created_at": timestamp.isoformat(),
    }
    intake_entry = {
        "id": "intake-2",
        "site_id": "S002",
        "zone_id": "Zone-L4-Boardroom-A",
        "type": "thermal",
        "title": "Human report",
        "summary": "Human report summary",
        "severity": "medium",
        "status": "new",
        "updated_at": timestamp.isoformat(),
        "created_at": timestamp.isoformat(),
    }

    issues, _, _, _ = service.aggregate(
        "S002",
        alert_entries=[bms_entry],
        intake_entries=[intake_entry],
        work_order_entries=[],
    )

    assert len(issues) == 1
    assert issues[0].location.zone_ids == ["Zone-L4-Boardroom-A"]


def test_selected_issue_id_preserved_when_present():
    service = CockpitIssueFusionService(
        alert_repo=_NoOpRepo(),
        email_repo=_NoOpRepo(),
        work_order_repo=_NoOpRepo(),
        audit_repo=_NoOpRepo(),
    )
    timestamp = _now()
    first_entry = {
        "id": "alert-3",
        "site_id": "S002",
        "equipment_id": "EQ-1",
        "type": "fault",
        "title": "First issue",
        "summary": "First summary",
        "severity": "critical",
        "status": "active",
        "updated_at": timestamp.isoformat(),
        "created_at": timestamp.isoformat(),
    }
    second_entry = {
        "id": "intake-3",
        "site_id": "S002",
        "equipment_id": "EQ-2",
        "type": "fault",
        "title": "Second issue",
        "summary": "Second summary",
        "severity": "medium",
        "status": "new",
        "updated_at": timestamp.isoformat(),
        "created_at": timestamp.isoformat(),
    }

    _, _, _, selected = service.aggregate(
        "S002",
        alert_entries=[first_entry],
        intake_entries=[second_entry],
        work_order_entries=[],
        selected_issue_id=second_entry["id"],
    )

    assert selected == second_entry["id"]

    _, _, _, fallback = service.aggregate(
        "S002",
        alert_entries=[first_entry],
        intake_entries=[second_entry],
        work_order_entries=[],
        selected_issue_id="missing",
    )

    assert fallback == first_entry["id"]


def test_bms_source_becomes_stale_when_freshness_exceeded():
    service = CockpitIssueFusionService(
        alert_repo=_NoOpRepo(),
        email_repo=_NoOpRepo(),
        work_order_repo=_NoOpRepo(),
        audit_repo=_NoOpRepo(),
    )
    stale_time = _now() - timedelta(seconds=200)
    fresh_time = _now()
    stale_entry = {
        "id": "alert-4",
        "site_id": "S002",
        "equipment_id": "EQ-3",
        "type": "fault",
        "title": "Stale issue",
        "summary": "Stale summary",
        "severity": "high",
        "status": "active",
        "updated_at": stale_time.isoformat(),
        "created_at": stale_time.isoformat(),
    }
    fresh_intake = {
        "id": "intake-4",
        "site_id": "S002",
        "equipment_id": "EQ-4",
        "type": "report",
        "title": "Fresh intake",
        "summary": "Fresh summary",
        "severity": "low",
        "status": "new",
        "updated_at": fresh_time.isoformat(),
        "created_at": fresh_time.isoformat(),
    }

    _, statuses, _, _ = service.aggregate(
        "S002",
        alert_entries=[stale_entry],
        intake_entries=[fresh_intake],
        work_order_entries=[],
    )

    bms = next(status for status in statuses if status.source == "bms")
    assert bms.state == "stale"
    assert bms.degraded_confidence


def test_issue_ordering_prioritizes_severity_unresolved_and_sla():
    service = CockpitIssueFusionService(
        alert_repo=_NoOpRepo(),
        email_repo=_NoOpRepo(),
        work_order_repo=_NoOpRepo(),
        audit_repo=_NoOpRepo(),
    )
    timestamp = _now()
    critical_new_soon = {
        "id": "alert-5",
        "site_id": "S002",
        "equipment_id": "EQ-5",
        "type": "fault",
        "title": "Soon SLA",
        "summary": "Critical soon",
        "severity": "critical",
        "status": "new",
        "updated_at": timestamp.isoformat(),
        "created_at": timestamp.isoformat(),
        "sla_due_at": (timestamp + timedelta(minutes=5)).isoformat(),
    }
    critical_new_late = {
        "id": "alert-6",
        "site_id": "S002",
        "equipment_id": "EQ-6",
        "type": "fault",
        "title": "Late SLA",
        "summary": "Critical later",
        "severity": "critical",
        "status": "new",
        "updated_at": timestamp.isoformat(),
        "created_at": timestamp.isoformat(),
        "sla_due_at": (timestamp + timedelta(minutes=20)).isoformat(),
    }
    critical_resolved = {
        "id": "alert-7",
        "site_id": "S002",
        "equipment_id": "EQ-7",
        "type": "fault",
        "title": "Resolved issue",
        "summary": "Critical resolved",
        "severity": "critical",
        "status": "resolved",
        "updated_at": timestamp.isoformat(),
        "created_at": timestamp.isoformat(),
        "sla_due_at": (timestamp + timedelta(minutes=30)).isoformat(),
    }
    high_new = {
        "id": "alert-8",
        "site_id": "S002",
        "equipment_id": "EQ-8",
        "type": "fault",
        "title": "High issue",
        "summary": "High severity",
        "severity": "high",
        "status": "new",
        "updated_at": timestamp.isoformat(),
        "created_at": timestamp.isoformat(),
        "sla_due_at": (timestamp + timedelta(minutes=10)).isoformat(),
    }

    issues, _, _, _ = service.aggregate(
        "S002",
        alert_entries=[critical_resolved, high_new, critical_new_late, critical_new_soon],
        intake_entries=[],
        work_order_entries=[],
    )

    assert issues[0].id == critical_new_soon["id"]
    assert issues[1].id == critical_new_late["id"]
    assert issues[2].id == critical_resolved["id"]
    assert issues[3].id == high_new["id"]


def test_issue_ordering_prefers_recent_updates_when_sla_ties():
    service = CockpitIssueFusionService(
        alert_repo=_NoOpRepo(),
        email_repo=_NoOpRepo(),
        work_order_repo=_NoOpRepo(),
        audit_repo=_NoOpRepo(),
    )
    timestamp = _now()
    sla_due = (timestamp + timedelta(minutes=15)).isoformat()
    older_issue = {
        "id": "alert-9",
        "site_id": "S002",
        "equipment_id": "EQ-9",
        "type": "fault",
        "title": "Older update",
        "summary": "Older summary",
        "severity": "critical",
        "status": "new",
        "updated_at": timestamp.isoformat(),
        "created_at": timestamp.isoformat(),
        "sla_due_at": sla_due,
    }
    newer_issue = {
        "id": "alert-10",
        "site_id": "S002",
        "equipment_id": "EQ-10",
        "type": "fault",
        "title": "Newer update",
        "summary": "Newer summary",
        "severity": "critical",
        "status": "new",
        "updated_at": (timestamp + timedelta(minutes=1)).isoformat(),
        "created_at": timestamp.isoformat(),
        "sla_due_at": sla_due,
    }

    issues, _, _, _ = service.aggregate(
        "S002",
        alert_entries=[older_issue, newer_issue],
        intake_entries=[],
        work_order_entries=[],
    )

    assert issues[0].id == newer_issue["id"]
    assert issues[1].id == older_issue["id"]
