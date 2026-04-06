"""
DecisionMomentAggregator — assembles DecisionMomentPayload from existing services (Phase 164).

Dependency map:
  affected_zone_ids  → ZoneMappingService.get_zones_for_equipment()
  urgency_score      → fault_urgency.compute_fault_urgency()
  alert_text         → fault_urgency.build_alert_text()
  time_to_discomfort → thermal_model.calculate_thermal_runway()
  active_posture     → building config + control_policy_engine
  recommended_action → rule-based lookup by fault_type + equipment type (v1)
  action_validation_state → tier_routing result + safety + writable check
"""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.models.decision_moment import DecisionMomentPayload
from app.services.fault_urgency import build_alert_text, compute_fault_urgency
from app.services.floor_zone_utils import build_active_incident_map
from app.services.thermal_model import calculate_thermal_runway
from app.services.zone_mapping_service import ZoneMappingService

logger = logging.getLogger(__name__)

# Default posture weights used when building profile is missing or incomplete
_DEFAULT_WEIGHTS = {"comfort": 0.70, "cost": 0.15, "asset": 0.15}

# Rule-based action lookup: (equipment_type, fault_type) → recommended action string
# v1: deterministic. v2: LLM-generated narrative.
_ACTION_RULES: dict[tuple[str, str], str] = {
    ("CHILLER", "chiller_fault"): "Inspect compressor — check refrigerant pressure, oil level, and condenser fans.",
    ("CHILLER", "thermal_drift_exceeded"): "Reduce chiller setpoint by 1°C and monitor delta-T. Alert HVAC technician.",
    (
        "AHU",
        "filter_pressure_high",
    ): "Schedule filter replacement on {asset_id}. Increase fresh-air bypass if available.",
    ("AHU", "thermal_drift_exceeded"): "Check AHU supply air temperature and inspect mixing damper position.",
    ("AHU", "comm_loss"): "Check BACnet connection to {asset_id}. Restart controller if unresponsive.",
    ("FCU", "comm_loss"): "Check FCU controller wiring for {asset_id}. Inspect terminal strip.",
    ("GEN", "generator_fault"): "Inspect generator {asset_id} — check fuel level, battery voltage, and coolant.",
    ("UPS", "ups_fault"): "Check UPS {asset_id} battery status. Notify critical load operators.",
    ("PUMP", "pump_fault"): "Inspect pump {asset_id} for bearing noise and seal leakage.",
    ("DALI", "comm_loss"): "Check DALI bus connection on {asset_id} controller.",
}
_DEFAULT_ACTION = "Inspect {asset_id} and escalate to site technician."


def _load_building_profile(building_id: str) -> dict[str, Any]:
    """Load building.json for the given building_id. Returns empty dict on failure."""
    try:
        # Try buildings directory first, then sites directory
        path = Path(f"app/data/buildings/{building_id}/building.json")
        if not path.exists():
            path = Path(f"app/data/sites/{building_id}/building.json")
        if path.exists():
            return json.loads(path.read_text())
    except Exception as e:
        logger.warning("Could not load building profile for %s: %s", building_id, e)
    return {}


def _compute_renderer_hint(urgency_score: float, profile: dict | None) -> str:
    """
    Compute renderer hint from urgency score and building profile threshold.

    Reads crisis_logic.urgency_threshold from the building profile.
    Falls back to 0.70 if missing — but NEVER hardcodes the threshold
    into the comparator. This allows per-building threshold tuning via
    a Supabase UPDATE, not a code deployment.
    """
    threshold = 0.70  # default (matches buildings.profile DEFAULT in migration 20260322_001)
    if profile:
        crisis_logic = profile.get("crisis_logic", {})
        threshold = float(crisis_logic.get("urgency_threshold", 0.70))
    return "crisis" if urgency_score >= threshold else "quiet"


def _get_posture_weights(profile: dict) -> dict[str, float]:
    """Extract posture weights from building profile. Falls back to defaults."""
    try:
        weights = profile.get("optimization", {}).get("weights", {})
        if weights and abs(sum(weights.values()) - 1.0) < 0.01:
            return weights
    except Exception:
        pass
    logger.info("Using default posture weights (building profile not configured)")
    return dict(_DEFAULT_WEIGHTS)


def _get_active_posture(profile: dict) -> str:
    """Extract posture label from building profile. Falls back to 'comfort_priority'."""
    return profile.get("optimization", {}).get("posture_label", "comfort_priority")


def _get_thermal_params(profile: dict) -> dict | None:
    """Extract thermal params. Returns None if not configured (never guess)."""
    return profile.get("optimization", {}).get("thermal_params")


def _resolve_action(fault_type: str, asset_id: str, affected_zone_ids: list[str]) -> str:
    """Rule-based action lookup. Falls back to default."""
    parts = asset_id.split("-")
    eq_type = parts[1].upper() if len(parts) >= 2 else "DEFAULT"
    template = _ACTION_RULES.get((eq_type, fault_type), _DEFAULT_ACTION)
    zones_str = ", ".join(affected_zone_ids[:3]) if affected_zone_ids else "affected areas"
    return template.format(asset_id=asset_id, zones=zones_str)


def _build_reasoning_summary(
    active_posture: str,
    posture_weights: dict,
    urgency_score: float,
    urgency_components: dict,
    profile_configured: bool,
) -> str:
    """Template-based reasoning summary (v1). LLM narrative is v2."""
    dominant = max(urgency_components, key=urgency_components.get) if urgency_components else "comfort"
    weight = posture_weights.get("comfort", 0.70)
    banner = "" if profile_configured else " [Using default weights — building profile not configured.]"
    return (
        f"{active_posture.replace('_', ' ').title()} posture "
        f"({weight:.0%} comfort weight). "
        f"Urgency: {urgency_score:.2f} — {dominant} component dominant.{banner}"
    )


class DecisionMomentAggregator:
    """
    Assembles DecisionMomentPayload from existing SENTINEL services.
    No LLM calls in v1. Deterministic and fast.
    """

    def __init__(self, zone_mapping_service: ZoneMappingService | None = None):
        self._zone_svc = zone_mapping_service or ZoneMappingService()

    async def _build_building_metadata(self, building_id: str) -> dict:
        """
        Build building_metadata dict for the kiosk renderer.

        Queries site_3d_configs for spatial floor data.
        Falls back to sane defaults if no spatial data exists.
        deployment_mode comes from buildings.profile (loaded separately).

        Returns:
            {
              "floors_count": int,
              "floor_labels": {"B1": "Basement 1", ...},
              "floor_stack_order": ["R", "L2", "L1", "L0", "G", "B1"],
              "has_spatial_data": bool,
              "floor_stack": [
                {
                  "floor_id": "B1",
                  "floor_width_m": 150.0,
                  "floor_depth_m": 120.0,
                  "equipment_positions": [{"x": 50, "y": 30, "type": "chiller"}, ...]
                }
              ],
              "deployment_mode": "ghost"
            }
        """
        from app.database.repositories.site_3d_config_repository import get_site_3d_config_repository
        from app.services.floor_zone_utils import FLOOR_LABELS, FLOOR_STACK_ORDER

        # Defaults
        metadata: dict = {
            "floors_count": 0,
            "floor_labels": dict(FLOOR_LABELS),
            "floor_stack_order": list(FLOOR_STACK_ORDER),
            "has_spatial_data": False,
            "floor_stack": [],
            "deployment_mode": "ghost",
        }

        # Load deployment_mode from profile
        try:
            profile = _load_building_profile(building_id)
            metadata["deployment_mode"] = profile.get("deployment_mode", "ghost") if profile else "ghost"
        except Exception as e:
            logger.warning("Could not load building profile for %s: %s", building_id, e)

        # Load spatial data from site_3d_configs
        try:
            repo = get_site_3d_config_repository()
            config = repo.get_by_site_id(building_id)
            if config:
                floors_raw = config.get("floors", [])
                equipment_positions = config.get("equipment_positions", [])

                # Build floor stack from stored floor dimensions
                floor_stack = []
                for floor_def in floors_raw:
                    floor_id = floor_def.get("level") or floor_def.get("floor_id", "")
                    # Get equipment for this floor from positions
                    floor_equipment = [
                        ep for ep in equipment_positions if ep.get("floor") == floor_id or ep.get("level") == floor_id
                    ]
                    floor_stack.append(
                        {
                            "floor_id": floor_id,
                            "floor_width_m": float(floor_def.get("width", 0)),
                            "floor_depth_m": float(floor_def.get("depth", 0)),
                            "equipment_positions": [
                                {
                                    "x": ep.get("x", 0),
                                    "y": ep.get("y", 0),
                                    "type": ep.get("equipment_type", "unknown"),
                                }
                                for ep in floor_equipment
                            ],
                        }
                    )

                if floor_stack:
                    metadata["has_spatial_data"] = True
                    metadata["floor_stack"] = floor_stack
                    metadata["floors_count"] = len(floor_stack)

        except Exception as e:
            logger.warning("Could not load site_3d_config for %s: %s", building_id, e)
            # has_spatial_data remains False — safe degraded state

        return metadata

    def assemble(
        self,
        building_id: str,
        fault_type: str,
        severity: str,
        asset_id: str,
        trigger_reason: str | None = None,
        current_hour: int | None = None,
        tier: int = 1,
        safety_approved: bool = False,
        point_writable: bool = False,
        requires_module: str | None = None,
    ) -> DecisionMomentPayload:
        """
        Assemble a DecisionMomentPayload.
        Never raises — always returns a payload with honest null fields where data is missing.
        """
        t0 = time.perf_counter()
        triggered_at = datetime.now(UTC)

        # Load building profile (graceful degradation if missing)
        profile = _load_building_profile(building_id)
        profile_configured = bool(profile.get("optimization", {}).get("weights"))

        posture_weights = _get_posture_weights(profile)
        active_posture = _get_active_posture(profile)
        thermal_params = _get_thermal_params(profile)

        # Urgency
        urgency_score, urgency_components = compute_fault_urgency(
            fault_type=fault_type,
            severity=severity,
            equipment_id=asset_id,
            posture_weights=posture_weights,
            current_hour=current_hour,
        )

        # Zone lookup (graceful degradation if lookup fails)
        try:
            affected_zone_ids = self._zone_svc.get_zones_for_equipment(asset_id)
        except Exception as e:
            logger.warning("Zone lookup failed for %s: %s", asset_id, e)
            affected_zone_ids = []

        # Alert text
        alert_text = build_alert_text(fault_type, asset_id, affected_zone_ids)

        # Thermal prediction — only if params available
        time_to_discomfort: int | None = None
        time_confidence = "unavailable"
        if thermal_params:
            try:
                minutes = calculate_thermal_runway(
                    current_temp=23.5,  # TODO: wire to live telemetry in v2
                    comfort_limit=26.0,
                    building_params=thermal_params,
                    weather_forecast={},
                )
                time_to_discomfort = int(minutes) if minutes is not None else None
                time_confidence = "estimated"
            except Exception as e:
                logger.warning("Thermal runway calculation failed: %s", e)

        # Action + validation state
        recommended_action = _resolve_action(fault_type, asset_id, affected_zone_ids)
        if tier >= 2 and safety_approved and point_writable:
            action_validation_state = "validated"
        else:
            action_validation_state = "unverified"

        # Reasoning summary (v1 template)
        reasoning_summary = _build_reasoning_summary(
            active_posture, posture_weights, urgency_score, urgency_components, profile_configured
        )

        # Phase 165 fields — build inline (sync path; _build_building_metadata is async for v2)
        from app.database.repositories.site_3d_config_repository import get_site_3d_config_repository
        from app.services.floor_zone_utils import FLOOR_LABELS, FLOOR_STACK_ORDER

        building_metadata: dict = {
            "floors_count": 0,
            "floor_labels": dict(FLOOR_LABELS),
            "floor_stack_order": list(FLOOR_STACK_ORDER),
            "has_spatial_data": False,
            "floor_stack": [],
            "deployment_mode": profile.get("deployment_mode", "ghost") if profile else "ghost",
            "dismiss_window_minutes": (
                profile.get("crisis_logic", {}).get("dismiss_window_minutes", 30) if profile else 30
            ),
            "equipment_count": 0,
            "active_risk_count": 0,
            "health_pct": 100,
        }
        try:
            repo = get_site_3d_config_repository()
            config = repo.get_by_site_id(building_id)
            if config:
                floors_raw = config.get("floors", [])
                equipment_positions = config.get("equipment_positions", [])
                floor_stack = []
                for floor_def in floors_raw:
                    floor_id = floor_def.get("level") or floor_def.get("floor_id", "")
                    floor_equipment = [
                        ep for ep in equipment_positions if ep.get("floor") == floor_id or ep.get("level") == floor_id
                    ]
                    floor_stack.append(
                        {
                            "floor_id": floor_id,
                            "floor_width_m": float(floor_def.get("width", 0)),
                            "floor_depth_m": float(floor_def.get("depth", 0)),
                            "equipment_positions": [
                                {"x": ep.get("x", 0), "y": ep.get("y", 0), "type": ep.get("equipment_type", "unknown")}
                                for ep in floor_equipment
                            ],
                        }
                    )
                if floor_stack:
                    building_metadata["has_spatial_data"] = True
                    building_metadata["floor_stack"] = floor_stack
                    building_metadata["floors_count"] = len(floor_stack)
        except Exception as e:
            logger.warning("Could not load site_3d_config for %s: %s", building_id, e)

        result = DecisionMomentPayload(
            building_id=building_id,
            triggered_at=triggered_at,
            trigger_reason=trigger_reason or fault_type,
            urgency_score=urgency_score,
            urgency_components=urgency_components,
            alert_text=alert_text,
            primary_asset_id=asset_id,
            affected_zone_ids=affected_zone_ids,
            affected_mesh_ids=[],  # mesh registry not yet implemented
            reasoning_summary=reasoning_summary,
            active_posture=active_posture,
            posture_weights=posture_weights,
            time_to_discomfort=time_to_discomfort,
            time_confidence=time_confidence,
            recommended_action=recommended_action,
            action_validation_state=action_validation_state,
            requires_module=requires_module,
            estimated_impact=(
                "Impact unknown — building profile not fully configured."
                if not profile_configured
                else "Estimated impact pending cost model."
            ),
            building_metadata=building_metadata,
            active_incident_map=build_active_incident_map(
                affected_zone_ids,
                asset_id,
            ),
            renderer_hint=_compute_renderer_hint(urgency_score, profile),
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "assemble() completed in %.1fms for %s (urgency=%.3f)",
            elapsed_ms,
            building_id,
            urgency_score,
        )
        return result
