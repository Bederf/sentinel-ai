from datetime import UTC, datetime, timedelta

import pytest

from app.services.reflex_reconciliation_service import (
    ReflexReconciliationService,
    _is_zone_relevant_equipment,
    recurrence_bucket,
    recurrence_bucket_parts,
)
from app.services.zone_identity_resolver import ZoneResolution


class FakeResolver:
    def __init__(self):
        self.gaps = []

    async def resolve(self, site_id, zone_id, *, source_context="unknown", record_gap=True):
        mapping = {
            "Zone-101": "Zone-101",
            "Zone-201": "Zone-201",
            "Zone-001": "Zone-001",
        }
        canonical = mapping.get(zone_id)
        if canonical:
            return ZoneResolution(zone_id, canonical, "resolved", "test_mapping", aliases=(zone_id, canonical))
        if record_gap:
            self.gaps.append((site_id, zone_id, source_context))
        return ZoneResolution(zone_id, None, "unresolved", "test_unresolved")


class FakeReflexRepository:
    def __init__(self):
        self.fcu_rows = []
        self.lighting_rows = []
        self.equipment_by_zone = {}
        self.created = []
        self.created_at = []
        self.rows = []
        self.occurrence_dates = {}
        self.occurrence_calls = []
        self.open_schedule_defect = False

    async def list_site_ids(self):
        return ["site-002"]

    async def list_latest_fcu_zone_state(self, site_id):
        return self.fcu_rows

    async def list_latest_lighting_energy(self, site_id):
        return self.lighting_rows

    async def list_equipment_by_zone(self, site_id):
        return self.equipment_by_zone

    async def list_active_reflex_recommendations(self, site_id):
        return [
            row
            for row in self.rows
            if row["site_id"] == site_id
            and row["source"] == "reflex_reconciliation"
            and row["status"] in {"pending", "advisory_info"}
        ]

    async def record_occurrence(self, finding, *, now):
        self.occurrence_calls.append((finding, now))
        day, bucket, local_date = recurrence_bucket_parts(now)
        key = (finding.canonical_zone_id, finding.system_type, finding.rule_key, day, bucket)
        self.occurrence_dates.setdefault(key, set()).add(local_date)
        return len(self.occurrence_dates[key])

    async def update_recommendation_observation(self, recommendation, finding, *, action_type, now):
        metadata = dict(recommendation.get("metadata") or {})
        metadata.pop("pending_clear_since", None)
        metadata.update(
            {
                "canonical_zone_id": finding.canonical_zone_id,
                "source_zone_id": finding.source_zone_id,
                "system_type": finding.system_type,
                "rule_key": finding.rule_key,
                "evidence": finding.evidence,
                "first_observed_at": metadata.get("first_observed_at") or recommendation["timestamp"],
                "last_observed_at": now.isoformat(),
                "observation_count": int(metadata.get("observation_count") or 1) + 1,
            }
        )
        recommendation.update(
            {
                "timestamp": now.isoformat(),
                "reason": finding.reason,
                "metadata": metadata,
            }
        )
        return type(
            "FakeRecommendation",
            (),
            {
                "id": recommendation["id"],
                "action_type": action_type,
                "target_equipment": finding.canonical_zone_id,
                "reason": finding.reason,
            },
        )()

    async def mark_pending_clear(self, recommendations, *, now):
        ids = {row["id"] for row in recommendations}
        marked = 0
        for row in self.rows:
            if row["id"] in ids:
                metadata = dict(row.get("metadata") or {})
                metadata["pending_clear_since"] = now.isoformat()
                row["metadata"] = metadata
                marked += 1
        return marked

    async def resolve_recommendations(self, recommendations, *, now, reason):
        resolved = 0
        ids = {row["id"] for row in recommendations}
        for row in self.rows:
            if row["id"] in ids and row["status"] in {"pending", "advisory_info"}:
                metadata = dict(row.get("metadata") or {})
                metadata.update({"resolved_at": now.isoformat(), "resolution_reason": reason})
                row["metadata"] = metadata
                row["status"] = "expired"
                resolved += 1
        return resolved

    async def expire_point_in_time_for_finding(self, finding, *, now, reason):
        rows = [
            row
            for row in await self.list_active_reflex_recommendations(finding.site_id)
            if row["action_type"] == finding.category
            and row["target_equipment"] == finding.canonical_zone_id
            and row["metadata"].get("system_type") == finding.system_type
            and row["metadata"].get("rule_key") == finding.rule_key
        ]
        return await self.resolve_recommendations(rows, now=now, reason=reason)

    async def open_schedule_defect_exists(self, finding):
        return any(
            row
            for row in await self.list_active_reflex_recommendations(finding.site_id)
            if row["action_type"] == "schedule_defect"
            and row["target_equipment"] == finding.canonical_zone_id
            and row["metadata"].get("system_type") == finding.system_type
            and row["metadata"].get("rule_key") == finding.rule_key
        )

    async def create_recommendation(self, finding, *, action_type, now):
        rec_id = f"rec-{len(self.created) + 1}"
        rec = type(
            "FakeRecommendation",
            (),
            {
                "id": rec_id,
                "action_type": action_type,
                "target_equipment": finding.canonical_zone_id,
                "reason": finding.reason,
            },
        )()
        self.created.append((action_type, finding))
        self.created_at.append((now, action_type, finding))
        self.rows.append(
            {
                "id": rec_id,
                "site_id": finding.site_id,
                "timestamp": now.isoformat(),
                "action_type": action_type,
                "target_equipment": finding.canonical_zone_id,
                "action": {
                    "type": "manual_schedule_review" if action_type == "schedule_defect" else "manual_operator_review",
                    "system_type": finding.system_type,
                    "rule_key": finding.rule_key,
                    "auto_actionable": False,
                },
                "reason": finding.reason,
                "status": "advisory_info",
                "source": "reflex_reconciliation",
                "metadata": {
                    "canonical_zone_id": finding.canonical_zone_id,
                    "source_zone_id": finding.source_zone_id,
                    "system_type": finding.system_type,
                    "rule_key": finding.rule_key,
                    "evidence": finding.evidence,
                    "first_observed_at": now.isoformat(),
                    "last_observed_at": now.isoformat(),
                    "observation_count": 1,
                },
            }
        )
        return rec


def _service(repo=None):
    repo = repo or FakeReflexRepository()
    return ReflexReconciliationService(repository=repo, resolver=FakeResolver()), repo


@pytest.mark.asyncio
async def test_empty_zone_hvac_running_creates_operational_mismatch():
    svc, repo = _service()
    repo.fcu_rows = [
        {
            "zone_id": "Zone-101",
            "occupancy_pct": 0,
            "room_temp_c": 22,
            "setpoint_c": 22,
            "fcu_inferred_running": True,
            "occupancy_source": "bridge",
        }
    ]

    created = await svc.reconcile_site("site-002", now=datetime(2026, 6, 21, 18, 0, tzinfo=UTC))

    assert len(created) == 1
    assert repo.created[0][0] == "operational_mismatch"
    assert repo.created[0][1].rule_key == "hvac.empty_zone_running"
    assert repo.created[0][1].canonical_zone_id == "Zone-101"


@pytest.mark.asyncio
async def test_occupied_zone_hvac_idle_outside_comfort_creates_comfort_risk():
    svc, repo = _service()
    repo.fcu_rows = [
        {
            "zone_id": "Zone-201",
            "occupancy_pct": 60,
            "room_temp_c": 28.5,
            "setpoint_c": 22,
            "fcu_inferred_running": False,
            "occupancy_source": "bridge",
        }
    ]

    await svc.reconcile_site("site-002", now=datetime(2026, 6, 22, 9, 0, tzinfo=UTC))

    assert repo.created[0][0] == "comfort_risk"
    assert repo.created[0][1].rule_key == "hvac.occupied_zone_idle_comfort_risk"


@pytest.mark.asyncio
async def test_lighting_rule_uses_lighting_telemetry_not_equipment_status():
    svc, repo = _service()
    repo.fcu_rows = [{"zone_id": "Zone-101", "occupancy_pct": 0, "fcu_inferred_running": False}]
    repo.lighting_rows = [
        {
            "zone_id": "Zone-101",
            "total_watts": 150,
            "active_luminaires": 4,
            "avg_dim_level": 60,
        }
    ]

    await svc.reconcile_site("site-002", now=datetime(2026, 6, 21, 18, 0, tzinfo=UTC))

    assert repo.created[0][0] == "operational_mismatch"
    assert repo.created[0][1].rule_key == "lighting.empty_zone_lights_on"


@pytest.mark.asyncio
async def test_no_lighting_telemetry_creates_no_lighting_finding_even_with_lighting_equipment():
    svc, repo = _service()
    repo.fcu_rows = [{"zone_id": "Zone-101", "occupancy_pct": 0, "fcu_inferred_running": False}]
    repo.equipment_by_zone = {"Zone-101": [{"code": "S002-LTG-101", "type": "lighting_panel", "status": "normal"}]}

    await svc.reconcile_site("site-002", now=datetime(2026, 6, 21, 18, 0, tzinfo=UTC))

    assert repo.created == []


@pytest.mark.asyncio
async def test_repeated_resolved_occurrence_same_bucket_promotes_to_schedule_defect():
    svc, repo = _service()
    repo.fcu_rows = [{"zone_id": "Zone-101", "occupancy_pct": 0, "fcu_inferred_running": True}]
    sunday_evening = datetime(2026, 6, 21, 18, 30, tzinfo=UTC)

    await svc.reconcile_site("site-002", now=sunday_evening)
    repo.fcu_rows = [{"zone_id": "Zone-101", "occupancy_pct": 40, "fcu_inferred_running": True}]
    # Clear debounce: first clear cycle stamps, a second past the window resolves.
    await svc.reconcile_site("site-002", now=sunday_evening + timedelta(minutes=10))
    await svc.reconcile_site("site-002", now=sunday_evening + timedelta(minutes=25))

    repo.fcu_rows = [{"zone_id": "Zone-101", "occupancy_pct": 0, "fcu_inferred_running": True}]
    await svc.reconcile_site("site-002", now=sunday_evening + timedelta(days=7))
    repo.fcu_rows = [{"zone_id": "Zone-101", "occupancy_pct": 40, "fcu_inferred_running": True}]
    await svc.reconcile_site("site-002", now=sunday_evening + timedelta(days=7, minutes=10))
    await svc.reconcile_site("site-002", now=sunday_evening + timedelta(days=7, minutes=25))

    repo.fcu_rows = [{"zone_id": "Zone-101", "occupancy_pct": 0, "fcu_inferred_running": True}]
    await svc.reconcile_site("site-002", now=sunday_evening + timedelta(days=14))

    assert [row[0] for row in repo.created] == [
        "operational_mismatch",
        "operational_mismatch",
        "schedule_defect",
    ]


@pytest.mark.asyncio
async def test_repeated_same_day_bucket_does_not_promote_to_schedule_defect():
    svc, repo = _service()
    repo.fcu_rows = [{"zone_id": "Zone-101", "occupancy_pct": 0, "fcu_inferred_running": True}]
    sunday_evening = datetime(2026, 6, 21, 18, 30, tzinfo=UTC)

    await svc.reconcile_site("site-002", now=sunday_evening)
    await svc.reconcile_site("site-002", now=sunday_evening + timedelta(minutes=5))
    await svc.reconcile_site("site-002", now=sunday_evening + timedelta(minutes=10))

    assert [row[0] for row in repo.created] == ["operational_mismatch"]


@pytest.mark.asyncio
async def test_persistent_same_condition_updates_one_active_row_without_new_occurrences():
    svc, repo = _service()
    repo.fcu_rows = [
        {
            "zone_id": "Zone-101",
            "occupancy_pct": 0,
            "room_temp_c": 22,
            "setpoint_c": 22,
            "fcu_inferred_running": True,
        }
    ]
    start = datetime(2026, 6, 21, 18, 0, tzinfo=UTC)

    created_counts = []
    for index in range(10):
        created = await svc.reconcile_site("site-002", now=start + timedelta(minutes=5 * index))
        created_counts.append(len(created))

    active_rows = [row for row in repo.rows if row["status"] == "advisory_info"]
    assert created_counts == [1, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    assert len(active_rows) == 1
    assert active_rows[0]["metadata"]["observation_count"] == 10
    assert len(repo.occurrence_calls) == 1


@pytest.mark.asyncio
async def test_continuous_condition_across_recurrence_window_does_not_promote_schedule_defect():
    svc, repo = _service()
    repo.fcu_rows = [{"zone_id": "Zone-101", "occupancy_pct": 0, "fcu_inferred_running": True}]
    sunday_evening = datetime(2026, 6, 21, 18, 30, tzinfo=UTC)

    await svc.reconcile_site("site-002", now=sunday_evening)
    await svc.reconcile_site("site-002", now=sunday_evening + timedelta(days=7))
    await svc.reconcile_site("site-002", now=sunday_evening + timedelta(days=14))

    active_rows = [row for row in repo.rows if row["status"] == "advisory_info"]
    assert [row[0] for row in repo.created] == ["operational_mismatch"]
    assert active_rows[0]["metadata"]["observation_count"] == 3
    assert len(repo.occurrence_calls) == 1


@pytest.mark.asyncio
async def test_condition_resolves_then_recurs_closes_old_row_and_opens_new_occurrence():
    svc, repo = _service()
    start = datetime(2026, 6, 21, 18, 0, tzinfo=UTC)
    repo.fcu_rows = [{"zone_id": "Zone-101", "occupancy_pct": 0, "fcu_inferred_running": True}]

    await svc.reconcile_site("site-002", now=start)
    repo.fcu_rows = [{"zone_id": "Zone-101", "occupancy_pct": 40, "fcu_inferred_running": True}]
    # First clear cycle starts the debounce; a second clear cycle past
    # CLEAR_DEBOUNCE_MINUTES actually resolves the row.
    await svc.reconcile_site("site-002", now=start + timedelta(minutes=5))
    await svc.reconcile_site("site-002", now=start + timedelta(minutes=20))
    repo.fcu_rows = [{"zone_id": "Zone-101", "occupancy_pct": 0, "fcu_inferred_running": True}]
    await svc.reconcile_site("site-002", now=start + timedelta(days=7))

    assert [row[0] for row in repo.created] == ["operational_mismatch", "operational_mismatch"]
    assert len([row for row in repo.rows if row["status"] == "expired"]) == 1
    assert len([row for row in repo.rows if row["status"] == "advisory_info"]) == 1
    assert len(repo.occurrence_calls) == 2


@pytest.mark.asyncio
async def test_single_cycle_occupancy_flap_does_not_resolve_advisory():
    """One noisy clear cycle (fused occupancy spiking past 5%) must not churn
    the advisory — observed 2026-07-05: 4 create/resolve episodes per zone on
    a closed Sunday while the physical condition never cleared."""
    svc, repo = _service()
    start = datetime(2026, 6, 21, 18, 0, tzinfo=UTC)

    repo.fcu_rows = [{"zone_id": "Zone-101", "occupancy_pct": 0, "fcu_inferred_running": True}]
    await svc.reconcile_site("site-002", now=start)

    # Single-cycle occupancy spike: debounce starts, row stays active.
    repo.fcu_rows = [{"zone_id": "Zone-101", "occupancy_pct": 17.1, "fcu_inferred_running": True}]
    await svc.reconcile_site("site-002", now=start + timedelta(minutes=5))
    assert len([row for row in repo.rows if row["status"] == "expired"]) == 0
    assert repo.rows[0]["metadata"].get("pending_clear_since") is not None

    # Condition re-observed: debounce aborted, same row keeps accumulating.
    repo.fcu_rows = [{"zone_id": "Zone-101", "occupancy_pct": 0, "fcu_inferred_running": True}]
    await svc.reconcile_site("site-002", now=start + timedelta(minutes=10))
    assert len(repo.created) == 1
    assert repo.rows[0]["metadata"].get("pending_clear_since") is None
    assert repo.rows[0]["metadata"]["observation_count"] == 2

    # Sustained clear (two cycles spanning >= debounce) does resolve.
    repo.fcu_rows = [{"zone_id": "Zone-101", "occupancy_pct": 60, "fcu_inferred_running": True}]
    await svc.reconcile_site("site-002", now=start + timedelta(minutes=15))
    await svc.reconcile_site("site-002", now=start + timedelta(minutes=30))
    assert len([row for row in repo.rows if row["status"] == "expired"]) == 1
    assert repo.rows[0]["metadata"]["resolution_reason"] == "condition_cleared"


def test_recurrence_bucket_uses_day_of_week_and_two_hour_local_bucket():
    # 16:30 UTC = 18:30 SAST on Sunday 2026-06-21
    assert recurrence_bucket(datetime(2026, 6, 21, 16, 30, tzinfo=UTC)) == (6, "18:00-20:00")


def test_missing_zone_key_gap_scope_only_live_zone_relevant_equipment():
    assert _is_zone_relevant_equipment({"type": "lighting_driver", "status": "normal"}) is True
    assert _is_zone_relevant_equipment({"type": "ahu", "status": "needs_attention"}) is True
    assert _is_zone_relevant_equipment({"type": "lighting_panel", "status": "offline"}) is False
    assert _is_zone_relevant_equipment({"type": "meter", "status": "normal"}) is False


@pytest.mark.asyncio
async def test_scheduler_reflex_reconciliation_does_not_call_optimizer(monkeypatch):
    import app.services.background_scheduler as scheduler_module

    class FakeService:
        async def reconcile_all_sites(self):
            return {"site-002": 0}

    monkeypatch.setattr(
        "app.services.reflex_reconciliation_service.get_reflex_reconciliation_service",
        lambda: FakeService(),
    )
    monkeypatch.setattr(
        "app.services.ai_optimizer.get_ai_optimizer",
        lambda: (_ for _ in ()).throw(AssertionError("reflex must not call optimizer")),
    )

    scheduler = scheduler_module.BackgroundSchedulerService()
    await scheduler._run_reflex_reconciliation_async()
