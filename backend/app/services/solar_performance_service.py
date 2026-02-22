"""Solar Performance Monitoring & Diagnostics service.

Provides:
  - Performance Ratio (PR) calculation for commercial SA installations
  - Inverter peer comparison (grouped by manufacturer/model)
  - String-level MPPT anomaly detection using statistical thresholds
  - Diagnostic summary with prioritised issues and recommended actions

Pattern follows cross_system_analyzer.py for anomaly detection logic and
ai_optimizer.py for equipment grouping / peer comparison.
"""

import logging
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.models.solar import SolarInverter, SolarString
from app.services.solar_ingestion_service import get_solar_ingestion_service

logger = logging.getLogger(__name__)


# === Performance thresholds (SA commercial installations) ===

PR_THRESHOLDS = {
    "excellent": 0.85,  # >85% — top-performing
    "good": 0.75,  # 75-85% — expected range
    "acceptable": 0.65,  # 65-75% — needs attention
    "poor": 0.0,  # <65% — investigate immediately
}

# System loss factors for PR calculation
SYSTEM_LOSSES = {
    "wiring": 0.02,  # DC wiring losses
    "soiling": 0.03,  # Panel soiling (SA conditions)
    "mismatch": 0.02,  # Module mismatch
    "temperature": 0.05,  # Temperature derating (JHB average)
    "inverter": 0.03,  # Inverter conversion losses
    "clipping": 0.01,  # Inverter clipping at peak
}

# Peer comparison thresholds
PEER_DEVIATION_WARNING = 0.05  # 5% below peer mean = underperforming
PEER_DEVIATION_INVESTIGATE = 0.10  # 10% below = investigate

# String anomaly thresholds
STRING_CURRENT_DEVIATION_PCT = 0.08  # 8% current deviation from peers
STRING_VOLTAGE_DEVIATION_PCT = 0.08  # 8% voltage deviation from peers
STRING_POWER_DEVIATION_PCT = 0.10  # 10% power deviation from peers

# Cost estimation (ZAR/kWh weighted average for City Power TOU)
AVERAGE_TARIFF_ZAR_KWH = 2.85  # Blended TOU rate
HOURS_PER_MONTH = 730


# === Data models ===


@dataclass
class PerformanceMetrics:
    """Performance ratio and generation metrics for a site."""

    site_id: str
    timestamp: str
    period: str  # day, week, month

    # PR metrics
    performance_ratio: float  # 0-1
    pr_rating: str  # excellent/good/acceptable/poor
    pr_target: float  # expected PR for this installation

    # Generation
    actual_generation_kw: float
    expected_generation_kw: float
    installed_capacity_kwp: float

    # Solar resource
    peak_sun_hours: float
    system_loss_factor: float

    # Trend
    pr_trend: str = "stable"  # improving/stable/declining
    pr_7d_average: float = 0.0

    def to_dict(self) -> Dict:
        return {
            "site_id": self.site_id,
            "timestamp": self.timestamp,
            "period": self.period,
            "performance_ratio": {
                "current": round(self.performance_ratio, 4),
                "target": round(self.pr_target, 4),
                "rating": self.pr_rating,
                "trend": self.pr_trend,
                "seven_day_average": round(self.pr_7d_average, 4),
            },
            "generation": {
                "actual_kw": round(self.actual_generation_kw, 1),
                "expected_kw": round(self.expected_generation_kw, 1),
                "installed_capacity_kwp": round(self.installed_capacity_kwp, 1),
            },
            "solar_resource": {
                "peak_sun_hours": round(self.peak_sun_hours, 2),
                "system_loss_factor": round(self.system_loss_factor, 4),
            },
        }


@dataclass
class InverterComparison:
    """Peer comparison result for a single inverter."""

    inverter_id: str
    name: str
    manufacturer: str
    model: str
    plant_id: str

    # Performance
    specific_yield_kwh_kwp: float  # kWh per kWp installed
    ac_power_kw: float
    rated_power_kva: float
    efficiency_pct: float

    # Peer comparison
    peer_group: str  # e.g. "Huawei SUN2000-330KTL-H2"
    peer_group_mean_yield: float
    deviation_pct: float  # negative = underperforming
    rank: int  # 1 = best in peer group
    peer_group_size: int

    # Assessment
    status: str  # "normal", "underperforming", "investigate"
    probable_cause: str = ""
    cost_impact_monthly_zar: float = 0.0

    def to_dict(self) -> Dict:
        return {
            "inverter_id": self.inverter_id,
            "name": self.name,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "plant_id": self.plant_id,
            "specific_yield_kwh_kwp": round(self.specific_yield_kwh_kwp, 3),
            "ac_power_kw": round(self.ac_power_kw, 2),
            "rated_power_kva": round(self.rated_power_kva, 1),
            "efficiency_pct": round(self.efficiency_pct, 1),
            "peer_comparison": {
                "peer_group": self.peer_group,
                "peer_group_mean_yield": round(self.peer_group_mean_yield, 3),
                "deviation_pct": round(self.deviation_pct, 4),
                "rank": self.rank,
                "peer_group_size": self.peer_group_size,
            },
            "status": self.status,
            "probable_cause": self.probable_cause,
            "cost_impact_monthly_zar": round(self.cost_impact_monthly_zar, 0),
        }


@dataclass
class StringAnomaly:
    """Anomaly detected at the string level."""

    string_id: str
    inverter_id: str
    mppt_tracker: int
    anomaly_type: str  # string_underperform, string_open_circuit, string_short, mppt_fault
    severity: str  # info, warning, critical
    confidence: float  # 0-1

    # Measurements
    measured_value: float
    expected_value: float
    deviation_pct: float
    metric: str  # current, voltage, power

    # Context
    description: str = ""
    probable_cause: str = ""
    recommended_action: str = ""

    def to_dict(self) -> Dict:
        return {
            "string_id": self.string_id,
            "inverter_id": self.inverter_id,
            "mppt_tracker": self.mppt_tracker,
            "anomaly_type": self.anomaly_type,
            "severity": self.severity,
            "confidence": round(self.confidence, 2),
            "measured": {
                "value": round(self.measured_value, 3),
                "expected": round(self.expected_value, 3),
                "deviation_pct": round(self.deviation_pct, 4),
                "metric": self.metric,
            },
            "description": self.description,
            "probable_cause": self.probable_cause,
            "recommended_action": self.recommended_action,
        }


@dataclass
class DiagnosticIssue:
    """A single issue in the diagnostic report."""

    severity: str  # critical, warning, info
    equipment_id: str
    issue_type: str
    detail: str
    probable_cause: str
    recommended_action: str
    confidence: float
    cost_impact_monthly_zar: float = 0.0

    def to_dict(self) -> Dict:
        return {
            "severity": self.severity,
            "equipment_id": self.equipment_id,
            "type": self.issue_type,
            "detail": self.detail,
            "probable_cause": self.probable_cause,
            "recommended_action": self.recommended_action,
            "confidence": round(self.confidence, 2),
            "cost_impact_monthly_zar": round(self.cost_impact_monthly_zar, 0),
        }


@dataclass
class DiagnosticReport:
    """Full diagnostic report for a site."""

    site_id: str
    timestamp: str
    performance_ratio: Dict
    issues: List[DiagnosticIssue] = field(default_factory=list)
    summary: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "site_id": self.site_id,
            "timestamp": self.timestamp,
            "performance_ratio": self.performance_ratio,
            "issues": [i.to_dict() for i in self.issues],
            "summary": self.summary,
        }


# === Service ===


class SolarPerformanceService:
    """Solar performance monitoring and diagnostics engine.

    Calculates Performance Ratio, compares inverter peers using statistical
    methods, and detects string-level anomalies through deviation analysis.
    """

    def __init__(self):
        self._ingestion = get_solar_ingestion_service()

    # === Performance Ratio ===

    async def calculate_pr(self, site_id: str, period: str = "day") -> Optional[PerformanceMetrics]:
        """Calculate Performance Ratio for a site.

        PR = Actual Energy / (Installed Capacity x Peak Sun Hours x (1 - System Losses))

        For instantaneous calculation (demo), we use current power vs expected
        power at current solar resource level.
        """
        overview = await self._ingestion.get_site_overview(site_id)
        if not overview:
            return None

        gen = overview.get("generation", {})
        actual_kw = gen.get("total_pv_kw", 0)
        capacity_kwp = gen.get("total_capacity_kwp", 0)

        if capacity_kwp <= 0:
            return None

        # Calculate system loss factor
        total_loss = sum(SYSTEM_LOSSES.values())
        loss_factor = 1.0 - total_loss

        # Estimate current peak sun hours factor from actual generation
        # In real system this comes from pyranometer; for demo we derive it
        # from the generation-to-capacity ratio
        instantaneous_ratio = actual_kw / capacity_kwp if capacity_kwp > 0 else 0

        # Peak sun hours for JHB (annual average ~5.5 kWh/m2/day)
        # For instantaneous: solar factor is the current irradiance fraction
        # We estimate PSH from the generation ratio adjusted for losses
        if instantaneous_ratio > 0:
            estimated_solar_factor = instantaneous_ratio / loss_factor
            # Clamp to realistic range
            estimated_solar_factor = min(1.0, max(0.0, estimated_solar_factor))
        else:
            estimated_solar_factor = 0.0

        # Expected generation at current solar resource
        expected_kw = capacity_kwp * estimated_solar_factor * loss_factor

        # PR = actual / (capacity * solar_resource_factor)
        # For meaningful PR, solar resource must be non-zero
        if estimated_solar_factor > 0.05:  # At least 5% solar resource
            pr = actual_kw / (capacity_kwp * estimated_solar_factor)
        else:
            # Nighttime or very low irradiance — PR not meaningful
            pr = 0.0

        # Clamp PR to 0-1 range
        pr = min(1.0, max(0.0, pr))

        # Rate the PR
        if pr >= PR_THRESHOLDS["excellent"]:
            rating = "excellent"
        elif pr >= PR_THRESHOLDS["good"]:
            rating = "good"
        elif pr >= PR_THRESHOLDS["acceptable"]:
            rating = "acceptable"
        else:
            rating = "poor"

        # Target PR for SA commercial installation
        target_pr = 0.82

        # Trend detection (simulated — in production, compare with historical)
        pr_7d = pr * (1.0 + 0.01)  # Simulated 7-day average slightly higher
        if pr < pr_7d * 0.98:
            trend = "declining"
        elif pr > pr_7d * 1.02:
            trend = "improving"
        else:
            trend = "stable"

        # PSH estimate for the day (JHB annual average ~5.5)
        psh = 5.5 if period == "day" else 5.5 * 7 if period == "week" else 5.5 * 30

        return PerformanceMetrics(
            site_id=site_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            period=period,
            performance_ratio=pr,
            pr_rating=rating,
            pr_target=target_pr,
            actual_generation_kw=actual_kw,
            expected_generation_kw=expected_kw,
            installed_capacity_kwp=capacity_kwp,
            peak_sun_hours=psh,
            system_loss_factor=loss_factor,
            pr_trend=trend,
            pr_7d_average=pr_7d,
        )

    # === Inverter Peer Comparison ===

    async def compare_inverter_peers(self, site_id: str) -> List[InverterComparison]:
        """Compare inverters against their peer group (same manufacturer/model).

        Groups inverters by manufacturer+model, calculates specific yield
        (kWh/kWp) for each, then ranks within peer group. Flags inverters
        that deviate >5% (underperforming) or >10% (investigate) from group mean.
        """
        inverters = await self._ingestion.get_inverters(site_id)
        if not inverters:
            return []

        # Group by manufacturer + model
        peer_groups: Dict[str, List[SolarInverter]] = {}
        for inv in inverters:
            key = f"{inv.manufacturer} {inv.model}"
            peer_groups.setdefault(key, []).append(inv)

        results: List[InverterComparison] = []

        for group_key, group_inverters in peer_groups.items():
            # Calculate specific yield for each inverter in group
            yields = []
            for inv in group_inverters:
                sy = inv.daily_yield_kwh / inv.rated_power_kva if inv.rated_power_kva > 0 else 0
                yields.append((inv, sy))

            # Group statistics
            yield_values = [y for _, y in yields]
            if not yield_values:
                continue

            group_mean = statistics.mean(yield_values)
            group_stdev = statistics.stdev(yield_values) if len(yield_values) > 1 else 0

            # Rank by specific yield (highest first)
            yields.sort(key=lambda x: x[1], reverse=True)

            for rank, (inv, sy) in enumerate(yields, start=1):
                # Deviation from group mean
                deviation = (sy - group_mean) / group_mean if group_mean > 0 else 0

                # Determine status
                if deviation < -PEER_DEVIATION_INVESTIGATE:
                    status = "investigate"
                elif deviation < -PEER_DEVIATION_WARNING:
                    status = "underperforming"
                else:
                    status = "normal"

                # Probable cause and cost impact
                probable_cause = ""
                cost_impact = 0.0

                if status != "normal" and group_mean > 0:
                    lost_yield = (group_mean - sy) * inv.rated_power_kva
                    cost_impact = lost_yield * AVERAGE_TARIFF_ZAR_KWH * 30  # Monthly estimate

                    if abs(deviation) > 0.15:
                        probable_cause = (
                            "Severe underperformance — possible MPPT tracker failure or multiple string faults"
                        )
                    elif abs(deviation) > 0.10:
                        probable_cause = f"String fault on MPPT tracker — {abs(deviation) * 100:.0f}% below peer group"
                    else:
                        probable_cause = (
                            "Minor underperformance — possible soiling, partial shading, or connector degradation"
                        )

                results.append(
                    InverterComparison(
                        inverter_id=inv.inverter_id,
                        name=inv.name,
                        manufacturer=inv.manufacturer,
                        model=inv.model,
                        plant_id=inv.plant_id,
                        specific_yield_kwh_kwp=sy,
                        ac_power_kw=inv.ac_power_kw,
                        rated_power_kva=inv.rated_power_kva,
                        efficiency_pct=inv.efficiency_pct,
                        peer_group=group_key,
                        peer_group_mean_yield=group_mean,
                        deviation_pct=deviation,
                        rank=rank,
                        peer_group_size=len(group_inverters),
                        status=status,
                        probable_cause=probable_cause,
                        cost_impact_monthly_zar=cost_impact,
                    )
                )

        # Sort results: investigate first, then underperforming, then by deviation
        severity_order = {"investigate": 0, "underperforming": 1, "normal": 2}
        results.sort(key=lambda r: (severity_order.get(r.status, 3), r.deviation_pct))

        return results

    # === String-Level MPPT Anomaly Detection ===

    async def detect_string_anomalies(
        self,
        site_id: str,
        inverter_id: Optional[str] = None,
    ) -> List[StringAnomaly]:
        """Detect string-level anomalies using statistical peer comparison.

        For each inverter, reads all strings and groups by MPPT tracker.
        Compares each string's current/voltage/power against its peers on the
        same tracker. Deviations beyond threshold indicate issues.

        Anomaly types:
          - string_underperform: Power deviation >10% (soiling/shade)
          - string_open_circuit: Near-zero current with normal voltage
          - string_short: Abnormally low voltage (bypass diode failure)
          - mppt_fault: All strings on a tracker underperforming
        """
        site = self._ingestion._sites.get(site_id)
        if not site:
            return []

        anomalies: List[StringAnomaly] = []

        # Get inverter list (filtered or all)
        inverters = await self._ingestion.get_inverters(site_id)
        if inverter_id:
            inverters = [i for i in inverters if i.inverter_id == inverter_id]

        for inv in inverters:
            # Get all strings for this inverter
            detail = await self._ingestion.get_inverter_detail(site_id, inv.inverter_id)
            if not detail:
                continue

            strings_data = detail.get("strings", [])
            if not strings_data:
                continue

            # Build SolarString objects from dict data
            strings: List[SolarString] = []
            for s_dict in strings_data:
                strings.append(
                    SolarString(
                        string_id=s_dict["string_id"],
                        inverter_id=s_dict["inverter_id"],
                        mppt_tracker=s_dict["mppt_tracker"],
                        panel_count=s_dict["panel_count"],
                        panel_model=s_dict.get("panel_model", ""),
                        panel_rating_w=s_dict.get("panel_rating_w", 0),
                        dc_voltage_v=s_dict["dc_voltage_v"],
                        dc_current_a=s_dict["dc_current_a"],
                        dc_power_kw=s_dict["dc_power_kw"],
                        irradiance_w_m2=s_dict.get("irradiance_w_m2", 0),
                    )
                )

            if not strings:
                continue

            # Skip anomaly detection if no meaningful generation (nighttime)
            max_power = max(s.dc_power_kw for s in strings)
            if max_power < 0.1:
                continue

            # Group strings by MPPT tracker
            mppt_groups: Dict[int, List[SolarString]] = {}
            for s in strings:
                mppt_groups.setdefault(s.mppt_tracker, []).append(s)

            # --- Intra-MPPT comparison (strings on same tracker) ---
            for mppt_num, mppt_strings in mppt_groups.items():
                if len(mppt_strings) < 2:
                    continue

                currents = [s.dc_current_a for s in mppt_strings]
                voltages = [s.dc_voltage_v for s in mppt_strings]
                powers = [s.dc_power_kw for s in mppt_strings]

                mean_current = statistics.mean(currents) if currents else 0
                mean_voltage = statistics.mean(voltages) if voltages else 0
                mean_power = statistics.mean(powers) if powers else 0

                for s in mppt_strings:
                    # Skip strings with near-zero values (nighttime)
                    if mean_current < 0.5 or mean_power < 0.05:
                        continue

                    # Current deviation check
                    current_dev = (s.dc_current_a - mean_current) / mean_current if mean_current > 0 else 0
                    # Voltage deviation check
                    voltage_dev = (s.dc_voltage_v - mean_voltage) / mean_voltage if mean_voltage > 0 else 0
                    # Power deviation check
                    power_dev = (s.dc_power_kw - mean_power) / mean_power if mean_power > 0 else 0

                    # --- String open circuit: near-zero current, normal voltage ---
                    if s.dc_current_a < mean_current * 0.1 and s.dc_voltage_v > mean_voltage * 0.8:
                        anomalies.append(
                            StringAnomaly(
                                string_id=s.string_id,
                                inverter_id=inv.inverter_id,
                                mppt_tracker=mppt_num,
                                anomaly_type="string_open_circuit",
                                severity="critical",
                                confidence=0.92,
                                measured_value=s.dc_current_a,
                                expected_value=mean_current,
                                deviation_pct=current_dev,
                                metric="current",
                                description=(
                                    f"String {s.string_id} has near-zero current "
                                    f"({s.dc_current_a:.2f}A) with normal voltage "
                                    f"({s.dc_voltage_v:.1f}V) — likely disconnected"
                                ),
                                probable_cause="String disconnection or fuse failure",
                                recommended_action=("Check string fuse, MC4 connectors, and combiner box connections"),
                            )
                        )
                        continue  # Don't double-flag

                    # --- String short / bypass diode: abnormally low voltage ---
                    if voltage_dev < -STRING_VOLTAGE_DEVIATION_PCT and abs(current_dev) < STRING_CURRENT_DEVIATION_PCT:
                        severity = "critical" if voltage_dev < -0.15 else "warning"
                        confidence = min(0.95, 0.7 + abs(voltage_dev))
                        anomalies.append(
                            StringAnomaly(
                                string_id=s.string_id,
                                inverter_id=inv.inverter_id,
                                mppt_tracker=mppt_num,
                                anomaly_type="string_short",
                                severity=severity,
                                confidence=confidence,
                                measured_value=s.dc_voltage_v,
                                expected_value=mean_voltage,
                                deviation_pct=voltage_dev,
                                metric="voltage",
                                description=(
                                    f"String {s.string_id} voltage "
                                    f"{abs(voltage_dev) * 100:.1f}% below peers "
                                    f"({s.dc_voltage_v:.1f}V vs "
                                    f"{mean_voltage:.1f}V mean) "
                                    f"with normal current — bypass diode likely active"
                                ),
                                probable_cause="Bypass diode activated due to hot spot or cell crack",
                                recommended_action=(
                                    "IR scan panels on this string to identify hot spot; check bypass diodes"
                                ),
                            )
                        )
                        continue

                    # --- String underperformance: low power ---
                    if power_dev < -STRING_POWER_DEVIATION_PCT:
                        severity = "warning" if power_dev > -0.15 else "critical"
                        confidence = min(0.90, 0.6 + abs(power_dev))
                        anomalies.append(
                            StringAnomaly(
                                string_id=s.string_id,
                                inverter_id=inv.inverter_id,
                                mppt_tracker=mppt_num,
                                anomaly_type="string_underperform",
                                severity=severity,
                                confidence=confidence,
                                measured_value=s.dc_power_kw,
                                expected_value=mean_power,
                                deviation_pct=power_dev,
                                metric="power",
                                description=(
                                    f"String {s.string_id} generating "
                                    f"{abs(power_dev) * 100:.1f}% less than peers "
                                    f"on MPPT {mppt_num}"
                                ),
                                probable_cause=("Soiling, partial shading, or connector degradation"),
                                recommended_action=("Inspect panels for soiling/shading; check connectors and wiring"),
                            )
                        )

            # --- Cross-MPPT comparison (detect tracker-level faults) ---
            if len(mppt_groups) >= 2:
                mppt_avg_powers: Dict[int, float] = {}
                for mppt_num, mppt_strings in mppt_groups.items():
                    avg_p = statistics.mean([s.dc_power_kw for s in mppt_strings])
                    mppt_avg_powers[mppt_num] = avg_p

                overall_mean = statistics.mean(mppt_avg_powers.values())
                if overall_mean > 0.05:
                    for mppt_num, avg_p in mppt_avg_powers.items():
                        mppt_dev = (avg_p - overall_mean) / overall_mean
                        if mppt_dev < -STRING_POWER_DEVIATION_PCT:
                            # All strings on this MPPT are underperforming
                            anomalies.append(
                                StringAnomaly(
                                    string_id=f"{inv.inverter_id}-MPPT{mppt_num:02d}",
                                    inverter_id=inv.inverter_id,
                                    mppt_tracker=mppt_num,
                                    anomaly_type="mppt_fault",
                                    severity="warning",
                                    confidence=min(0.88, 0.6 + abs(mppt_dev)),
                                    measured_value=avg_p,
                                    expected_value=overall_mean,
                                    deviation_pct=mppt_dev,
                                    metric="power",
                                    description=(
                                        f"MPPT tracker {mppt_num} on "
                                        f"{inv.inverter_id} averaging "
                                        f"{abs(mppt_dev) * 100:.1f}% below "
                                        f"other trackers"
                                    ),
                                    probable_cause=(
                                        "MPPT tracker hardware fault or systematic shading on tracker inputs"
                                    ),
                                    recommended_action=(
                                        "Check MPPT tracker firmware and hardware; "
                                        "compare string performance individually"
                                    ),
                                )
                            )

        # Sort by severity
        severity_order = {"critical": 0, "warning": 1, "info": 2}
        anomalies.sort(key=lambda a: (severity_order.get(a.severity, 3), -a.confidence))

        return anomalies

    # === Diagnostic Summary ===

    async def get_diagnostic_summary(self, site_id: str) -> Optional[DiagnosticReport]:
        """Generate a comprehensive diagnostic report for a site.

        Aggregates: PR metrics, underperforming inverters, string anomalies,
        and BESS health flags into a prioritised list of issues with
        recommended actions and cost impact estimates.
        """
        # Get all components
        pr = await self.calculate_pr(site_id)
        if not pr:
            return None

        peer_comparisons = await self.compare_inverter_peers(site_id)
        string_anomalies = await self.detect_string_anomalies(site_id)
        bess = await self._ingestion.get_bess_status(site_id)

        issues: List[DiagnosticIssue] = []

        # --- PR issues ---
        if pr.performance_ratio > 0 and pr.pr_rating in ("acceptable", "poor"):
            severity = "warning" if pr.pr_rating == "acceptable" else "critical"
            issues.append(
                DiagnosticIssue(
                    severity=severity,
                    equipment_id=site_id,
                    issue_type="low_performance_ratio",
                    detail=(f"Site PR at {pr.performance_ratio * 100:.1f}% (target {pr.pr_target * 100:.1f}%)"),
                    probable_cause=("System-wide degradation, soiling accumulation, or inverter efficiency loss"),
                    recommended_action=(
                        "Review inverter peer comparison for specific underperformers; schedule panel cleaning"
                    ),
                    confidence=0.80,
                    cost_impact_monthly_zar=self._estimate_pr_loss_cost(pr),
                )
            )

        # --- Inverter peer comparison issues ---
        for comp in peer_comparisons:
            if comp.status != "normal":
                severity = "warning" if comp.status == "underperforming" else "critical"
                issues.append(
                    DiagnosticIssue(
                        severity=severity,
                        equipment_id=comp.inverter_id,
                        issue_type="inverter_underperformance",
                        detail=(f"{abs(comp.deviation_pct) * 100:.0f}% below {comp.peer_group} peer group mean"),
                        probable_cause=comp.probable_cause,
                        recommended_action=(
                            f"Inspect strings on {comp.inverter_id}, check for soiling or disconnection"
                        ),
                        confidence=min(0.90, 0.7 + abs(comp.deviation_pct)),
                        cost_impact_monthly_zar=comp.cost_impact_monthly_zar,
                    )
                )

        # --- String anomalies ---
        for anomaly in string_anomalies:
            issues.append(
                DiagnosticIssue(
                    severity=anomaly.severity,
                    equipment_id=anomaly.string_id,
                    issue_type=anomaly.anomaly_type,
                    detail=anomaly.description,
                    probable_cause=anomaly.probable_cause,
                    recommended_action=anomaly.recommended_action,
                    confidence=anomaly.confidence,
                    cost_impact_monthly_zar=0.0,  # String-level cost included in inverter
                )
            )

        # --- BESS health flags ---
        if bess:
            # Cell imbalance warning
            if bess.cell_imbalance_mv > 50:
                issues.append(
                    DiagnosticIssue(
                        severity="warning",
                        equipment_id=bess.container_id,
                        issue_type="bess_cell_imbalance",
                        detail=(f"Cell imbalance {bess.cell_imbalance_mv:.0f}mV (threshold 50mV)"),
                        probable_cause=("Cell aging variance or BMS balancing failure"),
                        recommended_action=(
                            "Run BMS active balancing cycle; if persists, inspect rack for degraded cells"
                        ),
                        confidence=0.75,
                    )
                )

            # SOH degradation
            if bess.soh_pct < 90:
                issues.append(
                    DiagnosticIssue(
                        severity="warning" if bess.soh_pct >= 80 else "critical",
                        equipment_id=bess.container_id,
                        issue_type="bess_soh_degradation",
                        detail=f"BESS State of Health at {bess.soh_pct:.1f}%",
                        probable_cause="Calendar/cycle aging of LFP cells",
                        recommended_action=("Plan capacity replacement; adjust dispatch to reduce depth of discharge"),
                        confidence=0.85,
                    )
                )

        # Sort issues by severity then cost impact
        severity_order = {"critical": 0, "warning": 1, "info": 2}
        issues.sort(
            key=lambda i: (
                severity_order.get(i.severity, 3),
                -i.cost_impact_monthly_zar,
            )
        )

        # Build summary counts
        summary = {
            "total_issues": len(issues),
            "critical": sum(1 for i in issues if i.severity == "critical"),
            "warning": sum(1 for i in issues if i.severity == "warning"),
            "info": sum(1 for i in issues if i.severity == "info"),
            "total_monthly_cost_impact_zar": round(sum(i.cost_impact_monthly_zar for i in issues), 0),
        }

        return DiagnosticReport(
            site_id=site_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            performance_ratio={
                "current": round(pr.performance_ratio, 4),
                "target": round(pr.pr_target, 4),
                "trend": pr.pr_trend,
            },
            issues=issues,
            summary=summary,
        )

    # === Helpers ===

    def _estimate_pr_loss_cost(self, pr: PerformanceMetrics) -> float:
        """Estimate monthly cost of PR being below target."""
        if pr.performance_ratio >= pr.pr_target:
            return 0.0
        pr_gap = pr.pr_target - pr.performance_ratio
        lost_kwh_per_day = pr.installed_capacity_kwp * pr.peak_sun_hours * pr_gap
        return lost_kwh_per_day * AVERAGE_TARIFF_ZAR_KWH * 30


# === Singleton ===

_solar_performance_service: Optional[SolarPerformanceService] = None


def get_solar_performance_service() -> SolarPerformanceService:
    """Get the singleton solar performance service instance."""
    global _solar_performance_service
    if _solar_performance_service is None:
        _solar_performance_service = SolarPerformanceService()
    return _solar_performance_service
