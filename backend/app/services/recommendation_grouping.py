"""
Recommendation Grouping Service

Groups related recommendations across multiple systems (HVAC, lighting, power)
for coordinated impact and combined benefit calculation.

Purpose:
- Enable users to approve coordinated changes across systems
- Calculate combined benefit of multi-system changes
- Define execution order and atomicity for grouped changes
- Improve outcomes through cross-system optimization
"""

import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class RecommendationObjective(StrEnum):
    """Objective categories for grouping recommendations."""

    LOAD_REDUCTION = "load_reduction"  # Peak shaving, demand response
    COMFORT_IMPROVEMENT = "comfort_improvement"  # Temperature, humidity, light
    EFFICIENCY = "efficiency"  # Energy optimization, off-peak usage
    FAULT_RECOVERY = "fault_recovery"  # Recover from equipment failure
    MAINTENANCE = "maintenance"  # Scheduled maintenance actions


class SystemType(StrEnum):
    """Building systems that recommendations can affect."""

    HVAC = "hvac"  # Heating, ventilation, air conditioning
    LIGHTING = "lighting"  # DALI, LEDs
    POWER = "power"  # Generators, UPS, load shedding


class ExecutionOrder(StrEnum):
    """Execution order for grouped recommendations (safest to riskiest)."""

    LIGHTING = "lighting"  # Safest - most reversible
    HVAC = "hvac"  # Medium risk
    POWER = "power"  # Riskiest - affects system stability


@dataclass
class CombinedBenefit:
    """Aggregated benefit of grouped recommendations."""

    energy_reduction_kw: float = 0.0  # Peak load reduction in kW
    cost_savings_per_hour: float = 0.0  # Cost savings per hour in currency
    co2_reduction_kg_per_hour: float = 0.0  # CO₂ reduction per hour
    comfort_impact: str = ""  # "improved", "unchanged", "degraded"

    def __add__(self, other: "CombinedBenefit") -> "CombinedBenefit":
        """Sum two benefits."""
        return CombinedBenefit(
            energy_reduction_kw=self.energy_reduction_kw + other.energy_reduction_kw,
            cost_savings_per_hour=self.cost_savings_per_hour + other.cost_savings_per_hour,
            co2_reduction_kg_per_hour=self.co2_reduction_kg_per_hour + other.co2_reduction_kg_per_hour,
            comfort_impact=self.comfort_impact or other.comfort_impact,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "energy_reduction_kw": round(self.energy_reduction_kw, 2),
            "cost_savings_per_hour": round(self.cost_savings_per_hour, 2),
            "co2_reduction_kg_per_hour": round(self.co2_reduction_kg_per_hour, 2),
            "comfort_impact": self.comfort_impact,
        }


@dataclass
class GroupedRecommendation:
    """Multiple recommendations grouped by objective."""

    objective: RecommendationObjective
    component_ids: list[str]  # IDs of individual recommendations
    components: list[dict[str, Any]]  # Full recommendation details
    combined_benefit: CombinedBenefit = field(default_factory=CombinedBenefit)
    group_confidence: float = 0.0  # Minimum confidence of all components
    execution_order: list[SystemType] = field(default_factory=list)
    priority: str = "medium"  # "critical", "high", "medium", "low"
    description: str = ""  # Human-readable description

    def meets_tier2_requirement(self, threshold: float = 0.70) -> bool:
        """Check if group meets Tier 2 confidence requirement."""
        return self.group_confidence >= threshold

    def meets_tier3_requirement(self, threshold: float = 0.85) -> bool:
        """Check if group meets Tier 3 confidence requirement."""
        return self.group_confidence >= threshold

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "id": f"group_{self.objective}_{hash(tuple(self.component_ids))}",
            "objective": self.objective.value,
            "components": self.components,
            "combined_benefit": self.combined_benefit.to_dict(),
            "group_confidence": round(self.group_confidence, 3),
            "execution_order": [s.value for s in self.execution_order],
            "priority": self.priority,
            "description": self.description,
            "component_count": len(self.components),
        }


class RecommendationGrouping:
    """
    Service for grouping recommendations by objective.

    Groups recommendations from different systems into coordinated packages
    with combined benefit calculation.
    """

    # Objective patterns for classifying recommendations
    LOAD_REDUCTION_PATTERNS = {
        "chiller_setpoint_down",
        "chiller_down",
        "fan_down",
        "ahu_down",
        "fcu_down",
        "lights_dim",
        "lights_off",
        "ups_eco",
        "generator_standby",
        "load_shedding",
        "peak_shaving",
    }

    COMFORT_IMPROVEMENT_PATTERNS = {
        "temperature_increase",
        "temperature_decrease",
        "humidity_down",
        "humidity_increase",
        "lights_bright",
        "lights_increase",
        "comfort_adjustment",
    }

    EFFICIENCY_PATTERNS = {
        "efficiency_increase",
        "off_peak_optimization",
        "demand_response",
        "energy_saving",
        "switching_cheaper_source",
        "load_balancing",
    }

    FAULT_RECOVERY_PATTERNS = {
        "restart_equipment",
        "reset_alarms",
        "recovery_mode",
        "failover_activate",
    }

    MAINTENANCE_PATTERNS = {
        "scheduled_maintenance",
        "preventive_service",
        "filter_replacement",
        "calibration",
    }

    def __init__(self):
        """Initialize grouping service."""
        pass

    async def group_recommendations_by_objective(self, recommendations: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Group recommendations by objective across all systems.

        Args:
            recommendations: List of individual recommendations from all systems

        Returns:
            Dict with 'individual' (ungrouped) and 'grouped' (multi-system) recommendations
        """
        if not recommendations:
            return {"individual": [], "grouped": []}

        # Classify each recommendation
        classified = {}
        for rec in recommendations:
            objective = self._classify_objective(rec)
            if objective not in classified:
                classified[objective] = []
            classified[objective].append(rec)

        # Create grouped recommendations
        grouped = []
        individual = []

        for objective, recs in classified.items():
            if len(recs) > 1:
                # Group if multiple recommendations with same objective
                group = self._create_grouped_recommendation(objective, recs)
                grouped.append(group)
            else:
                # Keep single recommendations as individual
                individual.extend(recs)

        return {
            "individual": individual,
            "grouped": [g.to_dict() for g in grouped],
            "summary": {
                "total_recommendations": len(recommendations),
                "ungrouped_count": len(individual),
                "grouped_count": len(grouped),
                "total_grouped_components": sum(len(g.components) for g in grouped),
            },
        }

    def _classify_objective(self, recommendation: dict[str, Any]) -> RecommendationObjective:
        """Classify recommendation into objective category."""
        action = recommendation.get("action", "").lower()
        system = recommendation.get("system", "").lower()

        # Check patterns
        if self._matches_pattern(action, self.LOAD_REDUCTION_PATTERNS):
            return RecommendationObjective.LOAD_REDUCTION
        elif self._matches_pattern(action, self.COMFORT_IMPROVEMENT_PATTERNS):
            return RecommendationObjective.COMFORT_IMPROVEMENT
        elif self._matches_pattern(action, self.EFFICIENCY_PATTERNS):
            return RecommendationObjective.EFFICIENCY
        elif self._matches_pattern(action, self.FAULT_RECOVERY_PATTERNS):
            return RecommendationObjective.FAULT_RECOVERY
        elif self._matches_pattern(action, self.MAINTENANCE_PATTERNS):
            return RecommendationObjective.MAINTENANCE
        else:
            # Default based on system
            if "hvac" in system:
                return RecommendationObjective.COMFORT_IMPROVEMENT
            elif "lighting" in system:
                return RecommendationObjective.EFFICIENCY
            elif "power" in system:
                return RecommendationObjective.LOAD_REDUCTION
            else:
                return RecommendationObjective.EFFICIENCY

    def _matches_pattern(self, text: str, patterns: set[str]) -> bool:
        """Check if text matches any pattern."""
        text_lower = text.lower()
        return any(pattern in text_lower for pattern in patterns)

    def _create_grouped_recommendation(
        self, objective: RecommendationObjective, recommendations: list[dict[str, Any]]
    ) -> GroupedRecommendation:
        """Create grouped recommendation from multiple individual recommendations."""

        # Extract system types
        systems: set[SystemType] = set()
        for rec in recommendations:
            system = rec.get("system", "").lower()
            if "hvac" in system:
                systems.add(SystemType.HVAC)
            elif "lighting" in system:
                systems.add(SystemType.LIGHTING)
            elif "power" in system:
                systems.add(SystemType.POWER)

        # Define execution order (safest to riskiest)
        execution_order = []
        for system_type in [SystemType.LIGHTING, SystemType.HVAC, SystemType.POWER]:
            if system_type in systems:
                execution_order.append(system_type)

        # Calculate combined benefit
        combined_benefit = CombinedBenefit()
        for rec in recommendations:
            benefit = rec.get("benefit", {})
            combined_benefit = combined_benefit + CombinedBenefit(
                energy_reduction_kw=float(benefit.get("energy_reduction_kw", 0)),
                cost_savings_per_hour=float(benefit.get("cost_savings_per_hour", 0)),
                co2_reduction_kg_per_hour=float(benefit.get("co2_reduction_kg_per_hour", 0)),
            )

        # Calculate group confidence (minimum of all components)
        confidences = [float(rec.get("confidence", 0.5)) for rec in recommendations]
        group_confidence = min(confidences) if confidences else 0.5

        # Determine priority based on objective and confidence
        priority = self._determine_priority(objective, group_confidence, len(recommendations))

        # Create description
        description = self._create_description(objective, systems, len(recommendations))

        return GroupedRecommendation(
            objective=objective,
            component_ids=[rec.get("id", f"rec_{i}") for i, rec in enumerate(recommendations)],
            components=recommendations,
            combined_benefit=combined_benefit,
            group_confidence=group_confidence,
            execution_order=execution_order,
            priority=priority,
            description=description,
        )

    def _determine_priority(self, objective: RecommendationObjective, confidence: float, component_count: int) -> str:
        """Determine priority of grouped recommendation."""
        # High priority: high confidence + load reduction
        if objective == RecommendationObjective.LOAD_REDUCTION and confidence > 0.85:
            return "critical"
        elif confidence > 0.80:
            return "high"
        elif confidence > 0.70:
            return "medium"
        else:
            return "low"

    def _create_description(
        self, objective: RecommendationObjective, systems: set[SystemType], component_count: int
    ) -> str:
        """Create human-readable description of grouped recommendation."""
        system_names = ", ".join(s.value.capitalize() for s in sorted(systems))
        objective_name = objective.value.replace("_", " ").title()
        return f"{objective_name} via {system_names} ({component_count} changes)"

    async def group_with_api_recommendations(
        self,
        hvac_recommendations: list[dict[str, Any]],
        lighting_recommendations: list[dict[str, Any]],
        power_recommendations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Group recommendations from all three AI optimizer outputs.

        Args:
            hvac_recommendations: Output from optimize_hvac()
            lighting_recommendations: Output from optimize_lighting()
            power_recommendations: Output from optimize_power()

        Returns:
            Grouped and ungrouped recommendations with combined benefits
        """
        # Combine all recommendations
        all_recommendations = []

        # Add HVAC recommendations with system tag
        for rec in hvac_recommendations:
            rec["system"] = "hvac"
            all_recommendations.append(rec)

        # Add lighting recommendations
        for rec in lighting_recommendations:
            rec["system"] = "lighting"
            all_recommendations.append(rec)

        # Add power recommendations
        for rec in power_recommendations:
            rec["system"] = "power"
            all_recommendations.append(rec)

        # Group all recommendations
        result = await self.group_recommendations_by_objective(all_recommendations)

        logger.info(
            f"Grouped {len(all_recommendations)} recommendations into "
            f"{result['summary']['grouped_count']} groups and "
            f"{result['summary']['ungrouped_count']} individual recommendations"
        )

        return result


# Singleton instance
_grouping_service: RecommendationGrouping | None = None


def get_recommendation_grouping() -> RecommendationGrouping:
    """Get or create recommendation grouping service singleton."""
    global _grouping_service
    if _grouping_service is None:
        _grouping_service = RecommendationGrouping()
    return _grouping_service
