from app.services.coordinated_optimization_planner import (
    SIMBIOT_WRITE_MAPPING_BLOCKER,
    PlannerContext,
    build_coordinated_bundles,
)


def _bundle_payload(bundle):
    return bundle["metadata"]["coordination_bundle"]


def test_conflicting_recommendations_emit_suppression_bundle():
    bundles = build_coordinated_bundles(
        context=PlannerContext(site_id="site-002"),
        equipment=[],
        recommendations=[
            {
                "id": "rec-a",
                "target_equipment": "S002-AHU-B01",
                "action": {"point": "cooling_setpoint", "value": 21.0},
            },
            {
                "id": "rec-b",
                "target_equipment": "S002-AHU-B01",
                "action": {"point": "cooling_setpoint", "value": 23.0},
            },
        ],
    )

    assert len(bundles) == 1
    payload = _bundle_payload(bundles[0])
    assert payload["objective"] == "suppress_conflicting_single_equipment_recommendations"
    assert payload["affected_equipment"] == ["S002-AHU-B01"]
    assert "conflicting_recommendations_require_operator_review" in payload["blocked_reasons"]


def test_basement_plant_context_emits_read_only_bundle():
    bundles = build_coordinated_bundles(
        context=PlannerContext(site_id="site-002", site_phase="supervised"),
        equipment=[
            {"code": "S002-AHU-B01", "type": "ahu", "zone_key": "B1", "status": "warning", "health_score": 67},
            {"code": "S002-CHILLER-B01", "type": "chiller", "zone_key": "B1", "status": "normal", "health_score": 71},
            {"code": "S002-CT-B01", "type": "cooling_tower", "zone_key": "B1", "status": "warning", "health_score": 62},
        ],
    )

    assert len(bundles) == 1
    payload = _bundle_payload(bundles[0])
    assert payload["objective"] == "stabilize_plant_group_b1"
    assert payload["affected_equipment"] == ["S002-AHU-B01", "S002-CHILLER-B01", "S002-CT-B01"]
    assert payload["execution_eligibility"] == "not_executable"
    assert SIMBIOT_WRITE_MAPPING_BLOCKER in payload["blocked_reasons"]


def test_bundle_and_action_ids_are_stable_for_packaging_reruns():
    equipment = [
        {"code": "S002-AHU-B01", "type": "ahu", "zone_key": "B1", "status": "warning", "health_score": 67},
        {"code": "S002-CHILLER-B01", "type": "chiller", "zone_key": "B1", "status": "normal", "health_score": 71},
        {"code": "S002-CT-B01", "type": "cooling_tower", "zone_key": "B1", "status": "warning", "health_score": 62},
    ]

    first = build_coordinated_bundles(
        context=PlannerContext(site_id="site-002", site_phase="supervised"),
        equipment=equipment,
    )
    second = build_coordinated_bundles(
        context=PlannerContext(site_id="site-002", site_phase="supervised"),
        equipment=equipment,
    )

    first_payload = _bundle_payload(first[0])
    second_payload = _bundle_payload(second[0])
    assert first_payload["bundle_id"] == second_payload["bundle_id"]
    assert first_payload["recommended_actions"][0]["action_id"] == second_payload["recommended_actions"][0]["action_id"]


def test_zone_context_requires_multiple_related_signals():
    bundles = build_coordinated_bundles(
        context=PlannerContext(site_id="site-002"),
        equipment=[
            {"code": "S002-FCU-001", "type": "fcu", "zone_key": "Zone-L0-1", "status": "normal"},
            {"code": "S002-VAV-001", "type": "vav", "zone_key": "Zone-L0-1", "status": "warning"},
        ],
    )
    assert bundles == []

    bundles = build_coordinated_bundles(
        context=PlannerContext(site_id="site-002"),
        equipment=[
            {"code": "S002-FCU-001", "type": "fcu", "zone_key": "Zone-L0-1", "status": "warning"},
            {"code": "S002-VAV-001", "type": "vav", "zone_key": "Zone-L0-1", "status": "warning"},
        ],
    )
    assert len(bundles) == 1
    assert _bundle_payload(bundles[0])["objective"] == "coordinate_zone_zone-l0-1_terminal_response"


def test_zone_terminal_bundle_excludes_non_hvac_context_equipment():
    bundles = build_coordinated_bundles(
        context=PlannerContext(site_id="site-002"),
        equipment=[
            {"code": "S002-FCU-001", "type": "fcu", "zone_key": "Zone-L0-1", "status": "warning"},
            {"code": "S002-FCU-002", "type": "fcu", "zone_key": "Zone-L0-1", "status": "warning"},
            {"code": "S002-LTG-001", "type": "lighting", "zone_key": "Zone-L0-1", "status": "warning"},
            {"code": "S002-VAV-001", "type": "vav", "zone_key": "Zone-L0-1", "status": "warning"},
            {"code": "S002-WEATHER-001", "type": "weather", "zone_key": "Zone-L0-1", "status": "warning"},
        ],
    )

    assert len(bundles) == 1
    payload = _bundle_payload(bundles[0])
    assert payload["affected_equipment"] == ["S002-FCU-001", "S002-FCU-002", "S002-VAV-001"]
    assert "S002-LTG-001" not in payload["affected_equipment"]
    assert "S002-WEATHER-001" not in payload["affected_equipment"]


def test_active_work_order_blocks_bundle_actions():
    bundles = build_coordinated_bundles(
        context=PlannerContext(site_id="site-002", site_phase="supervised"),
        equipment=[
            {"code": "S002-AHU-B01", "type": "ahu", "zone_key": "B1", "status": "warning"},
            {"code": "S002-CHILLER-B01", "type": "chiller", "zone_key": "B1", "status": "warning"},
            {"code": "S002-CT-B01", "type": "cooling_tower", "zone_key": "B1", "status": "warning"},
        ],
        work_orders=[{"code": "WO-1", "equipment_code": "S002-AHU-B01", "status": "scheduled"}],
    )

    payload = _bundle_payload(bundles[0])
    assert "active_or_pending_work_order:WO-1" in payload["blocked_reasons"]


def test_single_ahu_fault_does_not_become_plant_bundle():
    bundles = build_coordinated_bundles(
        context=PlannerContext(site_id="site-002"),
        equipment=[
            {"code": "S002-AHU-L2-001", "type": "ahu", "zone_key": "Zone-L2-1", "status": "warning"},
        ],
        fault_signals=[
            {"equipment_code": "S002-AHU-L2-001", "fault_family": "OUT_OF_RANGE"},
        ],
    )

    assert bundles == []


def test_multiple_ahus_in_related_group_emit_airside_bundle():
    bundles = build_coordinated_bundles(
        context=PlannerContext(site_id="site-002", site_phase="supervised"),
        equipment=[
            {"code": "S002-AHU-L2-001", "type": "ahu", "zone_key": "Roof", "status": "warning"},
            {"code": "S002-AHU-R01", "type": "ahu", "zone_key": "Roof", "status": "warning"},
        ],
    )

    assert len(bundles) == 1
    payload = _bundle_payload(bundles[0])
    assert payload["objective"] == "stabilize_plant_group_roof"
    assert payload["affected_equipment"] == ["S002-AHU-L2-001", "S002-AHU-R01"]


def test_chiller_cycling_with_ahu_symptom_emits_plant_bundle():
    bundles = build_coordinated_bundles(
        context=PlannerContext(site_id="site-002", site_phase="supervised"),
        equipment=[
            {"code": "S002-AHU-B01", "type": "ahu", "zone_key": "B1", "status": "warning"},
            {"code": "S002-CHILLER-B01", "type": "chiller", "zone_key": "B1", "status": "normal"},
        ],
        fault_signals=[
            {
                "equipment_code": "S002-CHILLER-B01",
                "classification": "equipment_hunting_or_short_cycling",
                "cycle_count": 53,
            },
        ],
    )

    assert len(bundles) == 1
    payload = _bundle_payload(bundles[0])
    assert payload["objective"] == "stabilize_plant_group_b1"
    assert payload["evidence"]["fault_signal_count"] == 1


def test_cooling_tower_chiller_interaction_emits_plant_bundle_without_ahu():
    bundles = build_coordinated_bundles(
        context=PlannerContext(site_id="site-002", site_phase="supervised"),
        equipment=[
            {"code": "S002-CHILLER-B01", "type": "chiller", "zone_key": "B1", "status": "warning"},
            {"code": "S002-CT-B01", "type": "cooling_tower", "zone_key": "B1", "status": "warning"},
        ],
    )

    assert len(bundles) == 1
    payload = _bundle_payload(bundles[0])
    assert payload["affected_equipment"] == ["S002-CHILLER-B01", "S002-CT-B01"]


def test_simultaneous_multi_equipment_fault_emits_one_coordinated_bundle():
    bundles = build_coordinated_bundles(
        context=PlannerContext(site_id="site-002", site_phase="supervised"),
        equipment=[
            {"code": "S002-AHU-B01", "type": "ahu", "zone_key": "B1", "status": "normal"},
            {"code": "S002-CHILLER-B01", "type": "chiller", "zone_key": "B1", "status": "normal"},
            {"code": "S002-CT-B01", "type": "cooling_tower", "zone_key": "B1", "status": "normal"},
        ],
        fault_signals=[
            {"equipment_code": "S002-AHU-B01", "fault_family": "HIGH_LIMIT", "recorded_at": "2026-06-17T08:00:00Z"},
            {"equipment_code": "S002-CHILLER-B01", "fault_family": "HIGH_LIMIT", "recorded_at": "2026-06-17T08:00:02Z"},
            {"equipment_code": "S002-CT-B01", "fault_family": "HIGH_LIMIT", "recorded_at": "2026-06-17T08:00:04Z"},
        ],
    )

    assert len(bundles) == 1
    payload = _bundle_payload(bundles[0])
    assert payload["evidence"]["fault_signal_count"] == 3


def test_irregular_intervals_and_missed_polls_still_group_by_system_context():
    bundles = build_coordinated_bundles(
        context=PlannerContext(site_id="site-002", site_phase="supervised"),
        equipment=[
            {"code": "S002-AHU-B01", "type": "ahu", "zone_key": "B1", "status": "normal"},
            {"code": "S002-CHILLER-B01", "type": "chiller", "zone_key": "B1", "status": "normal"},
            {"code": "S002-CT-B01", "type": "cooling_tower", "zone_key": "B1", "status": "normal"},
        ],
        fault_signals=[
            {"equipment_code": "S002-AHU-B01", "fault_family": "HIGH_LIMIT", "recorded_at": "2026-06-17T08:00:00Z"},
            {"equipment_code": "S002-CHILLER-B01", "fault_family": "HIGH_LIMIT", "recorded_at": "2026-06-17T08:17:13Z"},
            {"equipment_code": "S002-CT-B01", "fault_family": "HIGH_LIMIT", "recorded_at": "2026-06-17T09:42:51Z"},
        ],
    )

    assert len(bundles) == 1
    assert _bundle_payload(bundles[0])["objective"] == "stabilize_plant_group_b1"


def test_unresolved_simbiot_write_mapping_blocker_is_always_present_until_cleared():
    bundles = build_coordinated_bundles(
        context=PlannerContext(site_id="site-002", site_phase="supervised", insurance_confirmed=True),
        equipment=[
            {"code": "S002-AHU-B01", "type": "ahu", "zone_key": "B1", "status": "warning"},
            {"code": "S002-CHILLER-B01", "type": "chiller", "zone_key": "B1", "status": "warning"},
        ],
    )

    assert SIMBIOT_WRITE_MAPPING_BLOCKER in _bundle_payload(bundles[0])["blocked_reasons"]


def test_bundle_id_is_stable_for_same_bundle_identity():
    equipment = [
        {"code": "S002-AHU-B01", "type": "ahu", "zone_key": "B1", "status": "warning"},
        {"code": "S002-CHILLER-B01", "type": "chiller", "zone_key": "B1", "status": "warning"},
    ]

    first = build_coordinated_bundles(
        context=PlannerContext(site_id="site-002", site_phase="supervised"),
        equipment=equipment,
    )
    second = build_coordinated_bundles(
        context=PlannerContext(site_id="site-002", site_phase="supervised"),
        equipment=equipment,
    )

    assert _bundle_payload(first[0])["bundle_id"] == _bundle_payload(second[0])["bundle_id"]
