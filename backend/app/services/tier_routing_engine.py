"""Confidence-based tier routing engine for PARASITE autonomous control.

Routes every AI recommendation to the correct autonomy tier (Tier 1/2/3) based on:
- ML confidence score (0.0-1.0)
- Equipment risk level
- Configured thresholds (settings + database)
- System safety gates and rate limiting

Purpose: The system earns its autonomy. Low confidence stays advisory (Tier 1),
medium goes through human approval (Tier 2), high confidence earns autonomous
execution (Tier 3).

Every decision is logged to parasite_decisions table with full context.
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Optional

from app.config.settings import settings
from app.database.repositories.parasite_decision_repository import (
    get_parasite_decision_repository,
)
from app.ml.models.model_registry_db import get_model_registry
from app.services.circuit_breaker import call_with_breaker, get_breaker
from app.services.decision_event_logger import emit_decision_event

logger = logging.getLogger(__name__)


class TierLevel(StrEnum):
    """Autonomy tier levels."""

    TIER1 = "tier1"  # Advisory only
    TIER2 = "tier2"  # Human approval required
    TIER3 = "tier3"  # Auto-execute


@dataclass
class TierRoutingResult:
    """Result of tier routing decision for a recommendation."""

    tier: str  # "tier1", "tier2", "tier3"
    action: str  # "advisory", "require_approval", "auto_execute"
    confidence_score: float
    threshold_source: str  # "settings" or "model_thresholds_db"
    tier2_threshold: float
    tier3_threshold: float
    reason: str
    equipment_type: str
    risk_level: str
    decision_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    correlation_id: str = ""  # Populated from recommendation.correlation_id


class TierRoutingEngine:
    """Routes AI recommendations to appropriate autonomy tier based on confidence.

    Singleton service that gates every AI decision through confidence-based
    tier routing. Reads thresholds from both settings.py config AND the
    model_thresholds database table, choosing the stricter (higher) of the two.

    Attributes:
        settings: Application configuration with PARASITE flags
        model_registry: Database-driven ML model registry for thresholds
        parasite_repo: Repository for logging decisions to audit trail
        _instance: Singleton instance
        _auto_executions_this_hour: In-memory counter for rate limiting
        _hour_start: Timestamp of current hour for rate limit reset
    """

    _instance: Optional["TierRoutingEngine"] = None

    def __init__(self):
        """Initialize tier routing engine with settings and repositories."""
        self.settings = settings
        self.model_registry = None  # Lazy-load via async getter
        self.parasite_repo = get_parasite_decision_repository()
        self._auto_executions_this_hour = 0
        self._hour_start = datetime.utcnow()

        # Circuit breakers for downstream dependencies
        self._cb_decision_db = get_breaker("parasite_decisions_db", failure_threshold=5, recovery_timeout_seconds=30.0)
        self._cb_threshold_db = get_breaker("model_thresholds_db", failure_threshold=3, recovery_timeout_seconds=20.0)

    async def route_recommendation(self, recommendation: dict) -> TierRoutingResult:
        """Route a recommendation to the appropriate autonomy tier.

        Implements the complete routing logic:
        1. Master switch check (parasite_enabled)
        2. Extract and normalize confidence score
        3. Get thresholds from settings and DB, use stricter
        4. Risk level override (critical/high never auto-execute)
        5. Tier 3 gate (disabled if not enabled)
        6. Rate limit check (hourly auto-executions)
        7. Route to tier and log decision

        Args:
            recommendation: Dict with keys:
                - site_id: Building identifier
                - target_equipment: Equipment code
                - confidence or confidence_score: Confidence value
                - risk_level: "low", "medium", "high", "critical"
                - action_type: Type of action being recommended
                - action: Dict with 'point' and 'value' keys
                - reason: Explanation from AI

        Returns:
            TierRoutingResult with tier, action, thresholds, and reasoning
        """
        # 1. Extract basics (equipment type, risk level, confidence, correlation_id)
        equipment_type = self._extract_equipment_type(recommendation)
        risk_level = recommendation.get("risk_level", "medium")
        confidence_score = self._extract_confidence(recommendation)
        correlation_id = recommendation.get("correlation_id", "")

        # 2. Master switch check
        if not self.settings.parasite_enabled:
            logger.debug("PARASITE disabled globally, routing to Tier 1 advisory")
            return TierRoutingResult(
                tier=TierLevel.TIER1.value,
                action="advisory",
                confidence_score=confidence_score,
                threshold_source="settings",
                tier2_threshold=self.settings.parasite_confidence_tier2_min,
                tier3_threshold=self.settings.parasite_confidence_tier3_min,
                reason="PARASITE master switch is disabled",
                equipment_type=equipment_type,
                risk_level=risk_level,
                correlation_id=correlation_id,
            )

        # 3. Get thresholds from TWO sources, use stricter (lazy-load model_registry)
        #    Only reached if PARASITE is enabled
        if self.model_registry is None:
            self.model_registry = await get_model_registry()
        tier2_threshold, tier3_threshold, threshold_source = await self.get_effective_thresholds(equipment_type)

        # 4. Risk level override: critical/high never auto-execute
        if risk_level in ("critical", "high"):
            logger.info(f"Risk level {risk_level} overrides to Tier 2 minimum (never auto-execute critical actions)")
            tier3_threshold = 999.0  # Impossible to reach Tier 3

        # 5. Tier 3 gate: disabled if not enabled in settings
        if not self.settings.parasite_tier3_enabled:
            logger.debug("Tier 3 disabled via settings, capping at Tier 2")
            tier3_threshold = 999.0  # Impossible to reach Tier 3

        # 6. Rate limit check: if auto-executions this hour >= limit, cap at Tier 2
        if self._should_reset_hourly_counter():
            self._auto_executions_this_hour = 0
            self._hour_start = datetime.utcnow()

        executions_remaining = max(
            0,
            self.settings.parasite_max_auto_executions_per_hour - self._auto_executions_this_hour,
        )
        if executions_remaining <= 0:
            logger.warning(
                f"Rate limit reached ({self.settings.parasite_max_auto_executions_per_hour}/hour), capping at Tier 2"
            )
            tier3_threshold = 999.0  # Impossible to reach Tier 3

        # 7. Route to appropriate tier
        if confidence_score < tier2_threshold:
            tier = TierLevel.TIER1.value
            tier_num = 1
            action = "advisory"
            reason = (
                f"Confidence {confidence_score:.2f} below Tier 2 threshold "
                f"{tier2_threshold:.2f} - recommendation advisory only"
            )
        elif confidence_score < tier3_threshold:
            tier = TierLevel.TIER2.value
            tier_num = 2
            action = "supervised"
            reason = (
                f"Confidence {confidence_score:.2f} meets Tier 2 ({tier2_threshold:.2f}) "
                f"but below Tier 3 ({tier3_threshold:.2f}) - requires operator approval"
            )
        else:
            tier = TierLevel.TIER3.value
            tier_num = 3
            action = "auto_execute"
            reason = f"Confidence {confidence_score:.2f} meets Tier 3 threshold {tier3_threshold:.2f} - auto-executing"
            self._auto_executions_this_hour += 1

        logger.info(
            f"Routed {equipment_type} to {tier} (confidence={confidence_score:.2f}, risk={risk_level}): {reason}"
        )

        # Prometheus metrics instrumentation (best-effort)
        try:
            from app.api.metrics import sentinel_recommendations_total

            rec_site_id = recommendation.get("site_id", "unknown")
            sentinel_recommendations_total.labels(site_id=rec_site_id, tier=tier, action=action).inc()
        except Exception:
            pass  # Metrics are best-effort, never block business logic

        # 8. Log decision to parasite_decisions
        equipment_code = recommendation.get("target_equipment", "unknown")
        site_id = recommendation.get("site_id", "unknown")

        # Emit structured lifecycle event
        emit_decision_event(
            "tier_routing.decided",
            correlation_id=correlation_id,
            equipment_code=equipment_code,
            site_id=site_id,
            tier=tier,
            status=action,
            details={
                "confidence_score": confidence_score,
                "tier2_threshold": tier2_threshold,
                "tier3_threshold": tier3_threshold,
                "threshold_source": threshold_source,
                "risk_level": risk_level,
                "reason": reason,
            },
        )
        _point = recommendation.get("action", {}).get("point", "unknown")
        decision_data = {
            "site_id": site_id,
            "equipment_code": equipment_code,
            "recommendation_id": recommendation.get("id"),
            "correlation_id": correlation_id,
            "decision_type": f"tier{tier_num}_{action}",
            "tier": f"tier{tier_num}",
            "confidence_score": confidence_score,
            "mode": settings.resolved_ingestion_mode.value,
            "actor": "auto_tier3" if tier_num == 3 else ("human_tier2" if tier_num == 2 else "system"),
            "point_name": _point,
            "control_point": _point,
            "routing_source": "recommendation_graph",
            "target_value": recommendation.get("action", {}).get("value"),
            "contributing_factors": {
                "confidence": confidence_score,
                "risk_level": risk_level,
                "threshold_source": threshold_source,
                "tier2_threshold": tier2_threshold,
                "tier3_threshold": tier3_threshold,
                # Merge domain-specific factors (e.g. AEGIS BESS audit fields)
                **(recommendation.get("contributing_factors") or {}),
            },
            "decision_details": {
                "target_equipment": equipment_code,
                "action_type": recommendation.get("action_type", "unknown"),
                "control_point": _point,
                "target_value": str(recommendation.get("action", {}).get("value", "")),
                "reasoning": reason,
            },
        }

        # Record decision with circuit breaker — never block tier routing if DB is down
        await call_with_breaker(
            self._cb_decision_db,
            self.parasite_repo.record_decision,
            decision_data,
            fallback=None,
            timeout_seconds=5.0,
        )

        return TierRoutingResult(
            tier=tier,
            action=action,
            confidence_score=confidence_score,
            threshold_source=threshold_source,
            tier2_threshold=tier2_threshold,
            tier3_threshold=tier3_threshold,
            reason=reason,
            equipment_type=equipment_type,
            risk_level=risk_level,
            correlation_id=correlation_id,
        )

    async def get_effective_thresholds(self, equipment_type: str) -> tuple[float, float, str]:
        """Get effective thresholds, using stricter-of-two logic.

        Reads thresholds from TWO sources:
        - Settings: parasite_confidence_tier2_min (0.70), parasite_confidence_tier3_min (0.85)
        - Database: model_thresholds table for equipment type (if available)

        Returns the STRICTER (higher) threshold from either source, ensuring
        equipment-specific models can enforce tighter gates than global defaults.

        Args:
            equipment_type: Equipment type (e.g., "CHILLER", "AHU")

        Returns:
            Tuple of (tier2_threshold, tier3_threshold, source)
            where source is "settings", "model_thresholds_db", or "combined"
        """
        # Get settings thresholds (always available)
        settings_tier2 = self.settings.parasite_confidence_tier2_min
        settings_tier3 = self.settings.parasite_confidence_tier3_min

        try:
            # Query database for equipment-specific thresholds (with circuit breaker)
            db_thresholds = await call_with_breaker(
                self._cb_threshold_db,
                self.model_registry.get_thresholds,
                equipment_type,
                fallback=None,
                timeout_seconds=2.0,
            )
            if db_thresholds and db_thresholds.is_enabled():
                db_tier2 = db_thresholds.tier2_confidence_min
                db_tier3 = db_thresholds.tier3_confidence_min

                # Use STRICTER (higher) threshold from either source
                effective_tier2 = max(settings_tier2, db_tier2)
                effective_tier3 = max(settings_tier3, db_tier3)

                # Determine source based on which was stricter
                if effective_tier2 == db_tier2 or effective_tier3 == db_tier3:
                    source = "combined"
                    logger.debug(
                        f"Using combined thresholds for {equipment_type}: "
                        f"tier2={effective_tier2}, tier3={effective_tier3}"
                    )
                else:
                    source = "settings"

                return effective_tier2, effective_tier3, source
        except Exception as e:
            logger.warning(f"Error querying DB thresholds for {equipment_type}: {e}")

        # Fallback to settings only
        return settings_tier2, settings_tier3, "settings"

    async def get_routing_stats(self) -> dict:
        """Get current routing statistics for monitoring dashboard.

        Returns:
            Dict with counts by tier and rate limit status
        """
        recent_decisions = await self.parasite_repo.get_recent_decisions(limit=100)

        tier1_count = sum(1 for d in recent_decisions if d.get("tier") == "tier1")
        tier2_count = sum(1 for d in recent_decisions if d.get("tier") == "tier2")
        tier3_count = sum(1 for d in recent_decisions if d.get("tier") == "tier3")

        executions_remaining = max(
            0,
            self.settings.parasite_max_auto_executions_per_hour - self._auto_executions_this_hour,
        )

        return {
            "tier1_advisory": tier1_count,
            "tier2_supervised": tier2_count,
            "tier3_auto_execute": tier3_count,
            "auto_executions_this_hour": self._auto_executions_this_hour,
            "auto_executions_remaining": executions_remaining,
            "rate_limit_max_per_hour": self.settings.parasite_max_auto_executions_per_hour,
            "parasite_enabled": self.settings.parasite_enabled,
            "tier3_enabled": self.settings.parasite_tier3_enabled,
        }

    def _extract_confidence(self, recommendation: dict) -> float:
        """Extract numeric confidence from recommendation dict.

        Handles both numeric (0.0-1.0) and string ("high"/"medium"/"low")
        confidence values. String values are mapped to numeric equivalents.

        Args:
            recommendation: Recommendation dict

        Returns:
            Numeric confidence score (0.0-1.0)
        """
        # First try numeric confidence_score
        confidence = recommendation.get("confidence_score")
        if isinstance(confidence, (int, float)) and 0.0 <= confidence <= 1.0:
            return float(confidence)

        # Try multi_objective_score (used by AI optimizer)
        confidence = recommendation.get("multi_objective_score")
        if isinstance(confidence, (int, float)) and 0.0 <= confidence <= 1.0:
            return float(confidence)

        # Fall back to string confidence mapping
        string_confidence = recommendation.get("confidence", "medium")
        mapping = {"high": 0.90, "medium": 0.75, "low": 0.50}
        return mapping.get(string_confidence, 0.50)

    def _extract_equipment_type(self, recommendation: dict) -> str:
        """Extract equipment type from target_equipment code.

        Equipment codes follow patterns:
        - Zone equipment: S002-VAV-101 (extract "VAV")
        - Plant equipment: S002-CHILLER-B1-001 (extract "CHILLER")

        Args:
            recommendation: Recommendation dict

        Returns:
            Equipment type (e.g., "CHILLER", "AHU", "VAV")
        """
        target_equipment = recommendation.get("target_equipment", "")
        if not target_equipment:
            return "unknown"

        # Equipment codes are typically {site}-{type}-{location}
        # Extract the part between first and second hyphen
        parts = target_equipment.split("-")
        if len(parts) >= 2:
            return parts[1].upper()

        return "unknown"

    def _should_reset_hourly_counter(self) -> bool:
        """Check if hourly rate limit window has passed and should be reset."""
        elapsed = (datetime.utcnow() - self._hour_start).total_seconds()
        return elapsed >= 3600  # 1 hour


# Singleton factory
_instance: TierRoutingEngine | None = None


def get_tier_routing_engine() -> TierRoutingEngine:
    """Get or create singleton TierRoutingEngine instance.

    Returns:
        TierRoutingEngine singleton
    """
    global _instance
    if _instance is None:
        _instance = TierRoutingEngine()
    return _instance
