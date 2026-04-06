"""Water Alert Service — leak detection algorithms and alert management.

Implements multiple leak detection strategies:
1. Continuous flow detection (flow during off-hours)
2. Statistical anomaly detection (z-score analysis)
3. Spike detection (sudden flow increase)
4. Night flow monitoring (minimum night flow)
"""

import logging
import uuid
from datetime import datetime, timedelta
from statistics import mean, stdev
from typing import Any

from pydantic import BaseModel

from app.database.repositories.water_consumption_repository import WaterConsumptionRepository
from app.models.water_meter import AlertSeverity, AlertStatus, AlertType, WaterAlert

logger = logging.getLogger(__name__)


class WaterAlertNotificationSettings(BaseModel):
    """Configuration for water alert notifications."""

    enabled: bool = True
    notify_critical: bool = True
    notify_warning: bool = True
    notify_channels: list[str] = ["sentry"]
    technician_group: str = "water_maintenance"
    escalate_after_hours: int = 2


class WaterAlertThresholds(BaseModel):
    """Configuration model for water alert thresholds."""

    continuous_flow_lpm: float = 10.0
    night_flow_lpm: float = 5.0
    statistical_sensitivity: float = 2.0
    statistical_critical_sensitivity: float = 3.0
    temperature_min_celsius: float = 4.0
    temperature_max_celsius: float = 60.0


# Lazy import to avoid circular dependencies
_occupancy_service = None


def _get_occupancy_service():
    """Get occupancy service lazily to avoid circular imports."""
    global _occupancy_service
    if _occupancy_service is None:
        try:
            from app.services.security_occupancy_service import get_security_occupancy_service

            _occupancy_service = get_security_occupancy_service()
        except Exception:
            _occupancy_service = False  # Mark as tried but unavailable
    return _occupancy_service if _occupancy_service else None


class WaterAlertService:
    """Water leak detection and alerting service.

    Configurable thresholds for different detection algorithms.
    """

    def __init__(
        self,
        continuous_flow_threshold_lpm: float = 10.0,
        continuous_flow_duration_minutes: float = 30.0,
        continuous_flow_off_hours_start: int = 22,  # 10 PM
        continuous_flow_off_hours_end: int = 6,  # 6 AM
        spike_detection_threshold_percent: float = 200.0,  # 200% increase
        spike_detection_window_minutes: int = 15,
        zscore_threshold: float = 3.0,
        zscore_baseline_days: int = 7,
        night_flow_threshold_lpm: float = 5.0,
        night_flow_hours_start: int = 2,
        night_flow_hours_end: int = 4,
        night_occupancy_max: int = 0,  # Building should be empty at night
        work_order_service: Any | None = None,
        technician_repository: Any | None = None,
    ):
        """Initialize alert service with detection thresholds."""
        self.continuous_flow_threshold_lpm = continuous_flow_threshold_lpm
        self.continuous_flow_duration_minutes = continuous_flow_duration_minutes
        self.continuous_flow_off_hours_start = continuous_flow_off_hours_start
        self.continuous_flow_off_hours_end = continuous_flow_off_hours_end
        self.spike_detection_threshold_percent = spike_detection_threshold_percent
        self.spike_detection_window_minutes = spike_detection_window_minutes
        self.zscore_threshold = zscore_threshold
        self.zscore_baseline_days = zscore_baseline_days
        self.night_flow_threshold_lpm = night_flow_threshold_lpm
        self.night_flow_hours_start = night_flow_hours_start
        self.night_flow_hours_end = night_flow_hours_end
        self.night_occupancy_max = night_occupancy_max

        self._repository = WaterConsumptionRepository()
        self.occupancy_service = _get_occupancy_service()
        self.work_order_service = work_order_service
        self.technician_repository = technician_repository
        self.notification_settings = WaterAlertNotificationSettings()

    # === Detection algorithms ===

    def check_continuous_flow(
        self,
        site: str,
        meter_id: str,
        current_flow_rate: float,
        timestamp: datetime,
    ) -> WaterAlert | None:
        """Check for continuous flow during off-hours.

        Detects leaks where water flows continuously during times when
        consumption should be minimal (e.g., 22:00-06:00).

        Args:
            site: Building site code
            meter_id: Meter identifier
            current_flow_rate: Current flow rate in LPM
            timestamp: Reading timestamp

        Returns:
            WaterAlert if leak detected, None otherwise
        """
        hour = timestamp.hour

        # Check if current time is within off-hours
        is_off_hours = hour >= self.continuous_flow_off_hours_start or hour < self.continuous_flow_off_hours_end

        if not is_off_hours:
            return None

        # Check if flow rate exceeds threshold
        if current_flow_rate < self.continuous_flow_threshold_lpm:
            return None

        # Check if condition has persisted for required duration
        # Look back at recent readings to see if flow has been high
        start_time = timestamp - timedelta(minutes=self.continuous_flow_duration_minutes)
        recent_readings = self._repository.get_consumption_by_meter(
            meter_id=meter_id,
            start_date=start_time.date(),
            end_date=timestamp.date(),
        )

        # Filter to last N minutes
        high_flow_count = 0
        for reading in recent_readings:
            reading_time = datetime.fromisoformat(reading["timestamp"])
            if start_time <= reading_time <= timestamp:
                if reading["flow_rate_lpm"] >= self.continuous_flow_threshold_lpm:
                    high_flow_count += 1

        # If 80% of readings show high flow, trigger alert
        if high_flow_count >= len(recent_readings) * 0.8 if recent_readings else False:
            return self._generate_alert(
                meter_id=meter_id,
                site=site,
                alert_type=AlertType.CONTINUOUS_FLOW,
                severity=AlertSeverity.HIGH,
                flow_rate=current_flow_rate,
                threshold=self.continuous_flow_threshold_lpm,
                duration_minutes=self.continuous_flow_duration_minutes,
                description=(
                    f"Continuous flow detected during off-hours ({self.continuous_flow_off_hours_start}:00-"
                    f"{self.continuous_flow_off_hours_end}:00). Flow rate {current_flow_rate:.1f} LPM exceeds "
                    f"threshold {self.continuous_flow_threshold_lpm} LPM for "
                    f"{self.continuous_flow_duration_minutes:.0f} minutes. "
                    "Possible leak in irrigation system or restroom fixture."
                ),
            )

        return None

    def check_unusual_pattern(
        self,
        site: str,
        meter_id: str,
        current_flow_rate: float,
        timestamp: datetime,
    ) -> WaterAlert | None:
        """Check for statistical anomaly using z-score analysis.

        Compares current flow to 7-day baseline. Z-score > 3.0 indicates
        statistically significant anomaly (99.7% confidence).

        Args:
            site: Building site code
            meter_id: Meter identifier
            current_flow_rate: Current flow rate in LPM
            timestamp: Reading timestamp

        Returns:
            WaterAlert if anomaly detected, None otherwise
        """
        # Get baseline data from past N days
        baseline_start = timestamp - timedelta(days=self.zscore_baseline_days)
        baseline_readings = self._repository.get_consumption_by_meter(
            meter_id=meter_id,
            start_date=baseline_start.date(),
            end_date=timestamp.date(),
        )

        if len(baseline_readings) < 10:  # Need sufficient data
            return None

        # Calculate baseline statistics for same hour of day
        current_hour = timestamp.hour
        hourly_flows = [
            r["flow_rate_lpm"] for r in baseline_readings if datetime.fromisoformat(r["timestamp"]).hour == current_hour
        ]

        if len(hourly_flows) < 5:
            return None

        baseline_mean = mean(hourly_flows)
        baseline_std = stdev(hourly_flows) if len(hourly_flows) > 1 else 1.0

        # Calculate z-score
        if baseline_std == 0:
            return None

        zscore = (current_flow_rate - baseline_mean) / baseline_std

        # Check if z-score exceeds threshold
        if abs(zscore) > self.zscore_threshold:
            severity = AlertSeverity.HIGH if zscore > 5 else AlertSeverity.MEDIUM
            return self._generate_alert(
                meter_id=meter_id,
                site=site,
                alert_type=AlertType.UNUSUAL_PATTERN,
                severity=severity,
                flow_rate=current_flow_rate,
                threshold=baseline_mean,
                duration_minutes=0,
                description=(
                    f"Unusual consumption pattern detected. Current flow {current_flow_rate:.1f} LPM is "
                    f"{zscore:.1f} standard deviations from {self.zscore_baseline_days}-day baseline of "
                    f"{baseline_mean:.1f} LPM for this time of day. Possible underground leak or "
                    "meter malfunction."
                ),
            )

        return None

    def check_spike(
        self,
        site: str,
        meter_id: str,
        current_flow_rate: float,
        timestamp: datetime,
    ) -> WaterAlert | None:
        """Check for sudden flow spike.

        Detects rapid increases in flow rate (>200% from 15-minute average).

        Args:
            site: Building site code
            meter_id: Meter identifier
            current_flow_rate: Current flow rate in LPM
            timestamp: Reading timestamp

        Returns:
            WaterAlert if spike detected, None otherwise
        """
        # Get recent readings for comparison
        window_start = timestamp - timedelta(minutes=self.spike_detection_window_minutes)
        recent_readings = self._repository.get_consumption_by_meter(
            meter_id=meter_id,
            start_date=window_start.date(),
            end_date=timestamp.date(),
        )

        # Filter to window
        window_readings = [
            r for r in recent_readings if window_start <= datetime.fromisoformat(r["timestamp"]) <= timestamp
        ]

        if len(window_readings) < 3:
            return None

        # Calculate average flow in window (excluding current)
        window_flows = [r["flow_rate_lpm"] for r in window_readings[:-1]]
        baseline_flow = mean(window_flows) if window_flows else 0

        if baseline_flow == 0:
            return None

        # Calculate percent increase
        percent_increase = ((current_flow_rate - baseline_flow) / baseline_flow) * 100

        # Check if spike exceeds threshold
        if percent_increase > self.spike_detection_threshold_percent:
            return self._generate_alert(
                meter_id=meter_id,
                site=site,
                alert_type=AlertType.SPIKE,
                severity=AlertSeverity.MEDIUM,
                flow_rate=current_flow_rate,
                threshold=baseline_flow,
                duration_minutes=self.spike_detection_window_minutes,
                description=(
                    f"Sudden flow spike detected. Flow increased from {baseline_flow:.1f} LPM to "
                    f"{current_flow_rate:.1f} LPM ({percent_increase:.0f}% increase) within "
                    f"{self.spike_detection_window_minutes} minutes. Possible equipment filling, "
                    "pipe burst, or unauthorized water usage."
                ),
            )

        return None

    async def get_zone_occupancy(self, zone_id: str) -> int:
        """Get occupancy count for a zone.

        Args:
            zone_id: Zone identifier

        Returns:
            Occupancy count (0 if service unavailable or zone empty)
        """
        if not self.occupancy_service:
            return 0

        try:
            occupancy_data = self.occupancy_service.get_zone_occupancy(zone_id)
            return occupancy_data.occupancy_count if occupancy_data else 0
        except Exception as e:
            logger.warning(f"Could not get occupancy for zone {zone_id}: {e}")
            return 0

    async def check_night_flow_with_occupancy(
        self,
        site: str,
        zone_id: str,
        current_flow: float,
        timestamp: datetime,
    ) -> WaterAlert | None:
        """Check for unauthorized water usage at night using occupancy context.

        Detects flow during night hours when the zone occupancy is below threshold.
        This indicates potential unauthorized water usage or leaks in unoccupied areas.

        Args:
            site: Building site code
            zone_id: Zone identifier
            current_flow: Current flow rate in LPM
            timestamp: Reading timestamp

        Returns:
            WaterAlert if unauthorized usage detected, None otherwise
        """
        hour = timestamp.hour

        # Check if time is within night hours (22:00-06:00)
        is_night = hour >= self.continuous_flow_off_hours_start or hour < self.continuous_flow_off_hours_end

        if not is_night:
            return None

        # Check if flow exceeds night threshold
        if current_flow < self.night_flow_threshold_lpm:
            return None

        # Get zone occupancy
        occupancy = await self.get_zone_occupancy(zone_id)

        # If occupancy is above threshold, water usage may be authorized (night shift workers)
        if occupancy > self.night_occupancy_max:
            return None

        # Unauthorized water usage during night when zone is empty
        return self._generate_alert(
            meter_id=f"{zone_id}-meter",
            site=site,
            alert_type=AlertType.CONTINUOUS_FLOW,
            severity=AlertSeverity.CRITICAL,
            flow_rate=current_flow,
            threshold=self.night_flow_threshold_lpm,
            duration_minutes=0,
            description=(
                f"Unauthorized water usage in zone {zone_id} during night hours ({timestamp.hour}:00). "
                f"Flow rate {current_flow:.1f} LPM exceeds threshold {self.night_flow_threshold_lpm} LPM "
                f"with zero occupancy. Possible leak or equipment malfunction in unoccupied area."
            ),
        )

    def calculate_statistical_baseline(self, flows: list[float]) -> dict[str, float]:
        """Calculate statistical baseline metrics from flow data.

        Args:
            flows: List of flow rate values in LPM

        Returns:
            Dictionary with mean, std_dev, min, max, median, and percentile_95
        """
        if not flows:
            return {
                "mean": 0.0,
                "std_dev": 0.0,
                "min": 0.0,
                "max": 0.0,
                "median": 0.0,
                "percentile_95": 0.0,
            }

        sorted_flows = sorted(flows)
        mean_val = mean(flows)
        std_dev_val = stdev(flows) if len(flows) > 1 else 0.0

        # Calculate median
        n = len(sorted_flows)
        median_val = sorted_flows[n // 2] if n % 2 == 1 else (sorted_flows[n // 2 - 1] + sorted_flows[n // 2]) / 2

        # Calculate 95th percentile
        percentile_95_idx = int(0.95 * (len(sorted_flows) - 1))
        percentile_95_val = sorted_flows[percentile_95_idx]

        return {
            "mean": round(mean_val, 2),
            "std_dev": round(std_dev_val, 2),
            "min": round(min(flows), 2),
            "max": round(max(flows), 2),
            "median": round(median_val, 2),
            "percentile_95": round(percentile_95_val, 2),
        }

    async def check_zone_statistical_anomaly(
        self,
        zone_id: str,
        current_flow: float,
        lookback_hours: int = 24,
        sensitivity: float = 2.0,
    ) -> WaterAlert | None:
        """Check for zone-based statistical anomaly.

        Detects abnormal flow by comparing current flow to historical baseline
        using statistical deviation (standard deviation multiplier).

        Args:
            zone_id: Zone identifier
            current_flow: Current flow rate in LPM
            lookback_hours: Number of hours to look back for baseline (default 24)
            sensitivity: Standard deviation multiplier for thresholds (default 2.0)

        Returns:
            WaterAlert if anomaly detected, None otherwise
        """
        # Get historical flow data for zone
        historical_flows = await self._repository.get_zone_historical_flow(
            zone_id=zone_id,
            lookback_hours=lookback_hours,
        )

        if not historical_flows or len(historical_flows) < 5:
            # Insufficient data for statistical analysis
            return None

        # Calculate baseline statistics
        baseline = self.calculate_statistical_baseline(historical_flows)

        # Check for anomaly
        mean_flow = baseline["mean"]
        std_dev = baseline["std_dev"]

        if std_dev == 0:
            return None

        # Calculate deviation from baseline
        deviation = (current_flow - mean_flow) / std_dev

        # Check thresholds
        if deviation > 3.0:
            # Critical anomaly (> 3 std dev)
            return self._generate_alert(
                meter_id=f"{zone_id}-meter",
                site="",  # Site will be determined from zone_id
                alert_type=AlertType.UNUSUAL_PATTERN,
                severity=AlertSeverity.CRITICAL,
                flow_rate=current_flow,
                threshold=mean_flow,
                duration_minutes=0,
                description=(
                    f"Critical anomaly in zone {zone_id}: Current flow {current_flow:.1f} LPM is "
                    f"{deviation:.1f} standard deviations from baseline {mean_flow:.1f} LPM. "
                    f"Possible severe leak or major equipment malfunction."
                ),
            )
        elif deviation > sensitivity:
            # Warning anomaly (> sensitivity std dev)
            return self._generate_alert(
                meter_id=f"{zone_id}-meter",
                site="",  # Site will be determined from zone_id
                alert_type=AlertType.UNUSUAL_PATTERN,
                severity=AlertSeverity.MEDIUM,
                flow_rate=current_flow,
                threshold=mean_flow,
                duration_minutes=0,
                description=(
                    f"Abnormal flow in zone {zone_id}: Current flow {current_flow:.1f} LPM is "
                    f"{deviation:.1f} standard deviations from baseline {mean_flow:.1f} LPM. "
                    f"Possible leak or unusual equipment usage."
                ),
            )

        return None

    def check_all_alerts(
        self,
        site: str,
        meter_id: str,
        current_flow_rate: float,
        timestamp: datetime,
    ) -> list[WaterAlert]:
        """Run all leak detection algorithms.

        Args:
            site: Building site code
            meter_id: Meter identifier
            current_flow_rate: Current flow rate in LPM
            timestamp: Reading timestamp

        Returns:
            List of generated alerts (may be empty)
        """
        alerts = []

        # Run all detection algorithms
        continuous_alert = self.check_continuous_flow(site, meter_id, current_flow_rate, timestamp)
        if continuous_alert:
            alerts.append(continuous_alert)

        unusual_alert = self.check_unusual_pattern(site, meter_id, current_flow_rate, timestamp)
        if unusual_alert:
            alerts.append(unusual_alert)

        spike_alert = self.check_spike(site, meter_id, current_flow_rate, timestamp)
        if spike_alert:
            alerts.append(spike_alert)

        # Save alerts to repository
        for alert in alerts:
            self._repository.create_alert(
                meter_id=alert.meter_id,
                site=alert.site,
                alert_type=alert.alert_type.value,
                severity=alert.severity.value,
                flow_rate_lpm=alert.flow_rate_lpm,
                threshold_lpm=alert.threshold_lpm,
                duration_minutes=alert.duration_minutes,
                description=alert.description,
            )
            logger.warning(f"Water alert generated: {alert.alert_type.value} for {meter_id}")

        return alerts

    # === Alert queries ===

    def get_leak_alerts(
        self,
        site: str,
        severity: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        status: str | None = None,
    ) -> list[WaterAlert]:
        """Get leak alerts for a site.

        Args:
            site: Building site code
            severity: Filter by severity level
            start_date: Start date filter
            end_date: End date filter
            status: Filter by status (active, resolved, etc.)

        Returns:
            List of WaterAlert objects
        """
        records = self._repository.get_alerts(
            site=site,
            severity=severity,
            start_date=start_date.date() if start_date else None,
            end_date=end_date.date() if end_date else None,
            status=status,
        )
        return [WaterAlert.from_dict(r) for r in records]

    def get_active_alerts(self, site: str) -> list[WaterAlert]:
        """Get all active (unresolved) alerts.

        Args:
            site: Building site code

        Returns:
            List of active alerts
        """
        return self.get_leak_alerts(site, status="active")

    def resolve_alert(
        self,
        alert_id: str,
        resolved_by: str,
        resolution_notes: str,
    ) -> bool:
        """Mark an alert as resolved.

        Args:
            alert_id: Alert identifier
            resolved_by: User resolving the alert
            resolution_notes: Resolution description

        Returns:
            True if resolved successfully
        """
        result = self._repository.resolve_alert(alert_id, resolved_by, resolution_notes)
        if result:
            logger.info(f"Alert {alert_id} resolved by {resolved_by}")
            return True
        logger.error(f"Failed to resolve alert {alert_id}")
        return False

    # === Work order integration ===

    async def create_work_order_from_alert(self, alert: WaterAlert) -> dict | None:
        """Create work order from water alert.

        Args:
            alert: WaterAlert object

        Returns:
            Dictionary with work_order_id, alert_id, created_at, technician_id, status
        """
        if not self.work_order_service:
            logger.warning("WorkOrderService not initialized - cannot create work order")
            return None

        try:
            # Extract zone ID from alert (meter_id format: "zone_id-meter" or similar)
            zone_id = alert.meter_id.replace("-meter", "") if alert.meter_id else "unknown"

            # Determine priority based on severity
            priority = (
                "critical"
                if alert.severity == AlertSeverity.CRITICAL
                else ("high" if alert.severity == AlertSeverity.HIGH else "medium")
            )

            # Create work order
            work_order = self.work_order_service.create_work_order(
                description=alert.description,
                site_id=alert.site,
                equipment_ref=f"METER-{zone_id}",
                category="water_maintenance",
                priority=priority,
                reported_by="WATER_ALERT_SERVICE",
            )

            # Try to assign technician
            technician_id = None
            if self.technician_repository:
                try:
                    # Look up technician for water maintenance specialty
                    technician = await self.technician_repository.get_technician_for_specialty(
                        specialty="water_maintenance", zone_id=zone_id
                    )
                    if technician:
                        technician_id = technician.get("id")
                        logger.info(f"Assigned technician {technician_id} to water work order {work_order.id}")
                except Exception as e:
                    logger.warning(f"Could not assign technician: {e}")

            result = {
                "work_order_id": work_order.id,
                "alert_id": alert.alert_id,
                "created_at": work_order.created_at,
                "technician_id": technician_id,
                "status": work_order.status,
                "priority": priority,
                "zone_id": zone_id,
            }

            logger.info(f"Created work order {work_order.id} from water alert {alert.alert_id}")
            return result

        except Exception as e:
            logger.error(f"Failed to create work order from alert: {e}")
            return None

    async def acknowledge_alert(
        self,
        alert_id: str,
        acknowledged_by: str,
        notes: str | None = None,
        work_order_id: str | None = None,
    ) -> dict:
        """Mark alert as acknowledged.

        Args:
            alert_id: Alert ID to acknowledge
            acknowledged_by: User or system acknowledging
            notes: Optional acknowledgment notes
            work_order_id: Link to associated work order

        Returns:
            Dictionary with alert_id, status, acknowledged_at, acknowledged_by, work_order_id
        """
        try:
            acknowledged_at = datetime.now().isoformat()

            # Update alert status to acknowledged (using resolve_alert)
            self._repository.resolve_alert(
                alert_id=alert_id,
                resolved_by=acknowledged_by,
                resolution_notes=notes or "Alert acknowledged by technician/system",
            )

            result = {
                "alert_id": alert_id,
                "status": "acknowledged",
                "acknowledged_at": acknowledged_at,
                "acknowledged_by": acknowledged_by,
                "work_order_id": work_order_id,
                "notes": notes,
            }

            logger.info(f"Alert {alert_id} acknowledged by {acknowledged_by}")
            return result

        except Exception as e:
            logger.error(f"Failed to acknowledge alert {alert_id}: {e}")
            return {
                "alert_id": alert_id,
                "status": "error",
                "message": str(e),
            }

    async def notify_sentry_water_alert(
        self,
        alert: WaterAlert,
        work_order_id: str,
        technician_id: str | None = None,
    ) -> dict:
        """Notify Sentry bot of water leak alert.

        Args:
            alert: WaterAlert object
            work_order_id: Associated work order ID
            technician_id: Assigned technician ID (optional)

        Returns:
            Dictionary with notification_id, sent_at, channel, status
        """
        if not self.notification_settings.enabled:
            logger.info("Water alert notifications disabled")
            return {"status": "disabled"}

        # Check if we should notify based on severity
        if alert.severity == AlertSeverity.WARNING and not self.notification_settings.notify_warning:
            logger.info(f"Warning alert notifications disabled, skipping alert {alert.alert_id}")
            return {"status": "skipped", "reason": "warning notifications disabled"}

        try:
            notification_id = str(uuid.uuid4())
            sent_at = datetime.now().isoformat()

            # Format Sentry message
            severity_emoji = (
                "🚨"
                if alert.severity == AlertSeverity.CRITICAL
                else ("⚠️" if alert.severity == AlertSeverity.HIGH else "ℹ️")
            )

            zone_id = alert.meter_id.replace("-meter", "") if alert.meter_id else "unknown"

            message_lines = [
                f"{severity_emoji} WATER ALERT: {alert.severity.value.upper()}",
                f"Zone: {zone_id}",
                f"Flow: {alert.flow_rate_lpm:.1f} L/min (threshold: {alert.threshold_lpm:.1f} L/min)",
                f"Type: {alert.alert_type.value.replace('_', ' ').title()}",
                "",
                f"Issue: {alert.description}",
                "",
                f"Work Order: {work_order_id}",
            ]

            if technician_id:
                message_lines.append(f"Technician: {technician_id}")

            message_lines.extend(
                [
                    "",
                    f"Command: /water_repair_{work_order_id}",
                    "Reply with repair details to submit feedback",
                ]
            )

            sentry_message = "\n".join(message_lines)

            # Log the notification intent
            result = {
                "notification_id": notification_id,
                "sent_at": sent_at,
                "channel": "sentry",
                "status": "queued_for_sending",
                "message_preview": sentry_message[:100] + "..." if len(sentry_message) > 100 else sentry_message,
                "work_order_id": work_order_id,
                "alert_id": alert.alert_id,
            }

            logger.info(
                f"Water alert notification queued: {notification_id} for work order {work_order_id}. "
                f"Message: {sentry_message[:200]}"
            )

            return result

        except Exception as e:
            logger.error(f"Failed to create Sentry notification for alert {alert.alert_id}: {e}")
            return {
                "status": "error",
                "message": str(e),
                "alert_id": alert.alert_id,
            }

    # === Helper methods ===

    def _generate_alert(
        self,
        meter_id: str,
        site: str,
        alert_type: AlertType,
        severity: AlertSeverity,
        flow_rate: float,
        threshold: float,
        duration_minutes: float,
        description: str,
    ) -> WaterAlert:
        """Generate a WaterAlert object."""
        import uuid

        return WaterAlert(
            alert_id=str(uuid.uuid4()),
            meter_id=meter_id,
            site=site,
            alert_type=alert_type,
            severity=severity,
            status=AlertStatus.ACTIVE,
            timestamp=datetime.now(),
            flow_rate_lpm=flow_rate,
            threshold_lpm=threshold,
            duration_minutes=duration_minutes,
            description=description,
        )


# Singleton instance
_water_alert_service: WaterAlertService | None = None


def get_water_alert_service() -> WaterAlertService:
    """Get singleton instance of WaterAlertService."""
    global _water_alert_service
    if _water_alert_service is None:
        _water_alert_service = WaterAlertService()
    return _water_alert_service
