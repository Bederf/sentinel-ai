"""
InfluxDB Service - Time-series data storage for ML training.

Phase 42: Data Collection & Storage
Provides time-series storage for sensor data with downsampling policies.

Buckets:
- sensor_data_raw: Raw readings (1s resolution, 7-day retention)
- sensor_data_1m: 1-minute aggregates (30-day retention)
- sensor_data_1h: Hourly aggregates (365-day retention)
- sensor_data_1d: Daily aggregates (5-year retention)

Usage:
    from app.services.influxdb_service import get_influxdb_service

    influx = get_influxdb_service()
    influx.write_sensor_data("chiller-001", "chw_supply_temp", 12.5)
    data = influx.query_hourly("chiller-001", "chw_supply_temp", hours=168)
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import os

logger = logging.getLogger(__name__)

# Check if InfluxDB client is available
try:
    from influxdb_client import InfluxDBClient, Point, WritePrecision
    from influxdb_client.client.write_api import SYNCHRONOUS
    INFLUXDB_AVAILABLE = True
except ImportError:
    INFLUXDB_AVAILABLE = False
    logger.warning("influxdb-client not installed. Using mock implementation.")


@dataclass
class SensorReading:
    """A single sensor reading."""
    timestamp: datetime
    value: float
    equipment_id: str
    sensor_type: str
    unit: Optional[str] = None
    quality: Optional[str] = None


class InfluxDBService:
    """
    InfluxDB service for time-series sensor data.

    Provides:
    - Write sensor readings with automatic bucket routing
    - Query historical data at various resolutions
    - Downsampling tasks for data retention
    - ML training data extraction
    """

    # Bucket configurations
    BUCKETS = {
        "raw": {
            "name": "sensor_data_raw",
            "retention": "7d",
            "description": "Raw sensor readings"
        },
        "1m": {
            "name": "sensor_data_1m",
            "retention": "30d",
            "description": "1-minute aggregates"
        },
        "1h": {
            "name": "sensor_data_1h",
            "retention": "365d",
            "description": "Hourly aggregates"
        },
        "1d": {
            "name": "sensor_data_1d",
            "retention": "1825d",  # 5 years
            "description": "Daily aggregates"
        }
    }

    def __init__(
        self,
        url: str = None,
        token: str = None,
        org: str = None,
        use_mock: bool = False
    ):
        """
        Initialize InfluxDB connection.

        Args:
            url: InfluxDB URL (default from env)
            token: API token (default from env)
            org: Organization (default from env)
            use_mock: Force mock mode for testing
        """
        self.url = url or os.getenv("INFLUXDB_URL", "http://localhost:8086")
        self.token = token or os.getenv("INFLUXDB_TOKEN", "")
        self.org = org or os.getenv("INFLUXDB_ORG", "bms-intelligence")

        self.use_mock = use_mock or not INFLUXDB_AVAILABLE or not self.token
        self.client = None
        self.write_api = None
        self.query_api = None

        # Mock data storage (for development/testing)
        self._mock_data: Dict[str, List[SensorReading]] = {}

        if not self.use_mock:
            self._connect()
        else:
            logger.info("Using mock InfluxDB implementation")

    def _connect(self):
        """Establish connection to InfluxDB."""
        try:
            self.client = InfluxDBClient(
                url=self.url,
                token=self.token,
                org=self.org
            )
            self.write_api = self.client.write_api(write_options=SYNCHRONOUS)
            self.query_api = self.client.query_api()
            logger.info(f"Connected to InfluxDB at {self.url}")
        except Exception as e:
            logger.error(f"Failed to connect to InfluxDB: {e}")
            self.use_mock = True

    def write_sensor_data(
        self,
        equipment_id: str,
        sensor_type: str,
        value: float,
        timestamp: datetime = None,
        unit: str = None,
        tags: Dict[str, str] = None
    ) -> bool:
        """
        Write a sensor reading.

        Args:
            equipment_id: Equipment identifier
            sensor_type: Type of sensor (e.g., "chw_supply_temp")
            value: Sensor value
            timestamp: Reading timestamp (default: now)
            unit: Unit of measurement
            tags: Additional tags

        Returns:
            True if write successful
        """
        timestamp = timestamp or datetime.utcnow()

        if self.use_mock:
            return self._mock_write(equipment_id, sensor_type, value, timestamp, unit)

        try:
            point = (
                Point("sensor_reading")
                .tag("equipment_id", equipment_id)
                .tag("sensor_type", sensor_type)
                .field("value", float(value))
                .time(timestamp, WritePrecision.MS)
            )

            if unit:
                point = point.tag("unit", unit)

            if tags:
                for key, val in tags.items():
                    point = point.tag(key, val)

            self.write_api.write(
                bucket=self.BUCKETS["raw"]["name"],
                org=self.org,
                record=point
            )
            return True

        except Exception as e:
            logger.error(f"Failed to write sensor data: {e}")
            return False

    def _mock_write(
        self,
        equipment_id: str,
        sensor_type: str,
        value: float,
        timestamp: datetime,
        unit: str = None
    ) -> bool:
        """Mock write for development."""
        key = f"{equipment_id}:{sensor_type}"
        if key not in self._mock_data:
            self._mock_data[key] = []

        self._mock_data[key].append(SensorReading(
            timestamp=timestamp,
            value=value,
            equipment_id=equipment_id,
            sensor_type=sensor_type,
            unit=unit
        ))
        return True

    def write_batch(
        self,
        readings: List[Dict[str, Any]],
        bucket: str = "raw"
    ) -> int:
        """
        Write multiple readings in batch.

        Args:
            readings: List of reading dicts with keys:
                     equipment_id, sensor_type, value, timestamp
            bucket: Target bucket

        Returns:
            Number of successful writes
        """
        if self.use_mock:
            count = 0
            for r in readings:
                if self._mock_write(
                    r["equipment_id"],
                    r["sensor_type"],
                    r["value"],
                    r.get("timestamp", datetime.utcnow()),
                    r.get("unit")
                ):
                    count += 1
            return count

        try:
            points = []
            for r in readings:
                point = (
                    Point("sensor_reading")
                    .tag("equipment_id", r["equipment_id"])
                    .tag("sensor_type", r["sensor_type"])
                    .field("value", float(r["value"]))
                    .time(r.get("timestamp", datetime.utcnow()), WritePrecision.MS)
                )
                if r.get("unit"):
                    point = point.tag("unit", r["unit"])
                points.append(point)

            self.write_api.write(
                bucket=self.BUCKETS[bucket]["name"],
                org=self.org,
                record=points
            )
            return len(points)

        except Exception as e:
            logger.error(f"Batch write failed: {e}")
            return 0

    def query_raw(
        self,
        equipment_id: str,
        sensor_type: str,
        start: datetime,
        end: datetime = None
    ) -> List[SensorReading]:
        """
        Query raw sensor data.

        Args:
            equipment_id: Equipment identifier
            sensor_type: Sensor type
            start: Start time
            end: End time (default: now)

        Returns:
            List of sensor readings
        """
        end = end or datetime.utcnow()

        if self.use_mock:
            return self._mock_query(equipment_id, sensor_type, start, end)

        query = f'''
        from(bucket: "{self.BUCKETS["raw"]["name"]}")
            |> range(start: {start.isoformat()}Z, stop: {end.isoformat()}Z)
            |> filter(fn: (r) => r["equipment_id"] == "{equipment_id}")
            |> filter(fn: (r) => r["sensor_type"] == "{sensor_type}")
            |> filter(fn: (r) => r["_field"] == "value")
        '''

        try:
            result = self.query_api.query(query, org=self.org)
            readings = []
            for table in result:
                for record in table.records:
                    readings.append(SensorReading(
                        timestamp=record.get_time(),
                        value=record.get_value(),
                        equipment_id=equipment_id,
                        sensor_type=sensor_type
                    ))
            return readings
        except Exception as e:
            logger.error(f"Query failed: {e}")
            return []

    def _mock_query(
        self,
        equipment_id: str,
        sensor_type: str,
        start: datetime,
        end: datetime
    ) -> List[SensorReading]:
        """Mock query for development."""
        key = f"{equipment_id}:{sensor_type}"
        if key not in self._mock_data:
            # Generate synthetic data
            return self._generate_mock_data(equipment_id, sensor_type, start, end)

        return [
            r for r in self._mock_data[key]
            if start <= r.timestamp <= end
        ]

    def _generate_mock_data(
        self,
        equipment_id: str,
        sensor_type: str,
        start: datetime,
        end: datetime,
        interval_minutes: int = 60
    ) -> List[SensorReading]:
        """Generate synthetic sensor data for testing."""
        import numpy as np
        np.random.seed(42)

        readings = []
        current = start
        hours_elapsed = 0

        while current <= end:
            # Generate realistic-looking sensor value
            base_value = 20.0
            daily_pattern = 5 * np.sin(2 * np.pi * hours_elapsed / 24)
            noise = np.random.normal(0, 0.5)
            value = base_value + daily_pattern + noise

            readings.append(SensorReading(
                timestamp=current,
                value=float(value),
                equipment_id=equipment_id,
                sensor_type=sensor_type
            ))

            current += timedelta(minutes=interval_minutes)
            hours_elapsed += interval_minutes / 60

        return readings

    def query_hourly(
        self,
        equipment_id: str,
        sensor_type: str,
        hours: int = 168
    ) -> List[Dict[str, Any]]:
        """
        Query hourly aggregated data.

        Args:
            equipment_id: Equipment identifier
            sensor_type: Sensor type
            hours: Number of hours to retrieve

        Returns:
            List of hourly readings
        """
        start = datetime.utcnow() - timedelta(hours=hours)
        end = datetime.utcnow()

        if self.use_mock:
            readings = self._generate_mock_data(
                equipment_id, sensor_type, start, end, interval_minutes=60
            )
            return [{"timestamp": r.timestamp, "value": r.value} for r in readings]

        query = f'''
        from(bucket: "{self.BUCKETS["1h"]["name"]}")
            |> range(start: -{hours}h)
            |> filter(fn: (r) => r["equipment_id"] == "{equipment_id}")
            |> filter(fn: (r) => r["sensor_type"] == "{sensor_type}")
            |> filter(fn: (r) => r["_field"] == "mean")
        '''

        try:
            result = self.query_api.query(query, org=self.org)
            return [
                {"timestamp": record.get_time(), "value": record.get_value()}
                for table in result
                for record in table.records
            ]
        except Exception as e:
            logger.error(f"Hourly query failed: {e}")
            return []

    def get_ml_training_data(
        self,
        equipment_id: str,
        sensor_types: List[str],
        days: int = 180
    ) -> Dict[str, List[float]]:
        """
        Get data formatted for ML training.

        Args:
            equipment_id: Equipment identifier
            sensor_types: List of sensor types to include
            days: Number of days of history

        Returns:
            Dict mapping sensor_type to list of hourly values
        """
        result = {}

        for sensor_type in sensor_types:
            data = self.query_hourly(equipment_id, sensor_type, hours=days * 24)
            result[sensor_type] = [d["value"] for d in data]

        return result

    def close(self):
        """Close InfluxDB connection."""
        if self.client:
            self.client.close()
            logger.info("InfluxDB connection closed")


# Singleton instance
_influxdb_service: Optional[InfluxDBService] = None


def get_influxdb_service() -> InfluxDBService:
    """Get singleton InfluxDB service."""
    global _influxdb_service
    if _influxdb_service is None:
        _influxdb_service = InfluxDBService()
    return _influxdb_service
