"""
Service Optimizer (Phase 56-03)

Uses RUL predictions and degradation data to recommend optimal service timing,
track asset utilization (% of component life consumed), and demonstrate cost
savings of condition-based maintenance over fixed schedules.

This is the business-value layer that justifies the conditional maintenance approach.
"""

import logging
from datetime import datetime, timedelta

from app.models.condition import (
    AssetUtilization,
    MaintenanceCostComparison,
    OptimizedSchedule,
    ServiceWindow,
    TrendDirection,
    UtilizationStatus,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Service Cost Rates (ZAR per service, by equipment type)
# ============================================================================

SERVICE_COST_RATES: dict[str, float] = {
    "chiller": 8500.0,
    "ahu": 3200.0,
    "fcu": 1800.0,
    "generator": 12000.0,
    "pump": 2500.0,
    "vav": 1200.0,
    "dali": 800.0,
}

DEFAULT_SERVICE_COST = 2000.0  # Default for unknown equipment types


# ============================================================================
# Elements where lower values are worse (inverted utilization)
# ============================================================================

INVERTED_ELEMENTS = {
    "efficiency",
    "cop",
    "eer",
    "seer",
    "cooling_capacity",
    "flow_rate",
    "airflow",
    "battery_voltage",
    "fuel_level",
}


class ServiceOptimizer:
    """
    Optimizes maintenance service timing based on equipment condition data.

    Provides:
    - Asset utilization tracking (% of component life consumed)
    - Optimal service window calculation (70% of remaining life)
    - Fixed vs conditional maintenance cost comparison
    - Fleet-wide schedule optimization
    """

    def __init__(self):
        """Initialize with lazy service references."""
        self._trend_service = None
        self._rul_calculator = None

    @property
    def trend_service(self):
        """Lazy-load ElementTrendService."""
        if self._trend_service is None:
            from app.services.element_trend_service import get_element_trend_service

            self._trend_service = get_element_trend_service()
        return self._trend_service

    @property
    def rul_calculator(self):
        """Lazy-load RULCalculator (from 56-02). Returns None if not available."""
        if self._rul_calculator is None:
            try:
                from app.services.rul_calculator import get_rul_calculator

                self._rul_calculator = get_rul_calculator()
            except (ImportError, Exception) as e:
                logger.debug(f"RULCalculator not available: {e}")
                self._rul_calculator = None
        return self._rul_calculator

    # ========================================================================
    # Asset Utilization
    # ========================================================================

    async def calculate_utilization(
        self, equipment_id: str, equipment_type: str | None = None
    ) -> list[AssetUtilization]:
        """
        Calculate asset utilization for all elements of an equipment.

        For each element:
        - utilization_percent = (current_value / threshold_value) * 100
        - For inverted elements (where lower is worse): invert the calculation
        - Status: <60% = healthy, 60-85% = aging, >85% = end_of_life

        Args:
            equipment_id: Equipment identifier
            equipment_type: Optional equipment type for context

        Returns:
            List of AssetUtilization, one per element with threshold data
        """
        utilizations: list[AssetUtilization] = []

        # Try to get element RULs (which include thresholds) from RULCalculator
        rul_calc = self.rul_calculator
        element_ruls = {}

        if rul_calc is not None:
            try:
                rul_result = await rul_calc.predict_equipment_rul(equipment_id)
                for erul in rul_result.element_ruls:
                    element_ruls[erul.element_name] = erul
            except Exception as e:
                logger.debug(f"Could not get RUL for {equipment_id}: {e}")

        # Get trend summary for current values
        try:
            summary = await self.trend_service.get_equipment_trend_summary(equipment_id)
            eq_type = equipment_type or summary.equipment_type

            for trend in summary.element_trends:
                # Get current value from latest data point
                current_value = None
                unit = ""
                if trend.data_points:
                    current_value = trend.data_points[-1].value
                    unit = trend.data_points[-1].unit

                # Get threshold from RUL calculator or use defaults
                threshold_value = self._get_threshold(trend.element_name, element_ruls, unit)

                if threshold_value is None or threshold_value == 0:
                    continue  # Skip elements without thresholds

                # Calculate utilization
                utilization_pct = self._calculate_utilization_percent(
                    current_value, threshold_value, trend.element_name
                )

                # Determine status
                status = self._classify_utilization_status(utilization_pct)

                remaining_pct = max(0.0, min(100.0, 100.0 - utilization_pct))

                utilizations.append(
                    AssetUtilization(
                        equipment_id=equipment_id,
                        equipment_type=eq_type,
                        element_name=trend.element_name,
                        current_value=current_value,
                        threshold_value=threshold_value,
                        unit=unit,
                        utilization_percent=round(utilization_pct, 1),
                        remaining_percent=round(remaining_pct, 1),
                        status=status,
                    )
                )

        except Exception as e:
            logger.warning(f"Could not calculate utilization for {equipment_id}: {e}")

        return utilizations

    def _get_threshold(self, element_name: str, element_ruls: dict, unit: str) -> float | None:
        """Get threshold value from RUL data or defaults."""
        # First try RUL calculator thresholds
        if element_name in element_ruls:
            return element_ruls[element_name].threshold_value

        # Fallback: default thresholds by measurement type
        return self._default_threshold(element_name, unit)

    @staticmethod
    def _default_threshold(element_name: str, unit: str) -> float | None:
        """Provide sensible default thresholds for common elements."""
        name_lower = element_name.lower()
        unit_lower = unit.lower().strip()

        # Vibration thresholds
        if "vibration" in name_lower or unit_lower in ("mm/s",):
            return 4.5  # ISO 10816 alarm level for general machinery

        # Temperature thresholds
        if "temp" in name_lower:
            if "bearing" in name_lower:
                return 85.0  # Bearing temperature alarm
            if "discharge" in name_lower:
                return 95.0  # Compressor discharge alarm
            if "coolant" in name_lower:
                return 100.0  # Engine coolant alarm
            return 90.0  # General temperature alarm

        # Pressure thresholds
        if "pressure" in name_lower:
            if "filter" in name_lower or "dp" in name_lower:
                return 250.0  # Filter differential pressure alarm (Pa)
            if "suction" in name_lower:
                return 6.0  # Refrigerant suction pressure alarm (bar)
            if "discharge" in name_lower:
                return 20.0  # Refrigerant discharge pressure alarm (bar)
            return 10.0  # General pressure alarm

        # Current thresholds
        if "current" in name_lower or unit_lower in ("a",):
            return 180.0  # Motor overcurrent alarm

        # Sound/noise thresholds
        if "noise" in name_lower or "sound" in name_lower or unit_lower in ("dba", "db"):
            return 95.0  # Noise alarm level

        return None

    @staticmethod
    def _calculate_utilization_percent(current_value: float | None, threshold_value: float, element_name: str) -> float:
        """
        Calculate utilization percentage.

        For most elements (vibration, temperature): higher = worse
        For inverted elements (efficiency, capacity): lower = worse
        """
        if current_value is None or threshold_value == 0:
            return 0.0

        name_lower = element_name.lower()
        is_inverted = any(inv in name_lower for inv in INVERTED_ELEMENTS)

        if is_inverted:
            # For inverted: utilization = how much capacity lost
            # If current is 80 and threshold is 50, utilization is low (still good)
            if current_value >= threshold_value:
                ratio = 1.0 - (current_value - threshold_value) / max(current_value, 1.0)
            else:
                ratio = 1.0  # Below threshold = fully consumed
            pct = ratio * 100.0
        else:
            # Standard: utilization = current / threshold
            pct = (abs(current_value) / abs(threshold_value)) * 100.0

        return max(0.0, min(100.0, pct))

    @staticmethod
    def _classify_utilization_status(utilization_percent: float) -> UtilizationStatus:
        """Classify utilization status based on percentage."""
        if utilization_percent > 85.0:
            return UtilizationStatus.END_OF_LIFE
        elif utilization_percent > 60.0:
            return UtilizationStatus.AGING
        else:
            return UtilizationStatus.HEALTHY

    # ========================================================================
    # Service Window Optimization
    # ========================================================================

    async def optimize_service_window(self, equipment_id: str) -> ServiceWindow | None:
        """
        Calculate optimal service window for equipment.

        Logic:
        - Get RUL from RULCalculator (or estimate from trends)
        - If no degrading elements: no service needed, return None
        - Optimal date = now + (days_until_first_threshold * 0.7)
        - Earliest = now + (days_until_first_threshold * 0.5)
        - Latest = now + (days_until_first_threshold * 0.9)
        - Cost impact: <30 days = high, 30-90 = medium, >90 = low

        Args:
            equipment_id: Equipment identifier

        Returns:
            ServiceWindow or None if no service needed
        """
        now = datetime.now()
        days_until_threshold = None
        driving_elements: list[str] = []
        reason_parts: list[str] = []

        # Try RUL calculator first
        rul_calc = self.rul_calculator
        if rul_calc is not None:
            try:
                rul_result = await rul_calc.predict_equipment_rul(equipment_id)
                if rul_result.days_until_first_threshold is not None:
                    days_until_threshold = rul_result.days_until_first_threshold
                    if rul_result.worst_element_name:
                        driving_elements.append(rul_result.worst_element_name)
                    # Collect all degrading elements
                    for erul in rul_result.element_ruls:
                        if erul.days_until_threshold is not None and erul.element_name not in driving_elements:
                            driving_elements.append(erul.element_name)
                    reason_parts.append(f"RUL prediction: {rul_result.message or 'degradation detected'}")
            except Exception as e:
                logger.debug(f"RUL calculator not available for {equipment_id}: {e}")

        # Fallback: estimate from trend data
        if days_until_threshold is None:
            days_until_threshold, driving_elements, reason_parts = await self._estimate_from_trends(equipment_id)

        # No degrading elements = no service needed
        if days_until_threshold is None:
            return None

        # Ensure minimum threshold (at least 1 day)
        days_until_threshold = max(1.0, days_until_threshold)

        # Calculate service window dates
        optimal_days = days_until_threshold * 0.7
        earliest_days = days_until_threshold * 0.5
        latest_days = days_until_threshold * 0.9

        optimal_date = (now + timedelta(days=optimal_days)).strftime("%Y-%m-%d")
        earliest_date = (now + timedelta(days=earliest_days)).strftime("%Y-%m-%d")
        latest_date = (now + timedelta(days=latest_days)).strftime("%Y-%m-%d")

        # Cost impact based on urgency
        if optimal_days < 30:
            cost_impact = "high"
        elif optimal_days < 90:
            cost_impact = "medium"
        else:
            cost_impact = "low"

        reason = "; ".join(reason_parts) if reason_parts else "Degradation detected in monitored elements"

        return ServiceWindow(
            equipment_id=equipment_id,
            optimal_date=optimal_date,
            earliest_date=earliest_date,
            latest_date=latest_date,
            reason=reason,
            elements_driving=driving_elements,
            cost_impact=cost_impact,
        )

    async def _estimate_from_trends(self, equipment_id: str) -> tuple:
        """
        Estimate days until threshold from trend data (fallback when RUL calculator unavailable).

        Returns:
            (days_until_threshold, driving_elements, reason_parts)
        """
        driving_elements: list[str] = []
        reason_parts: list[str] = []
        min_days = None

        try:
            summary = await self.trend_service.get_equipment_trend_summary(equipment_id)

            for trend in summary.element_trends:
                if trend.trend_direction not in (TrendDirection.DEGRADING, TrendDirection.RAPID_DEGRADING):
                    continue

                if trend.degradation_rate_per_day is None or trend.degradation_rate_per_day <= 0:
                    continue

                # Get current value and threshold
                if not trend.data_points:
                    continue

                current_val = trend.data_points[-1].value
                unit = trend.data_points[-1].unit
                threshold = self._default_threshold(trend.element_name, unit)

                if threshold is None:
                    continue

                remaining = abs(threshold - current_val)
                if remaining <= 0:
                    # Already at or past threshold
                    days_est = 1.0
                else:
                    days_est = remaining / abs(trend.degradation_rate_per_day)

                driving_elements.append(trend.element_name)
                reason_parts.append(
                    f"{trend.element_name}: {trend.trend_direction.value}, ~{int(days_est)} days to threshold"
                )

                if min_days is None or days_est < min_days:
                    min_days = days_est

        except Exception as e:
            logger.warning(f"Could not estimate from trends for {equipment_id}: {e}")

        return min_days, driving_elements, reason_parts

    # ========================================================================
    # Maintenance Cost Comparison
    # ========================================================================

    async def compare_maintenance_costs(
        self, equipment_id: str, equipment_type: str | None = None, fixed_interval_days: int = 90
    ) -> MaintenanceCostComparison:
        """
        Compare fixed-schedule vs condition-based maintenance costs.

        Fixed schedule: 365 / fixed_interval_days services per year
        Conditional: based on actual degradation rates
          - If stable: 1 service/year (annual check)
          - If slow degrading: 365 / days_until_threshold services/year
          - If rapid: may need more than fixed schedule

        Cost estimates use base rates per equipment type (ZAR).

        Args:
            equipment_id: Equipment identifier
            equipment_type: Optional type hint
            fixed_interval_days: Days between fixed services (default 90 = quarterly)

        Returns:
            MaintenanceCostComparison with savings analysis
        """
        # Determine equipment type
        eq_type = equipment_type
        if eq_type is None:
            try:
                summary = await self.trend_service.get_equipment_trend_summary(equipment_id)
                eq_type = summary.equipment_type
            except Exception:
                pass

        # Get service cost rate
        cost_per_service = SERVICE_COST_RATES.get((eq_type or "").lower(), DEFAULT_SERVICE_COST)

        # Fixed schedule calculation
        fixed_services_per_year = int(365 / fixed_interval_days)
        fixed_annual_cost = fixed_services_per_year * cost_per_service

        # Conditional schedule calculation
        conditional_services = await self._estimate_conditional_services(equipment_id, fixed_interval_days)
        conditional_annual_cost = conditional_services * cost_per_service

        # Calculate savings
        if fixed_annual_cost > 0:
            savings_pct = ((fixed_annual_cost - conditional_annual_cost) / fixed_annual_cost) * 100.0
        else:
            savings_pct = 0.0

        # Generate recommendation
        recommendation = self._generate_cost_recommendation(savings_pct, conditional_services, fixed_services_per_year)

        return MaintenanceCostComparison(
            equipment_id=equipment_id,
            equipment_type=eq_type,
            fixed_schedule_services_per_year=fixed_services_per_year,
            conditional_services_per_year=round(conditional_services, 1),
            fixed_annual_cost_estimate=round(fixed_annual_cost, 2),
            conditional_annual_cost_estimate=round(conditional_annual_cost, 2),
            savings_percent=round(savings_pct, 1),
            recommendation=recommendation,
        )

    async def _estimate_conditional_services(self, equipment_id: str, fixed_interval_days: int) -> float:
        """
        Estimate number of services per year based on actual condition.

        Logic:
        - All stable: 1 service/year (annual check)
        - Slow degrading: 365 / days_until_threshold
        - Rapid degrading: may exceed fixed schedule frequency
        """
        # Try RUL calculator first
        rul_calc = self.rul_calculator
        if rul_calc is not None:
            try:
                rul_result = await rul_calc.predict_equipment_rul(equipment_id)
                if rul_result.days_until_first_threshold is not None:
                    days = max(30.0, rul_result.days_until_first_threshold)
                    return 365.0 / days
                # No degrading elements
                return 1.0
            except Exception:
                pass

        # Fallback: estimate from trends
        try:
            summary = await self.trend_service.get_equipment_trend_summary(equipment_id)

            has_degrading = False
            min_days = None

            for trend in summary.element_trends:
                if trend.trend_direction in (TrendDirection.DEGRADING, TrendDirection.RAPID_DEGRADING):
                    has_degrading = True

                    if trend.degradation_rate_per_day and trend.degradation_rate_per_day > 0:
                        # Estimate days to threshold
                        if trend.data_points:
                            current_val = trend.data_points[-1].value
                            unit = trend.data_points[-1].unit
                            threshold = self._default_threshold(trend.element_name, unit)
                            if threshold is not None:
                                remaining = abs(threshold - current_val)
                                days_est = remaining / abs(trend.degradation_rate_per_day)
                                days_est = max(30.0, days_est)  # Min 30 days between services
                                if min_days is None or days_est < min_days:
                                    min_days = days_est

            if not has_degrading:
                return 1.0  # Annual check only

            if min_days is not None:
                return 365.0 / min_days

            # Degrading but can't estimate rate: assume twice per year
            return 2.0

        except Exception as e:
            logger.warning(f"Could not estimate conditional services for {equipment_id}: {e}")
            return 2.0  # Conservative default

    @staticmethod
    def _generate_cost_recommendation(savings_pct: float, conditional_services: float, fixed_services: int) -> str:
        """Generate human-readable cost recommendation."""
        if savings_pct > 40:
            return (
                f"Condition-based maintenance saves {savings_pct:.0f}% annually. "
                f"Equipment condition is stable, requiring ~{conditional_services:.1f} "
                f"services/year vs {fixed_services} on fixed schedule. "
                f"Strong recommendation to adopt condition-based approach."
            )
        elif savings_pct > 15:
            return (
                f"Condition-based maintenance saves {savings_pct:.0f}% annually. "
                f"Equipment shows moderate degradation needing ~{conditional_services:.1f} "
                f"services/year. Recommend transitioning to condition-based scheduling."
            )
        elif savings_pct > 0:
            return (
                f"Condition-based maintenance saves {savings_pct:.0f}% annually. "
                f"Marginal savings suggest equipment condition warrants close monitoring. "
                f"Consider hybrid approach with condition checks between fixed services."
            )
        elif savings_pct > -10:
            return (
                "Fixed and condition-based approaches are similar in cost. "
                "Equipment degradation rate aligns with fixed schedule interval. "
                "Either approach acceptable; condition-based adds early warning benefit."
            )
        else:
            return (
                f"Equipment requires more frequent service ({conditional_services:.1f}/year) "
                f"than fixed schedule ({fixed_services}/year). "
                f"Increase fixed frequency or address root cause of rapid degradation."
            )

    # ========================================================================
    # Fleet Schedule Optimization
    # ========================================================================

    async def optimize_fleet_schedule(
        self, equipment_ids: list[str] | None = None, fixed_interval_days: int = 90, limit: int = 20
    ) -> OptimizedSchedule:
        """
        Optimize service schedule across multiple equipment.

        If no IDs provided, enumerate from sites data.
        Gets service windows for all equipment, sorts by optimal_date,
        and generates cost comparison summary.

        Args:
            equipment_ids: List of equipment IDs (None = discover from sites)
            fixed_interval_days: Fixed interval for cost comparison
            limit: Maximum equipment to process

        Returns:
            OptimizedSchedule with sorted service windows and cost summary
        """
        # Discover equipment if not provided
        if equipment_ids is None or len(equipment_ids) == 0:
            equipment_ids = await self._discover_equipment(limit)

        equipment_ids = equipment_ids[:limit]

        # Collect service windows
        schedule: list[ServiceWindow] = []
        total_fixed_cost = 0.0
        total_conditional_cost = 0.0
        equipment_with_cost = 0

        for eq_id in equipment_ids:
            try:
                window = await self.optimize_service_window(eq_id)
                if window is not None:
                    schedule.append(window)
            except Exception as e:
                logger.debug(f"Could not optimize window for {eq_id}: {e}")

            # Collect cost data for summary
            try:
                cost = await self.compare_maintenance_costs(eq_id, fixed_interval_days=fixed_interval_days)
                total_fixed_cost += cost.fixed_annual_cost_estimate
                total_conditional_cost += cost.conditional_annual_cost_estimate
                equipment_with_cost += 1
            except Exception as e:
                logger.debug(f"Could not compare costs for {eq_id}: {e}")

        # Sort by optimal date
        schedule.sort(key=lambda w: w.optimal_date)

        # Cost comparison summary
        if total_fixed_cost > 0 and equipment_with_cost > 0:
            savings = total_fixed_cost - total_conditional_cost
            savings_pct = (savings / total_fixed_cost) * 100.0
            cost_summary = (
                f"Fleet analysis ({equipment_with_cost} equipment): "
                f"Fixed schedule R {total_fixed_cost:,.0f}/year vs "
                f"condition-based R {total_conditional_cost:,.0f}/year. "
                f"Projected savings: R {savings:,.0f}/year ({savings_pct:.0f}%)."
            )
        else:
            cost_summary = (
                f"Fleet analysis: {len(equipment_ids)} equipment analyzed. "
                f"No cost data available yet. Submit inspection data to enable cost comparison."
            )

        return OptimizedSchedule(
            equipment_ids=equipment_ids,
            schedule=schedule,
            total_equipment=len(equipment_ids),
            equipment_needing_service=len(schedule),
            cost_comparison_summary=cost_summary,
        )

    async def _discover_equipment(self, limit: int = 20) -> list[str]:
        """Discover equipment IDs from sites data."""
        equipment_ids: list[str] = []

        try:
            import json
            import os

            # Read buildings registry
            registry_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "sites", "_registry.json")

            if os.path.exists(registry_path):
                with open(registry_path) as f:
                    registry = json.load(f)

                for site_id in registry.get("active_sites", []):
                    site_path = os.path.join(os.path.dirname(registry_path), f"{site_id}.json")
                    if os.path.exists(site_path):
                        with open(site_path) as f:
                            site_data = json.load(f)

                        # Extract equipment IDs from site data
                        for eq in site_data.get("equipment", []):
                            eq_id = eq.get("equipment_id") or eq.get("id")
                            if eq_id:
                                equipment_ids.append(eq_id)

            if not equipment_ids:
                logger.info("No equipment IDs discovered — reference_devices.json fallback removed (2026-06)")

        except Exception as e:
            logger.warning(f"Could not discover equipment: {e}")

        return equipment_ids[:limit]


# ============================================================================
# Singleton Instance
# ============================================================================

_service_optimizer: ServiceOptimizer | None = None


def get_service_optimizer() -> ServiceOptimizer:
    """Get singleton ServiceOptimizer instance."""
    global _service_optimizer
    if _service_optimizer is None:
        _service_optimizer = ServiceOptimizer()
    return _service_optimizer
