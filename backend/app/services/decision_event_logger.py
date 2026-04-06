"""Structured lifecycle event logger for PARASITE decision pipeline.

Emits JSON events at every stage of the autonomy pipeline, keyed by
correlation_id for end-to-end traceability. Events are collected by
Promtail and shipped to Loki for querying in Grafana.

Pipeline stages:
    recommendation.created  → AI generates a recommendation
    tier_routing.decided    → Tier routing classifies to tier 1/2/3
    safety.validated        → SafetyEngine pass/fail
    device.write            → Device write success/fail
    cov.verified            → COV verification result
    outcome.scheduled       → Outcome measurement window started
    outcome.measured        → Outcome measurement complete
    rollback.executed       → Auto-rollback triggered
    approval.decided        → Tier 2 human approval/rejection
    feedback.recorded       → ML feedback loop closed
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any

# Dedicated logger for Promtail/Loki ingestion of decision events
decision_logger = logging.getLogger("sentinel.decisions")

logger = logging.getLogger(__name__)


def emit_decision_event(
    stage: str,
    *,
    correlation_id: str = "",
    decision_id: str = "",
    recommendation_id: str = "",
    equipment_code: str = "",
    site_id: str = "",
    tier: str = "",
    status: str = "",
    details: dict[str, Any] | None = None,
) -> None:
    """Emit a structured JSON event for a pipeline stage.

    Args:
        stage: Pipeline stage name (e.g., "tier_routing.decided")
        correlation_id: End-to-end trace ID linking all events
        decision_id: PARASITE decision UUID
        recommendation_id: Recommendation UUID
        equipment_code: Target equipment code
        site_id: Building site ID
        tier: Autonomy tier (tier1/tier2/tier3)
        status: Stage outcome (e.g., "success", "failed", "pending")
        details: Stage-specific data dict
    """
    try:
        event = {
            "timestamp": datetime.now(UTC).isoformat(),
            "stage": stage,
            "correlation_id": correlation_id,
            "decision_id": decision_id,
            "recommendation_id": recommendation_id,
            "equipment_code": equipment_code,
            "site_id": site_id,
            "tier": tier,
            "status": status,
            "details": details or {},
            "component": "sentinel-parasite",
        }

        log_line = json.dumps(event, default=str)

        # Use warning for failures, info for success/normal events
        if status in ("failed", "rejected", "rollback"):
            decision_logger.warning(log_line)
        else:
            decision_logger.info(log_line)

    except Exception as e:
        logger.error(f"Failed to emit decision event {stage}: {e}")
