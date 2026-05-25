"""
Health Rating Calculator — 5-component weighted formula.

Phase 109B: Health Assessment Timeline

Calculates a composite health score from five independently-sourced
component scores:

  1. Baseline Alignment  (weight 0.35) — deviation from baseline
  2. Service Compliance   (weight 0.20) — days overdue on service
  3. Runtime / Age        (weight 0.20) — age and runtime vs expected life
  4. Fault Burden         (weight 0.15) — weighted recent fault count
  5. Trend Momentum       (weight 0.10) — slope of health score trend

HARD RULES:
  - health_status is ONLY determined by HealthThresholdService.get_health_status()
  - This calculator NEVER writes risk probabilities
  - This calculator NEVER touches the predictions table
"""

import logging
from datetime import datetime, timedelta

from app.models.health_rating import (
    HealthComponentBreakdown,
    HealthRating,
)
from app.services.health_threshold_service import get_health_threshold_service

logger = logging.getLogger(__name__)

# Component weights (must sum to 1.0)
WEIGHTS = {
    "baseline_alignment": 0.35,
    "service_compliance": 0.20,
    "runtime_age": 0.20,
    "fault_burden": 0.15,
    "trend_momentum": 0.10,
}


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    """Clamp a value to [lo, hi]."""
    return max(lo, min(hi, value))


class HealthRatingCalculator:
    """Computes the 5-component weighted health score.

    All pure component methods are synchronous and return floats in [0, 100].
    The composite ``calculate_health_score`` applies weights and clamps.
    Status determination is always delegated to HealthThresholdService.
    """

    # ------------------------------------------------------------------
    # Component 1: Baseline Alignment (weight 0.35)
    # ------------------------------------------------------------------

    @staticmethod
    def calculate_baseline_alignment(deviation_percent: float | None) -> float:
        """Score from baseline deviation.

        Args:
            deviation_percent: Maximum deviation % from baseline (0-100+).
                If None (no baseline), returns 50.0 as a neutral score.

        Returns:
            Score in [0, 100]. Lower deviation = higher score.
        """
        if deviation_percent is None:
            return 50.0
        return _clamp(100 - 2 * deviation_percent)

    # ------------------------------------------------------------------
    # Component 2: Service Compliance (weight 0.20)
    # ------------------------------------------------------------------

    @staticmethod
    def calculate_service_compliance(
        days_since_last_service: int | None,
        service_interval_days: int,
    ) -> float:
        """Score from service schedule adherence.

        Args:
            days_since_last_service: Days since last service record.
                If None (no record), returns 60.0 (assume slightly overdue).
            service_interval_days: Expected interval between services.

        Returns:
            Score in [0, 100]. On-time or early = 100.
        """
        if days_since_last_service is None:
            return 60.0
        days_overdue = max(0, days_since_last_service - service_interval_days)
        return _clamp(100 - 1.5 * days_overdue)

    # ------------------------------------------------------------------
    # Component 3: Runtime / Age (weight 0.20)
    # ------------------------------------------------------------------

    @staticmethod
    def calculate_runtime_age(
        age_years: float | None,
        expected_life_years: float,
        runtime_hours: float | None = None,
        runtime_critical_hours: float | None = None,
    ) -> float:
        """Score from age and runtime hours relative to expected life.

        Both ratios are individually capped at 1.2 (120%) to prevent
        extreme outliers from dominating.

        Args:
            age_years: Equipment age in years. None → 0.
            expected_life_years: Expected useful life in years.
            runtime_hours: Cumulative runtime hours. None → 0 (age-only).
            runtime_critical_hours: Hours threshold for critical wear.

        Returns:
            Score in [0, 100].
        """
        age_ratio = min((age_years or 0) / max(expected_life_years, 1), 1.2)
        runtime_ratio = min((runtime_hours or 0) / max(runtime_critical_hours or 50000, 1), 1.2)
        return _clamp(100 - 50 * age_ratio - 50 * runtime_ratio)

    # ------------------------------------------------------------------
    # Component 4: Fault Burden (weight 0.15)
    # ------------------------------------------------------------------

    @staticmethod
    def calculate_fault_burden(
        critical_faults_30d: int,
        warning_faults_30d: int,
    ) -> float:
        """Score from weighted fault count in the last 30 days.

        Critical faults are weighted 3x, warning faults 1x.

        Args:
            critical_faults_30d: Number of critical-severity faults.
            warning_faults_30d: Number of warning-severity faults.

        Returns:
            Score in [0, 100]. Zero faults = 100.
        """
        weighted = critical_faults_30d * 3 + warning_faults_30d * 1
        return _clamp(100 - 8 * weighted)

    # ------------------------------------------------------------------
    # Component 5: Trend Momentum (weight 0.10)
    # ------------------------------------------------------------------

    @staticmethod
    def calculate_trend_momentum(slope_per_day: float | None) -> float:
        """Score from the slope of the health score trend.

        Slope is in health-score-points per day. Positive slope means
        health is degrading (score increasing = bad); negative means improving.

        Note: "slope" here is the rate of change of *deviation* or *degradation*,
        so a negative slope means the equipment is getting healthier.

        Args:
            slope_per_day: Rate of degradation per day.
                None → 80 (assume stable).

        Returns:
            One of four discrete scores: 95 (improving), 80 (stable),
            55 (degrading), 30 (rapidly degrading).
        """
        if slope_per_day is None:
            return 80.0  # assume stable
        if slope_per_day <= -0.3:
            return 95.0  # improving
        if slope_per_day < 0.3:
            return 80.0  # stable
        if slope_per_day < 1.0:
            return 55.0  # degrading
        return 30.0  # rapidly degrading

    # ------------------------------------------------------------------
    # Composite Score
    # ------------------------------------------------------------------

    @staticmethod
    def calculate_health_score(
        baseline_alignment: float,
        service_compliance: float,
        runtime_age: float,
        fault_burden: float,
        trend_momentum: float,
    ) -> float:
        """Compute the weighted composite health score.

        Args:
            baseline_alignment: Score from calculate_baseline_alignment.
            service_compliance: Score from calculate_service_compliance.
            runtime_age: Score from calculate_runtime_age.
            fault_burden: Score from calculate_fault_burden.
            trend_momentum: Score from calculate_trend_momentum.

        Returns:
            Weighted score clamped to [0, 100], rounded to 1 decimal.
        """
        score = (
            WEIGHTS["baseline_alignment"] * baseline_alignment
            + WEIGHTS["service_compliance"] * service_compliance
            + WEIGHTS["runtime_age"] * runtime_age
            + WEIGHTS["fault_burden"] * fault_burden
            + WEIGHTS["trend_momentum"] * trend_momentum
        )
        return round(_clamp(score), 1)

    # ------------------------------------------------------------------
    # Data quality helpers
    # ------------------------------------------------------------------

    @staticmethod
    def calculate_confidence(
        has_live_telemetry: bool,
        operating_data_age_minutes: int | None,
        ml_hours_accumulated: float,
    ) -> str:
        """Score the confidence in a health assessment.

        Returns:
            'high': live telemetry confirmed, operating_data fresh (<=30 min), ML trained
            'medium': some telemetry or ML model warming up
            'low': no live telemetry or operating_data empty/stale
        """
        if not has_live_telemetry or operating_data_age_minutes is None:
            return "low"
        if operating_data_age_minutes > 30:
            return "low"
        if ml_hours_accumulated < 72:
            return "medium"
        return "high"

    @staticmethod
    def calculate_trend(
        current_score: float,
        previous_score: float | None,
    ) -> str:
        """Determine health trend from current and previous score.

        Returns:
            'improving': score increased by >2 points (lower degradation)
            'stable': score change within ±2 points
            'degrading': score dropped by >2 points
            'unknown': no previous score available
        """
        if previous_score is None:
            return "unknown"
        delta = current_score - previous_score
        if delta > 2:
            return "improving"
        if delta < -2:
            return "degrading"
        return "stable"

    @staticmethod
    def get_health_status(score: float) -> str:
        """Get health status from HealthThresholdService.

        HARD RULE: Status is NEVER computed locally.

        Returns:
            'healthy' | 'warning' | 'critical'
        """
        return get_health_threshold_service().get_health_status(score)

    # ------------------------------------------------------------------
    # Full Rating
    # ------------------------------------------------------------------

    async def compute_rating(
        self,
        equipment_id: str,
        equipment: dict,
        mode: str,
        data_quality_result=None,
    ) -> HealthRating:
        """Compute a full HealthRating for one equipment item.

        Gathers data from existing services and computes all five component
        scores, the composite health score, and the health status.

        Args:
            equipment_id: Equipment code or UUID.
            equipment: Equipment dict with keys: age_years, expected_life_years,
                health_score, site_id, type, code, etc.
            mode: Ingestion mode string ('simulation', 'shadow_live', 'live_control').
            data_quality_result: Pre-computed HealthDataQualityResult, or None
                to use default values.

        Returns:
            HealthRating with all fields populated.
        """
        # --- Gather component inputs ---

        # 1. Baseline alignment: deviation from baseline_comparisons
        deviation_percent = await self._get_baseline_deviation(equipment_id)

        # 2. Service compliance: days since last service
        days_since_service = await self._get_days_since_service(equipment_id)
        service_interval = self._get_service_interval(equipment.get("type", ""))

        # 3. Runtime / Age
        age_years = equipment.get("age_years")
        expected_life = self._get_expected_life(equipment.get("type", ""))
        runtime_hours = equipment.get("runtime_hours")

        # 4. Fault burden: count alerts by severity in last 30 days
        critical_faults, warning_faults = await self._get_fault_counts(equipment_id)

        # 5. Trend momentum: slope of health score trend
        slope = await self._get_trend_slope(equipment_id)

        # --- Calculate component scores ---
        baseline_score = self.calculate_baseline_alignment(deviation_percent)
        service_score = self.calculate_service_compliance(days_since_service, service_interval)
        runtime_score = self.calculate_runtime_age(age_years, expected_life, runtime_hours)
        fault_score = self.calculate_fault_burden(critical_faults, warning_faults)
        trend_score = self.calculate_trend_momentum(slope)

        # --- Composite ---
        health_score = self.calculate_health_score(
            baseline_score, service_score, runtime_score, fault_score, trend_score
        )
        health_status = self.get_health_status(health_score)

        # --- Data quality ---
        if data_quality_result is None:
            from app.services.health_data_quality_gate import HealthDataQualityGate

            gate = HealthDataQualityGate()
            data_quality_result = gate.evaluate(
                mode=mode,
                freshness_minutes=0.0,
                snapshot_count_24h=0,
                valid_point_ratio=1.0,
                baseline_age_days=0,
            )

        components = HealthComponentBreakdown(
            baseline_alignment_score=baseline_score,
            service_compliance_score=service_score,
            runtime_age_score=runtime_score,
            fault_burden_score=fault_score,
            trend_momentum_score=trend_score,
        )

        return HealthRating(
            equipment_id=equipment_id,
            health_score=health_score,
            health_status=health_status,
            confidence=data_quality_result.confidence,
            assessment_state=data_quality_result.assessment_state,
            components=components,
            data_quality=data_quality_result,
            formula_version="v1",
            snapshot_at=datetime.utcnow().isoformat() + "Z",
        )


    async def calculate_from_sensors(
        self,
        equipment_id: str,
        equipment: dict,
        sensor_readings: dict,
        operating_data: dict | None = None,
    ) -> float | None:
        """
        Calculate health score from live sensor readings.

        Used when no pre-computed health_score exists (e.g., shadow polling path).
        Derives health from available telemetry signals rather than historical data.

        Args:
            equipment_id: Equipment code (e.g., 'S002-CHILLER-B1-001')
            equipment: Equipment dict with type, age, runtime, etc.
            sensor_readings: Live sensor data from bridge/telemetry
            operating_data: Existing operating_data dict with anomaly scores

        Returns:
            Health score 0-100, or None if insufficient data
        """
        # Gate: skip non-scoreable equipment types
        try:
            from app.config.health_config import get_scoreability
            eq_type = equipment.get("type", "")
            score_cfg = get_scoreability(eq_type)
            if not score_cfg.get("scoreable", False):
                logger.debug(f"[HEALTH-SENSORS] Skipping {equipment.get('code','?')} ({eq_type}): {score_cfg.get('reason', 'not scoreable')}")
                return None
        except Exception:
            pass

        if not sensor_readings and not operating_data:
            return None

        op_data = operating_data or {}

        # Component 1: Baseline alignment from sensor deviation
        # Use temperature deviation if available
        baseline_score = 75.0  # neutral default
        room_temp = sensor_readings.get("room_temp") or sensor_readings.get("chw_return_temp") or sensor_readings.get("return_air_temp")
        setpoint = sensor_readings.get("setpoint") or op_data.get("setpoint")
        if room_temp is not None and setpoint is not None:
            try:
                deviation = abs(float(room_temp) - float(setpoint))
                # 0°C deviation = 100, 5°C deviation = 50, 10°C deviation = 0
                baseline_score = max(0.0, 100.0 - (deviation * 10.0))
            except (ValueError, TypeError):
                pass

        # Component 2: Anomaly signal from Isolation Forest (inverted to health)
        anomaly_score = op_data.get("anomaly_score") or sensor_readings.get("anomaly_score")
        if anomaly_score is not None:
            try:
                anomaly_health = (1.0 - float(anomaly_score)) * 100.0
            except (ValueError, TypeError):
                anomaly_health = 80.0
        else:
            anomaly_health = 80.0  # neutral when no anomaly data

        # Component 3: Service compliance from equipment record
        days_since_service = await self._get_days_since_service(equipment_id)
        service_interval = self._get_service_interval(equipment.get("type", ""))
        service_score = self.calculate_service_compliance(days_since_service, service_interval)

        # Component 4: Runtime / Age from equipment record
        age_years = equipment.get("age_years")
        expected_life = self._get_expected_life(equipment.get("type", ""))
        runtime_hours = equipment.get("runtime_hours") or op_data.get("runtime_hours")
        runtime_score = self.calculate_runtime_age(age_years, expected_life, runtime_hours)

        # Component 5: Fault burden from recent alerts
        critical_faults, warning_faults = await self._get_fault_counts(equipment_id)
        fault_score = self.calculate_fault_burden(critical_faults, warning_faults)

        # Weighted composition (anomaly_health substitutes for trend_momentum in live path)
        # Weights: baseline 30%, anomaly 20%, service 20%, runtime 20%, fault 10%
        weighted = (
            baseline_score * 0.30 +
            anomaly_health * 0.20 +
            service_score * 0.20 +
            runtime_score * 0.20 +
            fault_score * 0.10
        )

        return round(max(0.0, min(100.0, weighted)), 2)

    # ------------------------------------------------------------------
    # Data Gathering Helpers (with try/except per source)
    # ------------------------------------------------------------------

    async def _get_baseline_deviation(self, equipment_id: str) -> float | None:
        """Get max deviation % from baseline_comparisons table."""
        try:
            from app.database.repositories.baseline_repository import BaselineRepository

            repo = BaselineRepository()
            comparisons = await repo.get_comparisons(
                equipment_id=equipment_id,
                hours=24,
            )
            if comparisons:
                deviations = [c.get("max_deviation_percent", 0) or 0 for c in comparisons]
                return max(deviations) if deviations else None
        except Exception as e:
            logger.debug(f"Could not get baseline deviation for {equipment_id}: {e}")
        return None

    async def _get_days_since_service(self, equipment_id: str) -> int | None:
        """Get days since last service record."""
        try:
            from app.database.repositories.service_record_repository import (
                ServiceRecordRepository,
            )

            repo = ServiceRecordRepository()
            records = repo.get_by_equipment(equipment_id, limit=1)
            if records:
                last_date_str = records[0].get("service_date") or records[0].get("created_at")
                if last_date_str:
                    last_date = datetime.fromisoformat(last_date_str.replace("Z", "+00:00"))
                    delta = datetime.now(last_date.tzinfo) - last_date
                    return delta.days
        except Exception as e:
            logger.debug(f"Could not get service records for {equipment_id}: {e}")
        return None

    def _get_service_interval(self, equipment_type: str) -> int:
        """Get service interval days from health config."""
        try:
            from app.api.health_config import load_config

            config = load_config()
            type_config = config.get(equipment_type.upper(), {})
            return type_config.get("service_interval_days", 90)
        except Exception:
            return 90  # default

    def _get_expected_life(self, equipment_type: str) -> float:
        """Get expected life years from health config."""
        try:
            from app.api.health_config import load_config

            config = load_config()
            type_config = config.get(equipment_type.upper(), {})
            return float(type_config.get("expected_life_years", 15))
        except Exception:
            return 15.0  # default

    async def _get_fault_counts(self, equipment_id: str) -> tuple:
        """Get critical and warning fault counts in last 30 days."""
        try:
            from app.database.supabase_client import get_supabase_client

            client = get_supabase_client()
            cutoff = (datetime.utcnow() - timedelta(days=30)).isoformat()

            result = (
                client.table("alerts")
                .select("severity")
                .eq("equipment_id", equipment_id)
                .neq("status", "resolved")  # Only count unresolved faults
                .gte("created_at", cutoff)
                .execute()
            )

            critical = sum(1 for a in (result.data or []) if a.get("severity") == "critical")
            warning = sum(1 for a in (result.data or []) if a.get("severity") == "warning")
            return critical, warning
        except Exception as e:
            logger.debug(f"Could not get fault counts for {equipment_id}: {e}")
        return 0, 0

    async def _get_trend_slope(self, equipment_id: str) -> float | None:
        """Get the health score trend slope (points per day)."""
        try:
            from app.services.element_trend_service import ElementTrendService

            svc = ElementTrendService()
            summary = await svc.get_equipment_trend_summary(equipment_id)
            if summary and hasattr(summary, "degradation_rate"):
                rate = summary.degradation_rate
                if rate is not None:
                    return rate.slope_per_day if hasattr(rate, "slope_per_day") else None
        except Exception as e:
            logger.debug(f"Could not get trend slope for {equipment_id}: {e}")
        return None
