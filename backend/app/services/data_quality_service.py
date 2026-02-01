"""Data Quality Service for ML Training Data Validation.

This service monitors and computes data quality metrics for BMS sensor data,
ensuring ML training datasets are reliable and complete.

Key capabilities:
- Sensor uptime tracking (expected vs actual readings)
- Data gap detection (missing data periods)
- Quality scoring per equipment (0-100 scale)
- Building-level quality reports
- ML training readiness assessment
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

from app.models.data_quality import (
    DataQualityLevel,
    DataGap,
    SensorHealth,
    EquipmentDataQuality,
    BuildingDataQualityReport,
    TrainingReadiness,
)
from app.services.influxdb_service import get_influxdb_service, InfluxDBService

logger = logging.getLogger(__name__)

# Singleton instance
_data_quality_service: Optional["DataQualityService"] = None


class DataQualityService:
    """Service for computing data quality metrics from InfluxDB sensor data.

    Provides quality assessment for individual equipment, buildings,
    and equipment types to ensure ML training data reliability.
    """

    # Expected readings per day (1-minute polling interval)
    EXPECTED_READINGS_PER_DAY = 1440

    # Sensor types tracked per equipment type
    EQUIPMENT_SENSORS: Dict[str, List[str]] = {
        "chiller": [
            "temperature", "chw_supply_temp", "chw_return_temp",
            "condenser_pressure", "evaporator_pressure", "current",
            "vibration_rms", "power"
        ],
        "ahu": [
            "supply_air_temp", "return_air_temp", "mixed_air_temp",
            "supply_fan_speed", "return_fan_speed", "filter_dp",
            "damper_position", "humidity"
        ],
        "generator": [
            "engine_temp", "oil_pressure", "coolant_temp",
            "rpm", "voltage", "current", "frequency", "fuel_level"
        ],
    }

    # Default sensors for unknown equipment types
    DEFAULT_SENSORS = ["temperature", "current", "power"]

    def __init__(self, influxdb_service: Optional[InfluxDBService] = None):
        """Initialize the data quality service.

        Args:
            influxdb_service: InfluxDB service instance (default: singleton)
        """
        self._influxdb = influxdb_service or get_influxdb_service()
        self._equipment_cache: Dict[str, Any] = {}
        self._cache_ttl = timedelta(minutes=5)
        self._cache_timestamps: Dict[str, datetime] = {}

    def get_equipment_quality(
        self,
        equipment_id: str,
        equipment_type: str = "unknown",
        building_id: str = "",
        lookback_hours: int = 24,
    ) -> EquipmentDataQuality:
        """Compute data quality metrics for an equipment.

        Args:
            equipment_id: Equipment identifier
            equipment_type: Equipment type (chiller, ahu, generator)
            building_id: Building identifier
            lookback_hours: Hours to analyze (default: 24)

        Returns:
            EquipmentDataQuality with sensor health and overall score
        """
        # Get sensor types for this equipment
        sensor_types = self.EQUIPMENT_SENSORS.get(
            equipment_type.lower(), self.DEFAULT_SENSORS
        )

        start = datetime.utcnow() - timedelta(hours=lookback_hours)
        sensor_health_list: List[SensorHealth] = []

        total_expected = 0
        total_actual = 0

        for sensor_type in sensor_types:
            health = self._check_sensor_health(
                equipment_id=equipment_id,
                sensor_type=sensor_type,
                start=start,
                expected_per_hour=60,  # 1-minute polling
            )
            sensor_health_list.append(health)
            total_expected += health.expected_readings_24h
            total_actual += health.actual_readings_24h

        # Calculate overall completeness
        completeness_pct = (
            (total_actual / total_expected * 100) if total_expected > 0 else 0.0
        )

        # Determine overall quality level
        overall_quality = self._level_from_pct(completeness_pct)

        # Quality score is the average of sensor completeness percentages
        quality_score = (
            sum(s.completeness_pct for s in sensor_health_list) / len(sensor_health_list)
            if sensor_health_list else 0.0
        )

        return EquipmentDataQuality(
            equipment_id=equipment_id,
            equipment_type=equipment_type,
            building_id=building_id,
            overall_quality=overall_quality,
            quality_score=round(quality_score, 2),
            sensor_health=sensor_health_list,
            total_expected_24h=total_expected,
            total_actual_24h=total_actual,
            completeness_pct=round(completeness_pct, 2),
            last_updated=datetime.utcnow(),
        )

    def _check_sensor_health(
        self,
        equipment_id: str,
        sensor_type: str,
        start: datetime,
        expected_per_hour: int = 60,
    ) -> SensorHealth:
        """Check health metrics for a single sensor.

        Args:
            equipment_id: Equipment identifier
            sensor_type: Sensor type to check
            start: Start time for analysis
            expected_per_hour: Expected readings per hour (default: 60)

        Returns:
            SensorHealth with completeness and gap information
        """
        end = datetime.utcnow()
        hours = (end - start).total_seconds() / 3600
        expected_readings = int(hours * expected_per_hour)

        # Query actual readings from InfluxDB
        readings = self._influxdb.query_raw(
            equipment_id=equipment_id,
            sensor_type=sensor_type,
            start=start,
            end=end,
        )

        actual_readings = len(readings)
        completeness_pct = (
            (actual_readings / expected_readings * 100)
            if expected_readings > 0 else 0.0
        )

        # Detect gaps (threshold: 5 minutes)
        gaps = self._detect_gaps(
            equipment_id=equipment_id,
            sensor_type=sensor_type,
            readings=readings,
            gap_threshold_minutes=5,
        )

        # Get last reading timestamp
        last_reading_at = readings[-1].timestamp if readings else None

        # Determine quality level
        status = self._level_from_pct(completeness_pct)

        return SensorHealth(
            sensor_type=sensor_type,
            equipment_id=equipment_id,
            expected_readings_24h=expected_readings,
            actual_readings_24h=actual_readings,
            completeness_pct=round(completeness_pct, 2),
            last_reading_at=last_reading_at,
            gaps=gaps,
            status=status,
        )

    def _detect_gaps(
        self,
        equipment_id: str,
        sensor_type: str,
        readings: List[Any],
        gap_threshold_minutes: int = 5,
    ) -> List[DataGap]:
        """Detect data gaps in sensor readings.

        A gap is detected when the interval between consecutive readings
        exceeds the threshold.

        Args:
            equipment_id: Equipment identifier
            sensor_type: Sensor type
            readings: List of SensorReading objects with timestamps
            gap_threshold_minutes: Minimum gap duration to report

        Returns:
            List of DataGap objects
        """
        if len(readings) < 2:
            return []

        gaps: List[DataGap] = []
        threshold = timedelta(minutes=gap_threshold_minutes)

        # Sort readings by timestamp
        sorted_readings = sorted(readings, key=lambda r: r.timestamp)

        for i in range(1, len(sorted_readings)):
            prev_ts = sorted_readings[i - 1].timestamp
            curr_ts = sorted_readings[i].timestamp
            delta = curr_ts - prev_ts

            if delta > threshold:
                duration_minutes = delta.total_seconds() / 60
                gaps.append(
                    DataGap(
                        start=prev_ts,
                        end=curr_ts,
                        duration_minutes=round(duration_minutes, 2),
                        sensor_type=sensor_type,
                        equipment_id=equipment_id,
                    )
                )

        return gaps

    def _level_from_pct(self, pct: float) -> DataQualityLevel:
        """Convert completeness percentage to quality level.

        Args:
            pct: Completeness percentage (0-100)

        Returns:
            DataQualityLevel enum value
        """
        if pct >= 95:
            return DataQualityLevel.EXCELLENT
        elif pct >= 80:
            return DataQualityLevel.GOOD
        elif pct >= 60:
            return DataQualityLevel.FAIR
        else:
            return DataQualityLevel.POOR

    def get_equipment_gaps(
        self,
        equipment_id: str,
        equipment_type: str = "unknown",
        lookback_hours: int = 24,
    ) -> List[DataGap]:
        """Get all data gaps for an equipment.

        Args:
            equipment_id: Equipment identifier
            equipment_type: Equipment type
            lookback_hours: Hours to analyze

        Returns:
            List of all DataGap objects across all sensors
        """
        quality = self.get_equipment_quality(
            equipment_id=equipment_id,
            equipment_type=equipment_type,
            lookback_hours=lookback_hours,
        )

        all_gaps: List[DataGap] = []
        for sensor_health in quality.sensor_health:
            all_gaps.extend(sensor_health.gaps)

        # Sort by start time
        all_gaps.sort(key=lambda g: g.start)
        return all_gaps

    def generate_daily_report(
        self,
        building_id: str,
        building_name: str = "",
        equipment_list: Optional[List[Dict[str, str]]] = None,
    ) -> BuildingDataQualityReport:
        """Generate a daily data quality report for a building.

        Args:
            building_id: Building identifier
            building_name: Building name
            equipment_list: List of equipment dicts with equipment_id and equipment_type

        Returns:
            BuildingDataQualityReport with aggregated metrics
        """
        # If no equipment list provided, load from equipment.json
        if equipment_list is None:
            equipment_list = self._load_equipment_for_building(building_id)

        equipment_quality_list: List[EquipmentDataQuality] = []
        total_score = 0.0

        for eq in equipment_list:
            quality = self.get_equipment_quality(
                equipment_id=eq["equipment_id"],
                equipment_type=eq.get("equipment_type", "unknown"),
                building_id=building_id,
                lookback_hours=24,
            )
            equipment_quality_list.append(quality)
            total_score += quality.quality_score

        # Calculate averages
        avg_score = total_score / len(equipment_quality_list) if equipment_quality_list else 0.0
        overall_quality = self._level_from_pct(avg_score)

        # Count active alerts and total gaps
        total_gaps = sum(eq.total_gaps for eq in equipment_quality_list)

        return BuildingDataQualityReport(
            building_id=building_id,
            building_name=building_name,
            report_date=datetime.utcnow(),
            equipment_count=len(equipment_quality_list),
            overall_quality=overall_quality,
            average_quality_score=round(avg_score, 2),
            equipment_quality=equipment_quality_list,
            active_alerts=0,  # Will be populated by alert service
            total_gaps=total_gaps,
        )

    def check_training_readiness(
        self,
        equipment_type: str,
        minimum_equipment: int = 5,
        minimum_days: int = 30,
        minimum_quality_score: float = 80.0,
    ) -> TrainingReadiness:
        """Check if sufficient data exists to train ML models.

        Args:
            equipment_type: Equipment type to assess
            minimum_equipment: Minimum equipment count required
            minimum_days: Minimum days of data required
            minimum_quality_score: Minimum quality score for "good" data

        Returns:
            TrainingReadiness assessment
        """
        # Load all equipment of this type
        equipment_list = self._load_equipment_by_type(equipment_type)
        total_equipment = len(equipment_list)

        # Check quality for each equipment
        good_data_count = 0
        for eq in equipment_list:
            quality = self.get_equipment_quality(
                equipment_id=eq["equipment_id"],
                equipment_type=equipment_type,
                lookback_hours=24,
            )
            if quality.quality_score >= minimum_quality_score:
                good_data_count += 1

        # Check if we have enough days of data (mock check - in real system would query InfluxDB)
        # For demo, assume we have data based on mock generation
        days_of_data = 30  # Mock value

        # Determine readiness
        issues: List[str] = []
        recommendations: List[str] = []

        if total_equipment < minimum_equipment:
            issues.append(
                f"Insufficient equipment: {total_equipment}/{minimum_equipment} required"
            )
            recommendations.append(
                f"Add at least {minimum_equipment - total_equipment} more {equipment_type} equipment to the system"
            )

        if good_data_count < minimum_equipment:
            issues.append(
                f"Insufficient quality data: {good_data_count}/{minimum_equipment} equipment with good data"
            )
            recommendations.append(
                "Improve sensor connectivity and reduce data gaps for affected equipment"
            )

        if days_of_data < minimum_days:
            issues.append(
                f"Insufficient history: {days_of_data}/{minimum_days} days of data"
            )
            recommendations.append(
                f"Continue collecting data for {minimum_days - days_of_data} more days"
            )

        is_ready = len(issues) == 0
        readiness_score = self._calculate_readiness_score(
            equipment_count=total_equipment,
            good_count=good_data_count,
            days_of_data=days_of_data,
            minimum_equipment=minimum_equipment,
            minimum_days=minimum_days,
        )

        return TrainingReadiness(
            equipment_type=equipment_type,
            is_ready=is_ready,
            readiness_score=round(readiness_score, 2),
            equipment_count=total_equipment,
            equipment_with_good_data=good_data_count,
            minimum_required=minimum_equipment,
            days_of_data=days_of_data,
            minimum_days_required=minimum_days,
            issues=issues,
            recommendations=recommendations,
        )

    def _calculate_readiness_score(
        self,
        equipment_count: int,
        good_count: int,
        days_of_data: int,
        minimum_equipment: int,
        minimum_days: int,
    ) -> float:
        """Calculate training readiness score (0-100).

        Weighted average of:
        - Equipment count vs requirement (30%)
        - Good quality equipment vs requirement (40%)
        - Days of data vs requirement (30%)
        """
        eq_score = min(100, (equipment_count / minimum_equipment) * 100)
        quality_score = min(100, (good_count / minimum_equipment) * 100)
        days_score = min(100, (days_of_data / minimum_days) * 100)

        return (eq_score * 0.3) + (quality_score * 0.4) + (days_score * 0.3)

    def _load_equipment_for_building(
        self, building_id: str
    ) -> List[Dict[str, str]]:
        """Load equipment list for a building from equipment.json.

        Args:
            building_id: Building identifier

        Returns:
            List of equipment dicts with equipment_id and equipment_type
        """
        try:
            equipment_path = Path(__file__).parent.parent / "data" / "equipment.json"
            with open(equipment_path, "r") as f:
                all_equipment = json.load(f)

            # Filter by building_id (site_id in equipment.json)
            return [
                {"equipment_id": eq["id"], "equipment_type": eq.get("type", "unknown")}
                for eq in all_equipment
                if eq.get("site_id", "") == building_id
            ]
        except Exception as e:
            logger.warning(f"Failed to load equipment for building {building_id}: {e}")
            return []

    def _load_equipment_by_type(
        self, equipment_type: str
    ) -> List[Dict[str, str]]:
        """Load all equipment of a specific type.

        Args:
            equipment_type: Equipment type to filter

        Returns:
            List of equipment dicts with equipment_id and equipment_type
        """
        try:
            equipment_path = Path(__file__).parent.parent / "data" / "equipment.json"
            with open(equipment_path, "r") as f:
                all_equipment = json.load(f)

            return [
                {"equipment_id": eq["id"], "equipment_type": eq.get("type", "unknown")}
                for eq in all_equipment
                if eq.get("type", "").lower() == equipment_type.lower()
            ]
        except Exception as e:
            logger.warning(f"Failed to load equipment of type {equipment_type}: {e}")
            return []


def get_data_quality_service() -> DataQualityService:
    """Get singleton data quality service instance.

    Returns:
        DataQualityService instance
    """
    global _data_quality_service

    if _data_quality_service is None:
        _data_quality_service = DataQualityService()

    return _data_quality_service
