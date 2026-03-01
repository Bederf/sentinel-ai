"""
Energy Rules Engine Service

Implements 5 optimization rules for energy consumption prediction.
Uses building state (occupancy, daylight, temperature, tariff) to calculate
realistic energy savings ranging from 0-35%.

Rules:
1. Chiller staging optimization (5% max) - reduces compressor load
2. Thermal pre-cooling (3% max) - shifts load to off-peak hours
3. Occupancy-based HVAC (2% max) - reduces ventilation when unoccupied
4. Daylight harvesting (4% max, DALI-only) - reduces artificial lighting
5. Peak load shaving (2% max) - shifts load away from peak tariff
"""

from datetime import date
from typing import Optional, List
from app.models.energy_rules import BuildingState, RuleResult, RulesEngineOutput, SystemBreakdown, LearningCurvePhase
from app.core.site_resolver import get_primary_site

# ==================== RULE THRESHOLDS (Tunable) ====================

# Rule 1: Chiller Staging Optimization
CHILLER_STAGING_THRESHOLD = 60  # % load - only applies above 60%
CHILLER_STAGING_MAX_SAVINGS = 5.0  # %
CHILLER_STAGING_SCALE = CHILLER_STAGING_MAX_SAVINGS / (100 - CHILLER_STAGING_THRESHOLD)

# Rule 2: Thermal Pre-Cooling
PRECOOLING_TEMP_THRESHOLD = 20  # °C - only applies above 20°C
PRECOOLING_MAX_SAVINGS = 3.0  # %
PRECOOLING_TEMP_MAX = 35  # °C - scale linearly to this
PRECOOLING_SCALE = PRECOOLING_MAX_SAVINGS / (PRECOOLING_TEMP_MAX - PRECOOLING_TEMP_THRESHOLD)

# Rule 3: Occupancy-Based HVAC
OCCUPANCY_HVAC_THRESHOLD = 30  # % - only applies below 30%
OCCUPANCY_HVAC_MAX_SAVINGS = 2.0  # %
OCCUPANCY_HVAC_SCALE = OCCUPANCY_HVAC_MAX_SAVINGS / OCCUPANCY_HVAC_THRESHOLD

# Rule 4: Daylight Harvesting (DALI only)
DAYLIGHT_HARVESTING_THRESHOLD = 500  # lux
DAYLIGHT_HARVESTING_MAX = 1000  # lux - scale to this
DAYLIGHT_HARVESTING_MAX_SAVINGS = 4.0  # %
DAYLIGHT_HARVESTING_SCALE = DAYLIGHT_HARVESTING_MAX_SAVINGS / (DAYLIGHT_HARVESTING_MAX - DAYLIGHT_HARVESTING_THRESHOLD)
DAYLIGHT_HARVESTING_HOURS = (7, 18)  # Active 07:00-18:00

# Rule 5: Peak Load Shaving
PEAK_DEMAND_THRESHOLD = 100  # kW
PEAK_DEMAND_MAX = 200  # kW - scale to this
PEAK_LOAD_SHAVING_MAX_SAVINGS = 2.0  # %
PEAK_LOAD_SHAVING_SCALE = PEAK_LOAD_SHAVING_MAX_SAVINGS / (PEAK_DEMAND_MAX - PEAK_DEMAND_THRESHOLD)

# System Allocation: How to distribute savings across HVAC/Lighting/Power
SYSTEM_ALLOCATION = {
    "chiller_staging": {"hvac": 1.0, "lighting": 0.0, "power": 0.0},
    "thermal_precooling": {"hvac": 1.0, "lighting": 0.0, "power": 0.0},
    "occupancy_hvac": {"hvac": 0.85, "lighting": 0.0, "power": 0.15},
    "daylight_harvesting": {"hvac": 0.0, "lighting": 0.9, "power": 0.1},
    "peak_load_shaving": {"hvac": 0.4, "lighting": 0.3, "power": 0.3},
}

# Deployment date for learning curve calculation (default)
DEFAULT_DEPLOYMENT_DATE = date(2025, 1, 1)

# Global singleton instance
_energy_rules_engine: Optional["EnergyRulesEngine"] = None


class EnergyRulesEngine:
    """
    Rules-based energy optimization engine.

    Evaluates 5 rules against building state to calculate realistic
    energy savings (0-35%) with transparent reasoning.
    """

    def __init__(self, site_id: str | None = None, deployment_date: Optional[date] = None):
        """Initialize rules engine.

        Args:
            site_id: Site identifier
            deployment_date: When SENTINEL deployment began (for learning curve)
                           If None, tries to get from lifecycle orchestrator,
                           then falls back to DEFAULT_DEPLOYMENT_DATE
        """
        self.site_id = site_id or get_primary_site() or "unknown"

        # Get deployment date, trying orchestrator first
        if deployment_date is None:
            try:
                from app.services.lifecycle_orchestrator import get_lifecycle_orchestrator

                orchestrator = get_lifecycle_orchestrator()
                if orchestrator.simulation_start_time:
                    deployment_date = orchestrator.simulation_start_time.date()
            except Exception:
                pass

        # Final fallback
        if deployment_date is None:
            deployment_date = DEFAULT_DEPLOYMENT_DATE

        self.deployment_date = deployment_date

    def evaluate_rules(
        self, building_state: BuildingState, active_modules: List[str], baseline_kwh: float
    ) -> RulesEngineOutput:
        """Evaluate all 5 rules and calculate total savings.

        Args:
            building_state: Current operational state
            active_modules: List of active module types (e.g., ["solar", "dali", "hvac"])
            baseline_kwh: Baseline energy consumption (kWh) to calculate delta

        Returns:
            RulesEngineOutput with all rules evaluated and totals calculated
        """
        # Evaluate each rule
        rule_results = [
            self._evaluate_rule_1_chiller_staging(building_state),
            self._evaluate_rule_2_thermal_precooling(building_state),
            self._evaluate_rule_3_occupancy_hvac(building_state),
            self._evaluate_rule_4_daylight_harvesting(building_state, active_modules),
            self._evaluate_rule_5_peak_load_shaving(building_state),
        ]

        # Sum savings from active rules (capped at 35%)
        total_savings_percent = sum(r.savings_percent for r in rule_results)
        total_savings_percent = min(total_savings_percent, 35.0)

        # Calculate kWh and ZAR savings
        delta_kwh = baseline_kwh * (total_savings_percent / 100)
        delta_zar = delta_kwh * 5.0  # R5/kWh rate

        # Calculate learning curve confidence
        confidence = self._calculate_learning_curve_confidence(date.today())
        learning_phase = self._get_learning_phase(date.today())

        # Calculate system breakdown using allocation matrix
        by_system = self._calculate_system_breakdown(rule_results, delta_kwh)

        return RulesEngineOutput(
            optimised_kwh=baseline_kwh - delta_kwh,
            delta_kwh=round(delta_kwh, 2),
            delta_percent=round(total_savings_percent, 1),
            delta_zar=round(delta_zar, 2),
            by_system=by_system,
            rules_applied=rule_results,
            confidence=round(confidence, 3),
            method="rules_based",
            learning_phase=learning_phase,
        )

    # ==================== RULE IMPLEMENTATIONS ====================

    def _evaluate_rule_1_chiller_staging(self, state: BuildingState) -> RuleResult:
        """Rule 1: Chiller staging optimization (5% max).

        Reduces compressor load by optimizing staging sequence when
        chiller load is high (>60%).
        """
        if state.chiller_load_percent <= CHILLER_STAGING_THRESHOLD:
            return RuleResult(
                rule_id="chiller_staging",
                description="Chiller staging optimization reduces compressor load",
                savings_percent=0.0,
                active=False,
                reason=f"Chiller load {state.chiller_load_percent}% is below threshold {CHILLER_STAGING_THRESHOLD}%",
                conditions_met={"chiller_load_high": False},
            )

        # Scale linearly from 60% → 0%, 100% → 5%
        excess_load = state.chiller_load_percent - CHILLER_STAGING_THRESHOLD
        savings = excess_load * CHILLER_STAGING_SCALE
        savings = min(savings, CHILLER_STAGING_MAX_SAVINGS)

        return RuleResult(
            rule_id="chiller_staging",
            description="Chiller staging optimization reduces compressor load",
            savings_percent=round(savings, 2),
            active=True,
            reason=f"Chiller load {state.chiller_load_percent}% triggers optimization",
            conditions_met={"chiller_load_high": True},
        )

    def _evaluate_rule_2_thermal_precooling(self, state: BuildingState) -> RuleResult:
        """Rule 2: Thermal pre-cooling (3% max).

        Shifts cooling load to off-peak hours when tariff is favorable
        and ambient temperature is high.
        """
        conditions_met = {
            "off_peak": state.tariff_band == "off_peak",
            "high_temp": state.ambient_temp_c > PRECOOLING_TEMP_THRESHOLD,
        }

        if not all(conditions_met.values()):
            reason = "Conditions not met: "
            if not conditions_met["off_peak"]:
                reason += "not off-peak; "
            if not conditions_met["high_temp"]:
                reason += f"temp {state.ambient_temp_c}°C below {PRECOOLING_TEMP_THRESHOLD}°C"

            return RuleResult(
                rule_id="thermal_precooling",
                description="Thermal pre-cooling shifts load to off-peak hours",
                savings_percent=0.0,
                active=False,
                reason=reason.strip("; "),
                conditions_met=conditions_met,
            )

        # Scale linearly from 20°C → 0%, 35°C → 3%
        excess_temp = state.ambient_temp_c - PRECOOLING_TEMP_THRESHOLD
        excess_temp = min(excess_temp, PRECOOLING_TEMP_MAX - PRECOOLING_TEMP_THRESHOLD)
        savings = excess_temp * PRECOOLING_SCALE

        return RuleResult(
            rule_id="thermal_precooling",
            description="Thermal pre-cooling shifts load to off-peak hours",
            savings_percent=round(savings, 2),
            active=True,
            reason=f"Off-peak + temp {state.ambient_temp_c}°C triggers pre-cooling",
            conditions_met=conditions_met,
        )

    def _evaluate_rule_3_occupancy_hvac(self, state: BuildingState) -> RuleResult:
        """Rule 3: Occupancy-based HVAC (2% max).

        Reduces ventilation and conditioning when occupancy is low (<30%).
        """
        conditions_met = {"low_occupancy": state.occupancy_percent < OCCUPANCY_HVAC_THRESHOLD}

        if not conditions_met["low_occupancy"]:
            return RuleResult(
                rule_id="occupancy_hvac",
                description="Occupancy-based HVAC reduces ventilation when empty",
                savings_percent=0.0,
                active=False,
                reason=f"Occupancy {state.occupancy_percent}% above threshold {OCCUPANCY_HVAC_THRESHOLD}%",
                conditions_met=conditions_met,
            )

        # Scale inversely: 30% → 0%, 0% → 2%
        savings = (OCCUPANCY_HVAC_THRESHOLD - state.occupancy_percent) * OCCUPANCY_HVAC_SCALE

        return RuleResult(
            rule_id="occupancy_hvac",
            description="Occupancy-based HVAC reduces ventilation when empty",
            savings_percent=round(savings, 2),
            active=True,
            reason=f"Low occupancy {state.occupancy_percent}% triggers HVAC reduction",
            conditions_met=conditions_met,
        )

    def _evaluate_rule_4_daylight_harvesting(self, state: BuildingState, active_modules: List[str]) -> RuleResult:
        """Rule 4: Daylight harvesting (4% max, DALI-only).

        Reduces artificial lighting when daylight is sufficient.
        Only activates if DALI/Lighting module is installed and active.
        """
        # Normalize module names to lowercase
        active_modules_lower = [m.lower() for m in active_modules]
        # Check for either "dali" or "lighting" (lighting module includes DALI)
        dali_active = "dali" in active_modules_lower or "lighting" in active_modules_lower

        # Check DALI module first
        if not dali_active:
            return RuleResult(
                rule_id="daylight_harvesting",
                description="DALI daylight harvesting reduces artificial lighting",
                savings_percent=0.0,
                active=False,
                reason="DALI module not active",
                conditions_met={"dali_active": False, "sufficient_daylight": False, "daytime": False},
            )

        # Check other conditions
        conditions_met = {
            "dali_active": True,
            "sufficient_daylight": state.daylight_lux > DAYLIGHT_HARVESTING_THRESHOLD,
            "daytime": DAYLIGHT_HARVESTING_HOURS[0] <= state.current_hour < DAYLIGHT_HARVESTING_HOURS[1],
        }

        if not all(v for k, v in conditions_met.items() if k != "dali_active"):
            reason = "DALI active but conditions not met: "
            if not conditions_met["sufficient_daylight"]:
                reason += f"daylight {state.daylight_lux} lux below {DAYLIGHT_HARVESTING_THRESHOLD} lux; "
            if not conditions_met["daytime"]:
                reason += (
                    f"outside daytime hours "
                    f"({DAYLIGHT_HARVESTING_HOURS[0]:02d}:00-{DAYLIGHT_HARVESTING_HOURS[1]:02d}:00); "
                )

            return RuleResult(
                rule_id="daylight_harvesting",
                description="DALI daylight harvesting reduces artificial lighting",
                savings_percent=0.0,
                active=False,
                reason=reason.strip("; "),
                conditions_met=conditions_met,
            )

        # Scale: 500 lux → 0%, 1000 lux → 4%
        excess_lux = state.daylight_lux - DAYLIGHT_HARVESTING_THRESHOLD
        excess_lux = min(excess_lux, DAYLIGHT_HARVESTING_MAX - DAYLIGHT_HARVESTING_THRESHOLD)
        savings = excess_lux * DAYLIGHT_HARVESTING_SCALE

        return RuleResult(
            rule_id="daylight_harvesting",
            description="DALI daylight harvesting reduces artificial lighting",
            savings_percent=round(savings, 2),
            active=True,
            reason=f"DALI + sufficient daylight {state.daylight_lux} lux at {state.current_hour:02d}:00",
            conditions_met=conditions_met,
        )

    def _evaluate_rule_5_peak_load_shaving(self, state: BuildingState) -> RuleResult:
        """Rule 5: Peak load shaving (2% max).

        Reduces non-critical loads during peak tariff hours and
        high demand periods to avoid demand charges.
        """
        conditions_met = {
            "peak_tariff": state.tariff_band == "peak",
            "high_demand": state.peak_demand_kw > PEAK_DEMAND_THRESHOLD,
        }

        if not all(conditions_met.values()):
            reason = "Conditions not met: "
            if not conditions_met["peak_tariff"]:
                reason += f"tariff {state.tariff_band} is not peak; "
            if not conditions_met["high_demand"]:
                reason += f"demand {state.peak_demand_kw:.1f} kW below threshold {PEAK_DEMAND_THRESHOLD} kW"

            return RuleResult(
                rule_id="peak_load_shaving",
                description="Peak load shaving reduces non-critical loads",
                savings_percent=0.0,
                active=False,
                reason=reason.strip("; "),
                conditions_met=conditions_met,
            )

        # Scale: 100 kW → 0%, 200 kW → 2%
        excess_demand = state.peak_demand_kw - PEAK_DEMAND_THRESHOLD
        excess_demand = min(excess_demand, PEAK_DEMAND_MAX - PEAK_DEMAND_THRESHOLD)
        savings = excess_demand * PEAK_LOAD_SHAVING_SCALE

        return RuleResult(
            rule_id="peak_load_shaving",
            description="Peak load shaving reduces non-critical loads",
            savings_percent=round(savings, 2),
            active=True,
            reason=f"Peak tariff + high demand {state.peak_demand_kw:.1f} kW triggers shaving",
            conditions_met=conditions_met,
        )

    # ==================== LEARNING CURVE & BREAKDOWN ====================

    def _calculate_learning_curve_confidence(self, current_date: date) -> float:
        """Calculate ML confidence based on deployment duration.

        Progression:
        - Phase 1 (1-2 months): 78-80% (learning period)
        - Phase 2 (3-6 months): 82-88% (tuning with data)
        - Phase 3 (7-12 months): 90-92% (mature optimization)
        - Phase 4 (12+ months): 92% (stable)

        Args:
            current_date: Current date for calculation

        Returns:
            Confidence level as fraction (0.78-0.92)
        """
        months_deployed = (current_date - self.deployment_date).days / 30.0

        if months_deployed <= 0:
            return 0.78
        elif months_deployed <= 2:
            # Phase 1: 78% + 1% per month
            return 0.78 + min(months_deployed * 0.01, 0.02)
        elif months_deployed <= 6:
            # Phase 2: 80% + 2% per month (82-88%)
            return 0.80 + min((months_deployed - 2) * 0.02, 0.08)
        elif months_deployed <= 12:
            # Phase 3: 88% + 0.33% per month (88-92%)
            return 0.88 + min((months_deployed - 6) * 0.0067, 0.04)
        else:
            # Phase 4: Stable at 92%
            return 0.92

    def _get_learning_phase(self, current_date: date) -> LearningCurvePhase:
        """Get current learning curve phase."""
        months_deployed = (current_date - self.deployment_date).days / 30.0

        if months_deployed <= 2:
            return LearningCurvePhase.PHASE_1_LEARNING
        elif months_deployed <= 6:
            return LearningCurvePhase.PHASE_2_TUNING
        elif months_deployed <= 12:
            return LearningCurvePhase.PHASE_3_MATURE
        else:
            return LearningCurvePhase.PHASE_4_STABLE

    def _calculate_system_breakdown(self, rules: List[RuleResult], total_delta_kwh: float) -> SystemBreakdown:
        """Allocate savings to HVAC/Lighting/Power systems.

        Uses SYSTEM_ALLOCATION matrix to distribute each rule's
        savings proportionally across systems.
        """
        hvac_kwh = 0.0
        lighting_kwh = 0.0
        power_kwh = 0.0

        for rule in rules:
            if not rule.active:
                continue

            rule_kwh = total_delta_kwh * (rule.savings_percent / 100)
            allocation = SYSTEM_ALLOCATION.get(rule.rule_id, {})

            hvac_kwh += rule_kwh * allocation.get("hvac", 0.0)
            lighting_kwh += rule_kwh * allocation.get("lighting", 0.0)
            power_kwh += rule_kwh * allocation.get("power", 0.0)

        return SystemBreakdown(
            hvac_kwh=round(hvac_kwh, 2), lighting_kwh=round(lighting_kwh, 2), power_kwh=round(power_kwh, 2)
        )


def get_energy_rules_engine(site_id: str | None = None, deployment_date: Optional[date] = None) -> EnergyRulesEngine:
    """Get or create singleton rules engine instance.

    Args:
        site_id: Site identifier
        deployment_date: Optional deployment date for learning curve
                        If None, tries to get from lifecycle orchestrator,
                        then falls back to DEFAULT_DEPLOYMENT_DATE

    Returns:
        EnergyRulesEngine singleton instance
    """
    global _energy_rules_engine

    if deployment_date is None and _energy_rules_engine is None:
        try:
            from app.services.lifecycle_orchestrator import get_lifecycle_orchestrator

            orchestrator = get_lifecycle_orchestrator()
            if orchestrator.simulation_start_time:
                deployment_date = orchestrator.simulation_start_time.date()
        except Exception:
            pass

    if _energy_rules_engine is None or _energy_rules_engine.site_id != site_id:
        _energy_rules_engine = EnergyRulesEngine(site_id=site_id, deployment_date=deployment_date)

    return _energy_rules_engine
