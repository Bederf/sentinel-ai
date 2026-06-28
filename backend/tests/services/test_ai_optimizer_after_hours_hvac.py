"""Regression tests for deterministic after-hours HVAC advisories."""

from datetime import datetime
from typing import Any

import pytest

from app.models.device import (
    DeviceEquipment,
    DeviceLocation,
    DevicePoint,
    DeviceType,
    HVACDevice,
    PointType,
    ProtocolType,
)
from app.models.recommendation import RecommendationStatus
from app.models.optimization import OptimizationRecommendation
from app.services.ai_optimizer import AIOptimizerService


def _optimizer() -> AIOptimizerService:
    optimizer = AIOptimizerService()
    optimizer._sites = [
        {
            "id": "site-002",
            "name": "S002",
            "operating_hours": {"start": "08:00", "end": "18:00"},
        }
    ]
    return optimizer


def _optimizer_with_site_005() -> AIOptimizerService:
    optimizer = _optimizer()
    optimizer._sites.append(
        {
            "id": "site-005",
            "name": "Busamed Gateway Private Hospital",
            "type": "hospital",
            "operating_hours": {
                "monday": {"start": "00:00", "end": "23:59", "operational": True},
                "tuesday": {"start": "00:00", "end": "23:59", "operational": True},
                "wednesday": {"start": "00:00", "end": "23:59", "operational": True},
                "thursday": {"start": "00:00", "end": "23:59", "operational": True},
                "friday": {"start": "00:00", "end": "23:59", "operational": True},
                "saturday": {"start": "00:00", "end": "23:59", "operational": True},
                "sunday": {"start": "00:00", "end": "23:59", "operational": True},
            },
        }
    )
    return optimizer


def _chiller() -> HVACDevice:
    return HVACDevice(
        id="S002-CHILLER-B01",
        name="S002 Chiller B01",
        device_type=DeviceType.HVAC,
        protocol=ProtocolType.MOCK,
        site_id="site-002",
        device_location=DeviceLocation(
            building="S002",
            floor="B1",
            zone="Plant",
            room="Chiller Plant",
            description="Basement chiller plant",
        ),
        equipment=DeviceEquipment(manufacturer="Test", model="CH-1"),
        hvac_type="chiller",
        points={},
    )


def _ahu() -> HVACDevice:
    return HVACDevice(
        id="S002-AHU-B01",
        name="S002 AHU B01",
        device_type=DeviceType.HVAC,
        protocol=ProtocolType.MOCK,
        site_id="site-002",
        device_location=DeviceLocation(
            building="S002",
            floor="B1",
            zone="Plant",
            room="AHU Plant",
            description="Basement AHU plant",
        ),
        equipment=DeviceEquipment(manufacturer="Test", model="AHU-1"),
        hvac_type="ahu",
        points={
            "fresh_air_damper": DevicePoint(
                name="fresh_air_damper",
                point_type=PointType.ANALOG_OUTPUT,
                unit="%",
                default_value=20.0,
                writable=True,
            ),
            "supply_air_temp_setpoint": DevicePoint(
                name="supply_air_temp_setpoint",
                point_type=PointType.ANALOG_OUTPUT,
                unit="°C",
                default_value=12.0,
                writable=True,
            ),
        },
    )


def _conditions(
    timestamp: str, occupancy: float = 0, hvac_kw: float = 24.0, site_peak_kw: float | None = None
) -> dict[str, Any]:
    conditions: dict[str, Any] = {
        "timestamp": timestamp,
        "indoor_temp": 22.0,
        "outdoor_temp": 22.0,
        "humidity": 55.0,
        "site_aggregate": {
            "total_occupancy": occupancy,
            "occupied_zones": 0 if occupancy == 0 else 1,
            "zone_count": 20,
        },
        "electrical": {
            "hvac_kw": hvac_kw,
            "total_kw": 30.0,
        },
        "active_urgent_work_orders": [],
    }
    if site_peak_kw is not None:
        conditions["site_peak_kw"] = site_peak_kw
        conditions["electrical"]["site_peak_kw"] = site_peak_kw
    return conditions


def test_day_keyed_247_hospital_schedule_is_inside_operating_hours_on_weekday():
    optimizer = _optimizer_with_site_005()

    assert optimizer._is_outside_site_operating_hours("site-005", datetime(2026, 6, 22, 6, 38)) is False


def test_day_keyed_247_hospital_schedule_is_inside_operating_hours_on_weekend():
    optimizer = _optimizer_with_site_005()

    assert optimizer._is_outside_site_operating_hours("site-005", datetime(2026, 6, 21, 6, 38)) is False


def test_day_keyed_closed_day_is_outside_operating_hours():
    optimizer = _optimizer_with_site_005()
    site_005 = next(site for site in optimizer._sites if site["id"] == "site-005")
    site_005["operating_hours"]["sunday"] = {"start": "00:00", "end": "23:59", "operational": False}

    assert optimizer._is_outside_site_operating_hours("site-005", datetime(2026, 6, 21, 6, 38)) is True


def test_partial_carbon_context_does_not_crash_full_context_formatter():
    optimizer = _optimizer()

    text = optimizer._format_full_context(
        {
            "carbon": {
                "site_id": "site-005",
                "estimated_load_kw": 174.5,
                "source": "electrical_telemetry",
            }
        }
    )

    assert "CARBON & ESG" in text
    assert "Grid import: 174.5 kW" in text


def _after_hours_recs(result):
    return [
        rec
        for rec in result.recommendations
        if rec.get("metadata", {}).get("rule")
        in {"after_hours_zero_occupancy_hvac_load", "closed_empty_building_hvac_running"}
    ]


def _with_served_zone_context(
    optimizer: AIOptimizerService,
    conditions: dict,
    mapping: dict[str, list[str]],
    states: list[dict],
    zone_metadata: dict | None = None,
) -> dict:
    conditions = dict(conditions)
    conditions["_served_zone_gate_context"] = optimizer._build_served_zone_gate_context(
        "site-002",
        conditions,
        {"hvac": [_ahu()], "power": [], "lighting": [], "meter": []},
        mapping,
        states,
        zone_metadata or {},
    )
    return conditions


def test_after_hours_zero_occupancy_hvac_load_generates_manual_advisory():
    optimizer = _optimizer()

    result = optimizer._analyze_with_rules(
        "site-002",
        _conditions("2026-06-18T22:00:00"),
        weather_forecast={},
        energy_prices={"current_rate": 2.28},
        equipment_inventory={"hvac": [_chiller()], "power": [], "lighting": [], "meter": []},
    )

    recs = _after_hours_recs(result)
    assert len(recs) == 1
    rec = recs[0]
    assert rec["target_equipment"] == "S002-CHILLER-B01"
    assert rec["confidence"] == 0.72
    assert rec["action"]["point"] is None
    assert rec["action"]["execution_blocked"] is True
    assert rec["metadata"]["rule"] == "closed_empty_building_hvac_running"


def test_after_hours_hvac_rule_does_not_fire_during_operating_hours():
    optimizer = _optimizer()

    result = optimizer._analyze_with_rules(
        "site-002",
        _conditions("2026-06-18T10:00:00"),
        weather_forecast={},
        energy_prices={"current_rate": 2.28},
        equipment_inventory={"hvac": [_chiller()], "power": [], "lighting": [], "meter": []},
    )

    assert _after_hours_recs(result) == []


def test_after_hours_hvac_rule_does_not_fire_when_occupied():
    optimizer = _optimizer()

    result = optimizer._analyze_with_rules(
        "site-002",
        _conditions("2026-06-18T22:00:00", occupancy=2),
        weather_forecast={},
        energy_prices={"current_rate": 2.28},
        equipment_inventory={"hvac": [_chiller()], "power": [], "lighting": [], "meter": []},
    )

    assert _after_hours_recs(result) == []


def test_aggregate_zero_with_fused_occupancy_conflict_emits_conflict_advisory_not_shutdown():
    optimizer = _optimizer()

    class _Conflict:
        signals = ("simbiot_aggregate", "co2_elevation")
        delta_pct = 100.0
        description = "simbiot_aggregate (0%) vs co2_elevation (100%) — Δ100pp"

    class _Signal:
        def __init__(self, source, pct, confidence, raw_value):
            self.source = source
            self.normalized_pct = pct
            self.confidence = confidence
            self.freshness_minutes = 2.0
            self.is_available = True
            self.raw_value = raw_value

    class _Fused:
        occupancy_percent = 100.0
        occupancy_count = 0
        confidence = 0.6
        is_occupied = True
        is_uncertain = True
        may_suppress = False
        gate_override = "conflict_uncertain"
        conflicts = (_Conflict(),)
        signals = {
            "simbiot_aggregate": _Signal("simbiot_aggregate", 0.0, 0.95, {"total_occupancy": 0}),
            "co2_elevation": _Signal("co2_elevation", 100.0, 0.6, {"avg_co2": 1100.0}),
        }

    recommendations = optimizer._append_after_hours_zero_occupancy_advisory(
        "site-002",
        {
            **_conditions("2026-06-18T22:00:00", occupancy=0, hvac_kw=24.0),
            "_fused_occupancy": _Fused(),
        },
        {"hvac": [_chiller()], "power": [], "lighting": [], "meter": []},
        [],
    )

    assert _after_hours_recs(type("Result", (), {"recommendations": recommendations})()) == []
    conflict_recs = [
        rec
        for rec in recommendations
        if rec.get("metadata", {}).get("rule") == "occupancy_conflict_blocks_hvac_shutdown"
    ]
    assert len(conflict_recs) == 1
    rec = conflict_recs[0]
    assert rec["risk_level"] == "medium"
    assert rec["confidence"] == 0.42
    assert rec["action"]["execution_blocked"] is True
    assert rec["action"]["blocker"] == "occupancy_signal_conflict"
    assert "Hold blanket HVAC shutdown" in rec["recommended_value"]
    assert rec["metadata"]["blocked_rule"] == "closed_empty_building_hvac_running"


def test_closed_empty_hvac_context_uses_site_specific_peak_threshold():
    optimizer = _optimizer()

    context = optimizer._closed_empty_hvac_context(
        "site-002",
        _conditions("2026-06-18T22:00:00", occupancy=0, hvac_kw=14.21, site_peak_kw=100.0),
    )

    assert context is not None
    assert context["threshold_kw"] == pytest.approx(8.0)
    assert context["hvac_kw"] == pytest.approx(14.21)


def test_closed_empty_hvac_context_uses_conservative_fallback_when_peak_is_missing():
    optimizer = _optimizer()

    context = optimizer._closed_empty_hvac_context(
        "site-002",
        _conditions("2026-06-18T22:00:00", occupancy=0, hvac_kw=14.21),
    )

    assert context is not None
    assert context["threshold_kw"] == pytest.approx(2.5)


def test_after_hours_advisory_is_enforced_when_llm_returns_no_recommendations():
    optimizer = _optimizer()

    recommendations = optimizer._append_after_hours_zero_occupancy_advisory(
        "site-002",
        _conditions("2026-06-18T22:00:00", occupancy=0, hvac_kw=24.0),
        {"hvac": [_chiller()], "power": [], "lighting": [], "meter": []},
        [],
    )

    recs = [
        rec
        for rec in recommendations
        if rec.get("metadata", {}).get("rule")
        in {"after_hours_zero_occupancy_hvac_load", "closed_empty_building_hvac_running"}
    ]
    assert len(recs) == 1
    assert recs[0]["target_equipment"] == "S002-CHILLER-B01"
    assert recs[0]["action"]["point"] is None
    assert recs[0]["action"]["execution_blocked"] is True
    assert recs[0]["action"]["blocker"] == "missing_verified_plant_enable_or_schedule_point"
    assert recs[0]["metadata"]["enforced_after_llm"] is True
    assert recs[0]["metadata"]["advisory_type"] == "site_profile_hvac_state_correction"


def test_after_hours_advisory_uses_existing_hvac_action_when_inventory_is_empty():
    optimizer = _optimizer()

    recommendations = optimizer._append_after_hours_zero_occupancy_advisory(
        "site-002",
        _conditions("2026-06-18T22:00:00", occupancy=0, hvac_kw=24.0),
        {"hvac": []},
        [
            {
                "target_equipment": "S002-CHILLER-B01",
                "equipment_name": "Chiller B01",
                "action": {"point": "chilled_water_setpoint", "value": 12.0},
            }
        ],
    )

    recs = [
        rec
        for rec in recommendations
        if rec.get("metadata", {}).get("rule")
        in {"after_hours_zero_occupancy_hvac_load", "closed_empty_building_hvac_running"}
    ]
    assert len(recs) == 1
    assert recs[0]["target_equipment"] == "SITE-002-HVAC-SCHEDULE"
    assert "Shut down or setback non-critical HVAC" in recs[0]["recommended_value"]


def test_closed_empty_building_suppresses_free_cooling_runtime_tuning():
    optimizer = _optimizer()

    result = optimizer._analyze_with_rules(
        "site-002",
        {
            **_conditions("2026-06-21T19:00:00", occupancy=0, hvac_kw=30.0),
            "outdoor_temp": 10.0,
            "humidity": 50.0,
        },
        weather_forecast={},
        energy_prices={"current_rate": 2.28},
        equipment_inventory={"hvac": [_chiller(), _ahu()], "power": [], "lighting": [], "meter": []},
    )

    recs = result.recommendations
    policy_recs = _after_hours_recs(result)
    assert len(policy_recs) == 1
    assert policy_recs[0]["metadata"]["rule"] == "closed_empty_building_hvac_running"
    assert not any((rec.get("point_name") or "") in {"fresh_air_damper", "supply_air_temp_setpoint"} for rec in recs)


def test_empty_served_zones_suppress_ahu_runtime_tuning_and_emit_operating_state_advisory():
    optimizer = _optimizer()
    conditions = _with_served_zone_context(
        optimizer,
        {
            **_conditions("2026-06-21T19:00:00", occupancy=1, hvac_kw=14.0),
            "outdoor_temp": 10.0,
            "humidity": 50.0,
        },
        {"S002-AHU-B01": ["Zone-101", "Zone-102"]},
        [
            {
                "zone_id": "Zone-101",
                "occupancy_pct": 0,
                "room_temp_c": 16.98,
                "setpoint_c": 22.0,
                "fcu_inferred_running": True,
                "timestamp": "2026-06-21T18:58:00",
            },
            {
                "zone_id": "Zone-102",
                "occupancy_pct": 0,
                "room_temp_c": 17.2,
                "setpoint_c": 22.0,
                "fcu_inferred_running": True,
                "timestamp": "2026-06-21T18:58:00",
            },
        ],
    )

    filtered = optimizer._filter_equipment_inventory_by_served_zone_gate(
        {"hvac": [_ahu()], "power": [], "lighting": [], "meter": []},
        conditions,
    )
    assert filtered["hvac"] == []

    result = optimizer._analyze_with_rules(
        "site-002",
        conditions,
        weather_forecast={},
        energy_prices={"current_rate": 2.28},
        equipment_inventory={"hvac": [_ahu()], "power": [], "lighting": [], "meter": []},
    )

    assert not any((rec.get("point_name") or "") == "supply_air_temp_setpoint" for rec in result.recommendations)
    served_zone_recs = [
        rec
        for rec in result.recommendations
        if rec.get("metadata", {}).get("rule") == "closed_empty_served_zones_hvac_running"
    ]
    assert len(served_zone_recs) == 1
    assert served_zone_recs[0]["target_equipment"] == "S002-AHU-B01"
    assert served_zone_recs[0]["metadata"]["any_occupied_zone_blocks_suppression"] is True
    assert served_zone_recs[0]["metadata"]["all_served_zones_empty_required"] is True
    assert served_zone_recs[0]["metadata"]["suppressed_recommendation_count"] >= 1


def test_any_occupied_served_zone_blocks_zone_level_suppression():
    optimizer = _optimizer()
    conditions = _with_served_zone_context(
        optimizer,
        {
            **_conditions("2026-06-21T19:00:00", occupancy=1, hvac_kw=14.0),
            "outdoor_temp": 10.0,
            "humidity": 50.0,
        },
        {"S002-AHU-B01": ["Zone-101", "Zone-102"]},
        [
            {
                "zone_id": "Zone-101",
                "occupancy_pct": 0,
                "room_temp_c": 17.0,
                "setpoint_c": 22.0,
                "timestamp": "2026-06-21T18:58:00",
            },
            {
                "zone_id": "Zone-102",
                "occupancy_pct": 12,
                "room_temp_c": 22.0,
                "setpoint_c": 22.0,
                "timestamp": "2026-06-21T18:58:00",
            },
        ],
    )

    result = optimizer._analyze_with_rules(
        "site-002",
        conditions,
        weather_forecast={},
        energy_prices={"current_rate": 2.28},
        equipment_inventory={"hvac": [_ahu()], "power": [], "lighting": [], "meter": []},
    )

    assert any((rec.get("point_name") or "") == "supply_air_temp_setpoint" for rec in result.recommendations)
    assert not any(
        rec.get("metadata", {}).get("rule") == "closed_empty_served_zones_hvac_running"
        for rec in result.recommendations
    )


def test_stale_served_zone_state_allows_optimization_and_marks_coverage_gap():
    optimizer = _optimizer()
    conditions = _with_served_zone_context(
        optimizer,
        {
            **_conditions("2026-06-21T19:00:00", occupancy=1, hvac_kw=14.0),
            "outdoor_temp": 10.0,
            "humidity": 50.0,
        },
        {"S002-AHU-B01": ["Zone-101"]},
        [
            {
                "zone_id": "Zone-101",
                "occupancy_pct": 0,
                "room_temp_c": 17.0,
                "setpoint_c": 22.0,
                "timestamp": "2026-06-21T17:30:00",
            }
        ],
    )

    decision = conditions["_served_zone_gate_context"]["decisions"]["S002-AHU-B01"]
    assert decision["suppress"] is False
    assert decision["coverage_gap"] == "missing_or_stale_zone_state"

    result = optimizer._analyze_with_rules(
        "site-002",
        conditions,
        weather_forecast={},
        energy_prices={"current_rate": 2.28},
        equipment_inventory={"hvac": [_ahu()], "power": [], "lighting": [], "meter": []},
    )

    assert any((rec.get("point_name") or "") == "supply_air_temp_setpoint" for rec in result.recommendations)


def test_utc_served_zone_state_timestamp_is_treated_as_fresh_sast_telemetry():
    optimizer = _optimizer()
    conditions = _with_served_zone_context(
        optimizer,
        {
            **_conditions("2026-06-22T06:20:00+02:00", occupancy=1, hvac_kw=14.0),
            "outdoor_temp": 10.0,
            "humidity": 50.0,
        },
        {"S002-AHU-B01": ["Zone-101"]},
        [
            {
                "zone_id": "Zone-101",
                "occupancy_pct": 5,
                "room_temp_c": 17.0,
                "setpoint_c": 22.0,
                "timestamp": "2026-06-22T04:20:00+00:00",
            }
        ],
    )

    decision = conditions["_served_zone_gate_context"]["decisions"]["S002-AHU-B01"]
    assert decision["suppress"] is True
    assert decision["reason_code"] == "all_served_zones_empty_outside_hours"


def test_served_zone_gate_keeps_direct_fcu_shutdown_action():
    optimizer = _optimizer()
    conditions = {
        **_conditions("2026-06-21T19:00:00", occupancy=1, hvac_kw=14.0),
        "_served_zone_gate_context": {
            "rule": "closed_empty_served_zones_hvac_running",
            "decisions": {
                "S002-FCU-001": {
                    "suppress": True,
                    "served_zones": ["Zone-101"],
                    "empty_zones": [{"zone_id": "Zone-101", "occupancy_pct": 0}],
                    "occupied_zones": [],
                }
            },
        },
    }
    shutdown_rec = {
        "equipment_id": "S002-FCU-001",
        "target_equipment": "S002-FCU-001",
        "point_name": "fan_speed",
        "recommended_value": "0speed",
        "reason": "Zone unoccupied and below safety minimum. Turn off FCU.",
        "system": "hvac",
    }

    gated = optimizer._apply_served_zone_runtime_gate(
        "site-002",
        conditions,
        {"hvac": [], "power": [], "lighting": [], "meter": []},
        [shutdown_rec],
    )

    assert gated == [shutdown_rec]


@pytest.mark.asyncio
async def test_served_zone_gate_expires_stale_active_runtime_tuning_recommendations(monkeypatch):
    optimizer = _optimizer()

    class StoredRec:
        def __init__(self, rec_id, action, reason):
            self.id = rec_id
            self.site_id = "site-002"
            self.status = RecommendationStatus.PENDING
            self.target_equipment = "S002-AHU-B01"
            self.action_type = "ai_optimization"
            self.action = action
            self.reason = reason
            self.metadata = {}

    stale_runtime = StoredRec(
        "runtime",
        {"point": "supply_air_temp_setpoint", "value": 13},
        "Raise SAT setpoint for runtime optimization.",
    )
    shutdown = StoredRec(
        "shutdown",
        {"point": "fan_speed", "value": 0},
        "Turn off FCU because the zone is empty.",
    )

    class FakeRepo:
        def __init__(self):
            self.updated = []

        async def get_by_status(self, *_args, **_kwargs):
            return [stale_runtime, shutdown]

        async def update(self, _rec_id, rec):
            self.updated.append(rec)
            return rec

    repo = FakeRepo()
    monkeypatch.setattr(
        "app.database.repositories.recommendation_repository.get_recommendation_repository",
        lambda: repo,
    )

    expired = await optimizer._expire_stale_served_zone_runtime_recommendations(
        "site-002",
        [
            {
                "target_equipment": "S002-AHU-B01",
                "metadata": {"rule": "closed_empty_served_zones_hvac_running"},
            }
        ],
    )

    assert expired == 1
    assert stale_runtime.status == RecommendationStatus.EXPIRED
    assert stale_runtime.metadata["superseded_by_rule"] == "closed_empty_served_zones_hvac_running"
    assert shutdown.status == RecommendationStatus.PENDING


@pytest.mark.asyncio
async def test_closed_empty_building_gate_skips_llm_equipment_optimization(monkeypatch):
    optimizer = _optimizer()

    async def _boom(*_args, **_kwargs):
        raise AssertionError("LLM equipment optimizer should not be called")

    async def _noop_init():
        return None

    async def _noop_quality_gate(_site_id, recommendation):
        return recommendation

    async def _noop_health_features(_site_id, recommendation):
        return recommendation

    async def _list_devices_by_site(_site_id):
        return [_chiller(), _ahu()]

    monkeypatch.setattr("app.services.ai_optimizer.ensure_device_manager_initialized", _noop_init)
    monkeypatch.setattr("app.services.ai_optimizer.device_manager.list_devices_by_site", _list_devices_by_site)
    monkeypatch.setattr(optimizer, "_gather_lighting_zone_data", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(optimizer, "_analyze_with_claude", _boom)
    monkeypatch.setattr(optimizer, "_apply_quality_gate", _noop_quality_gate)
    monkeypatch.setattr(optimizer, "_enrich_with_health_features", _noop_health_features)

    result = await optimizer.analyze_building(
        "site-002",
        current_conditions=_conditions("2026-06-21T19:00:00", occupancy=0, hvac_kw=30.0),
        weather_forecast={"source": "test", "forecast": []},
        energy_prices={"current_rate": 2.28},
    )

    assert len(result.recommendations) == 1
    assert result.recommendations[0]["metadata"]["rule"] == "closed_empty_building_hvac_running"


@pytest.mark.asyncio
async def test_open_occupied_building_uses_normal_llm_optimization_path(monkeypatch):
    optimizer = _optimizer()
    called = False

    async def _noop_init():
        return None

    async def _noop_quality_gate(_site_id, recommendation):
        return recommendation

    async def _noop_health_features(_site_id, recommendation):
        return recommendation

    async def _noop_ml_context(_site_id, _equipment_inventory):
        return {}

    async def _noop_decision_memory(_site_id):
        return ""

    async def _noop_precompute(**_kwargs):
        return {}

    async def _list_devices_by_site(_site_id):
        return [_chiller(), _ahu()]

    async def _llm_recommendation(site_id, *_args, **_kwargs):
        nonlocal called
        called = True
        return OptimizationRecommendation(
            site_id=site_id,
            timestamp="2026-06-22T10:00:00",
            recommendations=[
                {
                    "equipment_code": "S002-AHU-B01",
                    "equipment_name": "S002 AHU B01",
                    "point_name": "supply_air_temp_setpoint",
                    "recommended_value": 16.0,
                    "confidence": 0.82,
                    "reason": "Normal occupied-hours equipment optimization.",
                }
            ],
            projected_savings={"cost_zar_per_hour": 1.2},
            confidence=0.82,
        )

    monkeypatch.setattr("app.services.ai_optimizer.ensure_device_manager_initialized", _noop_init)
    monkeypatch.setattr("app.services.ai_optimizer.device_manager.list_devices_by_site", _list_devices_by_site)
    monkeypatch.setattr(optimizer, "_gather_lighting_zone_data", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(optimizer, "_gather_ml_context", _noop_ml_context)
    monkeypatch.setattr(optimizer, "_gather_decision_memory", _noop_decision_memory)
    monkeypatch.setattr(optimizer, "_gather_feedback_success_rates", lambda *_args, **_kwargs: "")
    monkeypatch.setattr(optimizer.context_precompute_service, "compute", _noop_precompute)

    async def _build_prompt(*_args, **_kwargs):
        return "prompt"

    monkeypatch.setattr(optimizer, "_build_optimization_prompt", _build_prompt)
    monkeypatch.setattr(optimizer, "_analyze_with_claude", _llm_recommendation)
    monkeypatch.setattr(optimizer, "_apply_quality_gate", _noop_quality_gate)
    monkeypatch.setattr(optimizer, "_enrich_with_health_features", _noop_health_features)

    result = await optimizer.analyze_building(
        "site-002",
        current_conditions=_conditions("2026-06-22T10:00:00", occupancy=12, hvac_kw=30.0),
        weather_forecast={"source": "test", "forecast": []},
        energy_prices={"current_rate": 2.28},
    )

    assert called is True
    assert len(result.recommendations) == 1
    assert result.recommendations[0]["equipment_code"] == "S002-AHU-B01"
    assert result.recommendations[0].get("metadata", {}).get("rule") != "closed_empty_building_hvac_running"
