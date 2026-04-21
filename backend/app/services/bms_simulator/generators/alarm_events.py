"""
Alarm Event Generator

Generates realistic alarm events based on equipment types, thresholds,
and degradation patterns.
"""

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from ..models import (
    EQUIPMENT_ALARM_PROFILES,
    SimulationConfig,
)
from ..patterns.degradation import DegradationPattern
from .point_list import PointListExporter


@dataclass
class AlarmEvent:
    """Represents a single alarm event."""

    timestamp: str
    equipment_id: str
    equipment_type: str
    alarm_code: str
    severity: str
    description: str
    point_name: str | None = None
    point_value: float | None = None
    threshold_value: float | None = None
    acknowledged: bool = False
    acknowledged_by: str | None = None
    acknowledged_at: str | None = None
    cleared: bool = False
    cleared_at: str | None = None
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary, excluding None values."""
        return {k: v for k, v in asdict(self).items() if v is not None}


class AlarmEventGenerator:
    """Generates alarm events for BMS equipment."""

    # Base paths
    DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"
    OUTPUT_DIR = DATA_DIR / "bms_simulator" / "alarms"

    # Alarm code descriptions
    ALARM_DESCRIPTIONS = {
        "VIB_WARN": "Compressor vibration warning - monitor closely",
        "VIB_HIGH": "Compressor vibration high - schedule maintenance",
        "VIB_CRIT": "Compressor vibration critical - immediate attention required",
        "TEMP_HI": "Temperature exceeds high limit",
        "TEMP_LO": "Temperature below low limit",
        "PRESS_HI": "Pressure exceeds high limit",
        "PRESS_LO": "Pressure below low limit",
        "MOTOR_OVL": "Motor overload detected",
        "FILTER_DP": "Filter differential pressure high - filter change required",
        "FAN_FAIL": "Fan failure detected",
        "VALVE_STUCK": "Valve stuck or unresponsive",
        "DAMPER_FAIL": "Damper actuator failure",
        "FLOW_LO": "Airflow below minimum setpoint",
        "FLOW_HI": "Airflow above maximum setpoint",
        "CO2_HI": "CO2 level exceeds threshold",
        "DETECTOR_FAULT": "Smoke detector fault",
        "BATTERY_LOW": "Battery voltage low",
        "TAMPER": "Tamper alarm activated",
        "COMM_FAIL": "Communication failure",
        "REFRIGERANT_LO": "Refrigerant level low",
    }

    def __init__(self, config: SimulationConfig | None = None):
        """
        Initialize the alarm event generator.

        Args:
            config: Simulation configuration
        """
        self.config = config or SimulationConfig()
        self.point_exporter = PointListExporter(config)
        self.degradation = DegradationPattern(seed=self.config.seed)
        self.rng = np.random.default_rng(self.config.seed)

    def generate_threshold_alarms(
        self,
        device: dict[str, Any],
        trend_data: dict[str, np.ndarray],
        timestamps: np.ndarray,
    ) -> list[AlarmEvent]:
        """
        Generate alarms when point values exceed thresholds.

        Args:
            device: Device definition
            trend_data: Dictionary of point name to value arrays
            timestamps: Array of timestamps

        Returns:
            List of alarm events
        """
        device_id = device.get("id", "")
        device_type = device.get("hvac_type", device.get("device_type", "unknown"))
        points = device.get("points", {})

        alarms = []

        for point_name, values in trend_data.items():
            point_def = points.get(point_name, {})

            # Check for threshold violations
            min_val = point_def.get("min_value")
            max_val = point_def.get("max_value")
            metadata = point_def.get("metadata", {})
            alarm_threshold = metadata.get("alarm_threshold")
            critical_threshold = metadata.get("critical_threshold")

            for i, (ts, val) in enumerate(zip(timestamps, values, strict=False)):
                # Skip if in existing alarm state (avoid duplicate alarms)
                prev_val = values[i - 1] if i > 0 else val

                # High threshold alarm
                if max_val is not None and val > max_val:
                    if prev_val <= max_val:  # New alarm
                        alarm = self._create_threshold_alarm(
                            timestamp=ts,
                            equipment_id=device_id,
                            equipment_type=device_type,
                            point_name=point_name,
                            value=val,
                            threshold=max_val,
                            alarm_type="high",
                        )
                        alarms.append(alarm)

                # Low threshold alarm
                elif min_val is not None and val < min_val:
                    if prev_val >= min_val:  # New alarm
                        alarm = self._create_threshold_alarm(
                            timestamp=ts,
                            equipment_id=device_id,
                            equipment_type=device_type,
                            point_name=point_name,
                            value=val,
                            threshold=min_val,
                            alarm_type="low",
                        )
                        alarms.append(alarm)

                # Custom alarm threshold
                elif alarm_threshold is not None and val > alarm_threshold:
                    if prev_val <= alarm_threshold:
                        severity = "critical" if critical_threshold and val > critical_threshold else "warning"
                        alarm = AlarmEvent(
                            timestamp=ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
                            equipment_id=device_id,
                            equipment_type=device_type,
                            alarm_code=f"{point_name.upper()}_HI",
                            severity=severity,
                            description=f"{point_name} exceeds threshold",
                            point_name=point_name,
                            point_value=float(val),
                            threshold_value=alarm_threshold,
                        )
                        alarms.append(alarm)

        return alarms

    def _create_threshold_alarm(
        self,
        timestamp: datetime,
        equipment_id: str,
        equipment_type: str,
        point_name: str,
        value: float,
        threshold: float,
        alarm_type: str,
    ) -> AlarmEvent:
        """Create a threshold-based alarm event."""
        code_suffix = "HI" if alarm_type == "high" else "LO"
        alarm_code = f"{point_name.upper()}_{code_suffix}"

        # Determine severity based on how much over threshold
        deviation = abs(value - threshold) / abs(threshold) if threshold != 0 else 0
        severity = "critical" if deviation > 0.2 else "warning"

        return AlarmEvent(
            timestamp=timestamp.isoformat() if hasattr(timestamp, "isoformat") else str(timestamp),
            equipment_id=equipment_id,
            equipment_type=equipment_type,
            alarm_code=alarm_code,
            severity=severity,
            description=self.ALARM_DESCRIPTIONS.get(alarm_code, f"{point_name} {alarm_type} alarm"),
            point_name=point_name,
            point_value=float(value),
            threshold_value=float(threshold),
        )

    def generate_degradation_alarms(
        self,
        equipment_id: str,
        equipment_type: str,
        start_date: datetime,
        days: int,
    ) -> list[AlarmEvent]:
        """
        Generate alarm sequence for degrading equipment.

        Simulates typical fault progression:
        1. Early warning
        2. Warning level
        3. High severity
        4. Critical / imminent failure

        Args:
            equipment_id: Equipment identifier
            equipment_type: Type of equipment
            start_date: Start date for simulation
            days: Number of days to simulate

        Returns:
            List of alarm events in progression order
        """
        alarms = []

        # Get alarm profile for equipment type
        profile = EQUIPMENT_ALARM_PROFILES.get(equipment_type, [])
        if not profile:
            return alarms

        # Generate degradation factors
        _, raw_alarms = self.degradation.generate_fault_sequence(
            equipment_id=equipment_id,
            equipment_type=equipment_type,
            start_date=start_date,
            days=days,
            interval_minutes=self.config.interval_minutes,
        )

        # Convert to AlarmEvent objects
        alarm_sequence = [a["code"] for a in profile if a.get("code")]

        for _i, raw_alarm in enumerate(raw_alarms):
            # Determine which alarm code based on threshold index
            alarm_idx = min(raw_alarm.get("threshold_index", 0), len(alarm_sequence) - 1)
            alarm_info = profile[alarm_idx] if alarm_idx < len(profile) else profile[-1]

            alarm = AlarmEvent(
                timestamp=raw_alarm["timestamp"],
                equipment_id=equipment_id,
                equipment_type=equipment_type,
                alarm_code=alarm_info.get("code", "DEGRADATION"),
                severity=alarm_info.get("severity", "warning"),
                description=alarm_info.get("description", "Equipment degradation detected"),
                point_name=alarm_info.get("trigger_point"),
                notes=f"Degradation: {raw_alarm.get('degradation_pct', 0):.1f}%",
            )
            alarms.append(alarm)

        return alarms

    def generate_random_alarms(
        self,
        device: dict[str, Any],
        timestamps: np.ndarray,
        alarm_probability: float = 0.001,
    ) -> list[AlarmEvent]:
        """
        Generate random sporadic alarms (transient faults, communication issues).

        Args:
            device: Device definition
            timestamps: Array of timestamps
            alarm_probability: Probability of alarm per interval

        Returns:
            List of random alarm events
        """
        device_id = device.get("id", "")
        device_type = device.get("hvac_type", device.get("device_type", "unknown"))

        # Get possible alarm codes for this device type
        profile = EQUIPMENT_ALARM_PROFILES.get(device_type, [])
        if not profile:
            return []

        alarms = []

        for ts in timestamps:
            if self.rng.random() < alarm_probability:
                # Pick a random alarm from profile
                alarm_info = self.rng.choice(profile)

                # Most random alarms should be transient (cleared quickly)
                cleared = self.rng.random() > 0.3

                alarm = AlarmEvent(
                    timestamp=ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
                    equipment_id=device_id,
                    equipment_type=device_type,
                    alarm_code=alarm_info.get("code", "TRANSIENT"),
                    severity=alarm_info.get("severity", "warning"),
                    description=alarm_info.get("description", "Transient alarm"),
                    point_name=alarm_info.get("trigger_point"),
                    cleared=cleared,
                    cleared_at=(ts + timedelta(minutes=int(self.rng.integers(5, 60)))).isoformat() if cleared else None,
                    notes="Transient fault - auto-cleared" if cleared else None,
                )
                alarms.append(alarm)

        return alarms

    def generate_all_alarms(
        self,
        site_id: str | None = None,
        include_diffusers: bool = True,
        include_random: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Generate all alarms for a site.

        Args:
            site_id: Site ID to generate alarms for
            include_diffusers: Include generated Rickard diffusers
            include_random: Include random sporadic alarms

        Returns:
            List of alarm event dictionaries
        """
        site_id = site_id or self.config.site_id

        # Load devices
        devices = self.point_exporter.load_devices(site_id)
        if include_diffusers:
            diffusers = self.point_exporter.generate_diffusers(site_id)
            devices = devices + diffusers

        # Generate timestamps
        start = datetime.combine(self.config.start_date, datetime.min.time())
        n_intervals = self.config.days * 24 * 60 // self.config.interval_minutes
        timestamps = np.array([start + timedelta(minutes=i * self.config.interval_minutes) for i in range(n_intervals)])

        all_alarms = []

        for device in devices:
            device_id = device.get("id", "")
            device_type = device.get("hvac_type", device.get("device_type", "unknown"))

            # Generate degradation alarms for specified equipment
            if device_id in self.config.degradation_equipment:
                deg_alarms = self.generate_degradation_alarms(
                    equipment_id=device_id,
                    equipment_type=device_type,
                    start_date=start,
                    days=self.config.days,
                )
                all_alarms.extend([a.to_dict() for a in deg_alarms])

            # Generate random alarms if requested
            if include_random:
                random_alarms = self.generate_random_alarms(
                    device=device,
                    timestamps=timestamps,
                    alarm_probability=0.0002,  # Low probability
                )
                all_alarms.extend([a.to_dict() for a in random_alarms])

        # Sort by timestamp
        all_alarms.sort(key=lambda x: x.get("timestamp", ""))

        return all_alarms

    def export_alarms(
        self,
        site_id: str | None = None,
        output_path: Path | None = None,
    ) -> str:
        """
        Export all alarms to JSON file.

        Args:
            site_id: Site ID to generate alarms for
            output_path: Custom output path

        Returns:
            Output file path
        """
        site_id = site_id or self.config.site_id
        alarms = self.generate_all_alarms(site_id)

        # Determine output path
        if output_path is None:
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"alarms_{site_id}_{timestamp_str}.json"
            output_path = self.OUTPUT_DIR / filename

        # Ensure directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Write JSON
        with open(output_path, "w") as f:
            json.dump(alarms, f, indent=2)

        return str(output_path)

    def get_alarm_summary(
        self,
        alarms: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Get summary statistics for generated alarms.

        Args:
            alarms: List of alarm dictionaries

        Returns:
            Summary statistics
        """
        summary = {
            "total_alarms": len(alarms),
            "by_severity": {},
            "by_equipment_type": {},
            "by_alarm_code": {},
            "cleared_count": 0,
            "acknowledged_count": 0,
        }

        for alarm in alarms:
            # By severity
            sev = alarm.get("severity", "unknown")
            summary["by_severity"][sev] = summary["by_severity"].get(sev, 0) + 1

            # By equipment type
            eq_type = alarm.get("equipment_type", "unknown")
            summary["by_equipment_type"][eq_type] = summary["by_equipment_type"].get(eq_type, 0) + 1

            # By alarm code
            code = alarm.get("alarm_code", "unknown")
            summary["by_alarm_code"][code] = summary["by_alarm_code"].get(code, 0) + 1

            # Counts
            if alarm.get("cleared"):
                summary["cleared_count"] += 1
            if alarm.get("acknowledged"):
                summary["acknowledged_count"] += 1

        return summary

    # ============================================================
    # Hospital-specific alarm scenario generators
    # ============================================================

    def generate_cold_room_excursion_scenario(
        self,
        equipment_id: str = "UMH-COLD-L1-001",
        start_date: datetime | None = None,
    ) -> list[AlarmEvent]:
        """
        Generate pharmacy cold room temperature excursion scenario.

        Simulates a gradual temperature rise due to compressor degradation,
        leading to vaccine storage compromise warning.

        Sequence:
        1. T+0h: TEMP_HI warning at 6.5C
        2. T+2h: Temperature continues rising
        3. T+4h: TEMP_CRIT at 8.5C (vaccine storage compromised)
        4. T+5h: Technician responds, compressor serviced
        5. T+8h: Temperature returns to normal, alarms cleared

        Args:
            equipment_id: Cold room equipment ID
            start_date: Scenario start datetime

        Returns:
            List of alarm events
        """
        if start_date is None:
            start_date = datetime.combine(self.config.start_date, datetime.min.time())
            start_date = start_date.replace(hour=3)  # 3 AM - worst case

        alarms = []

        # T+0h: TEMP_HI warning
        alarms.append(
            AlarmEvent(
                timestamp=(start_date).isoformat(),
                equipment_id=equipment_id,
                equipment_type="cold_room",
                alarm_code="TEMP_HI",
                severity="warning",
                description="Cold room temperature high - check compressor",
                point_name="cabinet_temp",
                point_value=6.5,
                threshold_value=6.0,
                notes="Temperature rising above normal range",
            )
        )

        # T+4h: TEMP_CRIT critical
        alarms.append(
            AlarmEvent(
                timestamp=(start_date + timedelta(hours=4)).isoformat(),
                equipment_id=equipment_id,
                equipment_type="cold_room",
                alarm_code="TEMP_CRIT",
                severity="critical",
                description="Cold room temperature critical - vaccine storage compromised",
                point_name="cabinet_temp",
                point_value=8.5,
                threshold_value=8.0,
                notes="URGENT: Vaccine cold chain at risk",
            )
        )

        # T+5h: Technician response - alarm acknowledged
        alarms.append(
            AlarmEvent(
                timestamp=(start_date + timedelta(hours=5)).isoformat(),
                equipment_id=equipment_id,
                equipment_type="cold_room",
                alarm_code="TEMP_CRIT",
                severity="critical",
                description="Cold room temperature critical - vaccine storage compromised",
                point_name="cabinet_temp",
                point_value=8.2,
                threshold_value=8.0,
                acknowledged=True,
                acknowledged_by="Maintenance Tech",
                acknowledged_at=(start_date + timedelta(hours=5)).isoformat(),
                notes="Technician on site, compressor being serviced",
            )
        )

        # T+8h: Alarms cleared
        alarms.append(
            AlarmEvent(
                timestamp=(start_date + timedelta(hours=8)).isoformat(),
                equipment_id=equipment_id,
                equipment_type="cold_room",
                alarm_code="TEMP_HI",
                severity="warning",
                description="Cold room temperature high - check compressor",
                point_name="cabinet_temp",
                point_value=4.5,
                threshold_value=6.0,
                acknowledged=True,
                cleared=True,
                cleared_at=(start_date + timedelta(hours=8)).isoformat(),
                notes="Compressor repaired, temperature returned to normal",
            )
        )

        return alarms

    def generate_chiller_cascade_scenario(
        self,
        equipment_ids: list[str] | None = None,
        start_date: datetime | None = None,
    ) -> list[AlarmEvent]:
        """
        Generate dual chiller failure risk scenario.

        Simulates N+1 redundancy being tested when lead chiller trips
        and lag chiller is already degraded.

        Sequence:
        1. T+0h: Chiller 1 VIB_WARN
        2. T+2h: Chiller 1 trips (VIB_CRIT)
        3. T+2h: Chiller 2 takes full load
        4. T+3h: Chiller 2 TEMP_HI (struggling with load)
        5. T+4h: Theatre cooling at risk alert
        6. T+6h: Chiller 1 repaired, load shared

        Args:
            equipment_ids: List of chiller IDs [primary, backup]
            start_date: Scenario start datetime

        Returns:
            List of alarm events
        """
        if equipment_ids is None:
            equipment_ids = ["UMH-CHILLER-B1-001", "UMH-CHILLER-B1-002"]
        if start_date is None:
            start_date = datetime.combine(self.config.start_date, datetime.min.time())
            start_date = start_date.replace(hour=14)  # Peak cooling demand

        alarms = []
        ch1, ch2 = equipment_ids[0], equipment_ids[1]

        # T+0h: Chiller 1 VIB_WARN
        alarms.append(
            AlarmEvent(
                timestamp=start_date.isoformat(),
                equipment_id=ch1,
                equipment_type="chiller",
                alarm_code="VIB_WARN",
                severity="warning",
                description="Compressor vibration warning - monitor closely",
                point_name="compressor_amps",
                point_value=220,
                threshold_value=200,
                notes="Vibration trending upward over past week",
            )
        )

        # T+2h: Chiller 1 trips
        alarms.append(
            AlarmEvent(
                timestamp=(start_date + timedelta(hours=2)).isoformat(),
                equipment_id=ch1,
                equipment_type="chiller",
                alarm_code="VIB_CRIT",
                severity="critical",
                description="Compressor vibration critical - unit tripped",
                point_name="compressor_amps",
                point_value=0,
                threshold_value=260,
                notes="Chiller 1 offline - Chiller 2 taking full load",
            )
        )

        # T+3h: Chiller 2 struggling
        alarms.append(
            AlarmEvent(
                timestamp=(start_date + timedelta(hours=3)).isoformat(),
                equipment_id=ch2,
                equipment_type="chiller",
                alarm_code="TEMP_HI",
                severity="warning",
                description="Chilled water temperature high",
                point_name="chw_supply_temp",
                point_value=8.5,
                threshold_value=7.5,
                notes="Single chiller unable to meet full building load",
            )
        )

        # T+4h: Theatre cooling risk
        alarms.append(
            AlarmEvent(
                timestamp=(start_date + timedelta(hours=4)).isoformat(),
                equipment_id="UMH-AHU-L3-TH1",
                equipment_type="theatre_ahu",
                alarm_code="TEMP_HI",
                severity="critical",
                description="Theatre supply air temperature high - surgery at risk",
                point_name="supply_air_temp",
                point_value=21.5,
                threshold_value=20.0,
                notes="URGENT: Surgical environment compromised",
            )
        )

        # T+6h: Resolution
        alarms.append(
            AlarmEvent(
                timestamp=(start_date + timedelta(hours=6)).isoformat(),
                equipment_id=ch1,
                equipment_type="chiller",
                alarm_code="VIB_CRIT",
                severity="critical",
                description="Compressor vibration critical - unit tripped",
                acknowledged=True,
                acknowledged_by="Senior Tech",
                acknowledged_at=(start_date + timedelta(hours=3)).isoformat(),
                cleared=True,
                cleared_at=(start_date + timedelta(hours=6)).isoformat(),
                notes="Bearing replaced, chiller back online",
            )
        )

        return alarms

    def generate_theatre_hepa_life_scenario(
        self,
        equipment_id: str = "UMH-AHU-L3-TH2",
        start_date: datetime | None = None,
        days: int = 90,
    ) -> list[AlarmEvent]:
        """
        Generate HEPA filter lifecycle trending scenario.

        Shows gradual filter loading over 90 days with predictive alerts.

        Sequence:
        1. Day 30: Prefilter DP trending high
        2. Day 60: HEPA_DP_HI warning
        3. Day 75: HEPA_DP approaching critical
        4. Day 85: HEPA_DP_CRIT - replacement scheduled
        5. Day 90: Filters replaced, alarms cleared

        Args:
            equipment_id: Theatre AHU equipment ID
            start_date: Scenario start datetime
            days: Duration of scenario in days

        Returns:
            List of alarm events
        """
        if start_date is None:
            start_date = datetime.combine(self.config.start_date, datetime.min.time())

        alarms = []

        # Day 30: Prefilter trending
        alarms.append(
            AlarmEvent(
                timestamp=(start_date + timedelta(days=30)).isoformat(),
                equipment_id=equipment_id,
                equipment_type="theatre_ahu",
                alarm_code="FILTER_DP",
                severity="info",
                description="Prefilter DP trending upward - schedule inspection",
                point_name="prefilter_dp",
                point_value=180,
                threshold_value=200,
                notes="ML prediction: HEPA replacement in 60 days",
            )
        )

        # Day 60: HEPA_DP_HI
        alarms.append(
            AlarmEvent(
                timestamp=(start_date + timedelta(days=60)).isoformat(),
                equipment_id=equipment_id,
                equipment_type="theatre_ahu",
                alarm_code="HEPA_DP_HI",
                severity="warning",
                description="HEPA filter DP high - schedule replacement",
                point_name="hepa_dp",
                point_value=380,
                threshold_value=350,
                notes="Filter loading at 75% - order replacement filters",
            )
        )

        # Day 75: Approaching critical
        alarms.append(
            AlarmEvent(
                timestamp=(start_date + timedelta(days=75)).isoformat(),
                equipment_id=equipment_id,
                equipment_type="theatre_ahu",
                alarm_code="HEPA_DP_HI",
                severity="warning",
                description="HEPA filter DP high - replacement overdue",
                point_name="hepa_dp",
                point_value=420,
                threshold_value=350,
                notes="URGENT: Schedule filter change this week",
            )
        )

        # Day 85: Critical
        alarms.append(
            AlarmEvent(
                timestamp=(start_date + timedelta(days=85)).isoformat(),
                equipment_id=equipment_id,
                equipment_type="theatre_ahu",
                alarm_code="HEPA_DP_CRIT",
                severity="critical",
                description="HEPA filter DP critical - replace immediately",
                point_name="hepa_dp",
                point_value=480,
                threshold_value=450,
                notes="Filter change scheduled for tomorrow between surgeries",
            )
        )

        # Day 90: Resolved
        alarms.append(
            AlarmEvent(
                timestamp=(start_date + timedelta(days=90)).isoformat(),
                equipment_id=equipment_id,
                equipment_type="theatre_ahu",
                alarm_code="HEPA_DP_HI",
                severity="warning",
                cleared=True,
                cleared_at=(start_date + timedelta(days=90)).isoformat(),
                description="HEPA filter replaced",
                point_name="hepa_dp",
                point_value=180,
                notes="New filters installed, DP returned to baseline",
            )
        )

        return alarms

    def generate_generator_fuel_scenario(
        self,
        equipment_id: str = "UMH-GEN-B1-001",
        start_date: datetime | None = None,
    ) -> list[AlarmEvent]:
        """
        Generate fuel vs load shedding duration correlation scenario.

        Simulates fuel consumption during extended load shedding events.

        Sequence:
        1. T+0h: Load shedding starts, generator online
        2. T+2h: Fuel at 70% (normal consumption)
        3. T+4h: Stage 6 continues, FUEL_LO at 45%
        4. T+5h: FUEL_CRIT at 25%
        5. T+6h: Mains restored, generator cooling down
        6. T+8h: Fuel truck arrives

        Args:
            equipment_id: Generator equipment ID
            start_date: Scenario start datetime

        Returns:
            List of alarm events
        """
        if start_date is None:
            start_date = datetime.combine(self.config.start_date, datetime.min.time())
            start_date = start_date.replace(hour=18)  # Evening load shedding

        alarms = []

        # T+0h: Generator starts
        alarms.append(
            AlarmEvent(
                timestamp=start_date.isoformat(),
                equipment_id=equipment_id,
                equipment_type="generator",
                alarm_code="ON_GENERATOR",
                severity="info",
                description="Generator online - load shedding stage 6",
                point_name="status",
                point_value=2,  # Running
                notes="Fuel level 85%, estimated runtime 8 hours",
            )
        )

        # T+4h: FUEL_LO
        alarms.append(
            AlarmEvent(
                timestamp=(start_date + timedelta(hours=4)).isoformat(),
                equipment_id=equipment_id,
                equipment_type="generator",
                alarm_code="FUEL_LO",
                severity="warning",
                description="Fuel level low",
                point_name="fuel_level",
                point_value=45,
                threshold_value=50,
                notes="Extended load shedding - fuel truck on standby",
            )
        )

        # T+5h: FUEL_CRIT
        alarms.append(
            AlarmEvent(
                timestamp=(start_date + timedelta(hours=5)).isoformat(),
                equipment_id=equipment_id,
                equipment_type="generator",
                alarm_code="FUEL_CRIT",
                severity="critical",
                description="Fuel level critical",
                point_name="fuel_level",
                point_value=25,
                threshold_value=30,
                notes="URGENT: Fuel truck dispatched, ETA 30 min",
            )
        )

        # T+6h: Mains restored
        alarms.append(
            AlarmEvent(
                timestamp=(start_date + timedelta(hours=6)).isoformat(),
                equipment_id=equipment_id,
                equipment_type="generator",
                alarm_code="FUEL_CRIT",
                severity="critical",
                cleared=True,
                cleared_at=(start_date + timedelta(hours=6)).isoformat(),
                description="Mains restored, generator cooling down",
                point_name="fuel_level",
                point_value=18,
                notes="Generator ran for 6 hours, fuel at 18%",
            )
        )

        return alarms

    def generate_icu_humidity_scenario(
        self,
        equipment_id: str = "UMH-AHU-L3-ICU",
        start_date: datetime | None = None,
    ) -> list[AlarmEvent]:
        """
        Generate ICU humidity excursion during Durban summer scenario.

        Simulates high outdoor humidity overwhelming dehumidification.

        Sequence:
        1. T+0h: Outdoor humidity 95%, building struggling
        2. T+1h: HUMIDITY_HI warning at 62%
        3. T+3h: Humidity reaches 68%
        4. T+4h: Cooling coil mode adjusted, reheat enabled
        5. T+6h: Humidity controlled, alarm cleared

        Args:
            equipment_id: ICU AHU equipment ID
            start_date: Scenario start datetime

        Returns:
            List of alarm events
        """
        if start_date is None:
            start_date = datetime.combine(self.config.start_date, datetime.min.time())
            start_date = start_date.replace(hour=10, month=1)  # Summer morning

        alarms = []

        # T+1h: HUMIDITY_HI
        alarms.append(
            AlarmEvent(
                timestamp=(start_date + timedelta(hours=1)).isoformat(),
                equipment_id=equipment_id,
                equipment_type="theatre_ahu",
                alarm_code="HUMIDITY_HI",
                severity="warning",
                description="ICU supply humidity high",
                point_name="supply_humidity",
                point_value=62,
                threshold_value=60,
                notes="Outdoor humidity 95%RH - dehumidification at max",
            )
        )

        # T+3h: Still high
        alarms.append(
            AlarmEvent(
                timestamp=(start_date + timedelta(hours=3)).isoformat(),
                equipment_id=equipment_id,
                equipment_type="theatre_ahu",
                alarm_code="HUMIDITY_HI",
                severity="warning",
                description="ICU humidity still elevated",
                point_name="supply_humidity",
                point_value=68,
                threshold_value=60,
                notes="Adjusting cooling coil discharge temp",
            )
        )

        # T+4h: Action taken
        alarms.append(
            AlarmEvent(
                timestamp=(start_date + timedelta(hours=4)).isoformat(),
                equipment_id=equipment_id,
                equipment_type="theatre_ahu",
                alarm_code="HUMIDITY_HI",
                severity="warning",
                acknowledged=True,
                acknowledged_by="BMS Operator",
                acknowledged_at=(start_date + timedelta(hours=4)).isoformat(),
                description="Humidity control adjusted",
                point_name="supply_humidity",
                point_value=63,
                notes="Reheat enabled, overcooling for dehumidification",
            )
        )

        # T+6h: Resolved
        alarms.append(
            AlarmEvent(
                timestamp=(start_date + timedelta(hours=6)).isoformat(),
                equipment_id=equipment_id,
                equipment_type="theatre_ahu",
                alarm_code="HUMIDITY_HI",
                severity="warning",
                acknowledged=True,
                cleared=True,
                cleared_at=(start_date + timedelta(hours=6)).isoformat(),
                description="Humidity returned to setpoint",
                point_name="supply_humidity",
                point_value=55,
                notes="Dehumidification successful with adjusted strategy",
            )
        )

        return alarms

    def generate_scenario_alarms(
        self,
        scenario: str,
        **kwargs,
    ) -> list[dict[str, Any]]:
        """
        Generate alarms for a named scenario.

        Args:
            scenario: Scenario name (cold-room-excursion, chiller-cascade, etc.)
            **kwargs: Additional arguments for the scenario

        Returns:
            List of alarm event dictionaries
        """
        scenario_map = {
            "cold-room-excursion": self.generate_cold_room_excursion_scenario,
            "chiller-cascade": self.generate_chiller_cascade_scenario,
            "theatre-hepa-life": self.generate_theatre_hepa_life_scenario,
            "generator-fuel": self.generate_generator_fuel_scenario,
            "icu-humidity": self.generate_icu_humidity_scenario,
        }

        generator = scenario_map.get(scenario)
        if generator is None:
            raise ValueError(f"Unknown scenario: {scenario}. Available: {list(scenario_map.keys())}")

        alarms = generator(**kwargs)
        return [a.to_dict() for a in alarms]
