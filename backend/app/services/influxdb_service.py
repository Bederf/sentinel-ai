"""InfluxDB Time-Series Service.

Provides time-series data storage and retrieval for BMS sensor data.
Supports high-frequency sensor readings (1-minute resolution) with
efficient querying and ML-ready feature extraction.
"""

import os
import logging
import random
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

try:
    from influxdb_client import InfluxDBClient, Point, WritePrecision
    from influxdb_client.client.write_api import SYNCHRONOUS

    INFLUXDB_AVAILABLE = True
except ImportError:
    INFLUXDB_AVAILABLE = False

logger = logging.getLogger(__name__)

# Singleton instance
_influxdb_service: Optional["InfluxDBService"] = None


@dataclass
class SensorReading:
    """Sensor reading with timestamp and value."""

    timestamp: datetime
    value: float
    equipment_id: str = ""
    sensor_type: str = ""


class InfluxDBService:
    """Service for InfluxDB time-series operations.

    Handles sensor data writes and queries with support for:
    - Raw data (1-minute resolution, 30-day retention)
    - Hourly aggregates (1-year retention)
    - Daily aggregates (5-year retention)
    """

    # Bucket configurations
    BUCKETS = {
        "raw": {"name": "sensor_data_raw", "retention": "30d", "description": "Raw sensor data at 1-minute resolution"},
        "hourly": {"name": "sensor_data_1h", "retention": "365d", "description": "Hourly aggregated sensor data"},
        "daily": {
            "name": "sensor_data_1d",
            "retention": "1825d",
            "description": "Daily aggregated sensor data (5 years)",
        },
    }

    def __init__(
        self,
        url: Optional[str] = None,
        token: Optional[str] = None,
        org: Optional[str] = None,
        bucket: Optional[str] = None,
    ):
        """Initialize InfluxDB connection.

        Args:
            url: InfluxDB URL (default: INFLUXDB_URL env var)
            token: Authentication token (default: INFLUXDB_TOKEN env var)
            org: Organization name (default: INFLUXDB_ORG env var)
            bucket: Default bucket (default: INFLUXDB_BUCKET env var)
        """
        self.url = url or os.getenv("INFLUXDB_URL", "http://localhost:8086")
        self.token = token or os.getenv("INFLUXDB_TOKEN", "")
        self.org = org or os.getenv("INFLUXDB_ORG", "bms-intelligence")
        self.bucket = bucket or os.getenv("INFLUXDB_BUCKET", "sensor_data_raw")

        # Use mock mode if InfluxDB client not available or token empty
        self.use_mock = not INFLUXDB_AVAILABLE or not self.token
        self._mock_data: Dict[str, List[SensorReading]] = {}

        self._client: Optional["InfluxDBClient"] = None
        self._write_api = None
        self._query_api = None

        if self.use_mock:
            logger.info("InfluxDB service running in mock mode")

    def _ensure_connected(self) -> None:
        """Ensure InfluxDB client is connected."""
        if self.use_mock:
            return

        if self._client is None:
            self._client = InfluxDBClient(url=self.url, token=self.token, org=self.org)
            self._write_api = self._client.write_api(write_options=SYNCHRONOUS)
            self._query_api = self._client.query_api()
            logger.info(f"Connected to InfluxDB at {self.url}")

    def health_check(self) -> Dict[str, Any]:
        """Check InfluxDB connection health.

        Returns:
            Dict with status and details
        """
        if self.use_mock:
            return {
                "status": "ok",
                "message": "Mock mode - no InfluxDB connection",
                "mode": "mock",
                "url": self.url,
                "org": self.org,
            }

        try:
            self._ensure_connected()
            health = self._client.health()
            return {
                "status": "ok" if health.status == "pass" else "error",
                "message": health.message or "InfluxDB is healthy",
                "version": health.version,
                "url": self.url,
                "org": self.org,
            }
        except Exception as e:
            logger.error(f"InfluxDB health check failed: {e}")
            return {"status": "error", "message": str(e), "url": self.url, "org": self.org}

    def write_sensor_data(
        self,
        equipment_id: str,
        sensor_type: str,
        value: float,
        timestamp: Optional[datetime] = None,
        unit: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
    ) -> bool:
        """Write a sensor reading (API-compatible signature).

        Args:
            equipment_id: Equipment identifier
            sensor_type: Type of sensor
            value: Sensor reading value
            timestamp: Reading timestamp (default: now)
            unit: Unit of measurement (optional)
            tags: Additional tags (optional)

        Returns:
            True if write succeeded
        """
        ts = timestamp or datetime.utcnow()

        if self.use_mock:
            key = f"{equipment_id}:{sensor_type}"
            if key not in self._mock_data:
                self._mock_data[key] = []
            self._mock_data[key].append(
                SensorReading(timestamp=ts, value=value, equipment_id=equipment_id, sensor_type=sensor_type)
            )
            return True

        return self.write_sensor_reading(
            building_id=tags.get("building", "default") if tags else "default",
            equipment_id=equipment_id,
            sensor_type=sensor_type,
            value=value,
            unit=unit,
            timestamp=ts,
        )

    def query_raw(
        self, equipment_id: str, sensor_type: str, start: datetime, end: Optional[datetime] = None
    ) -> List[SensorReading]:
        """Query raw sensor data.

        Args:
            equipment_id: Equipment identifier
            sensor_type: Sensor type to query
            start: Start time
            end: End time (default: now)

        Returns:
            List of SensorReading objects
        """
        end = end or datetime.utcnow()

        if self.use_mock:
            key = f"{equipment_id}:{sensor_type}"
            if key not in self._mock_data:
                # Generate mock data
                return self._generate_mock_readings(equipment_id, sensor_type, start, end)
            return [r for r in self._mock_data[key] if start <= r.timestamp <= end]

        data = self.query_sensor_data(equipment_id, sensor_type, start, end)
        return [
            SensorReading(
                timestamp=d["timestamp"], value=d["value"], equipment_id=equipment_id, sensor_type=sensor_type
            )
            for d in data
        ]

    def query_hourly(self, equipment_id: str, sensor_type: str, hours: int = 168) -> List[Dict[str, Any]]:
        """Query hourly aggregated data.

        Args:
            equipment_id: Equipment identifier
            sensor_type: Sensor type to query
            hours: Hours of history (default: 168 = 7 days)

        Returns:
            List of dicts with timestamp and value
        """
        if self.use_mock:
            return self._generate_mock_hourly(equipment_id, sensor_type, hours)

        try:
            self._ensure_connected()
            start = datetime.utcnow() - timedelta(hours=hours)

            query = f'''
                from(bucket: "{self.BUCKETS["hourly"]["name"]}")
                |> range(start: {start.isoformat()}Z)
                |> filter(fn: (r) => r._measurement == "sensor_reading_1h")
                |> filter(fn: (r) => r.equipment == "{equipment_id}")
                |> filter(fn: (r) => r.sensor_type == "{sensor_type}")
                |> sort(columns: ["_time"])
            '''

            result = self._query_api.query(query)

            data = []
            for table in result:
                for record in table.records:
                    data.append({"timestamp": record.get_time(), "value": record.get_value()})

            return data

        except Exception as e:
            logger.error(f"Failed to query hourly data: {e}")
            return self._generate_mock_hourly(equipment_id, sensor_type, hours)

    def get_ml_training_data(
        self, equipment_id: str, sensor_types: List[str], days: int = 180
    ) -> Dict[str, List[float]]:
        """Get data formatted for ML training.

        Args:
            equipment_id: Equipment identifier
            sensor_types: List of sensor types to include
            days: Days of history

        Returns:
            Dict mapping sensor type to list of values
        """
        data = {}
        hours = days * 24

        for sensor_type in sensor_types:
            hourly = self.query_hourly(equipment_id, sensor_type, hours)
            data[sensor_type] = [d["value"] for d in hourly]

        return data

    def _generate_mock_readings(
        self, equipment_id: str, sensor_type: str, start: datetime, end: datetime
    ) -> List[SensorReading]:
        """Generate mock sensor readings for demo."""
        readings = []
        current = start
        base_value = self._get_base_value(sensor_type)

        while current <= end:
            # Add some variation
            value = base_value + random.uniform(-5, 5)
            readings.append(
                SensorReading(
                    timestamp=current, value=round(value, 2), equipment_id=equipment_id, sensor_type=sensor_type
                )
            )
            current += timedelta(minutes=1)

        return readings

    def _generate_mock_hourly(self, equipment_id: str, sensor_type: str, hours: int) -> List[Dict[str, Any]]:
        """Generate mock hourly data for demo."""
        data = []
        base_value = self._get_base_value(sensor_type)
        current = datetime.utcnow() - timedelta(hours=hours)

        for _ in range(hours):
            value = base_value + random.uniform(-3, 3)
            data.append({"timestamp": current, "value": round(value, 2)})
            current += timedelta(hours=1)

        return data

    def _get_base_value(self, sensor_type: str) -> float:
        """Get base value for a sensor type in mock mode."""
        base_values = {
            "temperature": 22.0,
            "humidity": 45.0,
            "pressure": 101.3,
            "vibration_rms": 2.5,
            "current": 15.0,
            "voltage": 400.0,
            "power": 5000.0,
            "flow_rate": 100.0,
        }
        return base_values.get(sensor_type, 50.0)

    def write_sensor_reading(
        self,
        building_id: str,
        equipment_id: str,
        sensor_type: str,
        value: float,
        unit: Optional[str] = None,
        timestamp: Optional[datetime] = None,
    ) -> bool:
        """Write a single sensor reading.

        Args:
            building_id: Building identifier
            equipment_id: Equipment identifier
            sensor_type: Type of sensor (e.g., "temperature", "vibration_rms")
            value: Sensor reading value
            unit: Unit of measurement (optional)
            timestamp: Reading timestamp (default: now)

        Returns:
            True if write succeeded
        """
        ts = timestamp or datetime.utcnow()

        if self.use_mock:
            key = f"{equipment_id}:{sensor_type}"
            if key not in self._mock_data:
                self._mock_data[key] = []
            self._mock_data[key].append(
                SensorReading(timestamp=ts, value=value, equipment_id=equipment_id, sensor_type=sensor_type)
            )
            logger.debug(f"Mock wrote sensor reading: {equipment_id}/{sensor_type}={value}")
            return True

        try:
            self._ensure_connected()

            point = (
                Point("sensor_reading")
                .tag("building", building_id)
                .tag("equipment", equipment_id)
                .tag("sensor_type", sensor_type)
                .field("value", float(value))
            )

            if unit:
                point = point.tag("unit", unit)

            point = point.time(ts, WritePrecision.S)

            self._write_api.write(bucket=self.bucket, record=point)
            logger.debug(f"Wrote sensor reading: {equipment_id}/{sensor_type}={value}")
            return True

        except Exception as e:
            logger.error(f"Failed to write sensor reading: {e}")
            return False

    def write_batch(self, readings: List[Dict[str, Any]]) -> int:
        """Write multiple sensor readings in batch.

        Args:
            readings: List of reading dicts with keys:
                - building_id (optional), equipment_id, sensor_type, value
                - Optional: unit, timestamp

        Returns:
            Number of successful writes
        """
        if self.use_mock:
            for reading in readings:
                equipment_id = reading["equipment_id"]
                sensor_type = reading["sensor_type"]
                key = f"{equipment_id}:{sensor_type}"
                if key not in self._mock_data:
                    self._mock_data[key] = []
                self._mock_data[key].append(
                    SensorReading(
                        timestamp=reading.get("timestamp", datetime.utcnow()),
                        value=reading["value"],
                        equipment_id=equipment_id,
                        sensor_type=sensor_type,
                    )
                )
            logger.info(f"Mock wrote batch of {len(readings)} sensor readings")
            return len(readings)

        try:
            self._ensure_connected()

            points = []
            for reading in readings:
                point = (
                    Point("sensor_reading")
                    .tag("building", reading.get("building_id", "default"))
                    .tag("equipment", reading["equipment_id"])
                    .tag("sensor_type", reading["sensor_type"])
                    .field("value", float(reading["value"]))
                )

                if reading.get("unit"):
                    point = point.tag("unit", reading["unit"])

                timestamp = reading.get("timestamp", datetime.utcnow())
                point = point.time(timestamp, WritePrecision.S)
                points.append(point)

            self._write_api.write(bucket=self.bucket, record=points)
            logger.info(f"Wrote batch of {len(points)} sensor readings")
            return len(points)

        except Exception as e:
            logger.error(f"Failed to write batch: {e}")
            return 0

    def query_sensor_data(
        self,
        equipment_id: str,
        sensor_type: Optional[str] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        bucket: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Query sensor data for an equipment.

        Args:
            equipment_id: Equipment identifier
            sensor_type: Filter by sensor type (optional)
            start: Query start time (default: 24 hours ago)
            end: Query end time (default: now)
            bucket: Bucket to query (default: raw data bucket)

        Returns:
            List of sensor readings
        """
        start = start or (datetime.utcnow() - timedelta(hours=24))
        end = end or datetime.utcnow()

        if self.use_mock:
            # Return mock data
            if sensor_type:
                key = f"{equipment_id}:{sensor_type}"
                if key in self._mock_data:
                    readings = [r for r in self._mock_data[key] if start <= r.timestamp <= end]
                else:
                    readings = self._generate_mock_readings(equipment_id, sensor_type, start, end)
                return [
                    {
                        "timestamp": r.timestamp,
                        "building_id": "default",
                        "equipment_id": r.equipment_id,
                        "sensor_type": r.sensor_type,
                        "value": r.value,
                        "unit": None,
                    }
                    for r in readings
                ]
            else:
                # Return all sensor types for this equipment
                all_readings = []
                for key, readings in self._mock_data.items():
                    if key.startswith(f"{equipment_id}:"):
                        all_readings.extend(
                            [
                                {
                                    "timestamp": r.timestamp,
                                    "building_id": "default",
                                    "equipment_id": r.equipment_id,
                                    "sensor_type": r.sensor_type,
                                    "value": r.value,
                                    "unit": None,
                                }
                                for r in readings
                                if start <= r.timestamp <= end
                            ]
                        )
                return all_readings

        try:
            self._ensure_connected()

            bucket = bucket or self.bucket

            # Build Flux query
            query = f'''
                from(bucket: "{bucket}")
                |> range(start: {start.isoformat()}Z, stop: {end.isoformat()}Z)
                |> filter(fn: (r) => r._measurement == "sensor_reading")
                |> filter(fn: (r) => r.equipment == "{equipment_id}")
            '''

            if sensor_type:
                query += f'''
                |> filter(fn: (r) => r.sensor_type == "{sensor_type}")
                '''

            query += """
                |> sort(columns: ["_time"])
            """

            result = self._query_api.query(query)

            readings = []
            for table in result:
                for record in table.records:
                    readings.append(
                        {
                            "timestamp": record.get_time(),
                            "building_id": record.values.get("building"),
                            "equipment_id": record.values.get("equipment"),
                            "sensor_type": record.values.get("sensor_type"),
                            "value": record.get_value(),
                            "unit": record.values.get("unit"),
                        }
                    )

            return readings

        except Exception as e:
            logger.error(f"Failed to query sensor data: {e}")
            return []

    def get_equipment_features(self, equipment_id: str, window_days: int = 7) -> Dict[str, Any]:
        """Get ML features for an equipment.

        Computes statistical features over a time window:
        - mean, std, min, max for each sensor type
        - reading count and completeness

        Args:
            equipment_id: Equipment identifier
            window_days: Time window in days (default: 7)

        Returns:
            Dict of features per sensor type
        """
        try:
            self._ensure_connected()

            start = datetime.utcnow() - timedelta(days=window_days)

            query = f'''
                from(bucket: "{self.bucket}")
                |> range(start: {start.isoformat()}Z)
                |> filter(fn: (r) => r._measurement == "sensor_reading")
                |> filter(fn: (r) => r.equipment == "{equipment_id}")
                |> group(columns: ["sensor_type"])
            '''

            result = self._query_api.query(query)

            features = {
                "equipment_id": equipment_id,
                "window_days": window_days,
                "computed_at": datetime.utcnow().isoformat(),
                "sensors": {},
            }

            for table in result:
                if not table.records:
                    continue

                sensor_type = table.records[0].values.get("sensor_type")
                values = [r.get_value() for r in table.records if r.get_value() is not None]

                if values:
                    features["sensors"][sensor_type] = {
                        "count": len(values),
                        "mean": sum(values) / len(values),
                        "min": min(values),
                        "max": max(values),
                        "std": self._std(values),
                        "last_value": values[-1] if values else None,
                        "last_timestamp": table.records[-1].get_time().isoformat() if table.records else None,
                    }

            return features

        except Exception as e:
            logger.error(f"Failed to get equipment features: {e}")
            return {"equipment_id": equipment_id, "error": str(e), "sensors": {}}

    def _std(self, values: List[float]) -> float:
        """Calculate standard deviation."""
        if len(values) < 2:
            return 0.0
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
        return variance**0.5

    def close(self) -> None:
        """Close InfluxDB connection."""
        if self._client:
            self._client.close()
            self._client = None
            self._write_api = None
            self._query_api = None
            logger.info("Closed InfluxDB connection")


def get_influxdb_service() -> InfluxDBService:
    """Get singleton InfluxDB service instance.

    Returns:
        InfluxDBService instance
    """
    global _influxdb_service

    if _influxdb_service is None:
        _influxdb_service = InfluxDBService()

    return _influxdb_service
