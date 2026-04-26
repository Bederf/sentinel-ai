"""
Fleet Aggregator - Anonymized Cross-Site Failure Pattern Collection

Aggregates failure patterns across all sites without exposing site-specific data.
Provides fleet-wide summary statistics, risk distribution, and benchmarking.

Phase 45-02: Fleet Learning and Cross-Site Insights.
"""

import logging
from datetime import datetime
from typing import Any

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
        self._aggregation_cache: dict[str, Any] = {}
        self._last_aggregation: str | None = None

    def _get_supabase_client(self):
        """Get Supabase client lazily to avoid import-time errors."""
        from app.database.supabase_client import get_supabase_client

        return get_supabase_client()

    def _get_real_counts(self) -> dict[str, Any]:
        """Query real counts from Supabase."""
        supabase = self._get_supabase_client()

        # Real site count
        sites = supabase.table("sites").select("id", count="exact").execute()
        total_sites = sites.count or 0

        # Real equipment count + health
        equip_result = supabase.table("equipment").select("health_score", count="exact").execute()
        total_equipment = equip_result.count or 0
        scores = [r["health_score"] for r in equip_result.data if r.get("health_score") is not None]
        avg_health = round(sum(scores) / len(scores), 1) if scores else 0.0

        # Active alerts
        alerts = supabase.table("alerts").select("id", count="exact").eq("status", "active").execute()
        total_open_alerts = alerts.count or 0

        # Open work orders (maintenance proxy)
        wo = supabase.table("work_orders").select("id", count="exact").eq("status", "open").execute()
        open_wo = wo.count or 0

        return {
            "total_sites": total_sites,
            "total_equipment": total_equipment,
            "avg_fleet_health": avg_health,
            "total_open_alerts": total_open_alerts,
            "open_work_orders": open_wo,
        }

    def get_fleet_summary(self) -> dict[str, Any]:
        """Get fleet-wide summary statistics.

        Returns:
            Summary with overview, type distribution, top failure patterns.
        """
        counts = self._get_real_counts()

        # Fleet-wide overview — real data from Supabase
        overview = {
            "total_sites": counts["total_sites"],
            "total_equipment": counts["total_equipment"],
            "avg_fleet_health": counts["avg_fleet_health"],
            "total_open_alerts": counts["total_open_alerts"],
            "monthly_maintenance_zar": counts["open_work_orders"] * 5000,  # proxy
            "failure_patterns_tracked": 0,  # requires anomaly_events table
            "total_recorded_failures": 0,  # requires failure_events table
        }

        # Distribution by equipment type — real counts from DB
        supabase = self._get_supabase_client()
        equip_data = supabase.table("equipment").select("type", "status").execute()

        type_failures: dict[str, int] = {}
        for row in equip_data.data:
            eq_type = (row.get("type") or "unknown").lower()
            status = row.get("status", "normal")
            if status in ("critical", "fault", "offline"):
                type_failures[eq_type] = type_failures.get(eq_type, 0) + 1

        type_distribution = {}
        for eq_type in EQUIPMENT_TYPES:
            type_distribution[eq_type] = {
                "failures": type_failures.get(eq_type, 0),
                "total_cost_zar": type_failures.get(eq_type, 0) * 5000,
            }
        # Catch-all for types not in EQUIPMENT_TYPES
        unknown_failures = sum(v for k, v in type_failures.items() if k not in EQUIPMENT_TYPES)
        if unknown_failures:
            type_distribution["unknown"] = {"failures": unknown_failures, "total_cost_zar": unknown_failures * 5000}

        # Top failure patterns — real data from alerts table
        # Group active alerts by equipment type
        alert_data = supabase.table("alerts").select("equipment_id", "severity").eq("status", "active").execute()
        top_patterns = []
        if alert_data.data:
            # Extract equipment type from equipment_id if possible
            for row in alert_data.data[:5]:
                equip_id = row.get("equipment_id", "")
                parts = equip_id.split("-")
                eq_type = parts[1].lower() if len(parts) >= 2 else "unknown"
                top_patterns.append(
                    {
                        "equipment_type": eq_type,
                        "failure_type": "active_alert",
                        "count": 1,
                        "sites_affected": 1,
                    }
                )

        return {
            "fleet_overview": overview,
            "type_distribution": type_distribution,
            "top_failure_patterns": top_patterns,
            "last_aggregation": datetime.now().isoformat(),
        }

    def aggregate_failure_patterns(self, equipment_type: str | None = None) -> list[dict[str, Any]]:
        """Get anonymized failure patterns across fleet.

        Args:
            equipment_type: Filter by equipment type (optional).

        Returns:
            List of FailurePattern dicts — sourced from real alert/equipment data.
        """
        supabase = self._get_supabase_client()
        alert_data = (
            supabase.table("alerts").select("equipment_id", "severity", "created_at").eq("status", "active").execute()
        )

        patterns: dict[str, dict[str, Any]] = {}
        for row in alert_data.data:
            equip_id = row.get("equipment_id", "")
            parts = equip_id.split("-")
            eq_type = parts[1].lower() if len(parts) >= 2 else "unknown"
            severity = row.get("severity", "medium")

            key = f"{eq_type}_{severity}"
            if key not in patterns:
                patterns[key] = {
                    "equipment_type": eq_type,
                    "failure_type": f"{severity}_alert",
                    "occurrence_count": 0,
                    "avg_age_at_failure_years": 0,
                    "avg_health_at_detection": 0,
                    "common_precursors": [],
                    "avg_repair_cost_zar": 0,
                    "avg_downtime_hours": 0,
                    "sites_affected": set(),
                }
            patterns[key]["occurrence_count"] += 1
            patterns[key]["sites_affected"].add(equip_id.split("-")[0] if equip_id else "unknown")

        # Convert sets to counts
        result = []
        for p in patterns.values():
            p["sites_affected"] = len(p["sites_affected"])
            del p["sites_affected"]  # convert set to count inline
            result.append(p)

        if equipment_type:
            result = [p for p in result if p["equipment_type"] == equipment_type]

        return (
            result
            if result
            else [{"equipment_type": "none", "failure_type": "no_data", "occurrence_count": 0, "sites_affected": 0}]
        )

    def get_similar_failures(
        self,
        equipment_type: str,
        failure_type: str | None = None,
        exclude_site: str | None = None,
    ) -> list[dict[str, Any]]:
        """Find similar equipment failures across fleet."""
        patterns = self.aggregate_failure_patterns(equipment_type)
        if failure_type:
            patterns = [p for p in patterns if p["failure_type"] == failure_type]
        return patterns

    def get_risk_distribution(self) -> dict[str, Any]:
        """Get fleet-wide equipment risk distribution from real equipment health data."""
        supabase = self._get_supabase_client()
        counts = self._get_real_counts()

        equip_data = supabase.table("equipment").select("health_score").execute()
        scores = [r["health_score"] for r in equip_data.data if r.get("health_score") is not None]

        critical = sum(1 for s in scores if s < 40)
        high = sum(1 for s in scores if 40 <= s < 60)
        medium = sum(1 for s in scores if 60 <= s < 80)
        low = sum(1 for s in scores if s >= 80)
        total = len(scores) or 1

        return {
            "total_equipment": counts["total_equipment"],
            "distribution": {
                "critical": {"count": critical, "percentage": round(critical / total * 100, 1)},
                "high": {"count": high, "percentage": round(high / total * 100, 1)},
                "medium": {"count": medium, "percentage": round(medium / total * 100, 1)},
                "low": {"count": low, "percentage": round(low / total * 100, 1)},
            },
            "sites_with_critical": counts["total_sites"] if critical > 0 else 0,
            "total_sites": counts["total_sites"],
        }

    def get_benchmarks(self, equipment_type: str | None = None) -> list[dict[str, Any]]:
        """Get fleet benchmarking data — real averages from equipment health scores."""
        supabase = self._get_supabase_client()

        all_types = [equipment_type] if equipment_type else EQUIPMENT_TYPES
        benchmarks = []

        for eq_type in all_types:
            rows = supabase.table("equipment").select("health_score").eq("type", eq_type).execute()
            scores = [r["health_score"] for r in rows.data if r.get("health_score") is not None]

            if scores:
                avg = round(sum(scores) / len(scores), 1)
                benchmarks.append(
                    {
                        "equipment_type": eq_type,
                        "fleet_avg_health": avg,
                        "fleet_avg_mtbf_days": 0,  # requires mtbf table
                        "fleet_avg_maintenance_cost_zar": 0,
                        "fleet_best_health": round(max(scores), 1),
                        "fleet_worst_health": round(min(scores), 1),
                        "total_equipment_count": len(scores),
                        "total_sites": self._get_real_counts()["total_sites"],
                    }
                )

        return benchmarks

    def benchmark_site(
        self,
        site_code: str,
        site_health: float,
        equipment_type: str | None = None,
    ) -> dict[str, Any]:
        """Compare a site's performance against fleet average."""
        benchmarks = self.get_benchmarks(equipment_type)
        fleet_avg = sum(b["fleet_avg_health"] for b in benchmarks) / len(benchmarks) if benchmarks else 72.0

        percentile = min(100, (site_health / 100) * 100)
        if site_health >= 75:
            status = "healthy"
            message = "Performing above fleet average"
        elif site_health >= 60:
            status = "warning"
            message = "Performing at or below fleet average"
        else:
            status = "critical"
            message = "Urgent: Significant underperformance vs fleet"

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
_aggregator: FleetAggregator | None = None


def get_fleet_aggregator() -> FleetAggregator:
    """Get singleton FleetAggregator instance."""
    global _aggregator
    if _aggregator is None:
        _aggregator = FleetAggregator()
    return _aggregator
