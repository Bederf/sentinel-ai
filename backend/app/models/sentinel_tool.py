"""SENTINEL Tool Definition Layer — SentinelTool class.

Declarative tool classification for the PARASITE autonomous control pipeline.
Slots in between TierRoutingEngine.route_recommendation() and
ApprovalService.execute_approval() / auto_execute_recommendation().

Provides:
- Structured classification of action types (is_dangerous, is_reversible, priority)
- Dangerous-gate demotion: Tier3 → Tier2 when is_dangerous=True
- Tool metadata for audit trail (parasite_decisions tool_metadata field)
"""

import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Optional

logger = logging.getLogger(__name__)


class ActionClassification(StrEnum):
    """Classification categories for SENTINEL tool actions."""

    SETPOINT = "setpoint"  # Temperature, humidity, pressure setpoints
    LIGHTING = "lighting"  # DALI, 0-10V dimming
    ON_OFF = "on_off"  # Binary switch on/off
    STAGING = "staging"  # Chiller, boiler, AHU staging
    BESS = "bess"  # Battery dispatch (charge/discharge)
    LIFE_SAFETY = "life_safety"  # Fire, access control, emergency
    UNKNOWN = "unknown"


# ----------------------------------------------------------------------------- #
# Classification tables
#
# ⚠️  THREE-WAY SYNC REQUIRED — when adding a new action type, update all three:
#   1. _DANGEROUS_ACTION_TYPES  (this file)
#   2. _REVERSIBLE_ACTION_TYPES (this file)
#   3. safety_profiles matrix   (app/services/chat_tools.py — control_device entry)
#
# The dangerous-gate demotion (Tier3→Tier2) and the LLM safety_profile matrix
# both derive from these sets. Inconsistencies between the three will cause
# the approval pipeline and the LLM prompt to reason about different risk profiles
# for the same action type.
# ----------------------------------------------------------------------------- #

_DANGEROUS_ACTION_TYPES = frozenset(
    {
        # Binary overrides that can cause oscillations or comfort events
        "hvac_override",
        "ahu_on_off",
        "vav_on_off",
        "chiller_on_off",
        "boiler_on_off",
        "pump_on_off",
        "fan_on_off",
        "binary_override",
        # Dispatch actions that write power hardware
        "bess_dispatch",
        "genset_start",
        "genset_stop",
        # Emergency overrides
        "emergency_override",
        "fire_override",
        "access_override",
    }
)

_REVERSIBLE_ACTION_TYPES = frozenset(
    {
        # Setpoints are always reversible — just write back the original
        "hvac_setpoint_change",
        "vav_setpoint_change",
        "chiller_setpoint_change",
        "ahu_setpoint_change",
        "fcustatpoint",
        "temperature_setpoint",
        "humidity_setpoint",
        "pressure_setpoint",
        "set_setpoint",
        "lighting_level",
        "dimming_level",
        "dali_set_level",
        "0-10v_set_level",
        # Staging actions write setpoints that can be reverted
        "chiller_stage_up",
        "chiller_stage_down",
        "ahu_stage_up",
        "ahu_stage_down",
        "vav_stage_up",
        "vav_stage_down",
        # DALI recall/invoke are scene recalls — revert by recalling previous scene
        "dali_recall_scene",
        "dali_invoke_effect",
    }
)

_PRIORITY_BY_CLASSIFICATION = {
    ActionClassification.LIFE_SAFETY: 1,
    ActionClassification.BESS: 2,
    ActionClassification.STAGING: 3,
    ActionClassification.ON_OFF: 4,
    ActionClassification.SETPOINT: 5,
    ActionClassification.LIGHTING: 5,
    ActionClassification.UNKNOWN: 6,
}


# ----------------------------------------------------------------------------- #
# SentinelTool dataclass
# ----------------------------------------------------------------------------- #


@dataclass
class SentinelTool:
    """Declarative tool definition for a PARASITE recommendation.

    Annotates a Recommendation with structured safety, reversibility, and
    priority metadata. Produced by SentinelTool.from_recommendation() after
    tier routing. Consumed by ApprovalService for audit logging and by the
    LLM prompt builder for structured capability descriptions.

    Attributes:
        recommendation_id: Reference to the originating recommendation
        action_type: Raw action type string from recommendation
        classification: ActionClassification category
        is_dangerous: True for oscillation-causing or power-hardware writes
        is_reversible: True if a revert write can compensate this action
        priority: 1 (highest) - 6 (lowest); derived from classification
        demoted: True if dangerous_gate demoted effective_tier from 3→2
        effective_tier: Final tier after all gates applied (tier2 or tier3)
        sentinel_tool: Always present when this class is used (not Noneable here,
                      but the ApprovalService parameter is Optional for caller ergonomics)
    """

    recommendation_id: str
    action_type: str
    classification: ActionClassification
    is_dangerous: bool
    is_reversible: bool
    priority: int
    demoted: bool = False
    effective_tier: str = "tier3"
    sentinel_tool: Optional["SentinelTool"] = field(default=None, repr=False)

    # --------------------------------------------------------------------- #
    # Factory — classify a recommendation
    # --------------------------------------------------------------------- #

    @classmethod
    def from_recommendation(cls, recommendation, routing_result) -> "SentinelTool":
        """Classify a Recommendation into a SentinelTool.

        Applies the 6 classification rules:
          1. Life-safety  → FIRE, ACCESS, CCTV, FIRE_ALARM, EVACUATION (any action)
          2. BESS dispatch → BESS_DISPATCH, GENSET_START, GENSET_STOP
          3. Staging      → CHILLER/AHU/VAV/FCU/SPLIT/CT/CRAC/PUMP/FAN + stage/stop/start/on_off
          4. Lighting     → DALI, DIMMING, 0-10V
          5. Setpoint     → SETPOINT, SET, temperature/humidity/pressure
          6. Fallback     → ON_OFF for override types, UNKNOWN for the rest

        The dangerous-gate demotion (Tier3 → Tier2) is NOT applied here.
        Call apply_dangerous_gate() separately after from_recommendation()
        to get the post-demotion effective_tier.

        Args:
            recommendation: Recommendation dataclass instance
            routing_result: TierRoutingResult from TierRoutingEngine

        Returns:
            SentinelTool with full classification (pre-demotion)
        """
        at = recommendation.action_type or ""
        eq = recommendation.target_equipment or ""
        eq_type = eq.split("-")[1].upper() if "-" in eq else ""

        classification = cls._classify_action(at, eq_type)
        is_dangerous = at in _DANGEROUS_ACTION_TYPES
        is_reversible = at in _REVERSIBLE_ACTION_TYPES or classification == ActionClassification.SETPOINT
        priority = _PRIORITY_BY_CLASSIFICATION[classification]

        tool = cls(
            recommendation_id=recommendation.id,
            action_type=at,
            classification=classification,
            is_dangerous=is_dangerous,
            is_reversible=is_reversible,
            priority=priority,
            demoted=False,
            effective_tier=routing_result.tier,
            sentinel_tool=None,
        )
        return tool

    @classmethod
    def _classify_action(cls, action_type: str, eq_type: str) -> ActionClassification:
        """Classify action type + equipment into ActionClassification."""
        at = action_type.lower()
        et = eq_type.upper()

        # Rule 1: Life-safety equipment
        if et in ("FIRE", "ACCESS", "CCTV", "FIRE_ALARM", "EVACUATION"):
            return ActionClassification.LIFE_SAFETY

        # Rule 2: BESS / generator dispatch
        if "bess" in at or "genset" in at:
            return ActionClassification.BESS

        # Rule 3: HVAC staging (equipment types that stage, including PUMP/FAN)
        if et in ("CHILLER", "AHU", "VAV", "FCU", "SPLIT", "CT", "CRAC", "PUMP", "FAN"):
            if any(k in at for k in ("stage", "start", "stop", "on_off", "override")):
                return ActionClassification.STAGING
            return ActionClassification.SETPOINT

        # Rule 4: Lighting control
        if any(k in at for k in ("dali", "dimming", "0-10v", "light")):
            return ActionClassification.LIGHTING

        # Rule 5: Setpoint (explicit setpoint types or value-based)
        if any(k in at for k in ("setpoint", "set_", "temperature", "humidity", "pressure")):
            return ActionClassification.SETPOINT

        # Rule 6: Binary on/off overrides → ON_OFF; everything else → UNKNOWN
        if any(k in at for k in ("on_off", "override", "switch")):
            return ActionClassification.ON_OFF
        return ActionClassification.UNKNOWN

    # --------------------------------------------------------------------- #
    # Dangerous gate — demote Tier3 → Tier2 when is_dangerous=True
    # --------------------------------------------------------------------- #

    def apply_dangerous_gate(self, recommendation) -> "SentinelTool":
        """Apply dangerous-gate demotion: Tier3 → Tier2 when is_dangerous=True.

        Non-Tier3 recommendations pass through unchanged.
        Tier3 + is_dangerous=True: demotes effective_tier to tier2, sets demoted=True.
        Tier3 + is_dangerous=False: no-op.

        Demotion is logged at WARNING level with recommendation_id,
        action_type, and risk_level.

        Args:
            recommendation: Recommendation dataclass instance (for logging context)

        Returns:
            Self (demoted if applicable), otherwise unchanged
        """
        # Conservative catch-all: UNKNOWN-classified actions never auto-execute.
        # An unknown action_type means the classification rules don't cover it —
        # demote to tier2 regardless of confidence so a human reviews it.
        no_demotion_needed = self.effective_tier != "tier3" or (
            not self.is_dangerous and self.classification != ActionClassification.UNKNOWN
        )
        if no_demotion_needed:
            return self

        risk = (
            recommendation.risk_level.value
            if hasattr(recommendation.risk_level, "value")
            else str(recommendation.risk_level)
        )

        logger.warning(
            f"DANGEROUS_GATE: demoting recommendation_id={self.recommendation_id} "
            f"action_type={self.action_type!r} risk_level={risk!r} — tier3 → tier2 "
            f"(is_dangerous=True)"
        )

        self.effective_tier = "tier2"
        self.demoted = True
        return self
