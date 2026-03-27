from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from app.database.repositories.alert_repository import AlertRepository, get_alert_repository
from app.database.repositories.audit_repository import AuditRepository
from app.database.repositories.email_intake_repository import EmailIntakeRepository, get_email_intake_repository
from app.database.repositories.work_order_repository import WorkOrderRepository, get_work_order_repository
from app.schemas.cockpit import (
    CockpitActionAudit,
    CockpitIssue,
    CockpitIssueEvidenceRef,
    CockpitIssueLocation,
    CockpitSourceStatus,
    IssueSeverity,
    IssueSource,
)

SOURCE_ORDER = ["bms", "intake", "tech"]
SOURCE_THRESHOLDS = {
    "bms": {"healthy": 45, "degraded": 45, "stale": 90, "unavailable": 300},
    "intake": {"healthy": 180, "degraded": 180, "stale": 600, "unavailable": 1800},
    "tech": {"healthy": 300, "degraded": 300, "stale": 900, "unavailable": 3600},
}

SEVERITY_MAP = {"critical": 4, "high": 3, "medium": 2, "low": 1}


@dataclass
class _NormalizedIssue:
    issue: CockpitIssue
    priority: int
    dedupe_key: str
    updated_at: datetime


class CockpitIssueFusionService:
    def __init__(
        self,
        alert_repo: AlertRepository | None = None,
        email_repo: EmailIntakeRepository | None = None,
        work_order_repo: WorkOrderRepository | None = None,
        audit_repo: AuditRepository | None = None,
    ):
        self.alert_repo = alert_repo or get_alert_repository()
        self.email_repo = email_repo or get_email_intake_repository()
        self.work_order_repo = work_order_repo or get_work_order_repository()
        self.audit_repo = audit_repo or AuditRepository()

    def aggregate(
        self,
        site_id: str,
        selected_issue_id: str | None = None,
        *,
        alert_entries: list[dict[str, Any]] | None = None,
        intake_entries: list[dict[str, Any]] | None = None,
        work_order_entries: list[dict[str, Any]] | None = None,
        audit_entries: list[dict[str, Any]] | None = None,
        local_audit_entries: list[dict[str, Any]] | None = None,
    ) -> tuple[list[CockpitIssue], list[CockpitSourceStatus], list[CockpitActionAudit], str | None]:
        alerts = alert_entries if alert_entries is not None else self._fetch_alerts(site_id)
        intakes = intake_entries if intake_entries is not None else self._fetch_intakes(site_id)
        work_orders = work_order_entries if work_order_entries is not None else self._fetch_work_orders(site_id)
        audit_logs = audit_entries if audit_entries is not None else self._fetch_audit_logs(site_id)
        if local_audit_entries:
            audit_logs = local_audit_entries + audit_logs

        normalized = []
        normalized.extend(self._to_normalized_issues(alerts, source="bms", priority=0))
        normalized.extend(self._to_normalized_issues(intakes, source="intake", priority=1))
        normalized.extend(self._to_normalized_issues(work_orders, source="tech", priority=2))

        deduped = self._dedupe(normalized)

        selected = selected_issue_id
        if selected and selected not in {item.issue.id for item in deduped}:
            selected = None
        if not selected and deduped:
            selected = deduped[0].issue.id

        source_statuses = self._build_source_statuses(alerts, intakes, work_orders)
        return [item.issue for item in deduped], source_statuses, self._build_audit_trail(audit_logs), selected

    def _fetch_alerts(self, site_id: str) -> list[dict[str, Any]]:
        try:
            return self.alert_repo.get_active_by_site(site_id)
        except Exception:
            return []

    def _fetch_intakes(self, site_id: str) -> list[dict[str, Any]]:
        try:
            client = self.email_repo.client
            if client:
                response = (
                    client.table("email_intakes")
                    .select("*")
                    .eq("site_id", site_id)
                    .in_("pipeline_status", ["received", "enriched"])
                    .order("created_at", desc=True)
                    .limit(10)
                    .execute()
                )
                return response.data or []
        except Exception:
            pass
        return self._filter_json_intakes(site_id)

    def _fetch_work_orders(self, site_id: str) -> list[dict[str, Any]]:
        try:
            client = self.work_order_repo.client
            if client:
                response = (
                    client.table("work_orders")
                    .select("*")
                    .eq("site_id", site_id)
                    .neq("status", "completed")
                    .order("updated_at", desc=True)
                    .limit(10)
                    .execute()
                )
                return response.data or []
        except Exception:
            pass
        return []

    def _fetch_audit_logs(self, site_id: str) -> list[dict[str, Any]]:
        try:
            entries = self.audit_repo.get_all(limit=10, offset=0)
            return [entry for entry in entries if entry.get("metadata", {}).get("site_id") == site_id]
        except Exception:
            return []

    def _filter_json_intakes(self, site_id: str) -> list[dict[str, Any]]:
        try:
            with open(self.email_repo._json_path()) as f:
                records = json.load(f)
        except Exception:
            return []
        cutoff = datetime.now(UTC) - timedelta(hours=24)
        return [
            record
            for record in records
            if record.get("site_id") == site_id
            and datetime.fromisoformat(record.get("received_at")).replace(tzinfo=UTC) >= cutoff
        ]

    def _to_normalized_issues(
        self, entries: Iterable[dict[str, Any]], source: IssueSource, priority: int
    ) -> list[_NormalizedIssue]:
        normalized = []
        for entry in entries:
            issue = self._entry_to_issue(entry, source)
            if not issue:
                continue
            dedupe_key = self._build_dedupe_key(entry, issue, source)
            normalized.append(
                _NormalizedIssue(
                    issue=issue,
                    priority=priority,
                    dedupe_key=dedupe_key,
                    updated_at=self._parse_datetime(issue.updated_at),
                )
            )
        return normalized

    def _entry_to_issue(self, entry: dict[str, Any], source: IssueSource) -> CockpitIssue | None:
        now = datetime.now(UTC)
        equipment_id = entry.get("equipment_id") or entry.get("equipment_code")
        zone_ids = entry.get("zone_ids") or [entry.get("zone_id")] if entry.get("zone_id") else []
        floor_id = entry.get("floor_id") or entry.get("level")
        severity = self._map_severity(entry.get("severity"))
        issue_id = entry.get("id") or entry.get("issue_id") or str(uuid4())
        updated_at = self._parse_datetime(entry.get("updated_at")) or now
        opened_at = self._parse_datetime(entry.get("created_at")) or updated_at
        sla_due = updated_at + timedelta(minutes=20)
        return CockpitIssue(
            id=issue_id,
            title=entry.get("title") or entry.get("summary") or "Reported issue",
            summary=entry.get("message") or entry.get("description") or entry.get("issue_summary") or "",
            severity=severity,
            source=source,
            status=entry.get("status")
            if entry.get("status") in {"new", "triaged", "in_progress", "resolved"}
            else "new",
            owner=entry.get("owner") or entry.get("assigned_to"),
            owner_team=entry.get("operator_team") or entry.get("assigned_team"),
            opened_at=opened_at,
            updated_at=updated_at,
            sla_due_at=entry.get("sla_due_at") or sla_due,
            stale=False,
            impact_summary=entry.get("impact") or entry.get("impact_summary"),
            cause_hypothesis=entry.get("cause") or entry.get("cause_hypothesis"),
            recommended_action=entry.get("recommended_action"),
            confidence=self._severity_to_confidence(severity),
            confidence_label=f"{severity.capitalize()} confidence",
            location=CockpitIssueLocation(
                zone_ids=[zone for zone in (zone_ids or []) if zone],
                asset_ids=[equipment_id] if equipment_id else [],
                floor_id=floor_id,
            ),
            evidence_refs=self._extract_evidence(entry, source),
            source_record_id=entry.get("id"),
        )

    def _map_severity(self, value: str | None) -> IssueSeverity:
        if not value:
            return "medium"
        normalized = value.lower()
        if normalized in SEVERITY_MAP:
            return normalized
        return "medium"

    def _severity_to_confidence(self, severity: IssueSeverity) -> float:
        return {"critical": 0.95, "high": 0.8, "medium": 0.6, "low": 0.4}.get(severity, 0.5)

    def _extract_evidence(self, entry: dict[str, Any], source: IssueSource) -> list[CockpitIssueEvidenceRef]:
        refs = []
        if entry.get("telemetry_id"):
            refs.append(
                CockpitIssueEvidenceRef(
                    id=f"telemetry:{entry['telemetry_id']}",
                    kind="telemetry",
                    label=entry.get("telemetry_label", "Telemetry point"),
                    source=source,
                )
            )
        if entry.get("reference_id"):
            refs.append(
                CockpitIssueEvidenceRef(
                    id=str(entry["reference_id"]),
                    kind="ticket",
                    label=entry.get("reference_label", "Reference ticket"),
                    source=source,
                )
            )
        return refs

    def _build_dedupe_key(self, entry: dict[str, Any], issue: CockpitIssue, source: IssueSource) -> str:
        normalized_type = (
            (entry.get("type") or entry.get("issue_category") or entry.get("category") or source)
            .strip()
            .lower()
            .replace(" ", "_")
        )
        site_id = entry.get("site_id") or entry.get("building_id") or ""
        equipment_id = entry.get("equipment_id") or entry.get("equipment_code")
        if not equipment_id and issue.location.asset_ids:
            equipment_id = issue.location.asset_ids[0]
        if equipment_id:
            return f"{site_id}|{equipment_id}|{normalized_type}"
        zone_id = entry.get("zone_id")
        if not zone_id and issue.location.zone_ids:
            zone_id = issue.location.zone_ids[0]
        if zone_id:
            return f"{site_id}|{zone_id}|{normalized_type}"
        return f"{site_id}|unknown|{normalized_type}"

    def _dedupe(self, normalized: Iterable[_NormalizedIssue]) -> list[_NormalizedIssue]:
        now = datetime.now(UTC)

        def _sort_key(item: _NormalizedIssue) -> tuple[int, bool, float, float, int, str]:
            updated = item.updated_at or datetime.fromtimestamp(0, tz=UTC)
            severity_score = SEVERITY_MAP[item.issue.severity]
            sla_seconds = self._time_to_sla_due(item.issue, now)
            is_resolved = item.issue.status == "resolved"
            return (
                -severity_score,
                is_resolved,
                sla_seconds,
                -updated.timestamp(),
                item.priority,
                item.issue.id,
            )

        bucket: dict[str, _NormalizedIssue] = {}
        for entry in sorted(normalized, key=_sort_key):
            existing = bucket.get(entry.dedupe_key)
            if not existing or self._should_override(existing, entry, now):
                bucket[entry.dedupe_key] = entry
        return sorted(bucket.values(), key=_sort_key)

    def _should_override(self, current: _NormalizedIssue, candidate: _NormalizedIssue, now: datetime) -> bool:
        if candidate.priority != current.priority:
            return candidate.priority < current.priority
        candidate_severity = SEVERITY_MAP[candidate.issue.severity]
        current_severity = SEVERITY_MAP[current.issue.severity]
        if candidate_severity != current_severity:
            return candidate_severity > current_severity
        candidate_resolved = candidate.issue.status == "resolved"
        current_resolved = current.issue.status == "resolved"
        if candidate_resolved != current_resolved:
            return not candidate_resolved
        candidate_sla = self._time_to_sla_due(candidate.issue, now)
        current_sla = self._time_to_sla_due(current.issue, now)
        if candidate_sla != current_sla:
            return candidate_sla < current_sla
        candidate_updated = candidate.updated_at or datetime.fromtimestamp(0, tz=UTC)
        current_updated = current.updated_at or datetime.fromtimestamp(0, tz=UTC)
        if candidate_updated != current_updated:
            return candidate_updated > current_updated
        return candidate.issue.id < current.issue.id

    def _parse_datetime(self, value: Any | None) -> datetime | None:
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(value).replace(tzinfo=UTC)
        except Exception:
            return None

    def _time_to_sla_due(self, issue: CockpitIssue, now: datetime) -> float:
        sla_due = self._parse_datetime(issue.sla_due_at)
        if sla_due is None:
            return float("inf")
        return (sla_due - now).total_seconds()

    def _build_source_statuses(
        self, alerts: list[dict[str, Any]], intakes: list[dict[str, Any]], work_orders: list[dict[str, Any]]
    ) -> list[CockpitSourceStatus]:
        now = datetime.now(UTC)
        entries = {
            "bms": alerts,
            "intake": intakes,
            "tech": work_orders,
        }
        statuses = []
        for source, items in entries.items():
            last_updated = max(
                (self._parse_datetime(item.get("updated_at")) for item in items if item.get("updated_at")), default=None
            )
            statuses.append(
                self._build_source_status(source, last_updated, now),
            )
        return statuses

    def _build_source_status(self, source: str, last_updated: datetime | None, now: datetime) -> CockpitSourceStatus:
        thresholds = SOURCE_THRESHOLDS[source]
        if not last_updated:
            state = "unavailable"
            tone = "critical"
            message = "Source unavailable"
            freshness_seconds = None
        else:
            freshness_seconds = int((now - last_updated).total_seconds())
            if freshness_seconds <= thresholds["healthy"]:
                state = "healthy"
                tone = "normal"
                message = f"Data fresh ({freshness_seconds}s)"
            elif freshness_seconds <= thresholds["stale"]:
                state = "degraded"
                tone = "warning"
                message = f"Data lagging ({freshness_seconds}s)"
            elif freshness_seconds <= thresholds["unavailable"]:
                state = "stale"
                tone = "critical"
                message = f"Data stale ({freshness_seconds}s)"
            else:
                state = "unavailable"
                tone = "critical"
                message = f"Source unavailable ({freshness_seconds}s)"
        return CockpitSourceStatus(
            source=source,
            label=source.upper(),
            state=state,
            badge_tone=tone,
            last_updated_at=last_updated,
            freshness_seconds=freshness_seconds,
            stale_after_seconds=thresholds["stale"],
            degraded_after_seconds=thresholds["degraded"],
            degraded_confidence=state in {"degraded", "stale", "unavailable"},
            message=message,
        )

    def _build_audit_trail(self, entries: list[dict[str, Any]]) -> list[CockpitActionAudit]:
        audits: list[CockpitActionAudit] = []
        sorted_entries = sorted(
            entries,
            key=lambda data: (
                self._parse_datetime(data.get("timestamp") or data.get("occurred_at"))
                or datetime.fromtimestamp(0, tz=UTC)
            ),
            reverse=True,
        )
        for entry in sorted_entries:
            if not entry:
                continue
            audits.append(
                CockpitActionAudit(
                    id=entry.get("id", ""),
                    issue_id=entry.get("metadata", {}).get("issue_id", ""),
                    action=entry.get("action", "unknown"),
                    actor_type="user" if entry.get("user_id") else "system",
                    actor_id=entry.get("user_id", "system"),
                    actor_label=entry.get("user_name", "system"),
                    occurred_at=self._parse_datetime(entry.get("timestamp")) or datetime.now(UTC),
                    outcome="success" if entry.get("result") == "SUCCESS" else "failed",
                    status_before="new",
                    status_after="triaged",
                    notes=entry.get("notes"),
                    evidence_refs=entry.get("metadata", {}).get("evidence_refs", []),
                    work_order_id=entry.get("metadata", {}).get("work_order_id"),
                )
            )
        return audits[:10]
