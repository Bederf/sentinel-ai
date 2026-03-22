"""
DecisionMomentPayload — single-incident decision context (Phase 164).

Every field is traceable to a real data source in this codebase.
No fabricated values. Nullable fields return None honestly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class DecisionMomentPayload:
    # Identity
    building_id: str
    triggered_at: datetime
    trigger_reason: str  # e.g. "chiller_fault", "thermal_drift_exceeded"

    # Urgency Score  [fault_urgency.compute_fault_urgency()]
    urgency_score: float  # 0.0 - 1.0
    urgency_components: dict  # {"comfort": float, "asset_risk": float, "cost": float}

    # The Voice  [fault_urgency.build_alert_text()]
    alert_text: str  # Plain-language incident statement

    # The Where  [ZoneMappingService.get_zones_for_equipment()]
    primary_asset_id: str  # e.g. "S002-CHILLER-B1-001"
    affected_zone_ids: list[str]  # e.g. ["Zone-B1-001", "Zone-L1-A"]
    affected_mesh_ids: list[str]  # Digital twin mesh IDs — [] until mesh registry exists

    # The Why
    reasoning_summary: str  # Template-based posture narrative (v1); LLM prose (v2)
    active_posture: str  # "comfort_priority" | "cost_optimized" | "recommend_only"
    posture_weights: dict  # {"comfort": float, "cost": float, "asset": float}

    # The Time  [thermal_model.calculate_thermal_runway()]
    time_to_discomfort: int | None = None  # Minutes. None if thermal_params not configured.
    time_confidence: str = "unavailable"  # "calculated" | "estimated" | "unavailable"

    # The Next
    recommended_action: str = "monitor"  # Specific action string (rule-based v1)
    action_validation_state: str = "unverified"  # "validated" | "unverified" | "blocked"
    requires_module: str | None = None  # None = base tier. Module name = paid gate.
    estimated_impact: dict = field(default_factory=dict)  # e.g. {"summary": "Prevents R2,400 SLA breach"}

    # --- Phase 165 fields: kiosk renderer contract ---
    # Renderer needs zero additional API calls after receiving this payload.

    # Building geometry and spatial state.
    # has_spatial_data: True when site_3d_configs row exists with floor dimensions.
    # floor_stack: list of {floor_id, floor_width_m, floor_depth_m, equipment_positions[]}
    # deployment_mode: "ghost" | "advisory" | "supervised" | "autonomous"
    building_metadata: dict = field(
        default_factory=lambda: {
            "floors_count": 0,
            "floor_labels": {},
            "floor_stack_order": ["R", "L2", "L1", "L0", "G", "B1"],
            "has_spatial_data": False,
            "floor_stack": [],
            "deployment_mode": "ghost",
        }
    )

    # Floor-level incident overlay for the SVG renderer.
    # Keys are floor IDs (e.g. "B1", "L1"). Empty dict = no active incident on any floor.
    # {floor_id: {"stack_index": int, "svg_y_pct": float, "affected": bool}}
    active_incident_map: dict = field(default_factory=dict)

    # Pre-computed render mode: "quiet" (urgency < 0.7) or "crisis" (urgency >= 0.7).
    # Prevents the kiosk from re-implementing the threshold.
    renderer_hint: str = "quiet"

    def to_dict(self) -> dict:
        """Serialise to JSON-safe dict."""
        return {
            "building_id": self.building_id,
            "triggered_at": self.triggered_at.isoformat()
            if isinstance(self.triggered_at, datetime)
            else self.triggered_at,
            "trigger_reason": self.trigger_reason,
            "urgency_score": self.urgency_score,
            "urgency_components": self.urgency_components,
            "alert_text": self.alert_text,
            "primary_asset_id": self.primary_asset_id,
            "affected_zone_ids": self.affected_zone_ids,
            "affected_mesh_ids": self.affected_mesh_ids,
            "reasoning_summary": self.reasoning_summary,
            "active_posture": self.active_posture,
            "posture_weights": self.posture_weights,
            "time_to_discomfort": self.time_to_discomfort,
            "time_confidence": self.time_confidence,
            "recommended_action": self.recommended_action,
            "action_validation_state": self.action_validation_state,
            "requires_module": self.requires_module,
            "estimated_impact": self.estimated_impact,
            "building_metadata": self.building_metadata,
            "active_incident_map": self.active_incident_map,
            "renderer_hint": self.renderer_hint,
        }
