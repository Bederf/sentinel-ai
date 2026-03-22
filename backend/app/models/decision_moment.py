"""
DecisionMomentPayload — single-incident decision context (Phase 164).

Every field is traceable to a real data source in this codebase.
No fabricated values. Nullable fields return None honestly.
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime


@dataclass
class DecisionMomentPayload:
    # Identity
    building_id: str
    triggered_at: datetime
    trigger_reason: str  # e.g. "chiller_fault", "thermal_drift_exceeded"

    # Urgency Score  [fault_urgency.compute_fault_urgency()]
    urgency_score: float  # 0.0 – 1.0
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
    time_to_discomfort: int | None  # Minutes. None if thermal_params not configured.
    time_confidence: str  # "calculated" | "estimated" | "unavailable"

    # The Next
    recommended_action: str  # Specific action string (rule-based v1)
    action_validation_state: str  # "validated" | "unverified" | "blocked"
    requires_module: str | None  # None = base tier. Module name = paid gate.
    estimated_impact: str  # e.g. "Prevents R2,400 SLA breach" or "Impact unknown"

    def to_dict(self) -> dict:
        """Serialise to JSON-safe dict."""
        return {
            "building_id": self.building_id,
            "triggered_at": self.triggered_at.isoformat(),
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
        }
