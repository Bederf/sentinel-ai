"""Grid Parameters Service — ingests grid readings and routes to monitoring engines.

Aggregates frequency and voltage readings from:
  - BESS meter (primary source for real-time frequency)
  - Grid meter (import/export, frequency, voltage)
  - Inverter AC output (voltage, frequency, power)

Feeds readings to:
  - MonitoringEngine (compliance validation every 10 seconds)
  - LoadShedScheduler (stage detection every 2 seconds)
  - Dashboard APIs (real-time and trending)

Pattern follows solar_ingestion_service.py and solar_performance_service.py.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple

from app.models.solar import (
    GridMeter,
)
from app.services.solar_ingestion_service import get_solar_ingestion_service
from app.services.grid_compliance_service import (
    GridParameters,
    get_monitoring_engine,
    get_load_shed_scheduler,
)

logger = logging.getLogger(__name__)


class GridParametersService:
    """Manages grid parameter collection and distribution to monitoring engines."""

    def __init__(self):
        self.current_frequency_hz = 50.0
        self.current_voltage_v = 400.0
        self.current_power_kw = 0.0
        self.previous_power_kw = 0.0
        self.last_reading_time = datetime.now(timezone.utc)
        self.reading_history: List[Dict[str, Any]] = []
        self.max_history_length = 1440  # Keep 24 hours at 1-minute intervals

    async def poll_grid_meter(self, site_id: str) -> Optional[GridMeter]:
        """Poll solar grid meter for frequency, voltage, current."""
        try:
            ingestion_svc = get_solar_ingestion_service()
            meter = await ingestion_svc.get_grid_meter(site_id)

            if meter:
                self.current_frequency_hz = meter.frequency_hz
                self.current_voltage_v = meter.voltage_v
                self.last_reading_time = datetime.now(timezone.utc)

                logger.debug(f"Grid meter update: {self.current_frequency_hz} Hz, {self.current_voltage_v} V")

            return meter
        except Exception as e:
            logger.error(f"Failed to poll grid meter: {e}")
            return None

    async def poll_inverter_readings(self, site_id: str) -> Optional[Dict[str, Any]]:
        """Poll inverter AC output for frequency, voltage, power."""
        try:
            ingestion_svc = get_solar_ingestion_service()
            inverters = await ingestion_svc.get_inverters(site_id)

            if not inverters:
                return None

            # Aggregate readings from all inverters
            total_power_kw = 0.0
            avg_frequency_hz = 0.0
            avg_voltage_v = 0.0

            for inv in inverters:
                total_power_kw += inv.ac_power_kw
                avg_frequency_hz += inv.frequency_hz
                avg_voltage_v += getattr(inv, "voltage_v", 400.0)

            count = len(inverters)
            if count > 0:
                self.previous_power_kw = self.current_power_kw
                self.current_power_kw = total_power_kw
                self.current_frequency_hz = avg_frequency_hz / count
                self.current_voltage_v = avg_voltage_v / count
                self.last_reading_time = datetime.now(timezone.utc)

                logger.debug(f"Inverter update: {self.current_power_kw} kW, {self.current_frequency_hz} Hz")

            return {
                "ac_power_kw": self.current_power_kw,
                "frequency_hz": self.current_frequency_hz,
                "voltage_v": self.current_voltage_v,
                "inverter_count": count,
            }

        except Exception as e:
            logger.error(f"Failed to poll inverter readings: {e}")
            return None

    async def get_grid_parameters(self) -> GridParameters:
        """Get current grid parameters for compliance monitoring.

        Returns:
            GridParameters object with current frequency, voltage, power
        """
        now = datetime.now(timezone.utc)
        time_delta = (now - self.last_reading_time).total_seconds() if self.last_reading_time else 1.0

        params = GridParameters(
            timestamp=now.isoformat(),
            frequency_hz=self.current_frequency_hz,
            voltage_v=self.current_voltage_v,
            ac_power_kw=self.current_power_kw,
            previous_power_kw=self.previous_power_kw,
            time_delta_seconds=max(time_delta, 0.1),
        )

        return params

    async def check_compliance(self, site_id: str) -> Dict[str, Any]:
        """Poll grid meter and run compliance check.

        Returns:
            Compliance status with violations and actions
        """
        # Poll latest readings
        await self.poll_grid_meter(site_id)
        await self.poll_inverter_readings(site_id)

        # Get grid parameters
        params = await self.get_grid_parameters()

        # Run compliance validation
        engine = get_monitoring_engine()
        status = await engine.validate(params)

        # Record to history
        self._record_to_history(params, status)

        logger.info(
            f"Compliance check: {status.grid_code} - "
            f"Compliant={status.compliant}, Violations={len(status.active_violations)}"
        )

        return status.to_dict()

    async def detect_load_shedding(self) -> Tuple[int, Optional[Dict[str, Any]]]:
        """Detect current load shedding stage.

        Returns:
            Tuple of (stage_number, transition_event_dict_if_changed)
        """
        # Get latest frequency
        params = await self.get_grid_parameters()

        # Detect stage
        scheduler = get_load_shed_scheduler()
        stage, event = await scheduler.detect_stage(params.frequency_hz)

        if event:
            logger.info(f"Load shedding stage changed to {stage}")
            return stage, event.to_dict()

        return stage, None

    def _record_to_history(self, params: GridParameters, status: Dict[str, Any]) -> None:
        """Record reading to history for trending."""
        record = {
            "timestamp": params.timestamp,
            "frequency_hz": params.frequency_hz,
            "voltage_v": params.voltage_v,
            "ac_power_kw": params.ac_power_kw,
            "violations_count": len(status.get("active_violations", [])),
        }

        self.reading_history.append(record)

        # Prune old history
        if len(self.reading_history) > self.max_history_length:
            self.reading_history = self.reading_history[-self.max_history_length :]

    async def get_frequency_trend(self, window_minutes: int = 60) -> List[Dict[str, Any]]:
        """Get frequency readings over a time window.

        Args:
            window_minutes: Time window (5, 60, or 1440 for 24h)

        Returns:
            List of readings with timestamp and frequency
        """
        if not self.reading_history:
            return []

        # Filter to requested window
        filtered = []
        cutoff_records = max(1, window_minutes)  # 1 reading per minute

        for record in self.reading_history[-cutoff_records:]:
            filtered.append(
                {
                    "timestamp": record["timestamp"],
                    "frequency_hz": record["frequency_hz"],
                }
            )

        return filtered

    async def get_voltage_trend(self, window_minutes: int = 60) -> List[Dict[str, Any]]:
        """Get voltage readings over a time window.

        Args:
            window_minutes: Time window (5, 60, or 1440 for 24h)

        Returns:
            List of readings with timestamp and voltage
        """
        if not self.reading_history:
            return []

        filtered = []
        cutoff_records = max(1, window_minutes)

        for record in self.reading_history[-cutoff_records:]:
            filtered.append(
                {
                    "timestamp": record["timestamp"],
                    "voltage_v": record["voltage_v"],
                }
            )

        return filtered

    async def get_power_trend(self, window_minutes: int = 60) -> List[Dict[str, Any]]:
        """Get power readings over a time window.

        Args:
            window_minutes: Time window (5, 60, or 1440 for 24h)

        Returns:
            List of readings with timestamp and power
        """
        if not self.reading_history:
            return []

        filtered = []
        cutoff_records = max(1, window_minutes)

        for record in self.reading_history[-cutoff_records:]:
            filtered.append(
                {
                    "timestamp": record["timestamp"],
                    "ac_power_kw": record["ac_power_kw"],
                }
            )

        return filtered


# === Singleton accessor ===

_grid_parameters_service: Optional[GridParametersService] = None


def get_grid_parameters_service() -> GridParametersService:
    """Get or create GridParametersService singleton."""
    global _grid_parameters_service
    if _grid_parameters_service is None:
        _grid_parameters_service = GridParametersService()
    return _grid_parameters_service
