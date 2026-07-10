"""Optimization Tier Router — single routing policy for live optimization.

Routes AI recommendations to the correct action tier based on confidence,
equipment type, and site control tier configuration.

Phase 82-01: Foundation routing service.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class RoutingTier(StrEnum):
    """Routing tier for optimization recommendations."""

    BLOCKED = "blocked"
    TIER1_ADVISORY = "tier1_advisory"
    TIER2_APPROVAL = "tier2_approval"
    TIER3_AUTO_EXECUTE = "tier3_auto_execute"


@dataclass
class RoutingDecision:
    """Result of routing a single recommendation."""

    tier: RoutingTier
    action: str  # "blocked", "advisory", "log_only", "pending_approval", "auto_execute"
    reason: str
    effective_confidence: float
    original_confidence: float
    system: str
    point_name: str


@dataclass
class RoutingSummary:
    """Aggregate summary of routing decisions."""

    blocked: int = 0
    advisory: int = 0
    pending_approval: int = 0
    auto_executed: int = 0
    control_tier: str = ""
    thresholds_used: dict[str, float] = field(default_factory=dict)


class OptimizationTierRouter:
    """Routes optimization recommendations to action tiers.

    Thresholds (defaults):
        - blocked:            confidence < 0.30
        - tier1_advisory:     0.30 <= confidence < 0.60
        - tier2_approval:     0.60 <= confidence < 0.85
        - tier3_auto_execute: confidence >= 0.85

    FCU cap: FCU system actions have confidence capped at 0.45,
    forcing them to advisory-only routing at most.

    Control tier execution matrix:
        - monitor:       all actions become "log_only"
        - human_in_loop: tier3/tier2 -> "pending_approval", tier1 -> "advisory"
        - auto_execute:  tier3 -> "auto_execute", tier2 -> "pending_approval", tier1 -> "advisory"
        - blocked:       always "blocked" regardless of control tier

    Phase B — Trust-level thresholds:
        When class_readiness is provided, confidence thresholds are reweighted
        based on the class's effective trust level. The router remains sync and
        stateless; the caller fetches class_readiness and passes it in.
    """

    # Confidence thresholds by effective trust level (Phase B).
    # Format: (block_min, tier2_min, tier3_min)
    _THRESHOLDS_BY_LEVEL: dict[int, tuple[float, float, float]] = {
        1: (0.30, 0.60, 1.00),  # Advisory: tier3 unreachable
        2: (0.30, 0.60, 0.60),  # Supervised proven class: tier3 = tier2
        3: (0.30, 0.60, 0.75),  # Autonomous: tier3 at 0.75
    }

    def __init__(self, settings: Any | None = None):
        """Initialize with optional settings object.

        Args:
            settings: A pydantic Settings instance. If None, uses defaults.
        """
        from app.config.settings import settings as _app_settings

        _s = settings if settings is not None else _app_settings
        self._block_min = getattr(_s, "optimization_tier_block_min", 0.30)
        self._tier2_min = getattr(_s, "optimization_tier2_min", 0.60)
        self._tier3_min = getattr(_s, "optimization_tier3_min", 0.85)
        self._fcu_cap = getattr(_s, "optimization_fcu_confidence_cap", 0.45)
        # TODO: evaluate whether _fcu_cap belongs in model_thresholds table per equipment type

    # ------------------------------------------------------------------
    # Core routing
    # ------------------------------------------------------------------

    def route_recommendation(
        self,
        confidence: float,
        system: str,
        point_name: str,
        site_id: str,
        control_tier: str,
        class_readiness: dict | None = None,
    ) -> RoutingDecision:
        """Route a single recommendation to the appropriate tier and action.

        Args:
            confidence: Raw model confidence (0.0 - 1.0).
            system: Equipment system type (e.g. "HVAC", "FCU", "DALI").
            point_name: BACnet/oBIX point name.
            site_id: Site identifier.
            control_tier: One of "monitor", "supervised", "auto_execute".
            class_readiness: Optional dict with 'current_trust_level' key.
                             When provided, confidence thresholds are adjusted
                             based on the class's trust level (Phase B).
                             When None (backward compatible), behaves as Level 1.

        Returns:
            RoutingDecision with tier, action, and metadata.
        """
        original_confidence = confidence

        # FCU confidence cap — safety limit, applies before trust-level logic
        if self._is_fcu(system):
            confidence = min(confidence, self._fcu_cap)

        # Phase B: When class_readiness is provided, extract trust level and
        # override confidence thresholds. When absent (backward compatible),
        # use the instance defaults (self._*_min) unchanged.
        effective_level = 1
        if class_readiness is not None:
            effective_level = self._effective_class_level(class_readiness)

        if class_readiness is not None:
            # Use trust-level thresholds
            block_min, tier2_min, tier3_min = self._thresholds_for_trust_level(effective_level)
            tier = self._confidence_to_tier(confidence, block_min, tier2_min, tier3_min)
        else:
            # Backward compatible: use instance defaults (self._*_min)
            tier = self._confidence_to_tier(confidence)

        # Determine action from tier + control tier matrix
        action = self._resolve_action(tier, control_tier)

        # Build reason string
        reason = self._build_reason(
            tier, action, original_confidence, confidence, system, control_tier, effective_level=effective_level
        )

        return RoutingDecision(
            tier=tier,
            action=action,
            reason=reason,
            effective_confidence=confidence,
            original_confidence=original_confidence,
            system=system,
            point_name=point_name,
        )

    def route_recommendations(
        self,
        recommendations: list[dict[str, Any]],
        site_id: str,
        control_tier: str,
    ) -> list[RoutingDecision]:
        """Route a batch of recommendations.

        Each recommendation dict must contain at minimum:
            - confidence (float)
            - system (str)
            - point_name (str)

        Optionally each dict may include 'class_readiness' (dict with
        'current_trust_level') to apply per-class trust-level thresholds.

        Returns:
            List of RoutingDecision objects.
        """
        decisions = []
        for rec in recommendations:
            decision = self.route_recommendation(
                confidence=rec.get("confidence", 0.0),
                system=rec.get("system", ""),
                point_name=rec.get("point_name", ""),
                site_id=site_id,
                control_tier=control_tier,
                class_readiness=rec.get("class_readiness"),
            )
            decisions.append(decision)
        return decisions

    def get_routing_summary(
        self,
        decisions: list[RoutingDecision],
        control_tier: str,
    ) -> RoutingSummary:
        """Aggregate routing decisions into a summary.

        Args:
            decisions: List of RoutingDecision objects.
            control_tier: The active control tier.

        Returns:
            RoutingSummary with counts and metadata.
        """
        summary = RoutingSummary(
            control_tier=control_tier,
            thresholds_used={
                "block_min": self._block_min,
                "tier2_min": self._tier2_min,
                "tier3_min": self._tier3_min,
                "fcu_cap": self._fcu_cap,
            },
        )

        for d in decisions:
            if d.tier == RoutingTier.BLOCKED:
                summary.blocked += 1
            elif d.action == "advisory" or d.action == "log_only":
                summary.advisory += 1
            elif d.action == "pending_approval":
                summary.pending_approval += 1
            elif d.action == "auto_execute":
                summary.auto_executed += 1

        return summary

    # ------------------------------------------------------------------
    # Control tier resolution
    # ------------------------------------------------------------------

    @staticmethod
    def resolve_control_tier(
        site_profile: dict[str, Any] | None,
        optimization_settings: Any | None = None,
    ) -> str:
        """Resolve the effective control tier for a site.

        Resolution order:
            1. site_profile["control_tier"] if present and valid
            2. Fallback from optimization_settings.mode:
               - "supervised" -> "supervised"
               - "automatic" -> "auto_execute"
            3. Default: "supervised"

        Args:
            site_profile: Dict with optional "control_tier" key.
            optimization_settings: OptimizationSettings instance with .mode.

        Returns:
            One of "monitor", "supervised", "auto_execute".
        """
        valid_tiers = {"monitor", "supervised", "auto_execute"}

        # 1. Check site profile
        if site_profile:
            tier = site_profile.get("control_tier")
            if tier in valid_tiers:
                return tier

        # 2. Fallback from legacy optimization_settings.mode
        if optimization_settings is not None:
            mode = getattr(optimization_settings, "mode", None)
            if mode == "supervised":
                return "supervised"
            if mode == "automatic":
                return "auto_execute"

        # 3. Default
        return "supervised"

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Phase B: Trust-level threshold resolution
    # ------------------------------------------------------------------

    @staticmethod
    def _thresholds_for_trust_level(level: int) -> tuple[float, float, float]:
        """Return (block_min, tier2_min, tier3_min) for the given trust level.

        Falls back to Level 1 (advisory) for unknown levels.
        """
        return OptimizationTierRouter._THRESHOLDS_BY_LEVEL.get(level, (0.30, 0.60, 1.00))

    @staticmethod
    def _effective_class_level(class_readiness: dict | None) -> int:
        """Extract effective trust level from class_readiness dict.

        Returns 1 (advisory) if class_readiness is None or missing the key.
        """
        if class_readiness is None:
            return 1
        return class_readiness.get("current_trust_level", 1)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_fcu(system: str) -> bool:
        """Check if system is an FCU (case-insensitive)."""
        return system.upper().startswith("FCU")

    def _confidence_to_tier(
        self,
        confidence: float,
        block_min: float | None = None,
        tier2_min: float | None = None,
        tier3_min: float | None = None,
    ) -> RoutingTier:
        """Map effective confidence to a routing tier.

        Args:
            confidence: Effective confidence (after FCU cap).
            block_min/tier2_min/tier3_min: Override thresholds.
                When None, falls back to the instance defaults (self._*_min).

        Returns:
            RoutingTier enum value.
        """
        _block = self._block_min if block_min is None else block_min
        _tier2 = self._tier2_min if tier2_min is None else tier2_min
        _tier3 = self._tier3_min if tier3_min is None else tier3_min

        if confidence < _block:
            return RoutingTier.BLOCKED
        if confidence < _tier2:
            return RoutingTier.TIER1_ADVISORY
        if confidence < _tier3:
            return RoutingTier.TIER2_APPROVAL
        return RoutingTier.TIER3_AUTO_EXECUTE

    @staticmethod
    def _resolve_action(tier: RoutingTier, control_tier: str) -> str:
        """Apply the control tier execution matrix to determine the action.

        Matrix:
            blocked      -> "blocked"       (all control tiers)
            monitor      -> "log_only"      (all tiers)
            human_in_loop:
                tier1 -> "advisory"
                tier2 -> "pending_approval"
                tier3 -> "pending_approval"
            auto_execute:
                tier1 -> "advisory"
                tier2 -> "pending_approval"
                tier3 -> "auto_execute"
        """
        if tier == RoutingTier.BLOCKED:
            return "blocked"

        if control_tier == "monitor":
            return "log_only"

        if control_tier in ("supervised", "human_in_loop"):
            if tier == RoutingTier.TIER1_ADVISORY:
                return "advisory"
            # tier2 and tier3 both go to pending_approval
            return "pending_approval"

        if control_tier == "auto_execute":
            if tier == RoutingTier.TIER1_ADVISORY:
                return "advisory"
            if tier == RoutingTier.TIER2_APPROVAL:
                return "pending_approval"
            # tier3
            return "auto_execute"

        # Unknown control tier — default to advisory for safety
        return "advisory"

    @staticmethod
    def _build_reason(
        tier: RoutingTier,
        action: str,
        original_confidence: float,
        effective_confidence: float,
        system: str,
        control_tier: str,
        effective_level: int | None = None,
    ) -> str:
        """Build a human-readable reason string."""
        parts = [f"Tier={tier.value}, action={action}"]

        if original_confidence != effective_confidence:
            parts.append(
                f"confidence capped: {original_confidence:.2f} -> {effective_confidence:.2f} (FCU cap applied)"
            )
        else:
            parts.append(f"confidence={effective_confidence:.2f}")

        parts.append(f"control_tier={control_tier}")

        if effective_level is not None and effective_level > 1:
            parts.append(f"class_level={effective_level}")

        return "; ".join(parts)


# ------------------------------------------------------------------
# Module-level singleton
# ------------------------------------------------------------------

_router_instance: OptimizationTierRouter | None = None


def get_tier_router(settings: Any | None = None) -> OptimizationTierRouter:
    """Get or create the singleton OptimizationTierRouter.

    Args:
        settings: Optional settings object. Only used on first call
                  (or when explicitly passed to recreate).

    Returns:
        The shared OptimizationTierRouter instance.
    """
    global _router_instance
    if _router_instance is None or settings is not None:
        _router_instance = OptimizationTierRouter(settings)
    return _router_instance
