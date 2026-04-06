"""
Health Feature Provider — extracts health features for recommendation ranking.

Phase 109B-03: Recommendation Pipeline Health Feature Payload

Computes a HealthFeaturePayload from health snapshots and baseline data.
This service is a READ-ONLY consumer of health data. It never writes
risk probabilities or failure predictions.

HARD RULES:
  - NEVER imports prediction_generator or prediction_calculator
  - NEVER writes to the predictions table
  - NEVER produces risk probability values
  - Output is HealthFeaturePayload (health-only, separate from risk)
"""

import logging
import math

from app.models.health_rating import HealthFeaturePayload, HealthRating

logger = logging.getLogger(__name__)


class HealthFeatureProvider:
    """Provides health feature payloads for recommendation enrichment.

    Reads from HealthSnapshotService and HealthRatingCalculator to produce
    a 7-field HealthFeaturePayload that recommendation ranking can consume
    alongside (but separate from) risk prediction signals.
    """

    def __init__(self):
        """Initialize with lazy service references."""
        self._snapshot_service = None
        self._calculator = None

    def _get_snapshot_service(self):
        """Lazy-load HealthSnapshotService."""
        if self._snapshot_service is None:
            from app.services.health_snapshot_service import HealthSnapshotService

            self._snapshot_service = HealthSnapshotService()
        return self._snapshot_service

    def _get_calculator(self):
        """Lazy-load HealthRatingCalculator."""
        if self._calculator is None:
            from app.services.health_rating_calculator import HealthRatingCalculator

            self._calculator = HealthRatingCalculator()
        return self._calculator

    async def get_health_features(self, equipment_id: str) -> HealthFeaturePayload:
        """Compute health features for a single equipment item.

        Retrieves the latest health snapshot and computes trend slopes,
        volatility, and baseline deviation from historical data.

        Args:
            equipment_id: Equipment code or UUID.

        Returns:
            HealthFeaturePayload with all 7 health fields populated.
        """
        snapshot_service = self._get_snapshot_service()

        # 1. Get latest rating
        latest_rating = await snapshot_service.get_latest(equipment_id)

        if latest_rating is None:
            # No snapshot exists — compute a fresh rating
            latest_rating = await self._compute_fresh_rating(equipment_id)

        if latest_rating is None:
            # Still nothing — return a degraded payload
            return self._degraded_payload()

        # 2. Calculate trend slopes from history
        trend_7d = await self._calculate_trend_slope(equipment_id, days=7)
        trend_30d = await self._calculate_trend_slope(equipment_id, days=30)

        # 3. Calculate volatility (stddev of daily avg scores over 30d)
        volatility = await self._calculate_volatility(equipment_id, days=30)

        # 4. Get baseline deviation
        baseline_deviation = self._extract_baseline_deviation(latest_rating)

        return HealthFeaturePayload(
            health_score_current=latest_rating.health_score,
            health_status_current=latest_rating.health_status,
            health_trend_7d_slope=trend_7d,
            health_trend_30d_slope=trend_30d,
            health_volatility_30d=volatility,
            health_confidence=latest_rating.confidence,
            baseline_deviation_max_24h=baseline_deviation,
        )

    async def _compute_fresh_rating(self, equipment_id: str) -> HealthRating | None:
        """Attempt to compute a fresh HealthRating when no snapshot exists."""
        try:
            calculator = self._get_calculator()
            equipment = {"id": equipment_id, "code": equipment_id}
            rating = await calculator.compute_rating(
                equipment_id=equipment_id,
                equipment=equipment,
                mode="simulation",
            )
            return rating
        except Exception as e:
            logger.debug(f"Could not compute fresh rating for {equipment_id}: {e}")
            return None

    async def _calculate_trend_slope(self, equipment_id: str, days: int) -> float | None:
        """Calculate health score trend slope over the given period.

        Uses linear regression on daily rollup average scores.
        Returns slope in points-per-day (negative = improving health).

        Args:
            equipment_id: Equipment code or UUID.
            days: Number of days to consider.

        Returns:
            Slope (float) or None if insufficient data.
        """
        snapshot_service = self._get_snapshot_service()
        try:
            rollups = await snapshot_service.get_daily_rollups(equipment_id, range_days=days)
            if len(rollups) < 2:
                return None

            # Extract (day_index, score_avg) pairs
            points = []
            for i, rollup in enumerate(reversed(rollups)):  # oldest first
                if rollup.score_avg is not None:
                    points.append((float(i), rollup.score_avg))

            if len(points) < 2:
                return None

            return self._linear_slope(points)
        except Exception as e:
            logger.debug(f"Could not calculate {days}d trend for {equipment_id}: {e}")
            return None

    async def _calculate_volatility(self, equipment_id: str, days: int) -> float | None:
        """Calculate health score volatility (stddev of daily avg scores).

        Args:
            equipment_id: Equipment code or UUID.
            days: Number of days to consider.

        Returns:
            Standard deviation of daily average scores, or None if insufficient data.
        """
        snapshot_service = self._get_snapshot_service()
        try:
            rollups = await snapshot_service.get_daily_rollups(equipment_id, range_days=days)
            scores = [r.score_avg for r in rollups if r.score_avg is not None]
            if len(scores) < 2:
                return None
            return self._stddev(scores)
        except Exception as e:
            logger.debug(f"Could not calculate volatility for {equipment_id}: {e}")
            return None

    @staticmethod
    def _extract_baseline_deviation(rating: HealthRating) -> float | None:
        """Extract baseline deviation from the rating's component data.

        The baseline_alignment_score is derived from deviation via:
            score = 100 - 2 * deviation_percent
        So: deviation_percent = (100 - score) / 2

        Args:
            rating: The latest HealthRating.

        Returns:
            Estimated max deviation percentage, or None.
        """
        if rating.components and rating.components.baseline_alignment_score is not None:
            score = rating.components.baseline_alignment_score
            if score == 50.0:
                # 50.0 is the neutral/unknown value (no baseline)
                return None
            return round((100 - score) / 2, 1)
        return None

    @staticmethod
    def _linear_slope(points: list[tuple]) -> float:
        """Simple linear regression slope from (x, y) pairs.

        Args:
            points: List of (x, y) tuples.

        Returns:
            Slope of the best-fit line.
        """
        n = len(points)
        sum_x = sum(p[0] for p in points)
        sum_y = sum(p[1] for p in points)
        sum_xy = sum(p[0] * p[1] for p in points)
        sum_x2 = sum(p[0] ** 2 for p in points)

        denom = n * sum_x2 - sum_x**2
        if abs(denom) < 1e-10:
            return 0.0

        slope = (n * sum_xy - sum_x * sum_y) / denom
        return round(slope, 4)

    @staticmethod
    def _stddev(values: list[float]) -> float:
        """Population standard deviation.

        Args:
            values: List of numeric values.

        Returns:
            Standard deviation, rounded to 2 decimal places.
        """
        n = len(values)
        if n == 0:
            return 0.0
        mean = sum(values) / n
        variance = sum((v - mean) ** 2 for v in values) / n
        return round(math.sqrt(variance), 2)

    @staticmethod
    def _degraded_payload() -> HealthFeaturePayload:
        """Return a degraded payload when no health data is available.

        Uses conservative defaults: score of 50 (unknown), low confidence.
        """
        return HealthFeaturePayload(
            health_score_current=50.0,
            health_status_current="warning",
            health_trend_7d_slope=None,
            health_trend_30d_slope=None,
            health_volatility_30d=None,
            health_confidence="low",
            baseline_deviation_max_24h=None,
        )
