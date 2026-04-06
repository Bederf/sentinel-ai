"""Parity tests for CockpitTableProcessor.

Verifies that normalisation, deduplication, ranking, source-status
computation, and audit-trail assembly match the original logic that
lived in CockpitIssueFusionService before the refactor.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.processing.cockpit_table import (
    SOURCE_THRESHOLDS,
    CockpitTableProcessor,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _alert(
    id: str = "a1",
    severity: str = "medium",
    status: str = "new",
    equipment_id: str | None = "eq-1",
    site_id: str = "S001",
    updated_at: str | None = None,
    type_: str = "hvac",
) -> dict:
    now = datetime.now(UTC)
    return {
        "id": id,
        "severity": severity,
        "status": status,
        "equipment_id": equipment_id,
        "site_id": site_id,
        "updated_at": updated_at or now.isoformat(),
        "type": type_,
        "title": f"Alert {id}",
    }


def _audit(id: str = "au1", action: str = "acknowledge", user_id: str = "u1") -> dict:
    return {
        "id": id,
        "action": action,
        "user_id": user_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "metadata": {"site_id": "S001", "issue_id": "a1"},
        "result": "SUCCESS",
    }


# ---------------------------------------------------------------------------
# _map_severity
# ---------------------------------------------------------------------------


class TestMapSeverity:
    @pytest.mark.parametrize(
        "value,expected",
        [
            ("critical", "critical"),
            ("high", "high"),
            ("medium", "medium"),
            ("low", "low"),
            (None, "medium"),
            ("unknown", "medium"),
            ("CRITICAL", "critical"),  # .lower() normalises before map lookup
        ],
    )
    def test_mapping(self, value, expected):
        assert CockpitTableProcessor._map_severity(value) == expected


# ---------------------------------------------------------------------------
# _severity_to_confidence
# ---------------------------------------------------------------------------


class TestSeverityToConfidence:
    def test_critical_is_highest(self):
        c = CockpitTableProcessor._severity_to_confidence("critical")
        m = CockpitTableProcessor._severity_to_confidence("medium")
        assert c > m

    def test_known_values(self):
        assert CockpitTableProcessor._severity_to_confidence("critical") == pytest.approx(0.95)
        assert CockpitTableProcessor._severity_to_confidence("low") == pytest.approx(0.4)


# ---------------------------------------------------------------------------
# _build_dedupe_key
# ---------------------------------------------------------------------------


class TestBuildDedupeKey:
    def test_key_with_equipment_id(self):
        entry = {"equipment_id": "CH-001", "site_id": "S001", "type": "chiller_fault"}
        issue = CockpitTableProcessor._entry_to_issue(entry, "bms")
        key = CockpitTableProcessor._build_dedupe_key(entry, issue, "bms")
        assert "S001" in key
        assert "CH-001" in key

    def test_key_with_zone_id_fallback(self):
        entry = {"zone_id": "Z1", "site_id": "S001", "type": "comfort"}
        issue = CockpitTableProcessor._entry_to_issue(entry, "bms")
        key = CockpitTableProcessor._build_dedupe_key(entry, issue, "bms")
        assert "Z1" in key

    def test_unknown_fallback(self):
        entry = {"site_id": "S001"}
        issue = CockpitTableProcessor._entry_to_issue(entry, "bms")
        key = CockpitTableProcessor._build_dedupe_key(entry, issue, "bms")
        assert "unknown" in key

    def test_spaces_in_type_normalised(self):
        entry = {"equipment_id": "E1", "site_id": "S1", "type": "hvac fault"}
        issue = CockpitTableProcessor._entry_to_issue(entry, "bms")
        key = CockpitTableProcessor._build_dedupe_key(entry, issue, "bms")
        assert "hvac_fault" in key


# ---------------------------------------------------------------------------
# _dedupe — duplicate suppression
# ---------------------------------------------------------------------------


class TestDedupe:
    def test_same_key_kept_once(self):
        alerts = [_alert("a1", equipment_id="eq-1", type_="hvac")]
        intakes = [
            {
                "id": "i1",
                "equipment_id": "eq-1",
                "site_id": "S001",
                "type": "hvac",
                "updated_at": datetime.now(UTC).isoformat(),
            }
        ]
        issues, _, _, _ = CockpitTableProcessor.fuse(alerts, intakes, [], [], None)
        # Two sources, same equipment + type → deduplicated to 1
        assert len(issues) == 1

    def test_different_equipment_not_merged(self):
        alerts = [
            _alert("a1", equipment_id="eq-1", type_="hvac"),
            _alert("a2", equipment_id="eq-2", type_="hvac"),
        ]
        issues, _, _, _ = CockpitTableProcessor.fuse(alerts, [], [], [], None)
        assert len(issues) == 2

    def test_bms_priority_over_intake_for_same_key(self):
        now = datetime.now(UTC)
        alerts = [_alert("bms-1", equipment_id="eq-1", type_="fault", severity="critical", updated_at=now.isoformat())]
        intakes = [
            {
                "id": "int-1",
                "equipment_id": "eq-1",
                "site_id": "S001",
                "type": "fault",
                "severity": "low",
                "updated_at": (now - timedelta(hours=1)).isoformat(),
            }
        ]
        issues, _, _, _ = CockpitTableProcessor.fuse(alerts, intakes, [], [], None)
        assert len(issues) == 1
        # BMS (priority 0) wins over intake (priority 1)
        assert issues[0].source == "bms"


# ---------------------------------------------------------------------------
# _dedupe — ranking
# ---------------------------------------------------------------------------


class TestRanking:
    def test_critical_ranked_above_medium(self):
        now = datetime.now(UTC)
        alerts = [
            _alert("a-medium", severity="medium", equipment_id="eq-m", updated_at=now.isoformat()),
            _alert("a-critical", severity="critical", equipment_id="eq-c", updated_at=now.isoformat()),
        ]
        issues, _, _, _ = CockpitTableProcessor.fuse(alerts, [], [], [], None)
        assert issues[0].severity == "critical"

    def test_resolved_ranked_last_among_same_severity(self):
        """Resolved issues rank behind non-resolved ones of the same severity."""
        now = datetime.now(UTC)
        alerts = [
            _alert("a-resolved", severity="medium", status="resolved", equipment_id="eq-r", updated_at=now.isoformat()),
            _alert("a-new", severity="medium", status="new", equipment_id="eq-n", updated_at=now.isoformat()),
        ]
        issues, _, _, _ = CockpitTableProcessor.fuse(alerts, [], [], [], None)
        assert issues[-1].id == "a-resolved"

    def test_selected_id_preserved(self):
        now = datetime.now(UTC)
        alerts = [
            _alert("a1", equipment_id="eq-1", updated_at=now.isoformat()),
            _alert("a2", equipment_id="eq-2", updated_at=now.isoformat()),
        ]
        _, _, _, selected = CockpitTableProcessor.fuse(alerts, [], [], [], "a2")
        assert selected == "a2"

    def test_selected_id_falls_back_to_top_if_not_found(self):
        alerts = [_alert("a1", equipment_id="eq-1")]
        _, _, _, selected = CockpitTableProcessor.fuse(alerts, [], [], [], "missing-id")
        assert selected == "a1"

    def test_no_issues_returns_none_selected(self):
        _, _, _, selected = CockpitTableProcessor.fuse([], [], [], [], None)
        assert selected is None


# ---------------------------------------------------------------------------
# _build_source_statuses
# ---------------------------------------------------------------------------


class TestSourceStatuses:
    def test_returns_three_statuses(self):
        _, statuses, _, _ = CockpitTableProcessor.fuse([], [], [], [], None)
        assert len(statuses) == 3
        sources = {s.source for s in statuses}
        assert sources == {"bms", "intake", "tech"}

    def test_healthy_when_fresh(self):
        recent = datetime.now(UTC).isoformat()
        alerts = [_alert(updated_at=recent)]
        _, statuses, _, _ = CockpitTableProcessor.fuse(alerts, [], [], [], None)
        bms_status = next(s for s in statuses if s.source == "bms")
        assert bms_status.state == "healthy"

    def test_unavailable_when_no_data(self):
        _, statuses, _, _ = CockpitTableProcessor.fuse([], [], [], [], None)
        bms_status = next(s for s in statuses if s.source == "bms")
        assert bms_status.state == "unavailable"

    def test_stale_thresholds_in_output(self):
        _, statuses, _, _ = CockpitTableProcessor.fuse([], [], [], [], None)
        bms_status = next(s for s in statuses if s.source == "bms")
        assert bms_status.stale_after_seconds == SOURCE_THRESHOLDS["bms"]["stale"]


# ---------------------------------------------------------------------------
# _build_audit_trail
# ---------------------------------------------------------------------------


class TestAuditTrail:
    def test_sorted_newest_first(self):
        old = {**_audit("old"), "timestamp": (datetime.now(UTC) - timedelta(hours=2)).isoformat()}
        new = {**_audit("new"), "timestamp": datetime.now(UTC).isoformat()}
        _, _, trail, _ = CockpitTableProcessor.fuse([], [], [], [old, new], None)
        assert trail[0].id == "new"

    def test_max_ten_entries(self):
        entries = [_audit(str(i)) for i in range(15)]
        _, _, trail, _ = CockpitTableProcessor.fuse([], [], [], entries, None)
        assert len(trail) <= 10

    def test_empty_entries_returns_empty_trail(self):
        _, _, trail, _ = CockpitTableProcessor.fuse([], [], [], [], None)
        assert trail == []

    def test_success_outcome(self):
        _, _, trail, _ = CockpitTableProcessor.fuse([], [], [], [_audit()], None)
        assert trail[0].outcome == "success"
