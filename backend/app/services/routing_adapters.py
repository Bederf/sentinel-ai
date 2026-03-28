"""Routing adapters — type-bridging layer between routing subsystems.

Phase 172-10: Convert RoutingDecision (OptimizationTierRouter, sync, no DB)
into TierRoutingResult (expected by ApprovalService.auto_execute_recommendation).

These adapters contain NO new routing logic. Every field is either mapped
directly from the source object or assigned a documented safe default.
"""

from app.services.optimization_tier_router import RoutingDecision
from app.services.tier_routing_engine import TierRoutingResult


def optimization_routing_to_tier_result(
    decision: RoutingDecision,
    recommendation_id: str,
    correlation_id: str,
) -> TierRoutingResult:
    """Adapt a RoutingDecision into a TierRoutingResult.

    RoutingDecision is produced by OptimizationTierRouter (sync, no DB write).
    TierRoutingResult is consumed by ApprovalService.auto_execute_recommendation
    (and any other component in the PARASITE approval path).

    This function bridges the two types without touching either class. Call it
    after OptimizationTierRouter.route_recommendation() and before passing the
    result to ApprovalService.

    Args:
        decision: RoutingDecision returned by OptimizationTierRouter.
        recommendation_id: UUID string of the persisted Recommendation row
            (stamped into rec_item["_recommendation_id"] in G1).
        correlation_id: Correlation UUID shared between the Recommendation row
            and all downstream events (stamped in rec_item["_correlation_id"]
            in G1).

    Returns:
        TierRoutingResult populated from decision + caller-supplied identifiers.
    """
    # ------------------------------------------------------------------
    # Direct field mappings (no defaults required)
    # ------------------------------------------------------------------

    # tier: RoutingDecision.tier is a RoutingTier enum with values like
    # "tier1_advisory", "tier2_approval", "tier3_auto_execute". TierRoutingResult
    # expects "tier1" / "tier2" / "tier3". Strip the suffix after the first
    # underscore segment to normalise.
    raw_tier: str = decision.tier.value  # e.g. "tier1_advisory"
    # Normalise "tier1_advisory" -> "tier1", "tier2_approval" -> "tier2", etc.
    # The value always starts with "tier<N>"; everything after that is discarded.
    tier_parts = raw_tier.split("_", maxsplit=2)
    normalised_tier = tier_parts[0] if len(tier_parts) >= 1 else raw_tier

    action: str = decision.action
    # action values produced by OptimizationTierRouter:
    #   "blocked", "advisory", "log_only", "pending_approval", "auto_execute"
    # TierRoutingResult.action accepts: "advisory", "supervised", "auto_execute"
    # Map for any mismatch so downstream code never sees an unexpected value.
    _action_map = {
        "blocked": "advisory",  # blocked → advisory (safest fallback)
        "log_only": "advisory",  # log_only → advisory (monitor mode)
        "pending_approval": "supervised",  # tier2 flow
        "advisory": "advisory",
        "auto_execute": "auto_execute",
    }
    normalised_action = _action_map.get(action, "advisory")

    confidence_score: float = decision.effective_confidence

    reason: str = decision.reason

    # equipment_type: RoutingDecision.system holds the equipment system string
    # (e.g. "HVAC", "FCU", "DALI"). TierRoutingResult.equipment_type is the same
    # concept, just named differently.
    equipment_type: str = decision.system or "unknown"

    # ------------------------------------------------------------------
    # Defaulted fields — each default is documented with its rationale
    # ------------------------------------------------------------------

    # routing_source: the plan specifies routing_source = "optimization_api" to
    # identify this result as originating from the optimization API path (not the
    # PARASITE recommendation graph). TierRoutingResult does not expose a
    # routing_source field (it is recorded directly on ParasiteDecision rows by
    # TierRoutingEngine). The intent is preserved via threshold_source = "settings"
    # below, and via the recommendation's source="optimization_api" set in G1.
    # When the ParasiteDecision row is written downstream, callers must explicitly
    # set routing_source="optimization_api" on the decision_data dict.

    # threshold_source: "settings" — OptimizationTierRouter reads its thresholds
    # exclusively from the settings object (optimization_tier2_min,
    # optimization_tier3_min). There is no DB lookup, so "settings" is always
    # correct here.
    threshold_source: str = "settings"

    # tier2_threshold / tier3_threshold: RoutingDecision does not carry the raw
    # threshold values it used (only the outcome). We read the canonical defaults
    # from the settings object. These values match what OptimizationTierRouter
    # was initialised with (absent a custom settings override passed at
    # construction time). They are informational / audit-only inside
    # TierRoutingResult; ApprovalService does not re-evaluate them.
    from app.config.settings import settings as _settings

    tier2_threshold: float = getattr(_settings, "optimization_tier2_min", 0.60)
    tier3_threshold: float = getattr(_settings, "optimization_tier3_min", 0.85)

    # risk_level: RoutingDecision has no explicit risk_level field. The
    # OptimizationTierRouter does not incorporate risk level into its routing
    # logic; it uses only confidence + FCU cap + control tier. "medium" is the
    # safe default used by TierRoutingEngine itself when no risk_level is
    # present in a recommendation dict.
    risk_level: str = "medium"

    return TierRoutingResult(
        tier=normalised_tier,
        action=normalised_action,
        confidence_score=confidence_score,
        threshold_source=threshold_source,
        tier2_threshold=tier2_threshold,
        tier3_threshold=tier3_threshold,
        reason=reason,
        equipment_type=equipment_type,
        risk_level=risk_level,
        # decision_id: generated by TierRoutingResult.__post_init__ via
        # field(default_factory=lambda: str(uuid.uuid4()))
        correlation_id=correlation_id,
    )
