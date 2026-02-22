"""
Fleet Aggregator - Anonymized Cross-Site Failure Pattern Collection

Aggregates failure patterns across all sites without exposing site-specific data.
Provides fleet-wide summary statistics, risk distribution, and benchmarking.

Phase 45-02: Fleet Learning and Cross-Site Insights.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Equipment types in fleet
EQUIPMENT_TYPES = ["chiller", "ahu", "fcu", "gen", "vav", "pump"]

# Common failure modes per equipment type
FAILURE_MODES = {
    "chiller": ["compressor_failure", "refrigerant_leak", "bearing_wear"],
    "ahu": ["filter_clogging", "motor_failure", "bearing_wear"],
    "fcu": ["coil_fouling", "valve_failure", "fan_failure"],
    "gen": ["fuel_system_failure", "alternator_failure", "starter_failure"],
    "vav": ["damper_failure", "sensor_failure", "actuator_failure"],
    "pump": ["bearing_wear", "seal_failure", "impeller_failure"],
}


class FleetAggregator:
    """Aggregates anonymized failure patterns across fleet."""

    def __init__(self):
        self._aggregation_cache: Dict[str, Any] = {}
        self._last_aggregation: Optional[str] = None

    def get_fleet_summary(self) -> Dict[str, Any]:
        """Get fleet-wide summary statistics.

        Returns:
            Summary with overview, type distribution, top failure patterns.
        """
        # Fleet-wide overview
        overview = {
            "total_sites": 5,
            "total_equipment": 185,
            "avg_fleet_health": 73.2,
            "total_open_alerts": 31,
            "monthly_maintenance_zar": 660000,
            "failure_patterns_tracked": 8,
            "total_recorded_failures": 281,
        }

        # Distribution by equipment type
        type_distribution = {
            "chiller": {"failures": 45, "total_cost_zar": 42000},
            "ahu": {"failures": 120, "total_cost_zar": 9000},
            "fcu": {"failures": 380, "total_cost_zar": 3000},
            "gen": {"failures": 30, "total_cost_zar": 25000},
            "vav": {"failures": 520, "total_cost_zar": 2000},
            "pump": {"failures": 90, "total_cost_zar": 6000},
        }

        # Top failure patterns
        top_patterns = [
            {
                "equipment_type": "chiller",
                "failure_type": "compressor_failure",
                "count": 12,
                "sites_affected": 3,
            },
            {
                "equipment_type": "ahu",
                "failure_type": "filter_clogging",
                "count": 28,
                "sites_affected": 4,
            },
            {
                "equipment_type": "fcu",
                "failure_type": "coil_fouling",
                "count": 45,
                "sites_affected": 5,
            },
            {
                "equipment_type": "pump",
                "failure_type": "bearing_wear",
                "count": 18,
                "sites_affected": 3,
            },
            {
                "equipment_type": "vav",
                "failure_type": "damper_failure",
                "count": 35,
                "sites_affected": 5,
            },
        ]

        return {
            "fleet_overview": overview,
            "type_distribution": type_distribution,
            "top_failure_patterns": top_patterns,
            "last_aggregation": datetime.now().isoformat(),
        }

    def aggregate_failure_patterns(self, equipment_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get anonymized failure patterns across fleet.

        Args:
            equipment_type: Filter by equipment type (optional).

        Returns:
            List of FailurePattern dicts.
        """
        all_patterns = [
            {
                "equipment_type": "chiller",
                "failure_type": "compressor_failure",
                "occurrence_count": 12,
                "avg_age_at_failure_years": 6.2,
                "avg_health_at_detection": 38.5,
                "common_precursors": ["high_discharge_temp", "oil_analysis_degradation"],
                "avg_repair_cost_zar": 3500,
                "avg_downtime_hours": 12.5,
                "sites_affected": 3,
            },
            {
                "equipment_type": "chiller",
                "failure_type": "refrigerant_leak",
                "occurrence_count": 8,
                "avg_age_at_failure_years": 8.1,
                "avg_health_at_detection": 42.0,
                "common_precursors": ["rising_subcooling", "pressure_drop"],
                "avg_repair_cost_zar": 2800,
                "avg_downtime_hours": 8.0,
                "sites_affected": 2,
            },
            {
                "equipment_type": "ahu",
                "failure_type": "filter_clogging",
                "occurrence_count": 28,
                "avg_age_at_failure_years": 2.3,
                "avg_health_at_detection": 51.0,
                "common_precursors": ["rising_pressure_drop", "reduced_airflow"],
                "avg_repair_cost_zar": 320,
                "avg_downtime_hours": 4.0,
                "sites_affected": 4,
            },
            {
                "equipment_type": "ahu",
                "failure_type": "motor_failure",
                "occurrence_count": 15,
                "avg_age_at_failure_years": 7.5,
                "avg_health_at_detection": 35.0,
                "common_precursors": ["vibration_increase", "temperature_rise"],
                "avg_repair_cost_zar": 1200,
                "avg_downtime_hours": 16.0,
                "sites_affected": 3,
            },
            {
                "equipment_type": "fcu",
                "failure_type": "coil_fouling",
                "occurrence_count": 45,
                "avg_age_at_failure_years": 4.2,
                "avg_health_at_detection": 55.0,
                "common_precursors": ["reduced_cooling_capacity", "water_temp_deviation"],
                "avg_repair_cost_zar": 180,
                "avg_downtime_hours": 2.0,
                "sites_affected": 5,
            },
            {
                "equipment_type": "gen",
                "failure_type": "fuel_system_failure",
                "occurrence_count": 5,
                "avg_age_at_failure_years": 12.0,
                "avg_health_at_detection": 28.0,
                "common_precursors": ["fuel_filter_clogging", "injector_wear"],
                "avg_repair_cost_zar": 8500,
                "avg_downtime_hours": 24.0,
                "sites_affected": 2,
            },
            {
                "equipment_type": "vav",
                "failure_type": "damper_failure",
                "occurrence_count": 35,
                "avg_age_at_failure_years": 5.5,
                "avg_health_at_detection": 45.0,
                "common_precursors": ["actuator_drift", "control_error"],
                "avg_repair_cost_zar": 520,
                "avg_downtime_hours": 6.0,
                "sites_affected": 5,
            },
            {
                "equipment_type": "pump",
                "failure_type": "bearing_wear",
                "occurrence_count": 18,
                "avg_age_at_failure_years": 6.8,
                "avg_health_at_detection": 40.0,
                "common_precursors": ["vibration_increase", "temperature_rise"],
                "avg_repair_cost_zar": 950,
                "avg_downtime_hours": 8.0,
                "sites_affected": 3,
            },
        ]

        if equipment_type:
            return [p for p in all_patterns if p["equipment_type"] == equipment_type]

        return all_patterns

    def get_similar_failures(
        self,
        equipment_type: str,
        failure_type: Optional[str] = None,
        exclude_site: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Find similar equipment failures across fleet.

        Args:
            equipment_type: Equipment type to match.
            failure_type: Specific failure type (optional).
            exclude_site: Site to exclude for privacy (optional).

        Returns:
            List of similar failures from other sites.
        """
        patterns = self.aggregate_failure_patterns(equipment_type)

        if failure_type:
            patterns = [p for p in patterns if p["failure_type"] == failure_type]

        # In demo mode, return all matches (in production, exclude site-specific data)
        return patterns

    def get_risk_distribution(self) -> Dict[str, Any]:
        """Get fleet-wide equipment risk distribution.

        Returns:
            Risk distribution by severity level.
        """
        return {
            "total_equipment": 185,
            "distribution": {
                "critical": {"count": 9, "percentage": 4.9},
                "high": {"count": 22, "percentage": 11.9},
                "medium": {"count": 27, "percentage": 15},
                "low": {"count": 126, "percentage": 68.2},
            },
            "sites_with_critical": 5,
            "total_sites": 5,
        }

    def get_benchmarks(self, equipment_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get fleet benchmarking data for equipment types.

        Args:
            equipment_type: Filter by equipment type (optional).

        Returns:
            List of Benchmark dicts.
        """
        all_benchmarks = [
            {
                "equipment_type": "chiller",
                "fleet_avg_health": 68.5,
                "fleet_avg_mtbf_days": 245,
                "fleet_avg_maintenance_cost_zar": 42000,
                "fleet_best_health": 85.0,
                "fleet_worst_health": 42.0,
                "total_equipment_count": 45,
                "total_sites": 15,
            },
            {
                "equipment_type": "ahu",
                "fleet_avg_health": 74.2,
                "fleet_avg_mtbf_days": 180,
                "fleet_avg_maintenance_cost_zar": 9000,
                "fleet_best_health": 88.0,
                "fleet_worst_health": 55.0,
                "total_equipment_count": 120,
                "total_sites": 15,
            },
            {
                "equipment_type": "fcu",
                "fleet_avg_health": 71.0,
                "fleet_avg_mtbf_days": 210,
                "fleet_avg_maintenance_cost_zar": 3000,
                "fleet_best_health": 82.0,
                "fleet_worst_health": 48.0,
                "total_equipment_count": 380,
                "total_sites": 15,
            },
            {
                "equipment_type": "gen",
                "fleet_avg_health": 82.1,
                "fleet_avg_mtbf_days": 365,
                "fleet_avg_maintenance_cost_zar": 25000,
                "fleet_best_health": 92.0,
                "fleet_worst_health": 70.0,
                "total_equipment_count": 30,
                "total_sites": 15,
            },
            {
                "equipment_type": "vav",
                "fleet_avg_health": 76.8,
                "fleet_avg_mtbf_days": 190,
                "fleet_avg_maintenance_cost_zar": 2000,
                "fleet_best_health": 89.0,
                "fleet_worst_health": 58.0,
                "total_equipment_count": 520,
                "total_sites": 15,
            },
            {
                "equipment_type": "pump",
                "fleet_avg_health": 72.4,
                "fleet_avg_mtbf_days": 220,
                "fleet_avg_maintenance_cost_zar": 6000,
                "fleet_best_health": 84.0,
                "fleet_worst_health": 52.0,
                "total_equipment_count": 90,
                "total_sites": 15,
            },
        ]

        if equipment_type:
            return [b for b in all_benchmarks if b["equipment_type"] == equipment_type]

        return all_benchmarks

    def benchmark_site(
        self,
        site_code: str,
        site_health: float,
        equipment_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Compare a site's performance against fleet average.

        Args:
            site_code: Site to benchmark.
            site_health: Current site health score (0-100).
            equipment_type: Filter by equipment type (optional).

        Returns:
            Comparison with fleet benchmarks.
        """
        benchmarks = self.get_benchmarks(equipment_type)

        # Calculate percentile (simple demo calculation)
        percentile = min(100, (site_health / 100) * 100)

        # Determine status
        if site_health >= 75:
            status = "healthy"
            message = "Performing above fleet average"
        elif site_health >= 60:
            status = "warning"
            message = "Performing at or below fleet average"
        else:
            status = "critical"
            message = "Urgent: Significant underperformance vs fleet"

        fleet_avg = sum(b["fleet_avg_health"] for b in benchmarks) / len(benchmarks) if benchmarks else 72.0

        return {
            "site_health": site_health,
            "fleet_avg_health": round(fleet_avg, 1),
            "fleet_best": max((b["fleet_best_health"] for b in benchmarks), default=92.0),
            "fleet_worst": min((b["fleet_worst_health"] for b in benchmarks), default=42.0),
            "percentile": round(percentile, 1),
            "status": status,
            "message": message,
            "equipment_type": equipment_type or "all",
            "benchmarks": benchmarks,
        }


# Singleton instance
_aggregator: Optional[FleetAggregator] = None


def get_fleet_aggregator() -> FleetAggregator:
    """Get singleton FleetAggregator instance."""
    global _aggregator
    if _aggregator is None:
        _aggregator = FleetAggregator()
    return _aggregator
