"""
Element Trend Service (Phase 56-01)

Aggregates inspection measurement data over time per equipment element,
calculates degradation rates using linear regression, and detects
trending patterns (stable, degrading, rapid_degrading, improving).

This is the data foundation for RUL prediction and service optimization.

Uses numpy-free manual least squares for degradation rate calculation.
"""

import logging
from datetime import datetime, timedelta

from app.models.condition import (
    DegradationRate,
    ElementTrend,
    ElementTrendPoint,
    EquipmentTrendSummary,
    TrendDirection,
    TrendSource,
)

logger = logging.getLogger(__name__)


class ElementTrendService:
    """
    Service for element-level trend analysis from inspection data.

    Provides:
    - Historical measurement retrieval from inspection records
    - Degradation rate calculation (manual linear regression)
    - Trend direction classification
    - Equipment-level trend summaries with condition scoring
    """

    def __init__(self):
        """Initialize service with lazy repository access."""
        self._inspection_repo = None
        self._baseline_repo = None

    @property
    def inspection_repo(self):
        """Lazy-load inspection repository."""
        if self._inspection_repo is None:
            from app.database.repositories.inspection_repository import InspectionRepository

            self._inspection_repo = InspectionRepository()
        return self._inspection_repo

    @property
    def baseline_repo(self):
        """Lazy-load baseline repository."""
        if self._baseline_repo is None:
            from app.database.repositories.baseline_repository import BaselineRepository

            self._baseline_repo = BaselineRepository()
        return self._baseline_repo

    # ========================================================================
    # Element History
    # ========================================================================

    async def get_element_history(
        self, equipment_id: str, element_name: str, days: int = 90
    ) -> list[ElementTrendPoint]:
        """
        Get historical measurement data for an equipment element.

        Aggregates data from:
        1. Inspection measurements (InspectionRepository)
        2. Baseline comparison deviations (BaselineRepository)

        Args:
            equipment_id: Equipment identifier
            element_name: Element/measurement point name
            days: Number of days of history to retrieve

        Returns:
            List of ElementTrendPoint sorted by timestamp, deduplicated
        """
        points: list[ElementTrendPoint] = []
        cutoff = datetime.now() - timedelta(days=days)

        # 1. Query inspection measurements
        try:
            measurements = await self.inspection_repo.get_measurements_by_equipment(
                equipment_id=equipment_id,
                measurement_type=None,  # All types
                limit=500,
            )

            for m in measurements:
                # Filter by element name (measurement_point matches element_name)
                if m.measurement_point != element_name:
                    continue
                if m.measurement_date < cutoff:
                    continue

                points.append(
                    ElementTrendPoint(
                        timestamp=m.measurement_date,
                        value=m.measured_value,
                        unit=m.unit,
                        deviation_percent=m.baseline_deviation_percent or 0.0,
                        source=TrendSource.INSPECTION,
                    )
                )

            logger.debug(
                f"Found {len(points)} inspection measurements for {equipment_id}/{element_name} in last {days} days"
            )
        except Exception as e:
            logger.warning(f"Could not query inspection measurements: {e}")

        # 2. Query baseline comparison deviations
        try:
            comparisons = await self.baseline_repo.get_recent_comparisons(equipment_id=equipment_id, limit=50)

            for comp in comparisons:
                if comp.comparison_date < cutoff:
                    continue

                # Extract the specific element from comparison_results
                results = comp.comparison_results
                if isinstance(results, dict) and element_name in results:
                    result_data = results[element_name]
                    if isinstance(result_data, dict):
                        current_val = result_data.get("current")
                        deviation = result_data.get("deviation_percent", 0)
                        if current_val is not None:
                            points.append(
                                ElementTrendPoint(
                                    timestamp=comp.comparison_date,
                                    value=float(current_val),
                                    unit="",  # Unit not always stored in comparisons
                                    deviation_percent=float(deviation),
                                    source=TrendSource.BASELINE,
                                )
                            )

            logger.debug(f"Found {len(points)} total data points (incl. baseline) for {equipment_id}/{element_name}")
        except Exception as e:
            logger.warning(f"Could not query baseline comparisons: {e}")

        # 3. Sort by timestamp, deduplicate (same timestamp & source)
        points.sort(key=lambda p: p.timestamp)
        points = self._deduplicate_points(points)

        return points

    def _deduplicate_points(self, points: list[ElementTrendPoint]) -> list[ElementTrendPoint]:
        """Remove duplicate data points (same timestamp to the minute)."""
        seen = set()
        unique = []
        for p in points:
            # Key: timestamp rounded to minute + source
            key = (p.timestamp.replace(second=0, microsecond=0), p.source)
            if key not in seen:
                seen.add(key)
                unique.append(p)
        return unique

    # ========================================================================
    # Degradation Rate Calculation
    # ========================================================================

    def calculate_degradation_rate(self, data_points: list[ElementTrendPoint]) -> DegradationRate:
        """
        Calculate degradation rate using manual linear regression.

        Uses numpy-free least squares:
        slope = (n * sum(xy) - sum(x) * sum(y)) / (n * sum(x^2) - sum(x)^2)

        R-squared = 1 - (SS_res / SS_tot)

        Args:
            data_points: List of measurement points (must have >= 2 points)

        Returns:
            DegradationRate with rate_per_day, rate_per_month, and confidence
        """
        n = len(data_points)
        unit = data_points[0].unit if data_points else ""
        element_name = ""

        if n < 2:
            return DegradationRate(
                element_name=element_name, rate_per_day=0.0, rate_per_month=0.0, unit=unit, confidence=0.0
            )

        # Convert timestamps to days from first point
        t0 = data_points[0].timestamp
        x_values = [(p.timestamp - t0).total_seconds() / 86400.0 for p in data_points]
        y_values = [p.value for p in data_points]

        # Manual least squares regression
        sum_x = sum(x_values)
        sum_y = sum(y_values)
        sum_xy = sum(x * y for x, y in zip(x_values, y_values, strict=False))
        sum_x2 = sum(x * x for x in x_values)

        mean_x = sum_x / n
        mean_y = sum_y / n

        denominator = sum_x2 - n * mean_x * mean_x

        if abs(denominator) < 1e-10:
            # All x values are the same (measurements at same time)
            return DegradationRate(
                element_name=element_name, rate_per_day=0.0, rate_per_month=0.0, unit=unit, confidence=0.0
            )

        slope = (sum_xy - n * mean_x * mean_y) / denominator

        # Calculate R-squared
        # SS_tot = sum((y - mean_y)^2)
        ss_tot = sum((y - mean_y) ** 2 for y in y_values)
        # SS_res = sum((y - predicted_y)^2)
        intercept = mean_y - slope * mean_x
        ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(x_values, y_values, strict=False))

        r_squared = max(0.0, 1.0 - ss_res / ss_tot) if ss_tot > 0 else 0.0

        # Confidence is based on R-squared and number of data points
        # More data points and better fit = higher confidence
        data_factor = min(1.0, n / 10.0)  # Max confidence at 10+ points
        confidence = r_squared * data_factor

        rate_per_day = slope
        rate_per_month = slope * 30.0

        return DegradationRate(
            element_name=element_name,
            rate_per_day=round(rate_per_day, 6),
            rate_per_month=round(rate_per_month, 4),
            unit=unit,
            confidence=round(confidence, 3),
        )

    # ========================================================================
    # Trend Classification
    # ========================================================================

    def classify_trend(self, degradation_rate: DegradationRate, tolerance: float = 10.0) -> TrendDirection:
        """
        Classify the trend direction based on degradation rate.

        For most measurements (vibration, temperature), increasing values mean degradation.
        For efficiency metrics, decreasing values mean degradation.

        Thresholds (based on tolerance percentage):
        - Stable: abs(rate) < tolerance * 0.01 / 30 per day
        - Rapid degrading: rate > tolerance * 0.05 / 30 per day
        - Degrading: rate > stable threshold
        - Improving: rate < -stable threshold (negative = decreasing)

        Args:
            degradation_rate: Calculated degradation rate
            tolerance: Baseline tolerance percentage (default 10%)

        Returns:
            TrendDirection enum value
        """
        rate = degradation_rate.rate_per_day

        # Threshold calculations (per day)
        stable_threshold = tolerance * 0.01 / 30.0  # Very small daily change
        rapid_threshold = tolerance * 0.05 / 30.0  # 5x the stable threshold

        if abs(rate) < stable_threshold:
            return TrendDirection.STABLE

        if rate > rapid_threshold:
            return TrendDirection.RAPID_DEGRADING

        if rate > stable_threshold:
            return TrendDirection.DEGRADING

        if rate < -stable_threshold:
            return TrendDirection.IMPROVING

        return TrendDirection.STABLE

    # ========================================================================
    # Equipment Trend Summary
    # ========================================================================

    async def get_equipment_trend_summary(self, equipment_id: str, days: int = 90) -> EquipmentTrendSummary:
        """
        Get comprehensive trend analysis for all elements of an equipment.

        Steps:
        1. Get all unique elements from inspection history
        2. Calculate trend for each element
        3. Identify worst degrading element
        4. Compute overall condition from element trends

        Args:
            equipment_id: Equipment identifier
            days: History window in days

        Returns:
            EquipmentTrendSummary with all element trends and overall assessment
        """
        logger.info(f"Calculating trend summary for {equipment_id} (last {days} days)")

        # 1. Discover unique elements from inspection measurements
        element_names = await self._discover_elements(equipment_id, days)

        if not element_names:
            logger.info(f"No inspection data found for {equipment_id}")
            return EquipmentTrendSummary(
                equipment_id=equipment_id,
                element_trends=[],
                overall_trend_direction=TrendDirection.STABLE,
                condition_score=100.0,
                message="No inspection data available for trend analysis",
            )

        # 2. Calculate trend for each element
        element_trends: list[ElementTrend] = []
        for element_name, measurement_type in element_names.items():
            points = await self.get_element_history(equipment_id, element_name, days)

            if len(points) < 2:
                # Not enough data for trend calculation
                trend = ElementTrend(
                    element_name=element_name,
                    equipment_id=equipment_id,
                    measurement_type=measurement_type,
                    data_points=points,
                    degradation_rate_per_day=None,
                    trend_direction=TrendDirection.STABLE,
                    r_squared=None,
                    days_of_data=0,
                )
            else:
                rate = self.calculate_degradation_rate(points)
                rate.element_name = element_name

                direction = self.classify_trend(rate)

                days_span = (points[-1].timestamp - points[0].timestamp).total_seconds() / 86400.0

                trend = ElementTrend(
                    element_name=element_name,
                    equipment_id=equipment_id,
                    measurement_type=measurement_type,
                    data_points=points,
                    degradation_rate_per_day=rate.rate_per_day,
                    trend_direction=direction,
                    r_squared=rate.confidence,
                    days_of_data=int(days_span),
                )

            element_trends.append(trend)

        # 3. Identify worst degrading element
        worst_element = self._find_worst_element(element_trends)

        # 4. Compute overall condition
        overall_direction = self._compute_overall_direction(element_trends)
        condition_score = self._compute_condition_score(element_trends)

        # Build summary message
        degrading_count = sum(
            1 for t in element_trends if t.trend_direction in (TrendDirection.DEGRADING, TrendDirection.RAPID_DEGRADING)
        )
        message = self._build_summary_message(element_trends, degrading_count, worst_element)

        return EquipmentTrendSummary(
            equipment_id=equipment_id,
            element_trends=element_trends,
            worst_element=worst_element,
            overall_trend_direction=overall_direction,
            condition_score=condition_score,
            message=message,
        )

    async def _discover_elements(self, equipment_id: str, days: int) -> dict[str, str]:
        """
        Discover unique element names and their measurement types
        from inspection history.

        Returns:
            Dict mapping element_name -> measurement_type
        """
        elements: dict[str, str] = {}

        try:
            measurements = await self.inspection_repo.get_measurements_by_equipment(
                equipment_id=equipment_id, limit=500
            )

            cutoff = datetime.now() - timedelta(days=days)
            for m in measurements:
                if m.measurement_date < cutoff:
                    continue
                if m.measurement_point not in elements:
                    elements[m.measurement_point] = m.measurement_type

        except Exception as e:
            logger.warning(f"Could not discover elements for {equipment_id}: {e}")

        return elements

    def _find_worst_element(self, trends: list[ElementTrend]) -> str | None:
        """Find the element with the worst degradation rate."""
        worst = None
        worst_rate = 0.0

        for trend in trends:
            if trend.degradation_rate_per_day is not None:
                rate = abs(trend.degradation_rate_per_day)
                if trend.trend_direction in (TrendDirection.DEGRADING, TrendDirection.RAPID_DEGRADING):
                    if rate > worst_rate:
                        worst_rate = rate
                        worst = trend.element_name

        return worst

    def _compute_overall_direction(self, trends: list[ElementTrend]) -> TrendDirection:
        """
        Compute overall equipment trend from element trends.

        Rules:
        - Any rapid_degrading -> rapid_degrading
        - Multiple degrading -> degrading
        - All stable -> stable
        - All improving -> improving
        """
        directions = [t.trend_direction for t in trends if t.trend_direction is not None]

        if not directions:
            return TrendDirection.STABLE

        if TrendDirection.RAPID_DEGRADING in directions:
            return TrendDirection.RAPID_DEGRADING

        degrading_count = directions.count(TrendDirection.DEGRADING)
        improving_count = directions.count(TrendDirection.IMPROVING)

        if degrading_count > 0:
            return TrendDirection.DEGRADING

        if improving_count > 0 and degrading_count == 0:
            return TrendDirection.IMPROVING

        return TrendDirection.STABLE

    def _compute_condition_score(self, trends: list[ElementTrend]) -> float:
        """
        Compute overall condition score (0-100) from element trends.

        Scoring:
        - Stable elements: 100 points each
        - Improving: 100 points
        - Degrading: 60 points
        - Rapid degrading: 30 points
        - Average across all elements
        """
        if not trends:
            return 100.0

        direction_scores = {
            TrendDirection.IMPROVING: 100.0,
            TrendDirection.STABLE: 100.0,
            TrendDirection.DEGRADING: 60.0,
            TrendDirection.RAPID_DEGRADING: 30.0,
        }

        scores = [direction_scores.get(t.trend_direction, 100.0) for t in trends]

        return round(sum(scores) / len(scores), 1)

    def _build_summary_message(
        self, trends: list[ElementTrend], degrading_count: int, worst_element: str | None
    ) -> str:
        """Build human-readable summary message."""
        total = len(trends)

        if degrading_count == 0:
            return f"All {total} monitored elements are stable or improving."

        if worst_element:
            rapid = sum(1 for t in trends if t.trend_direction == TrendDirection.RAPID_DEGRADING)
            if rapid > 0:
                return (
                    f"{degrading_count} of {total} elements degrading "
                    f"({rapid} rapidly). Worst: {worst_element}. "
                    f"Immediate attention recommended."
                )
            return f"{degrading_count} of {total} elements degrading. Worst: {worst_element}. Monitor closely."

        return f"{degrading_count} of {total} elements showing degradation."


# ============================================================================
# Singleton Instance
# ============================================================================

_trend_service: ElementTrendService | None = None


def get_element_trend_service() -> ElementTrendService:
    """Get singleton ElementTrendService instance."""
    global _trend_service
    if _trend_service is None:
        _trend_service = ElementTrendService()
    return _trend_service
