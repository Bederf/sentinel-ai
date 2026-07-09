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


def _bacnet_alert(
    id: str,
    *,
    equipment_id: str | None = None,
    zone_id: str | None = None,
    type_: str = "change_of_state",
    source_dedupe_key: str = "nc:10|obj:analogInput,8060",
) -> dict:
    now = datetime.now(UTC)
    alert = {
        "id": id,
        "severity": "critical",
        "status": "new",
        "equipment_id": equipment_id,
        "site_id": "S002",
        "updated_at": now.isoformat(),
        "created_at": now.isoformat(),
        "type": type_,
        "title": f"BACnet alert {id}",
        "source": "bacnet_bridge",
        "source_dedupe_key": source_dedupe_key,
    }
    if zone_id:
        alert["zone_id"] = zone_id
    return alert


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
        issues, _, _, _, _ = CockpitTableProcessor.fuse(alerts, intakes, [], [], None)
        # Two sources, same equipment + type → deduplicated to 1
        assert len(issues) == 1

    def test_different_equipment_same_type_cascades_to_group(self):
        # Phase 224: two BMS alerts, same type, same 30-min window → cascade group
        alerts = [
            _alert("a1", equipment_id="eq-1", type_="hvac"),
            _alert("a2", equipment_id="eq-2", type_="hvac"),
        ]
        issues, _, _, _, _ = CockpitTableProcessor.fuse(alerts, [], [], [], None)
        assert len(issues) == 1
        assert issues[0].is_group is True
        assert issues[0].member_count == 2

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
        issues, _, _, _, _ = CockpitTableProcessor.fuse(alerts, intakes, [], [], None)
        assert len(issues) == 1
        # BMS (priority 0) wins over intake (priority 1)
        assert issues[0].source == "bms"


# ---------------------------------------------------------------------------
# BACnet bridge echo filtering
# ---------------------------------------------------------------------------


class TestBacnetBridgeEchoFiltering:
    def test_unmapped_bacnet_fault_echoes_removed_from_primary_and_overflow(self):
        alerts = [
            _bacnet_alert("bac-1", source_dedupe_key="nc:10|obj:analogInput,8060"),
            _bacnet_alert("bac-2", type_="unsigned_range", source_dedupe_key="nc:10|obj:analogInput,8061"),
            _alert("real-1", severity="high", equipment_id="S002-FCU-204", site_id="S002", type_="fcu_fault"),
        ]

        primary, overflow, _, _, selected = CockpitTableProcessor.fuse(alerts, [], [], [], None)

        assert [issue.id for issue in primary] == ["real-1"]
        assert overflow == []
        assert selected == "real-1"

    def test_unmapped_generic_bacnet_fault_echoes_removed(self):
        alerts = [
            _bacnet_alert(
                "bac-generic",
                type_="fault",
                source_dedupe_key="nc:18|obj:binaryInput,2245",
            ),
            _alert("real-1", severity="high", equipment_id="S002-FCU-204", site_id="S002", type_="fcu_fault"),
        ]

        primary, overflow, _, _, selected = CockpitTableProcessor.fuse(alerts, [], [], [], None)

        assert [issue.id for issue in primary] == ["real-1"]
        assert overflow == []
        assert selected == "real-1"

    def test_equipment_grounded_bacnet_fault_echo_remains(self):
        alerts = [
            _bacnet_alert(
                "bac-grounded",
                equipment_id="S002-CT-B01",
                source_dedupe_key="nc:10|obj:binaryInput,57",
            )
        ]

        primary, overflow, _, _, selected = CockpitTableProcessor.fuse(alerts, [], [], [], None)

        assert [issue.id for issue in primary] == ["bac-grounded"]
        assert primary[0].location.asset_ids == ["S002-CT-B01"]
        assert overflow == []
        assert selected == "bac-grounded"

    def test_zone_grounded_bacnet_fault_echo_remains(self):
        alerts = [
            _bacnet_alert(
                "bac-zone",
                zone_id="S002-ZONE-B1",
                type_="unsigned_range",
                source_dedupe_key="nc:10|obj:analogInput,8062",
            )
        ]

        primary, overflow, _, _, selected = CockpitTableProcessor.fuse(alerts, [], [], [], None)

        assert [issue.id for issue in primary] == ["bac-zone"]
        assert primary[0].location.zone_ids == ["S002-ZONE-B1"]
        assert overflow == []
        assert selected == "bac-zone"

    def test_ai_recommendation_remains_when_unmapped_bacnet_echo_filtered(self):
        alerts = [_bacnet_alert("bac-1")]
        recommendations = [
            {
                "id": "rec-1",
                "target_equipment": "S002-CT-B01",
                "risk_level": "high",
                "action_type": "optimization",
                "reason": "Cooling tower trend requires review.",
                "confidence_score": 0.82,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        ]

        primary, overflow, _, _, selected = CockpitTableProcessor.fuse(
            alerts,
            [],
            [],
            [],
            None,
            recommendations=recommendations,
        )

        assert [issue.id for issue in primary] == ["rec-1"]
        assert primary[0].source == "ai"
        assert overflow == []
        assert selected == "rec-1"


# ---------------------------------------------------------------------------
# Health grouping
# ---------------------------------------------------------------------------


class TestHealthGrouping:
    def test_health_group_uses_operator_summary(self):
        alerts = [
            _alert(f"health-{idx}", severity="warning", equipment_id=f"S002-FCU-{idx}", site_id="S002", type_="health")
            for idx in range(3)
        ]

        primary, overflow, _, _, selected = CockpitTableProcessor.fuse(alerts, [], [], [], None)

        assert overflow == []
        assert selected == primary[0].id
        assert primary[0].title == "Health — 3 equipment"
        assert "health warning band" in primary[0].summary
        assert "scores should diversify" in primary[0].summary
        assert primary[0].recommended_action == (
            "Review the affected equipment cohort and prioritize assets trending toward critical."
        )


# ---------------------------------------------------------------------------
# Current telemetry condition grouping
# ---------------------------------------------------------------------------


class TestCurrentConditionGrouping:
    def test_co2_cascade_uses_fresh_telemetry_count_not_active_alert_count(self):
        alerts = []
        now = datetime.now(UTC).isoformat()
        for idx in range(1, 12):
            alert = _bacnet_alert(
                f"co2-{idx}",
                type_="fault",
                source_dedupe_key=f"point:sensor.zone-{idx:03d}.co2|code:unsigned_range|type:unsigned_range",
            )
            alert["title"] = f"{idx:03d}.CO2 alert: UNSIGNED_RANGE"
            alert["created_at"] = now
            alert["updated_at"] = now
            alerts.append(alert)

        primary, _, _, _, _ = CockpitTableProcessor.fuse(
            alerts,
            [],
            [],
            [],
            None,
            onboarding_phase="advisory",
            zone_count=16,
            co2_condition={
                "fresh_zone_count": 15,
                "elevated_zone_ids": ["ZONE-001", "ZONE-002", "ZONE-003", "ZONE-004", "ZONE-005"],
                "threshold_ppm": 800.0,
            },
        )

        assert primary[0].title == "Fresh air disruption — 5 zones affected"
        assert "5 of 15 fresh zones" in primary[0].summary
        assert primary[0].member_count == 5
        assert primary[0].location.zone_ids == ["ZONE-001", "ZONE-002", "ZONE-003", "ZONE-004", "ZONE-005"]

    def test_co2_cascade_without_current_telemetry_support_does_not_promote_condition(self):
        alerts = []
        now = datetime.now(UTC).isoformat()
        for idx in range(1, 12):
            alert = _bacnet_alert(
                f"co2-stale-{idx}",
                type_="fault",
                source_dedupe_key=f"point:sensor.zone-{idx:03d}.co2|code:unsigned_range|type:unsigned_range",
            )
            alert["title"] = f"{idx:03d}.CO2 alert: UNSIGNED_RANGE"
            alert["created_at"] = now
            alert["updated_at"] = now
            alerts.append(alert)

        primary, overflow, _, _, selected = CockpitTableProcessor.fuse(
            alerts,
            [],
            [],
            [],
            None,
            onboarding_phase="advisory",
            zone_count=16,
            co2_condition={
                "fresh_zone_count": 15,
                "elevated_zone_ids": ["ZONE-001", "ZONE-002"],
                "threshold_ppm": 800.0,
            },
        )

        assert primary == []
        assert overflow == []
        assert selected is None


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
        issues, _, _, _, _ = CockpitTableProcessor.fuse(alerts, [], [], [], None)
        assert issues[0].severity == "critical"

    def test_resolved_ranked_last_among_same_severity(self):
        """Resolved issues rank behind non-resolved ones of the same severity."""
        now = datetime.now(UTC)
        alerts = [
            _alert(
                "a-resolved",
                severity="medium",
                status="resolved",
                equipment_id="eq-r",
                type_="fault_r",
                updated_at=now.isoformat(),
            ),
            _alert(
                "a-new",
                severity="medium",
                status="new",
                equipment_id="eq-n",
                type_="fault_n",
                updated_at=now.isoformat(),
            ),
        ]
        issues, _, _, _, _ = CockpitTableProcessor.fuse(alerts, [], [], [], None)
        assert issues[-1].id == "a-resolved"

    def test_selected_id_preserved(self):
        # Use distinct types so cascade grouping doesn't collapse them
        now = datetime.now(UTC)
        alerts = [
            _alert("a1", equipment_id="eq-1", type_="type_x", updated_at=now.isoformat()),
            _alert("a2", equipment_id="eq-2", type_="type_y", updated_at=now.isoformat()),
        ]
        _, _, _, _, selected = CockpitTableProcessor.fuse(alerts, [], [], [], "a2")
        assert selected == "a2"

    def test_selected_id_falls_back_to_top_if_not_found(self):
        alerts = [_alert("a1", equipment_id="eq-1")]
        _, _, _, _, selected = CockpitTableProcessor.fuse(alerts, [], [], [], "missing-id")
        assert selected == "a1"

    def test_no_issues_returns_none_selected(self):
        _, _, _, _, selected = CockpitTableProcessor.fuse([], [], [], [], None)
        assert selected is None


# ---------------------------------------------------------------------------
# _build_source_statuses
# ---------------------------------------------------------------------------


class TestSourceStatuses:
    def test_returns_three_statuses(self):
        _, _, statuses, _, _ = CockpitTableProcessor.fuse([], [], [], [], None)
        assert len(statuses) == 4  # bms, intake, tech, ai
        sources = {s.source for s in statuses}
        assert sources == {"bms", "intake", "tech", "ai"}

    def test_healthy_when_fresh(self):
        recent = datetime.now(UTC).isoformat()
        alerts = [_alert(updated_at=recent)]
        _, _, statuses, _, _ = CockpitTableProcessor.fuse(alerts, [], [], [], None)
        bms_status = next(s for s in statuses if s.source == "bms")
        assert bms_status.state == "healthy"

    def test_unavailable_when_no_data(self):
        _, _, statuses, _, _ = CockpitTableProcessor.fuse([], [], [], [], None)
        bms_status = next(s for s in statuses if s.source == "bms")
        assert bms_status.state == "unavailable"

    def test_stale_thresholds_in_output(self):
        _, _, statuses, _, _ = CockpitTableProcessor.fuse([], [], [], [], None)
        bms_status = next(s for s in statuses if s.source == "bms")
        assert bms_status.stale_after_seconds == SOURCE_THRESHOLDS["bms"]["stale"]


# ---------------------------------------------------------------------------
# _build_audit_trail
# ---------------------------------------------------------------------------


class TestAuditTrail:
    def test_sorted_newest_first(self):
        old = {**_audit("old"), "timestamp": (datetime.now(UTC) - timedelta(hours=2)).isoformat()}
        new = {**_audit("new"), "timestamp": datetime.now(UTC).isoformat()}
        _, _, _, trail, _ = CockpitTableProcessor.fuse([], [], [], [old, new], None)
        assert trail[0].id == "new"

    def test_max_ten_entries(self):
        entries = [_audit(str(i)) for i in range(15)]
        _, _, _, trail, _ = CockpitTableProcessor.fuse([], [], [], entries, None)
        assert len(trail) <= 10

    def test_empty_entries_returns_empty_trail(self):
        _, _, _, trail, _ = CockpitTableProcessor.fuse([], [], [], [], None)
        assert trail == []

    def test_success_outcome(self):
        _, _, _, trail, _ = CockpitTableProcessor.fuse([], [], [], [_audit()], None)
        assert trail[0].outcome == "success"
