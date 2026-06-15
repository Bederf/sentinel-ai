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
    IssueCategory,
    IssueSeverity,
    IssueSource,
    IssueSubsystem,
)

# ---------------------------------------------------------------------------
# Constants (moved here so callers import from one place)
# ---------------------------------------------------------------------------

SOURCE_ORDER: list[str] = ["bms", "intake", "tech"]

SOURCE_THRESHOLDS: dict[str, dict[str, int]] = {
    "bms": {"healthy": 45, "degraded": 45, "stale": 90, "unavailable": 300},
    "intake": {"healthy": 180, "degraded": 180, "stale": 600, "unavailable": 1800},
    "tech": {"healthy": 300, "degraded": 300, "stale": 900, "unavailable": 3600},
    "ai": {"healthy": 3600, "degraded": 3600, "stale": 7200, "unavailable": 14400},
}

SEVERITY_MAP: dict[str, int] = {"critical": 4, "high": 3, "medium": 2, "low": 1}

# ---------------------------------------------------------------------------
# Phase 224 — cascade grouping
# ---------------------------------------------------------------------------

_CASCADE_WINDOW_MINUTES: int = 30
_PRIMARY_RAIL_LIMIT: int = 5
_SEVERITY_ORDER: dict[str, int] = {"critical": 0, "high": 1, "medium": 2, "low": 3}

_CASCADE_ELIGIBLE_TYPES: frozenset[str] = frozenset(
    {
        "co2_high",
        "co2_alert",
        "unsigned_range",
        "hvac_fault",
        "change_of_state",
        "out_of_range",
        "ahu_fault",
        "fcu_fault",
        "vav_fault",
        "temperature_high",
        "temperature_low",
        "equipment_alert",
    }
)

# ---------------------------------------------------------------------------
# Phase 225 — advisory mode intelligence filter
# ---------------------------------------------------------------------------

CASCADE_PROMOTE_THRESHOLD: int = 3

# bacnet_bridge alerts normalize to source="bms" in our pipeline
FAULT_ECHO_SOURCES: frozenset[str] = frozenset({"bms"})

FAULT_ECHO_TYPES: frozenset[str] = frozenset(
    {
        "fault_state",
        "change_of_state",
        "out_of_range",
        "unsigned_range",
        "equipment_alert",
        "equipment_fault",
        "ahu_fault",
        "fcu_fault",
        "chiller_alarm",
        "co2_alert",
        "co2_high",
        "bacnet_alarm",
    }
)

# IssueSource values (Literal) that represent SENTINEL-generated intelligence
ADVISORY_ALLOWED_SOURCES: frozenset[str] = frozenset({"ai"})


# ---------------------------------------------------------------------------
# Internal record type — pure data, no I/O
# ---------------------------------------------------------------------------


@dataclass
class _NormalizedIssue:
    issue: CockpitIssue
    priority: int
    dedupe_key: str
    updated_at: datetime


def _time_bucket(dt: datetime) -> int:
    """Floor a datetime to a 30-minute bucket index."""
    return int(dt.timestamp() // (_CASCADE_WINDOW_MINUTES * 60))


def _is_synthetic_bacnet_asset_id(asset_id: str) -> bool:
    """Return true for BACnet COV object keys used as synthetic asset ids."""
    return asset_id.startswith("nc:") and "|obj:" in asset_id


def _filter_unmapped_bacnet_echoes(
    items: list[_NormalizedIssue],
) -> list[_NormalizedIssue]:
    """Remove BACnet fault alerts with no real equipment or zone grounding.

    Applies to all phases. Unmapped bacnet_bridge fault alerts use
    source_dedupe_key values such as ``nc:10|obj:analogInput,8060`` as
    synthetic asset ids so the 3D layer can still reason about them. Those keys
    are not equipment grounding for issue triage, so raw fault echoes with only
    synthetic BACnet object ids are dropped before cascade grouping.

    Promoted cascade groups are always retained because they carry SENTINEL
    intelligence derived from the raw rows. BMS alerts with real equipment_id or
    zone_id pass through unchanged.
    """
    filtered: list[_NormalizedIssue] = []
    for item in items:
        if item.issue.is_group and (item.issue.member_count or 0) >= CASCADE_PROMOTE_THRESHOLD:
            filtered.append(item)
            continue

        if item.issue.source != "bms":
            filtered.append(item)
            continue

        has_real_equipment = any(
            asset_id and not _is_synthetic_bacnet_asset_id(asset_id) for asset_id in item.issue.location.asset_ids
        )
        has_zone = bool(item.issue.location.zone_ids)
        if has_real_equipment or has_zone:
            filtered.append(item)
            continue

        has_synthetic_bacnet_asset = any(
            asset_id and _is_synthetic_bacnet_asset_id(asset_id) for asset_id in item.issue.location.asset_ids
        )
        raw_type = item.dedupe_key.split("|")[-1] if "|" in item.dedupe_key else ""
        is_known_fault_echo = raw_type in FAULT_ECHO_TYPES
        is_generic_bacnet_fault_echo = raw_type == "fault" and has_synthetic_bacnet_asset
        if not is_known_fault_echo and not is_generic_bacnet_fault_echo:
            filtered.append(item)
            continue

        # Unmapped BACnet echo; do not feed the decision rail or overflow.

    return filtered


def _group_cascades(items: list[_NormalizedIssue]) -> list[_NormalizedIssue]:
    """Collapse same-type, same-severity, co-incident issues into group records.

    BMS-source issues in the same 30-min window with the same alarm type are
    collapsed into one group issue.  Single-member groups and non-BMS issues
    pass through unchanged.  Any grouping failure degrades to individual items.
    """
    if len(items) <= 1:
        return items

    eligible: list[_NormalizedIssue] = []
    non_eligible: list[_NormalizedIssue] = []
    for item in items:
        raw_type = item.dedupe_key.split("|")[-1] if "|" in item.dedupe_key else ""
        if item.issue.source == "bms" or raw_type in _CASCADE_ELIGIBLE_TYPES:
            eligible.append(item)
        else:
            non_eligible.append(item)

    # Bucket by (type, severity, time_window)
    buckets: dict[tuple[str, str, int], list[_NormalizedIssue]] = {}
    for item in eligible:
        raw_type = item.dedupe_key.split("|")[-1] if "|" in item.dedupe_key else "unknown"
        key = (raw_type, item.issue.severity, _time_bucket(item.issue.opened_at))
        buckets.setdefault(key, []).append(item)

    result: list[_NormalizedIssue] = []

    for (raw_type, _sev, _bucket), members in buckets.items():
        if len(members) == 1:
            m = members[0]
            result.append(
                _NormalizedIssue(
                    issue=m.issue.model_copy(update={"is_group": False, "member_count": 1}),
                    priority=m.priority,
                    dedupe_key=m.dedupe_key,
                    updated_at=m.updated_at,
                )
            )
            continue

        members_sorted = sorted(
            members,
            key=lambda m: (
                m.issue.sla_due_at or datetime.max.replace(tzinfo=UTC),
                m.issue.opened_at,
            ),
        )
        rep = members_sorted[0]

        # Count distinct zones (not raw alarm rows — one zone can fire many alerts)
        distinct_zones: set[str] = set()
        for m in members:
            for zid in m.issue.location.zone_ids or []:
                distinct_zones.add(zid)
            if not m.issue.location.zone_ids:
                for aid in m.issue.location.asset_ids or []:
                    distinct_zones.add(aid)
        count = len(distinct_zones) if distinct_zones else len(members)

        is_co2 = "co2" in raw_type or any("co2" in (m.issue.title or "").lower() for m in members)

        if is_co2 or raw_type == "unsigned_range":
            group_title = f"CO2 elevated — {count} zones affected"
            group_summary = (
                f"{count} zones reporting elevated CO2. "
                f"Likely root cause: fresh air supply disruption. "
                f"Inspect AHUs and cooling plant."
            )
        else:
            type_label = raw_type.replace("_", " ").title()
            group_title = f"{type_label} — {count} equipment"
            group_summary = (
                f"{count} equipment units reporting {raw_type.replace('_', ' ')}. "
                f"Review affected equipment and upstream systems."
            )

        sla_values = [m.issue.sla_due_at for m in members if m.issue.sla_due_at]
        member_asset_ids = [m.issue.location.asset_ids[0] for m in members if m.issue.location.asset_ids]
        # Use a semantically meaningful group_type (used by _enrich_cascade_summary)
        effective_type = "co2_alert" if is_co2 else raw_type

        result.append(
            _NormalizedIssue(
                issue=rep.issue.model_copy(
                    update={
                        "title": group_title,
                        "summary": group_summary,
                        "sla_due_at": min(sla_values) if sla_values else None,
                        "is_group": True,
                        "member_count": count,
                        "member_ids": [m.issue.id for m in members],
                        "member_equipment_ids": member_asset_ids,
                        "group_type": effective_type,
                    }
                ),
                priority=rep.priority,
                dedupe_key=rep.dedupe_key,
                updated_at=rep.updated_at,
            )
        )

    for item in non_eligible:
        result.append(
            _NormalizedIssue(
                issue=item.issue.model_copy(update={"is_group": False, "member_count": 1}),
                priority=item.priority,
                dedupe_key=item.dedupe_key,
                updated_at=item.updated_at,
            )
        )

    result.sort(
        key=lambda item: (
            _SEVERITY_ORDER.get(item.issue.severity, 9),
            item.issue.sla_due_at or datetime.max.replace(tzinfo=UTC),
            -(item.issue.member_count or 1),
        )
    )
    return result


def _apply_rail_limit(
    items: list[_NormalizedIssue],
) -> tuple[list[_NormalizedIssue], list[_NormalizedIssue]]:
    """Split into primary rail (max _PRIMARY_RAIL_LIMIT) and overflow."""
    return items[:_PRIMARY_RAIL_LIMIT], items[_PRIMARY_RAIL_LIMIT:]


def _enrich_cascade_summary(item: _NormalizedIssue, zone_count: int = 0) -> _NormalizedIssue:
    """Promote a grouped BACnet cascade into a SENTINEL intelligence insight.

    Groups with member_count >= CASCADE_PROMOTE_THRESHOLD are reclassified to
    source='ai' (SENTINEL inference) and given predictive root-cause framing.
    Single-member items and small groups pass through unchanged.

    zone_count: known zone count for the site.  When > 0, CO2 cascade counts are
    capped at zone_count — BACnet alerts carry no zone_id, so member_count reflects
    distinct sensor points (many per zone).  min(sensor_points, zone_count) gives
    the correct "zones affected" display count.
    """
    if not item.issue.is_group or item.issue.member_count < CASCADE_PROMOTE_THRESHOLD:
        return item

    # Normalise before matching — BACnet type field may arrive in any case
    group_type_lower = (item.issue.group_type or "").lower()
    raw_count = item.issue.member_count

    if "co2" in group_type_lower or "unsigned_range" in group_type_lower:
        # BACnet alerts carry no zone_id; member_count = distinct sensor points.
        # Cap at zone_count so the display reflects zones, not sensors.
        count = min(raw_count, zone_count) if zone_count > 0 else raw_count
        new_title = f"Fresh air disruption — {count} zones affected"
        new_summary = (
            f"CO2 is elevated across {count} zones. "
            f"Root cause: fresh air supply interrupted — inspect AHUs and cooling plant. "
            f"Comfort breach risk increases with each additional 30-minute window."
        )
    elif "change_of_state" in group_type_lower or "fault_state" in group_type_lower or group_type_lower == "fault":
        count = raw_count
        new_title = f"Equipment cascade — {count} units in fault state"
        new_summary = (
            f"{count} units reporting fault state simultaneously. "
            f"Likely upstream cause: cooling plant or power supply. "
            f"Investigate common upstream dependencies before resetting individual units."
        )
    else:
        return item

    return _NormalizedIssue(
        issue=item.issue.model_copy(update={"title": new_title, "summary": new_summary, "source": "ai"}),
        priority=item.priority,
        dedupe_key=item.dedupe_key,
        updated_at=item.updated_at,
    )


def _filter_advisory_echoes(
    items: list[_NormalizedIssue],
    onboarding_phase: str,
) -> list[_NormalizedIssue]:
    """In advisory mode: remove raw BMS fault echoes from the decision rail.

    Cascade groups (is_group=True, member_count >= CASCADE_PROMOTE_THRESHOLD)
    are retained — _enrich_cascade_summary has already promoted them to
    source='ai' (SENTINEL intelligence).  Raw individual BMS fault rows are
    excluded.  All phases other than 'advisory' pass through unchanged.
    """
    if onboarding_phase != "advisory":
        return items

    filtered: list[_NormalizedIssue] = []
    for item in items:
        source = item.issue.source
        raw_type = item.dedupe_key.split("|")[-1] if "|" in item.dedupe_key else ""
        is_group = item.issue.is_group
        member_count = item.issue.member_count

        # Promoted cascade intelligence — always keep
        if is_group and member_count >= CASCADE_PROMOTE_THRESHOLD:
            filtered.append(item)
            continue

        # Raw BMS fault echo — exclude from advisory decision rail
        if source in FAULT_ECHO_SOURCES and raw_type in FAULT_ECHO_TYPES:
            continue

        # SENTINEL-generated intelligence (ML, AI, energy optimiser) — keep
        if source in ADVISORY_ALLOWED_SOURCES:
            filtered.append(item)
            continue

        # Non-BMS sources not covered above — keep
        if source not in FAULT_ECHO_SOURCES:
            filtered.append(item)

    return filtered


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
        recommendations: list[dict[str, Any]] | None = None,
        onboarding_phase: str = "supervised",
        zone_count: int = 0,
    ) -> tuple[list[CockpitIssue], list[CockpitIssue], list[CockpitSourceStatus], list[CockpitActionAudit], str | None]:
        """Combine issue sources into a deduplicated, grouped, rail-limited feed.

        Pipeline order:
            normalize → dedupe → filter-unmapped-echoes → cascade-group →
            enrich-cascade → advisory-filter → rail-limit

        Args:
            alerts:            BMS alert rows (source = "bms", priority 0).
            intakes:           Email intake rows (source = "intake", priority 1).
            work_orders:       Work-order rows (source = "tech", priority 2).
            audit_logs:        Audit-trail rows (pre-merged by the caller).
            selected_issue_id: ID to keep selected; falls back to top issue.
            recommendations:   AI recommendation rows (source = "ai", priority -1).
            onboarding_phase:  Site onboarding phase; "advisory" activates the
                               intelligence filter (Phase 225).
            zone_count:        Known zone count for the site; used to cap CO2
                               cascade display counts (BACnet alerts carry no
                               zone_id, so sensor-point count ≠ zone count).

        Returns:
            (primary_issues, overflow_issues, source_statuses, audit_trail, selected_id)
            primary_issues: max _PRIMARY_RAIL_LIMIT grouped issues for the decision rail.
            overflow_issues: remaining issues collapsed into the overflow section.
        """
        normalized: list[_NormalizedIssue] = []
        normalized.extend(CockpitTableProcessor._to_normalized_issues(alerts, source="bms", priority=0))
        normalized.extend(CockpitTableProcessor._to_normalized_issues(intakes, source="intake", priority=1))
        normalized.extend(CockpitTableProcessor._to_normalized_issues(work_orders, source="tech", priority=2))
        if recommendations:
            normalized.extend(CockpitTableProcessor._to_normalized_issues(recommendations, source="ai", priority=-1))

        deduped = CockpitTableProcessor._dedupe(normalized)
        # Phase 226 — drop unmapped BACnet echoes before cascade grouping
        echo_filtered = _filter_unmapped_bacnet_echoes(deduped)
        # Phase 224 — cascade grouping
        grouped = _group_cascades(echo_filtered)
        # Phase 225 — enrich BACnet cascade groups into SENTINEL intelligence
        enriched = [_enrich_cascade_summary(item, zone_count=zone_count) for item in grouped]
        # Phase 225 — advisory mode filter: raw echoes out, interpreted insights in
        filtered = _filter_advisory_echoes(enriched, onboarding_phase)
        primary_items, overflow_items = _apply_rail_limit(filtered)

        selected = selected_issue_id
        if selected and selected not in {item.issue.id for item in primary_items}:
            selected = None
        if not selected and primary_items:
            selected = primary_items[0].issue.id

        source_statuses = CockpitTableProcessor._build_source_statuses(
            alerts,
            intakes,
            work_orders,
            bridge_last_updated=bridge_last_updated,
        )
        audit_trail = CockpitTableProcessor._build_audit_trail(audit_logs)
        return (
            [item.issue for item in primary_items],
            [item.issue for item in overflow_items],
            source_statuses,
            audit_trail,
            selected,
        )

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
            issue = (
                CockpitTableProcessor._recommendation_to_issue(entry)
                if source == "ai"
                else CockpitTableProcessor._entry_to_issue(entry, source)
            )
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
    def _recommendation_to_issue(entry: dict[str, Any]) -> CockpitIssue | None:
        """Normalize an AI recommendation row into a CockpitIssue."""
        now = datetime.now(UTC)
        target = entry.get("target_equipment") or entry.get("equipment_code")
        equipment_id = target[0] if isinstance(target, list) else (str(target) if target else None)
        action = entry.get("action") or {}
        risk = str(entry.get("risk_level", "medium")).lower()
        severity = "critical" if risk in ("critical", "mission_critical") else "high" if risk == "high" else "medium"
        recommended_action = action.get("point") if isinstance(action, dict) else str(action)
        action_type = entry.get("action_type", "optimization")

        # Phase 227 — maintenance gap: single grouped issue for equipment cohort
        meta = entry.get("metadata") or {}
        is_gap = action_type == "maintenance_gap"
        if is_gap:
            member_count = meta.get("member_count", 0)
            member_ids = meta.get("member_ids", [])
            member_equipment_ids = meta.get("member_codes", [])
            eq_type = meta.get("equipment_type", "equipment")
            title = f"{eq_type.upper()} maintenance gap — {member_count} units"
            summary = (
                f"{member_count} {eq_type} units averaging health score {meta.get('avg_health_score', '?')} "
                f"with no recorded maintenance history. "
                f"Recommend priority inspection before next occupancy cycle."
            )
            return CockpitIssue(
                id=str(entry.get("id", uuid4())),
                title=title,
                summary=summary,
                severity=severity,
                source="ai",
                status="new",
                opened_at=CockpitTableProcessor._parse_datetime(entry.get("timestamp")) or now,
                updated_at=CockpitTableProcessor._parse_datetime(entry.get("timestamp")) or now,
                sla_due_at=now + timedelta(hours=4),
                stale=False,
                impact_summary=f"Systemic {eq_type} degradation — {member_count} units affected",
                cause_hypothesis=f"7 {eq_type} units at health_score <= 65 with no service history",
                recommended_action="Priority inspection of all affected units",
                confidence=float(entry.get("confidence_score") or 0.7),
                confidence_label="Medium confidence",
                issue_category="fault",
                subsystem="hvac",
                constraint_type="asset",
                location=CockpitIssueLocation(
                    zone_ids=[],
                    asset_ids=member_ids[:1] if member_ids else [],
                    floor_id=entry.get("floor_id"),
                ),
                evidence_refs=[
                    CockpitIssueEvidenceRef(
                        id=str(entry.get("id", "")), kind="recommendation", label=risk, source="ai"
                    ),
                ],
                source_record_id=str(entry.get("id")),
                is_group=True,
                member_count=member_count,
                member_ids=member_ids,
                member_equipment_ids=member_equipment_ids,
                group_type="maintenance_gap",
            )

        return CockpitIssue(
            id=str(entry.get("id", uuid4())),
            title=f"AI: {action_type} — {equipment_id}" if equipment_id else f"AI: {action_type}",
            summary=entry.get("reason") or entry.get("description") or "",
            severity=severity,
            source="ai",
            status="new",
            opened_at=CockpitTableProcessor._parse_datetime(entry.get("timestamp")) or now,
            updated_at=CockpitTableProcessor._parse_datetime(entry.get("timestamp")) or now,
            sla_due_at=now + timedelta(hours=4),
            stale=False,
            impact_summary=str(entry.get("expected_impact", {})),
            cause_hypothesis=(entry.get("reason") or "")[:200],
            recommended_action=recommended_action,
            confidence=float(entry.get("confidence_score") or 0.5),
            confidence_label=f"{severity.capitalize()} confidence",
            issue_category="energy",
            subsystem=CockpitTableProcessor._infer_subsystem(equipment_id, "energy", "ai"),
            constraint_type="energy",
            location=CockpitIssueLocation(
                zone_ids=[],
                asset_ids=[equipment_id] if equipment_id else [],
                floor_id=entry.get("floor_id"),
            ),
            evidence_refs=[
                CockpitIssueEvidenceRef(id=str(entry.get("id", "")), kind="recommendation", label=risk, source="ai"),
            ],
            source_record_id=str(entry.get("id")),
        )

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
                asset_ids=[equipment_id]
                if equipment_id
                # BACnet alerts have no equipment FK but ARE physically grounded —
                # use the dedupe key as a synthetic asset_id so spatially_grounded=True
                else (
                    [entry["source_dedupe_key"]]
                    if entry.get("source_dedupe_key") and entry.get("source") == "bacnet_bridge"
                    else []
                ),
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
        entries = {"bms": alerts, "intake": intakes, "tech": work_orders, "ai": []}
        statuses = []
        for source, items in entries.items():
            last_updated = max(
                (
                    CockpitTableProcessor._parse_datetime(item.get("updated_at"))
                    for item in items
                    if item.get("updated_at")
                ),
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
