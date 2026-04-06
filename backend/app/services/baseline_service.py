"""
Baseline Service for Equipment and Element Baseline Management

Provides services for:
- Capturing equipment baselines
- Comparing current readings to baselines
- Element-level baseline tracking
- Deviation detection and alerting

Phase 44: Asset Baseline Assessment
"""

import logging
from datetime import datetime
from typing import Any

from app.database.repositories.baseline_repository import BaselineRepository
from app.models.baseline import (
    BaselineComparison,
    ComparisonResult,
    DeviationStatus,
    ElementBaseline,
    EquipmentBaseline,
)
from app.services.influxdb_service import get_influxdb_service

logger = logging.getLogger(__name__)


class BaselineService:
    """Service for equipment and element baseline operations."""

    def __init__(self):
        self.repository = BaselineRepository()
        self.influx_service = get_influxdb_service()

    async def capture_equipment_baseline(
        self,
        equipment_id: str,
        captured_by: str,
        baseline_type: str = "initial",
        notes: str | None = None,
        measurement_conditions: dict[str, Any] | None = None,
        source_type: str = "manual",
        attachment_urls: list[str] | None = None,
    ) -> EquipmentBaseline:
        """
        Capture a new baseline for equipment.

        For automated baselines, reads from BMS sensors.
        For manual baselines, expects baseline_values to be provided via API.

        Args:
            equipment_id: Equipment identifier
            captured_by: Engineer name or 'automated'
            baseline_type: initial, periodic, post_repair
            notes: Engineer notes
            measurement_conditions: Ambient conditions during measurement
            source_type: manual, bms_average, mobile_sensor
            attachment_urls: URLs to photos/documentation

        Returns:
            Created EquipmentBaseline record
        """
        # For automated capture, fetch current sensor values
        baseline_values = {}
        if source_type in ["bms_average", "automated"]:
            # Get average readings from last 24 hours
            baseline_values = await self._get_equipment_sensor_averages(equipment_id)

        baseline = await self.repository.create_equipment_baseline(
            equipment_id=equipment_id,
            captured_by=captured_by,
            baseline_type=baseline_type,
            baseline_values=baseline_values,
            measurement_conditions=measurement_conditions or {},
            source_type=source_type,
            notes=notes,
            attachment_urls=attachment_urls or [],
        )

        logger.info(f"Captured baseline for equipment {equipment_id}: {baseline.id}")
        return baseline

    async def capture_element_baseline(
        self,
        equipment_id: str,
        element_id: str,
        captured_by: str,
        measurement_type: str,
        baseline_type: str = "initial",
        baseline_values: dict[str, Any] | None = None,
        notes: str | None = None,
        measurement_conditions: dict[str, Any] | None = None,
        attachment_urls: list[str] | None = None,
    ) -> ElementBaseline:
        """
        Capture baseline for a specific element (bearing, filter, etc.).

        Args:
            equipment_id: Parent equipment identifier
            element_id: Element identifier (e.g., 'bearing_1')
            captured_by: Engineer name or sensor type
            measurement_type: vibration, temperature, visual_inspection
            baseline_type: initial, periodic, post_repair
            baseline_values: Measured values (e.g., {"vibration_rms": 1.2, "temp": 45.2})
            notes: Measurement notes
            measurement_conditions: Context (load, speed, ambient)
            attachment_urls: URLs to measurements/photos

        Returns:
            Created ElementBaseline record
        """
        # Get or create equipment element
        element = await self.repository.get_or_create_element(
            equipment_id=equipment_id, element_id=element_id, element_type=measurement_type
        )

        baseline = await self.repository.create_element_baseline(
            element_id=element.id,
            captured_by=captured_by,
            baseline_type=baseline_type,
            measurement_type=measurement_type,
            baseline_values=baseline_values or {},
            measurement_conditions=measurement_conditions or {},
            notes=notes,
            attachment_urls=attachment_urls or [],
        )

        logger.info(f"Captured baseline for element {element_id}: {baseline.id}")
        return baseline

    async def compare_to_baseline(
        self, equipment_id: str, current_values: dict[str, Any] | None = None, data_source: str = "bms_sensor"
    ) -> BaselineComparison:
        """
        Compare current readings to stored baseline and calculate deviations.

        Args:
            equipment_id: Equipment to compare
            current_values: Current sensor values (if None, fetch from BMS)
            data_source: Source of current values

        Returns:
            BaselineComparison with deviation analysis
        """
        # Get the active baseline for this equipment
        baseline = await self.repository.get_active_equipment_baseline(equipment_id)
        if not baseline:
            raise ValueError(f"No active baseline found for equipment {equipment_id}")

        # Get current values if not provided
        if current_values is None:
            current_values = await self._get_current_equipment_readings(equipment_id)

        # Perform comparison
        comparison_results = self._calculate_deviations(
            baseline_values=baseline.baseline_values, current_values=current_values
        )

        # Determine overall status
        overall_status, max_deviation = self._assess_overall_status(comparison_results)

        # Store comparison result
        comparison = await self.repository.create_baseline_comparison(
            comparison_type="equipment_baseline",
            baseline_id=baseline.id,
            equipment_id=equipment_id,
            comparison_results=comparison_results,
            overall_status=overall_status,
            max_deviation_percent=max_deviation,
            data_source=data_source,
        )

        # Generate alert if critical deviation
        if overall_status == "critical":
            await self._generate_deviation_alert(comparison)

        logger.info(f"Baseline comparison for {equipment_id}: {overall_status} ({max_deviation:.1f}% max deviation)")
        return comparison

    async def compare_element_to_baseline(
        self,
        equipment_id: str,
        element_id: str,
        current_values: dict[str, Any] | None = None,
        measurement_type: str = "vibration",
    ) -> BaselineComparison:
        """
        Compare element readings to baseline.

        Args:
            equipment_id: Parent equipment identifier
            element_id: Element identifier
            current_values: Current measurement values
            measurement_type: Type of measurement

        Returns:
            BaselineComparison for the element
        """
        # Get element and its active baseline
        element = await self.repository.get_element(equipment_id, element_id)
        if not element:
            raise ValueError(f"Element {element_id} not found for equipment {equipment_id}")

        baseline = await self.repository.get_active_element_baseline(element.id)
        if not baseline:
            raise ValueError(f"No active baseline found for element {element_id}")

        # Get current values if not provided
        if current_values is None:
            current_values = await self._get_current_element_readings(equipment_id, element_id, measurement_type)

        # Compare
        comparison_results = self._calculate_deviations(
            baseline_values=baseline.baseline_values, current_values=current_values
        )

        overall_status, max_deviation = self._assess_overall_status(comparison_results)

        # Store comparison
        comparison = await self.repository.create_baseline_comparison(
            comparison_type="element_baseline",
            baseline_id=baseline.id,
            equipment_id=equipment_id,
            element_id=element.id,
            comparison_results=comparison_results,
            overall_status=overall_status,
            max_deviation_percent=max_deviation,
            data_source=baseline.measurement_type,
        )

        return comparison

    def _calculate_deviations(
        self, baseline_values: dict[str, Any], current_values: dict[str, Any]
    ) -> dict[str, ComparisonResult]:
        """
        Calculate deviations between baseline and current values.

        Args:
            baseline_values: Baseline readings
            current_values: Current readings

        Returns:
            Dictionary of comparison results per metric
        """
        results = {}

        for metric_name, baseline_val in baseline_values.items():
            if metric_name not in current_values:
                continue

            current_val = current_values[metric_name]

            # Calculate deviation percentage
            if baseline_val != 0:
                deviation = abs((current_val - baseline_val) / baseline_val) * 100
            else:
                deviation = 0 if current_val == 0 else 100

            # Determine status based on deviation
            if deviation <= 10:
                status = DeviationStatus.NORMAL
            elif deviation <= 20:
                status = DeviationStatus.WARNING
            else:
                status = DeviationStatus.CRITICAL

            results[metric_name] = ComparisonResult(
                baseline=baseline_val, current=current_val, deviation_percent=round(deviation, 2), status=status
            )

        return results

    def _assess_overall_status(self, comparison_results: dict[str, ComparisonResult]) -> tuple[str, float]:
        """
        Determine overall status from comparison results.

        Returns:
            Tuple of (status, max_deviation_percent)
        """
        if not comparison_results:
            return "normal", 0.0

        # Find the worst status and maximum deviation
        status_priority = {"normal": 0, "warning": 1, "critical": 2}
        max_deviation = 0.0
        overall_status = "normal"

        for result in comparison_results.values():
            max_deviation = max(max_deviation, result.deviation_percent)
            if status_priority[result.status] > status_priority[overall_status]:
                overall_status = result.status

        return overall_status, max_deviation

    async def _get_equipment_sensor_averages(self, equipment_id: str) -> dict[str, float]:
        """Get 24-hour average readings from BMS sensors for baseline capture."""
        try:
            # Query InfluxDB for average values over last 24 hours
            query = f'''
                from(bucket: "sensor_data_raw")
                  |> range(start: -24h)
                  |> filter(fn: (r) => r.equipment_id == "{equipment_id}")
                  |> aggregateWindow(every: 24h, fn: mean, createEmpty: false)
            '''

            result = await self.influx_service.query(query)
            # Parse result and return as dict
            return self._parse_influx_result(result)

        except Exception as e:
            logger.error(f"Failed to get sensor averages for {equipment_id}: {e}")
            return {}

    async def _get_current_equipment_readings(self, equipment_id: str) -> dict[str, float]:
        """Get current sensor readings for equipment."""
        try:
            # Query InfluxDB for latest values
            query = f'''
                from(bucket: "sensor_data_raw")
                  |> range(start: -15m)
                  |> filter(fn: (r) => r.equipment_id == "{equipment_id}")
                  |> last()
            '''

            result = await self.influx_service.query(query)
            return self._parse_influx_result(result)

        except Exception as e:
            logger.error(f"Failed to get current readings for {equipment_id}: {e}")
            return {}

    async def _get_current_element_readings(
        self, equipment_id: str, element_id: str, measurement_type: str
    ) -> dict[str, float]:
        """Get current readings for an element."""
        try:
            # This would integrate with mobile sensor data or specialized sensors
            # For now, return empty - in real implementation would query appropriate source
            return {}
        except Exception as e:
            logger.error(f"Failed to get element readings: {e}")
            return {}

    def _parse_influx_result(self, result: Any) -> dict[str, float]:
        """Parse InfluxDB query result to dictionary."""
        # Simplified parsing - actual implementation would handle Flux tables
        return {}

    async def _generate_deviation_alert(self, comparison: BaselineComparison):
        """Generate alert for critical baseline deviation."""
        # This would integrate with the alert system
        # Implementation depends on existing alert infrastructure
        logger.warning(f"Critical baseline deviation detected: {comparison.equipment_id}")

    async def get_baseline_history(self, equipment_id: str, limit: int = 10) -> list[EquipmentBaseline]:
        """Get baseline history for equipment."""
        return await self.repository.get_equipment_baseline_history(equipment_id, limit)

    async def get_baseline_report(self, equipment_id: str) -> dict[str, Any]:
        """
        Generate comprehensive baseline report for equipment.

        Returns:
            Report with baseline values, comparisons, element status
        """
        # Get active baseline
        baseline = await self.repository.get_active_equipment_baseline(equipment_id)
        if not baseline:
            return {"error": "No active baseline found"}

        # Get recent comparisons
        comparisons = await self.repository.get_recent_comparisons(equipment_id, limit=5)

        # Get element baselines
        elements = await self.repository.get_equipment_elements(equipment_id)

        report = {
            "equipment_id": equipment_id,
            "baseline": baseline,
            "comparison_history": comparisons,
            "elements": elements,
            "generated_at": datetime.now().isoformat(),
        }

        return report

    async def archive_old_baselines(self, equipment_id: str, keep_last: int = 5):
        """Archive old baselines, keeping only the last N."""
        await self.repository.archive_old_baselines(equipment_id, keep_last)
        logger.info(f"Archived old baselines for {equipment_id}, keeping last {keep_last}")


# Singleton instance
_baseline_service = None


def get_baseline_service() -> BaselineService:
    """Get singleton baseline service instance."""
    global _baseline_service
    if _baseline_service is None:
        _baseline_service = BaselineService()
    return _baseline_service
