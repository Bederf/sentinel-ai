"""Power meter validation and anomaly detection engine.

Compares simulated HVAC power consumption with real meter readings
to detect anomalies, track equipment degradation, and fine-tune COP factors.

Model:
  Variance Analysis: Compare simulated vs actual hourly power
  Anomaly Detection: Flag readings >15% deviation from baseline
  Degradation Tracking: Monitor COP decline over time
  Equipment Health: Correlate power efficiency with maintenance

Integration: Called hourly when real meter data available.
Output: Validation records, anomaly alerts, COP adjustment recommendations.
"""

import json
import logging
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Dict, Optional, Any
from statistics import mean, stdev
from app.database.supabase_client import get_supabase_client

# Demo fixture path
_DATA_DIR = Path(__file__).resolve().parent.parent / "data"

logger = logging.getLogger(__name__)

# Anomaly detection thresholds
VARIANCE_THRESHOLD_PCT = 15.0  # Flag >15% deviation
CRITICAL_VARIANCE_PCT = 25.0  # Critical if >25% off
MINIMUM_READINGS_FOR_BASELINE = 7  # Days of data to establish baseline
SEASONAL_ADJUSTMENT_FACTOR = 0.95  # Account for seasonal COP variations

# Expected COP ranges (Coefficient of Performance)
EXPECTED_CHILLER_COP = 3.5  # Design COP
COP_ACCEPTABLE_RANGE = (2.8, 4.2)  # 2.8 to 4.2 is healthy
COP_WARNING_THRESHOLD = 2.9  # Alert if below this
COP_CRITICAL_THRESHOLD = 2.5  # Critical if below this


class PowerMeterValidationEngine:
    """Engine for validating simulated power against real meter data."""

    def __init__(self, building_id: str):
        """Initialize power meter validation engine.

        Args:
            building_id: Building/site identifier (e.g., 'site-002')
        """
        self.building_id = building_id
        self.client = get_supabase_client()
        self._baseline_cache = {}

    async def get_power_baseline(
        self,
        meter_id: str,
        lookback_days: int = 7,
    ) -> Dict[str, float]:
        """Get baseline power statistics from real meter data.

        Args:
            meter_id: Meter identifier (e.g., 'S002-MTR-B1-HVAC')
            lookback_days: Days to analyze for baseline

        Returns:
            Baseline stats: mean_kw, stdev_kw, min_kw, max_kw, percentile_95
        """
        try:
            cutoff = datetime.now() - timedelta(days=lookback_days)

            # Query real power consumption history
            response = (
                self.client.table("energy_consumption_history")
                .select("*")
                .eq("meter_id", meter_id)
                .gte("timestamp", cutoff.isoformat())
                .order("timestamp", desc=False)
                .execute()
            )

            readings = response.data or []
            if not readings:
                logger.warning(f"No meter data found for {meter_id}")
                return self._get_default_baseline()

            # Extract power values (use energy_kwh as proxy for hourly power)
            powers = [float(r.get("energy_kwh", 0)) for r in readings if r.get("energy_kwh")]

            if len(powers) < MINIMUM_READINGS_FOR_BASELINE:
                logger.warning(f"Insufficient readings ({len(powers)}) for baseline")
                return self._get_default_baseline()

            # Calculate statistics
            baseline = {
                "mean_kw": round(mean(powers), 2),
                "stdev_kw": round(stdev(powers) if len(powers) > 1 else 0, 2),
                "min_kw": round(min(powers), 2),
                "max_kw": round(max(powers), 2),
                "median_kw": round(sorted(powers)[len(powers) // 2], 2),
                "p95_kw": round(sorted(powers)[int(len(powers) * 0.95)], 2),
                "samples": len(powers),
                "lookback_days": lookback_days,
            }

            # Cache for reuse
            self._baseline_cache[meter_id] = baseline
            return baseline

        except Exception as e:
            logger.error(f"Error calculating baseline: {e}")
            return self._get_default_baseline()

    def _get_default_baseline(self) -> Dict[str, float]:
        """Get default baseline when real data unavailable.

        Falls back to demo_power_baseline.json fixture if available,
        otherwise uses hardcoded defaults.
        """
        # Try loading from demo fixture (3-tier fallback: Supabase -> Cache -> JSON)
        try:
            fixture_path = _DATA_DIR / "demo_power_baseline.json"
            if fixture_path.exists():
                with open(fixture_path) as f:
                    demo = json.load(f)
                stats = demo.get("baseline_stats", {})
                return {
                    "mean_kw": stats.get("mean_kwh", 315.4),
                    "stdev_kw": stats.get("stdev_kwh", 42.1),
                    "min_kw": stats.get("min_kwh", 245.0),
                    "max_kw": stats.get("max_kwh", 412.0),
                    "median_kw": round((stats.get("mean_kwh", 315.4) + stats.get("p95_kwh", 385.0)) / 2, 2),
                    "p95_kw": stats.get("p95_kwh", 385.0),
                    "samples": 168,
                    "lookback_days": 7,
                    "source": "demo_fixture",
                }
        except Exception as e:
            logger.debug(f"Could not load demo baseline: {e}")

        # Hardcoded fallback
        return {
            "mean_kw": 28.2,  # Typical HVAC peak
            "stdev_kw": 8.5,
            "min_kw": 6.7,
            "max_kw": 45.2,
            "median_kw": 25.4,
            "p95_kw": 42.1,
            "samples": 168,
            "lookback_days": 7,
        }

    async def validate_hourly_power(
        self,
        meter_id: str,
        simulated_power_kw: float,
        real_power_kw: Optional[float] = None,
        simulated_hour: int = 0,
        simulated_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Validate simulated power against real meter reading.

        Args:
            meter_id: Meter identifier
            simulated_power_kw: Simulated HVAC power
            real_power_kw: Actual meter reading (if available)
            simulated_hour: Hour of day (0-23)
            simulated_date: Date of simulation

        Returns:
            Validation result with variance, status, recommendations
        """
        if real_power_kw is None:
            # No real data yet - validation skipped
            return {
                "validation_status": "skipped",
                "reason": "no_real_meter_data",
                "simulated_kw": simulated_power_kw,
                "real_kw": None,
                "variance_pct": None,
            }

        if simulated_date is None:
            simulated_date = datetime.now()

        baseline = await self.get_power_baseline(meter_id)

        # Calculate variance
        if real_power_kw > 0:
            variance_pct = abs(simulated_power_kw - real_power_kw) / real_power_kw * 100
        else:
            variance_pct = 0.0

        # Determine status
        if variance_pct > CRITICAL_VARIANCE_PCT:
            status = "critical"
            severity = "critical"
        elif variance_pct > VARIANCE_THRESHOLD_PCT:
            status = "anomaly"
            severity = "warning"
        else:
            status = "normal"
            severity = "healthy"

        # Generate recommendation
        recommendation = self._get_recommendation(variance_pct, simulated_power_kw, real_power_kw, baseline)

        result = {
            "validation_status": status,
            "severity": severity,
            "simulated_kw": round(simulated_power_kw, 2),
            "real_kw": round(real_power_kw, 2),
            "variance_pct": round(variance_pct, 2),
            "variance_direction": "over" if simulated_power_kw > real_power_kw else "under",
            "hour": simulated_hour,
            "date": simulated_date.date().isoformat(),
            "baseline_mean_kw": baseline["mean_kw"],
            "baseline_stdev_kw": baseline["stdev_kw"],
            "zscore": round((real_power_kw - baseline["mean_kw"]) / max(baseline["stdev_kw"], 0.1), 2),
            "recommendation": recommendation,
        }

        # Write validation record if anomaly detected
        if status != "normal":
            await self._write_validation_record(meter_id, result, simulated_date)

        return result

    def _get_recommendation(
        self,
        variance_pct: float,
        simulated_kw: float,
        real_kw: float,
        baseline: Dict[str, float],
    ) -> str:
        """Generate actionable recommendation based on variance."""
        if variance_pct < VARIANCE_THRESHOLD_PCT:
            return "Normal operation - model and meter aligned"

        if simulated_kw > real_kw * 1.2:
            # Simulation overestimating
            return (
                "Simulation overestimating power consumption. "
                "Possible causes: COP lower than expected, equipment not running full load."
            )
        elif simulated_kw < real_kw * 0.85:
            # Simulation underestimating
            return (
                "Simulation underestimating power consumption. "
                "Possible causes: COP degradation, equipment health issues, additional loads."
            )
        else:
            return f"Variance {variance_pct:.1f}% detected. Review equipment efficiency."

    async def _write_validation_record(
        self,
        meter_id: str,
        validation_result: Dict[str, Any],
        simulated_date: datetime,
    ) -> None:
        """Write validation record to database for analysis.

        Args:
            meter_id: Meter identifier
            validation_result: Validation data
            simulated_date: Date of reading
        """
        try:
            record = {
                "building_id": self.building_id,
                "meter_id": meter_id,
                "timestamp": simulated_date.isoformat(),
                "validation_status": validation_result["validation_status"],
                "severity": validation_result["severity"],
                "simulated_kw": validation_result["simulated_kw"],
                "real_kw": validation_result["real_kw"],
                "variance_pct": validation_result["variance_pct"],
                "recommendation": validation_result["recommendation"],
                "zscore": validation_result["zscore"],
                "created_at": datetime.now().isoformat(),
            }

            # Try to insert validation record
            try:
                self.client.table("power_meter_validations").insert(record).execute()
            except Exception as e:
                logger.debug(f"Could not write validation record: {e}")

        except Exception as e:
            logger.error(f"Error writing validation record: {e}")

    async def calculate_cop_adjustment(
        self,
        meter_id: str,
        lookback_days: int = 30,
    ) -> Dict[str, Any]:
        """Calculate recommended COP adjustment based on real vs simulated power.

        Args:
            meter_id: Meter identifier
            lookback_days: Days to analyze

        Returns:
            COP adjustment recommendation with confidence
        """
        try:
            # Get real power consumption
            cutoff = datetime.now() - timedelta(days=lookback_days)

            response = (
                self.client.table("energy_consumption_history")
                .select("*")
                .eq("meter_id", meter_id)
                .gte("timestamp", cutoff.isoformat())
                .execute()
            )

            records = response.data or []
            if len(records) < MINIMUM_READINGS_FOR_BASELINE:
                return {
                    "adjustment_needed": False,
                    "reason": "insufficient_data",
                    "current_cop": EXPECTED_CHILLER_COP,
                    "recommended_cop": EXPECTED_CHILLER_COP,
                }

            # Extract power values
            real_powers = [float(r.get("energy_kwh", 0)) for r in records]
            avg_real_power = mean(real_powers)

            # Estimate COP from actual power usage
            # Typical cooling load = 15-20 kW, so COP = Load / Power
            # Assuming 45 kW cooling load (from zone calculations)
            assumed_cooling_load = 45.0  # kW
            estimated_cop = assumed_cooling_load / avg_real_power if avg_real_power > 0 else EXPECTED_CHILLER_COP

            # Check if adjustment needed
            if COP_ACCEPTABLE_RANGE[0] <= estimated_cop <= COP_ACCEPTABLE_RANGE[1]:
                status = "healthy"
                adjustment_needed = False
                confidence = 0.85
            elif estimated_cop < COP_WARNING_THRESHOLD:
                status = "degraded"
                adjustment_needed = True
                confidence = 0.75
            else:
                status = "unknown"
                adjustment_needed = False
                confidence = 0.5

            return {
                "adjustment_needed": adjustment_needed,
                "status": status,
                "current_cop": round(EXPECTED_CHILLER_COP, 2),
                "estimated_cop": round(estimated_cop, 2),
                "recommended_cop": round(max(estimated_cop, COP_CRITICAL_THRESHOLD), 2),
                "avg_real_power_kw": round(avg_real_power, 2),
                "cooling_load_assumption_kw": assumed_cooling_load,
                "confidence": round(confidence, 2),
                "lookback_days": lookback_days,
                "reason": (
                    "COP within acceptable range"
                    if not adjustment_needed
                    else "COP degradation detected - equipment maintenance recommended"
                ),
            }

        except Exception as e:
            logger.error(f"Error calculating COP adjustment: {e}")
            return {
                "adjustment_needed": False,
                "status": "error",
                "current_cop": EXPECTED_CHILLER_COP,
                "error": str(e),
            }

    async def validate_daily_power(
        self,
        simulated_date: datetime,
        hourly_power_data: Dict[int, float],
    ) -> Dict[str, Any]:
        """Validate a full day of power data against baseline.

        Aggregates hourly power, compares to baseline stats, and returns
        a daily validation result. Used by thermal engine at hour 23.

        Args:
            simulated_date: The date being validated
            hourly_power_data: {hour: total_hvac_kw} for each hour of the day

        Returns:
            Validation result dict with status, variance, recommendations
        """
        try:
            if not hourly_power_data:
                return {
                    "validation_status": "skipped",
                    "reason": "no_hourly_data",
                    "date": simulated_date.date().isoformat()
                    if hasattr(simulated_date, "date")
                    else str(simulated_date),
                }

            # Aggregate daily totals
            total_kwh = sum(hourly_power_data.values())
            hours_recorded = len(hourly_power_data)
            avg_kw = total_kwh / max(hours_recorded, 1)

            # Get baseline (tries real data first, falls back to demo/default)
            meter_id = "S002-MTR-B1-MAIN"  # Default main meter
            baseline = await self.get_power_baseline(meter_id)

            baseline_mean = baseline.get("mean_kw", 0)
            baseline_stdev = baseline.get("stdev_kw", 1)

            # Calculate variance from baseline
            if baseline_mean > 0:
                variance_pct = abs(avg_kw - baseline_mean) / baseline_mean * 100
            else:
                variance_pct = 0.0

            # Determine status
            if variance_pct > CRITICAL_VARIANCE_PCT:
                status = "critical"
                severity = "critical"
            elif variance_pct > VARIANCE_THRESHOLD_PCT:
                status = "anomaly"
                severity = "warning"
            else:
                status = "normal"
                severity = "normal"

            result_date = simulated_date.date().isoformat() if hasattr(simulated_date, "date") else str(simulated_date)

            return {
                "validation_status": status,
                "severity": severity,
                "date": result_date,
                "total_kwh": round(total_kwh, 2),
                "avg_kw": round(avg_kw, 2),
                "hours_recorded": hours_recorded,
                "baseline_mean_kw": round(baseline_mean, 2),
                "baseline_stdev_kw": round(baseline_stdev, 2),
                "variance_pct": round(variance_pct, 2),
                "meter_id": meter_id,
            }

        except Exception as e:
            logger.warning(f"Error in validate_daily_power: {e}")
            return {
                "validation_status": "error",
                "error": str(e),
                "date": simulated_date.date().isoformat() if hasattr(simulated_date, "date") else str(simulated_date),
                "variance_pct": 0.0,
            }

    async def get_daily_validation_summary(
        self,
        meter_id: str,
        summary_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """Get daily summary of power meter validation.

        Args:
            meter_id: Meter identifier
            summary_date: Date to summarize (default: today)

        Returns:
            Daily validation metrics and anomaly count
        """
        if summary_date is None:
            summary_date = date.today()

        try:
            # Query validation records for the day
            start_time = datetime.combine(summary_date, datetime.min.time())
            end_time = datetime.combine(summary_date, datetime.max.time())

            response = (
                self.client.table("power_meter_validations")
                .select("*")
                .eq("meter_id", meter_id)
                .gte("timestamp", start_time.isoformat())
                .lte("timestamp", end_time.isoformat())
                .execute()
            )

            records = response.data or []

            if not records:
                return {
                    "date": summary_date.isoformat(),
                    "meter_id": meter_id,
                    "records_count": 0,
                    "normal_count": 0,
                    "anomaly_count": 0,
                    "critical_count": 0,
                    "avg_variance_pct": 0.0,
                    "max_variance_pct": 0.0,
                    "overall_status": "no_data",
                }

            normal = [r for r in records if r["validation_status"] == "normal"]
            anomalies = [r for r in records if r["validation_status"] == "anomaly"]
            critical = [r for r in records if r["validation_status"] == "critical"]

            variances = [float(r["variance_pct"]) for r in records if r.get("variance_pct")]
            avg_variance = mean(variances) if variances else 0.0
            max_variance = max(variances) if variances else 0.0

            overall_status = (
                "healthy"
                if len(critical) == 0 and len(anomalies) <= 2
                else "warning"
                if len(anomalies) > 2
                else "critical"
            )

            return {
                "date": summary_date.isoformat(),
                "meter_id": meter_id,
                "records_count": len(records),
                "normal_count": len(normal),
                "anomaly_count": len(anomalies),
                "critical_count": len(critical),
                "avg_variance_pct": round(avg_variance, 2),
                "max_variance_pct": round(max_variance, 2),
                "overall_status": overall_status,
                "anomaly_hours": [r["hour"] for r in anomalies],
                "critical_hours": [r["hour"] for r in critical],
            }

        except Exception as e:
            logger.error(f"Error getting daily validation summary: {e}")
            return {
                "date": summary_date.isoformat(),
                "meter_id": meter_id,
                "error": str(e),
                "overall_status": "error",
            }


async def validate_power_meter(
    building_id: str,
    meter_id: str,
    simulated_power_kw: float,
    real_power_kw: Optional[float] = None,
    simulated_hour: int = 0,
    simulated_date: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Public API for power meter validation.

    Called hourly when real meter data available.

    Args:
        building_id: Building/site ID
        meter_id: Meter identifier
        simulated_power_kw: Simulated HVAC power
        real_power_kw: Real meter reading
        simulated_hour: Hour (0-23)
        simulated_date: Date

    Returns:
        Validation result with variance analysis
    """
    engine = PowerMeterValidationEngine(building_id)
    return await engine.validate_hourly_power(
        meter_id=meter_id,
        simulated_power_kw=simulated_power_kw,
        real_power_kw=real_power_kw,
        simulated_hour=simulated_hour,
        simulated_date=simulated_date,
    )


def get_power_meter_validation_engine(building_id: str) -> PowerMeterValidationEngine:
    """Get singleton instance of PowerMeterValidationEngine.

    Args:
        building_id: Building identifier

    Returns:
        PowerMeterValidationEngine instance
    """
    return PowerMeterValidationEngine(building_id)
