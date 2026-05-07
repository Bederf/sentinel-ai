from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.api.settings import load_settings

RiskBand = Literal["low", "medium", "high", "critical"]
PolicyLevel = Literal["site_asset_criticality", "site_asset", "site", "posture", "system"]
ConstraintType = Literal["comfort", "asset", "cost", "compliance"]
HealthState = Literal["healthy", "stable", "watch", "degraded", "critical"]
HealthTrend = Literal["improving", "flat", "declining", "volatile"]
Criticality = Literal["low", "medium", "high", "mission_critical"]


@dataclass(frozen=True)
class AffectedScope:
    zones: list[str]
    assets: list[str]
    occupants_estimate: int | None


@dataclass(frozen=True)
class AssetContext:
    asset_class: str
    criticality: Criticality


@dataclass(frozen=True)
class ResolvedPolicy:
    risk_thresholds: dict[str, int]
    policy_source: str
    policy_level: PolicyLevel
    constraint_type: ConstraintType


@dataclass(frozen=True)
class ResolvedRisk:
    score: float
    band: RiskBand
    reason: str
    policy_source: str
    policy_level: PolicyLevel
    constraint_type: ConstraintType
    time_to_constraint_breach_min: int | None
    affected_scope: AffectedScope


@dataclass(frozen=True)
class ResolvedHealth:
    score: float
    state: HealthState
    trend: HealthTrend
    reason: str
    asset_class: str
    criticality: Criticality


@dataclass(frozen=True)
class CockpitResolution:
    risk: ResolvedRisk
    health: ResolvedHealth


@dataclass(frozen=True)
class PolicyOverride:
    risk_thresholds: dict[str, int]
    constraint_type: ConstraintType
    policy_source: str
    policy_level: PolicyLevel


SYSTEM_POLICY_FALLBACK = {"medium": 31, "high": 61, "critical": 81}
SYSTEM_HEALTH_FALLBACK = {"healthy": 80, "warning": 60, "critical": 0}

POSTURE_POLICIES: dict[str, PolicyOverride] = {
    "comfort_priority": PolicyOverride(
        risk_thresholds={"medium": 28, "high": 55, "critical": 76},
        constraint_type="comfort",
        policy_source="posture.comfort.default",
        policy_level="posture",
    ),
    "energy_priority": PolicyOverride(
        risk_thresholds={"medium": 36, "high": 66, "critical": 86},
        constraint_type="cost",
        policy_source="posture.energy.default",
        policy_level="posture",
    ),
    "asset_priority": PolicyOverride(
        risk_thresholds={"medium": 30, "high": 57, "critical": 74},
        constraint_type="asset",
        policy_source="posture.asset.default",
        policy_level="posture",
    ),
}

SITE_POLICIES: dict[str, PolicyOverride] = {
    "site-002": PolicyOverride(
        risk_thresholds={"medium": 27, "high": 54, "critical": 74},
        constraint_type="comfort",
        policy_source="site-002.default",
        policy_level="site",
    ),
}

SITE_ASSET_POLICIES: dict[tuple[str, str], PolicyOverride] = {
    ("site-002", "chiller"): PolicyOverride(
        risk_thresholds={"medium": 25, "high": 50, "critical": 70},
        constraint_type="comfort",
        policy_source="site-002.chiller.default",
        policy_level="site_asset",
    ),
}

SITE_ASSET_CRITICALITY_POLICIES: dict[tuple[str, str, Criticality], PolicyOverride] = {
    ("site-002", "chiller", "high"): PolicyOverride(
        risk_thresholds={"medium": 23, "high": 47, "critical": 67},
        constraint_type="comfort",
        policy_source="site-002.chiller.high.comfort",
        policy_level="site_asset_criticality",
    ),
    ("site-002", "generator", "mission_critical"): PolicyOverride(
        risk_thresholds={"medium": 18, "high": 36, "critical": 56},
        constraint_type="asset",
        policy_source="site-002.generator.mission-critical.asset",
        policy_level="site_asset_criticality",
    ),
}


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _normalized_posture(value: str | None) -> str:
    if not value:
        return "adaptive_intelligence"
    return value.strip().lower()


def _load_system_thresholds() -> tuple[dict[str, int], dict[str, int]]:
    try:
        settings = load_settings()
    except Exception:
        return SYSTEM_HEALTH_FALLBACK, SYSTEM_POLICY_FALLBACK

    health_thresholds = settings.get("healthThresholds", SYSTEM_HEALTH_FALLBACK)
    risk_thresholds = settings.get("riskThresholds", SYSTEM_POLICY_FALLBACK)
    return health_thresholds, risk_thresholds


def infer_asset_context(site_id: str, primary_asset_id: str | None) -> AssetContext:
    asset_token = ""
    if primary_asset_id:
        parts = primary_asset_id.split("-")
        if len(parts) >= 2:
            asset_token = parts[1].strip().upper()

    asset_class = {
        "CHILLER": "chiller",
        "AHU": "ahu",
        "FCU": "fcu",
        "VAV": "vav",
        "PMP": "pump",
        "GEN": "generator",
    }.get(asset_token, "hvac")

    if asset_class == "generator":
        criticality: Criticality = "mission_critical"
    elif site_id == "site-002" and asset_class == "chiller":
        criticality = "high"
    elif asset_class in {"pump", "ahu"}:
        criticality = "medium"
    else:
        criticality = "low"

    return AssetContext(asset_class=asset_class, criticality=criticality)


def resolve_policy(site_id: str, asset_context: AssetContext, active_posture: str | None) -> ResolvedPolicy:
    _, system_risk_thresholds = _load_system_thresholds()

    site_asset_criticality_key = (site_id, asset_context.asset_class, asset_context.criticality)
    if site_asset_criticality_key in SITE_ASSET_CRITICALITY_POLICIES:
        override = SITE_ASSET_CRITICALITY_POLICIES[site_asset_criticality_key]
        return ResolvedPolicy(
            risk_thresholds=override.risk_thresholds,
            policy_source=override.policy_source,
            policy_level=override.policy_level,
            constraint_type=override.constraint_type,
        )

    site_asset_key = (site_id, asset_context.asset_class)
    if site_asset_key in SITE_ASSET_POLICIES:
        override = SITE_ASSET_POLICIES[site_asset_key]
        return ResolvedPolicy(
            risk_thresholds=override.risk_thresholds,
            policy_source=override.policy_source,
            policy_level=override.policy_level,
            constraint_type=override.constraint_type,
        )

    if site_id in SITE_POLICIES:
        override = SITE_POLICIES[site_id]
        return ResolvedPolicy(
            risk_thresholds=override.risk_thresholds,
            policy_source=override.policy_source,
            policy_level=override.policy_level,
            constraint_type=override.constraint_type,
        )

    posture_key = _normalized_posture(active_posture)
    if posture_key in POSTURE_POLICIES:
        override = POSTURE_POLICIES[posture_key]
        return ResolvedPolicy(
            risk_thresholds=override.risk_thresholds,
            policy_source=override.policy_source,
            policy_level=override.policy_level,
            constraint_type=override.constraint_type,
        )

    return ResolvedPolicy(
        risk_thresholds=system_risk_thresholds,
        policy_source="system.default",
        policy_level="system",
        constraint_type="asset",
    )


def resolve_affected_scope(
    site_id: str,
    affected_zone_ids: list[str] | None,
    primary_asset_id: str | None,
) -> AffectedScope:
    zones = list(affected_zone_ids or [])
    assets = [primary_asset_id] if primary_asset_id else []

    if site_id == "site-002" and zones:
        occupants_estimate = 18 if any("boardroom" in zone.lower() for zone in zones) else len(zones) * 6
    elif zones:
        occupants_estimate = len(zones) * 4
    else:
        occupants_estimate = None

    return AffectedScope(zones=zones, assets=assets, occupants_estimate=occupants_estimate)


def _criticality_risk_bump(score_percent: int, thresholds: dict[str, int], criticality: Criticality) -> RiskBand | None:
    if criticality not in {"high", "mission_critical"}:
        return None
    if score_percent >= max(thresholds["critical"] - 5, thresholds["high"]):
        return "critical"
    if score_percent >= max(thresholds["high"] - 5, thresholds["medium"]):
        return "high"
    return None


def resolve_risk_band(score: float, thresholds: dict[str, int], criticality: Criticality) -> RiskBand:
    score_percent = round(clamp01(score) * 100)

    if score_percent >= thresholds["critical"]:
        return "critical"
    if score_percent >= thresholds["high"]:
        band: RiskBand = "high"
    elif score_percent >= thresholds["medium"]:
        band = "medium"
    else:
        band = "low"

    return _criticality_risk_bump(score_percent, thresholds, criticality) or band


def _humanize_constraint(constraint_type: ConstraintType) -> str:
    if constraint_type == "comfort":
        return "comfort"
    if constraint_type == "asset":
        return "asset protection"
    if constraint_type == "cost":
        return "cost"
    return "compliance"


def build_risk_reason(
    *,
    score: float,
    band: RiskBand,
    constraint_type: ConstraintType,
    time_to_constraint_breach_min: int | None,
    affected_scope: AffectedScope,
) -> str:
    if time_to_constraint_breach_min is not None:
        zone_count = len(affected_scope.zones)
        if constraint_type == "comfort" and zone_count > 0:
            scope_label = "zone" if zone_count == 1 else "zones"
            return (
                f"{zone_count} {scope_label} will breach {constraint_type} limits in "
                f"{time_to_constraint_breach_min} minutes."
            )
        return (
            f"{_humanize_constraint(constraint_type).capitalize()} breach projected within "
            f"{time_to_constraint_breach_min} minutes."
        )

    score_percent = round(clamp01(score) * 100)
    return f"Resolved {constraint_type} risk is {score_percent} and currently maps to {band}."


def _health_state_thresholds(health_thresholds: dict[str, int], criticality: Criticality) -> tuple[int, int, int, int]:
    adjustment = 0
    if criticality == "high":
        adjustment = 4
    elif criticality == "mission_critical":
        adjustment = 7

    healthy = min(100, int(health_thresholds["healthy"]) + 10 + adjustment)
    stable = min(100, int(health_thresholds["healthy"]) + adjustment)
    watch = min(100, int(health_thresholds["warning"]) + adjustment)
    degraded = max(int(health_thresholds["critical"]), int(health_thresholds["warning"]) - 20 + adjustment)
    return healthy, stable, watch, degraded


def resolve_health_state(score: float, health_thresholds: dict[str, int], criticality: Criticality) -> HealthState:
    score_percent = round(clamp01(score) * 100)
    healthy, stable, watch, degraded = _health_state_thresholds(health_thresholds, criticality)

    if score_percent >= healthy:
        return "healthy"
    if score_percent >= stable:
        return "stable"
    if score_percent >= watch:
        return "watch"
    if score_percent >= degraded:
        return "degraded"
    return "critical"


def resolve_health_trend(
    urgency_score: float,
    time_to_constraint_breach_min: int | None,
    time_confidence: str | int | float | None,
) -> HealthTrend:
    if time_to_constraint_breach_min is not None and time_to_constraint_breach_min <= 15 and urgency_score >= 0.75:
        return "volatile"

    if isinstance(time_confidence, str):
        normalized = time_confidence.strip().lower()
        if normalized in {"declining", "critical"}:
            return "declining"
        if normalized in {"stable", "steady"}:
            return "flat"

    if urgency_score >= 0.55:
        return "declining"
    if urgency_score <= 0.2:
        return "improving"
    return "flat"


def build_health_reason(
    *,
    asset_context: AssetContext,
    constraint_type: ConstraintType,
    reasoning_summary: str | None,
    urgency_components: dict[str, float] | None,
) -> str:
    if reasoning_summary:
        return reasoning_summary

    dominant_component = None
    if urgency_components:
        dominant_component = max(urgency_components.items(), key=lambda item: item[1])[0]

    if dominant_component == "comfort":
        return (
            f"{asset_context.asset_class.capitalize()} drift is pushing the building outside "
            "its normal comfort envelope."
        )
    if dominant_component == "asset_risk":
        return f"{asset_context.asset_class.capitalize()} protection signals are outside the normal operating envelope."
    if dominant_component == "cost":
        return f"{asset_context.asset_class.capitalize()} operation is outside the expected cost envelope."
    return (
        f"{asset_context.asset_class.capitalize()} condition is degrading against the active {constraint_type} posture."
    )


def resolve_health_score(
    urgency_score: float,
    asset_context: AssetContext,
    time_to_constraint_breach_min: int | None,
) -> float:
    score = 0.98 - clamp01(urgency_score) * 0.45

    if asset_context.asset_class in {"chiller", "generator"}:
        score -= 0.06
    elif asset_context.asset_class in {"ahu", "pump"}:
        score -= 0.04

    if asset_context.criticality == "high":
        score -= 0.04
    elif asset_context.criticality == "mission_critical":
        score -= 0.06

    if time_to_constraint_breach_min is not None and time_to_constraint_breach_min <= 15:
        score -= 0.08
    elif time_to_constraint_breach_min is not None and time_to_constraint_breach_min <= 60:
        score -= 0.05

    return clamp01(score)


def resolve_cockpit_contract(
    *,
    site_id: str,
    primary_asset_id: str | None,
    affected_zone_ids: list[str] | None,
    active_posture: str | None,
    urgency_score: float,
    time_to_constraint_breach_min: int | None,
    time_confidence: str | int | float | None,
    reasoning_summary: str | None,
    urgency_components: dict[str, float] | None,
) -> CockpitResolution:
    health_thresholds, _ = _load_system_thresholds()
    asset_context = infer_asset_context(site_id, primary_asset_id)
    policy = resolve_policy(site_id, asset_context, active_posture)
    affected_scope = resolve_affected_scope(site_id, affected_zone_ids, primary_asset_id)
    risk_band = resolve_risk_band(urgency_score, policy.risk_thresholds, asset_context.criticality)
    health_score = resolve_health_score(urgency_score, asset_context, time_to_constraint_breach_min)

    risk = ResolvedRisk(
        score=clamp01(urgency_score),
        band=risk_band,
        reason=build_risk_reason(
            score=urgency_score,
            band=risk_band,
            constraint_type=policy.constraint_type,
            time_to_constraint_breach_min=time_to_constraint_breach_min,
            affected_scope=affected_scope,
        ),
        policy_source=policy.policy_source,
        policy_level=policy.policy_level,
        constraint_type=policy.constraint_type,
        time_to_constraint_breach_min=time_to_constraint_breach_min,
        affected_scope=affected_scope,
    )
    health = ResolvedHealth(
        score=health_score,
        state=resolve_health_state(health_score, health_thresholds, asset_context.criticality),
        trend=resolve_health_trend(urgency_score, time_to_constraint_breach_min, time_confidence),
        reason=build_health_reason(
            asset_context=asset_context,
            constraint_type=policy.constraint_type,
            reasoning_summary=reasoning_summary,
            urgency_components=urgency_components,
        ),
        asset_class=asset_context.asset_class,
        criticality=asset_context.criticality,
    )
    return CockpitResolution(risk=risk, health=health)
