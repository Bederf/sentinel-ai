"""
24-Hour Building Lifecycle Orchestrator

Simulates a complete building day with:
- AI optimization adjustments
- Equipment degradation and faults
- Alert generation and Sentry notifications
- Technician dispatch and repair
- Service feedback and health restoration

Time compression: 24 hours → configurable (default 24 minutes)
"""

import asyncio
import contextlib
import logging
import math
import random
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, StrEnum
from typing import Any

from app.core.site_resolver import get_primary_site_code, normalize_site_id
from app.database.repositories.equipment_repository import EquipmentRepository
from app.database.repositories.prediction_repository import PredictionRepository
from app.database.repositories.work_order_repository import get_work_order_repository
from app.services.building_schedule import (
    BuildingState,
    ChilledWaterModel,
    HVACMode,
    ScheduleState,
    SiteSchedule,
)
from app.services.cost_validation_engine import get_cost_validation_engine
from app.services.device_control_service import get_device_control_service
from app.services.equipment_json_loader import load_site_equipment
from app.services.feedback_collection_service import (
    FeedbackItemType,
    get_feedback_collection_service,
)
from app.services.occupancy_profile_service import calculate_building_occupancy_percent, calculate_zone_occupancy
from app.services.power_meter_validation_engine import get_power_meter_validation_engine
from app.services.seasonal_modeler import SeasonalModeler
from app.services.sentinel_alert_engine import AlertContext, SentinelAlertEngine
from app.services.sentinel_data_sync import get_sentinel_data_sync
from app.services.simulation_persistence import get_simulation_persistence
from app.services.site_capacity_service import get_site_capacity_service
from app.services.site_holiday_service import get_site_holiday_service
from app.services.sustainability_metrics_collector import SustainabilityMetricsCollector
from app.services.thermal_simulation_engine import update_simulation_temperatures

logger = logging.getLogger(__name__)


class SimulatedHour(int, Enum):
    """Hours of the simulated day."""

    MIDNIGHT = 0
    EARLY_MORNING = 6
    MORNING_START = 8
    MID_MORNING = 10
    NOON = 12
    AFTERNOON = 14
    LATE_AFTERNOON = 16
    EVENING = 18
    NIGHT = 22


class EventType(StrEnum):
    """Types of lifecycle events."""

    BUILDING_WAKE = "building_wake"
    OCCUPANCY_INCREASE = "occupancy_increase"
    PEAK_LOAD = "peak_load"
    EQUIPMENT_FAULT = "equipment_fault"
    ALERT_GENERATED = "alert_generated"
    WORK_ORDER_CREATED = "work_order_created"
    TECHNICIAN_DISPATCHED = "technician_dispatched"
    REPAIR_COMPLETED = "repair_completed"
    FEEDBACK_SUBMITTED = "feedback_submitted"
    HEALTH_RESTORED = "health_restored"
    ALERT_RESOLVED = "alert_resolved"
    ALERT_CREATED = "alert_created"
    HEALTH_DEGRADED = "health_degraded"
    OCCUPANCY_DECREASE = "occupancy_decrease"
    NIGHT_MODE = "night_mode"
    AI_OPTIMIZATION = "ai_optimization"
    SETPOINT_CHANGE = "setpoint_change"
    SAFETY_VIOLATION = "safety_violation"
    SHADOW_WRITE = "shadow_write"


class OperationMode(StrEnum):
    """Building operation modes for comparison."""

    HVAC_ONLY = "hvac_only"
    HVAC_DALI = "hvac_dali"
    HVAC_DALI_SENTINEL = "hvac_dali_sentinel"
    SOLAR_BESS_BASELINE = "solar_bess_baseline"
    SOLAR_BESS_SENTINEL = "solar_bess_sentinel"
    FULL_SENTINEL = "full_sentinel"  # HVAC + DALI + Solar + BESS combined


@dataclass
class LifecycleEvent:
    """A single event in the building lifecycle."""

    timestamp: datetime
    simulated_hour: int
    event_type: EventType
    equipment_id: str | None = None
    equipment_name: str | None = None
    description: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    success: bool = True


@dataclass
class ScenarioConfig:
    """Configuration for a simulation scenario."""

    name: str
    description: str
    demo_mode: bool = False
    fault_probability: float = 0.3  # 30% chance of fault during day
    fault_hour: int | None = None  # Specific hour for fault (None = random)
    fault_equipment_type: str | None = None  # Specific type to fault
    auto_repair: bool = True  # Automatically simulate technician repair
    repair_delay_hours: int = 2  # Hours after fault before repair
    optimization_enabled: bool = True
    sentry_notifications: bool = True
    operation_mode: OperationMode | None = None


# Active scenarios — only sentinel_annual is exposed in /api/lifecycle/scenarios
SCENARIOS = {
    "sentinel_annual": ScenarioConfig(
        name="SENTINEL Full Building Simulation (365 days)",
        description=(
            "Full-year simulation: HVAC + DALI + Solar 3.9 MWp + BESS 5 MWh + "
            "City Power TOU arbitrage, South African seasonal variations, "
            "temperature cycles, rainfall patterns, occupancy variations, "
            "and seasonal fault probabilities"
        ),
        operation_mode=OperationMode.FULL_SENTINEL,
        fault_probability=0.05,
        auto_repair=True,
        repair_delay_hours=4,
        optimization_enabled=True,
    ),
}

# Backward-compatible aliases — MUST stay: existing DB rows reference these old names
SCENARIOS["grant_hvac_dali_ai_annual"] = SCENARIOS["sentinel_annual"]
SCENARIOS["grant_solar_bess_ai_annual"] = SCENARIOS["sentinel_annual"]

# Archived scenarios — kept for reference and backward-compatible API calls, not listed in /scenarios
ARCHIVED_SCENARIOS = {
    "normal_day": ScenarioConfig(
        name="Normal Day",
        description="Typical building operations with no major issues",
        fault_probability=0.1,
        auto_repair=True,
    ),
    "fault_day": ScenarioConfig(
        name="Fault Day",
        description="A day with equipment fault, alert, repair cycle",
        fault_probability=1.0,
        fault_hour=11,  # Fault at 11am during peak
        auto_repair=True,
        repair_delay_hours=2,
    ),
    "chiller_failure": ScenarioConfig(
        name="Chiller Failure",
        description="Chiller develops fault requiring urgent repair",
        fault_probability=1.0,
        fault_hour=10,
        fault_equipment_type="chiller",
        auto_repair=True,
        repair_delay_hours=3,
    ),
    "multi_fault": ScenarioConfig(
        name="Multiple Faults",
        description="Stressful day with multiple equipment issues",
        fault_probability=1.0,
        fault_hour=9,
        auto_repair=True,
        repair_delay_hours=1,
    ),
    "maintenance_day": ScenarioConfig(
        name="Maintenance Day",
        description="Scheduled maintenance with controlled downtime",
        fault_probability=0.0,
        auto_repair=False,
        optimization_enabled=True,
    ),
    "grant_hvac_only_7day": ScenarioConfig(
        name="Grant Demo: HVAC Only (7 days)",
        description="7-day HVAC baseline for Grant demo - AC runs all day",
        demo_mode=False,
        operation_mode=OperationMode.HVAC_ONLY,
        fault_probability=0.0,
        optimization_enabled=False,
    ),
    "grant_hvac_dali_7day": ScenarioConfig(
        name="Grant Demo: HVAC + DALI (7 days)",
        description="7-day reactive occupancy control for Grant demo",
        demo_mode=False,
        operation_mode=OperationMode.HVAC_DALI,
        fault_probability=0.0,
        optimization_enabled=False,
    ),
    "grant_hvac_dali_ai_7day": ScenarioConfig(
        name="Grant Demo: HVAC + DALI + Sentinel AI (7 days)",
        description="7-day predictive AI control for Grant demo",
        demo_mode=False,
        operation_mode=OperationMode.HVAC_DALI_SENTINEL,
        fault_probability=0.0,
        optimization_enabled=True,
    ),
    "solar_bess_baseline_7day": ScenarioConfig(
        name="Solar + BESS: Baseline (7 days)",
        description="7-day building with 40kWp solar + 50kWh battery, reactive control",
        operation_mode=OperationMode.SOLAR_BESS_BASELINE,
        fault_probability=0.0,
        optimization_enabled=False,
    ),
    "solar_bess_sentinel_7day": ScenarioConfig(
        name="Solar + BESS: Sentinel AI (7 days)",
        description="7-day building with solar + BESS + Sentinel AI optimization",
        operation_mode=OperationMode.SOLAR_BESS_SENTINEL,
        fault_probability=0.0,
        optimization_enabled=True,
    ),
}

# Combined lookup — used internally for start() and crash recovery
ALL_SCENARIOS = {**ARCHIVED_SCENARIOS, **SCENARIOS}

# Proportional control ramp rates (max % or °C change per simulated hour)
# These prevent step changes in actuator outputs, matching real BMS behaviour
RAMP_RATES: dict[str, float] = {
    "valve_position": 25.0,  # Belimo actuator ~90s full stroke
    "damper_position": 30.0,  # VAV direct-coupled actuator
    "fan_speed_pct": 20.0,  # VFD soft-start ramp
    "supply_air_temp": 2.0,  # Coil thermal mass (°C/hr)
    "speed_pct": 15.0,  # Pump VFD ramp
    "load_pct": 15.0,  # Chiller compressor staging
    "fan_speed": 1.0,  # FCU discrete fan step per hour
}


class LifecycleOrchestrator:
    """
    Orchestrates a 24-hour building simulation.

    Integrates health simulation, work order automation, AI optimization,
    and multi-day seasonal patterns into a unified lifecycle loop.
    """

    def __init__(self, task_id: str | None = None, site_id: str | None = None):
        self.task_id = task_id  # For database task tracking
        self.site_id = site_id or get_primary_site_code() or "unknown"
        self.running = False
        self.paused = False
        self.current_scenario: ScenarioConfig | None = None
        self.simulated_time: datetime = datetime.now().replace(hour=0, minute=0, second=0)
        self.real_start_time: datetime | None = None
        self.time_multiplier: float = 60.0  # 1 real minute = 1 simulated hour
        self.speed_multiplier: float = 1.0  # 1x real-time, 10x = 10x faster, etc.
        self.max_days: int = 1  # 1 for daily, 365 for annual
        self.events: list[LifecycleEvent] = []
        self.active_faults: dict[str, dict[str, Any]] = {}
        self.pending_repairs: dict[str, dict[str, Any]] = {}
        self.equipment_repo = EquipmentRepository()
        self.prediction_repo = PredictionRepository()
        self.work_order_repo = get_work_order_repository()
        self.feedback_service = get_feedback_collection_service()
        self.device_control_service = get_device_control_service()
        self._sentinel_alert_engine = SentinelAlertEngine()
        self._task: asyncio.Task | None = None
        self._callbacks: list[Callable[[LifecycleEvent], None]] = []

        # Cycle tracking for completion
        self.max_cycles: int = 1  # How many full cycles before completing
        self.completed_cycles: int = 0
        self._site_prefix: str = normalize_site_id(self.site_id, to_supabase=True).upper()  # site-003 → S003

        # Energy tracking
        self.total_energy_kwh: float = 0.0  # Cumulative energy consumption
        self.current_hour_power_kw: float = 0.0  # Current hour's power in kW
        self.days_simulated: int = 0  # Track days for annual simulations
        # Same scenario always produces same results, but with day-to-day variation
        self._scenario_rng = random.Random()
        self._occupancy_seed: int | None = None

        # Seasonal modeler for annual simulations
        self.seasonal_modeler: SeasonalModeler | None = None

        # Building schedule engine for time-of-day operating states
        self.site_schedule = SiteSchedule(self.site_id)
        self.site_holiday_service = get_site_holiday_service()
        self.site_capacity_service = get_site_capacity_service()
        self.site_total_capacity = self.site_capacity_service.get_total_capacity(self.site_id)
        self.site_desk_count = self.site_capacity_service.get_desk_count(self.site_id)

        # Chilled water model for physics-based zone cooling (105-01)
        self.chw_model = ChilledWaterModel()

        # Zone temperatures from thermal engine (105-01)
        self.zone_temperatures: dict[str, float] = {}

        # In-memory equipment health tracking — seeded from DB once, updated each hour
        # Avoids DB roundtrip precision loss on small wear increments (0.0006/hr)
        self._equipment_health: dict[str, float] = {}
        self._equipment_health_seeded: bool = False

        # JHB climate engine for realistic ambient temperature (104-01)
        # Lazy-import ClimatePattern to avoid bms_simulator/__init__.py which
        # triggers pandas import via the full simulator chain
        self.climate_engine = None
        try:
            import importlib.util
            import os

            spec = importlib.util.spec_from_file_location(
                "climate_pattern",
                os.path.join(os.path.dirname(__file__), "bms_simulator", "patterns", "climate.py"),
            )
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                self.climate_engine = mod.ClimatePattern(climate_zone="johannesburg")
        except Exception:
            pass  # Fall back to seasonal modeler

        # Runtime hours tracking per equipment (105-02)
        self.runtime_hours: dict[str, float] = {}  # equipment_code -> cumulative hours

        # Health monitoring state (106-01)
        self.health_status_cache: dict[str, str] = {}  # code -> "healthy"/"warning"/"critical"
        self.last_alert_time: dict[str, int] = {}  # code -> simulated_hour of last alert

        # Dashboard alert cooldown — prevents re-creating alerts after user clears them.
        # Maps "equipment_code::alert_type" -> datetime of last dashboard push.
        self._dashboard_alert_cooldown: dict[str, datetime] = {}

        # Zone temperature alert tracking — status transitions + cooldown (like health monitor)
        self._zone_temp_status_cache: dict[str, str] = {}  # zone_id -> "normal"|"warning"|"critical"
        self._zone_temp_last_alert: dict[str, int] = {}  # zone_id -> absolute_hour of last alert

        # BMS simulation persistence: writes JSON only
        self.persistence = get_simulation_persistence(site_id=site_id)

        # SENTINEL data sync: Supabase updates + ML pipeline
        self.sentinel_sync = get_sentinel_data_sync(site_id=site_id)

        # BESS state of charge tracking across hours
        self.bess_soc: float = 50.0  # Start at 50% SoC

        # Current ambient temp and solar efficiency (set each hour in _process_hour)
        self.current_ambient_temp: float = 22.0
        self.current_solar_efficiency: float = 0.0

        # Sustainability metrics accumulators (111-01)
        self._daily_hvac_kwh: float = 0.0
        self._daily_lighting_kwh: float = 0.0
        self._daily_other_kwh: float = 0.0
        self._daily_occupancy_samples: list[float] = []
        self._sustainability_collector = SustainabilityMetricsCollector(self.site_id)

        # AI optimization savings tracking (includes rules engine + solar/BESS offset)
        self._daily_baseline_kwh: float = 0.0
        self._daily_sentinel_kwh: float = 0.0
        self._daily_ai_savings_kwh: float = 0.0
        self._daily_solar_gen_kwh: float = 0.0
        self._daily_bess_discharge_kwh: float = 0.0
        self._cumulative_baseline_kwh: float = 0.0
        self._cumulative_sentinel_kwh: float = 0.0
        self._cumulative_solar_gen_kwh: float = 0.0
        self._cumulative_bess_discharge_kwh: float = 0.0

        # Solar/BESS daily accumulators for Supabase solar_daily_aggregates
        self._daily_bess_charge_kwh: float = 0.0
        self._daily_grid_import_kwh: float = 0.0
        self._daily_grid_export_kwh: float = 0.0
        self._daily_peak_solar_kw: float = 0.0
        self._daily_bess_soc_samples: list[float] = []
        self._solar_hour_index: int = 0  # cumulative hour counter (0-8759)

        # Building vs council consumption distinction
        # site_load = total electrical demand (after AI opt, before solar/BESS)
        # grid_import = what the council meter reads (site_load + bess_charge_grid - solar - bess_discharge)
        # grid_export = excess solar fed back to grid
        self.current_site_load_kw: float = 0.0
        self.current_solar_gen_kw: float = 0.0
        self.current_grid_import_kw: float = 0.0
        self.current_grid_export_kw: float = 0.0

        # DALI→HVAC occupancy bridge state
        self.current_occupancy_data: dict[str, float] = {}
        self._prev_zone_occupancy_state: dict[str, bool] = {}  # zone -> was_occupied

        # Unified simulation equipment snapshot — updated each tick for API access
        self._simulation_equipment: dict[str, dict[str, Any]] = {}

        # Proportional control: tracks previous actuator values for ramp limiting
        self._actuator_state: dict[str, dict[str, float]] = {}

        # Alert management (transplanted from BMSimulationService)
        self._alert_queue: list[dict[str, Any]] = []
        self._alert_history: list[dict[str, Any]] = []
        self._alert_id_counter: int = 1000

        # SENTINEL optimization wiring (v28.0)
        # In sentinel mode, the simulation calls AIOptimizerService.analyze_building()
        # — the same code path SENTINEL uses with real buildings. The simulation writes
        # BMS data to Supabase; SENTINEL reads it back through the BMS data layer.
        from app.config.settings import settings as app_settings

        self._last_state_fingerprint = ""  # For intelligent caching
        self._cached_sentinel_recs: list[dict] = []  # Cached recs for unchanged state
        self._llm_call_count = 0  # Token budget tracking
        self._optimization_mode = app_settings.simulation_optimization_mode

    @property
    def site_prefix(self) -> str:
        """Derive equipment code prefix from site_id: 'site-003' -> 'S003'."""
        return self._site_prefix

    # Normalize DB type names (e.g. GEN, MTR, INV) to internal names
    TYPE_ALIASES: dict[str, str] = {
        "gen": "generator",
        "mtr": "meter",
        "inv": "inverter",
        "ct": "cooling_tower",
        "dali": "dali_zone",
        "zone": "zone_controller",
        "lighting_zone": "luminaire",
        "ltg": "luminaire",
    }

    # Equipment type -> technician specialty mapping (106-01)
    EQUIPMENT_SPECIALTY_MAP = {
        "chiller": "HVAC",
        "cooling_tower": "HVAC",
        "ahu": "HVAC",
        "vav": "HVAC",
        "fcu": "HVAC",
        "pump": "HVAC",
        "ups": "Electrical",
        "generator": "Electrical",
        "meter": "Electrical",
        "inverter": "Electrical",
        "bess": "Electrical",
        "dali_zone": "Controls",
        "dali_controller": "Controls",
        "controller": "Controls",
        "luminaire": "Controls",
        "zone_controller": "Controls",
        "fire": "Fire Safety",
        "unknown": "Facilities",
        "sensor": "Controls",
    }

    # Baseline wear rates per running hour (% health loss) (105-02)
    # All zeroed — equipment stays healthy until degradation scenarios are enabled.
    # Per-hour health degradation applied during running hours only.
    # At ~14 running hrs/day over 365 days, annual wear = rate × 14 × 365.
    # Rates are simulation-accelerated for meaningful AI recommendation testing.
    # Floor is 30% (equipment doesn't die from wear alone, see _collect_equipment_states).
    WEAR_RATES = {
        "chiller": 0.008,  # Heavy plant, moderate wear → ~41% annual
        "cooling_tower": 0.012,  # Exposed to elements → ~61% annual
        "ahu": 0.010,  # Filter clogging, belt wear → ~51% annual
        "fcu": 0.015,  # Fan bearings, filters → ~77% annual (first to degrade)
        "vav": 0.012,  # Actuator wear → ~61% annual
        "pump": 0.010,  # Seal/bearing wear → ~51% annual
        "ups": 0.008,  # Battery degradation → ~41% annual
        "generator": 0.005,  # Standby, low run hours → ~26% annual
        "meter": 0.002,  # Passive device → ~10% annual
        "inverter": 0.005,  # Solid-state, slow wear → ~26% annual
        "bess": 0.012,  # Cycle degradation → ~61% annual
        "luminaire": 0.005,  # LED driver aging → ~26% annual
        "zone_controller": 0.003,  # Electronics → ~15% annual
        "dali_zone": 0.005,  # Driver aging → ~26% annual
        "dali_controller": 0.003,  # Electronics → ~15% annual
        "lighting_zone": 0.005,  # Lamp aging → ~26% annual
        "controller": 0.003,  # Electronics → ~15% annual
        "zone_sensor": 0.005,  # Calibration drift → ~26% annual
        "co2_sensor": 0.008,  # Sensor drift → ~41% annual
        "sensor": 0.005,  # Calibration drift → ~26% annual
        "unknown": 0.005,  # Default → ~26% annual
        "fire": 0.005,  # Battery/sensor aging → ~26% annual
    }

    # Safety boundary limits for proactive monitoring (106-02)
    SAFETY_LIMITS = {
        "zone_temp": {"min": 16.0, "max": 28.0, "unit": "°C"},
        "room_temp": {"min": 16.0, "max": 28.0, "unit": "°C"},
        "supply_temp": {"min": 4.0, "max": 25.0, "unit": "°C"},
        "supply_air_temp": {"min": 12.0, "max": 22.0, "unit": "°C"},
        "battery_pct": {"min": 30.0, "max": 100.0, "unit": "%"},
        "load_pct": {"min": 0.0, "max": 95.0, "unit": "%"},
        "differential_pressure_kpa": {"min": 0.0, "max": 200.0, "unit": "kPa"},
    }

    # Normal operating bands — values within these ranges are expected and should
    # NOT trigger alerts, even if they fall within 10% of a safety limit.
    # Structure: point_name → equip_type (or "_default") → time_period → (min, max)
    NORMAL_BANDS = {
        "supply_temp": {
            "chiller": {"default": (5.0, 8.5)},  # Design supply 6-7°C
            "ahu": {"default": (12.5, 18.0)},
        },
        "supply_air_temp": {
            "_default": {"default": (13.0, 20.0)},
        },
        "zone_temp": {
            "_default": {
                "peak": (20.0, 24.0),
                "off_peak": (18.0, 26.0),
            },
        },
        "room_temp": {
            "_default": {
                "peak": (20.0, 24.0),
                "off_peak": (18.0, 26.0),
            },
        },
        "load_pct": {
            "chiller": {"peak": (0.0, 92.0), "off_peak": (0.0, 70.0)},
            "ups": {"default": (0.0, 80.0)},
            "_default": {"default": (0.0, 85.0)},
        },
        "battery_pct": {
            "_default": {"default": (50.0, 100.0)},
        },
        "differential_pressure_kpa": {
            "_default": {"default": (20.0, 150.0)},
        },
    }

    # Recommended actions for safety boundary alerts — tells operators WHAT TO DO.
    # Structure: point_name → equip_type (or "_default") → severity → action_text
    SAFETY_ACTIONS = {
        "supply_temp": {
            "chiller": {
                "warning": "Check chiller staging and condenser water temps. Consider staging up if load demands it.",
                "critical": (
                    "IMMEDIATE: Verify chiller refrigerant charge and compressor operation."
                    " Risk of coil freeze below 4\u00b0C."
                ),
            },
            "ahu": {
                "warning": "Check AHU coil valve position and mixed air dampers.",
                "critical": "IMMEDIATE: Check AHU heating/cooling coil for failure. Verify supply fan operation.",
            },
            "_default": {
                "warning": "Check equipment supply temperature trending and control setpoints.",
                "critical": "IMMEDIATE: Investigate supply temperature deviation. Check control loop and actuators.",
            },
        },
        "supply_air_temp": {
            "_default": {
                "warning": "Check AHU mixed air damper position and cooling coil valve.",
                "critical": (
                    "IMMEDIATE: Supply air temperature out of range. Check AHU cooling/heating coils and control loop."
                ),
            },
        },
        "zone_temp": {
            "_default": {
                "warning": "Check zone FCU/VAV operation and thermostat setpoint. Verify occupancy schedule.",
                "critical": "IMMEDIATE: Zone temperature out of comfort range. Check FCU/VAV and AHU supply.",
            },
        },
        "room_temp": {
            "_default": {
                "warning": "Check room FCU operation and thermostat setpoint.",
                "critical": "IMMEDIATE: Room temperature out of comfort range. Check HVAC supply to this zone.",
            },
        },
        "load_pct": {
            "chiller": {
                "warning": "Monitor chiller load trend. Consider staging another chiller online if available.",
                "critical": "Stage additional chiller ASAP. Current unit at risk of trip on high pressure.",
            },
            "ups": {
                "warning": "Review connected loads on this UPS. Plan load shedding if trend continues.",
                "critical": "IMMEDIATE: Shed non-critical loads. UPS at risk of overload trip.",
            },
            "_default": {
                "warning": "Monitor equipment load trend. Consider load redistribution.",
                "critical": "IMMEDIATE: Equipment overloaded. Reduce load or bring standby online.",
            },
        },
        "battery_pct": {
            "_default": {
                "warning": "Check charger operation and battery voltage. Schedule battery test.",
                "critical": (
                    "IMMEDIATE: Check charger operation. Prepare for mains transfer if battery continues to discharge."
                ),
            },
        },
        "differential_pressure_kpa": {
            "_default": {
                "warning": "Check filter condition and fan speed. Schedule filter inspection.",
                "critical": "IMMEDIATE: Differential pressure critical. Check for blocked filters or duct obstruction.",
            },
        },
    }

    def _get_normal_band(self, point_name: str, equip_type: str, is_peak: bool) -> tuple | None:
        """Look up normal operating band for a point/equipment/time combination.

        Returns (min, max) tuple if a band exists, None otherwise.
        Tries equipment-specific band first, then _default.
        Tries peak/off_peak key first, then default.
        """
        point_bands = self.NORMAL_BANDS.get(point_name)
        if not point_bands:
            return None

        # Try equipment-specific first, then _default
        equip_bands = point_bands.get(equip_type) or point_bands.get("_default")
        if not equip_bands:
            return None

        # Try peak/off_peak key first, then default
        time_key = "peak" if is_peak else "off_peak"
        band = equip_bands.get(time_key) or equip_bands.get("default")
        return band

    def _get_safety_action(self, point_name: str, equip_type: str, severity: str) -> str:
        """Look up recommended action for a safety boundary alert.

        Returns action text string. Falls back to generic message.
        """
        point_actions = self.SAFETY_ACTIONS.get(point_name)
        if not point_actions:
            return f"Investigate {point_name} on this equipment."

        # Try equipment-specific first, then _default
        equip_actions = point_actions.get(equip_type) or point_actions.get("_default")
        if not equip_actions:
            return f"Investigate {point_name} on this equipment."

        return equip_actions.get(severity, f"Investigate {point_name} on this equipment.")

    def reset(self):
        """Reset orchestrator state for a fresh demo.

        Clears all simulation state so the next start() call begins fresh.
        Called when a user logs in to ensure demo restarts clean each time.
        """
        self.running = False
        self.paused = False
        self.current_scenario = None
        self.simulated_time = datetime.now().replace(hour=0, minute=0, second=0)
        self.real_start_time = None
        self.time_multiplier = 60.0
        self.speed_multiplier = 1.0
        self.max_days = 1
        self.events = []
        self.active_faults = {}
        self.pending_repairs = {}
        self._task = None
        self._scenario_rng = random.Random()
        self._occupancy_seed = None
        self.seasonal_modeler = None
        self.days_simulated = 0
        self.runtime_hours = {}  # Reset runtime hours (105-02)
        self.chw_model = ChilledWaterModel()  # Reset CHW model (105-01)
        self.zone_temperatures = {}  # Reset zone temps (105-01)
        self._equipment_health = {}  # Reset in-memory health tracking
        self._equipment_health_seeded = False
        self._actuator_state = {}  # Reset ramp-limit tracking
        self.health_status_cache = {}  # Reset health monitoring (106-01)
        self.last_alert_time = {}  # Reset alert cooldowns (106-01)
        self._daily_hvac_kwh = 0.0  # Reset sustainability accumulators (111-01)
        self._daily_lighting_kwh = 0.0
        self._daily_other_kwh = 0.0
        self._daily_occupancy_samples = []
        self._daily_baseline_kwh = 0.0
        self._daily_sentinel_kwh = 0.0
        self._daily_ai_savings_kwh = 0.0
        self._daily_solar_gen_kwh = 0.0
        self._daily_bess_discharge_kwh = 0.0
        self._cumulative_baseline_kwh = 0.0
        self._cumulative_sentinel_kwh = 0.0
        self._cumulative_solar_gen_kwh = 0.0
        self._cumulative_bess_discharge_kwh = 0.0
        self._daily_bess_charge_kwh = 0.0
        self._daily_grid_import_kwh = 0.0
        self._daily_grid_export_kwh = 0.0
        self._daily_peak_solar_kw = 0.0
        self._daily_bess_soc_samples = []
        self._solar_hour_index = 0
        logger.info("Orchestrator reset: Ready for fresh demo")

    @property
    def seconds_per_simulated_hour(self) -> float:
        """Real seconds to wait between each simulated hour.

        At 1x speed: 60 seconds per simulated hour (24h sim takes 24 minutes).
        At 10x speed: 6 seconds per simulated hour (24h sim takes 2.4 minutes).
        At 100x speed: 0.6 seconds per simulated hour (24h sim takes 14.4 seconds).
        At 1000x speed: 0.06 seconds per simulated hour (24h sim takes 1.4 seconds).
        """
        base_seconds = 60.0  # 1 minute per simulated hour at 1x
        return max(0.05, base_seconds / self.speed_multiplier)

    def set_speed(self, speed_multiplier: float) -> dict[str, Any]:
        """Change simulation speed while running.

        Args:
            speed_multiplier: New speed multiplier (0.1 to 10000).

        Returns:
            Dict with new speed and seconds_per_hour.
        """
        old_speed = self.speed_multiplier
        self.speed_multiplier = max(0.1, min(10000, speed_multiplier))
        logger.info(
            f"Speed changed: {old_speed}x -> {self.speed_multiplier}x "
            f"({self.seconds_per_simulated_hour:.2f}s per simulated hour)"
        )
        return {
            "speed": self.speed_multiplier,
            "seconds_per_hour": self.seconds_per_simulated_hour,
        }

    def add_event_callback(self, callback: Callable[[LifecycleEvent], None]):
        """Add callback to be notified of events."""
        self._callbacks.append(callback)

    def _emit_event(self, event: LifecycleEvent):
        """Emit event to all callbacks."""
        self.events.append(event)
        logger.info(f"[{event.simulated_hour:02d}:00] {event.event_type.value}: {event.description}")
        for callback in self._callbacks:
            try:
                callback(event)
            except Exception as e:
                logger.error(f"Event callback error: {e}")

    async def start(
        self,
        scenario: str = "normal_day",
        duration_minutes: float = 24.0,
        start_hour: int = 0,
        task_id: str | None = None,  # For checkpoint recovery
        speed_multiplier: float = 10.0,
        start_date: str | None = None,  # ISO date string e.g. "2025-06-15"
        max_cycles: int = 1,  # Number of full cycles before completing (0=infinite)
    ) -> dict[str, Any]:
        """
        Start the 24-hour simulation.

        Args:
            scenario: Scenario name from SCENARIOS
            duration_minutes: Real-time duration (24 = 1 min per hour)
            start_hour: Simulated hour to start (0-23)
            task_id: Optional task_id for checkpoint recovery
            speed_multiplier: Speed factor (1x=real-time, 10x=10x faster, etc.)
            start_date: Optional ISO date string for simulation start date

        Returns:
            Status dict with session info
        """
        # FIRST: Check for existing checkpoint to recover from
        checkpoint = None
        if task_id and "annual" in scenario:
            try:
                from app.services.simulation_store import get_simulation_store

                store = get_simulation_store(self.site_id)
                task_data = store.get_task_progress(task_id)
                if task_data and task_data.get("state_snapshot"):
                    checkpoint = task_data["state_snapshot"]
                    day = checkpoint.get("days_simulated", 0)
                    logger.info(f"✅ Found checkpoint for task {task_id}, recovering from day {day}/365")
            except Exception as e:
                logger.warning(f"Could not load checkpoint: {e}")

        # If already running, only allow if we have a checkpoint to recover (fresh start, not overlay)
        if self.running and not checkpoint:
            return {"success": False, "error": "Simulation already running"}

        # Get scenario config (check ALL_SCENARIOS for archived scenarios)
        self.current_scenario = ALL_SCENARIOS.get(scenario, SCENARIOS["sentinel_annual"])

        # Random seed per run — every simulation is unique
        import time

        self._occupancy_seed = int(time.time() * 1000) % (2**32)
        self._scenario_rng.seed(self._occupancy_seed)
        logger.info(f"Simulation seed={self._occupancy_seed} (random per run)")

        # Check if this is an annual scenario (365-day simulations have "annual" in name)
        is_annual = "annual" in scenario.lower()

        # Set speed multiplier for new speed control system
        self.speed_multiplier = max(0.1, min(10000, speed_multiplier))

        # Set max cycles (0 = infinite loop, 1 = single run, N = N cycles)
        self.max_cycles = max_cycles
        self.completed_cycles = 0

        # Determine max days for recovery path too
        self.max_days = 365 if is_annual else 1

        # RECOVERY PATH: If we have a checkpoint, restore ALL state BEFORE starting loop
        if checkpoint and is_annual:
            logger.info("RECOVERY PATH: Restoring checkpoint state...")
            self.simulated_time = datetime.fromisoformat(checkpoint.get("simulated_time", datetime.now().isoformat()))
            self.days_simulated = checkpoint.get("days_simulated", 0)
            self.time_multiplier = checkpoint.get("time_multiplier", 60.0)
            self.active_faults = checkpoint.get("active_faults", {})
            self.pending_repairs = checkpoint.get("pending_repairs", {})
            self.events = checkpoint.get("events", [])

            # Restore seasonal modeler for annual sims
            if self.days_simulated > 0:
                self.seasonal_modeler = SeasonalModeler(seed=self._occupancy_seed)
                time_str = self.simulated_time.strftime("%Y-%m-%d %H:%M")
                logger.info(f"✅ Restored checkpoint: day {self.days_simulated}/365, time={time_str}")

            self.real_start_time = datetime.now()
            self.running = True
            self.paused = False

            # Start loop directly with restored state (NO fresh init)
            self._task = asyncio.create_task(self._run_simulation())
            return {
                "success": True,
                "scenario": self.current_scenario.name,
                "recovered_from_checkpoint": True,
                "days_simulated": self.days_simulated,
                "started_at": self.real_start_time.isoformat(),
            }

        # FRESH START PATH: Initialize fresh (no checkpoint)
        # Determine simulation duration from scenario
        self.max_days = 365 if is_annual else 1

        if is_annual:
            # Annual simulation: 365 days x 24 hours = 8760 hours total
            self.seasonal_modeler = SeasonalModeler(seed=self._occupancy_seed)
            self.days_simulated = 0
            # Calculate time multiplier for 365-day simulation
            # duration_minutes = real time in minutes (e.g., 120 min = 2 hours)
            # total_hours = 365 * 24 = 8760 simulated hours
            # Each simulated hour takes: (duration_minutes * 60) / 8760 seconds
            total_hours_annual = 365 * 24
            self.time_multiplier = (duration_minutes * 60.0) / total_hours_annual  # seconds per simulated hour
            # Start date: use provided date or default to January 1st
            if start_date:
                self.simulated_time = datetime.fromisoformat(start_date).replace(hour=start_hour, minute=0, second=0)
            else:
                self.simulated_time = datetime(2024, 1, 1, start_hour, 0, 0)
            time_mult = f"{self.time_multiplier:.3f}"
            speed_str = f"{self.speed_multiplier}x"
            logger.info(
                f"Annual simulation initialized: {speed_str} speed, {duration_minutes} min for full year "
                f"(365 days), {time_mult}s per hour, {self.seconds_per_simulated_hour:.2f}s effective"
            )
        else:
            # Daily simulation: just 24 hours
            self.seasonal_modeler = None
            # Calculate time multiplier for 24-hour simulation
            # duration_minutes for full 24 hours
            # Each simulated hour takes: (duration_minutes * 60) / 24 seconds
            self.time_multiplier = (duration_minutes * 60.0) / 24.0  # seconds per simulated hour
            # Start date: use provided date or default to today
            if start_date:
                self.simulated_time = datetime.fromisoformat(start_date).replace(hour=start_hour, minute=0, second=0)
            else:
                self.simulated_time = datetime.now().replace(hour=start_hour, minute=0, second=0, microsecond=0)

        self.real_start_time = datetime.now()
        self.events = []
        self.active_faults = {}
        self.pending_repairs = {}
        self.running = True
        self.paused = False
        self._solar_hour_index = 0

        # Clear old solar snapshot data so dashboard starts from 0
        try:
            from app.services.simulation_store import get_simulation_store

            sim_store = get_simulation_store(self.site_id)
            for fname in ("solar_hourly_snapshots.jsonl", "solar_daily_aggregates.jsonl"):
                fpath = sim_store._dir / fname
                if fpath.exists():
                    fpath.unlink()
            logger.info("[SOLAR] Cleared old snapshot data for fresh simulation start")
        except Exception as e:
            logger.debug(f"[SOLAR] Could not clear old snapshots: {e}")

        logger.info(
            f"Starting lifecycle simulation: {self.current_scenario.name}, "
            f"speed={self.speed_multiplier}x, start_hour={start_hour}, "
            f"seconds_per_hour={self.seconds_per_simulated_hour:.2f}s"
        )

        # Start background task
        self._task = asyncio.create_task(self._run_simulation())

        return {
            "success": True,
            "scenario": self.current_scenario.name,
            "speed_multiplier": self.speed_multiplier,
            "seconds_per_simulated_hour": self.seconds_per_simulated_hour,
            "duration_minutes": duration_minutes,
            "time_multiplier_seconds_per_hour": self.time_multiplier,
            "start_hour": start_hour,
            "started_at": self.real_start_time.isoformat(),
        }

    async def stop(self) -> dict[str, Any]:
        """Stop the running simulation cleanly.

        Returns:
            Summary dict with simulation statistics.
        """
        if not self.running:
            return {"success": False, "error": "No simulation running"}

        self.running = False
        summary = {
            "success": True,
            "days_simulated": self.days_simulated,
            "total_energy_kwh": round(self.total_energy_kwh, 1),
            "events_count": len(self.events),
            "faults_occurred": len(self.active_faults),
            "stopped_at": datetime.now().isoformat(),
        }

        # Cancel the async task
        if self._task and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task

        # Write stopped status to DB (with final state snapshot)
        await self._write_stopped_status()

        logger.info(
            f"Simulation stopped: {self.days_simulated} days, "
            f"{self.total_energy_kwh:.0f} kWh, {len(self.events)} events"
        )
        return summary

    def pause(self):
        """Pause the simulation."""
        self.paused = True
        logger.info(f"[SIMULATION] Paused at {self.simulated_time}")

    def unpause(self):
        """Resume a paused simulation."""
        self.paused = False
        logger.info(f"[SIMULATION] Resumed at {self.simulated_time}")

    def resume(self):
        """Backward-compatible alias for resuming a paused simulation."""
        self.unpause()

    def get_status(self) -> dict[str, Any]:
        """Get current simulation status including weather and seasonal data."""
        # Auto-heal: if running flag is True but the async task is dead, reset
        if self.running and self._task and self._task.done():
            logger.warning("[STATUS] Simulation task is dead but running=True — resetting to stopped")
            self.running = False

        elapsed_real = (datetime.now() - self.real_start_time).total_seconds() if self.real_start_time else 0

        # Calculate progress percentage
        total_iterations = 8760 if self.seasonal_modeler is not None else 24
        progress_percent = int((self.days_simulated * 24 / total_iterations) * 100) if total_iterations > 0 else 0

        # Get seasonal/weather data if available
        current_season = ""
        is_raining = False
        cloud_cover = 0
        ambient_temp = 22.0
        solar_efficiency = 100.0

        # Use JHB climate engine for ambient temp if available
        if self.climate_engine and self.running:
            current_hour = self.simulated_time.hour
            day_of_year = self.simulated_time.timetuple().tm_yday
            ambient_temp = self.climate_engine.get_temperature(day_of_year, current_hour)

        if self.seasonal_modeler:
            current_date = self.simulated_time.date()
            current_season = self.seasonal_modeler.get_season_name(current_date)
            current_hour = self.simulated_time.hour

            # Get weather data using individual SeasonalModeler methods
            is_raining = self.seasonal_modeler.should_rain_today(current_date)
            cloud_cover = self.seasonal_modeler.get_cloud_cover_percent(current_date)
            # Only use seasonal modeler for temp if climate engine not available
            if not self.climate_engine:
                ambient_temp = self.seasonal_modeler.get_ambient_temperature(current_date, current_hour, is_raining)

            # Calculate solar efficiency based on time and weather
            if 6 <= current_hour < 18:  # Daytime
                base_efficiency = 100 - (cloud_cover * 0.8)
                if is_raining:
                    base_efficiency *= 0.3  # Rain reduces efficiency significantly
                solar_efficiency = max(10, base_efficiency)
            else:
                solar_efficiency = 0

        return {
            "running": self.running,
            "paused": self.paused,
            "scenario": self.current_scenario.name if self.current_scenario else None,
            "simulated_time": self.simulated_time.strftime("%H:%M") if self.running else None,
            "simulated_hour": self.simulated_time.hour if self.running else None,
            "real_elapsed_seconds": round(elapsed_real, 1),
            "events_count": len(self.events),
            "active_faults": len(self.active_faults),
            "pending_repairs": len(self.pending_repairs),
            "progress_percent": progress_percent,
            "is_raining": is_raining,
            "cloud_cover": cloud_cover,
            "ambient_temp": ambient_temp,
            "humidity": getattr(self, "current_humidity", 50.0),
            "solar_efficiency": solar_efficiency,
            "current_season": current_season,
            "occupancy_percent": self._calculate_occupancy(self.simulated_time.hour if self.simulated_time else 0),
            "total_energy_kwh": round(self.total_energy_kwh, 1),
            "current_hour_power_kw": round(self.current_hour_power_kw, 2),
            "recent_events": [
                {
                    "hour": e.simulated_hour,
                    "type": e.event_type.value,
                    "description": e.description,
                    "equipment": e.equipment_name,
                }
                for e in self.events[-10:]
            ],
            "ml_feeder": self.sentinel_sync.ml_feeder.get_buffer_stats()
            if hasattr(self, "sentinel_sync")
            else {"error": "ml_feeder not initialized"},
        }

    async def _run_simulation(self):
        """Main simulation loop -- advances hour-by-hour.

        Handles both 24-hour single-day and 365-day annual scenarios.
        Uses self.max_days (set in start()) to determine when to stop or cycle.
        Uses self.seconds_per_simulated_hour (speed-controlled) for pacing.
        Checks self.running and self.paused each iteration.
        """
        try:
            is_annual = self.seasonal_modeler is not None
            max_days = getattr(self, "max_days", 365 if is_annual else 1)
            total_iterations = max_days * 24
            speed_str = f"{self.speed_multiplier}x"
            logger.warning(
                f"[SIMULATION START] task_id={self.task_id}, is_annual={is_annual}, "
                f"max_days={max_days}, speed={speed_str}, "
                f"days={self.days_simulated}, "
                f"{self.seconds_per_simulated_hour:.2f}s/hour"
            )

            # On recovery, skip iterations already completed so we don't re-simulate days
            iteration = self.days_simulated * 24 if self.days_simulated > 0 else 0
            last_checkpoint_hour = -1  # Track checkpoint saves

            # Persistent loop: Run max_days, then restart (loops until manually stopped)
            cycle_num = 1
            while self.running:
                iteration += 1
                current_hour = self.simulated_time.hour

                # Log progress periodically
                if iteration <= 10 or iteration % 100 == 0:
                    day_num = self.days_simulated + 1
                    logger.warning(
                        f"[SIMULATION CYCLE {cycle_num}] Hour {iteration}/{total_iterations} "
                        f"(day={day_num}/{max_days}, hour={current_hour:02d}:00)"
                    )

                try:
                    # Pause support: hold on same hour
                    if self.paused:
                        await asyncio.sleep(0.1)
                        continue

                    # Check self.running before processing (may have been stopped)
                    if not self.running:
                        break

                    # Process events for this hour
                    await self._process_hour(current_hour)

                    # Save checkpoint every 6 simulated hours for crash recovery
                    if is_annual and (current_hour % 6 == 0):
                        if current_hour != last_checkpoint_hour:
                            await self.save_checkpoint()
                            last_checkpoint_hour = current_hour

                    # Advance time by 1 hour
                    self.simulated_time += timedelta(hours=1)

                    # Track day transitions (every 24 hours)
                    if iteration > 0 and (iteration % 24) == 0:
                        # Write daily sustainability snapshot before incrementing day (111-01)
                        await self._write_daily_sustainability()

                        self.days_simulated += 1
                        progress = int((self.days_simulated / max_days) * 100)
                        if is_annual:
                            logger.warning(f"[DAY COMPLETE] Day {self.days_simulated}/{max_days}, progress={progress}%")
                            # Update database with progress every day
                            await self._update_progress_to_db(iteration, total_iterations)

                    # Sleep for the calculated time per simulated hour
                    # (uses speed_multiplier via seconds_per_simulated_hour property)
                    await asyncio.sleep(self.seconds_per_simulated_hour)

                except asyncio.CancelledError:
                    logger.warning(f"[CANCELLED] iteration={iteration}, task was cancelled")
                    raise
                except Exception as e:
                    logger.error(
                        f"[ERROR in iteration {iteration}] {type(e).__name__}: {e}",
                        exc_info=True,
                    )
                    raise

                # Check if completed max_days (one full cycle)
                if iteration >= total_iterations:
                    self.completed_cycles += 1
                    days = self.days_simulated
                    logger.warning(
                        f"[CYCLE {cycle_num} COMPLETE] Completed {days}"
                        f" days (cycle {self.completed_cycles}"
                        f"/{self.max_cycles or '∞'})"
                    )

                    # Check if we've reached max_cycles (0 = infinite)
                    if self.max_cycles > 0 and self.completed_cycles >= self.max_cycles:
                        logger.warning(
                            f"[SIMULATION COMPLETE] {self.max_cycles} cycle(s) done — writing completion status"
                        )
                        await self._write_completion_status()
                        break

                    # Reset for next cycle
                    iteration = 0
                    self.days_simulated = 0
                    # Reset simulated_time to start of year/day
                    if is_annual:
                        self.simulated_time = datetime(2024, 1, 1, 0, 0, 0)
                    else:
                        self.simulated_time = self.simulated_time.replace(hour=0, minute=0, second=0)
                    cycle_num += 1
                    last_checkpoint_hour = -1
                    logger.warning(f"[CYCLE {cycle_num} START] Beginning persistent loop cycle {cycle_num}")

            logger.warning(f"[SIMULATION STOPPED] Completed {cycle_num - 1} full cycles, last iteration={iteration}")
            self.running = False

        except asyncio.CancelledError:
            logger.info("Simulation cancelled")
            self.running = False
        except Exception as e:
            logger.error(f"Simulation error: {e}", exc_info=True)
            self.running = False

    async def _update_progress_to_db(self, iteration: int, total_iterations: int) -> None:
        """Update simulation progress to JSON store (called every simulated day)."""
        if not self.task_id:
            return

        try:
            from app.services.simulation_store import get_simulation_store

            store = get_simulation_store(self.site_id)
            progress_pct = int((iteration / total_iterations) * 100)

            store.update_task_progress(
                self.task_id,
                {
                    "progress_pct": progress_pct,
                    "days_completed": self.days_simulated,
                },
            )

            logger.debug(f"Updated task {self.task_id}: {progress_pct}% progress, {self.days_simulated} days")
        except Exception as e:
            logger.warning(f"Failed to update progress for task {self.task_id}: {e}")

    async def _write_completion_status(self) -> None:
        """Write final completion status to JSON store when simulation finishes."""
        if not self.task_id:
            return

        try:
            from app.services.simulation_store import get_simulation_store

            store = get_simulation_store(self.site_id)
            state_snapshot = self.serialize_state()

            store.update_task_progress(
                self.task_id,
                {
                    "status": "completed",
                    "progress_pct": 100,
                    "days_completed": self.days_simulated,
                    "state_snapshot": state_snapshot,
                    "completed_at": datetime.now().isoformat(),
                },
            )

            logger.info(
                f"Simulation {self.task_id} completed: {self.completed_cycles} cycle(s), "
                f"{self.days_simulated} days, {self.total_energy_kwh:.0f} kWh"
            )
        except Exception as e:
            logger.error(f"Failed to write completion status for task {self.task_id}: {e}")

    async def _write_stopped_status(self) -> None:
        """Write stopped status to JSON store when simulation is manually stopped."""
        if not self.task_id:
            return

        try:
            from app.services.simulation_store import get_simulation_store

            store = get_simulation_store(self.site_id)
            state_snapshot = self.serialize_state()

            store.update_task_progress(
                self.task_id,
                {
                    "status": "stopped",
                    "state_snapshot": state_snapshot,
                    "completed_at": datetime.now().isoformat(),
                },
            )

            logger.info(f"Simulation {self.task_id} stopped at day {self.days_simulated}")
        except Exception as e:
            logger.error(f"Failed to write stopped status for task {self.task_id}: {e}")

    async def _process_hour(self, hour: int):
        """Process a simulated hour using the building schedule engine.

        Equipment behavior (chiller staging, AHU fan speed, VAV damper positions,
        FCU valve positions, DALI lighting levels) is keyed off schedule state +
        occupancy + ambient temperature rather than hardcoded hour checks.
        """
        day_of_week = self.simulated_time.weekday()
        schedule_state = self.site_schedule.get_state(hour, day_of_week)

        logger.info(
            f"[Hour {hour:02d}:00] Day {self.days_simulated + 1} "
            f"| {schedule_state.state.value} | HVAC: {schedule_state.hvac_mode.value} "
            f"| Occupancy: {schedule_state.target_occupancy_pct:.0f}%"
        )

        # Emit schedule transition events
        await self._emit_schedule_event(hour, schedule_state)

        # Midnight: daily summary for annual simulations
        if hour == 0 and self.seasonal_modeler:
            season = self.seasonal_modeler.get_season_name(self.simulated_time.date())
            self._emit_event(
                LifecycleEvent(
                    timestamp=datetime.now(),
                    simulated_hour=0,
                    event_type=EventType.BUILDING_WAKE,
                    description=f"Day {self.days_simulated + 1}: {season.capitalize()} - Building daily cycle begins",
                    details={
                        "day_of_year": self.days_simulated + 1,
                        "season": season,
                        "month": self.simulated_time.strftime("%B"),
                    },
                )
            )

        if hour == 0:
            try:
                from app.services.space_booking_simulator import get_space_booking_simulator

                booking_summary = await get_space_booking_simulator().ingest_day(
                    self.site_id,
                    self.simulated_time.date(),
                )
                if booking_summary["generated_bookings"]:
                    logger.info(
                        (
                            "[SPACE BOOKINGS] %s day=%s generated=%s saved=%s "
                            "alerts=%s notified=%s intake_emails=%s intelligence_signals=%s"
                        ),
                        self.site_id,
                        self.simulated_time.date().isoformat(),
                        booking_summary["generated_bookings"],
                        booking_summary["saved_bookings"],
                        booking_summary["alerts_generated"],
                        booking_summary["alerts_notified"],
                        booking_summary.get("intelligence_emails_generated", 0),
                        booking_summary.get("intelligence_signals_created", 0),
                    )
            except Exception as exc:
                logger.warning("[SPACE BOOKINGS] Failed to simulate room bookings: %s", exc)

        try:
            from app.services.space_booking_simulator import get_space_booking_simulator

            room_summary = await get_space_booking_simulator().replay_hour(
                self.site_id,
                self.simulated_time,
            )
            if room_summary["events_replayed"] or room_summary["ghost_findings_created"]:
                logger.info(
                    "[SPACE ROOMS] %s hour=%02d events=%s meeting=%s focus=%s ghosts=%s notified=%s",
                    self.site_id,
                    hour,
                    room_summary["events_replayed"],
                    room_summary.get("meeting_room_events_replayed", 0),
                    room_summary.get("focus_room_events_replayed", 0),
                    room_summary["ghost_findings_created"],
                    room_summary["ghost_notifications_sent"],
                )
        except Exception as exc:
            logger.warning("[SPACE ROOMS] Failed to simulate room occupancy: %s", exc)

        # === FAULT INJECTION (scenario-driven) ===
        if self.current_scenario and self.current_scenario.fault_probability > 0:
            if self.current_scenario.fault_hour == hour:
                await self._inject_fault()
            elif self.current_scenario.fault_hour is None:
                # Random fault based on probability (spread across 24 hours)
                if self._scenario_rng.random() < (self.current_scenario.fault_probability / 24):
                    await self._inject_fault()

        # === PENDING REPAIRS CHECK ===
        if self.active_faults:
            await self._check_pending_repairs()

        # === THERMAL UPDATE ===
        ambient_temp = 20.0  # Default, updated below
        occupancy_data = {}
        try:
            occupancy_data = self._generate_occupancy_for_hour(hour)
            self.current_occupancy_data = occupancy_data

            # Get ambient temperature from JHB climate engine (preferred)
            # or fall back to seasonal modeler for backward compatibility
            if self.climate_engine:
                day_of_year = self.simulated_time.timetuple().tm_yday
                ambient_temp = self.climate_engine.get_temperature(day_of_year, hour)
                self.current_humidity = self.climate_engine.get_humidity(day_of_year, hour)
            elif self.seasonal_modeler:
                is_raining = self.seasonal_modeler.should_rain_today(self.simulated_time.date())
                ambient_temp = self.seasonal_modeler.get_ambient_temperature(
                    self.simulated_time.date(), self.simulated_time.hour, is_raining
                )
                self.current_humidity = 50.0  # Default when no climate engine
            else:
                ambient_temp = 20.0
                self.current_humidity = 50.0

            # Always consider equipment health — healthy equipment has factor=1.0 (no impact)
            # Gradual wear degrades health over months; thermal engine needs to see it
            consider_health = True

            is_night_mode = schedule_state.hvac_mode in (HVACMode.OFF, HVACMode.NIGHT_SETBACK)

            # Refresh the thermal engine's health cache with in-memory values
            # so degradation accumulated over the simulation is reflected in HVAC response
            if self._equipment_health:
                from app.services.thermal_simulation_engine import get_thermal_engine

                thermal_engine = get_thermal_engine(self.site_id, consider_equipment_health=consider_health)
                thermal_engine.update_health_cache(self._equipment_health)

            thermal_temps = await update_simulation_temperatures(
                site_id=self.site_id,
                simulated_hour=hour,
                occupancy_data=occupancy_data,
                ambient_temp=ambient_temp,
                is_night_mode=is_night_mode,
                consider_equipment_health=consider_health,
                simulated_date=self.simulated_time,
            )

            # Use thermal engine results as source of truth for zone temperatures
            if thermal_temps:
                for zone_id, temp in thermal_temps.items():
                    self.zone_temperatures[zone_id] = round(temp, 1)
        except Exception as e:
            logger.warning(f"[THERMAL] Failed to update temperatures at hour {hour}: {e}")
            occupancy_data = {}

        # === STORE ENVIRONMENT FOR SENSOR GENERATION ===
        self.current_ambient_temp = ambient_temp
        # Calculate solar efficiency for this hour
        if self.seasonal_modeler:
            current_date = self.simulated_time.date()
            is_raining_now = self.seasonal_modeler.should_rain_today(current_date)
            cloud_cover = self.seasonal_modeler.get_cloud_cover_percent(current_date)
            if 6 <= hour < 18:
                base_eff = 100 - (cloud_cover * 0.8)
                if is_raining_now:
                    base_eff *= 0.3
                self.current_solar_efficiency = max(10, base_eff)
            else:
                self.current_solar_efficiency = 0
        else:
            self.current_solar_efficiency = 100.0 if 6 <= hour < 18 else 0.0

        # === CHILLED WATER MODEL UPDATE (105-01) ===
        # Advance CHW supply/return temps based on chiller staging and ambient
        # (kept for CHW sensor generation; zone temps now come from thermal engine above)
        self.chw_model.update(schedule_state.chiller_staging, ambient_temp)

        # === DALI→HVAC OCCUPANCY BRIDGE EVENTS ===
        self._emit_occupancy_bridge_events(hour)

        # === ENERGY CONSUMPTION TRACKING (schedule-driven) ===
        # Power consumption based on equipment staging, not flat 20-35kW
        base_power = self._calculate_hourly_power(schedule_state, occupancy_data)

        # === TARIFF BAND (used by energy rules and solar persistence) ===
        tariff = (
            "peak"
            if hour in range(7, 10) or hour in range(18, 20)
            else ("off_peak" if hour < 6 or hour >= 22 else "standard")
        )

        # === AI OPTIMIZATION ENERGY SAVINGS ===
        # Apply rules-engine savings to hourly power when HVAC is active
        ai_savings_kwh = 0.0
        if schedule_state.hvac_mode != HVACMode.OFF:
            try:
                from app.models.energy_rules import BuildingState as RulesBuildingState
                from app.services.energy_rules_engine import get_energy_rules_engine

                rules_engine = get_energy_rules_engine(self.site_prefix)

                avg_occ = schedule_state.target_occupancy_pct
                chiller_load = {"off": 0, "stage_1": 30, "stage_2": 60, "full_load": 90}.get(
                    schedule_state.chiller_staging.value, 0
                )
                daylight = (
                    max(0, min(1000, int(500 * math.sin(math.pi * max(0, hour - 6) / 12)))) if 6 <= hour < 18 else 0
                )

                rules_state = RulesBuildingState(
                    current_hour=hour,
                    occupancy_percent=int(avg_occ),
                    daylight_lux=daylight,
                    chiller_load_percent=chiller_load,
                    peak_demand_kw=base_power,
                    tariff_band=tariff,
                    ambient_temp_c=ambient_temp,
                    site_id=self.site_prefix,
                    date=self.simulated_time.date().isoformat(),
                )

                rules_output = rules_engine.evaluate_rules(
                    site_state=rules_state,
                    active_modules=["hvac", "dali", "solar"],
                    baseline_kwh=base_power,
                )
                ai_savings_kwh = rules_output.delta_kwh
            except Exception as e:
                logger.debug(f"[ENERGY RULES] Skipped: {e}")

        # === SOLAR GENERATION + BESS DISCHARGE OFFSET ===
        # 297 kWp total plant capacity (4× Huawei SUN2000-100KTL inverters, 540× 550W panels)
        solar_offset_kwh = 0.0
        bess_offset_kwh = 0.0
        solar_eff = self.current_solar_efficiency
        if solar_eff > 0 and 6 <= hour < 18:
            # Solar output: 297 kWp plant * efficiency * time-of-day bell curve * inverter eff
            time_factor = max(0, 1.0 - abs(hour - 12) / 6.0)
            solar_offset_kwh = 297.0 * (solar_eff / 100.0) * time_factor * 0.96  # 96% inverter eff
        # BESS discharge during peak hours offsets grid demand
        max_discharge_kw = 50.0
        if (7 <= hour <= 10 or 17 <= hour <= 21) and self.bess_soc > 10:
            bess_offset_kwh = max_discharge_kw * min(1.0, (self.bess_soc - 10) / 30.0)

        self._daily_solar_gen_kwh += solar_offset_kwh
        self._daily_bess_discharge_kwh += bess_offset_kwh

        # Track baseline (before AI) and optimized (after AI + solar/BESS)
        self._daily_baseline_kwh += base_power
        total_offset = ai_savings_kwh + solar_offset_kwh + bess_offset_kwh
        optimized_power = max(0, base_power - total_offset)
        self.current_hour_power_kw = optimized_power
        self.total_energy_kwh += optimized_power
        self._daily_sentinel_kwh += optimized_power
        self._daily_ai_savings_kwh += ai_savings_kwh

        # === BUILDING vs COUNCIL CONSUMPTION ===
        # Building load = what the building needs (after AI optimization, before solar/BESS)
        # Council meter = site_load + bess_charge_from_grid - solar - bess_discharge
        self.current_site_load_kw = max(0, base_power - ai_savings_kwh)
        self.current_solar_gen_kw = solar_offset_kwh

        # BESS charging from grid (off-peak) increases council meter reading
        bess_charge_from_grid_kw = 0.0
        if (hour < 6 or hour >= 22) and self.bess_soc < 100:
            bess_charge_from_grid_kw = 50.0 * 0.8  # Off-peak grid charge rate

        net_grid = self.current_site_load_kw + bess_charge_from_grid_kw - solar_offset_kwh - bess_offset_kwh
        self.current_grid_import_kw = max(0, net_grid)
        self.current_grid_export_kw = max(0, -net_grid)

        # === SUSTAINABILITY ACCUMULATORS (111-01) ===
        breakdown = getattr(self, "_last_hour_power_breakdown", {})
        if total_offset > 0 and base_power > 0:
            savings_ratio = min(total_offset / base_power, 1.0)
            hvac_savings = breakdown.get("hvac_kw", 0) * savings_ratio * 0.6
            lighting_savings = breakdown.get("lighting_kw", 0) * savings_ratio * 0.25
            other_savings = total_offset - hvac_savings - lighting_savings
            self._daily_hvac_kwh += max(0, breakdown.get("hvac_kw", 0) - hvac_savings)
            self._daily_lighting_kwh += max(0, breakdown.get("lighting_kw", 0) - lighting_savings)
            self._daily_other_kwh += max(0, breakdown.get("other_kw", 0) - other_savings)
        else:
            self._daily_hvac_kwh += breakdown.get("hvac_kw", 0)
            self._daily_lighting_kwh += breakdown.get("lighting_kw", 0)
            self._daily_other_kwh += breakdown.get("other_kw", 0)
        if occupancy_data:
            avg_occ = sum(occupancy_data.values()) / max(len(occupancy_data), 1)
            self._daily_occupancy_samples.append(avg_occ)

        # === POWER METER VALIDATION (A.3) ===
        try:
            power_engine = get_power_meter_validation_engine(self.site_prefix)
            result = await power_engine.validate_hourly_power(
                meter_id=f"{self.site_prefix}-MTR-B1-HVAC",
                reading_kwh=base_power,
                simulated_hour=hour,
                simulated_date=self.simulated_time,
            )
            if result.get("anomaly_detected"):
                logger.warning(f"[POWER VALIDATION] Anomaly at {hour}: {result.get('reason')}")
        except Exception as e:
            logger.debug(f"[POWER VALIDATION] Skipped: {e}")

        # === COST VALIDATION (A.4) ===
        if hour == 23:
            try:
                cost_engine = get_cost_validation_engine(self.site_prefix)
                result = await cost_engine.validate_monthly_cost(
                    invoice_period_start=self.simulated_time.replace(day=1),
                    invoice_period_end=self.simulated_time,
                    real_cost_r=None,
                )
                if result.get("variance_pct", 0) > 5:
                    logger.warning(f"[COST VALIDATION] Variance > 5%: {result.get('variance_pct')}%")
            except Exception as e:
                logger.debug(f"[COST VALIDATION] Skipped: {e}")

        # AI optimization runs when the building is occupied (HVAC active)
        if schedule_state.hvac_mode != HVACMode.OFF:
            await self._ai_optimization(f"hour_{hour}")

        # === STEP 1: BMS persists to JSON ===
        # Simulation store writes equipment health, sensor readings, energy
        equipment_states = {}
        try:
            equipment_states = await self._collect_equipment_states(hour, schedule_state)
            await self.persistence.persist_hourly_state(
                simulated_time=self.simulated_time,
                equipment_states=equipment_states,
                schedule_state=schedule_state,
                energy_kw=self.current_hour_power_kw,
                ambient_temp=ambient_temp,
                humidity=getattr(self, "current_humidity", 50.0),
            )
        except Exception as e:
            logger.warning(f"[PERSISTENCE] Failed to persist hourly state: {e}")

        # === STEP 2: SENTINEL syncs to Supabase + ML ===
        # After BMS JSON persist, SENTINEL updates equipment operating_data,
        # zone temperatures, and feeds ML pipeline
        if equipment_states:
            try:
                await self.sentinel_sync.ingest_equipment_states(equipment_states, self.simulated_time)
            except Exception as e:
                logger.warning(f"[SENTINEL SYNC] Failed: {e}")

        # === PERSIST SOLAR SNAPSHOT TO SUPABASE ===
        # Write solar/BESS state to solar_hourly_snapshots for dashboard
        try:
            if equipment_states:
                await self.persistence.persist_solar_snapshot(
                    simulated_time=self.simulated_time,
                    equipment_states=equipment_states,
                    site_load_kw=self.current_site_load_kw,
                    tariff_band=tariff,
                    tariff_rate=self._get_tariff_rate(tariff),
                    hour_index=self._solar_hour_index,
                )
                # Track daily solar accumulators from equipment states
                self._accumulate_solar_daily(equipment_states)
                self._solar_hour_index += 1
        except Exception as e:
            logger.debug(f"[SOLAR SNAPSHOT] Failed: {e}")

        # Runtime processing/ingestion gates now live at the SIMBIOT connector
        # boundary. The building simulator should not own the site connection
        # state.

        # ML feeding is handled by SENTINEL persistence layer (simulation_persistence.py)
        # after writing to Supabase — SENTINEL feeds ML, not the orchestrator.

        # === HEALTH MONITORING & ALERT PIPELINE (106-01) ===
        # Monitor equipment health against thresholds, trigger alerts on transitions
        try:
            await self._monitor_equipment_health(equipment_states, hour)
        except Exception as e:
            logger.warning(f"[HEALTH MONITOR] Failed health monitoring at hour {hour}: {e}")

        # === SAFETY BOUNDARY SCANNING (106-02) — replaced by SentinelAlertEngine ===
        # Old: self._scan_safety_boundaries(equipment_states, hour, schedule_state)
        # New: Equipment-type-aware engine with chiller ramp-up suppression
        try:
            if equipment_states:
                is_peak = False
                if schedule_state:
                    is_peak = schedule_state.state in (
                        BuildingState.PEAK_OCCUPIED,
                        BuildingState.OCCUPIED_RAMPUP,
                        BuildingState.MORNING_STARTUP,
                    )
                alert_context = AlertContext(
                    simulated_hour=hour,
                    is_peak=is_peak,
                    site_state=schedule_state.state.value if schedule_state else "unknown",
                    occupancy_pct=schedule_state.target_occupancy_pct if schedule_state else 0,
                    hvac_mode=schedule_state.hvac_mode.value if schedule_state else "unknown",
                )
                violations = self._sentinel_alert_engine.evaluate(equipment_states, alert_context)
                for v in violations:
                    action_preview = (
                        v.recommended_action[:80] if len(v.recommended_action) > 80 else v.recommended_action
                    )
                    description = (
                        f"{v.equipment_code} {v.point_name} at {v.value}{v.unit} "
                        f"({v.limit_desc}). Action: {action_preview}"
                    )
                    self._emit_event(
                        LifecycleEvent(
                            timestamp=datetime.now(),
                            simulated_hour=hour,
                            event_type=EventType.SAFETY_VIOLATION
                            if v.severity == "critical"
                            else EventType.ALERT_CREATED,
                            equipment_id=v.equipment_code,
                            description=description,
                            details={
                                "code": v.equipment_code,
                                "point": v.point_name,
                                "value": v.value,
                                "limits": f"{v.limit_min}-{v.limit_max} {v.unit}",
                                "approach_pct": v.approach_pct,
                                "severity": v.severity,
                                "recommended_action": v.recommended_action,
                                "operational_context": v.operational_context,
                                "limit_desc": v.limit_desc,
                            },
                        )
                    )
                    self._push_alert_to_dashboard(
                        equipment_code=v.equipment_code,
                        severity=v.severity,
                        alert_type="safety_boundary",
                        message=description,
                        details={
                            "code": v.equipment_code,
                            "point": v.point_name,
                            "value": v.value,
                            "severity": v.severity,
                            "recommended_action": v.recommended_action,
                            "limit_desc": v.limit_desc,
                        },
                    )
                    if v.severity == "critical":
                        try:
                            from app.services.equipment_alert_service import get_equipment_alert_service

                            alert_svc = get_equipment_alert_service()
                            alert_svc.create_alert_for_equipment(
                                equipment_id=v.equipment_code,
                                alert_type="safety_boundary",
                                severity="critical",
                                message=description,
                                site_id=self.site_id,
                                notify_telegram=True,
                            )
                        except Exception as e:
                            logger.debug(f"Could not send Sentry notification for safety violation: {e}")
        except Exception as e:
            logger.warning(f"[SAFETY SCAN] Failed safety boundary scan at hour {hour}: {e}")

        # === ZONE TEMPERATURE DEVIATION MONITORING ===
        # Check zone temps against setpoints — independent of equipment running state.
        # This catches building-wide cooling/heating failures that equipment-level scans miss.
        try:
            if self.zone_temperatures:
                await self._monitor_zone_temperatures(hour)
        except Exception as e:
            logger.warning(f"[ZONE TEMP] Failed zone temperature monitoring at hour {hour}: {e}")

    async def _write_daily_sustainability(self):
        """Emit daily sustainability metrics at end of simulated day (111-01)."""
        try:
            energy_breakdown = {
                "total_kwh": self._daily_hvac_kwh + self._daily_lighting_kwh + self._daily_other_kwh,
                "hvac_kwh": self._daily_hvac_kwh,
                "lighting_kwh": self._daily_lighting_kwh,
                "other_kwh": self._daily_other_kwh,
            }
            occ_samples = self._daily_occupancy_samples
            occupancy_data = {
                "avg_pct": sum(occ_samples) / max(len(occ_samples), 1),
                "peak_count": int(max(occ_samples, default=0) / 100 * 150),  # 150 capacity
            }

            metrics = await self._sustainability_collector.collect_daily_metrics(
                date=self.simulated_time.date(),
                energy_breakdown=energy_breakdown,
                occupancy_data=occupancy_data,
            )
            await self._sustainability_collector.persist(metrics)

            # Track cumulative AI optimization totals
            self._cumulative_baseline_kwh += self._daily_baseline_kwh
            self._cumulative_sentinel_kwh += self._daily_sentinel_kwh
            self._cumulative_solar_gen_kwh += self._daily_solar_gen_kwh
            self._cumulative_bess_discharge_kwh += self._daily_bess_discharge_kwh

            logger.info(
                f"[SUSTAINABILITY] Day {self.days_simulated}: "
                f"grid={energy_breakdown['total_kwh']:.1f} kWh, "
                f"hvac={energy_breakdown['hvac_kwh']:.1f} kWh, "
                f"scope2={metrics.scope2_kg_co2:.1f} kg CO2, "
                f"ai_savings={self._daily_ai_savings_kwh:.1f} kWh, "
                f"solar={self._daily_solar_gen_kwh:.1f} kWh, "
                f"bess={self._daily_bess_discharge_kwh:.1f} kWh"
            )
        except Exception as e:
            logger.warning(f"[SUSTAINABILITY] Failed to write daily metrics: {e}")

        # === PERSIST SOLAR DAILY AGGREGATE ===
        try:
            avg_soc = (
                sum(self._daily_bess_soc_samples) / len(self._daily_bess_soc_samples)
                if self._daily_bess_soc_samples
                else 50.0
            )
            await self.persistence.persist_solar_daily(
                simulated_date=self.simulated_time.date(),
                solar_gen_kwh=self._daily_solar_gen_kwh,
                site_load_kwh=self._daily_baseline_kwh,
                bess_charge_kwh=self._daily_bess_charge_kwh,
                bess_discharge_kwh=self._daily_bess_discharge_kwh,
                grid_import_kwh=self._daily_grid_import_kwh,
                grid_export_kwh=self._daily_grid_export_kwh,
                peak_generation_kw=self._daily_peak_solar_kw,
                avg_bess_soc_pct=avg_soc,
            )
        except Exception as e:
            logger.debug(f"[SOLAR DAILY] Failed: {e}")

        # Reset daily accumulators regardless of success
        self._daily_hvac_kwh = 0.0
        self._daily_lighting_kwh = 0.0
        self._daily_other_kwh = 0.0
        self._daily_occupancy_samples = []
        self._daily_baseline_kwh = 0.0
        self._daily_sentinel_kwh = 0.0
        self._daily_ai_savings_kwh = 0.0
        self._daily_solar_gen_kwh = 0.0
        self._daily_bess_discharge_kwh = 0.0
        self._daily_bess_charge_kwh = 0.0
        self._daily_grid_import_kwh = 0.0
        self._daily_grid_export_kwh = 0.0
        self._daily_peak_solar_kw = 0.0
        self._daily_bess_soc_samples = []

    def get_energy_comparison_data(self) -> dict:
        """Return baseline vs optimized energy for comparison API.

        SENTINEL savings include: AI rules engine + solar generation offset + BESS discharge.
        """
        baseline = self._cumulative_baseline_kwh + self._daily_baseline_kwh
        sentinel = self._cumulative_sentinel_kwh + self._daily_sentinel_kwh
        solar_gen = self._cumulative_solar_gen_kwh + self._daily_solar_gen_kwh
        bess_discharge = self._cumulative_bess_discharge_kwh + self._daily_bess_discharge_kwh
        if baseline <= 0:
            baseline = self.total_energy_kwh
            sentinel = self.total_energy_kwh
        savings_pct = ((baseline - sentinel) / baseline * 100) if baseline > 0 else 0
        return {
            "baseline_kwh": round(baseline, 2),
            "dali_kwh": round(baseline * 0.80, 2),  # DALI provides ~20% lighting savings (industry benchmark)
            "sentinel_kwh": round(sentinel, 2),
            "savings_kwh": round(baseline - sentinel, 2),
            "savings_percent": round(savings_pct, 1),
            "solar_gen_kwh": round(solar_gen, 2),
            "bess_discharge_kwh": round(bess_discharge, 2),
            "days_simulated": self.days_simulated,
        }

    async def _emit_schedule_event(self, hour: int, schedule_state: ScheduleState):
        """Emit events on meaningful schedule transitions."""
        event_map = {
            BuildingState.PRE_COOL: (
                EventType.BUILDING_WAKE,
                "Pre-cool cycle started -- pulling overnight heat from zones",
            ),
            BuildingState.MORNING_STARTUP: (
                EventType.BUILDING_WAKE,
                "Full plant online -- chillers staged, AHUs at design speed",
            ),
            BuildingState.OCCUPIED_RAMPUP: (
                EventType.OCCUPANCY_INCREASE,
                "Staff arriving -- occupancy ramping, HVAC at full capacity",
            ),
            BuildingState.AFTERNOON_WINDDOWN: (
                EventType.OCCUPANCY_DECREASE,
                "Staff leaving -- HVAC de-staging",
            ),
            BuildingState.HVAC_SHUTDOWN: (
                EventType.NIGHT_MODE,
                "HVAC shutdown -- building coasting on thermal mass",
            ),
            BuildingState.UNOCCUPIED: (
                EventType.NIGHT_MODE,
                "Building empty -- security mode activated",
            ),
        }
        mapping = event_map.get(schedule_state.state)
        if mapping:
            event_type, description = mapping
            self._emit_event(
                LifecycleEvent(
                    timestamp=datetime.now(),
                    simulated_hour=hour,
                    event_type=event_type,
                    description=description,
                    details={
                        "schedule_state": schedule_state.state.value,
                        "hvac_mode": schedule_state.hvac_mode.value,
                        "chiller": schedule_state.chiller_staging.value,
                        "occupancy_target": schedule_state.target_occupancy_pct,
                    },
                )
            )

    @staticmethod
    def _get_tariff_rate(tariff_band: str) -> float:
        """Return tariff rate in c/kWh for a given band (SA commercial rates)."""
        rates = {"peak": 350.0, "standard": 200.0, "off_peak": 80.0}
        return rates.get(tariff_band, 200.0)

    def _accumulate_solar_daily(self, equipment_states: dict) -> None:
        """Accumulate solar/BESS data for daily aggregation from equipment states."""
        hourly_solar_kw = 0.0
        for _code, state in equipment_states.items():
            if state.get("type", "").lower() == "inverter":
                readings = state.get("sensor_readings", {})
                hourly_solar_kw += readings.get("ac_power_kw", 0.0)

        for _code, state in equipment_states.items():
            if state.get("type", "").lower() == "bess":
                readings = state.get("sensor_readings", {})
                self._daily_bess_charge_kwh += readings.get("charge_power_kw", 0.0)
                soc = readings.get("state_of_charge_pct", 50.0)
                self._daily_bess_soc_samples.append(soc)
                break

        # Use pre-computed grid values from energy section
        self._daily_grid_import_kwh += self.current_grid_import_kw
        self._daily_grid_export_kwh += self.current_grid_export_kw
        self._daily_peak_solar_kw = max(self._daily_peak_solar_kw, hourly_solar_kw)

    def _calculate_hourly_power(self, schedule_state: ScheduleState, occupancy_data: dict[str, float]) -> float:
        """Calculate realistic hourly power based on equipment staging.

        Args:
            schedule_state: Current building schedule state
            occupancy_data: Zone occupancy percentages

        Returns:
            Power consumption in kW for this hour
        """
        # Base loads (always-on: UPS, security, lifts, IT) — 9,000 sqm building
        base_kw = 25.0

        # HVAC power based on chiller staging (scaled for 9,000 sqm)
        hvac_kw = {
            "off": 0.0,
            "stage_1": 80.0,  # ~25% chiller + AHU
            "stage_2": 200.0,  # ~60% chiller + AHU + pumps
            "full_load": 320.0,  # Full cooling plant
        }.get(schedule_state.chiller_staging.value, 0.0)

        # AHU fan power (proportional to fan %)
        ahu_kw = (schedule_state.ahu_fan_pct / 100.0) * 60.0  # 60kW at 100%

        # Lighting power based on mode (20 zones × 4.5 kW baseline)
        lighting_kw = {
            "off": 0.0,
            "security_only": 3.0,
            "dimmed": 15.0,
            "full": 54.0,
            "daylight_harvest": 35.0,
        }.get(schedule_state.lighting_mode.value, 0.0)

        # Occupancy-driven misc loads (computers, appliances) — 400 desks
        if occupancy_data:
            avg_occupancy = sum(occupancy_data.values()) / len(occupancy_data)
        else:
            avg_occupancy = schedule_state.target_occupancy_pct
        misc_kw = (avg_occupancy / 100.0) * 80.0  # 80kW at full occupancy

        total = base_kw + hvac_kw + ahu_kw + lighting_kw + misc_kw
        # Add +/-5% noise for realism
        noise = self._scenario_rng.uniform(0.95, 1.05)
        total_noisy = round(total * noise, 1)

        # Store breakdown for sustainability collector (111-01)
        self._last_hour_power_breakdown = {
            "hvac_kw": round((hvac_kw + ahu_kw) * noise, 1),
            "lighting_kw": round(lighting_kw * noise, 1),
            "other_kw": round((base_kw + misc_kw) * noise, 1),
            "total_kw": total_noisy,
        }

        return total_noisy

    def _generate_occupancy_for_hour(self, hour: int) -> dict[str, float]:
        """
        Generate zone occupancy percentages for all zones based on hour of day.

        Returns:
            Dictionary mapping zone_id -> occupancy_percent (0-100)
        """
        # Get day-of-week info
        day_of_week = self.simulated_time.weekday()  # 0=Monday, 6=Sunday
        is_weekend = day_of_week >= 5
        is_holiday = self._is_site_holiday()

        # Site 002 zone occupancy profiles, including both meeting rooms on each office floor.
        zone_profiles = {
            "Zone-B1-001": "utility",  # Basement plant room
            "Zone-L1-A": "office",  # Level 1 Zone A
            "Zone-L1-B": "office",  # Level 1 Zone B
            "Zone-L1-C": "office",  # Level 1 Zone C
            "Zone-L1-D": "office",  # Level 1 Zone D
            "Zone-L1-E": "office",  # Level 1 Zone E
            "Zone-L1-MR1": "meeting",  # Level 1 meeting room
            "Zone-L1-MR2": "meeting",  # Level 1 meeting room
            "Zone-L2-A": "office",  # Level 2 Zone A
            "Zone-L2-B": "office",  # Level 2 Zone B
            "Zone-L2-C": "office",  # Level 2 Zone C
            "Zone-L2-D": "office",  # Level 2 Zone D
            "Zone-L2-E": "office",  # Level 2 Zone E
            "Zone-L2-MR1": "meeting",  # Level 2 meeting room
            "Zone-L2-MR2": "meeting",  # Level 2 meeting room
            "Zone-L3-A": "office",  # Level 3 Zone A
            "Zone-L3-B": "office",  # Level 3 Zone B
            "Zone-L3-C": "office",  # Level 3 Zone C
            "Zone-L3-D": "office",  # Level 3 Zone D
            "Zone-L3-E": "office",  # Level 3 Zone E
            "Zone-L3-MR1": "meeting",  # Level 3 meeting room
            "Zone-L3-MR2": "meeting",  # Level 3 meeting room
        }

        occupancy_data = {}

        for zone_id, zone_type in zone_profiles.items():
            # Calculate occupancy using existing dali logic
            occupancy_pct = calculate_zone_occupancy(
                hour=hour,
                day_of_week=day_of_week,
                is_weekend=is_weekend,
                zone_type=zone_type,
                is_holiday=is_holiday,
                rng=self._scenario_rng,
            )

            # Apply seasonal variation if in annual simulation
            if self.seasonal_modeler:
                seasonal_factor = self._get_seasonal_occupancy_factor(hour)
                occupancy_pct *= seasonal_factor

            # Add small random variation for realism (±5%)
            variance = self._scenario_rng.uniform(0.95, 1.05)
            occupancy_pct *= variance

            # Clamp to 0-100%
            occupancy_data[zone_id] = max(0.0, min(100.0, occupancy_pct))

        return occupancy_data

    def _is_site_holiday(self) -> bool:
        """Return whether the current simulated date is a configured holiday."""
        return self.site_holiday_service.is_holiday(self.site_id, self.simulated_time.date())

    def _get_zone_occupancy(self, zone_id: str) -> float:
        """Map a temperature zone (Zone-001..Zone-205) to DALI occupancy %.

        Temperature zones use numeric IDs while DALI occupancy zones use
        floor-letter IDs.  Mapping:
          Zone-001..005 (B1/L0)  → Zone-B1-001 (utility, typically low)
          Zone-101,102,103 (L1)  → Zone-L1-A
          Zone-104,105     (L1)  → Zone-L1-B
          Zone-201,202,203 (L2)  → Zone-L2-A
          Zone-204,205     (L2)  → Zone-L2-B
        """
        if not self.current_occupancy_data:
            return 50.0  # Fallback: assume moderate occupancy

        # Parse numeric zone number from "Zone-NNN"
        parts = zone_id.split("-")
        if len(parts) < 2 or not parts[-1].isdigit():
            return 50.0
        zone_num = int(parts[-1])

        if zone_num <= 99:
            # Basement / L0 → Zone-B1-001
            return self.current_occupancy_data.get("Zone-B1-001", 10.0)
        elif zone_num <= 199:
            # L1: 101-103 → L1-A, 104-105 → L1-B
            if zone_num <= 103:
                return self.current_occupancy_data.get("Zone-L1-A", 50.0)
            else:
                return self.current_occupancy_data.get("Zone-L1-B", 50.0)
        elif zone_num <= 299:
            # L2: 201-203 → L2-A, 204-205 → L2-B
            if zone_num <= 203:
                return self.current_occupancy_data.get("Zone-L2-A", 50.0)
            else:
                return self.current_occupancy_data.get("Zone-L2-B", 50.0)
        return 50.0

    def _emit_occupancy_bridge_events(self, hour: int):
        """Emit cross-module bridge events when zones transition occupied↔unoccupied."""
        # Map temperature zones to their occupancy
        default_zones = [f"Zone-{z:03d}" for z in list(range(1, 6)) + list(range(101, 106)) + list(range(201, 206))]
        for zone_id in default_zones:
            occ_pct = self._get_zone_occupancy(zone_id)
            is_occupied = occ_pct >= 10.0
            was_occupied = self._prev_zone_occupancy_state.get(zone_id, True)

            if was_occupied and not is_occupied:
                # Transition: occupied → unoccupied
                self._emit_event(
                    LifecycleEvent(
                        timestamp=datetime.now(),
                        simulated_hour=hour,
                        event_type=EventType.AI_OPTIMIZATION,
                        description=(
                            f"DALI\u2192HVAC bridge: {zone_id} unoccupied ({occ_pct:.0f}%) "
                            f"\u2192 VAV damper 15%, setpoint +2\u00b0C"
                        ),
                        details={
                            "bridge": "dali_hvac_occupancy",
                            "zone": zone_id,
                            "occupancy_pct": round(occ_pct, 1),
                            "action": "reduce_cooling",
                            "damper_min_pct": 15,
                            "setpoint_offset_c": 2.0,
                        },
                    )
                )
            elif not was_occupied and is_occupied:
                # Transition: unoccupied → occupied
                self._emit_event(
                    LifecycleEvent(
                        timestamp=datetime.now(),
                        simulated_hour=hour,
                        event_type=EventType.AI_OPTIMIZATION,
                        description=(
                            f"DALI\u2192HVAC bridge: {zone_id} occupied ({occ_pct:.0f}%) \u2192 restore full cooling"
                        ),
                        details={
                            "bridge": "dali_hvac_occupancy",
                            "zone": zone_id,
                            "occupancy_pct": round(occ_pct, 1),
                            "action": "restore_cooling",
                        },
                    )
                )

            self._prev_zone_occupancy_state[zone_id] = is_occupied

    async def _building_wake(self):
        """Simulate building morning startup."""
        self._emit_event(
            LifecycleEvent(
                timestamp=datetime.now(),
                simulated_hour=6,
                event_type=EventType.BUILDING_WAKE,
                description="Building systems starting up for the day",
                details={"hvac_mode": "pre_cooling", "lighting": "minimal"},
            )
        )

        # AI optimization handled by hourly check in _process_hour

    async def _occupancy_increase(self):
        """Simulate morning occupancy increase with realistic day-to-day variation."""
        # Day-of-week variation (Monday=100%, Friday=80%, realistic WFH/hybrid patterns)
        day_of_week = self.simulated_time.weekday()  # 0=Monday, 6=Sunday
        day_factor = [1.0, 0.95, 0.90, 0.88, 0.80, 0.3, 0.2][day_of_week]  # Mon-Sun

        # Seeded random variation (±10% reproducible)
        occupancy_variance = self._scenario_rng.uniform(0.90, 1.10)
        occupancy_percent = int(60 * day_factor * occupancy_variance)

        # Apply seasonal occupancy factor if in annual simulation
        if self.seasonal_modeler:
            seasonal_factor = self._get_seasonal_occupancy_factor(8)
            occupancy_percent = int(occupancy_percent * seasonal_factor)

        zones_active = max(2, int(12 * day_factor * occupancy_variance / 100) * 100 // 100)

        self._emit_event(
            LifecycleEvent(
                timestamp=datetime.now(),
                simulated_hour=8,
                event_type=EventType.OCCUPANCY_INCREASE,
                description=f"Occupancy increasing - staff arriving (~{occupancy_percent}%)",
                details={"occupancy_percent": occupancy_percent, "zones_active": zones_active},
            )
        )

        # Adjust setpoints for occupancy
        await self._setpoint_change("cooling_setpoint", 22.0, "Occupied mode")
        await self._setpoint_change("lighting_level", int(80 * day_factor), "Occupied mode")

    async def _peak_load(self):
        """Simulate peak load period."""
        self._emit_event(
            LifecycleEvent(
                timestamp=datetime.now(),
                simulated_hour=11,
                event_type=EventType.PEAK_LOAD,
                description="Peak cooling load - maximum demand",
                details={"load_percent": 95, "ambient_temp": 32},
            )
        )

    async def _occupancy_decrease(self):
        """Simulate evening occupancy decrease with realistic variation."""
        # Day-of-week variation (some people leave early Friday, more people Friday night)
        day_of_week = self.simulated_time.weekday()
        day_factor = [0.9, 0.85, 0.85, 0.88, 1.2, 0.1, 0.05][day_of_week]  # Mon-Sun

        # Seeded random variation (±15% reproducible)
        occupancy_variance = self._scenario_rng.uniform(0.85, 1.15)
        occupancy_percent = max(5, int(20 * day_factor * occupancy_variance))
        zones_active = max(1, int(occupancy_percent / 5))

        self._emit_event(
            LifecycleEvent(
                timestamp=datetime.now(),
                simulated_hour=18,
                event_type=EventType.OCCUPANCY_DECREASE,
                description=f"Occupancy decreasing - staff leaving (~{occupancy_percent}%)",
                details={"occupancy_percent": occupancy_percent, "zones_active": zones_active},
            )
        )

        # Adjust setpoints for reduced occupancy
        await self._setpoint_change("cooling_setpoint", 25.0, "Unoccupied mode")
        await self._setpoint_change("lighting_level", int(30 * day_factor), "Unoccupied mode")

    async def _night_mode(self):
        """Simulate night mode."""
        self._emit_event(
            LifecycleEvent(
                timestamp=datetime.now(),
                simulated_hour=22,
                event_type=EventType.NIGHT_MODE,
                description="Building entering night mode",
                details={"hvac_mode": "setback", "lighting": "security_only"},
            )
        )

    async def _ai_optimization(self, context: str):
        """Simulate AI optimization cycle - generates occupancy-aware + daylight-aware recommendations."""
        try:
            # Get current building state
            current_hour = self.simulated_time.hour

            # Calculate occupancy based on hour
            occupancy_percent = self._calculate_occupancy(current_hour)

            # Calculate daylight factor (0-100%, peaks at noon)
            daylight_factor = self._calculate_daylight(current_hour)

            # Determine zones that should be active
            zones_active = max(1, int(occupancy_percent / 8)) if occupancy_percent > 10 else 0

            logger.info(
                f"AI Optimization ({context}): hour={current_hour}, "
                f"occupancy={occupancy_percent}%, daylight={daylight_factor}%, zones={zones_active}"
            )

            recommendations_created = []
            hvac_recs = []
            dali_recs = []

            # ========== OPTIMIZATION MODE DISPATCH ==========
            if self._optimization_mode == "sentinel":
                equipment_list = self.equipment_repo.get_all()
                if not equipment_list:
                    return

                # Filter to target site if available — process ALL equipment (no cap)
                equip_prefix = f"{self.site_prefix}-"
                site_equipment = [eq for eq in equipment_list if eq.get("code", "").startswith(equip_prefix)]
                if not site_equipment:
                    site_equipment = equipment_list

                # Filter to controllable equipment
                controllable_equipment = [
                    eq
                    for eq in site_equipment
                    if self.device_control_service.is_controllable(eq.get("code", eq.get("id")))
                ]

                # Track lighting equipment (never optimized by AI — Tridonic handles natively)
                for eq in site_equipment:
                    eq_type = eq.get("type", "unknown").lower()
                    if eq_type in ["dali", "luminaire", "controller", "dali_zone"]:
                        dali_recs.append(eq.get("code", eq.get("id")))

                sentinel_recs = await self._sentinel_optimization(
                    controllable_equipment, context, occupancy_percent, daylight_factor, current_hour
                )
                recommendations_created = sentinel_recs
                hvac_recs = [r.get("equipment", "") for r in sentinel_recs]
            elif self._optimization_mode == "hybrid":
                equipment_list = self.equipment_repo.get_all()
                if not equipment_list:
                    return

                equip_prefix = f"{self.site_prefix}-"
                site_equipment = [eq for eq in equipment_list if eq.get("code", "").startswith(equip_prefix)]
                if not site_equipment:
                    site_equipment = equipment_list

                controllable_equipment = [
                    eq
                    for eq in site_equipment
                    if self.device_control_service.is_controllable(eq.get("code", eq.get("id")))
                ]

                for eq in site_equipment:
                    eq_type = eq.get("type", "unknown").lower()
                    if eq_type in ["dali", "luminaire", "controller", "dali_zone"]:
                        dali_recs.append(eq.get("code", eq.get("id")))

                sentinel_recs = await self._sentinel_optimization(
                    controllable_equipment, context, occupancy_percent, daylight_factor, current_hour
                )
                hardcoded_plan = self._build_hardcoded_control_plan(
                    context=context,
                    occupancy_percent=occupancy_percent,
                    daylight_factor=daylight_factor,
                    current_hour=current_hour,
                    zones_active=zones_active,
                )
                hardcoded_recs = hardcoded_plan["recommendations"]
                self._log_optimization_comparison(sentinel_recs, hardcoded_recs, current_hour)
                # Use SENTINEL results, log hardcoded for comparison
                recommendations_created = sentinel_recs
                hvac_recs = [r.get("equipment", "") for r in sentinel_recs]
            else:  # "hardcoded"
                hardcoded_plan = self._build_hardcoded_control_plan(
                    context=context,
                    occupancy_percent=occupancy_percent,
                    daylight_factor=daylight_factor,
                    current_hour=current_hour,
                    zones_active=zones_active,
                )
                recommendations_created = hardcoded_plan["recommendations"]
                hvac_recs = hardcoded_plan["hvac_recommendations"]
                dali_recs = hardcoded_plan["dali_recommendations"]

            # Emit comprehensive optimization event
            self._emit_event(
                LifecycleEvent(
                    timestamp=datetime.now(),
                    simulated_hour=current_hour,
                    event_type=EventType.AI_OPTIMIZATION,
                    description=(
                        f"AI optimization ({context}) - Occupancy {occupancy_percent}%, "
                        f"Daylight {daylight_factor}%, {len(recommendations_created)} recommendations pending"
                    ),
                    details={
                        "context": context,
                        "occupancy_percent": occupancy_percent,
                        "daylight_factor": daylight_factor,
                        "zones_active": zones_active,
                        "hvac_recommendations": len(hvac_recs),
                        "dali_recommendations": len(dali_recs),
                        "total_recommendations": len(recommendations_created),
                        "recommendations": recommendations_created,
                    },
                )
            )
        except Exception as e:
            logger.warning(f"AI optimization error: {e}")

    def _build_hardcoded_control_plan(
        self,
        *,
        context: str,
        occupancy_percent: int,
        daylight_factor: int,
        current_hour: int,
        zones_active: int,
    ) -> dict[str, Any]:
        """Build a simulator-owned control plan without any SENTINEL coupling.

        This method is the stable seam for the lifecycle engine's internal
        building behavior. It scopes equipment to the current site, filters to
        controllable assets, applies the hardcoded control policy, and appends
        demo-only building actions such as BESS arbitrage.
        """
        equipment_list = self.equipment_repo.get_all()
        if not equipment_list:
            return {
                "context": context,
                "occupancy_percent": occupancy_percent,
                "daylight_factor": daylight_factor,
                "zones_active": zones_active,
                "hvac_recommendations": [],
                "dali_recommendations": [],
                "total_recommendations": 0,
                "recommendations": [],
            }

        equip_prefix = f"{self.site_prefix}-"
        site_equipment = [eq for eq in equipment_list if eq.get("code", "").startswith(equip_prefix)]
        if not site_equipment:
            site_equipment = equipment_list

        controllable_equipment = [
            eq for eq in site_equipment if self.device_control_service.is_controllable(eq.get("code", eq.get("id")))
        ]
        dali_recs = []
        for eq in site_equipment:
            eq_type = eq.get("type", "unknown").lower()
            if eq_type in ["dali", "luminaire", "controller", "dali_zone"]:
                dali_recs.append(eq.get("code", eq.get("id")))

        recommendations = self._hardcoded_optimization_batch(
            controllable_equipment, context, occupancy_percent, daylight_factor, current_hour
        )

        return {
            "context": context,
            "occupancy_percent": occupancy_percent,
            "daylight_factor": daylight_factor,
            "zones_active": zones_active,
            "hvac_recommendations": [r.get("equipment", "") for r in recommendations],
            "dali_recommendations": dali_recs,
            "total_recommendations": len(recommendations),
            "recommendations": recommendations,
        }

    def _calculate_occupancy(self, hour: int) -> int:
        """Calculate occupancy percent based on hour and day of week.

        Applies weekend/holiday factors: Sat 30%, Sun 20% of weekday base.
        """
        day_of_week = self.simulated_time.weekday() if self.simulated_time else 0
        is_weekend = day_of_week >= 5
        is_holiday = self._is_site_holiday()
        occupancy_percent = calculate_building_occupancy_percent(
            hour=hour,
            day_of_week=day_of_week,
            is_weekend=is_weekend,
            is_holiday=is_holiday,
            rng=self._scenario_rng,
            demo_mode=bool(self.current_scenario and self.current_scenario.demo_mode),
        )

        if self.seasonal_modeler:
            occupancy_percent *= self._get_seasonal_occupancy_factor(hour)

        return int(max(0, min(100, occupancy_percent)))

    def _calculate_daylight(self, hour: int) -> int:
        """Calculate available natural daylight as percentage (0-100%)."""
        if hour < 6 or hour >= 20:
            return 0  # Night: 0% daylight
        elif hour < 8:
            return int((hour - 6) * 25)  # 0-50% (sunrise ramp)
        elif hour < 12:
            return int(50 + (hour - 8) * 10)  # 50-90% (morning increase)
        elif hour < 13:
            return 100  # Peak: full daylight at noon
        elif hour < 16:
            return int(100 - (hour - 13) * 10)  # 100-70% (afternoon decline)
        elif hour < 18:
            return int(70 - (hour - 16) * 20)  # 70-30% (sunset ramp down)
        else:
            return int(max(0, 30 - (hour - 18) * 10))  # 30-0% (sunset finish)

    def _get_seasonal_occupancy_factor(self, hour: int) -> float:
        """Get occupancy factor with seasonal adjustments for annual simulations."""
        if not self.seasonal_modeler:
            # No seasonal modeler: return 1.0 (no adjustment)
            return 1.0

        # Get seasonal occupancy factor from modeler
        rain_today = self.seasonal_modeler.should_rain_today(self.simulated_time.date())
        seasonal_factor = self.seasonal_modeler.get_occupancy_factor(self.simulated_time.date(), hour, rain_today)
        return seasonal_factor

    def _get_seasonal_fault_probability(self, base_probability: float) -> float:
        """Get fault probability adjusted for seasonal stress."""
        if not self.seasonal_modeler:
            # No seasonal modeler: use base probability
            return base_probability

        # Get seasonal multiplier from modeler
        rain_today = self.seasonal_modeler.should_rain_today(self.simulated_time.date())
        multiplier = self.seasonal_modeler.get_fault_probability_multiplier(self.simulated_time.date(), rain_today)
        # Apply multiplier to base probability (capped at 1.0 for daily chance)
        return min(1.0, base_probability * multiplier)

    def _get_demo_thresholds(self) -> tuple:
        """Return (low_occupancy, high_occupancy) thresholds adjusted for demo mode."""
        is_demo = self.current_scenario and self.current_scenario.demo_mode
        return (30 if is_demo else 20, 70 if is_demo else 80)

    # ========== SENTINEL AI OPTIMIZATION WIRING (v28.0) ==========
    #
    # Architecture: The simulation is the fake building. SENTINEL is the real system.
    # The simulation writes BMS data to Supabase (equipment health, sensor readings,
    # zone history). SENTINEL reads from Supabase through AIOptimizerService — the
    # exact same code path it uses with a real building.
    #
    # Flow:
    #   Simulation → persist_hourly_state() → Supabase
    #   SENTINEL  → AIOptimizerService.analyze_building() → reads Supabase → Claude → QualityGate
    #

    def _compute_state_fingerprint(self, occupancy_percent: int, current_hour: int, daylight_factor: int) -> str:
        """Quantize building state into coarse buckets for analyze_building() caching.

        Same fingerprint = skip re-running SENTINEL. Reduces LLM calls by ~60%.
        Expected ~8-12 unique fingerprints per day instead of 24.
        """
        # Occupancy: 10% buckets
        occ_bucket = (occupancy_percent // 10) * 10
        # Hour: 3-hour periods
        hour_bucket = (current_hour // 3) * 3
        # Daylight: 25% buckets
        day_bucket = (daylight_factor // 25) * 25
        # HVAC mode from building schedule
        hvac_mode = "unknown"
        if self.site_schedule:
            try:
                state = self.site_schedule.get_state(self.simulated_time)
                hvac_mode = state.hvac_mode.value
            except Exception:
                pass
        return f"occ{occ_bucket}_hr{hour_bucket}_dl{day_bucket}_hvac{hvac_mode}"

    async def _sentinel_optimization(
        self,
        controllable_equipment: list[dict],
        context: str,
        occupancy_percent: int,
        daylight_factor: int,
        current_hour: int,
    ) -> list[dict]:
        """Run SENTINEL optimization via LLM — DEPRECATED for simulation use.

        Simulation should NEVER consume LLM tokens. The simulation uses
        rule-based (_hardcoded_optimization_batch) for its own equipment
        state progression. SENTINEL's background scheduler (every 15 min)
        independently runs LLM-powered analyze_building() — that's the
        correct production path and it writes recommendations to Supabase.

        This method is retained for manual/hybrid testing only.

        Returns list of recommendation dicts for event tracking.
        """
        from app.config.settings import settings as app_settings

        # Simulation must not consume LLM tokens — always use hardcoded
        if app_settings.simulation_optimization_mode == "hardcoded":
            logger.debug("Simulation using rule-based optimization (no LLM tokens)")
            return self._hardcoded_optimization_batch(
                controllable_equipment, context, occupancy_percent, daylight_factor, current_hour
            )

        # Skip if no LLM available
        if app_settings.local_ai_only:
            logger.debug("local_ai_only=true, falling back to hardcoded optimization")
            return self._hardcoded_optimization_batch(
                controllable_equipment, context, occupancy_percent, daylight_factor, current_hour
            )

        # Fingerprint cache — avoid redundant analyze_building() calls
        fingerprint = self._compute_state_fingerprint(occupancy_percent, current_hour, daylight_factor)
        if fingerprint == self._last_state_fingerprint and self._cached_sentinel_recs:
            logger.info(
                f"SENTINEL cache hit (fingerprint={fingerprint}), reusing {len(self._cached_sentinel_recs)} recs"
            )
            return self._cached_sentinel_recs

        # Budget check
        if self._llm_call_count >= app_settings.simulation_llm_budget_max_calls:
            logger.warning(
                f"SENTINEL LLM budget exhausted "
                f"({self._llm_call_count}/{app_settings.simulation_llm_budget_max_calls}), "
                "falling back to hardcoded"
            )
            return self._hardcoded_optimization_batch(
                controllable_equipment, context, occupancy_percent, daylight_factor, current_hour
            )

        # Call the REAL SENTINEL optimization service — same as production
        try:
            from app.services.ai_optimizer import get_ai_optimizer

            optimizer = get_ai_optimizer()
            result = await optimizer.analyze_building(self.site_id)
            self._llm_call_count += 1

            # Convert OptimizationRecommendation to list of dicts for event tracking
            recs_out = []
            for rec_dict in result.recommendations:
                recs_out.append(
                    {
                        "equipment": rec_dict.get("equipment_id", rec_dict.get("equipment_name", "")),
                        "control_point": rec_dict.get("point_name", ""),
                        "target_value": rec_dict.get("recommended_value"),
                        "reason": rec_dict.get("reason", ""),
                        "confidence": result.confidence if hasattr(result, "confidence") else 0.75,
                        "energy_savings_percent": rec_dict.get("savings_kwh", 0),
                        "source": "sentinel_analyze_building",
                        "quality_gate_status": getattr(result, "quality_gate_status", None),
                        "quality_gate_enforcement": getattr(result, "quality_gate_enforcement", None),
                    }
                )

            logger.info(
                f"SENTINEL analyze_building({self.site_id}): {len(recs_out)} recommendations "
                f"(LLM call #{self._llm_call_count}, fingerprint={fingerprint}, "
                f"quality_gate={getattr(result, 'quality_gate_status', 'n/a')})"
            )

            # Update cache
            self._last_state_fingerprint = fingerprint
            self._cached_sentinel_recs = recs_out
            return recs_out

        except Exception as e:
            logger.warning(f"SENTINEL analyze_building failed: {e}, falling back to hardcoded")
            return self._hardcoded_optimization_batch(
                controllable_equipment, context, occupancy_percent, daylight_factor, current_hour
            )

    def _hardcoded_optimization_batch(
        self,
        equipment_list: list[dict],
        context: str,
        occupancy_percent: int,
        daylight_factor: int,
        current_hour: int,
    ) -> list[dict]:
        """Run original hardcoded threshold-based optimization for all equipment.

        Calls the existing _generate_*_recommendation() methods that are preserved
        as fallback. Returns list of recommendation dicts.
        """
        recommendations = []
        for eq in equipment_list:
            eq_code = eq.get("code", eq.get("id"))
            eq_type = eq.get("type", "unknown").upper()

            hvac_rec = None
            if eq_type == "FCU":
                hvac_rec = self._generate_fcu_recommendation(eq_code, context, occupancy_percent, current_hour)
            elif eq_type == "AHU":
                hvac_rec = self._generate_ahu_recommendation(eq_code, context, occupancy_percent, current_hour)
            elif eq_type == "CHILLER":
                hvac_rec = self._generate_chiller_recommendation(eq_code, context, occupancy_percent, current_hour)
            elif eq_type == "VAV":
                hvac_rec = self._generate_vav_recommendation(eq_code, context, occupancy_percent, current_hour)
            elif eq_type == "PUMP":
                hvac_rec = self._generate_pump_recommendation(eq_code, context, occupancy_percent, current_hour)
            elif eq_type in ["CT", "SPLIT", "ZONE", "CONTROLLER"]:
                hvac_rec = self._generate_hvac_recommendation(
                    eq_code, eq_type, context, occupancy_percent, current_hour
                )

            if hvac_rec:
                recommendations.append(hvac_rec)

        return recommendations

    def _log_optimization_comparison(self, sentinel_recs: list[dict], hardcoded_recs: list[dict], hour: int):
        """Log comparison between SENTINEL and hardcoded recommendations for hybrid mode."""
        logger.info(f"[HYBRID] Hour {hour}: SENTINEL={len(sentinel_recs)} recs, hardcoded={len(hardcoded_recs)} recs")
        # Log equipment overlap
        sentinel_equip = {r.get("equipment", "") for r in sentinel_recs}
        hardcoded_equip = {r.get("equipment", "") for r in hardcoded_recs}
        overlap = sentinel_equip & hardcoded_equip
        sentinel_only = sentinel_equip - hardcoded_equip
        hardcoded_only = hardcoded_equip - sentinel_equip
        if overlap:
            logger.info(f"[HYBRID]   Both recommend: {overlap}")
        if sentinel_only:
            logger.info(f"[HYBRID]   SENTINEL only: {sentinel_only}")
        if hardcoded_only:
            logger.info(f"[HYBRID]   Hardcoded only: {hardcoded_only}")

    # ========== ORIGINAL HARDCODED RECOMMENDATION GENERATORS (fallback) ==========

    def _generate_fcu_recommendation(
        self, eq_code: str, context: str, occupancy_percent: int, hour: int
    ) -> dict[str, Any] | None:
        """Generate FCU recommendation — cooling_setpoint adjustments."""
        low_thresh, high_thresh = self._get_demo_thresholds()

        if occupancy_percent < low_thresh:
            return {
                "equipment": eq_code,
                "control_point": "cooling_setpoint",
                "target_value": 24.0,
                "reason": f"Low occupancy ({occupancy_percent}%) - reduce active cooling",
                "description": "Increase FCU setpoint to 24°C for energy efficiency",
                "savings": 8,
            }
        elif occupancy_percent >= high_thresh and 10 <= hour <= 12:
            return {
                "equipment": eq_code,
                "control_point": "cooling_setpoint",
                "target_value": 20.5,
                "reason": f"High occupancy ({occupancy_percent}%) + peak demand - anticipatory pre-cooling",
                "description": "Reduce FCU setpoint to 20.5°C for peak demand management",
                "savings": 5,
            }
        elif context == "afternoon":
            return {
                "equipment": eq_code,
                "control_point": "cooling_setpoint",
                "target_value": 21.5,
                "reason": f"Afternoon FCU optimization at {occupancy_percent}% occupancy",
                "description": "Adjust FCU setpoint to 21.5°C for afternoon efficiency",
                "savings": 3,
            }
        return None

    def _generate_ahu_recommendation(
        self, eq_code: str, context: str, occupancy_percent: int, hour: int
    ) -> dict[str, Any] | None:
        """Generate AHU recommendation — supply_temp_setpoint + economizer control."""
        low_thresh, high_thresh = self._get_demo_thresholds()

        if occupancy_percent < low_thresh:
            # Low occupancy: raise supply air temp to save reheat energy
            return {
                "equipment": eq_code,
                "control_point": "supply_temp_setpoint",
                "target_value": 14.0,
                "reason": f"Low occupancy ({occupancy_percent}%) - raise supply air temp to reduce reheat",
                "description": "Increase AHU supply air to 14°C (from 12°C) during low occupancy",
                "savings": 10,
            }
        elif 9 <= hour <= 16 and occupancy_percent >= high_thresh:
            # Business hours, high occupancy: full cooling capacity
            return {
                "equipment": eq_code,
                "control_point": "supply_temp_setpoint",
                "target_value": 12.0,
                "reason": f"Peak occupancy ({occupancy_percent}%) - maintain full AHU cooling",
                "description": "Set AHU supply air to 12°C for maximum cooling capacity",
                "savings": 2,
            }
        elif 6 <= hour <= 9:
            # Morning mild conditions: enable economizer (free cooling)
            return {
                "equipment": eq_code,
                "control_point": "economizer_mode",
                "target_value": 1,  # 1=enabled
                "reason": "Morning hours - enable AHU economizer for free cooling",
                "description": "Enable economizer mode during mild morning temperatures",
                "savings": 12,
            }
        elif context == "afternoon" and hour >= 14:
            # Hot afternoon: disable economizer, lower supply air
            return {
                "equipment": eq_code,
                "control_point": "supply_temp_setpoint",
                "target_value": 11.5,
                "reason": "Hot afternoon - lower AHU supply air for increased cooling",
                "description": "Reduce AHU supply air to 11.5°C during peak afternoon heat",
                "savings": 3,
            }
        return None

    def _generate_chiller_recommendation(
        self, eq_code: str, context: str, occupancy_percent: int, hour: int
    ) -> dict[str, Any] | None:
        """Generate chiller recommendation — chw_setpoint + capacity_percent."""
        low_thresh, high_thresh = self._get_demo_thresholds()

        if occupancy_percent < low_thresh:
            # Low load: raise CHW setpoint for compressor efficiency
            return {
                "equipment": eq_code,
                "control_point": "chw_setpoint",
                "target_value": 8.0,
                "reason": f"Low occupancy ({occupancy_percent}%) - raise CHW setpoint for efficiency",
                "description": "Raise chiller CHW setpoint to 8°C (from 6°C) to reduce compressor load",
                "savings": 12,
            }
        elif occupancy_percent >= high_thresh and 10 <= hour <= 15:
            # Peak load: ensure full capacity
            return {
                "equipment": eq_code,
                "control_point": "capacity_percent",
                "target_value": 100,
                "reason": f"Peak occupancy ({occupancy_percent}%) during business hours - full chiller capacity",
                "description": "Set chiller to 100% capacity for peak cooling demand",
                "savings": 0,
            }
        elif context == "afternoon":
            # Afternoon: moderate CHW adjustment
            return {
                "equipment": eq_code,
                "control_point": "chw_setpoint",
                "target_value": 7.0,
                "reason": f"Afternoon optimization - moderate CHW setpoint at {occupancy_percent}% occupancy",
                "description": "Set chiller CHW to 7°C for balance of efficiency and capacity",
                "savings": 6,
            }
        elif hour >= 17:
            # After hours: raise CHW temp aggressively
            return {
                "equipment": eq_code,
                "control_point": "chw_setpoint",
                "target_value": 9.0,
                "reason": "After-hours operation - raise CHW setpoint to minimize energy use",
                "description": "Raise chiller CHW to 9°C during low-demand after-hours period",
                "savings": 15,
            }
        return None

    def _generate_vav_recommendation(
        self, eq_code: str, context: str, occupancy_percent: int, hour: int
    ) -> dict[str, Any] | None:
        """Generate VAV recommendation — damper_position + airflow_setpoint."""
        low_thresh, high_thresh = self._get_demo_thresholds()

        if occupancy_percent < low_thresh:
            # Low occupancy: close damper toward minimum
            return {
                "equipment": eq_code,
                "control_point": "damper_position",
                "target_value": 30,  # 30% minimum position
                "reason": f"Low occupancy ({occupancy_percent}%) - reduce VAV airflow to minimum",
                "description": "Close VAV damper to 30% minimum position during low occupancy",
                "savings": 10,
            }
        elif occupancy_percent >= high_thresh:
            # High occupancy: open damper fully
            return {
                "equipment": eq_code,
                "control_point": "damper_position",
                "target_value": 90,  # 90% open
                "reason": f"High occupancy ({occupancy_percent}%) - increase VAV airflow for comfort",
                "description": "Open VAV damper to 90% for adequate airflow during high occupancy",
                "savings": 0,
            }
        elif context == "afternoon":
            # Afternoon moderate: adjust airflow setpoint
            return {
                "equipment": eq_code,
                "control_point": "airflow_setpoint",
                "target_value": 60,  # 60% of design airflow
                "reason": f"Afternoon VAV optimization at {occupancy_percent}% occupancy",
                "description": "Set VAV airflow to 60% of design for afternoon efficiency",
                "savings": 5,
            }
        return None

    def _generate_pump_recommendation(
        self, eq_code: str, context: str, occupancy_percent: int, hour: int
    ) -> dict[str, Any] | None:
        """Generate pump recommendation — speed_percent (affinity laws: 50% speed ≈ 12.5% power)."""
        low_thresh, _ = self._get_demo_thresholds()

        if occupancy_percent < low_thresh:
            # Low load: reduce pump speed aggressively
            return {
                "equipment": eq_code,
                "control_point": "speed_percent",
                "target_value": 40,
                "reason": f"Low occupancy ({occupancy_percent}%) - reduce pump speed (affinity law savings)",
                "description": "Reduce pump to 40% speed — affinity laws yield ~94% power reduction vs full speed",
                "savings": 18,
            }
        elif hour < 7 or hour >= 20:
            # Night/unoccupied: minimum pump speed
            return {
                "equipment": eq_code,
                "control_point": "speed_percent",
                "target_value": 30,
                "reason": "Night/unoccupied hours - pump at minimum circulation speed",
                "description": "Reduce pump to 30% minimum speed during unoccupied hours",
                "savings": 20,
            }
        elif context == "afternoon":
            # Afternoon moderate reduction
            return {
                "equipment": eq_code,
                "control_point": "speed_percent",
                "target_value": 70,
                "reason": f"Afternoon pump optimization at {occupancy_percent}% occupancy",
                "description": "Reduce pump to 70% speed for afternoon efficiency",
                "savings": 8,
            }
        return None

    def _generate_hvac_recommendation(
        self, eq_code: str, eq_type: str, context: str, occupancy_percent: int, hour: int
    ) -> dict[str, Any] | None:
        """Generate generic HVAC recommendation (fallback for CT, SPLIT, etc.)."""
        low_thresh, high_thresh = self._get_demo_thresholds()

        if occupancy_percent < low_thresh:
            return {
                "equipment": eq_code,
                "control_point": "cooling_setpoint",
                "target_value": 24.0,
                "reason": f"Low occupancy ({occupancy_percent}%) - reduce active cooling",
                "description": f"Increase {eq_type} setpoint to 24°C for energy efficiency",
                "savings": 8,
            }
        elif occupancy_percent >= high_thresh and 10 <= hour <= 12:
            return {
                "equipment": eq_code,
                "control_point": "cooling_setpoint",
                "target_value": 20.5,
                "reason": f"High occupancy ({occupancy_percent}%) + peak demand - anticipatory pre-cooling",
                "description": f"Reduce {eq_type} setpoint to 20.5°C for peak demand management",
                "savings": 5,
            }
        elif context == "afternoon":
            return {
                "equipment": eq_code,
                "control_point": "cooling_setpoint",
                "target_value": 21.5,
                "reason": f"Afternoon optimization at {occupancy_percent}% occupancy",
                "description": f"Adjust {eq_type} setpoint to 21.5°C for afternoon efficiency",
                "savings": 3,
            }
        return None

    def _generate_dali_recommendation(
        self,
        eq_code: str,
        eq_type: str,
        context: str,
        occupancy_percent: int,
        daylight_factor: int,
        zones_active: int,
        hour: int,
    ) -> dict[str, Any] | None:
        """DEPRECATED: Tridonic DALI-2 gateway handles daylight harvesting, occupancy
        dimming, and emergency zone protection natively. AI should not duplicate these.
        Returns None — kept for signature compatibility only."""
        return None

    async def _setpoint_change(self, point: str, value: float, reason: str):
        """Simulate a setpoint change."""
        self._emit_event(
            LifecycleEvent(
                timestamp=datetime.now(),
                simulated_hour=self.simulated_time.hour,
                event_type=EventType.SETPOINT_CHANGE,
                description=f"Setpoint change: {point} → {value}",
                details={"point": point, "value": value, "reason": reason},
            )
        )

    # === RUNTIME & DEGRADATION METHODS (105-02) ===

    def _is_equipment_running(self, equip_type: str, schedule_state: ScheduleState) -> bool:
        """Determine if equipment is running based on type and schedule."""
        if equip_type in ("chiller", "cooling_tower"):
            return schedule_state.chiller_staging.value != "off"
        elif equip_type == "ahu":
            return schedule_state.ahu_fan_pct > 0
        elif equip_type in ("vav", "fcu"):
            return schedule_state.hvac_mode.value not in ("off", "night_setback")
        elif equip_type == "pump":
            return schedule_state.chiller_staging.value != "off"
        elif equip_type in ("ups", "generator", "bess", "meter"):
            return True  # Always on
        elif equip_type == "inverter":
            return self.current_solar_efficiency > 0  # Daytime only
        elif equip_type in ("dali_zone", "dali_controller", "controller", "luminaire"):
            return schedule_state.lighting_mode.value != "off"
        elif equip_type == "zone_controller":
            return schedule_state.target_occupancy_pct > 0  # Active during occupied hours
        elif equip_type == "unknown":
            return True  # Generic equipment — assume always on
        elif equip_type == "fire":
            return True  # Fire safety — always on
        elif equip_type == "sensor":
            return True  # Sensors always on
        return False

    def _apply_cascade_effects(self, equipment_states: dict[str, dict]) -> dict[str, dict]:
        """Apply cascade effects from failed equipment to downstream systems.

        When critical plant equipment (chillers, pumps) degrades, downstream
        zone equipment (VAVs, FCUs) loses cooling capacity, and zone temps
        drift warmer.
        """
        # Collect health of critical plant equipment
        chillers = []
        pumps = []

        for _code, state in equipment_states.items():
            if state.get("type") == "chiller":
                chillers.append(state.get("health_score", 100))
            elif state.get("type") == "pump":
                pumps.append(state.get("health_score", 100))

        chiller_health_avg = sum(chillers) / len(chillers) if chillers else 100.0
        pump_health_avg = sum(pumps) / len(pumps) if pumps else 100.0

        # Cascade: chiller/pump failure -> reduced cooling for all zones
        cooling_capacity = min(chiller_health_avg, pump_health_avg) / 100.0

        if cooling_capacity < 0.9:  # Some degradation
            for _code, state in equipment_states.items():
                if state.get("type") in ("vav", "fcu"):
                    readings = state.get("sensor_readings", {})
                    # Reduce damper/valve effectiveness
                    if "damper_position" in readings:
                        effective_damper = readings["damper_position"] * cooling_capacity
                        readings["damper_position"] = round(effective_damper, 1)
                    if "valve_position" in readings:
                        effective_valve = readings["valve_position"] * cooling_capacity
                        readings["valve_position"] = round(effective_valve, 1)
                    # Zone temp drifts warmer if cooling reduced significantly
                    if "zone_temp" in readings and cooling_capacity < 0.7:
                        temp_drift = (1 - cooling_capacity) * 3.0  # Up to 3C drift
                        readings["zone_temp"] = round(readings["zone_temp"] + temp_drift, 1)
                    if "room_temp" in readings and cooling_capacity < 0.7:
                        temp_drift = (1 - cooling_capacity) * 3.0
                        readings["room_temp"] = round(readings["room_temp"] + temp_drift, 1)

        return equipment_states

    # === PERSISTENCE METHODS (104-02) ===

    async def _collect_equipment_states(self, hour: int, schedule_state: ScheduleState) -> dict[str, dict]:
        """Collect current state of all site equipment for persistence.

        Loads equipment from JSON files first (site-002 uses disk as source of truth).
        Falls back to Supabase if JSON directory is empty or missing.
        """
        equipment_states: dict[str, dict] = {}

        try:
            # JSON-first: load from on-disk equipment files
            equipment_list = load_site_equipment(self.site_id)

            if not equipment_list:
                # Fallback: resolve building UUID and load from Supabase
                site_uuid = None
                try:
                    from app.database.supabase_client import get_supabase_client

                    client = get_supabase_client()
                    bld_resp = client.table("sites").select("id").eq("code", self.site_id).execute()
                    if bld_resp.data:
                        site_uuid = bld_resp.data[0]["id"]
                except Exception:
                    pass

                equipment_list = self.equipment_repo.get_all(site_id=site_uuid)

            for equip in equipment_list:
                code = equip.get("code", "")
                if not code.startswith(self.site_prefix):
                    continue

                equip_type = equip.get("type", "unknown").lower()
                # Normalize DB type names to internal names
                equip_type = self.TYPE_ALIASES.get(equip_type, equip_type)

                # Use in-memory health if seeded, otherwise seed from DB
                if code in self._equipment_health:
                    health = self._equipment_health[code]
                else:
                    raw_health = equip.get("health_score")
                    health = float(raw_health if raw_health is not None else 100) or 100
                    if health < 100:
                        logger.warning(f"[HEALTH SEED] {code} seeded at {health} (raw={raw_health}, type={equip_type})")
                    self._equipment_health[code] = health

                # Baseline wear: slow degradation during normal operation (105-02)
                is_running = self._is_equipment_running(equip_type, schedule_state)
                if is_running:
                    wear_rate = self.WEAR_RATES.get(equip_type, 0.0)
                    health -= wear_rate  # Very small per hour, adds up over months
                    health = max(30.0, health)  # Floor: equipment doesn't die from wear alone

                # Apply fault degradation if this equipment has an active fault
                if code in self.active_faults:
                    fault = self.active_faults[code]
                    hours_faulted = fault.get("hours_faulted", 0) + 1
                    fault["hours_faulted"] = hours_faulted
                    health = max(10, health - (hours_faulted * 2))  # 2% per hour while faulted

                # Persist in-memory health (accumulates tiny wear without DB precision loss)
                self._equipment_health[code] = health

                # Generate sensor readings based on equipment type and schedule
                sensor_readings = self._generate_sensor_readings(code, equip_type, health, hour, schedule_state)

                # Track runtime hours (105-02)
                if is_running:
                    self.runtime_hours[code] = self.runtime_hours.get(code, 0) + 1

                equipment_states[code] = {
                    "health_score": health,
                    "status": "online" if health >= 70 else ("degraded" if health >= 40 else "offline"),
                    "sensor_readings": sensor_readings,
                    "type": equip_type,
                    "is_running": is_running,
                    "runtime_hours": self.runtime_hours.get(code, 0),
                }
        except Exception as e:
            logger.warning(f"Failed to collect equipment states: {e}")

        # Apply cascade effects from failed plant to downstream zones (105-02)
        equipment_states = self._apply_cascade_effects(equipment_states)

        # Store snapshot for API access
        self._simulation_equipment = equipment_states

        return equipment_states

    # =========================================================================
    # Health Monitoring & Alert Pipeline (106-01)
    # =========================================================================

    async def _monitor_equipment_health(self, equipment_states: dict[str, dict], simulated_hour: int):
        """Monitor equipment health against thresholds. Trigger alerts on status transitions.

        Uses HealthThresholdService for configurable thresholds (not hardcoded).
        Only alerts on STATUS TRANSITIONS (healthy->warning, warning->critical, etc.),
        not every hour, with a 1-hour cooldown per equipment to prevent spam.

        Args:
            equipment_states: Dict of equipment_code -> state dict (from _collect_equipment_states)
            simulated_hour: Current simulated hour (0-23, cumulative across days)
        """
        from app.services.health_threshold_service import get_health_threshold_service

        threshold_svc = get_health_threshold_service()
        thresholds = threshold_svc.get_thresholds()
        warning_threshold = thresholds.get("warning", 70)
        critical_threshold = thresholds.get("critical", 50)

        # Use absolute hour for cooldown tracking across multi-day simulations
        absolute_hour = self.days_simulated * 24 + simulated_hour

        for code, state in equipment_states.items():
            health = state.get("health_score", 100)
            equip_type = state.get("type", "unknown")

            # Determine current status using threshold boundaries
            if health >= warning_threshold:
                current_status = "healthy"
            elif health >= critical_threshold:
                current_status = "warning"
            else:
                current_status = "critical"

            previous_status = self.health_status_cache.get(code, "healthy")
            self.health_status_cache[code] = current_status

            # Only act on TRANSITIONS (not every hour)
            if current_status == previous_status:
                continue

            # Cooldown: don't re-alert within 1 simulated hour
            last_alert = self.last_alert_time.get(code, -999)
            if absolute_hour - last_alert < 1:
                continue

            if current_status == "warning" and previous_status == "healthy":
                # Health degraded to warning
                await self._create_health_alert(code, equip_type, health, "warning", simulated_hour)
                self.last_alert_time[code] = absolute_hour
                # SENTINEL AI response — generate recommendation and potentially auto-execute (106-02)
                await self._sentinel_response(code, equip_type, health, current_status, simulated_hour)

            elif current_status == "critical":
                # Health degraded to critical -- alert + work order
                await self._create_health_alert(code, equip_type, health, "critical", simulated_hour)
                await self._auto_create_work_order(code, equip_type, health, simulated_hour)
                self.last_alert_time[code] = absolute_hour
                # SENTINEL AI response — escalate with technician dispatch (106-02)
                await self._sentinel_response(code, equip_type, health, current_status, simulated_hour)

    async def _create_health_alert(self, code: str, equip_type: str, health: float, severity: str, simulated_hour: int):
        """Create a health-driven alert with deduplication.

        Checks for existing active alerts before creating a new one to avoid
        duplicate alerts for the same equipment. Emits a lifecycle event.

        Args:
            code: Equipment code (e.g., S002-CHILLER-B1-001)
            equip_type: Equipment type (e.g., chiller, ahu)
            health: Current health score (0-100)
            severity: Alert severity (warning, critical)
            simulated_hour: Current simulated hour
        """
        # Check for existing active alert (deduplication)
        try:
            from app.database.repositories.alert_repository import AlertRepository

            alert_repo = AlertRepository()
            existing = alert_repo.get_active_alerts_for_equipment(code)
            if existing:
                # Already have an active alert for this equipment -- skip
                return
        except Exception:
            pass  # No dedup if repo unavailable

        description = (
            f"{code} ({equip_type}) health degraded to {health:.1f}% -- "
            f"status: {severity}. "
            f"{'Immediate attention required.' if severity == 'critical' else 'Monitor closely.'}"
        )

        # Use EquipmentAlertService if available
        try:
            from app.services.equipment_alert_service import get_equipment_alert_service

            alert_svc = get_equipment_alert_service()
            alert_svc.create_alert_for_equipment(
                equipment_id=code,
                alert_type="health_degradation",
                severity=severity,
                message=description,
                site_id=self.site_id,
            )
        except Exception as e:
            logger.warning(f"Could not create alert via service: {e}")

        description = f"Health alert ({severity}): {code} at {health:.1f}%"
        self._emit_event(
            LifecycleEvent(
                timestamp=datetime.now(),
                simulated_hour=simulated_hour,
                event_type=EventType.ALERT_CREATED if severity == "critical" else EventType.HEALTH_DEGRADED,
                equipment_id=code,
                description=description,
                details={"equipment_code": code, "health": health, "severity": severity},
            )
        )
        # Push to dashboard Recent Alerts
        self._push_alert_to_dashboard(
            equipment_code=code,
            severity=severity,
            alert_type="health_degradation",
            message=description,
            details={"health": health},
        )

    async def _monitor_zone_temperatures(self, simulated_hour: int):
        """Monitor zone temperatures against configured safety limits.

        Checks self.zone_temperatures against temp_min/temp_max from the
        settings page (controlLimits.temperature_setpoint). These are the
        configured safety thresholds — any zone outside them needs attention.

        Unlike _scan_safety_boundaries which checks per-equipment sensor
        readings, this monitors zones directly — catching building-wide
        cooling/heating failures even when individual equipment reports healthy.

        Uses transition-based alerting with 2-hour cooldown to prevent spam.

        Thresholds (from settings):
            temp < temp_min or temp > temp_max → critical
            temp within 1°C of limit           → warning
            otherwise                          → normal

        Args:
            simulated_hour: Current simulated hour (0-23)
        """
        # Load zone setpoints from thermal engine cache
        try:
            from app.services.thermal_simulation_engine import get_thermal_engine

            thermal_engine = get_thermal_engine(self.site_id, consider_equipment_health=False)
            zone_cache = thermal_engine._zone_cache
        except Exception:
            return  # Can't check without zone config

        if not zone_cache:
            return

        # Load configured safety limits from settings
        try:
            import json
            from pathlib import Path

            settings_path = Path("/opt/bms-intelligence/backend/app/data/settings.json")
            with open(settings_path) as f:
                site_settings = json.load(f)
            temp_limits = site_settings.get("controlLimits", {}).get("temperature_setpoint", {})
            temp_min = float(temp_limits.get("min", 18))
            temp_max = float(temp_limits.get("max", 26))
        except Exception:
            temp_min = 18.0
            temp_max = 26.0

        absolute_hour = self.days_simulated * 24 + simulated_hour

        for zone_id, temp in self.zone_temperatures.items():
            config = zone_cache.get(zone_id)
            if not config:
                continue

            setpoint = config.get("setpoint", 22.0)

            # Classify against configured safety limits (not deviation from setpoint)
            if temp < temp_min or temp > temp_max:
                current_status = "critical"
                deviation = temp - temp_min if temp < temp_min else temp - temp_max
            elif temp < temp_min + 1.0 or temp > temp_max - 1.0:
                current_status = "warning"
                deviation = temp - setpoint
            else:
                current_status = "normal"
                deviation = temp - setpoint

            previous_status = self._zone_temp_status_cache.get(zone_id, "normal")
            self._zone_temp_status_cache[zone_id] = current_status

            # Only alert on transitions (normal->warning, warning->critical, etc.)
            if current_status == "normal" or current_status == previous_status:
                continue

            # Cooldown: 2 hours between alerts per zone
            last_alert = self._zone_temp_last_alert.get(zone_id, -999)
            if absolute_hour - last_alert < 2:
                continue

            self._zone_temp_last_alert[zone_id] = absolute_hour

            zone_name = config.get("zone_name", zone_id)
            fcu_code = config.get("fcu_id", "")
            direction = "cold" if temp < setpoint else "hot"

            if current_status == "critical":
                breach = f"below minimum {temp_min}°C" if temp < temp_min else f"above maximum {temp_max}°C"
                message = (
                    f"Zone temperature OUTSIDE SAFETY LIMITS: {zone_name} at {temp:.1f}°C "
                    f"({breach}, setpoint {setpoint:.1f}°C). "
                    f"IMMEDIATE: Check chiller plant and central HVAC controls."
                )
            else:
                approaching = (
                    f"approaching minimum {temp_min}°C"
                    if temp < temp_min + 1.0
                    else f"approaching maximum {temp_max}°C"
                )
                message = (
                    f"Zone temperature warning: {zone_name} at {temp:.1f}°C "
                    f"({approaching}, setpoint {setpoint:.1f}°C). "
                    f"Monitor zone FCU/VAV operation."
                )

            # Write to Supabase alerts table via EquipmentAlertService
            try:
                from app.services.equipment_alert_service import get_equipment_alert_service

                alert_svc = get_equipment_alert_service()
                # Use the FCU code if available, otherwise use zone_id as equipment reference
                equipment_ref = fcu_code if fcu_code else f"ZONE-{zone_id}"
                alert_svc.create_alert_for_equipment(
                    equipment_id=equipment_ref,
                    alert_type="temperature_deviation",
                    severity=current_status,
                    message=message,
                    site_id=self.site_id,
                    notify_telegram=(current_status == "critical"),
                )
            except Exception as e:
                logger.debug(f"Could not create zone temp alert: {e}")

            # Emit lifecycle event
            self._emit_event(
                LifecycleEvent(
                    timestamp=datetime.now(),
                    simulated_hour=simulated_hour,
                    event_type=EventType.SAFETY_VIOLATION if current_status == "critical" else EventType.ALERT_CREATED,
                    equipment_id=fcu_code or f"ZONE-{zone_id}",
                    description=message,
                    details={
                        "zone_id": zone_id,
                        "zone_name": zone_name,
                        "current_temp": temp,
                        "setpoint": setpoint,
                        "temp_min": temp_min,
                        "temp_max": temp_max,
                        "deviation": deviation,
                        "direction": direction,
                        "severity": current_status,
                    },
                )
            )

            # Push to dashboard
            self._push_alert_to_dashboard(
                equipment_code=fcu_code or f"ZONE-{zone_id}",
                severity=current_status,
                alert_type="temperature_deviation",
                message=message,
                details={
                    "zone_name": zone_name,
                    "temp": temp,
                    "setpoint": setpoint,
                    "temp_min": temp_min,
                    "temp_max": temp_max,
                    "deviation": deviation,
                },
            )

            logger.info(
                f"[ZONE TEMP] {current_status.upper()}: {zone_name} at {temp:.1f}°C "
                f"(limits {temp_min}-{temp_max}°C, setpoint {setpoint:.1f}°C)"
            )

    async def _auto_create_work_order(self, code: str, equip_type: str, health: float, simulated_hour: int):
        """Auto-create work order with technician specialty matching.

        Maps equipment type to technician specialty via EQUIPMENT_SPECIALTY_MAP,
        finds an available technician, and creates a work order with proper assignment.

        Args:
            code: Equipment code (e.g., S002-CHILLER-B1-001)
            equip_type: Equipment type (e.g., chiller, ahu)
            health: Current health score (0-100)
            simulated_hour: Current simulated hour
        """
        specialty = self.EQUIPMENT_SPECIALTY_MAP.get(equip_type, "Facilities")

        # Find available technician by specialty
        technician_name = None
        try:
            from app.database.repositories.technician_repository import TechnicianRepository

            tech_repo = TechnicianRepository()
            technician = await tech_repo.get_technician_for_equipment_code(code)
            if technician:
                technician_name = technician.get("name", "Unassigned")
        except Exception:
            technician_name = "Unassigned"

        wo_id = f"WO-SIM-{code}-{self.days_simulated * 24 + simulated_hour}"

        # Look up the latest active prediction for this equipment to link the WO
        prediction_id = None
        try:
            from app.database.repositories.prediction_repository import get_prediction_repository

            pred_repo = get_prediction_repository()
            preds = await pred_repo.get_by_equipment_code(code, status="active", limit=1)
            if preds:
                prediction_id = preds[0].get("id")
        except Exception:
            pass  # Prediction linkage is best-effort — WO is created regardless

        try:
            self.work_order_repo.create_work_order(
                {
                    "id": wo_id,
                    "site_id": self.site_id,
                    "equipment_code": code,
                    "title": f"Health critical: {code} at {health:.1f}%",
                    "description": (
                        f"Equipment {code} ({equip_type}) health has degraded to {health:.1f}%. "
                        f"Specialty: {specialty}. Assigned to: {technician_name or 'Unassigned'}."
                    ),
                    "priority": "high" if health < 40 else "medium",
                    "category": "corrective_maintenance",
                    "status": "assigned" if technician_name else "scheduled",
                    "assigned_to": technician_name,
                    "created_by": "SENTINEL_HEALTH_MONITOR",
                    "prediction_id": prediction_id,
                }
            )
        except Exception as e:
            logger.warning(f"Could not create work order: {e}")

        self._emit_event(
            LifecycleEvent(
                timestamp=datetime.now(),
                simulated_hour=simulated_hour,
                event_type=EventType.WORK_ORDER_CREATED,
                equipment_id=code,
                description=f"Work order {wo_id}: {code} assigned to {technician_name or 'unassigned'} ({specialty})",
                details={
                    "wo_id": wo_id,
                    "equipment_code": code,
                    "technician": technician_name,
                    "specialty": specialty,
                },
            )
        )

        # Notify technician via Sentry bot (Telegram + email) — same pipeline as production
        if self.current_scenario and getattr(self.current_scenario, "sentry_notifications", False):
            equipment_dict = {"type": equip_type, "code": code, "name": code}
            fault_info = {
                "equipment_id": code,
                "equipment_code": code,
                "equipment_name": code,
                "fault_type": f"Health critical ({health:.1f}%)",
                "severity": 90 if health < 40 else 60,
            }
            await self._notify_sentry(equipment_dict, fault_info, wo_id)

    def _equipment_to_zone(self, equipment_code: str) -> str:
        """Map equipment code to zone ID for temperature lookup.

        Supports both numbered and letter-based equipment codes:
            S002-FCU-201   -> Zone-201
            S002-VAV-003   -> Zone-003
            S002-VAV-L1-A  -> Zone-L1-A  (legacy)
            S002-FCU-L2-B  -> Zone-L2-B  (legacy)
        """
        parts = equipment_code.split("-")
        if len(parts) >= 3:
            location = "-".join(parts[2:])  # 201, 003, L1-A, L2-B
            return f"Zone-{location}"
        return ""

    def _ramp_limit(self, code: str, reading_name: str, target: float, hour: int) -> float:
        """Apply ramp rate limiting to an actuator output.

        Prevents unrealistic step changes by constraining how fast a value
        can change per simulated hour — matching real BMS actuator dynamics.

        Args:
            code: Equipment code (e.g. S002-FCU-201)
            reading_name: Sensor reading name (e.g. valve_position)
            target: Desired raw value before limiting
            hour: Current simulation hour (0-23)

        Returns:
            Ramp-limited value stored in _actuator_state for next call
        """
        max_rate = RAMP_RATES.get(reading_name)
        if max_rate is None:
            return target

        equip_state = self._actuator_state.setdefault(code, {})
        prev = equip_state.get(reading_name)

        if prev is None:
            # First tick for this equipment — 50% approach (soft startup)
            result = target * 0.5
        else:
            delta = target - prev
            if abs(delta) <= max_rate:
                result = target
            elif delta > 0:
                result = prev + max_rate
            else:
                result = prev - max_rate

        equip_state[reading_name] = result
        return round(result, 1)

    def _generate_sensor_readings(
        self,
        code: str,
        equip_type: str,
        health: float,
        hour: int,
        schedule_state: ScheduleState,
    ) -> dict[str, float]:
        """Generate realistic sensor readings for an equipment item.

        equip_type is already normalized via TYPE_ALIASES in _collect_equipment_states.
        """
        readings: dict[str, float] = {}
        ambient = self.current_ambient_temp
        solar_eff = self.current_solar_efficiency

        if equip_type == "chiller":
            # Use CHW model for supply/return temps (105-01)
            readings["supply_temp"] = round(self.chw_model.supply_temp, 1)
            readings["return_temp"] = round(self.chw_model.return_temp, 1)
            if schedule_state.chiller_staging.value != "off":
                load_target = {"stage_1": 30, "stage_2": 60, "full_load": 90}.get(
                    schedule_state.chiller_staging.value, 0
                )
                readings["load_pct"] = self._ramp_limit(code, "load_pct", load_target, hour)
                readings["compressor_status"] = 1
                # COP degrades with health (105-01)
                base_cop = 5.5  # Design COP
                readings["cop"] = round(base_cop * (health / 100.0), 2)
            else:
                readings["load_pct"] = self._ramp_limit(code, "load_pct", 0.0, hour)
                readings["compressor_status"] = 0
                readings["cop"] = 0

        elif equip_type == "cooling_tower":
            # CT responds to ambient temp, humidity, and chiller staging
            chillers_on = schedule_state.chiller_staging.value != "off"
            readings["status"] = 1.0 if chillers_on else 0.0
            if chillers_on:
                fan_target = {"stage_1": 50, "stage_2": 75, "full_load": 95}.get(
                    schedule_state.chiller_staging.value, 0
                )
                readings["fan_speed_pct"] = self._ramp_limit(code, "fan_speed_pct", fan_target, hour)
                # Water inlet = CHW return (warm water from building)
                readings["water_inlet_temp_c"] = round(self.chw_model.return_temp + 2.0, 1)
                # Outlet approaches wet-bulb (ambient - 3C), limited by fan speed
                wet_bulb_approx = ambient - 3.0
                fan_factor = readings["fan_speed_pct"] / 100.0
                inlet = readings["water_inlet_temp_c"]
                outlet = inlet - (inlet - wet_bulb_approx) * fan_factor * 0.7
                readings["water_outlet_temp_c"] = round(max(wet_bulb_approx, outlet), 1)
            else:
                readings["fan_speed_pct"] = self._ramp_limit(code, "fan_speed_pct", 0.0, hour)
                readings["water_inlet_temp_c"] = round(ambient, 1)
                readings["water_outlet_temp_c"] = round(ambient, 1)

        elif equip_type == "ahu":
            # Demand-responsive AHU: SAT reset + fan speed modulation
            fan_ceiling = schedule_state.ahu_fan_pct
            if fan_ceiling > 0:
                # SAT reset: scan zone temps, find worst-case error
                setpoint = self.site_schedule.COMFORT_SETPOINT + schedule_state.setpoint_offset
                worst_error = 0.0
                zone_count = max(len(self.zone_temperatures), 1)
                zones_above = 0
                for zt in self.zone_temperatures.values():
                    err = zt - setpoint
                    if err > worst_error:
                        worst_error = err
                    if err > 0.5:
                        zones_above += 1
                zone_demand_ratio = zones_above / zone_count

                # SAT: 12°C at high demand (3°C+ error), 16°C when satisfied
                prop_band = 3.0
                sat_raw = 16.0 - (min(worst_error, prop_band) / prop_band) * 4.0
                # Health degradation: +0.05°C per 1% health loss
                sat_raw += (100 - health) * 0.05
                sat_target = max(12.0, min(16.0, sat_raw))
                readings["supply_air_temp"] = self._ramp_limit(code, "supply_air_temp", sat_target, hour)

                # Fan speed: proportional to zone demand, ceiling from schedule
                base_fan = fan_ceiling * (0.4 + 0.6 * zone_demand_ratio)
                # Boost +10% if any zone >2°C above setpoint
                if worst_error > 2.0:
                    base_fan = min(100, base_fan + 10)
                fan_target = max(30.0, min(100.0, base_fan))
                readings["fan_speed_pct"] = self._ramp_limit(code, "fan_speed_pct", fan_target, hour)
                readings["fan_status"] = 1
            else:
                readings["supply_air_temp"] = self._ramp_limit(code, "supply_air_temp", ambient, hour)
                readings["fan_speed_pct"] = self._ramp_limit(code, "fan_speed_pct", 0.0, hour)
                readings["fan_status"] = 0

        elif equip_type == "vav":
            # Proportional VAV control with ramp limiting
            zone_id = self._equipment_to_zone(code)
            setpoint = self.site_schedule.COMFORT_SETPOINT + schedule_state.setpoint_offset
            actual_temp = self.zone_temperatures.get(zone_id, setpoint)
            sensor_noise = self._scenario_rng.uniform(-0.3, 0.3)
            readings["zone_temp"] = round(actual_temp + sensor_noise, 1)

            zone_occ_pct = self._get_zone_occupancy(zone_id)

            if schedule_state.hvac_mode.value not in ("off", "night_setback"):
                temp_error = actual_temp - setpoint
                deadband = 0.5
                prop_band = 2.5
                min_damper = 15.0  # ASHRAE 62.1 outdoor air minimum

                if abs(temp_error) <= deadband:
                    # Within deadband — hold current position
                    prev = self._actuator_state.get(code, {}).get("damper_position", min_damper)
                    damper_target = prev
                elif temp_error > deadband:
                    # Cooling demand: proportional 0-100% over prop_band
                    demand = min((temp_error - deadband) / prop_band, 1.0)
                    damper_target = min_damper + (100.0 - min_damper) * demand
                else:
                    # Below setpoint: minimum outdoor air only
                    damper_target = min_damper

                # Occupancy override: unoccupied zones cap at minimum
                if zone_occ_pct < 10.0:
                    damper_target = min(damper_target, min_damper)

                readings["damper_position"] = self._ramp_limit(code, "damper_position", damper_target, hour)
                readings["airflow_lps"] = round(readings["damper_position"] * 0.8, 1)
            else:
                readings["damper_position"] = self._ramp_limit(code, "damper_position", 0.0, hour)
                readings["airflow_lps"] = 0

        elif equip_type == "fcu":
            # Proportional FCU control with ramp limiting
            zone_id = self._equipment_to_zone(code)
            setpoint = self.site_schedule.COMFORT_SETPOINT + schedule_state.setpoint_offset
            actual_temp = self.zone_temperatures.get(zone_id, setpoint)
            sensor_noise = self._scenario_rng.uniform(-0.3, 0.3)
            readings["room_temp"] = round(actual_temp + sensor_noise, 1)

            zone_occ_pct = self._get_zone_occupancy(zone_id)

            if schedule_state.hvac_mode.value not in ("off", "night_setback"):
                temp_error = actual_temp - setpoint
                deadband = 0.5
                prop_band = 3.0
                min_valve_active = 10.0
                min_valve_below = 5.0

                if abs(temp_error) <= deadband:
                    # Within deadband — hold current position
                    prev = self._actuator_state.get(code, {}).get("valve_position", min_valve_active)
                    valve_target = prev
                elif temp_error > deadband:
                    # Cooling demand: proportional 0-100% over prop_band
                    demand = min((temp_error - deadband) / prop_band, 1.0)
                    valve_target = min_valve_active + (100.0 - min_valve_active) * demand
                else:
                    # Below setpoint: minimum circulation
                    valve_target = min_valve_below

                # Occupancy override: unoccupied zones cap valve
                if zone_occ_pct < 10.0:
                    valve_target = min(valve_target, min_valve_active)

                readings["valve_position"] = self._ramp_limit(code, "valve_position", valve_target, hour)

                # Fan speed follows valve demand
                vp = readings["valve_position"]
                if vp < 5:
                    fan_target = 0
                elif vp < 20 or vp < 50:
                    fan_target = 1  # low
                elif vp < 80:
                    fan_target = 2  # medium
                else:
                    fan_target = 3  # high
                readings["fan_speed"] = self._ramp_limit(code, "fan_speed", fan_target, hour)
            else:
                readings["valve_position"] = self._ramp_limit(code, "valve_position", 0.0, hour)
                readings["fan_speed"] = self._ramp_limit(code, "fan_speed", 0.0, hour)

        elif equip_type == "ups":
            readings["battery_level"] = max(50, 100 - (24 - hour) * 0.5)  # Slow drain
            readings["load_pct"] = 30 + self._scenario_rng.uniform(-5, 5)

        elif equip_type == "generator":
            readings["status"] = 0  # Standby unless load shedding
            readings["fuel_level"] = 85 + self._scenario_rng.uniform(-2, 2)

        elif equip_type == "pump":
            # Zone-demand responsive pump with affinity laws
            if schedule_state.chiller_staging.value != "off":
                staging_base = {"stage_1": 50, "stage_2": 75, "full_load": 95}.get(
                    schedule_state.chiller_staging.value, 50
                )
                # Modulate speed by zone demand
                setpoint = self.site_schedule.COMFORT_SETPOINT + schedule_state.setpoint_offset
                zone_count = max(len(self.zone_temperatures), 1)
                zones_demanding = sum(1 for zt in self.zone_temperatures.values() if zt > setpoint + 0.5)
                demand_factor = zones_demanding / zone_count
                speed_target = staging_base * (0.5 + 0.5 * demand_factor)
                speed_target = max(25.0, min(100.0, speed_target))
                readings["speed_pct"] = self._ramp_limit(code, "speed_pct", speed_target, hour)
                # Affinity laws: Q ∝ N, dP ∝ N²
                readings["flow_lps"] = round(readings["speed_pct"] * 0.3, 1)
                readings["differential_pressure_kpa"] = round((readings["speed_pct"] / 100.0) ** 2 * 150.0, 1)
                readings["status"] = 1
            else:
                readings["speed_pct"] = self._ramp_limit(code, "speed_pct", 0.0, hour)
                readings["flow_lps"] = 0
                readings["differential_pressure_kpa"] = 0
                readings["status"] = 0

        elif equip_type == "meter":
            if "MTR-B1-MAIN" in code or "MTR-GRID" in code:
                # Main grid meter (council meter): shows NET consumption
                # Council sees: site_load + bess_charge_grid - solar - bess_discharge
                readings["power_kw"] = round(self.current_grid_import_kw, 1)
                readings["grid_export_kw"] = round(self.current_grid_export_kw, 1)
                readings["site_load_kw"] = round(self.current_site_load_kw, 1)
                readings["solar_offset_kw"] = round(self.current_solar_gen_kw, 1)
                readings["net_direction"] = 1.0 if self.current_grid_import_kw > 0 else -1.0
            elif "MTR-R-SOLAR" in code or "MTR-PV" in code:
                # Solar generation meter: shows PV output
                readings["power_kw"] = round(self.current_solar_gen_kw, 1)
                readings["daily_energy_kwh"] = round(self._daily_solar_gen_kwh, 1)
            elif "MTR-W" in code or "WATER" in code:
                # Water meter: not electrical, keep separate
                readings["flow_rate_lpm"] = round(2.0 + self._scenario_rng.uniform(-0.5, 0.5), 1)
            else:
                # Default: building consumption
                readings["power_kw"] = round(self.current_site_load_kw, 1)
            readings["power_factor"] = round(0.92 + self._scenario_rng.uniform(-0.02, 0.02), 3)

        elif equip_type == "bess":
            # Battery Energy Storage System — responds to TOU schedule and solar
            # Charge off-peak (22:00-06:00) and when solar excess, discharge peak (07:00-10:00, 17:00-21:00)
            bess_capacity_kwh = 200.0  # 200 kWh system
            max_charge_kw = 50.0
            max_discharge_kw = 50.0
            # Round-trip losses: ~85% each way → ~72% round-trip
            # Includes battery cells + power electronics + thermal management
            bess_charge_eff = 0.85
            bess_discharge_eff = 0.85

            charge_kw = 0.0
            discharge_kw = 0.0

            if hour < 6 or hour >= 22:
                # Off-peak: charge from grid (grid provides charge_kw, battery stores 85%)
                charge_kw = max_charge_kw * 0.8
                stored_kwh = charge_kw * bess_charge_eff
                soc_delta = (stored_kwh / bess_capacity_kwh) * 100.0
                self.bess_soc = min(100.0, self.bess_soc + soc_delta)
            elif 7 <= hour <= 10 or 17 <= hour <= 21:
                # Peak: discharge to offset grid (battery depletes more than delivered)
                if self.bess_soc > 10:
                    discharge_kw = max_discharge_kw * min(1.0, (self.bess_soc - 10) / 30.0)
                    # Battery must deplete discharge_kw / eff internally
                    depleted_kwh = discharge_kw / bess_discharge_eff
                    soc_delta = (depleted_kwh / bess_capacity_kwh) * 100.0
                    self.bess_soc = max(10.0, self.bess_soc - soc_delta)
            elif solar_eff > 50 and self.bess_soc < 90:
                # Midday solar excess: charge from solar (same efficiency loss)
                charge_kw = max_charge_kw * 0.5 * (solar_eff / 100.0)
                stored_kwh = charge_kw * bess_charge_eff
                soc_delta = (stored_kwh / bess_capacity_kwh) * 100.0
                self.bess_soc = min(100.0, self.bess_soc + soc_delta)

            readings["state_of_charge_pct"] = round(self.bess_soc, 1)
            readings["charge_power_kw"] = round(charge_kw, 1)
            readings["discharge_power_kw"] = round(discharge_kw, 1)
            readings["grid_import_kw"] = round(self.current_grid_import_kw, 1)
            # Battery temp: ambient + self-heating from efficiency losses
            charge_heat = charge_kw * (1 - bess_charge_eff)
            discharge_heat = discharge_kw * (1 / bess_discharge_eff - 1) if discharge_kw > 0 else 0
            self_heat = (charge_heat + discharge_heat) * 0.5  # °C per kW loss
            readings["battery_temp_c"] = round(ambient + self_heat, 1)
            readings["status"] = 1.0

        elif equip_type == "inverter":
            # Solar inverter — responds to solar_efficiency, time of day, health
            # 297 kWp total plant / 4 inverters = 74.25 kWp per string
            panel_capacity_kw = 74.25
            if solar_eff > 0:
                # Time-of-day bell curve: peak at noon
                hour_mod = hour % 24
                time_factor = max(0, 1.0 - abs(hour_mod - 12) / 6.0) if 6 <= hour_mod < 18 else 0.0

                dc_power = panel_capacity_kw * (solar_eff / 100.0) * time_factor * (health / 100.0)
                inv_efficiency = 0.96 * (health / 100.0)  # Degrades slightly with health
                ac_power = dc_power * inv_efficiency

                readings["dc_power_kw"] = round(dc_power, 1)
                readings["ac_power_kw"] = round(ac_power, 1)
                readings["efficiency_pct"] = round(inv_efficiency * 100, 1)
                readings["dc_voltage"] = round(600 + (solar_eff / 100.0 - 0.5) * 100, 0)  # ~550-650V
                readings["temperature_c"] = round(ambient + 15 * time_factor, 1)
                readings["status"] = 1.0
            else:
                readings["dc_power_kw"] = 0.0
                readings["ac_power_kw"] = 0.0
                readings["efficiency_pct"] = 0.0
                readings["dc_voltage"] = 0.0
                readings["temperature_c"] = round(ambient, 1)
                readings["status"] = 0.0

        elif equip_type == "luminaire":
            # Luminaire — responds to lighting_mode, daylight (solar as proxy), occupancy
            lighting_mode = schedule_state.lighting_mode.value

            # DALI→Lighting occupancy bridge: use per-zone DALI PIR occupancy
            zone_id = self._equipment_to_zone(code)
            zone_occ_pct = self._get_zone_occupancy(zone_id)
            occupancy = zone_occ_pct / 100.0  # 0.0-1.0

            base_brightness = {
                "off": 0,
                "security_only": 10,
                "dimmed": 30,
                "full": 100,
                "daylight_harvest": 65,
            }.get(lighting_mode, 0)

            if lighting_mode == "daylight_harvest" and solar_eff > 0:
                # Tridonic DALI daylight harvesting: reduce brightness when daylight strong
                daylight_reduction = (solar_eff / 100.0) * 40  # Up to 40% reduction
                base_brightness = max(20, base_brightness - daylight_reduction)

            # Tridonic native occupancy dimming: unoccupied zones dim to 20%
            if occupancy < 0.1 and lighting_mode not in ("off", "security_only"):
                base_brightness = min(base_brightness, 20)
            elif occupancy < 0.3 and lighting_mode not in ("off", "security_only"):
                # Low occupancy: scale brightness down proportionally
                scale = occupancy / 0.3  # 0.0 at 0%, 1.0 at 30%
                base_brightness = max(20, base_brightness * scale)

            power_w = base_brightness / 100.0 * 40.0  # 40W at full brightness
            readings["brightness_pct"] = round(base_brightness, 1)
            readings["power_w"] = round(power_w, 1)
            readings["dimming_level"] = round(base_brightness, 1)
            readings["status"] = 1.0 if base_brightness > 0 else 0.0

        elif equip_type == "zone_controller":
            # Zone controller — reports zone environment and control state
            zone_id = self._equipment_to_zone(code)
            zone_temp = self.zone_temperatures.get(
                zone_id, self.site_schedule.COMFORT_SETPOINT + schedule_state.setpoint_offset
            )
            setpoint = self.site_schedule.COMFORT_SETPOINT + schedule_state.setpoint_offset
            occupancy = schedule_state.target_occupancy_pct

            readings["zone_temp_c"] = round(zone_temp + self._scenario_rng.uniform(-0.2, 0.2), 1)
            readings["occupancy_pct"] = round(occupancy + self._scenario_rng.uniform(-2, 2), 1)
            readings["setpoint_c"] = round(setpoint, 1)
            # Mode: heating if below setpoint-1, cooling if above setpoint+1, else off
            if zone_temp < setpoint - 1.0:
                readings["mode"] = 1.0  # heating
            elif zone_temp > setpoint + 1.0:
                readings["mode"] = 2.0  # cooling
            else:
                readings["mode"] = 0.0  # satisfied / off
            readings["status"] = 1.0 if occupancy > 0 else 0.0

        elif equip_type == "dali_controller":
            # DALI bus controller — reports bus health and connected devices
            readings["status"] = 1.0 if schedule_state.lighting_mode.value != "off" else 0.0
            readings["bus_fault"] = 0.0 if health > 50 else 1.0
            readings["devices_online"] = round(20 * (health / 100.0))

        elif equip_type in ("dali_zone", "controller"):
            lighting_pct = {
                "off": 0,
                "security_only": 10,
                "dimmed": 30,
                "full": 100,
                "daylight_harvest": 65,
            }.get(schedule_state.lighting_mode.value, 0)
            readings["brightness_pct"] = float(lighting_pct)
            readings["status"] = 1.0 if lighting_pct > 0 else 0.0

        elif equip_type == "zone_sensor":
            # CO2 and humidity (legacy combined sensor)
            occupancy_factor = schedule_state.target_occupancy_pct / 100.0
            readings["co2_ppm"] = 400 + occupancy_factor * 200 + self._scenario_rng.uniform(-20, 20)
            readings["humidity_pct"] = 45 + occupancy_factor * 10 + self._scenario_rng.uniform(-3, 3)

        elif equip_type == "temp_sensor":
            # Temperature sensor — reads zone temperature
            zone_id = self._equipment_to_zone(code)
            actual_temp = self.zone_temperatures.get(
                zone_id, self.site_schedule.COMFORT_SETPOINT + schedule_state.setpoint_offset
            )
            sensor_noise = self._scenario_rng.uniform(-0.2, 0.2)
            readings["zone_temp"] = round(actual_temp + sensor_noise, 1)

        elif equip_type == "co2_sensor":
            # CO2 sensor — occupancy-driven
            occupancy_factor = schedule_state.target_occupancy_pct / 100.0
            readings["co2_ppm"] = round(400 + occupancy_factor * 200 + self._scenario_rng.uniform(-20, 20))

        elif equip_type == "humidity_sensor":
            # Humidity sensor — seasonal + occupancy
            occupancy_factor = schedule_state.target_occupancy_pct / 100.0
            base_humidity = getattr(self, "current_humidity", 50.0)
            indoor_rh = base_humidity * 0.6 + occupancy_factor * 10 + self._scenario_rng.uniform(-3, 3)
            readings["humidity_pct"] = round(max(25, min(75, indoor_rh)), 1)

        elif equip_type == "diffuser":
            # Diffuser status — follows HVAC schedule
            from app.services.site_schedule import HVACMode

            is_hvac_on = schedule_state.hvac_mode not in (HVACMode.OFF, HVACMode.NIGHT_SETBACK)
            readings["status"] = 1.0 if is_hvac_on else 0.0
            if is_hvac_on:
                readings["airflow_pct"] = round(60 + self._scenario_rng.uniform(-10, 10), 1)
            else:
                readings["airflow_pct"] = 0.0

        elif equip_type == "unknown":
            # Generic equipment — minimal readings
            readings["status"] = 1.0 if health > 50 else 0.0

        elif equip_type == "fire":
            # Fire safety system — always healthy unless faulted
            readings["status"] = 1.0 if health > 30 else 0.0
            readings["alarm_active"] = 0.0

        return readings

    async def _inject_fault(self):
        """Inject a fault into equipment and create real alerts."""
        try:
            # Get equipment to fault (resolve site code to UUID internally)
            equipment_list = self.equipment_repo.get_by_site_code(self.site_id)
            if not equipment_list:
                logger.warning(f"No equipment available to fault (site_id={self.site_id})")
                return

            # Filter by type if specified
            if self.current_scenario and self.current_scenario.fault_equipment_type:
                target_type = self.current_scenario.fault_equipment_type.lower()
                filtered = [
                    eq
                    for eq in equipment_list
                    if target_type in (eq.get("equipment_type", "") or "").lower()
                    or target_type in (eq.get("code", "") or "").lower()
                ]
                if filtered:
                    equipment_list = filtered
            else:
                # Prefer HVAC equipment for faults (more realistic)
                hvac_types = {"chiller", "ahu", "fcu", "vav", "pump", "cooling_tower", "ct"}
                hvac_candidates = [e for e in equipment_list if (e.get("type", "") or "").lower() in hvac_types]
                if hvac_candidates:
                    equipment_list = hvac_candidates

            # Pick random equipment
            equipment = self._scenario_rng.choice(equipment_list)
            eq_id = equipment.get("id")
            eq_code = equipment.get("code", eq_id)
            eq_name = equipment.get("name", eq_code)
            eq_type = (equipment.get("type", "") or "unknown").lower()

            # Generate fault details
            fault_types = [
                ("High vibration detected", "vibration", 85),
                ("Temperature deviation", "temperature", 75),
                ("Pressure anomaly", "pressure", 70),
                ("Current draw elevated", "electrical", 80),
                ("Filter differential high", "filter", 65),
            ]
            fault_type, fault_category, severity = self._scenario_rng.choice(fault_types)

            # Record fault with hours_faulted tracking for persistence degradation
            fault_info = {
                "equipment_id": eq_id,
                "equipment_code": eq_code,
                "equipment_name": eq_name,
                "fault_type": fault_type,
                "fault_category": fault_category,
                "severity": severity,
                "fault_hour": self.simulated_time.hour,
                "detected_at": datetime.now().isoformat(),
                "hours_faulted": 0,
            }
            self.active_faults[eq_code] = fault_info
            logger.warning(f"[FAULT INJECT] {eq_code}: {fault_type} (severity={severity}, day={self.days_simulated})")

            # Emit fault event
            self._emit_event(
                LifecycleEvent(
                    timestamp=datetime.now(),
                    simulated_hour=self.simulated_time.hour,
                    event_type=EventType.EQUIPMENT_FAULT,
                    equipment_id=eq_code,
                    equipment_name=eq_name,
                    description=f"{fault_type} on {eq_name}",
                    details=fault_info,
                )
            )

            # Degrade equipment health
            current_health = equipment.get("health_score", 80)
            new_health = max(30, current_health - self._scenario_rng.randint(15, 30))

            self.equipment_repo.update(
                eq_code,
                {
                    "health_score": new_health,
                    "status": "warning" if new_health >= 50 else "critical",
                },
            )

            # Create prediction in database
            await self._create_prediction(equipment, fault_info)

            # Generate alert and work order via existing pipeline
            await self._generate_alert(equipment, fault_info)

            # Create real alert in Supabase via EquipmentAlertService (104-02)
            try:
                from app.services.equipment_alert_service import EquipmentAlertService

                alert_svc = EquipmentAlertService()
                alert_severity = "critical" if eq_type in ("chiller", "generator") else "warning"
                alert_svc.create_alert_for_equipment(
                    equipment_id=eq_id,
                    site_id=equipment.get("site_id", self.site_id),
                    severity=alert_severity,
                    message=f"Fault detected on {eq_code}: {fault_type}",
                    alert_type="equipment_fault",
                    notify_telegram=self.current_scenario.sentry_notifications if self.current_scenario else False,
                )
                logger.info(f"Alert created for {eq_code} via EquipmentAlertService")
            except Exception as e:
                logger.debug(f"Could not create Supabase alert for {eq_code}: {e}")

            # Schedule repair if auto_repair enabled
            if self.current_scenario and self.current_scenario.auto_repair:
                repair_hour = self.simulated_time.hour + self.current_scenario.repair_delay_hours
                if repair_hour >= 24:
                    repair_hour -= 24

                self.pending_repairs[eq_code] = {
                    **fault_info,
                    "scheduled_repair_hour": repair_hour,
                    "work_order_id": None,
                }
                logger.info(f"Repair scheduled for {eq_code} at hour {repair_hour}")

        except Exception as e:
            logger.error(f"Fault injection error: {e}")

    async def _create_prediction(self, equipment: dict, fault_info: dict):
        """Create a prediction in the database."""
        try:
            eq_id = equipment.get("id")
            site_id = equipment.get("site_id")

            prediction_data = {
                "equipment_id": eq_id,
                "site_id": site_id,
                "prediction_type": "failure",
                "probability_percent": fault_info["severity"],
                "timeframe": "14 days",
                "severity": "high" if fault_info["severity"] >= 75 else "medium",
                "description": f"ML detected: {fault_info['fault_type']}",
                "status": "active",
                "model_version": "lifecycle_sim_v1",
            }

            self.prediction_repo.create(prediction_data)

            self._emit_event(
                LifecycleEvent(
                    timestamp=datetime.now(),
                    simulated_hour=self.simulated_time.hour,
                    event_type=EventType.ALERT_GENERATED,
                    equipment_id=fault_info["equipment_code"],
                    equipment_name=fault_info["equipment_name"],
                    description=f"ML prediction created: {fault_info['severity']}% failure probability",
                    details={"prediction": prediction_data},
                )
            )

        except Exception as e:
            logger.error(f"Prediction creation error: {e}")

    async def _generate_alert(self, equipment: dict, fault_info: dict):
        """Generate alert and optionally notify Sentry."""
        try:
            # Create work order
            work_order = await self.work_order_repo.create_work_order(
                {
                    "equipment_id": equipment.get("id"),
                    "title": f"Repair: {fault_info['fault_type']}",
                    "description": (
                        f"Automated work order for {fault_info['equipment_name']}: {fault_info['fault_type']}"
                    ),
                    "priority": "high" if fault_info["severity"] >= 75 else "medium",
                    "status": "scheduled",
                    "created_by": "LIFECYCLE_SIM",
                }
            )

            wo_code = work_order.get("code", "WO-SIM") if work_order else "WO-SIM"

            self._emit_event(
                LifecycleEvent(
                    timestamp=datetime.now(),
                    simulated_hour=self.simulated_time.hour,
                    event_type=EventType.WORK_ORDER_CREATED,
                    equipment_id=fault_info["equipment_code"],
                    equipment_name=fault_info["equipment_name"],
                    description=f"Work order {wo_code} created",
                    details={"work_order_code": wo_code, "priority": "high"},
                )
            )

            # Update pending repair with work order ID
            if fault_info["equipment_code"] in self.pending_repairs:
                self.pending_repairs[fault_info["equipment_code"]]["work_order_id"] = wo_code

            # Notify Sentry if enabled
            if self.current_scenario and self.current_scenario.sentry_notifications:
                await self._notify_sentry(equipment, fault_info, wo_code)

        except Exception as e:
            logger.error(f"Alert generation error: {e}")

    async def _notify_sentry(self, equipment: dict, fault_info: dict, work_order_code: str):
        """Send notification to Sentry bot via email and Telegram."""
        try:
            from app.services.sentry_integration.work_order_notifier import WorkOrderNotifier

            notifier = WorkOrderNotifier()

            # Build work_order_data in the format WorkOrderNotifier expects
            work_order_data = {
                "work_order_id": work_order_code,
                "work_order_code": work_order_code,
                "equipment_id": fault_info.get("equipment_id"),
                "equipment_code": fault_info.get("equipment_code"),
                "equipment_name": fault_info.get("equipment_name"),
                "equipment_type": equipment.get("type", "unknown"),
                "site_code": self.site_id,
                "title": f"Repair: {fault_info['fault_type']}",
                "description": f"Automated work order for {fault_info['equipment_name']}: {fault_info['fault_type']}",
                "criticality": "HIGH" if fault_info.get("severity", 0) >= 75 else "MEDIUM",
                "service_type": "callout",
                "technician_id": "bederf@gmail.com",
                "technician_email": "bederf@gmail.com",
                "technician_name": "John Smith",
            }

            result = await notifier.notify_technician_with_code(work_order_data)
            email_sent = result.get("email_sent", False)
            telegram_sent = result.get("telegram_sent", False)
            logger.info(f"[SENTRY] Notification for {work_order_code}: email={email_sent}, telegram={telegram_sent}")

            self._emit_event(
                LifecycleEvent(
                    timestamp=datetime.now(),
                    simulated_hour=self.simulated_time.hour,
                    event_type=EventType.TECHNICIAN_DISPATCHED,
                    equipment_id=fault_info["equipment_code"],
                    equipment_name=fault_info["equipment_name"],
                    description=f"Technician notified via Sentry for {work_order_code}",
                    details={
                        "notification_method": "email+telegram",
                        "work_order": work_order_code,
                        "email_sent": email_sent,
                        "telegram_sent": telegram_sent,
                    },
                )
            )

        except Exception as e:
            logger.warning(f"Sentry notification failed: {e}")

    async def _check_pending_repairs(self):
        """Check if any repairs are due."""
        current_hour = self.simulated_time.hour
        repairs_to_complete = []

        for eq_code, repair_info in self.pending_repairs.items():
            if repair_info.get("scheduled_repair_hour") == current_hour:
                repairs_to_complete.append((eq_code, repair_info))

        for eq_code, repair_info in repairs_to_complete:
            await self._complete_repair(eq_code, repair_info)

    async def _complete_repair(self, eq_code: str, repair_info: dict):
        """Simulate technician completing repair with health restoration."""
        try:
            # Create completed work order in Supabase (104-02)
            try:
                wo_id = f"WO-SIM-{eq_code}-{self.simulated_time.strftime('%m%d%H')}"
                await self.work_order_repo.create_work_order(
                    {
                        "work_order_id": wo_id,
                        "equipment_id": repair_info.get("equipment_id", eq_code),
                        "title": f"Repair complete: {repair_info.get('fault_type', 'fault')}",
                        "description": (f"Repair completed for fault on {eq_code}. Health restored to 85%."),
                        "status": "completed",
                        "priority": "high",
                        "created_by": "LIFECYCLE_SIM",
                    }
                )
                logger.info(f"Work order {wo_id} created for repair of {eq_code}")
            except Exception as e:
                logger.debug(f"Work order creation skipped for {eq_code}: {e}")

            # Restore equipment health to 85% via Supabase (104-02)
            try:
                from app.services.simulation_store import get_simulation_store

                store = get_simulation_store(self.site_id)
                store.update_equipment_state(eq_code, {"health_score": 85, "status": "normal"})
                logger.info(f"Health restored to 85% for {eq_code}")
            except Exception:
                pass

            # Emit repair completed event
            self._emit_event(
                LifecycleEvent(
                    timestamp=datetime.now(),
                    simulated_hour=self.simulated_time.hour,
                    event_type=EventType.REPAIR_COMPLETED,
                    equipment_id=eq_code,
                    equipment_name=repair_info.get("equipment_name"),
                    description=(f"Repair complete: {repair_info.get('equipment_name')} health restored to 85%"),
                    details={
                        "fault_type": repair_info.get("fault_type"),
                        "health_restored": 85,
                    },
                )
            )

            # Submit service feedback
            await self._submit_service_feedback(eq_code, repair_info)

            # Remove from active faults and pending repairs
            self.active_faults.pop(eq_code, None)
            self.pending_repairs.pop(eq_code, None)

        except Exception as e:
            logger.error(f"Repair completion error: {e}")

    async def _submit_service_feedback(self, eq_code: str, repair_info: dict):
        """Simulate technician submitting service feedback."""
        try:
            # Start feedback session
            work_order_id = repair_info.get("work_order_id", "WO-SIM-001")
            equipment_id = repair_info.get("equipment_id", eq_code)

            session = await self.feedback_service.start_feedback_session(
                work_order_id=work_order_id, equipment_id=equipment_id, equipment_code=eq_code, service_type="breakdown"
            )

            # Submit some readings showing improvement
            fault_category = repair_info.get("fault_category", "vibration")

            # Submit a good reading (improved from fault)
            if fault_category == "vibration":
                await self.feedback_service.submit_feedback_item(
                    session.session_id,
                    "vibration",
                    1.2,  # Good value
                    FeedbackItemType.READING,
                    unit="mm/s",
                    notes="Post-repair vibration within normal range",
                )
            elif fault_category == "temperature":
                await self.feedback_service.submit_feedback_item(
                    session.session_id,
                    "temperature",
                    22.5,
                    FeedbackItemType.READING,
                    unit="°C",
                    notes="Temperature stable after repair",
                )

            # Submit observation
            await self.feedback_service.submit_feedback_item(
                session.session_id,
                "observation",
                f"Repaired {repair_info.get('fault_type')}. Equipment operating normally.",
                FeedbackItemType.OBSERVATION,
                notes="Repair successful",
            )

            # Complete session (force=True to skip missing items)
            result = await self.feedback_service.complete_feedback_session(session.session_id, force=True)

            self._emit_event(
                LifecycleEvent(
                    timestamp=datetime.now(),
                    simulated_hour=self.simulated_time.hour,
                    event_type=EventType.FEEDBACK_SUBMITTED,
                    equipment_id=eq_code,
                    equipment_name=repair_info.get("equipment_name"),
                    description=f"Service feedback submitted: health +{result.get('health_score_change', 0)}",
                    details={
                        "session_id": session.session_id,
                        "health_change": result.get("health_score_change", 0),
                        "items_collected": result.get("items_collected", 0),
                    },
                )
            )

            # Emit health restored event
            self._emit_event(
                LifecycleEvent(
                    timestamp=datetime.now(),
                    simulated_hour=self.simulated_time.hour,
                    event_type=EventType.HEALTH_RESTORED,
                    equipment_id=eq_code,
                    equipment_name=repair_info.get("equipment_name"),
                    description=f"Equipment health restored for {repair_info.get('equipment_name')}",
                    details={"new_status": "normal"},
                )
            )

            # Resolve predictions
            equipment = self.equipment_repo.get_by_id(eq_code)
            if equipment:
                self.prediction_repo.resolve_by_equipment(equipment.get("id"))

            self._emit_event(
                LifecycleEvent(
                    timestamp=datetime.now(),
                    simulated_hour=self.simulated_time.hour,
                    event_type=EventType.ALERT_RESOLVED,
                    equipment_id=eq_code,
                    equipment_name=repair_info.get("equipment_name"),
                    description=f"Alert resolved for {repair_info.get('equipment_name')}",
                    details={},
                )
            )

        except Exception as e:
            logger.error(f"Service feedback submission error: {e}")

    def serialize_state(self) -> dict[str, Any]:
        """
        Serialize orchestrator state to JSON-serializable dict for database storage.
        Enables crash recovery by preserving simulation state.

        Returns:
            Dict with: simulated_time, days_simulated, active_faults, pending_repairs,
            recent_events, time_multiplier, occupancy_seed
        """
        return {
            "simulated_time": self.simulated_time.isoformat(),
            "days_simulated": self.days_simulated,
            "active_faults": self.active_faults,
            "pending_repairs": self.pending_repairs,
            "recent_events": [
                {
                    "timestamp": e.timestamp.isoformat(),
                    "event_type": e.event_type.value,
                    "equipment_id": e.equipment_id,
                    "message": e.description,
                }
                for e in self.events[-50:]  # Keep last 50 events for display
            ],
            "time_multiplier": self.time_multiplier,
            "occupancy_seed": self._occupancy_seed,
            "total_energy_kwh": round(self.total_energy_kwh, 1),
            "current_hour_power_kw": round(self.current_hour_power_kw, 2),
            "cumulative_baseline_kwh": round(self._cumulative_baseline_kwh, 2),
            "cumulative_sentinel_kwh": round(self._cumulative_sentinel_kwh, 2),
            "cumulative_solar_gen_kwh": round(self._cumulative_solar_gen_kwh, 2),
            "cumulative_bess_discharge_kwh": round(self._cumulative_bess_discharge_kwh, 2),
            "solar_hour_index": self._solar_hour_index,
            "actuator_state": self._actuator_state,
        }

    @staticmethod
    def deserialize_state(state_dict: dict[str, Any]) -> "LifecycleOrchestrator":
        """
        Restore orchestrator from serialized state (crash recovery).
        Creates new instance and restores state from checkpoint.

        Args:
            state_dict: Dict from serialize_state()

        Returns:
            LifecycleOrchestrator instance with restored state
        """
        orchestrator = LifecycleOrchestrator()

        # Restore time and simulation progress
        orchestrator.simulated_time = datetime.fromisoformat(state_dict["simulated_time"])
        orchestrator.days_simulated = state_dict["days_simulated"]
        orchestrator.time_multiplier = state_dict["time_multiplier"]
        orchestrator._occupancy_seed = state_dict["occupancy_seed"]

        # Restore faults and repairs
        orchestrator.active_faults = state_dict.get("active_faults", {})
        orchestrator.pending_repairs = state_dict.get("pending_repairs", {})

        # Restore energy consumption tracking
        orchestrator.total_energy_kwh = state_dict.get("total_energy_kwh", 0.0)
        orchestrator.current_hour_power_kw = state_dict.get("current_hour_power_kw", 0.0)
        orchestrator._cumulative_baseline_kwh = state_dict.get("cumulative_baseline_kwh", 0.0)
        orchestrator._cumulative_sentinel_kwh = state_dict.get("cumulative_sentinel_kwh", 0.0)
        orchestrator._cumulative_solar_gen_kwh = state_dict.get("cumulative_solar_gen_kwh", 0.0)
        orchestrator._cumulative_bess_discharge_kwh = state_dict.get("cumulative_bess_discharge_kwh", 0.0)
        orchestrator._solar_hour_index = state_dict.get("solar_hour_index", 0)
        orchestrator._actuator_state = state_dict.get("actuator_state", {})

        # Restore occupancy randomness (deterministic for same seed)
        if orchestrator._occupancy_seed is not None:
            orchestrator._scenario_rng.seed(orchestrator._occupancy_seed)

        logger.info(
            f"Restored orchestrator state: day {orchestrator.days_simulated}, "
            f"{len(orchestrator.active_faults)} active faults, "
            f"{len(orchestrator.pending_repairs)} pending repairs"
        )

        return orchestrator

    async def save_checkpoint(self) -> bool:
        """
        Save current state to JSON store (called every 6 simulated hours).
        Enables resumption from checkpoint if server crashes.

        Returns:
            True if saved successfully, False otherwise
        """
        if not self.task_id:
            logger.warning(f"Cannot save checkpoint: task_id is None or empty. days_simulated={self.days_simulated}")
            return False

        try:
            from app.services.simulation_store import get_simulation_store

            store = get_simulation_store(self.site_id)
            state_snapshot = self.serialize_state()

            store.update_task_progress(
                self.task_id,
                {
                    "state_snapshot": state_snapshot,
                    "progress_pct": int((self.days_simulated / 365) * 100) if self.seasonal_modeler else 0,
                    "days_completed": self.days_simulated,
                },
            )

            logger.info(f"Checkpoint saved for task {self.task_id}: day {self.days_simulated}")
            return True

        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}")
            return False

    # === SENTINEL RESPONSE LOOP (106-02) ===

    def _generate_health_recommendation(self, code: str, equip_type: str, health: float, tier: int) -> dict:
        """Generate a targeted recommendation based on equipment health and type.

        Args:
            code: Equipment code (e.g. S002-CHILLER-B1-001)
            equip_type: Equipment type (e.g. chiller, ahu, vav, fcu, ups)
            health: Current health score (0-100)
            tier: Response tier (1=auto-execute, 2=pending approval, 3=escalation)

        Returns:
            Dict with action, point_name, target_value, rationale
        """
        recommendations = {
            "chiller": {
                1: {
                    "action": "Reduce chiller load by staging down",
                    "point_name": "load_pct",
                    "target_value": 60,
                    "rationale": f"Chiller {code} health at {health:.0f}% — reduce load to slow degradation",
                },
                2: {
                    "action": "Schedule chiller maintenance inspection",
                    "point_name": "maintenance_flag",
                    "target_value": 1,
                    "rationale": f"Chiller {code} health at {health:.0f}% — maintenance inspection recommended",
                },
                3: {
                    "action": "Emergency chiller shutdown and technician dispatch",
                    "point_name": "compressor_status",
                    "target_value": 0,
                    "rationale": f"Chiller {code} critically degraded at {health:.0f}% — shutdown to prevent damage",
                },
            },
            "ahu": {
                1: {
                    "action": "Reduce AHU fan speed 10%",
                    "point_name": "fan_speed_pct",
                    "target_value": 70,
                    "rationale": f"AHU {code} health at {health:.0f}% — reduce fan stress",
                },
                2: {
                    "action": "Schedule AHU filter and belt inspection",
                    "point_name": "maintenance_flag",
                    "target_value": 1,
                    "rationale": f"AHU {code} health at {health:.0f}% — belt/filter check needed",
                },
                3: {
                    "action": "Emergency AHU shutdown",
                    "point_name": "fan_status",
                    "target_value": 0,
                    "rationale": f"AHU {code} critically degraded at {health:.0f}%",
                },
            },
            "vav": {
                1: {
                    "action": "Widen VAV deadband by 1°C",
                    "point_name": "setpoint_offset",
                    "target_value": 1.0,
                    "rationale": f"VAV {code} health at {health:.0f}% — reduce cycling",
                },
                2: {
                    "action": "Schedule VAV actuator inspection",
                    "point_name": "maintenance_flag",
                    "target_value": 1,
                    "rationale": f"VAV {code} health at {health:.0f}% — actuator wear likely",
                },
                3: {
                    "action": "Lock VAV to minimum position",
                    "point_name": "damper_position",
                    "target_value": 20,
                    "rationale": f"VAV {code} critically degraded — lock to safe minimum",
                },
            },
            "fcu": {
                1: {
                    "action": "Reduce FCU fan speed",
                    "point_name": "fan_speed",
                    "target_value": "low",
                    "rationale": f"FCU {code} health at {health:.0f}% — reduce wear",
                },
                2: {
                    "action": "Schedule FCU filter clean and valve inspection",
                    "point_name": "maintenance_flag",
                    "target_value": 1,
                    "rationale": f"FCU {code} health at {health:.0f}%",
                },
                3: {
                    "action": "Disable FCU",
                    "point_name": "status",
                    "target_value": 0,
                    "rationale": f"FCU {code} critically degraded at {health:.0f}%",
                },
            },
            "ups": {
                1: {
                    "action": "Reduce UPS load by shedding non-critical circuits",
                    "point_name": "load_shed",
                    "target_value": 1,
                    "rationale": f"UPS {code} battery health at {health:.0f}% — reduce draw",
                },
                2: {
                    "action": "Schedule UPS battery test",
                    "point_name": "maintenance_flag",
                    "target_value": 1,
                    "rationale": f"UPS {code} health at {health:.0f}% — battery test required",
                },
                3: {
                    "action": "UPS battery replacement required",
                    "point_name": "battery_replace",
                    "target_value": 1,
                    "rationale": f"UPS {code} critically degraded at {health:.0f}% — replace batteries",
                },
            },
        }

        # Default recommendation for unknown equipment types
        default = {
            1: {
                "action": f"Monitor {equip_type} {code} closely",
                "point_name": "monitoring_flag",
                "target_value": 1,
                "rationale": f"{code} health at {health:.0f}%",
            },
            2: {
                "action": f"Schedule {equip_type} inspection",
                "point_name": "maintenance_flag",
                "target_value": 1,
                "rationale": f"{code} health at {health:.0f}%",
            },
            3: {
                "action": f"Escalate {equip_type} to technician",
                "point_name": "escalation_flag",
                "target_value": 1,
                "rationale": f"{code} critically degraded at {health:.0f}%",
            },
        }

        type_recs = recommendations.get(equip_type, default)
        return type_recs.get(tier, default[tier])

    async def _sentinel_response(self, code: str, equip_type: str, health: float, severity: str, simulated_hour: int):
        """SENTINEL AI response to equipment health issues.

        Generates recommendation and acts on Tier 1 (safe auto-execute).
        Logs Tier 2 as pending_approval. Escalates Tier 3 with technician dispatch.

        Args:
            code: Equipment code (e.g. S002-CHILLER-B1-001)
            equip_type: Equipment type (e.g. chiller, ahu, vav)
            health: Current health score (0-100)
            severity: Health status ("warning" or "critical")
            simulated_hour: Current simulated hour (0-23)
        """
        # Determine response tier based on severity and health
        if severity == "warning" and health > 60:
            tier = 1  # Safe auto-response
        elif severity == "critical" or health < 40:
            tier = 3  # Escalation needed
        else:
            tier = 2  # Log recommendation

        # Generate targeted recommendation
        recommendation = self._generate_health_recommendation(code, equip_type, health, tier)

        if tier == 1:
            # Auto-execute safe response
            try:
                from app.services.autonomous_decision_engine import AutonomousDecisionEngine

                decision_engine = AutonomousDecisionEngine()

                result = await decision_engine.evaluate_and_execute(
                    rule_id=f"health_response_{code}",
                    device_id=code,
                    point_name=recommendation["point_name"],
                    target_value=recommendation["target_value"],
                    rationale=recommendation["rationale"],
                )

                self._emit_event(
                    LifecycleEvent(
                        timestamp=datetime.now(),
                        simulated_hour=simulated_hour,
                        event_type=EventType.AI_OPTIMIZATION,
                        equipment_id=code,
                        description=f"SENTINEL auto-response (Tier 1): {recommendation['action']} for {code}",
                        details={
                            "tier": 1,
                            "equipment": code,
                            "action": recommendation["action"],
                            "result": result.status if hasattr(result, "status") else "executed",
                        },
                    )
                )
            except Exception as e:
                # If auto-execute fails, fall through to logged recommendation
                logger.info(f"Tier 1 auto-execute unavailable for {code}: {e}")
                self._emit_event(
                    LifecycleEvent(
                        timestamp=datetime.now(),
                        simulated_hour=simulated_hour,
                        event_type=EventType.AI_OPTIMIZATION,
                        equipment_id=code,
                        description=f"SENTINEL recommendation (Tier 1 fallback): {recommendation['action']} for {code}",
                        details={"tier": 1, "equipment": code, "action": recommendation["action"], "status": "logged"},
                    )
                )

        elif tier == 2:
            self._emit_event(
                LifecycleEvent(
                    timestamp=datetime.now(),
                    simulated_hour=simulated_hour,
                    event_type=EventType.AI_OPTIMIZATION,
                    equipment_id=code,
                    description=f"SENTINEL recommendation (Tier 2): {recommendation['action']} for {code}",
                    details={
                        "tier": 2,
                        "equipment": code,
                        "action": recommendation["action"],
                        "status": "pending_approval",
                    },
                )
            )

        else:  # tier == 3
            self._emit_event(
                LifecycleEvent(
                    timestamp=datetime.now(),
                    simulated_hour=simulated_hour,
                    event_type=EventType.ALERT_CREATED,
                    equipment_id=code,
                    description=(f"SENTINEL escalation (Tier 3): {recommendation['action']} for {code}"),
                    details={"tier": 3, "equipment": code, "action": recommendation["action"], "status": "escalated"},
                )
            )

    def _scan_safety_boundaries(self, equipment_states: dict[str, dict], simulated_hour: int, schedule_state=None):
        """DEPRECATED — replaced by SentinelAlertEngine. Kept for reference.

        Checks all equipment sensor readings against SAFETY_LIMITS. If a reading
        is within 10% of a boundary, emits a warning. If it exceeds the boundary,
        emits a critical event. Limits to 3 violations per scan to prevent spam.

        Suppresses alerts when values fall within NORMAL_BANDS for the equipment
        type and time period — e.g. chiller supply_temp=6°C during peak is normal.

        Skips equipment that is not running — zero readings during off-hours
        are expected, not safety concerns.

        Args:
            equipment_states: Dict mapping equipment code to state dict with sensor_readings
            simulated_hour: Current simulated hour (0-23)
            schedule_state: Current SiteScheduleState (for peak/off-peak context)
        """
        # Determine peak status from schedule state
        is_peak = False
        if schedule_state:
            is_peak = schedule_state.state in (
                BuildingState.PEAK_OCCUPIED,
                BuildingState.OCCUPIED_RAMPUP,
                BuildingState.MORNING_STARTUP,
            )

        violations = []

        for code, state in equipment_states.items():
            # Skip equipment that is off — zero values are expected, not violations
            if not state.get("is_running", False):
                continue

            readings = state.get("sensor_readings", {})
            equip_type = state.get("type", "unknown").lower()

            for point_name, value in readings.items():
                if point_name not in self.SAFETY_LIMITS:
                    continue

                limits = self.SAFETY_LIMITS[point_name]
                safe_min = limits["min"]
                safe_max = limits["max"]
                safe_range = safe_max - safe_min

                if not isinstance(value, (int, float)):
                    continue

                # Check proximity to boundaries
                if value < safe_min:
                    approach_pct = 100  # Already violated
                elif value > safe_max:
                    approach_pct = 100
                elif value < safe_min + safe_range * 0.1:
                    approach_pct = 90  # Within 10% of lower limit
                elif value > safe_max - safe_range * 0.1:
                    approach_pct = 90  # Within 10% of upper limit
                else:
                    approach_pct = 0  # Safe

                if approach_pct < 90:
                    continue

                # Suppress alerts for values within normal operating bands
                normal_band = self._get_normal_band(point_name, equip_type, is_peak)
                if normal_band and normal_band[0] <= value <= normal_band[1]:
                    continue  # Value within normal operating range — suppress

                severity = "critical" if approach_pct >= 100 else "warning"
                recommended_action = self._get_safety_action(point_name, equip_type, severity)

                # Build operational context
                operational_context = {
                    "site_state": schedule_state.state.value if schedule_state else "unknown",
                    "is_peak_hours": is_peak,
                    "occupancy_pct": schedule_state.target_occupancy_pct if schedule_state else 0,
                    "hvac_mode": schedule_state.hvac_mode.value if schedule_state else "unknown",
                    "hour": simulated_hour,
                }

                # Determine which limit is being approached
                if value <= safe_min or value < safe_min + safe_range * 0.1:
                    limit_desc = f"limit: {safe_min}{limits['unit']}"
                else:
                    limit_desc = f"limit: {safe_max}{limits['unit']}"

                violations.append(
                    {
                        "code": code,
                        "point": point_name,
                        "value": value,
                        "limits": f"{safe_min}-{safe_max} {limits['unit']}",
                        "approach_pct": approach_pct,
                        "severity": severity,
                        "recommended_action": recommended_action,
                        "operational_context": operational_context,
                        "limit_desc": limit_desc,
                    }
                )

        # Emit events for violations (limit to top 3 to avoid event spam)
        for v in violations[:3]:
            severity = v["severity"]
            action_preview = (
                v["recommended_action"][:80] if len(v["recommended_action"]) > 80 else v["recommended_action"]
            )
            description = (
                f"{v['code']} {v['point']} at {v['value']}{self.SAFETY_LIMITS[v['point']]['unit']} "
                f"({v['limit_desc']}). Action: {action_preview}"
            )
            self._emit_event(
                LifecycleEvent(
                    timestamp=datetime.now(),
                    simulated_hour=simulated_hour,
                    event_type=EventType.SAFETY_VIOLATION if severity == "critical" else EventType.ALERT_CREATED,
                    equipment_id=v["code"],
                    description=description,
                    details=v,
                )
            )
            # Push to dashboard Recent Alerts
            self._push_alert_to_dashboard(
                equipment_code=v["code"],
                severity=severity,
                alert_type="safety_boundary",
                message=description,
                details=v,
            )
            # Notify Sentry bot (Telegram) for critical safety violations
            if severity == "critical":
                try:
                    from app.services.equipment_alert_service import get_equipment_alert_service

                    alert_svc = get_equipment_alert_service()
                    alert_svc.create_alert_for_equipment(
                        equipment_id=v["code"],
                        alert_type="safety_boundary",
                        severity="critical",
                        message=description,
                        site_id=self.site_id,
                        notify_telegram=True,
                    )
                except Exception as e:
                    logger.debug(f"Could not send Sentry notification for safety violation: {e}")

    def _push_alert_to_dashboard(
        self, equipment_code: str, severity: str, alert_type: str, message: str, details: dict | None = None
    ):
        """Push a SENTINEL alert into the simulation service so it appears in Recent Alerts.

        The lifecycle orchestrator tracks events internally. This bridges them to
        the bms_simulation_service alert queue, which the /api/alerts endpoint reads.

        Deduplication (two layers):
        1. Active alert check — skip if an active alert already exists for this
           equipment + alert_type (prevents duplicate rows).
        2. Cooldown — skip if an alert was pushed for this equipment + alert_type
           within the last 30 minutes (prevents cleared alerts from reappearing
           immediately when the underlying condition persists).

        Sentry bot notifications are handled separately by the caller and are NOT
        affected by this dedup — they fire every time the condition is detected.
        """
        try:
            cooldown_key = f"{equipment_code}::{alert_type}"

            # Dedup layer 1: skip if an active alert already exists for this equipment + type
            for existing in self._alert_queue:
                if (
                    existing.get("equipment_id") == equipment_code
                    and existing.get("type") == alert_type
                    and existing.get("status") == "active"
                ):
                    logger.debug(
                        f"Dedup: skipping duplicate dashboard alert for {equipment_code} "
                        f"({alert_type}) — active alert {existing['id']} already exists"
                    )
                    return

            # Dedup layer 2: cooldown — skip if we pushed an alert recently
            # (prevents cleared/acknowledged alerts from reappearing immediately)
            COOLDOWN_SECONDS = 1800  # 30 minutes
            last_push = self._dashboard_alert_cooldown.get(cooldown_key)
            if last_push:
                elapsed = (datetime.now() - last_push).total_seconds()
                if elapsed < COOLDOWN_SECONDS:
                    logger.debug(
                        f"Cooldown: skipping dashboard alert for {equipment_code} "
                        f"({alert_type}) — last pushed {elapsed:.0f}s ago (cooldown {COOLDOWN_SECONDS}s)"
                    )
                    return

            self._alert_id_counter += 1
            equip_type = (equipment_code.split("-")[1] or "unknown").lower() if "-" in equipment_code else "unknown"

            alert = {
                "id": f"SIM-ALERT-{self._alert_id_counter}",
                "equipment_id": equipment_code,
                "equipment_code": equipment_code,
                "equipment_name": equipment_code,
                "site_id": self.site_id,
                "site_name": self.site_id,
                "type": alert_type,
                "severity": severity,
                "priority": 1 if severity == "critical" else 2 if severity == "warning" else 3,
                "status": "active",
                "title": f"{severity.upper()}: {equipment_code} - {alert_type.replace('_', ' ').title()}",
                "message": message,
                "health_score": details.get("health") if details else None,
                "fault_codes": [],
                "created_at": datetime.now().isoformat(),
                "acknowledged": False,
                "acknowledged_by": None,
                "category": "hvac" if equip_type in ("chiller", "ahu", "fcu", "vav", "pump", "ct") else "electrical",
                "suggested_action": details.get("recommended_action") if details else None,
                "recommended_action": details.get("recommended_action") if details else None,
                "operational_context": details.get("operational_context") if details else None,
                "actionable_remotely": False,
            }

            self._alert_queue.append(alert)
            self._alert_history.append(alert)

            # Record cooldown timestamp
            self._dashboard_alert_cooldown[cooldown_key] = datetime.now()

            # Keep history manageable
            if len(self._alert_history) > 500:
                self._alert_history = self._alert_history[-500:]
        except Exception as e:
            logger.debug(f"Could not push alert to dashboard: {e}")

    def _get_sentinel_status(self) -> dict[str, Any]:
        """Get current SENTINEL response loop status for API.

        Returns:
            Dict with monitoring_active, equipment_monitored, health_distribution,
            active_alerts, recent_responses, and response_loop status.
        """
        health_distribution = {"healthy": 0, "warning": 0, "critical": 0}
        for status in self.health_status_cache.values():
            health_distribution[status] = health_distribution.get(status, 0) + 1

        recent_responses = [
            e
            for e in self.events[-50:]
            if e.event_type
            in (
                EventType.AI_OPTIMIZATION,
                EventType.ALERT_CREATED,
                EventType.WORK_ORDER_CREATED,
                EventType.SAFETY_VIOLATION,
            )
        ]

        return {
            "monitoring_active": self.running,
            "equipment_monitored": len(self.health_status_cache),
            "health_distribution": health_distribution,
            "active_alerts": len(self.last_alert_time),
            "recent_responses": len(recent_responses),
            "response_loop": "active" if self.running else "idle",
        }

    # =========================================================================
    # Unified Simulation API Compatibility (transplanted from BMSimulationService)
    # =========================================================================

    def get_active_alerts(self) -> list[dict[str, Any]]:
        """Return currently active (unresolved) alerts."""
        return [a for a in self._alert_queue if a.get("status") != "resolved"]

    def get_alert_history(self) -> list[dict[str, Any]]:
        """Return all historical alerts."""
        return list(self._alert_history)

    def acknowledge_alert(self, alert_id: str) -> bool:
        """Mark an alert as acknowledged."""
        for alert in self._alert_queue:
            if str(alert.get("id")) == str(alert_id):
                alert["status"] = "acknowledged"
                alert["acknowledged_at"] = datetime.now().isoformat()
                return True
        return False

    def clear_alert(self, alert_id: str) -> bool:
        """Resolve/clear an alert."""
        for alert in self._alert_queue:
            if str(alert.get("id")) == str(alert_id):
                alert["status"] = "resolved"
                alert["resolved_at"] = datetime.now().isoformat()
                self._alert_history.append(alert)
                return True
        return False

    def perform_maintenance(self, equipment_code: str) -> dict[str, Any]:
        """Perform maintenance on equipment — restore health, clear faults.

        Returns a summary of what was done.
        """
        if equipment_code not in self._equipment_health:
            return {"success": False, "error": f"Equipment {equipment_code} not found"}

        old_health = self._equipment_health[equipment_code]
        new_health = min(95.0, old_health + 30.0)
        self._equipment_health[equipment_code] = new_health

        # Clear active faults
        fault_cleared = equipment_code in self.active_faults
        if fault_cleared:
            del self.active_faults[equipment_code]

        # Update snapshot if available
        if equipment_code in self._simulation_equipment:
            self._simulation_equipment[equipment_code]["health_score"] = new_health
            self._simulation_equipment[equipment_code]["status"] = (
                "online" if new_health >= 70 else ("degraded" if new_health >= 40 else "offline")
            )

        # Reset health status cache so next monitoring cycle sees clean state
        if equipment_code in self.health_status_cache:
            self.health_status_cache[equipment_code] = "healthy" if new_health >= 70 else "warning"

        logger.info(
            f"Maintenance performed on {equipment_code}: "
            f"health {old_health:.1f} → {new_health:.1f}, fault_cleared={fault_cleared}"
        )

        return {
            "success": True,
            "equipment_code": equipment_code,
            "old_health": round(old_health, 1),
            "new_health": round(new_health, 1),
            "fault_cleared": fault_cleared,
        }

    def inject_fault(self, equipment_code: str, fault_type: str = "GENERAL_FAULT") -> dict[str, Any]:
        """Inject a fault into equipment for testing/demo."""
        if equipment_code not in self._equipment_health:
            return {"success": False, "error": f"Equipment {equipment_code} not found"}

        self.active_faults[equipment_code] = {
            "fault_type": fault_type,
            "injected_at": datetime.now().isoformat(),
            "hours_faulted": 0,
        }

        # Generate an alert for the fault
        self._alert_id_counter += 1
        alert = {
            "id": self._alert_id_counter,
            "equipment_code": equipment_code,
            "type": fault_type,
            "severity": "critical",
            "status": "active",
            "message": f"Fault injected: {fault_type} on {equipment_code}",
            "created_at": datetime.now().isoformat(),
        }
        self._alert_queue.append(alert)

        logger.info(f"Fault injected: {fault_type} on {equipment_code}")
        return {
            "success": True,
            "equipment_code": equipment_code,
            "fault_type": fault_type,
            "alert_id": self._alert_id_counter,
        }

    def clear_faults(self, equipment_code: str) -> bool:
        """Clear all faults for an equipment item."""
        if equipment_code in self.active_faults:
            del self.active_faults[equipment_code]
            return True
        return False

    def get_equipment_summary(self) -> dict[str, Any]:
        """Get a summary of all equipment in the simulation."""
        states = self._simulation_equipment
        if not states:
            return {"total": 0, "by_type": {}, "health_stats": {}, "faults": 0}

        by_type: dict[str, int] = {}
        healths: list[float] = []
        for _code, state in states.items():
            t = state.get("type", "unknown")
            by_type[t] = by_type.get(t, 0) + 1
            healths.append(state.get("health_score", 0))

        return {
            "total": len(states),
            "by_type": by_type,
            "health_stats": {
                "avg": round(sum(healths) / len(healths), 1) if healths else 0,
                "min": round(min(healths), 1) if healths else 0,
                "max": round(max(healths), 1) if healths else 0,
            },
            "faults": len(self.active_faults),
        }


def create_lifecycle_orchestrator(task_id: str | None = None, site_id: str | None = None) -> LifecycleOrchestrator:
    """
    Create a new lifecycle orchestrator instance.

    Args:
        task_id: Optional task ID for database-backed task tracking
        site_id: Target site identifier (resolved from registered buildings if None)

    Returns:
        New LifecycleOrchestrator instance
    """
    return LifecycleOrchestrator(task_id=task_id, site_id=site_id)


# Global singleton instance
_orchestrator_instance: LifecycleOrchestrator | None = None


def get_lifecycle_orchestrator(site_id: str | None = None) -> LifecycleOrchestrator:
    """
    Get or create the global lifecycle orchestrator singleton.

    Args:
        site_id: Target site identifier (resolved from registered buildings if None)

    Returns:
        Singleton LifecycleOrchestrator instance
    """
    global _orchestrator_instance
    if _orchestrator_instance is None:
        _orchestrator_instance = LifecycleOrchestrator(site_id=site_id)
        logger.info(f"Created lifecycle orchestrator singleton for {site_id}")
    return _orchestrator_instance


def get_effective_now() -> datetime:
    """Return the effective current time — simulated time if running, real time otherwise.

    When the simulator is running at accelerated speed, AI services must use the
    simulated clock instead of wall-clock time, otherwise schedule gates, prompt
    context, and recommendations will be out of sync with the equipment state.
    """
    if _orchestrator_instance is not None and _orchestrator_instance.running:
        return _orchestrator_instance.simulated_time
    return datetime.now()
