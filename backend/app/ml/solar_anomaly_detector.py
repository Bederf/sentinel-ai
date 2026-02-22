"""Solar Anomaly Detector — String-level MPPT tracking and failure detection.

Provides:
  - Per-string MPPT performance analysis
  - String failure detection: dead, shorted, degraded, bypass diode
  - Anomaly scoring based on 7-day baseline comparison
  - Persistent anomaly flagging

Pattern follows cross_system_analyzer.py for anomaly detection logic.
"""

import logging
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple

from app.models.solar import SolarString

logger = logging.getLogger(__name__)


# === String anomaly thresholds ===

CURRENT_DEVIATION_THRESHOLD = 0.08  # 8% deviation from baseline
VOLTAGE_DEVIATION_THRESHOLD = 0.08  # 8% deviation
POWER_DEVIATION_THRESHOLD = 0.10  # 10% deviation

# Failure detection thresholds
DEAD_STRING_CURRENT_THRESHOLD = 0.1  # <0.1A = dead string
DEAD_STRING_VOLTAGE_THRESHOLD = 45.0  # >45V = open circuit (high voltage)

SHORTED_STRING_VOLTAGE_THRESHOLD = 5.0  # <5V = short circuit
SHORTED_STRING_CURRENT_THRESHOLD = 8.0  # >8A = short circuit (high current)

DEGRADED_STRING_POWER_LOSS = 0.20  # >20% power loss = degraded
BYPASS_DIODE_VOLTAGE_RIPPLE = 0.15  # >15% voltage variance = bypass diode failure

# Anomaly scoring
ANOMALY_SCORE_THRESHOLDS = {
    "warning": 70,  # >70: Warning, investigate within 24h
    "critical": 90,  # >90: Critical, stop array or shut down
}

ANOMALY_PERSISTENCE_HOURS = 4  # >4h persistent = likely hardware failure


@dataclass
class StringBaseline:
    """7-day rolling baseline for a PV string."""

    string_id: str
    inverter_id: str
    mppt_tracker: int

    # Baseline metrics
    voltage_v_avg: float = 45.0
    current_a_avg: float = 5.0
    power_kw_avg: float = 0.2

    # Variability
    voltage_v_std: float = 1.0
    current_a_std: float = 0.5
    power_kw_std: float = 0.02

    # History
    voltage_history: List[float] = field(default_factory=list)
    current_history: List[float] = field(default_factory=list)
    power_history: List[float] = field(default_factory=list)

    # Timestamps
    baseline_start: Optional[str] = None
    last_updated: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "string_id": self.string_id,
            "inverter_id": self.inverter_id,
            "mppt_tracker": self.mppt_tracker,
            "voltage_v_avg": round(self.voltage_v_avg, 2),
            "current_a_avg": round(self.current_a_avg, 2),
            "power_kw_avg": round(self.power_kw_avg, 3),
            "voltage_v_std": round(self.voltage_v_std, 2),
            "current_a_std": round(self.current_a_std, 2),
            "power_kw_std": round(self.power_kw_std, 3),
            "last_updated": self.last_updated,
        }


@dataclass
class StringHealthScore:
    """Health assessment for a single string."""

    string_id: str
    inverter_id: str
    timestamp: str

    # Health metrics
    health_score: float = 100.0  # 0-100, 0=perfect, 100=critical
    health_status: str = "healthy"  # healthy/warning/critical

    # Current measurements
    voltage_v: float = 45.0
    current_a: float = 5.0
    power_kw: float = 0.2
    irradiance_w_m2: float = 500.0

    # Baseline comparison
    voltage_deviation_pct: float = 0.0
    current_deviation_pct: float = 0.0
    power_deviation_pct: float = 0.0

    # Failure detection
    failure_type: Optional[str] = None  # dead, shorted, degraded, bypass_diode, healthy
    failure_confidence: float = 0.0  # 0-1

    # Recommendations
    recommendation: str = ""

    def to_dict(self) -> Dict:
        return {
            "string_id": self.string_id,
            "inverter_id": self.inverter_id,
            "timestamp": self.timestamp,
            "health": {
                "score": round(self.health_score, 1),
                "status": self.health_status,
            },
            "current_readings": {
                "voltage_v": round(self.voltage_v, 2),
                "current_a": round(self.current_a, 2),
                "power_kw": round(self.power_kw, 3),
                "irradiance_w_m2": round(self.irradiance_w_m2, 1),
            },
            "baseline_comparison": {
                "voltage_deviation_pct": round(self.voltage_deviation_pct, 2),
                "current_deviation_pct": round(self.current_deviation_pct, 2),
                "power_deviation_pct": round(self.power_deviation_pct, 2),
            },
            "failure_analysis": {
                "type": self.failure_type,
                "confidence": round(self.failure_confidence, 3),
            },
            "recommendation": self.recommendation,
        }


class StringAnalyzer:
    """Analyzes per-string MPPT performance and detects failures."""

    def __init__(self):
        """Initialize string analyzer."""
        self._baselines: Dict[str, StringBaseline] = {}
        self._anomaly_history: Dict[str, List[StringHealthScore]] = {}
        self._persistent_anomalies: Dict[str, datetime] = {}  # string_id -> first_anomaly_time

    def analyze_string_health(
        self,
        string: SolarString,
        baseline: Optional[StringBaseline] = None,
    ) -> StringHealthScore:
        """
        Analyze health of a single PV string.

        Compares current readings against 7-day baseline.

        Args:
            string: SolarString object with current readings
            baseline: Optional StringBaseline for comparison

        Returns:
            StringHealthScore with health metrics
        """
        # Get or create baseline
        if baseline is None:
            baseline = self._get_or_create_baseline(string)

        # Calculate deviations from baseline
        voltage_deviation = 0.0
        current_deviation = 0.0
        power_deviation = 0.0

        if baseline.voltage_v_avg > 0:
            voltage_deviation = abs(string.dc_voltage_v - baseline.voltage_v_avg) / baseline.voltage_v_avg

        if baseline.current_a_avg > 0:
            # Current is expected to vary with irradiance
            current_baseline_adjusted = baseline.current_a_avg * (
                string.irradiance_w_m2 / 500.0
            )  # Normalize to 500 W/m²
            current_deviation = (
                abs(string.dc_current_a - current_baseline_adjusted) / current_baseline_adjusted
                if current_baseline_adjusted > 0.1
                else 0.0
            )

        if baseline.power_kw_avg > 0:
            power_baseline_adjusted = baseline.power_kw_avg * (
                (string.irradiance_w_m2 / 500.0) ** 1.1
            )  # Power scales non-linearly
            power_deviation = (
                abs(string.dc_power_kw - power_baseline_adjusted) / power_baseline_adjusted
                if power_baseline_adjusted > 0.01
                else 0.0
            )

        # Detect failure type
        failure_type, failure_confidence = self._detect_failure_type(string, baseline)

        # Calculate health score (0=perfect, 100=critical)
        health_score = self._calculate_health_score(
            voltage_deviation,
            current_deviation,
            power_deviation,
            failure_type,
            string.irradiance_w_m2,
        )

        # Determine status
        health_status = "healthy"
        if health_score > ANOMALY_SCORE_THRESHOLDS["critical"]:
            health_status = "critical"
        elif health_score > ANOMALY_SCORE_THRESHOLDS["warning"]:
            health_status = "warning"

        # Generate recommendation
        recommendation = self._generate_recommendation(failure_type, health_score)

        health_score_obj = StringHealthScore(
            string_id=string.string_id,
            inverter_id=string.inverter_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            health_score=health_score,
            health_status=health_status,
            voltage_v=string.dc_voltage_v,
            current_a=string.dc_current_a,
            power_kw=string.dc_power_kw,
            irradiance_w_m2=string.irradiance_w_m2,
            voltage_deviation_pct=voltage_deviation * 100,
            current_deviation_pct=current_deviation * 100,
            power_deviation_pct=power_deviation * 100,
            failure_type=failure_type,
            failure_confidence=failure_confidence,
            recommendation=recommendation,
        )

        # Track anomaly persistence
        self._track_persistent_anomaly(string.string_id, health_score_obj)

        return health_score_obj

    def _detect_failure_type(
        self,
        string: SolarString,
        baseline: StringBaseline,
    ) -> Tuple[Optional[str], float]:
        """
        Detect specific string failure type.

        Returns:
            (failure_type, confidence) tuple
        """
        confidence = 0.0
        failure_type = None

        # Dead string: High voltage, no current
        if string.dc_voltage_v > DEAD_STRING_VOLTAGE_THRESHOLD and string.dc_current_a < DEAD_STRING_CURRENT_THRESHOLD:
            failure_type = "dead"
            confidence = min(1.0, (string.dc_voltage_v / 50.0) * (0.1 / (string.dc_current_a + 0.01)))

        # Shorted string: Low voltage, high current
        elif (
            string.dc_voltage_v < SHORTED_STRING_VOLTAGE_THRESHOLD
            and string.dc_current_a > SHORTED_STRING_CURRENT_THRESHOLD
        ):
            failure_type = "shorted"
            confidence = min(1.0, (string.dc_current_a / 10.0) * ((5.0 - string.dc_voltage_v) / 5.0))

        # Degraded string: Sustained power loss >20%
        elif string.dc_power_kw > 0.01:
            power_baseline_adjusted = baseline.power_kw_avg * ((string.irradiance_w_m2 / 500.0) ** 1.1)
            if power_baseline_adjusted > 0.01:
                power_loss = (power_baseline_adjusted - string.dc_power_kw) / power_baseline_adjusted
                if power_loss > DEGRADED_STRING_POWER_LOSS:
                    failure_type = "degraded"
                    confidence = min(1.0, power_loss - DEGRADED_STRING_POWER_LOSS)

        # Bypass diode failure: High voltage ripple (variance in readings)
        if string.irradiance_w_m2 > 200 and string.dc_voltage_v > baseline.voltage_v_avg * 1.1:
            # Check if we have history to detect ripple pattern
            if baseline.voltage_history and len(baseline.voltage_history) > 3:
                voltage_std = statistics.stdev(baseline.voltage_history[-5:])
                if voltage_std / baseline.voltage_v_avg > BYPASS_DIODE_VOLTAGE_RIPPLE:
                    failure_type = "bypass_diode"
                    confidence = min(1.0, (voltage_std / baseline.voltage_v_avg) - BYPASS_DIODE_VOLTAGE_RIPPLE)

        if failure_type is None:
            failure_type = "healthy"
            confidence = 1.0

        return failure_type, confidence

    def _calculate_health_score(
        self,
        voltage_deviation: float,
        current_deviation: float,
        power_deviation: float,
        failure_type: Optional[str],
        irradiance_w_m2: float,
    ) -> float:
        """
        Calculate composite health score (0=perfect, 100=critical).

        Args:
            voltage_deviation: Voltage deviation from baseline (0-1)
            current_deviation: Current deviation from baseline (0-1)
            power_deviation: Power deviation from baseline (0-1)
            failure_type: Detected failure type
            irradiance_w_m2: Current solar irradiance

        Returns:
            Health score 0-100
        """
        if irradiance_w_m2 < 100:
            # Low light, can't accurately assess health
            return 0.0

        # Base score from deviation thresholds
        score = 0.0

        # Voltage deviation: 30% weight
        if voltage_deviation > VOLTAGE_DEVIATION_THRESHOLD:
            voltage_score = min(40, (voltage_deviation - VOLTAGE_DEVIATION_THRESHOLD) * 100)
            score += voltage_score * 0.30

        # Current deviation: 30% weight
        if current_deviation > CURRENT_DEVIATION_THRESHOLD:
            current_score = min(40, (current_deviation - CURRENT_DEVIATION_THRESHOLD) * 100)
            score += current_score * 0.30

        # Power deviation: 40% weight
        if power_deviation > POWER_DEVIATION_THRESHOLD:
            power_score = min(60, (power_deviation - POWER_DEVIATION_THRESHOLD) * 100)
            score += power_score * 0.40

        # Penalty for specific failure types
        failure_penalties = {
            "dead": 100,  # Critical
            "shorted": 95,  # Critical
            "degraded": 50,  # Warning
            "bypass_diode": 70,  # Warning
            "healthy": 0,  # No penalty
        }

        failure_penalty = failure_penalties.get(failure_type, 0)
        score = max(score, failure_penalty)

        return min(100, score)

    def _generate_recommendation(self, failure_type: Optional[str], health_score: float) -> str:
        """Generate actionable recommendation based on failure type."""
        recommendations = {
            "dead": (
                "String open circuit detected. Check for: loose connections, "
                "broken modules, damaged bypass diodes. Estimated loss: -20% capacity. "
                "Action: Schedule immediate inspection."
            ),
            "shorted": (
                "String short circuit detected. Check for: moisture ingress, "
                "module damage, faulty combiner box. Risk: Fire hazard. "
                "Action: Isolate string immediately and investigate."
            ),
            "degraded": (
                "String power output 20%+ below baseline. Likely causes: "
                "partial shading, module soiling, degradation. "
                "Action: Clean modules and retest."
            ),
            "bypass_diode": (
                "Bypass diode failure suspected (voltage ripple pattern). "
                "Causes: thermal stress, manufacturing defect. "
                "Action: Schedule module replacement."
            ),
            "healthy": "String performing within normal parameters.",
        }

        base_recommendation = recommendations.get(failure_type, "Unknown condition.")

        if health_score > ANOMALY_SCORE_THRESHOLDS["critical"]:
            return f"[CRITICAL] {base_recommendation}"
        elif health_score > ANOMALY_SCORE_THRESHOLDS["warning"]:
            return f"[WARNING] {base_recommendation}"

        return base_recommendation

    def _get_or_create_baseline(self, string: SolarString) -> StringBaseline:
        """Get existing baseline or create default."""
        if string.string_id not in self._baselines:
            self._baselines[string.string_id] = StringBaseline(
                string_id=string.string_id,
                inverter_id=string.inverter_id,
                mppt_tracker=string.mppt_tracker,
                voltage_v_avg=45.0,
                current_a_avg=5.0,
                power_kw_avg=0.2,
                baseline_start=datetime.now(timezone.utc).isoformat(),
            )

        return self._baselines[string.string_id]

    def _track_persistent_anomaly(
        self,
        string_id: str,
        health_score_obj: StringHealthScore,
    ) -> None:
        """Track anomalies that persist >4h for hardware failure confirmation."""
        # Store in anomaly history
        if string_id not in self._anomaly_history:
            self._anomaly_history[string_id] = []

        self._anomaly_history[string_id].append(health_score_obj)

        # Keep only last 24 hours
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=24)
        self._anomaly_history[string_id] = [
            a for a in self._anomaly_history[string_id] if datetime.fromisoformat(a.timestamp) > cutoff_time
        ]

        # Check for persistence
        if health_score_obj.health_status != "healthy":
            if string_id not in self._persistent_anomalies:
                self._persistent_anomalies[string_id] = datetime.now(timezone.utc)
            else:
                elapsed_hours = (
                    datetime.now(timezone.utc) - self._persistent_anomalies[string_id]
                ).total_seconds() / 3600
                if elapsed_hours > ANOMALY_PERSISTENCE_HOURS:
                    logger.warning(
                        f"String {string_id} has persistent anomaly ({health_score_obj.failure_type}) "
                        f"for {elapsed_hours:.1f}h - likely hardware failure"
                    )
        else:
            # Clear persistent flag if healthy
            if string_id in self._persistent_anomalies:
                del self._persistent_anomalies[string_id]

    def track_string_degradation(
        self,
        string_id: str,
        new_power_kw: float,
        new_voltage_v: float,
        new_current_a: float,
    ) -> StringBaseline:
        """
        Update 7-day rolling baseline for a string.

        Args:
            string_id: String identifier
            new_power_kw: Latest power measurement
            new_voltage_v: Latest voltage measurement
            new_current_a: Latest current measurement

        Returns:
            Updated StringBaseline
        """
        # Get baseline
        baseline = self._baselines.get(string_id)
        if baseline is None:
            logger.warning(f"No baseline found for string {string_id}")
            return StringBaseline(
                string_id=string_id,
                inverter_id="unknown",
                mppt_tracker=0,
            )

        # Add measurements to history
        baseline.voltage_history.append(new_voltage_v)
        baseline.current_history.append(new_current_a)
        baseline.power_history.append(new_power_kw)

        # Keep only last 7 days (assuming daily measurements)
        if len(baseline.voltage_history) > 7:
            baseline.voltage_history = baseline.voltage_history[-7:]
            baseline.current_history = baseline.current_history[-7:]
            baseline.power_history = baseline.power_history[-7:]

        # Recalculate averages and std deviation
        if baseline.voltage_history:
            baseline.voltage_v_avg = statistics.mean(baseline.voltage_history)
            baseline.voltage_v_std = (
                statistics.stdev(baseline.voltage_history) if len(baseline.voltage_history) > 1 else 0.5
            )

        if baseline.current_history:
            baseline.current_a_avg = statistics.mean(baseline.current_history)
            baseline.current_a_std = (
                statistics.stdev(baseline.current_history) if len(baseline.current_history) > 1 else 0.5
            )

        if baseline.power_history:
            baseline.power_kw_avg = statistics.mean(baseline.power_history)
            baseline.power_kw_std = (
                statistics.stdev(baseline.power_history) if len(baseline.power_history) > 1 else 0.02
            )

        baseline.last_updated = datetime.now(timezone.utc).isoformat()

        logger.debug(
            f"Updated degradation baseline for {string_id}: "
            f"power={baseline.power_kw_avg:.3f}kW, "
            f"voltage={baseline.voltage_v_avg:.1f}V, "
            f"current={baseline.current_a_avg:.1f}A"
        )

        return baseline

    def get_persistent_anomalies(self) -> Dict[str, Dict]:
        """Get all strings with persistent anomalies (>4h)."""
        persistent = {}
        now = datetime.now(timezone.utc)

        for string_id, first_time in self._persistent_anomalies.items():
            elapsed_hours = (now - first_time).total_seconds() / 3600
            if elapsed_hours > ANOMALY_PERSISTENCE_HOURS:
                # Get latest anomaly for this string
                if string_id in self._anomaly_history and self._anomaly_history[string_id]:
                    latest = self._anomaly_history[string_id][-1]
                    persistent[string_id] = {
                        "string_id": string_id,
                        "failure_type": latest.failure_type,
                        "health_score": latest.health_score,
                        "persistent_hours": elapsed_hours,
                        "recommendation": latest.recommendation,
                    }

        return persistent


# === Singleton accessor ===

_string_analyzer: Optional[StringAnalyzer] = None


def get_string_analyzer() -> StringAnalyzer:
    """Get or create singleton StringAnalyzer instance."""
    global _string_analyzer
    if _string_analyzer is None:
        _string_analyzer = StringAnalyzer()
        logger.info("Initialized StringAnalyzer")
    return _string_analyzer
