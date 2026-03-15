"""Governance Metrics Collector — Phase 160: AI Governance Metrics.

Provides a best-effort metric emission layer for governance observability.
Each method wraps Prometheus metric updates in try/except so business logic
is never blocked by metric failures.

Usage:
    from app.services.governance_metrics_collector import governance_metrics
    governance_metrics.record_quality_gate_rule("freshness_minutes", "pass")
"""

import logging

logger = logging.getLogger(__name__)

# Bounded route categories for AI usage metrics
_ROUTE_MAP = {
    "chat": "chat",
    "chat_response": "chat",
    "tools": "tools",
    "tool_call": "tools",
    "sentry": "sentry",
    "background": "background",
    "optimization": "optimization",
}

# Valid statuses for quality gate rule evaluations
_VALID_RULE_STATUSES = {"pass", "warn", "fail"}

# Valid error types for tool call errors
_VALID_ERROR_TYPES = {
    "param_validation",
    "execution",
    "timeout",
    "permission",
    "module_inactive",
}


def _normalise_route(source: str) -> str:
    """Map a source string to a bounded route category."""
    if not source:
        return "other"
    lower = source.lower()
    # Direct match
    if lower in _ROUTE_MAP:
        return _ROUTE_MAP[lower]
    # Prefix match for background_* and optimization_*
    for prefix in ("background", "optimization"):
        if lower.startswith(prefix):
            return prefix
    return "other"


class GovernanceMetricsCollector:
    """Best-effort governance metric emitter.

    All methods are fire-and-forget: exceptions are logged at debug level
    and never propagated to callers.
    """

    def record_quality_gate_rule(self, rule_name: str, status: str) -> None:
        """Increment per-rule quality gate evaluation counter.

        Args:
            rule_name: Name of the quality gate rule evaluated.
            status: Evaluation outcome — "pass", "warn", or "fail".
        """
        try:
            from app.api.metrics import sentinel_quality_gate_rule_evaluations_total

            safe_status = status if status in _VALID_RULE_STATUSES else "fail"
            safe_name = str(rule_name or "unknown")[:64]
            sentinel_quality_gate_rule_evaluations_total.labels(rule_name=safe_name, status=safe_status).inc()
        except Exception:
            logger.debug("Failed to record quality gate rule metric", exc_info=True)

    def record_drift_score(self, model_id: str, model_type: str, score: float) -> None:
        """Set the current drift score gauge for a model.

        Args:
            model_id: Unique model identifier.
            model_type: Model category (e.g. "CHILLER", "AHU").
            score: Drift score between 0.0 and 1.0.
        """
        try:
            from app.api.metrics import sentinel_model_drift_score

            safe_id = str(model_id or "unknown")[:64]
            safe_type = str(model_type or "unknown")[:32]
            clamped = max(0.0, min(1.0, float(score)))
            sentinel_model_drift_score.labels(model_id=safe_id, model_type=safe_type).set(clamped)
        except Exception:
            logger.debug("Failed to record drift score metric", exc_info=True)

    def record_tool_error(self, tool_name: str, error_type: str) -> None:
        """Increment tool-call error counter by error classification.

        Args:
            tool_name: Name of the tool that errored.
            error_type: Classification — one of param_validation, execution,
                        timeout, permission, module_inactive.
        """
        try:
            from app.api.metrics import sentinel_tool_call_errors_total

            safe_name = str(tool_name or "unknown")[:64]
            safe_type = error_type if error_type in _VALID_ERROR_TYPES else "execution"
            sentinel_tool_call_errors_total.labels(tool_name=safe_name, error_type=safe_type).inc()
        except Exception:
            logger.debug("Failed to record tool error metric", exc_info=True)

    def record_approval_latency(self, site_id: str, tier: str, latency_seconds: float) -> None:
        """Observe approval latency in the histogram.

        Args:
            site_id: Site identifier.
            tier: Autonomy tier (tier1, tier2, tier3).
            latency_seconds: Seconds from request to decision.
        """
        try:
            from app.api.metrics import sentinel_approval_latency_seconds

            safe_site = str(site_id or "unknown")[:32]
            safe_tier = str(tier or "unknown")[:8]
            sentinel_approval_latency_seconds.labels(site_id=safe_site, tier=safe_tier).observe(
                max(0.0, float(latency_seconds))
            )
        except Exception:
            logger.debug("Failed to record approval latency metric", exc_info=True)

    def record_approval_rejection(self, site_id: str, rejected: bool) -> None:
        """Update rolling rejection rate gauge for a site.

        This is a simple gauge set — callers should compute the rate externally
        or this can be refined with a sliding window in future.

        Args:
            site_id: Site identifier.
            rejected: True if the decision was a rejection.
        """
        try:
            from app.api.metrics import sentinel_approval_rejection_rate

            safe_site = str(site_id or "unknown")[:32]
            # Increment/decrement a simple gauge tracking rejection count
            # Prometheus rate() on the counter gives the actual rate
            if rejected:
                sentinel_approval_rejection_rate.labels(site_id=safe_site).inc()
        except Exception:
            logger.debug("Failed to record approval rejection metric", exc_info=True)

    def record_ai_usage(
        self,
        route: str,
        site_id: str,
        provider: str,
        tokens: int,
        cost: float,
    ) -> None:
        """Increment token and cost counters by route and site.

        Args:
            route: Source/route category (will be normalised to bounded set).
            site_id: Site identifier.
            provider: AI provider name.
            tokens: Total tokens (input + output).
            cost: Cost in USD.
        """
        try:
            from app.api.metrics import (
                sentinel_ai_tokens_by_route_total,
                sentinel_ai_cost_by_route_total,
            )

            safe_route = _normalise_route(route)
            safe_site = str(site_id or "unknown")[:32]
            safe_provider = str(provider or "unknown")[:32]
            safe_tokens = max(0, int(tokens))
            safe_cost = max(0.0, float(cost))

            sentinel_ai_tokens_by_route_total.labels(route=safe_route, site_id=safe_site, provider=safe_provider).inc(
                safe_tokens
            )
            sentinel_ai_cost_by_route_total.labels(route=safe_route, site_id=safe_site).inc(safe_cost)
        except Exception:
            logger.debug("Failed to record AI usage metric", exc_info=True)


# Module-level singleton
governance_metrics = GovernanceMetricsCollector()
