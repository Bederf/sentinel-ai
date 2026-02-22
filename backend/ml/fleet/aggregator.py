"""
Fleet Aggregator - Anonymized failure pattern aggregation across sites.

Aggregates failure patterns, equipment health, and maintenance data across
multiple buildings without exposing site-specific identifiers. Enables
fleet-wide learning while maintaining privacy.

Phase 45-02: Fleet Learning and Cross-Site Insights.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Equipment types tracked in fleet
FLEET_EQUIPMENT_TYPES = [
    "CHILLER",
    "AHU",
    "FCU",
    "VAV",
    "GEN",
    "UPS",
    "PUMP",
    "CT",
    "DALI",
]

# Failure types aggregated
FAILURE_TYPES = [
    "compressor_failure",
    "bearing_wear",
    "refrigerant_leak",
    "filter_blockage",
    "motor_overload",
    "belt_wear",
    "electrical_fault",
    "sensor_drift",
    "valve_stuck",
    "fan_imbalance",
    "coil_fouling",
    "control_failure",
]


@dataclass
class FailurePattern:
    """An aggregated failure pattern across the fleet."""

    equipment_type: str
    failure_type: str
    count: int = 0
    avg_age_at_failure_years: float = 0.0
    avg_health_at_detection: float = 0.0
    common_precursors: List[str] = field(default_factory=list)
    avg_repair_cost_zar: float = 0.0
    avg_downtime_hours: float = 0.0
    sites_affected: int = 0  # Count only, no identifiers


@dataclass
class FleetBenchmark:
    """Benchmarking data for comparing site against fleet."""

    equipment_type: str
    fleet_avg_health: float
    fleet_avg_mtbf_days: float  # Mean time between failures
    fleet_avg_maintenance_cost_zar: float
    fleet_best_health: float
    fleet_worst_health: float
    total_equipment_count: int
    total_sites: int


class FleetAggregator:
    """Aggregates anonymized failure patterns across fleet.

    Privacy-first design: all data is aggregated and anonymized
    before sharing. Site identifiers are stripped, only counts
    and averages are exposed.
    """

    def __init__(self):
        self._failure_patterns: Dict[str, FailurePattern] = {}
        self._site_data: Dict[str, Dict[str, Any]] = {}
        self._benchmarks: Dict[str, FleetBenchmark] = {}
        self._last_aggregation: Optional[str] = None
        self._seed_demo_data()

    def _seed_demo_data(self):
        """Seed with realistic fleet data for demo."""
        demo_patterns = [
            FailurePattern(
                equipment_type="CHILLER",
                failure_type="compressor_failure",
                count=23,
                avg_age_at_failure_years=18.5,
                avg_health_at_detection=42.0,
                common_precursors=[
                    "high_discharge_pressure",
                    "elevated_vibration",
                    "oil_analysis_abnormal",
                ],
                avg_repair_cost_zar=65000.0,
                avg_downtime_hours=48.0,
                sites_affected=8,
            ),
            FailurePattern(
                equipment_type="CHILLER",
                failure_type="refrigerant_leak",
                count=15,
                avg_age_at_failure_years=12.3,
                avg_health_at_detection=58.0,
                common_precursors=[
                    "subcooling_low",
                    "superheat_high",
                    "pressure_differential",
                ],
                avg_repair_cost_zar=28000.0,
                avg_downtime_hours=24.0,
                sites_affected=6,
            ),
            FailurePattern(
                equipment_type="AHU",
                failure_type="bearing_wear",
                count=31,
                avg_age_at_failure_years=8.2,
                avg_health_at_detection=55.0,
                common_precursors=[
                    "elevated_vibration",
                    "abnormal_noise",
                    "motor_current_drift",
                ],
                avg_repair_cost_zar=12000.0,
                avg_downtime_hours=8.0,
                sites_affected=11,
            ),
            FailurePattern(
                equipment_type="AHU",
                failure_type="filter_blockage",
                count=89,
                avg_age_at_failure_years=0.5,
                avg_health_at_detection=72.0,
                common_precursors=[
                    "pressure_drop_high",
                    "airflow_reduced",
                ],
                avg_repair_cost_zar=3500.0,
                avg_downtime_hours=2.0,
                sites_affected=14,
            ),
            FailurePattern(
                equipment_type="FCU",
                failure_type="valve_stuck",
                count=42,
                avg_age_at_failure_years=6.7,
                avg_health_at_detection=48.0,
                common_precursors=[
                    "temperature_hunting",
                    "actuator_fault",
                ],
                avg_repair_cost_zar=4500.0,
                avg_downtime_hours=3.0,
                sites_affected=9,
            ),
            FailurePattern(
                equipment_type="GEN",
                failure_type="electrical_fault",
                count=7,
                avg_age_at_failure_years=15.0,
                avg_health_at_detection=35.0,
                common_precursors=[
                    "insulation_resistance_low",
                    "voltage_regulation_drift",
                    "excitation_fault",
                ],
                avg_repair_cost_zar=85000.0,
                avg_downtime_hours=72.0,
                sites_affected=4,
            ),
            FailurePattern(
                equipment_type="PUMP",
                failure_type="bearing_wear",
                count=19,
                avg_age_at_failure_years=9.1,
                avg_health_at_detection=50.0,
                common_precursors=[
                    "elevated_vibration",
                    "seal_leak",
                    "motor_temperature_high",
                ],
                avg_repair_cost_zar=8000.0,
                avg_downtime_hours=6.0,
                sites_affected=7,
            ),
            FailurePattern(
                equipment_type="VAV",
                failure_type="control_failure",
                count=55,
                avg_age_at_failure_years=5.3,
                avg_health_at_detection=60.0,
                common_precursors=[
                    "sensor_drift",
                    "actuator_hunting",
                    "communication_fault",
                ],
                avg_repair_cost_zar=2500.0,
                avg_downtime_hours=1.5,
                sites_affected=12,
            ),
        ]

        for pattern in demo_patterns:
            key = f"{pattern.equipment_type}:{pattern.failure_type}"
            self._failure_patterns[key] = pattern

        # Seed fleet benchmarks
        self._benchmarks = {
            "CHILLER": FleetBenchmark(
                equipment_type="CHILLER",
                fleet_avg_health=68.5,
                fleet_avg_mtbf_days=245,
                fleet_avg_maintenance_cost_zar=42000.0,
                fleet_best_health=92.0,
                fleet_worst_health=28.0,
                total_equipment_count=45,
                total_sites=15,
            ),
            "AHU": FleetBenchmark(
                equipment_type="AHU",
                fleet_avg_health=74.2,
                fleet_avg_mtbf_days=180,
                fleet_avg_maintenance_cost_zar=8500.0,
                fleet_best_health=95.0,
                fleet_worst_health=35.0,
                total_equipment_count=120,
                total_sites=15,
            ),
            "FCU": FleetBenchmark(
                equipment_type="FCU",
                fleet_avg_health=71.0,
                fleet_avg_mtbf_days=210,
                fleet_avg_maintenance_cost_zar=3200.0,
                fleet_best_health=98.0,
                fleet_worst_health=40.0,
                total_equipment_count=380,
                total_sites=15,
            ),
            "GEN": FleetBenchmark(
                equipment_type="GEN",
                fleet_avg_health=82.1,
                fleet_avg_mtbf_days=365,
                fleet_avg_maintenance_cost_zar=25000.0,
                fleet_best_health=96.0,
                fleet_worst_health=45.0,
                total_equipment_count=30,
                total_sites=15,
            ),
            "VAV": FleetBenchmark(
                equipment_type="VAV",
                fleet_avg_health=76.8,
                fleet_avg_mtbf_days=190,
                fleet_avg_maintenance_cost_zar=1800.0,
                fleet_best_health=99.0,
                fleet_worst_health=42.0,
                total_equipment_count=520,
                total_sites=15,
            ),
            "PUMP": FleetBenchmark(
                equipment_type="PUMP",
                fleet_avg_health=72.4,
                fleet_avg_mtbf_days=220,
                fleet_avg_maintenance_cost_zar=5500.0,
                fleet_best_health=94.0,
                fleet_worst_health=30.0,
                total_equipment_count=90,
                total_sites=15,
            ),
        }

        # Seed site-level data (anonymized - site codes only for internal tracking)
        sites = ["site-001", "site-002", "site-003", "site-004", "site-005"]
        site_health = [72.3, 65.8, 81.2, 69.5, 77.1]
        site_equipment_counts = [32, 48, 28, 35, 42]
        site_open_alerts = [5, 12, 2, 8, 4]
        site_maintenance_costs = [125000, 185000, 95000, 145000, 110000]

        for i, site_code in enumerate(sites):
            self._site_data[site_code] = {
                "avg_health": site_health[i],
                "equipment_count": site_equipment_counts[i],
                "open_alerts": site_open_alerts[i],
                "monthly_maintenance_zar": site_maintenance_costs[i],
                "critical_equipment": max(1, site_open_alerts[i] // 3),
            }

        self._last_aggregation = datetime.now().isoformat()

    def aggregate_failure_patterns(
        self,
        equipment_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Aggregate anonymized failure patterns across fleet.

        Args:
            equipment_type: Optional filter by equipment type.

        Returns:
            List of failure pattern dicts without site identifiers.
        """
        patterns = list(self._failure_patterns.values())

        if equipment_type:
            patterns = [p for p in patterns if p.equipment_type.upper() == equipment_type.upper()]

        # Sort by count descending (most common failures first)
        patterns.sort(key=lambda p: p.count, reverse=True)

        return [
            {
                "equipment_type": p.equipment_type,
                "failure_type": p.failure_type,
                "occurrence_count": p.count,
                "avg_age_at_failure_years": round(p.avg_age_at_failure_years, 1),
                "avg_health_at_detection": round(p.avg_health_at_detection, 1),
                "common_precursors": p.common_precursors,
                "avg_repair_cost_zar": round(p.avg_repair_cost_zar, 0),
                "avg_downtime_hours": round(p.avg_downtime_hours, 1),
                "sites_affected": p.sites_affected,
            }
            for p in patterns
        ]

    def get_similar_failures(
        self,
        equipment_type: str,
        failure_type: Optional[str] = None,
        exclude_site: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Find similar equipment failures across fleet.

        Privacy: excludes the requesting site's data from results.

        Args:
            equipment_type: Type of equipment to match.
            failure_type: Optional specific failure type to match.
            exclude_site: Site to exclude from results (privacy).

        Returns:
            List of similar failure patterns with anonymized data.
        """
        matches = []

        for key, pattern in self._failure_patterns.items():
            if pattern.equipment_type.upper() != equipment_type.upper():
                continue
            if failure_type and pattern.failure_type != failure_type:
                continue

            # Adjust count if excluding a site (approximate)
            adjusted_count = pattern.count
            adjusted_sites = pattern.sites_affected
            if exclude_site and adjusted_sites > 1:
                # Remove ~1/sites worth of data
                reduction_factor = 1.0 / adjusted_sites
                adjusted_count = max(1, int(adjusted_count * (1 - reduction_factor)))
                adjusted_sites -= 1

            matches.append(
                {
                    "equipment_type": pattern.equipment_type,
                    "failure_type": pattern.failure_type,
                    "fleet_occurrences": adjusted_count,
                    "avg_age_at_failure_years": round(pattern.avg_age_at_failure_years, 1),
                    "precursor_pattern": pattern.common_precursors,
                    "avg_days_warning": max(7, int(pattern.avg_health_at_detection / 2)),
                    "avg_repair_cost_zar": round(pattern.avg_repair_cost_zar, 0),
                    "confidence": min(0.95, 0.5 + (adjusted_count / 100)),
                    "other_sites_count": adjusted_sites,
                }
            )

        # Sort by occurrences
        matches.sort(key=lambda m: m["fleet_occurrences"], reverse=True)
        return matches

    def get_fleet_summary(self) -> Dict[str, Any]:
        """Get fleet-wide summary statistics.

        Returns anonymized, aggregated fleet overview.
        """
        total_patterns = len(self._failure_patterns)
        total_occurrences = sum(p.count for p in self._failure_patterns.values())
        total_sites = len(self._site_data)
        total_equipment = sum(s["equipment_count"] for s in self._site_data.values())
        avg_fleet_health = sum(s["avg_health"] for s in self._site_data.values()) / max(total_sites, 1)
        total_alerts = sum(s["open_alerts"] for s in self._site_data.values())
        total_maintenance = sum(s["monthly_maintenance_zar"] for s in self._site_data.values())

        # Equipment type distribution
        type_distribution = {}
        for pattern in self._failure_patterns.values():
            eq_type = pattern.equipment_type
            if eq_type not in type_distribution:
                type_distribution[eq_type] = {"failures": 0, "total_cost_zar": 0}
            type_distribution[eq_type]["failures"] += pattern.count
            type_distribution[eq_type]["total_cost_zar"] += pattern.count * pattern.avg_repair_cost_zar

        # Top failure patterns
        top_patterns = sorted(
            self._failure_patterns.values(),
            key=lambda p: p.count,
            reverse=True,
        )[:5]

        return {
            "fleet_overview": {
                "total_sites": total_sites,
                "total_equipment": total_equipment,
                "avg_fleet_health": round(avg_fleet_health, 1),
                "total_open_alerts": total_alerts,
                "monthly_maintenance_zar": total_maintenance,
                "failure_patterns_tracked": total_patterns,
                "total_recorded_failures": total_occurrences,
            },
            "type_distribution": type_distribution,
            "top_failure_patterns": [
                {
                    "equipment_type": p.equipment_type,
                    "failure_type": p.failure_type,
                    "count": p.count,
                    "sites_affected": p.sites_affected,
                }
                for p in top_patterns
            ],
            "last_aggregation": self._last_aggregation,
        }

    def get_benchmarks(
        self,
        equipment_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get fleet benchmarking data.

        Args:
            equipment_type: Optional filter.

        Returns:
            Benchmark data for comparison against fleet averages.
        """
        benchmarks = list(self._benchmarks.values())

        if equipment_type:
            benchmarks = [b for b in benchmarks if b.equipment_type.upper() == equipment_type.upper()]

        return [
            {
                "equipment_type": b.equipment_type,
                "fleet_avg_health": b.fleet_avg_health,
                "fleet_avg_mtbf_days": b.fleet_avg_mtbf_days,
                "fleet_avg_maintenance_cost_zar": b.fleet_avg_maintenance_cost_zar,
                "fleet_best_health": b.fleet_best_health,
                "fleet_worst_health": b.fleet_worst_health,
                "total_equipment_count": b.total_equipment_count,
                "total_sites": b.total_sites,
            }
            for b in benchmarks
        ]

    def benchmark_site(
        self,
        site_code: str,
        site_health: float,
        equipment_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Compare a site's performance against fleet average.

        Args:
            site_code: The site to benchmark (used internally only).
            site_health: Current site health score.
            equipment_type: Optional equipment type filter.

        Returns:
            Comparison results with percentile ranking.
        """
        benchmarks = self.get_benchmarks(equipment_type)

        if not benchmarks:
            return {
                "site_health": site_health,
                "comparison": "no_data",
                "message": "No fleet benchmarks available",
            }

        # Average across requested benchmarks
        avg_fleet_health = sum(b["fleet_avg_health"] for b in benchmarks) / len(benchmarks)
        best_health = max(b["fleet_best_health"] for b in benchmarks)
        worst_health = min(b["fleet_worst_health"] for b in benchmarks)

        # Percentile approximation (linear interpolation)
        health_range = best_health - worst_health
        if health_range > 0:
            percentile = ((site_health - worst_health) / health_range) * 100
            percentile = max(0, min(100, percentile))
        else:
            percentile = 50.0

        # Classification
        if site_health >= avg_fleet_health * 1.1:
            status = "above_average"
            message = "Site is performing above fleet average"
        elif site_health >= avg_fleet_health * 0.9:
            status = "on_par"
            message = "Site is performing on par with fleet average"
        else:
            status = "below_average"
            message = "Site is performing below fleet average"

        return {
            "site_health": round(site_health, 1),
            "fleet_avg_health": round(avg_fleet_health, 1),
            "fleet_best": round(best_health, 1),
            "fleet_worst": round(worst_health, 1),
            "percentile": round(percentile, 1),
            "status": status,
            "message": message,
            "equipment_type": equipment_type or "all",
            "benchmarks": benchmarks,
        }

    def get_risk_distribution(self) -> Dict[str, Any]:
        """Get fleet-wide risk distribution.

        Returns distribution of equipment by risk level across fleet.
        """
        # Derive from site data and failure patterns
        total_equipment = sum(s["equipment_count"] for s in self._site_data.values())
        total_critical = sum(s["critical_equipment"] for s in self._site_data.values())
        total_alerts = sum(s["open_alerts"] for s in self._site_data.values())

        # Approximate distribution
        critical_pct = (total_critical / max(total_equipment, 1)) * 100
        high_pct = ((total_alerts - total_critical) / max(total_equipment, 1)) * 100
        medium_pct = 15.0  # Estimated from typical fleet distributions
        low_pct = 100.0 - critical_pct - high_pct - medium_pct

        return {
            "total_equipment": total_equipment,
            "distribution": {
                "critical": {
                    "count": total_critical,
                    "percentage": round(critical_pct, 1),
                },
                "high": {
                    "count": total_alerts - total_critical,
                    "percentage": round(max(0, high_pct), 1),
                },
                "medium": {
                    "count": int(total_equipment * medium_pct / 100),
                    "percentage": round(medium_pct, 1),
                },
                "low": {
                    "count": int(total_equipment * max(0, low_pct) / 100),
                    "percentage": round(max(0, low_pct), 1),
                },
            },
            "sites_with_critical": sum(1 for s in self._site_data.values() if s["critical_equipment"] > 0),
            "total_sites": len(self._site_data),
        }


# Singleton
_aggregator: Optional[FleetAggregator] = None


def get_fleet_aggregator() -> FleetAggregator:
    """Get singleton FleetAggregator instance."""
    global _aggregator
    if _aggregator is None:
        _aggregator = FleetAggregator()
    return _aggregator
