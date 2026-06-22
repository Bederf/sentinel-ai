"""Read-only coordinated optimization planner.

This module builds advisory-only coordination bundles from already available
equipment, recommendation, work-order, and fault context. It does not persist
recommendations, create work orders, approve actions, or execute writes.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from typing import Any
from uuid import NAMESPACE_URL, uuid5


READ_ONLY_BLOCKER = "coordinated_bundle_read_only"
SIMBIOT_WRITE_MAPPING_BLOCKER = "missing_verified_simbiot_write_mapping"
LEGACY_JACE_BACNET_BLOCKER = "missing_jace_bacnet_device_ids"
TERMINAL_HVAC_TYPES = {"fcu", "vav"}


@dataclass(frozen=True)
class PlannerContext:
    site_id: str
    site_phase: str = "advisory"
    simbiot_write_mapping_verified: bool = False
    insurance_confirmed: bool = False
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def build_coordinated_bundles(
    *,
    context: PlannerContext,
    equipment: list[dict[str, Any]],
    recommendations: list[dict[str, Any]] | None = None,
    work_orders: list[dict[str, Any]] | None = None,
    fault_signals: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Build advisory-only coordinated optimization bundles.

    The output is intentionally shaped for ``recommendations.metadata`` under
    ``metadata.coordination_bundle``. It is not written to the database here.
    """

    recommendations = recommendations or []
    work_orders = work_orders or []
    fault_signals = fault_signals or []

    bundles: list[dict[str, Any]] = []
    conflict_bundle = _build_conflict_suppression_bundle(context, recommendations)
    if conflict_bundle:
        bundles.append(conflict_bundle)

    bundles.extend(_build_plant_bundles(context, equipment, work_orders, fault_signals))
    bundles.extend(_build_zone_bundles(context, equipment, work_orders, fault_signals))

    return bundles


def _build_conflict_suppression_bundle(
    context: PlannerContext,
    recommendations: list[dict[str, Any]],
) -> dict[str, Any] | None:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for rec in recommendations:
        target = rec.get("target_equipment") or rec.get("equipment_code") or rec.get("equipment_id")
        action = rec.get("action") if isinstance(rec.get("action"), dict) else {}
        point = action.get("point") or rec.get("point")
        if target and point:
            grouped[(str(target), str(point))].append(rec)

    conflicts: list[dict[str, Any]] = []
    for (equipment_code, point), recs in grouped.items():
        values = {
            str((rec.get("action") if isinstance(rec.get("action"), dict) else {}).get("value") or rec.get("value"))
            for rec in recs
        }
        if len(values) > 1:
            conflicts.append(
                {
                    "equipment_code": equipment_code,
                    "point": point,
                    "values": sorted(values),
                    "source_recommendation_ids": [rec.get("id") for rec in recs if rec.get("id")],
                }
            )

    if not conflicts:
        return None

    affected = sorted({conflict["equipment_code"] for conflict in conflicts})
    return _bundle(
        context=context,
        objective="suppress_conflicting_single_equipment_recommendations",
        primary_equipment=affected[0],
        affected_equipment=affected,
        zones=[],
        system_context={"conflicts": conflicts},
        recommended_actions=[],
        constraints_checked=["conflict_suppression", "site_phase", "read_only"],
        blocked_reasons=[READ_ONLY_BLOCKER, "conflicting_recommendations_require_operator_review"],
        expected_benefit={"reliability": "prevents contradictory recommendations from being actioned together"},
        confidence={"score": 0.9, "basis": "deterministic conflict check on target_equipment + point"},
        source_recommendation_ids=[
            rec_id for conflict in conflicts for rec_id in conflict.get("source_recommendation_ids", [])
        ],
        evidence={"conflict_count": len(conflicts)},
    )


def _build_plant_bundles(
    context: PlannerContext,
    equipment: list[dict[str, Any]],
    work_orders: list[dict[str, Any]],
    fault_signals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    plant_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in equipment:
        if _equipment_type(item) in {"ahu", "chiller", "cooling_tower", "pump"}:
            group = str(item.get("zone_key") or item.get("plant_group") or "").strip()
            if group:
                plant_groups[group].append(item)

    bundles: list[dict[str, Any]] = []
    for group, items in plant_groups.items():
        types = {_equipment_type(item) for item in items}
        ahu_count = sum(1 for item in items if _equipment_type(item) == "ahu")
        has_chiller_tower_pair = {"chiller", "cooling_tower"}.issubset(types)
        has_airside_plant_pair = bool({"chiller", "cooling_tower"} & types and "ahu" in types)
        has_multi_ahu_group = ahu_count >= 2
        if not (has_chiller_tower_pair or has_airside_plant_pair or has_multi_ahu_group):
            continue

        concerning = [item for item in items if _is_concerning_status(item)]
        related_faults = _signals_for_equipment(fault_signals, {_code(item) for item in items})
        if not concerning and not related_faults:
            continue

        affected = sorted(_code(item) for item in items if _code(item))
        blockers = _default_blockers(context)
        blockers.extend(_work_order_blockers(work_orders, affected))
        action = {
            "action_id": _stable_action_id(context.site_id, f"plant:{group}", affected),
            "equipment_code": affected[0],
            "affected_equipment": affected,
            "action_type": "operator_review",
            "point": None,
            "current_value": None,
            "recommended_value": None,
            "unit": None,
            "recommended_adjustment": f"Coordinate plant sequencing and setpoint strategy for group {group}",
            "reason": f"Related plant equipment in group {group} is showing warning or fault signals",
            "risk_level": "medium",
            "blocked_reasons": blockers,
            "approval_status": "blocked",
        }
        bundles.append(
            _bundle(
                context=context,
                objective=f"stabilize_plant_group_{group.lower()}",
                primary_equipment=affected[0],
                affected_equipment=affected,
                zones=[group],
                system_context={
                    "group": group,
                    "equipment_types": sorted(types),
                    "concerning_status_equipment": [_code(item) for item in concerning],
                },
                recommended_actions=[action],
                constraints_checked=_default_constraints(),
                blocked_reasons=blockers,
                expected_benefit={"reliability": "reduce repeated plant/airside instability"},
                confidence={
                    "score": 0.65,
                    "basis": "shared plant group with related AHU/chiller/cooling tower context",
                },
                evidence={"fault_signal_count": len(related_faults)},
            )
        )

    return bundles


def _build_zone_bundles(
    context: PlannerContext,
    equipment: list[dict[str, Any]],
    work_orders: list[dict[str, Any]],
    fault_signals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    zone_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in equipment:
        group = str(item.get("zone_key") or item.get("zone_id") or "").strip()
        if group and group.lower().startswith("zone-"):
            zone_groups[group].append(item)

    bundles: list[dict[str, Any]] = []
    for zone, items in zone_groups.items():
        terminal_items = [item for item in items if _equipment_type(item) in TERMINAL_HVAC_TYPES]
        if len(terminal_items) < 2:
            continue

        concerning = [item for item in terminal_items if _is_concerning_status(item)]
        related_faults = _signals_for_equipment(fault_signals, {_code(item) for item in terminal_items})
        related_equipment = {_code(item) for item in concerning}
        related_equipment.update(
            str(signal.get("equipment_code") or signal.get("target_equipment") or signal.get("equipment_id"))
            for signal in related_faults
            if signal.get("equipment_code") or signal.get("target_equipment") or signal.get("equipment_id")
        )
        if len(related_equipment) < 2:
            continue

        affected = sorted(_code(item) for item in terminal_items if _code(item))
        blockers = _default_blockers(context)
        blockers.extend(_work_order_blockers(work_orders, affected))
        bundles.append(
            _bundle(
                context=context,
                objective=f"coordinate_zone_{zone.lower()}_terminal_response",
                primary_equipment=affected[0],
                affected_equipment=affected,
                zones=[zone],
                system_context={
                    "zone_key": zone,
                    "concerning_status_equipment": [_code(item) for item in concerning],
                },
                recommended_actions=[
                    {
                        "action_id": _stable_action_id(context.site_id, f"zone:{zone}", affected),
                        "equipment_code": affected[0],
                        "affected_equipment": affected,
                        "action_type": "operator_review",
                        "point": None,
                        "current_value": None,
                        "recommended_value": None,
                        "unit": None,
                        "recommended_adjustment": f"Coordinate terminal unit response in {zone}",
                        "reason": f"Multiple related terminal units in {zone} are showing warning or fault signals",
                        "risk_level": "low",
                        "blocked_reasons": blockers,
                        "approval_status": "blocked",
                    }
                ],
                constraints_checked=_default_constraints(),
                blocked_reasons=blockers,
                expected_benefit={"comfort": "avoid isolated terminal changes that fight zone behavior"},
                confidence={"score": 0.6, "basis": "multiple related equipment signals in same zone"},
                evidence={"fault_signal_count": len(related_faults)},
            )
        )

    return bundles


def _bundle(
    *,
    context: PlannerContext,
    objective: str,
    primary_equipment: str,
    affected_equipment: list[str],
    zones: list[str],
    system_context: dict[str, Any],
    recommended_actions: list[dict[str, Any]],
    constraints_checked: list[str],
    blocked_reasons: list[str],
    expected_benefit: dict[str, Any],
    confidence: dict[str, Any],
    source_recommendation_ids: list[str] | None = None,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    execution_eligibility = (
        "draft_only" if not blocked_reasons and context.site_phase in {"supervised", "automatic"} else "not_executable"
    )
    approval_mode = "supervised_pending_approval_eligible" if execution_eligibility == "draft_only" else "advisory_only"
    bundle_id = _stable_bundle_id(
        site_id=context.site_id,
        objective=objective,
        primary_equipment=primary_equipment,
        affected_equipment=affected_equipment,
        zones=zones,
        system_context=system_context,
    )
    metadata_bundle = {
        "bundle_id": bundle_id,
        "schema_version": 1,
        "objective": objective,
        "site_id": context.site_id,
        "primary_equipment": primary_equipment,
        "affected_equipment": affected_equipment,
        "zones": zones,
        "system_context": system_context,
        "recommended_actions": recommended_actions,
        "constraints_checked": constraints_checked,
        "blocked_reasons": blocked_reasons,
        "expected_benefit": expected_benefit,
        "confidence": confidence,
        "approval_mode": approval_mode,
        "execution_eligibility": execution_eligibility,
        "source_recommendation_ids": source_recommendation_ids or [],
        "evidence": evidence or {},
        "generated_at": context.generated_at.isoformat(),
    }
    return {
        "site_id": context.site_id,
        "action_type": "coordinated_optimization",
        "target_equipment": primary_equipment,
        "action": {"execution_blocked": True, "blocker": READ_ONLY_BLOCKER},
        "reason": objective.replace("_", " "),
        "expected_impact": expected_benefit,
        "confidence": "medium",
        "confidence_score": confidence.get("score", 0.0),
        "status": "advisory",
        "requires_approval": False,
        "metadata": {"coordination_bundle": metadata_bundle},
    }


def _default_constraints() -> list[str]:
    return [
        "safety_limits",
        "site_phase",
        "work_orders",
        "equipment_status",
        "simbiot_write_mapping",
        "insurance",
        "read_only",
    ]


def _default_blockers(context: PlannerContext) -> list[str]:
    blockers = [READ_ONLY_BLOCKER]
    if not context.simbiot_write_mapping_verified:
        blockers.append(SIMBIOT_WRITE_MAPPING_BLOCKER)
    if not context.insurance_confirmed:
        blockers.append("insurance_not_confirmed")
    if context.site_phase not in {"supervised", "automatic"}:
        blockers.append(f"site_phase_{context.site_phase}_not_supervised")
    return blockers


def _work_order_blockers(work_orders: list[dict[str, Any]], equipment_codes: list[str]) -> list[str]:
    active_statuses = {"open", "scheduled", "assigned", "in_progress", "pending", "draft"}
    active = []
    equipment_set = set(equipment_codes)
    for work_order in work_orders:
        code = work_order.get("equipment_code") or work_order.get("target_equipment")
        status = str(work_order.get("status") or "").lower()
        if code in equipment_set and status in active_statuses:
            active.append(str(work_order.get("code") or work_order.get("id") or code))
    return [f"active_or_pending_work_order:{code}" for code in active]


def _signals_for_equipment(fault_signals: list[dict[str, Any]], equipment_codes: set[str]) -> list[dict[str, Any]]:
    return [
        signal
        for signal in fault_signals
        if (signal.get("equipment_code") or signal.get("target_equipment") or signal.get("equipment_id"))
        in equipment_codes
    ]


def _equipment_type(item: dict[str, Any]) -> str:
    return str(item.get("type") or item.get("equipment_type") or "").lower()


def _code(item: dict[str, Any]) -> str:
    return str(item.get("code") or item.get("equipment_code") or item.get("id") or "")


def _is_concerning_status(item: dict[str, Any]) -> bool:
    status = str(item.get("status") or "").lower()
    if status in {"warning", "needs_attention", "degraded", "critical"}:
        return True
    try:
        return float(item.get("health_score")) < 70
    except (TypeError, ValueError):
        return False


def _stable_bundle_id(
    *,
    site_id: str,
    objective: str,
    primary_equipment: str,
    affected_equipment: list[str],
    zones: list[str],
    system_context: dict[str, Any],
) -> str:
    identity = {
        "site_id": site_id,
        "objective": objective,
        "primary_equipment": primary_equipment,
        "affected_equipment": sorted(affected_equipment),
        "zones": sorted(zones),
        "system_context": system_context,
    }
    return str(uuid5(NAMESPACE_URL, json.dumps(identity, sort_keys=True, default=str)))


def _stable_action_id(site_id: str, action_scope: str, affected_equipment: list[str]) -> str:
    identity = {
        "site_id": site_id,
        "action_scope": action_scope,
        "affected_equipment": sorted(affected_equipment),
    }
    return str(uuid5(NAMESPACE_URL, json.dumps(identity, sort_keys=True, default=str)))
