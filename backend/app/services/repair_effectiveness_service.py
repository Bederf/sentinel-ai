"""
Repair Effectiveness Service (Phase 57-01)

Post-repair comparison, effectiveness scoring, and equipment health recalculation.
Closes the feedback loop by verifying whether repairs actually resolved equipment issues.

Connects pre-repair baselines to post-repair measurements to produce effectiveness scores.

Integration points:
- BaselineComparisonService: element-by-element comparison
- ElementTrendService: trend-based health scoring
- BaselineRepository: fetching pre/post repair baselines
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

from app.models.repair_effectiveness import (
    RepairOutcome,
    EffectivenessScore,
    ElementImprovement,
    HealthScoreUpdate,
    RepairHistoryEntry,
)

logger = logging.getLogger(__name__)


class RepairEffectivenessService:
    """
    Service for validating repair effectiveness and recalculating health scores.

    Features:
    - Pre/post repair baseline comparison
    - Effectiveness scoring (0-100)
    - Element-level improvement tracking
    - Equipment health score recalculation from element trends
    - Repair history and fleet-wide summary

    Uses in-memory storage for demo scope.
    """

    # Thresholds
    EFFECTIVENESS_SUCCESS_THRESHOLD = 50.0  # Minimum score for successful repair
    BASELINE_TOLERANCE = 15.0  # Percentage tolerance for back-to-baseline check

    def __init__(self):
        """Initialize service with in-memory storage."""
        self._repair_outcomes: Dict[str, RepairOutcome] = {}  # work_order_id -> RepairOutcome
        self._effectiveness_scores: Dict[str, EffectivenessScore] = {}  # work_order_id -> EffectivenessScore
        self._health_scores: Dict[str, float] = {}  # equipment_id -> latest health score

        logger.info("RepairEffectivenessService initialized")

    # ========================================================================
    # Core Methods
    # ========================================================================

    async def validate_repair(
        self, equipment_id: str, work_order_id: str, post_readings: Optional[Dict[str, float]] = None
    ) -> EffectivenessScore:
        """
        Validate repair effectiveness by comparing pre-repair baseline
        to post-repair readings.

        Steps:
        1. Fetch pre-repair baseline from baseline repository (baseline_type=PRE_REPAIR)
        2. If post_readings is None, simulate BMS readings (demo scope)
        3. Use BaselineComparisonService for element-by-element comparison
        4. Calculate effectiveness_score as average improvement, capped at 100
        5. Calculate health scores from element deviations
        6. Store EffectivenessScore in memory
        7. Return EffectivenessScore

        Args:
            equipment_id: Equipment identifier (v2.0 format)
            work_order_id: Work order reference
            post_readings: Optional post-repair readings dict

        Returns:
            EffectivenessScore with element-level details
        """
        logger.info(f"Validating repair effectiveness: {equipment_id}, WO {work_order_id}")

        # 1. Fetch pre-repair baseline
        pre_baseline = await self._get_pre_repair_baseline(equipment_id)
        pre_baseline_id = ""
        pre_values: Dict[str, float] = {}

        if pre_baseline:
            pre_baseline_id = pre_baseline.get("id", "")
            raw_values = pre_baseline.get("baseline_values", {})
            # Extract numeric values from baseline structure
            for key, val in raw_values.items():
                if isinstance(val, dict):
                    pre_values[key] = float(val.get("value", 0))
                elif isinstance(val, (int, float)):
                    pre_values[key] = float(val)
        else:
            logger.warning(f"No pre-repair baseline found for {equipment_id}, using defaults")
            # Demo fallback: generate synthetic pre-repair values
            pre_values = self._generate_demo_pre_values(equipment_id)

        # 2. Get post-repair readings
        if post_readings is None:
            # Demo scope: generate improved readings (simulating successful repair)
            post_readings = self._generate_demo_post_values(equipment_id, pre_values)

        # 3. Calculate element-by-element improvements
        element_improvements: Dict[str, ElementImprovement] = {}

        for element_name, pre_value in pre_values.items():
            post_value = post_readings.get(element_name)
            if post_value is None:
                continue

            # Baseline value (original healthy state) - approximate as midpoint
            # In production, this would come from the INITIAL baseline
            baseline_value = await self._get_original_baseline_value(equipment_id, element_name, pre_value)

            # Calculate improvement percentage
            if abs(pre_value - baseline_value) > 0.001:
                # How much of the deviation was recovered
                deviation_before = abs(pre_value - baseline_value)
                deviation_after = abs(post_value - baseline_value)
                improvement_pct = ((deviation_before - deviation_after) / deviation_before) * 100
            else:
                improvement_pct = 0.0

            # Clamp improvement to reasonable range
            improvement_pct = max(-100.0, min(100.0, improvement_pct))

            # Determine status
            if improvement_pct > 5.0:
                status = "improved"
            elif improvement_pct < -5.0:
                status = "worsened"
            else:
                status = "unchanged"

            # Check if back to baseline
            back_to_bl = False
            if baseline_value != 0:
                deviation_pct = abs(post_value - baseline_value) / abs(baseline_value) * 100
                back_to_bl = deviation_pct < self.BASELINE_TOLERANCE

            element_improvements[element_name] = ElementImprovement(
                element_name=element_name,
                pre_value=pre_value,
                post_value=post_value,
                baseline_value=baseline_value,
                improvement_percent=round(improvement_pct, 2),
                back_to_baseline=back_to_bl,
                status=status,
            )

        # 4. Calculate overall effectiveness score
        if element_improvements:
            improvements_list = [ei.improvement_percent for ei in element_improvements.values()]
            raw_score = sum(improvements_list) / len(improvements_list)
            effectiveness_score = max(0.0, min(100.0, raw_score))
        else:
            effectiveness_score = 0.0

        # 5. Calculate health scores
        health_before = self._calculate_health_from_deviations(pre_values, element_improvements)
        health_after = self._calculate_health_from_post_readings(post_readings, element_improvements)

        # Store health score
        self._health_scores[equipment_id] = health_after

        # 6. Build and store EffectivenessScore
        repair_successful = effectiveness_score >= self.EFFECTIVENESS_SUCCESS_THRESHOLD
        all_back = all(ei.back_to_baseline for ei in element_improvements.values()) if element_improvements else False

        result = EffectivenessScore(
            work_order_id=work_order_id,
            equipment_id=equipment_id,
            pre_baseline_id=pre_baseline_id,
            post_baseline_id=f"post-{work_order_id}",
            effectiveness_score=round(effectiveness_score, 1),
            element_improvements=element_improvements,
            repair_successful=repair_successful,
            back_to_baseline=all_back,
            health_score_before=round(health_before, 1),
            health_score_after=round(health_after, 1),
            health_improvement=round(health_after - health_before, 1),
            validated_at=datetime.now(),
        )

        self._effectiveness_scores[work_order_id] = result

        logger.info(
            f"Repair validation complete: {equipment_id}, WO {work_order_id}, "
            f"score={effectiveness_score:.1f}%, successful={repair_successful}"
        )

        return result

    async def get_equipment_health_score(self, equipment_id: str) -> HealthScoreUpdate:
        """
        Calculate equipment health score from latest element trends.

        Uses ElementTrendService to get trend directions, then scores:
        - stable: 100
        - improving: 90
        - degrading: 70
        - rapid_degrading: 30

        Returns weighted average as health score.

        Args:
            equipment_id: Equipment identifier

        Returns:
            HealthScoreUpdate with score and contributing factors
        """
        logger.info(f"Calculating health score for {equipment_id}")

        previous_score = self._health_scores.get(equipment_id, 100.0)
        contributing_factors: Dict[str, float] = {}

        try:
            # Lazy import to avoid circular dependencies
            from app.services.element_trend_service import get_element_trend_service

            trend_service = get_element_trend_service()
            summary = await trend_service.get_equipment_trend_summary(equipment_id)

            if not summary.element_trends:
                # No trend data - return previous or default score
                return HealthScoreUpdate(
                    equipment_id=equipment_id,
                    previous_score=previous_score,
                    new_score=previous_score,
                    contributing_factors={"no_data": 100.0},
                    updated_at=datetime.now(),
                )

            # Score each element based on trend direction
            direction_scores = {
                "stable": 100.0,
                "improving": 90.0,
                "degrading": 70.0,
                "rapid_degrading": 30.0,
            }

            element_scores = []
            for trend in summary.element_trends:
                direction = trend.trend_direction.value if trend.trend_direction else "stable"
                score = direction_scores.get(direction, 100.0)
                element_scores.append(score)
                contributing_factors[trend.element_name] = score

            new_score = sum(element_scores) / len(element_scores) if element_scores else 100.0
            new_score = round(max(0.0, min(100.0, new_score)), 1)

        except Exception as e:
            logger.warning(f"Could not calculate trend-based health score for {equipment_id}: {e}")
            new_score = previous_score
            contributing_factors = {"error": 0.0}

        # Update stored score
        self._health_scores[equipment_id] = new_score

        return HealthScoreUpdate(
            equipment_id=equipment_id,
            previous_score=previous_score,
            new_score=new_score,
            contributing_factors=contributing_factors,
            updated_at=datetime.now(),
        )

    async def get_repair_history(self, equipment_id: str) -> List[RepairHistoryEntry]:
        """
        Get repair history for equipment, sorted by date (newest first).

        Args:
            equipment_id: Equipment identifier

        Returns:
            List of RepairHistoryEntry sorted by repair date descending
        """
        entries: List[RepairHistoryEntry] = []

        for wo_id, score in self._effectiveness_scores.items():
            if score.equipment_id != equipment_id:
                continue

            # Get associated repair outcome for cost/fault info
            outcome = self._repair_outcomes.get(wo_id)
            repair_cost = outcome.repair_cost if outcome else 0.0
            fault_type = outcome.repair_type if outcome else ""
            repair_date = outcome.repair_date if outcome else score.validated_at

            entries.append(
                RepairHistoryEntry(
                    work_order_id=wo_id,
                    equipment_id=equipment_id,
                    repair_date=repair_date,
                    effectiveness_score=score.effectiveness_score,
                    repair_successful=score.repair_successful,
                    repair_cost=repair_cost,
                    fault_type=fault_type,
                )
            )

        # Sort by date descending
        entries.sort(key=lambda e: e.repair_date, reverse=True)
        return entries

    async def get_effectiveness_summary(self) -> Dict:
        """
        Get fleet-wide effectiveness summary.

        Returns:
            Dict with total_repairs, avg_effectiveness, success_rate,
            total_cost, repairs_by_type
        """
        total_repairs = len(self._effectiveness_scores)

        if total_repairs == 0:
            return {
                "total_repairs": 0,
                "avg_effectiveness": 0.0,
                "success_rate": 0.0,
                "total_cost": 0.0,
                "repairs_by_type": {},
            }

        # Calculate averages
        scores = [s.effectiveness_score for s in self._effectiveness_scores.values()]
        avg_effectiveness = sum(scores) / len(scores)

        successful = sum(1 for s in self._effectiveness_scores.values() if s.repair_successful)
        success_rate = (successful / total_repairs) * 100

        # Calculate total cost and repairs by type
        total_cost = 0.0
        repairs_by_type: Dict[str, int] = {}

        for wo_id, outcome in self._repair_outcomes.items():
            total_cost += outcome.repair_cost
            rt = outcome.repair_type
            repairs_by_type[rt] = repairs_by_type.get(rt, 0) + 1

        return {
            "total_repairs": total_repairs,
            "avg_effectiveness": round(avg_effectiveness, 1),
            "success_rate": round(success_rate, 1),
            "total_cost": round(total_cost, 2),
            "repairs_by_type": repairs_by_type,
        }

    async def record_repair_outcome(self, outcome: RepairOutcome) -> None:
        """
        Store repair metadata before validation.

        Args:
            outcome: RepairOutcome with repair details
        """
        self._repair_outcomes[outcome.work_order_id] = outcome
        logger.info(
            f"Recorded repair outcome: {outcome.equipment_id}, WO {outcome.work_order_id}, type={outcome.repair_type}"
        )

    # ========================================================================
    # Private Helper Methods
    # ========================================================================

    async def _get_pre_repair_baseline(self, equipment_id: str) -> Optional[Dict]:
        """Fetch pre-repair baseline from repository."""
        try:
            from app.database.repositories.baseline_repository import BaselineRepository

            repo = BaselineRepository()
            # Get most recent pre_repair baseline
            baselines = await repo.get_equipment_baseline_history(equipment_id=equipment_id, limit=10)

            for bl in baselines:
                if bl.baseline_type.value == "pre_repair":
                    return {"id": bl.id, "baseline_values": bl.baseline_values, "baseline_date": bl.baseline_date}

            return None

        except Exception as e:
            logger.warning(f"Could not fetch pre-repair baseline for {equipment_id}: {e}")
            return None

    async def _get_original_baseline_value(
        self, equipment_id: str, element_name: str, pre_repair_value: float
    ) -> float:
        """
        Get original (initial) baseline value for an element.

        Falls back to estimating from pre-repair value if not available.
        """
        try:
            from app.database.repositories.baseline_repository import BaselineRepository

            repo = BaselineRepository()
            baseline = await repo.get_active_equipment_baseline(equipment_id)

            if baseline and baseline.baseline_values:
                values = baseline.baseline_values
                el_data = values.get(element_name)
                if isinstance(el_data, dict):
                    return float(el_data.get("value", pre_repair_value))
                elif isinstance(el_data, (int, float)):
                    return float(el_data)

        except Exception as e:
            logger.debug(f"Could not fetch original baseline for {equipment_id}/{element_name}: {e}")

        # Fallback: estimate original as 80% of pre-repair value
        # (pre-repair is degraded, so original should be lower/better)
        return pre_repair_value * 0.8

    def _calculate_health_from_deviations(
        self, pre_values: Dict[str, float], element_improvements: Dict[str, ElementImprovement]
    ) -> float:
        """
        Calculate health score from pre-repair state.

        Base score: 100
        For each element with deviation from baseline:
        - critical deviation (>30%): -20 points
        - warning deviation (>15%): -10 points
        - normal: 0 points
        Minimum score: 0
        """
        score = 100.0

        for name, ei in element_improvements.items():
            if ei.baseline_value == 0:
                continue
            deviation_pct = abs(ei.pre_value - ei.baseline_value) / abs(ei.baseline_value) * 100

            if deviation_pct > 30.0:
                score -= 20.0
            elif deviation_pct > 15.0:
                score -= 10.0

        return max(0.0, score)

    def _calculate_health_from_post_readings(
        self, post_readings: Dict[str, float], element_improvements: Dict[str, ElementImprovement]
    ) -> float:
        """
        Calculate health score from post-repair state.

        Same formula as pre-repair but using post values.
        """
        score = 100.0

        for name, ei in element_improvements.items():
            if ei.baseline_value == 0:
                continue
            deviation_pct = abs(ei.post_value - ei.baseline_value) / abs(ei.baseline_value) * 100

            if deviation_pct > 30.0:
                score -= 20.0
            elif deviation_pct > 15.0:
                score -= 10.0

        return max(0.0, score)

    def _generate_demo_pre_values(self, equipment_id: str) -> Dict[str, float]:
        """Generate synthetic pre-repair values for demo scope."""
        # Typical chiller pre-repair values (degraded state)
        if "CHILLER" in equipment_id.upper():
            return {
                "chw_supply_temp": 9.5,  # Degraded (baseline ~7.2)
                "motor_current": 168.0,  # High (baseline ~145)
                "vibration_rms": 3.2,  # Elevated (baseline ~1.2)
                "discharge_pressure": 18.5,  # High (baseline ~15.8)
                "oil_pressure": 38.0,  # Low (baseline ~45)
            }
        elif "AHU" in equipment_id.upper():
            return {"supply_air_temp": 16.5, "filter_dp": 380.0, "fan_vibration": 2.8, "motor_current": 22.5}
        else:
            return {"temperature": 28.5, "vibration": 2.5, "current": 15.0}

    def _generate_demo_post_values(self, equipment_id: str, pre_values: Dict[str, float]) -> Dict[str, float]:
        """
        Generate synthetic post-repair values for demo scope.

        Simulates a mostly successful repair (70-90% improvement).
        """
        post = {}
        for key, pre_val in pre_values.items():
            # Simulate improvement: bring value closer to baseline
            # Improvement factor: 70-90% recovery
            import random

            factor = random.uniform(0.7, 0.9)

            # Estimate baseline as 80% of pre-repair value
            baseline_est = pre_val * 0.8

            # New value = baseline + remaining deviation
            deviation = pre_val - baseline_est
            post[key] = round(baseline_est + deviation * (1 - factor), 2)

        return post


# ============================================================================
# Singleton Instance
# ============================================================================

_repair_effectiveness_service: Optional[RepairEffectivenessService] = None


def get_repair_effectiveness_service() -> RepairEffectivenessService:
    """Get singleton RepairEffectivenessService instance."""
    global _repair_effectiveness_service
    if _repair_effectiveness_service is None:
        _repair_effectiveness_service = RepairEffectivenessService()
    return _repair_effectiveness_service
