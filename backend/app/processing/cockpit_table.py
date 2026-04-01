"""Cockpit issue tabular processing.

Owns all normalisation, deduplication, ranking, source-status computation,
and audit-trail assembly for the cockpit issue feed.

Receives pre-fetched ``list[dict]`` rows from three sources (BMS alerts,
email intakes, work orders) and returns typed schema objects.

Polars adoption path
--------------------
The heavy operations are ``fuse()`` → ``_dedupe()`` (sort + bucket) and
``_build_source_statuses()`` (max-per-source).  Replace those internals with
Polars expressions; the method signatures are the stable contract.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from app.schemas.cockpit import (
    CockpitActionAudit,
    CockpitIssue,
    CockpitIssueEvidenceRef,
    CockpitIssueLocation,
    CockpitSourceStatus,
    IssueSeverity,
    IssueSource,
    IssueCategory,
    IssueSubsystem,
)

# ---------------------------------------------------------------------------
# Constants (moved here so callers import from one place)
# ---------------------------------------------------------------------------

SOURCE_ORDER: list[str] = ["bms", "intake", "tech"]

SOURCE_THRESHOLDS: dict[str, dict[str, int]] = {
    "bms":    {"healthy": 45,  "degraded": 45,  "stale": 90,   "unavailable": 300},
    "intake": {"healthy": 180, "degraded": 180, "stale": 600,  "unavailable": 1800},
    "tech":   {"healthy": 300, "degraded": 300, "stale": 900,  "unavailable": 3600},
}

SEVERITY_MAP: dict[str, int] = {"critical": 4, "high": 3, "medium": 2, "low": 1}


# ---------------------------------------------------------------------------
# Internal record type — pure data, no I/O
# ---------------------------------------------------------------------------

@dataclass
class _NormalizedIssue:
    issue: CockpitIssue
    priority: int
    dedupe_key: str
    updated_at: datetime


# ---------------------------------------------------------------------------
# Processor
# ---------------------------------------------------------------------------

class CockpitTableProcessor:
    """Pure tabular shaping for the cockpit issue feed.

    All methods are static and side-effect free.  No database access.
    """

    @staticmethod
    def fuse(
        alerts: list[dict[str, Any]],
        intakes: list[dict[str, Any]],
        work_orders: list[dict[str, Any]],
        audit_logs: list[dict[str, Any]],
        selected_issue_id: str | None,
        *,
        bridge_last_updated: datetime | None = None,
    ) -> tuple[list[CockpitIssue], list[CockpitSourceStatus], list[CockpitActionAudit], str | None]:
        """Combine three issue sources into a deduplicated, ranked feed.

        Args:
            alerts:            BMS alert rows (source = "bms", priority 0).
            intakes:           Email intake rows (source = "intake", priority 1).
            work_orders:       Work-order rows (source = "tech", priority 2).
            audit_logs:        Audit-trail rows (pre-merged by the caller).
            selected_issue_id: ID to keep selected; falls back to top issue.

        Returns:
            (issues, source_statuses, audit_trail, selected_id)
        """
        normalized: list[_NormalizedIssue] = []
        normalized.extend(CockpitTableProcessor._to_normalized_issues(alerts,      source="bms",    priority=0))
        normalized.extend(CockpitTableProcessor._to_normalized_issues(intakes,     source="intake", priority=1))
        normalized.extend(CockpitTableProcessor._to_normalized_issues(work_orders, source="tech",   priority=2))

        deduped = CockpitTableProcessor._dedupe(normalized)

        selected = selected_issue_id
        if selected and selected not in {item.issue.id for item in deduped}:
            selected = None
        if not selected and deduped:
            selected = deduped[0].issue.id

        source_statuses = CockpitTableProcessor._build_source_statuses(
            alerts,
            intakes,
            work_orders,
            bridge_last_updated=bridge_last_updated,
        )
        audit_trail = CockpitTableProcessor._build_audit_trail(audit_logs)
        return [item.issue for item in deduped], source_statuses, audit_trail, selected

    # ------------------------------------------------------------------
    # Normalisation
    # ------------------------------------------------------------------

    @staticmethod
    def _to_normalized_issues(
        entries: Iterable[dict[str, Any]],
        source: IssueSource,
        priority: int,
    ) -> list[_NormalizedIssue]:
        normalized = []
        for entry in entries:
            issue = CockpitTableProcessor._entry_to_issue(entry, source)
            if not issue:
                continue
            dedupe_key = CockpitTableProcessor._build_dedupe_key(entry, issue, source)
            normalized.append(
                _NormalizedIssue(
                    issue=issue,
                    priority=priority,
                    dedupe_key=dedupe_key,
                    updated_at=CockpitTableProcessor._parse_datetime(issue.updated_at),
                )
            )
        return normalized

    @staticmethod
    def _entry_to_issue(entry: dict[str, Any], source: IssueSource) -> CockpitIssue | None:
        now = datetime.now(UTC)
        equipment_id = entry.get("equipment_id") or entry.get("equipment_code")
        zone_ids = entry.get("zone_ids") or ([entry.get("zone_id")] if entry.get("zone_id") else [])
        floor_id = entry.get("floor_id") or entry.get("level")
        severity = CockpitTableProcessor._map_severity(entry.get("severity"))
        issue_id = entry.get("id") or entry.get("issue_id") or str(uuid4())
        updated_at = CockpitTableProcessor._parse_datetime(entry.get("updated_at")) or now
        opened_at = CockpitTableProcessor._parse_datetime(entry.get("created_at")) or updated_at
        sla_due = updated_at + timedelta(minutes=20)
        issue_category = CockpitTableProcessor._normalize_issue_category(
            entry.get("type") or entry.get("issue_category") or entry.get("category")
        )
        subsystem = CockpitTableProcessor._infer_subsystem(equipment_id, issue_category, source)
        constraint_type = CockpitTableProcessor._infer_constraint_type(issue_category, subsystem)
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
            confidence=CockpitTableProcessor._severity_to_confidence(severity),
            confidence_label=f"{severity.capitalize()} confidence",
            issue_category=issue_category,
            subsystem=subsystem,
            constraint_type=constraint_type,
            location=CockpitIssueLocation(
                zone_ids=[z for z in (zone_ids or []) if z],
                asset_ids=[equipment_id] if equipment_id else [],
                floor_id=floor_id,
            ),
            evidence_refs=CockpitTableProcessor._extract_evidence(entry, source),
            source_record_id=entry.get("id"),
        )

    @staticmethod
    def _map_severity(value: str | None) -> IssueSeverity:
        if not value:
            return "medium"
        normalized = value.lower()
        return normalized if normalized in SEVERITY_MAP else "medium"

    @staticmethod
    def _severity_to_confidence(severity: IssueSeverity) -> float:
        return {"critical": 0.95, "high": 0.8, "medium": 0.6, "low": 0.4}.get(severity, 0.5)

    @staticmethod
    def _normalize_issue_category(value: str | None) -> IssueCategory:
        if not value:
            return "general"
        normalized = value.strip().lower().replace(" ", "_")
        if normalized in {"thermal", "temperature", "comfort"}:
            return "thermal"
        if normalized in {"fault", "failure", "alarm"}:
            return "fault"
        if normalized in {"energy", "power", "cost"}:
            return "energy"
        if normalized in {"occupant", "complaint", "meeting"}:
            return "occupant"
        if normalized in {"stability", "cycling", "volatile", "oscillation"}:
            return "stability"
        if normalized in {"security", "access", "intrusion"}:
            return "security"
        if normalized in {"water", "leak", "plumbing"}:
            return "water"
        return "general"

    @staticmethod
    def _infer_subsystem(equipment_id: str | None, category: IssueCategory, source: IssueSource) -> IssueSubsystem:
        asset_type = None
        if equipment_id:
            parts = equipment_id.split("-")
            if len(parts) > 1:
                asset_type = parts[1].upper()

        if asset_type in {"CHILLER", "AHU", "FCU", "VAV", "PUMP", "CT"}:
            return "hvac"
        if asset_type in {"UPS", "GEN", "INV", "MTR"} or category == "energy":
            return "power"
        if asset_type in {"DALI", "LTG", "DALI_CONTROLLER"}:
            return "lighting"
        if category == "security":
            return "security"
        if category == "water":
            return "water"
        if category == "occupant" or source == "tech":
            return "occupancy"
        return "general"

    @staticmethod
    def _infer_constraint_type(category: IssueCategory, subsystem: IssueSubsystem):
        if category == "thermal" or subsystem == "hvac":
            return "comfort"
        if category == "fault":
            return "asset"
        if category == "energy" or subsystem == "power":
            return "energy"
        if category == "occupant" or subsystem == "occupancy":
            return "occupant"
        if category == "stability":
            return "stability"
        return "general"

    @staticmethod
    def _extract_evidence(entry: dict[str, Any], source: IssueSource) -> list[CockpitIssueEvidenceRef]:
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

    # ------------------------------------------------------------------
    # Deduplication & ranking
    # ------------------------------------------------------------------

    @staticmethod
    def _build_dedupe_key(entry: dict[str, Any], issue: CockpitIssue, source: IssueSource) -> str:
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

    @staticmethod
    def _dedupe(normalized: Iterable[_NormalizedIssue]) -> list[_NormalizedIssue]:
        now = datetime.now(UTC)

        def _sort_key(item: _NormalizedIssue) -> tuple[int, bool, float, float, int, str]:
            updated = item.updated_at or datetime.fromtimestamp(0, tz=UTC)
            severity_score = SEVERITY_MAP[item.issue.severity]
            sla_seconds = CockpitTableProcessor._time_to_sla_due(item.issue, now)
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
            if not existing or CockpitTableProcessor._should_override(existing, entry, now):
                bucket[entry.dedupe_key] = entry
        return sorted(bucket.values(), key=_sort_key)

    @staticmethod
    def _should_override(current: _NormalizedIssue, candidate: _NormalizedIssue, now: datetime) -> bool:
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
        candidate_sla = CockpitTableProcessor._time_to_sla_due(candidate.issue, now)
        current_sla = CockpitTableProcessor._time_to_sla_due(current.issue, now)
        if candidate_sla != current_sla:
            return candidate_sla < current_sla
        candidate_updated = candidate.updated_at or datetime.fromtimestamp(0, tz=UTC)
        current_updated = current.updated_at or datetime.fromtimestamp(0, tz=UTC)
        if candidate_updated != current_updated:
            return candidate_updated > current_updated
        return candidate.issue.id < current.issue.id

    # ------------------------------------------------------------------
    # Source status
    # ------------------------------------------------------------------

    @staticmethod
    def _build_source_statuses(
        alerts: list[dict[str, Any]],
        intakes: list[dict[str, Any]],
        work_orders: list[dict[str, Any]],
        *,
        bridge_last_updated: datetime | None = None,
    ) -> list[CockpitSourceStatus]:
        now = datetime.now(UTC)
        entries = {"bms": alerts, "intake": intakes, "tech": work_orders}
        statuses = []
        for source, items in entries.items():
            last_updated = max(
                (CockpitTableProcessor._parse_datetime(item.get("updated_at")) for item in items if item.get("updated_at")),
                default=None,
            )
            if source == "bms" and bridge_last_updated:
                last_updated = max(last_updated, bridge_last_updated) if last_updated else bridge_last_updated
            statuses.append(CockpitTableProcessor._build_source_status(source, last_updated, now))
        return statuses

    @staticmethod
    def _build_source_status(source: str, last_updated: datetime | None, now: datetime) -> CockpitSourceStatus:
        thresholds = SOURCE_THRESHOLDS[source]
        if not last_updated:
            return CockpitSourceStatus(
                source=source,
                label=source.upper(),
                state="unavailable",
                badge_tone="critical",
                last_updated_at=None,
                freshness_seconds=None,
                stale_after_seconds=thresholds["stale"],
                degraded_after_seconds=thresholds["degraded"],
                degraded_confidence=True,
                message="Source unavailable",
            )
        freshness_seconds = int((now - last_updated).total_seconds())
        if freshness_seconds <= thresholds["healthy"]:
            state, tone, message = "healthy", "normal", f"Data fresh ({freshness_seconds}s)"
        elif freshness_seconds <= thresholds["stale"]:
            state, tone, message = "degraded", "warning", f"Data lagging ({freshness_seconds}s)"
        elif freshness_seconds <= thresholds["unavailable"]:
            state, tone, message = "stale", "critical", f"Data stale ({freshness_seconds}s)"
        else:
            state, tone, message = "unavailable", "critical", f"Source unavailable ({freshness_seconds}s)"
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

    # ------------------------------------------------------------------
    # Audit trail
    # ------------------------------------------------------------------

    @staticmethod
    def _build_audit_trail(entries: list[dict[str, Any]]) -> list[CockpitActionAudit]:
        audits: list[CockpitActionAudit] = []
        sorted_entries = sorted(
            entries,
            key=lambda data: (
                CockpitTableProcessor._parse_datetime(data.get("timestamp") or data.get("occurred_at"))
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
                    occurred_at=CockpitTableProcessor._parse_datetime(entry.get("timestamp")) or datetime.now(UTC),
                    outcome="success" if entry.get("result") == "SUCCESS" else "failed",
                    status_before="new",
                    status_after="triaged",
                    notes=entry.get("notes"),
                    evidence_refs=entry.get("metadata", {}).get("evidence_refs", []),
                    work_order_id=entry.get("metadata", {}).get("work_order_id"),
                )
            )
        return audits[:10]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(value).replace(tzinfo=UTC)
        except Exception:
            return None

    @staticmethod
    def _time_to_sla_due(issue: CockpitIssue, now: datetime) -> float:
        sla_due = CockpitTableProcessor._parse_datetime(issue.sla_due_at)
        if sla_due is None:
            return float("inf")
        return (sla_due - now).total_seconds()
