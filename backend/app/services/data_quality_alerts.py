"""Data Quality Alert Service for ML Training Data.

This service monitors data quality and generates alerts for issues
that may affect ML model training quality.

Alert types:
- stale: No readings for extended period (>15 minutes)
- gap: Significant data gap (>30 minutes)
- drift: Sudden value change indicating sensor drift
- anomaly: Statistical anomaly in readings
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

from app.models.data_quality import (
    DataQualityAlert,
)
from app.services.data_quality_service import get_data_quality_service, DataQualityService

logger = logging.getLogger(__name__)

# Singleton instance
_alert_service: Optional["DataQualityAlertService"] = None


class DataQualityAlertService:
    """Service for generating and managing data quality alerts.

    Monitors sensor data streams and generates alerts when quality
    issues are detected that may affect ML training.
    """

    # Thresholds for alert generation
    STALE_THRESHOLD_MINUTES = 15  # No data for 15 minutes
    GAP_THRESHOLD_MINUTES = 30  # Gap longer than 30 minutes
    DRIFT_THRESHOLD_PERCENT = 50  # Value changed by >50% in short time

    def __init__(
        self,
        data_quality_service: Optional[DataQualityService] = None,
    ):
        """Initialize the alert service.

        Args:
            data_quality_service: Data quality service instance
        """
        self._quality_service = data_quality_service or get_data_quality_service()
        self._active_alerts: Dict[str, DataQualityAlert] = {}
        self._alert_history: List[DataQualityAlert] = []

    def check_all_equipment(
        self,
        equipment_list: Optional[List[Dict[str, str]]] = None,
    ) -> List[DataQualityAlert]:
        """Check all equipment for data quality issues.

        Args:
            equipment_list: List of equipment dicts. If None, loads from equipment.json

        Returns:
            List of new alerts generated
        """
        if equipment_list is None:
            equipment_list = self._load_all_equipment()

        new_alerts: List[DataQualityAlert] = []

        for eq in equipment_list:
            equipment_id = eq["equipment_id"]
            equipment_type = eq.get("equipment_type", "unknown")

            alerts = self._check_equipment(
                equipment_id=equipment_id,
                equipment_type=equipment_type,
            )
            new_alerts.extend(alerts)

        return new_alerts

    def _check_equipment(
        self,
        equipment_id: str,
        equipment_type: str,
    ) -> List[DataQualityAlert]:
        """Check a single equipment for data quality issues.

        Checks for:
        1. Stale data (no readings in 15 minutes)
        2. Significant gaps (>30 minutes)
        3. Sensor drift (sudden value changes)

        Args:
            equipment_id: Equipment identifier
            equipment_type: Equipment type

        Returns:
            List of alerts generated for this equipment
        """
        alerts: List[DataQualityAlert] = []

        # Get quality metrics for this equipment
        quality = self._quality_service.get_equipment_quality(
            equipment_id=equipment_id,
            equipment_type=equipment_type,
            lookback_hours=24,
        )

        # Check each sensor
        for sensor_health in quality.sensor_health:
            # Check for stale data
            stale_alert = self._check_stale_data(
                equipment_id=equipment_id,
                sensor_type=sensor_health.sensor_type,
                last_reading_at=sensor_health.last_reading_at,
            )
            if stale_alert:
                alerts.append(stale_alert)

            # Check for significant gaps
            gap_alerts = self._check_significant_gaps(
                equipment_id=equipment_id,
                sensor_health=sensor_health,
            )
            alerts.extend(gap_alerts)

        return alerts

    def _check_stale_data(
        self,
        equipment_id: str,
        sensor_type: str,
        last_reading_at: Optional[datetime],
    ) -> Optional[DataQualityAlert]:
        """Check if sensor data is stale (no recent readings).

        Args:
            equipment_id: Equipment identifier
            sensor_type: Sensor type
            last_reading_at: Timestamp of last reading

        Returns:
            DataQualityAlert if data is stale, None otherwise
        """
        alert_key = f"stale:{equipment_id}:{sensor_type}"

        if last_reading_at is None:
            # No data at all
            if alert_key not in self._active_alerts:
                alert = DataQualityAlert(
                    alert_type="stale",
                    severity="critical",
                    equipment_id=equipment_id,
                    sensor_type=sensor_type,
                    message=f"No data received for {sensor_type} sensor on {equipment_id}",
                    detected_at=datetime.utcnow(),
                    details={"minutes_since_last": None},
                )
                self._active_alerts[alert_key] = alert
                self._alert_history.append(alert)
                return alert
            return None

        minutes_since = (datetime.utcnow() - last_reading_at).total_seconds() / 60

        if minutes_since > self.STALE_THRESHOLD_MINUTES:
            if alert_key not in self._active_alerts:
                alert = DataQualityAlert(
                    alert_type="stale",
                    severity="warning" if minutes_since < 60 else "critical",
                    equipment_id=equipment_id,
                    sensor_type=sensor_type,
                    message=(
                        f"Stale data: {sensor_type} on {equipment_id} - no readings for {int(minutes_since)} minutes"
                    ),
                    detected_at=datetime.utcnow(),
                    details={"minutes_since_last": round(minutes_since, 2)},
                )
                self._active_alerts[alert_key] = alert
                self._alert_history.append(alert)
                return alert
        else:
            # Data is fresh, resolve any existing stale alert
            if alert_key in self._active_alerts:
                self._active_alerts[alert_key].resolved_at = datetime.utcnow()
                del self._active_alerts[alert_key]

        return None

    def _check_significant_gaps(
        self,
        equipment_id: str,
        sensor_health: Any,
    ) -> List[DataQualityAlert]:
        """Check for significant data gaps.

        Args:
            equipment_id: Equipment identifier
            sensor_health: SensorHealth object with gaps

        Returns:
            List of alerts for significant gaps
        """
        alerts: List[DataQualityAlert] = []

        for gap in sensor_health.gaps:
            if gap.duration_minutes >= self.GAP_THRESHOLD_MINUTES:
                alert_key = f"gap:{equipment_id}:{sensor_health.sensor_type}:{gap.start.isoformat()}"

                if alert_key not in self._active_alerts:
                    severity = "critical" if gap.duration_minutes >= 60 else "warning"
                    alert = DataQualityAlert(
                        alert_type="gap",
                        severity=severity,
                        equipment_id=equipment_id,
                        sensor_type=sensor_health.sensor_type,
                        message=(
                            f"Data gap: {sensor_health.sensor_type} on "
                            f"{equipment_id} - {int(gap.duration_minutes)} "
                            f"minute gap"
                        ),
                        detected_at=gap.start,
                        resolved_at=gap.end,  # Gap is already resolved (we have data after it)
                        details={
                            "gap_start": gap.start.isoformat(),
                            "gap_end": gap.end.isoformat(),
                            "duration_minutes": gap.duration_minutes,
                        },
                    )
                    self._active_alerts[alert_key] = alert
                    self._alert_history.append(alert)
                    alerts.append(alert)

        return alerts

    def check_sensor_drift(
        self,
        equipment_id: str,
        sensor_type: str,
        values: List[float],
        timestamps: List[datetime],
    ) -> Optional[DataQualityAlert]:
        """Check for sudden sensor drift.

        Detects when a sensor value changes by more than the drift
        threshold in a short time period.

        Args:
            equipment_id: Equipment identifier
            sensor_type: Sensor type
            values: List of sensor values
            timestamps: List of corresponding timestamps

        Returns:
            DataQualityAlert if drift detected, None otherwise
        """
        if len(values) < 2:
            return None

        alert_key = f"drift:{equipment_id}:{sensor_type}"

        # Check for sudden changes
        for i in range(1, len(values)):
            prev_val = values[i - 1]
            curr_val = values[i]

            if prev_val == 0:
                continue

            pct_change = abs((curr_val - prev_val) / prev_val) * 100

            if pct_change >= self.DRIFT_THRESHOLD_PERCENT:
                if alert_key not in self._active_alerts:
                    alert = DataQualityAlert(
                        alert_type="drift",
                        severity="warning",
                        equipment_id=equipment_id,
                        sensor_type=sensor_type,
                        message=f"Sensor drift: {sensor_type} on {equipment_id} - {pct_change:.1f}% change",
                        detected_at=timestamps[i] if i < len(timestamps) else datetime.utcnow(),
                        details={
                            "previous_value": prev_val,
                            "current_value": curr_val,
                            "percent_change": round(pct_change, 2),
                        },
                    )
                    self._active_alerts[alert_key] = alert
                    self._alert_history.append(alert)
                    return alert

        return None

    def get_active_alerts(
        self,
        equipment_id: Optional[str] = None,
        alert_type: Optional[str] = None,
    ) -> List[DataQualityAlert]:
        """Get all active (unresolved) alerts.

        Args:
            equipment_id: Filter by equipment (optional)
            alert_type: Filter by alert type (optional)

        Returns:
            List of active alerts
        """
        alerts = [a for a in self._active_alerts.values() if a.is_active]

        if equipment_id:
            alerts = [a for a in alerts if a.equipment_id == equipment_id]

        if alert_type:
            alerts = [a for a in alerts if a.alert_type == alert_type]

        return sorted(alerts, key=lambda a: a.detected_at, reverse=True)

    def get_alert_history(
        self,
        limit: int = 100,
        equipment_id: Optional[str] = None,
    ) -> List[DataQualityAlert]:
        """Get alert history (including resolved alerts).

        Args:
            limit: Maximum number of alerts to return
            equipment_id: Filter by equipment (optional)

        Returns:
            List of alerts sorted by detected_at (newest first)
        """
        alerts = self._alert_history

        if equipment_id:
            alerts = [a for a in alerts if a.equipment_id == equipment_id]

        # Sort by detected_at descending
        alerts = sorted(alerts, key=lambda a: a.detected_at, reverse=True)

        return alerts[:limit]

    def resolve_alert(
        self,
        equipment_id: str,
        sensor_type: str,
        alert_type: str,
    ) -> bool:
        """Manually resolve an alert.

        Args:
            equipment_id: Equipment identifier
            sensor_type: Sensor type
            alert_type: Alert type

        Returns:
            True if alert was resolved, False if not found
        """
        for key, alert in list(self._active_alerts.items()):
            if (
                alert.equipment_id == equipment_id
                and alert.sensor_type == sensor_type
                and alert.alert_type == alert_type
            ):
                alert.resolved_at = datetime.utcnow()
                del self._active_alerts[key]
                return True

        return False

    def get_alert_summary(self) -> Dict[str, Any]:
        """Get summary of alerts by type and severity.

        Returns:
            Dict with alert counts and breakdown
        """
        active = self.get_active_alerts()

        by_type: Dict[str, int] = {}
        by_severity: Dict[str, int] = {}

        for alert in active:
            by_type[alert.alert_type] = by_type.get(alert.alert_type, 0) + 1
            by_severity[alert.severity] = by_severity.get(alert.severity, 0) + 1

        return {
            "total_active": len(active),
            "by_type": by_type,
            "by_severity": by_severity,
            "total_history": len(self._alert_history),
        }

    def _load_all_equipment(self) -> List[Dict[str, str]]:
        """Load all equipment from equipment.json.

        Returns:
            List of equipment dicts
        """
        try:
            equipment_path = Path(__file__).parent.parent / "data" / "equipment.json"
            with open(equipment_path, "r") as f:
                all_equipment = json.load(f)

            return [{"equipment_id": eq["id"], "equipment_type": eq.get("type", "unknown")} for eq in all_equipment]
        except Exception as e:
            logger.warning(f"Failed to load equipment: {e}")
            return []


def get_data_quality_alert_service() -> DataQualityAlertService:
    """Get singleton alert service instance.

    Returns:
        DataQualityAlertService instance
    """
    global _alert_service

    if _alert_service is None:
        _alert_service = DataQualityAlertService()

    return _alert_service
