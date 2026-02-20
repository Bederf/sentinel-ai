"""
Building daily operating schedule for lifecycle simulation.

Encodes the real-world operating cycle of Sandton City Office Tower (Site 002):
- 05:30: Pre-cool start (chiller + AHU ramp to pull overnight heat)
- 06:00: Full plant on (chillers staged, AHUs at design speed)
- 07:00: Staff arrive (occupancy ramps 0->60% over 1hr, DALI full)
- 08:00-14:00: Peak occupancy (60-80%, full HVAC, daylight harvesting)
- 15:00: Staff leaving (occupancy drops, HVAC begins de-staging)
- 17:00: HVAC off (chillers off, AHUs coast, VAV dampers close)
- 18:00: Building empty (security lights only, night setback +3C)
- 22:00-05:00: Overnight (minimal systems, security lights)

Weekend: Skeleton mode (server room HVAC if any, security lights only)
"""

from dataclasses import dataclass
from enum import Enum


class HVACMode(str, Enum):
    OFF = "off"
    PRE_COOL = "pre_cool"
    FULL = "full"
    REDUCED = "reduced"
    NIGHT_SETBACK = "night_setback"


class LightingMode(str, Enum):
    OFF = "off"
    SECURITY_ONLY = "security_only"
    DIMMED = "dimmed"
    FULL = "full"
    DAYLIGHT_HARVEST = "daylight_harvest"


class ChillerStaging(str, Enum):
    OFF = "off"
    STAGE_1 = "stage_1"  # ~30% load
    STAGE_2 = "stage_2"  # ~60% load
    FULL_LOAD = "full_load"  # ~90%+ load


class BuildingState(str, Enum):
    OVERNIGHT = "overnight"
    PRE_COOL = "pre_cool"
    MORNING_STARTUP = "morning_startup"
    OCCUPIED_RAMPUP = "occupied_rampup"
    PEAK_OCCUPIED = "peak_occupied"
    AFTERNOON_WINDDOWN = "afternoon_winddown"
    HVAC_SHUTDOWN = "hvac_shutdown"
    UNOCCUPIED = "unoccupied"
    WEEKEND_SKELETON = "weekend_skeleton"


@dataclass
class ScheduleState:
    """What the building looks like at a given hour."""

    state: BuildingState
    hvac_mode: HVACMode
    target_occupancy_pct: float  # 0-100
    lighting_mode: LightingMode
    chiller_staging: ChillerStaging
    ahu_fan_pct: float  # 0-100
    setpoint_offset: float  # Degrees above comfort setpoint
    description: str


class BuildingSchedule:
    """Daily operating schedule for Site 002."""

    COMFORT_SETPOINT = 22.0  # deg C
    NIGHT_SETBACK = 3.0  # deg C above comfort

    def get_state(self, hour: int, day_of_week: int) -> ScheduleState:
        """Return building state for given hour and day.

        Args:
            hour: Hour of day (0-23)
            day_of_week: Day of week (0=Monday, 6=Sunday)

        Returns:
            ScheduleState with equipment staging levels
        """
        is_weekend = day_of_week >= 5  # Saturday=5, Sunday=6
        if is_weekend:
            return self._weekend_state(hour)
        return self._weekday_state(hour)

    def _weekday_state(self, hour: int) -> ScheduleState:
        """Return schedule state for a weekday hour."""
        if hour < 5:
            return ScheduleState(
                BuildingState.OVERNIGHT,
                HVACMode.OFF,
                0,
                LightingMode.SECURITY_ONLY,
                ChillerStaging.OFF,
                0,
                self.NIGHT_SETBACK,
                "Overnight -- minimal systems",
            )
        elif hour == 5:
            return ScheduleState(
                BuildingState.PRE_COOL,
                HVACMode.PRE_COOL,
                0,
                LightingMode.DIMMED,
                ChillerStaging.STAGE_1,
                60,
                0,
                "Pre-cool -- pulling overnight heat",
            )
        elif hour == 6:
            return ScheduleState(
                BuildingState.MORNING_STARTUP,
                HVACMode.FULL,
                5,
                LightingMode.FULL,
                ChillerStaging.STAGE_2,
                80,
                0,
                "Morning startup -- full plant on",
            )
        elif hour == 7:
            return ScheduleState(
                BuildingState.OCCUPIED_RAMPUP,
                HVACMode.FULL,
                40,
                LightingMode.FULL,
                ChillerStaging.STAGE_2,
                85,
                0,
                "Staff arriving -- occupancy ramping",
            )
        elif 8 <= hour <= 14:
            return ScheduleState(
                BuildingState.PEAK_OCCUPIED,
                HVACMode.FULL,
                75,
                LightingMode.DAYLIGHT_HARVEST,
                ChillerStaging.FULL_LOAD,
                95,
                0,
                "Peak occupied -- full HVAC",
            )
        elif hour == 15:
            return ScheduleState(
                BuildingState.AFTERNOON_WINDDOWN,
                HVACMode.FULL,
                50,
                LightingMode.FULL,
                ChillerStaging.STAGE_2,
                80,
                0,
                "Staff leaving -- occupancy dropping",
            )
        elif hour == 16:
            return ScheduleState(
                BuildingState.AFTERNOON_WINDDOWN,
                HVACMode.REDUCED,
                30,
                LightingMode.FULL,
                ChillerStaging.STAGE_1,
                60,
                0.5,
                "Late afternoon -- HVAC reducing",
            )
        elif hour == 17:
            return ScheduleState(
                BuildingState.HVAC_SHUTDOWN,
                HVACMode.OFF,
                10,
                LightingMode.DIMMED,
                ChillerStaging.OFF,
                0,
                1.0,
                "HVAC off -- building coasting",
            )
        elif hour == 18:
            return ScheduleState(
                BuildingState.UNOCCUPIED,
                HVACMode.OFF,
                2,
                LightingMode.SECURITY_ONLY,
                ChillerStaging.OFF,
                0,
                self.NIGHT_SETBACK,
                "Building empty -- security mode",
            )
        else:  # 19-23
            return ScheduleState(
                BuildingState.OVERNIGHT,
                HVACMode.OFF,
                0,
                LightingMode.SECURITY_ONLY,
                ChillerStaging.OFF,
                0,
                self.NIGHT_SETBACK,
                "Overnight -- minimal systems",
            )

    def _weekend_state(self, hour: int) -> ScheduleState:
        """Return schedule state for a weekend hour (skeleton mode)."""
        return ScheduleState(
            BuildingState.WEEKEND_SKELETON,
            HVACMode.OFF,
            0,
            LightingMode.SECURITY_ONLY,
            ChillerStaging.OFF,
            0,
            self.NIGHT_SETBACK,
            "Weekend skeleton -- security lights only",
        )

    def get_target_setpoint(self, hour: int, day_of_week: int) -> float:
        """Get target zone setpoint for given hour and day.

        Args:
            hour: Hour of day (0-23)
            day_of_week: Day of week (0=Monday, 6=Sunday)

        Returns:
            Target setpoint in deg C (comfort + offset)
        """
        state = self.get_state(hour, day_of_week)
        return self.COMFORT_SETPOINT + state.setpoint_offset
