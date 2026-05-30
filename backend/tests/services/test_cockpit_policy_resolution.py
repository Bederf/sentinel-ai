from app.services.cockpit_policy_resolution import (
    AssetContext,
    infer_asset_context,
    resolve_cockpit_contract,
    resolve_policy,
    resolve_risk_band,
)


def test_site_policy_beats_posture_default() -> None:
    asset_context = AssetContext(asset_class="vav", criticality="low")

    policy = resolve_policy("site-002", asset_context, "energy_priority")

    assert policy.policy_level == "site"
    assert policy.policy_source == "site-002.default"
    assert policy.constraint_type == "comfort"


def test_asset_policy_beats_site_default() -> None:
    asset_context = infer_asset_context("site-002", "S002-CHILLER-B1-001")

    policy = resolve_policy("site-002", asset_context, "comfort_priority")

    assert policy.policy_level == "site_asset_criticality"
    assert policy.policy_source == "site-002.chiller.high.comfort"
    assert policy.risk_thresholds["critical"] == 67


def test_critical_asset_escalates_band_near_threshold() -> None:
    thresholds = {"medium": 31, "high": 61, "critical": 67}

    band = resolve_risk_band(0.64, thresholds, "high")

    assert band == "critical"


def test_contract_resolves_health_and_scope() -> None:
    resolved = resolve_cockpit_contract(
        site_id="site-002",
        primary_asset_id="S002-CHILLER-B1-001",
        affected_zone_ids=["Zone-L4-Boardroom-A", "Zone-L4-Boardroom-B"],
        active_posture="comfort_priority",
        urgency_score=0.78,
        time_to_constraint_breach_min=12,
        time_confidence="declining",
        reasoning_summary="Compressor load is rising while boardroom thermal drift accelerates.",
        urgency_components={"comfort": 0.42, "asset_risk": 0.24, "cost": 0.12},
    )

    assert resolved.risk.policy_level == "site_asset_criticality"
    assert resolved.risk.constraint_type == "comfort"
    assert resolved.risk.time_to_constraint_breach_min == 12
    assert resolved.risk.affected_scope.zones == ["Zone-L4-Boardroom-A", "Zone-L4-Boardroom-B"]
    assert resolved.risk.affected_scope.occupants_estimate == 18
    assert resolved.health.asset_class == "chiller"
    assert resolved.health.criticality == "high"
    assert resolved.health.state in ("degraded", "critical")  # depends on system thresholds
    assert resolved.health.trend == "volatile"
    assert resolved.health.reason == "Compressor load is rising while boardroom thermal drift accelerates."
