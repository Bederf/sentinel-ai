"""
Energy Rules Engine Models

Defines data structures for the rules-based energy optimization system.
"""

from pydantic import BaseModel
from typing import Optional, List, Dict
from enum import Enum


class LearningCurvePhase(str, Enum):
    """Learning curve phases for ML confidence progression."""
    PHASE_1_LEARNING = "phase_1_learning"  # Months 1-2, confidence 78-80%
    PHASE_2_TUNING = "phase_2_tuning"      # Months 3-6, confidence 82-88%
    PHASE_3_MATURE = "phase_3_mature"      # Months 7-12, confidence 90-92%
    PHASE_4_STABLE = "phase_4_stable"      # 12+ months, confidence 92%


class BuildingState(BaseModel):
    """Current building operational state for rules evaluation."""
    
    current_hour: int  # 0-23
    occupancy_percent: int  # 0-100%
    daylight_lux: int  # 0-1000+ lux
    chiller_load_percent: int  # 0-100%
    peak_demand_kw: float  # Current peak demand in kW
    tariff_band: str  # "peak" | "standard" | "off_peak"
    ambient_temp_c: float  # Ambient temperature in Celsius
    site_id: str  # Site identifier
    date: str  # ISO format date


class RuleResult(BaseModel):
    """Result of a single rule evaluation."""
    
    rule_id: str  # "chiller_staging", "thermal_precooling", etc.
    description: str  # Human-readable rule description
    savings_percent: float  # Savings percentage (0-35%)
    active: bool  # Whether rule fired and contributed savings
    reason: str  # Explanation of why rule is/isn't active
    conditions_met: Dict[str, bool]  # Which conditions were satisfied


class SystemBreakdown(BaseModel):
    """Savings breakdown by system type."""
    
    hvac_kwh: float  # HVAC savings in kWh
    lighting_kwh: float  # Lighting savings in kWh
    power_kwh: float  # Power/electrical savings in kWh


class RulesEngineOutput(BaseModel):
    """Complete output from rules engine evaluation."""
    
    optimised_kwh: float  # Total optimized consumption (baseline minus savings)
    delta_kwh: float  # Savings in kWh
    delta_percent: float  # Savings as percentage (0-35%)
    delta_zar: float  # Estimated savings in ZAR
    by_system: SystemBreakdown  # Breakdown by HVAC/Lighting/Power
    rules_applied: List[RuleResult]  # List of all evaluated rules
    confidence: float  # ML confidence level (0.78-0.92)
    method: str  # "rules_based" | "hardcoded"
    learning_phase: LearningCurvePhase  # Current learning curve phase
