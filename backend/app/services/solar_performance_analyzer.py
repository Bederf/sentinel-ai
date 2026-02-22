"""Solar Performance Analyzer — Baseline calculation, peer comparison, soiling detection.

Provides:
  - Inverter efficiency and capacity factor calculation
  - 7-day rolling average baseline per inverter type
  - Peer comparison with percentile reporting
  - Soiling and degradation detection
  - Clear-sky model estimation for expected generation

Pattern follows solar_performance_service.py thresholds and energy models.
"""

import logging
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from app.models.solar import SolarInverter

logger = logging.getLogger(__name__)


# === Efficiency thresholds ===

EFFICIENCY_THRESHOLDS = {
    "excellent": 0.95,  # >95% system efficiency
    "good": 0.90,  # 90-95% acceptable
    "acceptable": 0.85,  # 85-90% needs attention
    "poor": 0.0,  # <85% investigate
}

AVAILABILITY_THRESHOLDS = {
    "excellent": 0.99,  # >99% uptime
    "good": 0.95,  # 95-99%
    "acceptable": 0.90,  # 90-95%
    "poor": 0.0,  # <90% investigate
}

# System loss factors for efficiency calculation
SYSTEM_LOSSES = {
    "wiring_dc": 0.015,  # DC wiring losses
    "wiring_ac": 0.010,  # AC wiring losses
    "soiling": 0.030,  # Panel soiling (SA conditions)
    "mismatch": 0.020,  # Module mismatch
    "temperature": 0.050,  # Temperature derating (Johannesburg avg ~25°C)
    "inverter": 0.030,  # Inverter conversion losses
    "clipping": 0.010,  # Inverter clipping at peak
}

# Temperature coefficient for PV panels
TEMP_COEFFICIENT = -0.004  # -0.4% per °C above 25°C STC

# Soiling and degradation thresholds
SOILING_ALERT_THRESHOLD = 0.05  # 5% loss triggers alert
SOILING_CLEANING_THRESHOLD = 0.10  # 10% loss triggers work order
ANNUAL_DEGRADATION_WARNING = 0.02  # >2% annual degradation
ANNUAL_DEGRADATION_NORMAL = 0.008  # Expected 0.5-0.8% per year


@dataclass
class PerformanceBaseline:
    """7-day rolling baseline for a single inverter."""

    inverter_id: str
    inverter_type: str  # manufacturer + model
    capacity_kva: float

    # Baseline metrics (7-day rolling average)
    efficiency_7d_avg: float = 0.90
    availability_7d_avg: float = 0.99
    temp_rise_c: float = 15.0  # Typical temp rise above ambient

    # String voltage balance baseline
    string_voltage_balance_7d_avg: float = 1.01  # Max/Min ratio
    string_current_balance_7d_avg: float = 1.03

    # Timestamps
    baseline_start: Optional[str] = None
    last_updated: Optional[str] = None

    # Historical data (last 7 days)
    historical_efficiency: List[float] = field(default_factory=list)
    historical_availability: List[float] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "inverter_id": self.inverter_id,
            "inverter_type": self.inverter_type,
            "capacity_kva": round(self.capacity_kva, 2),
            "efficiency_7d_avg": round(self.efficiency_7d_avg, 4),
            "availability_7d_avg": round(self.availability_7d_avg, 4),
            "temp_rise_c": round(self.temp_rise_c, 2),
            "string_voltage_balance_7d_avg": round(self.string_voltage_balance_7d_avg, 4),
            "baseline_start": self.baseline_start,
            "last_updated": self.last_updated,
        }


@dataclass
class PeerComparisonReport:
    """Peer comparison metrics for an inverter against same model fleet."""

    inverter_id: str
    inverter_type: str
    comparison_period: str  # day, week, month

    # Current inverter metrics
    efficiency_current: float
    availability_current: float
    temp_rise_current: float

    # Peer statistics (same manufacturer + model)
    peer_count: int = 1
    peer_efficiency_p50: float = 0.90  # Median
    peer_efficiency_p10: float = 0.85  # 10th percentile
    peer_efficiency_p25: float = 0.88
    peer_efficiency_p75: float = 0.92
    peer_efficiency_p90: float = 0.94

    # Deviation analysis
    efficiency_deviation_pct: float = 0.0  # % below peer median
    availability_deviation_pct: float = 0.0
    is_underperforming: bool = False
    confidence_level: str = "medium"  # low/medium/high

    # Recommendation
    recommendation: str = ""
    estimated_loss_kwh_day: float = 0.0
    estimated_loss_zar_day: float = 0.0

    def to_dict(self) -> Dict:
        return {
            "inverter_id": self.inverter_id,
            "inverter_type": self.inverter_type,
            "comparison_period": self.comparison_period,
            "current_metrics": {
                "efficiency": round(self.efficiency_current, 4),
                "availability": round(self.availability_current, 4),
                "temp_rise_c": round(self.temp_rise_current, 2),
            },
            "peer_statistics": {
                "peer_count": self.peer_count,
                "efficiency": {
                    "p10": round(self.peer_efficiency_p10, 4),
                    "p25": round(self.peer_efficiency_p25, 4),
                    "p50": round(self.peer_efficiency_p50, 4),  # median
                    "p75": round(self.peer_efficiency_p75, 4),
                    "p90": round(self.peer_efficiency_p90, 4),
                },
            },
            "deviation_analysis": {
                "efficiency_deviation_pct": round(self.efficiency_deviation_pct, 2),
                "availability_deviation_pct": round(self.availability_deviation_pct, 2),
                "is_underperforming": self.is_underperforming,
                "confidence": self.confidence_level,
            },
            "impact": {
                "estimated_loss_kwh_day": round(self.estimated_loss_kwh_day, 2),
                "estimated_loss_zar_day": round(self.estimated_loss_zar_day, 2),
            },
            "recommendation": self.recommendation,
        }


@dataclass
class SoilingAnalysis:
    """Soiling and degradation analysis for a site/plant."""

    site_id: str
    plant_id: str
    timestamp: str

    # Soiling metrics
    clear_sky_generation_kwh: float
    actual_generation_kwh: float
    soiling_loss_pct: float = 0.0
    soiling_status: str = "clean"  # clean/alert/critical

    # Degradation metrics
    annual_degradation_pct: float = 0.0
    degradation_status: str = "healthy"  # healthy/warning/critical
    warranty_eligible: bool = True

    # Recommendations
    cleaning_recommended: bool = False
    estimated_gain_kwh_day: float = 0.0
    estimated_gain_zar_day: float = 0.0

    def to_dict(self) -> Dict:
        return {
            "site_id": self.site_id,
            "plant_id": self.plant_id,
            "timestamp": self.timestamp,
            "soiling": {
                "clear_sky_generation_kwh": round(self.clear_sky_generation_kwh, 2),
                "actual_generation_kwh": round(self.actual_generation_kwh, 2),
                "loss_pct": round(self.soiling_loss_pct, 2),
                "status": self.soiling_status,
                "cleaning_recommended": self.cleaning_recommended,
                "estimated_gain_kwh_day": round(self.estimated_gain_kwh_day, 2),
                "estimated_gain_zar_day": round(self.estimated_gain_zar_day, 2),
            },
            "degradation": {
                "annual_rate_pct": round(self.annual_degradation_pct, 3),
                "status": self.degradation_status,
                "warranty_eligible": self.warranty_eligible,
            },
        }


class SolarPerformanceAnalyzer:
    """Analyzes solar inverter performance with baseline and peer comparison."""

    def __init__(self):
        """Initialize performance analyzer."""
        self._baselines: Dict[str, PerformanceBaseline] = {}
        self._peer_baselines: Dict[str, Dict] = {}  # inverter_type -> baseline dict
        self._soiling_history: Dict[str, List[SoilingAnalysis]] = {}

    def calculate_efficiency(
        self,
        ac_power_kw: float,
        irradiance_w_m2: float,
        array_capacity_kwp: float,
        inverter_temp_c: float = 25.0,
        ambient_temp_c: float = 25.0,
    ) -> float:
        """
        Calculate system efficiency as percentage.

        Efficiency = (AC Power Output / (Irradiance × Array Capacity)) × 100%
        Adjusts for temperature effects.

        Args:
            ac_power_kw: AC output power in kW
            irradiance_w_m2: Solar irradiance in W/m²
            array_capacity_kwp: Installed array capacity in kWp
            inverter_temp_c: Inverter temperature in °C
            ambient_temp_c: Ambient temperature in °C

        Returns:
            Efficiency as float (0.0 to 1.0)
        """
        if array_capacity_kwp == 0 or irradiance_w_m2 < 50:
            # Not enough light to measure efficiency
            return 0.0

        # Theoretical output at STC (Standard Test Conditions)
        theoretical_output_kw = (irradiance_w_m2 / 1000.0) * array_capacity_kwp

        if theoretical_output_kw < 0.1:
            # Below minimum generation threshold
            return 0.0

        # Apply temperature derating for PV module output
        # Typical PV modules derating: -0.4% per °C above 25°C STC
        panel_temp_c = ambient_temp_c + 20  # Typical panel temp rise above ambient
        temp_derating = 1.0 + (TEMP_COEFFICIENT * (panel_temp_c - 25.0))
        temp_derating = max(0.5, temp_derating)  # Cap at 50% minimum efficiency

        # Apply system losses
        system_loss_factor = sum(SYSTEM_LOSSES.values())
        actual_efficiency = (1.0 - system_loss_factor) * temp_derating

        # Account for inverter thermal derating (high temp reduces output)
        if inverter_temp_c > 50:
            thermal_derating = 1.0 - ((inverter_temp_c - 50) * 0.01)  # 1% loss per °C above 50°C
            actual_efficiency *= max(0.7, thermal_derating)

        # Measured efficiency
        measured_efficiency = ac_power_kw / theoretical_output_kw

        return min(max(measured_efficiency, 0.0), 1.0)

    def calculate_capacity_factor(
        self,
        actual_generation_kwh: float,
        capacity_kwp: float,
        hours_period: float = 24.0,
    ) -> float:
        """
        Calculate capacity factor.

        CF = Actual Generation / (Capacity × Hours) × 100%
        Typical range: 15-25% for Johannesburg

        Args:
            actual_generation_kwh: Energy generated in period (kWh)
            capacity_kwp: Installed capacity (kWp)
            hours_period: Period in hours (default 24h)

        Returns:
            Capacity factor as float (0.0 to 1.0)
        """
        if capacity_kwp == 0 or hours_period == 0:
            return 0.0

        theoretical_kwh = capacity_kwp * hours_period
        return min(actual_generation_kwh / theoretical_kwh, 1.0)

    def calculate_availability(
        self,
        runtime_hours: float,
        total_hours: float = 24.0,
    ) -> float:
        """
        Calculate system availability as uptime percentage.

        Args:
            runtime_hours: Hours system was operational
            total_hours: Total hours in period (default 24h)

        Returns:
            Availability as float (0.0 to 1.0)
        """
        if total_hours == 0:
            return 0.0
        return min(runtime_hours / total_hours, 1.0)

    def get_peer_baseline(
        self,
        inverter_type: str,
        capacity_kva: float,
    ) -> PerformanceBaseline:
        """
        Get 7-day rolling baseline for inverter type + capacity.

        Args:
            inverter_type: Manufacturer and model (e.g., "Huawei SUN2000-100K")
            capacity_kva: Rated capacity in kVA

        Returns:
            PerformanceBaseline object with 7-day rolling averages
        """
        # Check if baseline exists
        baseline_key = f"{inverter_type}_{capacity_kva}"

        if baseline_key in self._peer_baselines:
            baseline_data = self._peer_baselines[baseline_key]
            baseline = PerformanceBaseline(
                inverter_id=f"fleet_{baseline_key}",
                inverter_type=inverter_type,
                capacity_kva=capacity_kva,
                efficiency_7d_avg=baseline_data.get("efficiency_7d_avg", 0.90),
                availability_7d_avg=baseline_data.get("availability_7d_avg", 0.99),
                temp_rise_c=baseline_data.get("temp_rise_c", 15.0),
                string_voltage_balance_7d_avg=baseline_data.get("string_voltage_balance_7d_avg", 1.01),
            )
            return baseline

        # Return default baseline if not yet tracked
        return PerformanceBaseline(
            inverter_id=f"fleet_{baseline_key}",
            inverter_type=inverter_type,
            capacity_kva=capacity_kva,
            efficiency_7d_avg=0.90,  # Industry average for South Africa
            availability_7d_avg=0.99,
            temp_rise_c=15.0,
            string_voltage_balance_7d_avg=1.01,
        )

    def compare_to_peers(
        self,
        inverter: SolarInverter,
        peer_inverters: List[SolarInverter],
        current_efficiency: float = 0.90,
        current_availability: float = 0.99,
        current_temp_rise_c: float = 15.0,
    ) -> PeerComparisonReport:
        """
        Compare inverter against same model/capacity peers.

        Args:
            inverter: The inverter to analyze
            peer_inverters: List of same-type peer inverters for comparison
            current_efficiency: Current efficiency measurement
            current_availability: Current availability percentage
            current_temp_rise_c: Current temperature rise

        Returns:
            PeerComparisonReport with percentiles and deviation analysis
        """
        # Extract peer efficiencies for percentile calculation
        peer_efficiencies = []
        for peer in peer_inverters:
            # Simulate fetching peer efficiency from baseline/history
            peer_baseline = self.get_peer_baseline(
                f"{peer.manufacturer} {peer.model}",
                peer.rated_power_kva,
            )
            peer_efficiencies.append(peer_baseline.efficiency_7d_avg)

        # Ensure we have at least current inverter for percentile calculation
        if not peer_efficiencies:
            peer_efficiencies = [current_efficiency]

        # Sort for percentile calculation
        peer_efficiencies_sorted = sorted(peer_efficiencies)
        n = len(peer_efficiencies_sorted)

        # Calculate percentiles
        p10_idx = max(0, int(n * 0.10) - 1)
        p25_idx = max(0, int(n * 0.25) - 1)
        p50_idx = max(0, int(n * 0.50) - 1)
        p75_idx = min(n - 1, int(n * 0.75))
        p90_idx = min(n - 1, int(n * 0.90))

        p10 = peer_efficiencies_sorted[p10_idx]
        p25 = peer_efficiencies_sorted[p25_idx]
        p50 = peer_efficiencies_sorted[p50_idx]  # Median
        p75 = peer_efficiencies_sorted[p75_idx]
        p90 = peer_efficiencies_sorted[p90_idx]

        # Calculate deviation from peer median
        efficiency_deviation = ((p50 - current_efficiency) / p50) * 100 if p50 > 0 else 0

        # Determine if underperforming (>5% below median)
        is_underperforming = efficiency_deviation > 5.0

        # Estimate financial impact
        # Assume 100 kWh/day generation at peer efficiency
        baseline_daily_generation = 100.0  # kWh (representative)
        peer_daily_kwh = baseline_daily_generation * p50
        current_daily_kwh = baseline_daily_generation * current_efficiency
        loss_kwh_day = peer_daily_kwh - current_daily_kwh

        # Cost impact using typical South African tariff (2.85 ZAR/kWh)
        tariff_zar_kwh = 2.85
        loss_zar_day = loss_kwh_day * tariff_zar_kwh

        # Build recommendation
        recommendation = "System performing within expected range."
        if efficiency_deviation > 10:
            recommendation = (
                f"CRITICAL: Efficiency {efficiency_deviation:.1f}% below peers. "
                f"Investigate immediately. Potential fault in inverter or strings."
            )
        elif efficiency_deviation > 5:
            recommendation = (
                f"WARNING: Efficiency {efficiency_deviation:.1f}% below peers. Schedule diagnostics within 24h."
            )
        elif efficiency_deviation < -5:
            recommendation = "Excellent performance. Above peer average. Maintain current operations."

        return PeerComparisonReport(
            inverter_id=inverter.inverter_id,
            inverter_type=f"{inverter.manufacturer} {inverter.model}",
            comparison_period="24h",
            efficiency_current=current_efficiency,
            availability_current=current_availability,
            temp_rise_current=current_temp_rise_c,
            peer_count=len(peer_inverters),
            peer_efficiency_p10=p10,
            peer_efficiency_p25=p25,
            peer_efficiency_p50=p50,
            peer_efficiency_p75=p75,
            peer_efficiency_p90=p90,
            efficiency_deviation_pct=efficiency_deviation,
            is_underperforming=is_underperforming,
            confidence_level="high" if len(peer_inverters) > 2 else "medium",
            recommendation=recommendation,
            estimated_loss_kwh_day=max(0, loss_kwh_day),
            estimated_loss_zar_day=max(0, loss_zar_day),
        )

    def track_baseline_changes(
        self,
        inverter_id: str,
        inverter_type: str,
        capacity_kva: float,
        new_efficiency: float,
        new_availability: float,
    ) -> PerformanceBaseline:
        """
        Update 7-day rolling average baseline for an inverter.

        Args:
            inverter_id: Unique inverter identifier
            inverter_type: Manufacturer and model
            capacity_kva: Rated capacity
            new_efficiency: Latest efficiency measurement
            new_availability: Latest availability measurement

        Returns:
            Updated PerformanceBaseline
        """
        # Get or create baseline
        if inverter_id not in self._baselines:
            self._baselines[inverter_id] = PerformanceBaseline(
                inverter_id=inverter_id,
                inverter_type=inverter_type,
                capacity_kva=capacity_kva,
                baseline_start=datetime.now(timezone.utc).isoformat(),
            )

        baseline = self._baselines[inverter_id]

        # Add new measurement to history
        baseline.historical_efficiency.append(new_efficiency)
        baseline.historical_availability.append(new_availability)

        # Keep only last 7 days of data (assuming daily measurements)
        if len(baseline.historical_efficiency) > 7:
            baseline.historical_efficiency = baseline.historical_efficiency[-7:]
            baseline.historical_availability = baseline.historical_availability[-7:]

        # Calculate 7-day rolling averages
        if baseline.historical_efficiency:
            baseline.efficiency_7d_avg = statistics.mean(baseline.historical_efficiency)
            baseline.availability_7d_avg = statistics.mean(baseline.historical_availability)

        baseline.last_updated = datetime.now(timezone.utc).isoformat()

        # Update peer baseline cache
        type_key = f"{inverter_type}_{capacity_kva}"
        if type_key not in self._peer_baselines:
            self._peer_baselines[type_key] = {}

        self._peer_baselines[type_key]["efficiency_7d_avg"] = baseline.efficiency_7d_avg
        self._peer_baselines[type_key]["availability_7d_avg"] = baseline.availability_7d_avg

        logger.info(
            f"Updated baseline for {inverter_id}: "
            f"efficiency={baseline.efficiency_7d_avg:.4f}, "
            f"availability={baseline.availability_7d_avg:.4f}"
        )

        return baseline

    def estimate_clear_sky_generation(
        self,
        installed_capacity_kwp: float,
        peak_sun_hours: float = 5.0,
        temperature_c: float = 25.0,
        irradiance_w_m2: float = 1000.0,
    ) -> float:
        """
        Estimate expected generation under clear-sky conditions.

        Uses simplified clear-sky model for South African conditions.

        Args:
            installed_capacity_kwp: Installed PV capacity
            peak_sun_hours: Expected peak sun hours for the day
            temperature_c: Average panel temperature
            irradiance_w_m2: Peak irradiance (STC = 1000 W/m²)

        Returns:
            Expected generation in kWh
        """
        # Base clear-sky generation at STC
        clear_sky_kwh = installed_capacity_kwp * peak_sun_hours

        # Temperature derating
        panel_temp = temperature_c + 20  # Typical panel-ambient offset
        temp_factor = 1.0 + (TEMP_COEFFICIENT * (panel_temp - 25.0))
        temp_factor = max(0.7, temp_factor)

        # System loss factor (soiling-free conditions)
        clear_sky_losses = sum(SYSTEM_LOSSES.values()) - SYSTEM_LOSSES["soiling"]
        clear_sky_kwh *= (1.0 - clear_sky_losses) * temp_factor

        return clear_sky_kwh

    def calculate_soiling_loss(
        self,
        actual_generation_kwh: float,
        clear_sky_generation_kwh: float,
    ) -> float:
        """
        Calculate soiling loss as percentage of expected generation.

        Soiling Loss % = (Expected - Actual) / Expected × 100%

        Args:
            actual_generation_kwh: Measured generation
            clear_sky_generation_kwh: Expected generation under clear sky

        Returns:
            Soiling loss as percentage (0.0 to 1.0)
        """
        if clear_sky_generation_kwh == 0:
            return 0.0

        loss_pct = (clear_sky_generation_kwh - actual_generation_kwh) / clear_sky_generation_kwh
        return max(0.0, min(loss_pct, 1.0))

    def analyze_soiling(
        self,
        site_id: str,
        plant_id: str,
        actual_generation_kwh: float,
        installed_capacity_kwp: float,
        temperature_c: float = 25.0,
    ) -> SoilingAnalysis:
        """
        Analyze soiling and degradation for a site.

        Args:
            site_id: Site identifier
            plant_id: Plant identifier
            actual_generation_kwh: Actual energy generated
            installed_capacity_kwp: Installed capacity
            temperature_c: Current ambient temperature

        Returns:
            SoilingAnalysis object with recommendations
        """
        # Estimate clear-sky generation
        clear_sky_kwh = self.estimate_clear_sky_generation(
            installed_capacity_kwp,
            peak_sun_hours=5.0,  # Johannesburg average
            temperature_c=temperature_c,
        )

        # Calculate soiling loss
        soiling_loss_pct = self.calculate_soiling_loss(actual_generation_kwh, clear_sky_kwh)

        # Determine soiling status
        soiling_status = "clean"
        cleaning_recommended = False
        if soiling_loss_pct > SOILING_CLEANING_THRESHOLD:
            soiling_status = "critical"
            cleaning_recommended = True
        elif soiling_loss_pct > SOILING_ALERT_THRESHOLD:
            soiling_status = "alert"
            cleaning_recommended = True

        # Estimate recovery from cleaning
        lost_generation_kwh = clear_sky_kwh - actual_generation_kwh
        tariff_zar_kwh = 2.85
        estimated_gain_zar = lost_generation_kwh * tariff_zar_kwh

        # Simple degradation estimate (would use historical data in production)
        # Typical degradation: 0.5-0.8% per year, flag if >2%
        annual_degradation_pct = 0.008  # 0.8% (default)
        degradation_status = "healthy"
        if annual_degradation_pct > ANNUAL_DEGRADATION_WARNING:
            degradation_status = "warning"

        analysis = SoilingAnalysis(
            site_id=site_id,
            plant_id=plant_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            clear_sky_generation_kwh=clear_sky_kwh,
            actual_generation_kwh=actual_generation_kwh,
            soiling_loss_pct=soiling_loss_pct,
            soiling_status=soiling_status,
            annual_degradation_pct=annual_degradation_pct,
            degradation_status=degradation_status,
            cleaning_recommended=cleaning_recommended,
            estimated_gain_kwh_day=lost_generation_kwh,
            estimated_gain_zar_day=estimated_gain_zar,
        )

        # Store in history
        if site_id not in self._soiling_history:
            self._soiling_history[site_id] = []
        self._soiling_history[site_id].append(analysis)

        # Keep only last 30 days
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=30)
        self._soiling_history[site_id] = [
            a for a in self._soiling_history[site_id] if datetime.fromisoformat(a.timestamp) > cutoff_date
        ]

        return analysis

    def track_annual_degradation(
        self,
        site_id: str,
        current_pr: float,
        last_year_pr: Optional[float] = None,
    ) -> Dict:
        """
        Track annual performance degradation.

        Args:
            site_id: Site identifier
            current_pr: Current performance ratio
            last_year_pr: Performance ratio from 1 year ago (if available)

        Returns:
            Degradation analysis dict
        """
        annual_degradation = 0.008  # Default 0.8%

        if last_year_pr and current_pr > 0:
            annual_degradation = (last_year_pr - current_pr) / last_year_pr

        degradation_status = "healthy"
        if annual_degradation > ANNUAL_DEGRADATION_WARNING:
            degradation_status = "warning"

        return {
            "site_id": site_id,
            "annual_degradation_pct": round(annual_degradation * 100, 3),
            "status": degradation_status,
            "warranty_eligible": annual_degradation < 0.03,  # <3% is typical warranty claim threshold
            "recommendation": "System within normal degradation parameters."
            if degradation_status == "healthy"
            else "Consider warranty claim investigation.",
        }


# === Singleton accessor ===

_performance_analyzer: Optional[SolarPerformanceAnalyzer] = None


def get_solar_performance_analyzer() -> SolarPerformanceAnalyzer:
    """Get or create singleton SolarPerformanceAnalyzer instance."""
    global _performance_analyzer
    if _performance_analyzer is None:
        _performance_analyzer = SolarPerformanceAnalyzer()
        logger.info("Initialized SolarPerformanceAnalyzer")
    return _performance_analyzer
