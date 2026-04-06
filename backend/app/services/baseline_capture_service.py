"""
Baseline Capture Service (Phase 54-02)

Multi-source baseline data capture for equipment baseline assessment.

Supports three capture sources:
- manual: Engineer manual measurement and entry
- device: Live BMS device readings via device_abstraction layer
- sensor_analysis: Phone sensor baselines (vibration, audio)

This service normalizes data from different sources, applies default tolerances,
and integrates with the existing baseline_service for storage.

Phase 54: Equipment Baseline Assessment - Wave 1 (Parallel with 54-01, 54-03)
"""

import logging
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# Import baseline models
from app.models.baseline import BaselineSource, BaselineStatus, BaselineType, EquipmentBaseline

# Import existing services
try:
    from app.services.baseline_comparator import get_baseline_comparator
    from app.services.baseline_service import BaselineService
    from app.services.device_abstraction import DeviceManager
    from app.services.safety_interlocks import safety_engine
except ImportError as e:
    # Fallback for development
    logging.warning(f"Import error in baseline_capture_service: {e}")
    DeviceManager = None
    get_baseline_comparator = None
    BaselineService = None
    safety_engine = None

logger = logging.getLogger(__name__)


# ============================================================================
# Exception Classes
# ============================================================================


class BaselineCaptureError(Exception):
    """Base exception for baseline capture errors."""

    pass


class EquipmentNotFound(BaselineCaptureError):
    """Raised when equipment_id does not exist."""

    pass


class InvalidBaselineData(BaselineCaptureError):
    """Raised when baseline data is malformed or invalid."""

    pass


class DeviceNotAvailable(BaselineCaptureError):
    """Raised when device source is requested but device_manager not initialized."""

    pass


class SensorDataNotAvailable(BaselineCaptureError):
    """Raised when sensor_analysis source is requested but no baseline exists."""

    pass


# ============================================================================
# Baseline Element Structure
# ============================================================================


class BaselineElement(BaseModel):
    """Single baseline element with value, unit, and tolerance."""

    model_config = ConfigDict(
        json_schema_extra={"example": {"value": 7.2, "unit": "°C", "tolerance": 2.0, "tolerance_type": "absolute"}}
    )

    value: float = Field(..., description="Baseline value")
    unit: str = Field(..., description="Measurement unit (°C, PSI, mm/s, etc.)")
    tolerance: float = Field(..., description="Acceptable deviation (absolute or %)")
    tolerance_type: str = Field(default="percent", description="Tolerance type: 'percent' or 'absolute'")


# ============================================================================
# BaselineCaptureService
# ============================================================================


class BaselineCaptureService:
    """
    Multi-source baseline capture service.

    Normalizes baseline data from multiple sources:
    - Manual entry by engineer
    - Live BMS device readings
    - Phone sensor analysis (vibration, audio)

    Applies intelligent default tolerances based on equipment type.
    """

    # Default tolerances per equipment_type
    DEFAULT_TOLERANCES = {
        "chiller": {
            "temperature": 2.0,  # ±2°C
            "pressure": 10,  # ±10%
            "vibration": 0.3,  # ±0.3 mm/s
            "current": 15,  # ±15%
            "flow_rate": 10,  # ±10%
        },
        "generator": {
            "temperature": 5.0,  # ±5°C
            "pressure": 15,  # ±15%
            "vibration": 0.5,  # ±0.5 mm/s
            "frequency": 2,  # ±2 Hz
            "voltage": 5,  # ±5%
        },
        "ahu": {
            "temperature": 3.0,  # ±3°C
            "filter_dp": 50,  # ±50 Pa (absolute)
            "vibration": 0.4,  # ±0.4 mm/s
            "current": 12,  # ±12%
        },
        "fcu": {
            "temperature": 3.0,  # ±3°C
            "filter_dp": 30,  # ±30 Pa (absolute)
            "vibration": 0.5,  # ±0.5 mm/s
            "airflow": 15,  # ±15%
        },
        "pump": {
            "temperature": 5.0,  # ±5°C
            "pressure": 15,  # ±15%
            "vibration": 0.5,  # ±0.5 mm/s
            "flow_rate": 12,  # ±12%
        },
        "default": {
            "temperature": 5.0,  # ±5°C
            "pressure": 15,  # ±15%
            "vibration": 0.5,  # ±0.5 mm/s
            "current": 15,  # ±15%
            "generic": 10,  # ±10% for any other metric
        },
    }

    # Sensor baseline tolerances (phone sensors)
    SENSOR_TOLERANCES = {
        "vibration_rms": 20,  # ±20%
        "vibration_peak": 15,  # ±15%
        "frequency_peak": 15,  # ±15%
        "audio_level": 10,  # ±10% dBA
        "noise_floor": 10,  # ±10% dBA
    }

    # Point mappings from device_point names to baseline elements
    DEVICE_POINT_MAPPINGS = {
        # Temperature points
        "discharge_temp": {"element": "discharge_temp", "unit": "°C", "type": "temperature"},
        "suction_temp": {"element": "suction_temp", "unit": "°C", "type": "temperature"},
        "condenser_temp": {"element": "condenser_temp", "unit": "°C", "type": "temperature"},
        "evaporator_temp": {"element": "evaporator_temp", "unit": "°C", "type": "temperature"},
        "oil_temp": {"element": "oil_temp", "unit": "°C", "type": "temperature"},
        "bearing_temp": {"element": "bearing_temp", "unit": "°C", "type": "temperature"},
        # Pressure points
        "suction_pressure": {"element": "suction_pressure", "unit": "PSI", "type": "pressure"},
        "discharge_pressure": {"element": "discharge_pressure", "unit": "PSI", "type": "pressure"},
        "oil_pressure": {"element": "oil_pressure", "unit": "PSI", "type": "pressure"},
        "head_pressure": {"element": "head_pressure", "unit": "PSI", "type": "pressure"},
        # Vibration points
        "vibration": {"element": "vibration", "unit": "mm/s", "type": "vibration"},
        "vibration_x": {"element": "vibration_x", "unit": "mm/s", "type": "vibration"},
        "vibration_y": {"element": "vibration_y", "unit": "mm/s", "type": "vibration"},
        "vibration_z": {"element": "vibration_z", "unit": "mm/s", "type": "vibration"},
        # Filter differential pressure
        "filter_dp": {"element": "filter_dp", "unit": "Pa", "type": "filter_dp"},
        # Electrical points
        "current": {"element": "motor_current", "unit": "A", "type": "current"},
        "motor_current": {"element": "motor_current", "unit": "A", "type": "current"},
        "voltage": {"element": "voltage", "unit": "V", "type": "voltage"},
        # Flow points
        "flow_rate": {"element": "flow_rate", "unit": "L/s", "type": "flow_rate"},
        "chw_flow": {"element": "chw_flow", "unit": "L/s", "type": "flow_rate"},
        # Frequency points
        "frequency": {"element": "frequency", "unit": "Hz", "type": "frequency"},
        "running_speed": {"element": "running_speed", "unit": "RPM", "type": "generic"},
    }

    def __init__(self):
        """Initialize the baseline capture service."""
        self.device_manager = None
        self.baseline_comparator = None
        self._initialize_integrations()

    def _initialize_integrations(self):
        """Initialize optional integrations (device_manager, sensor_analysis)."""
        # Try to initialize device manager (uses __new__ singleton)
        if DeviceManager:
            try:
                self.device_manager = DeviceManager()
                if hasattr(self.device_manager, "initialized") and not self.device_manager.initialized:
                    logger.warning("Device manager available but not initialized")
            except Exception as e:
                logger.warning(f"Could not initialize device manager: {e}")
                self.device_manager = None

        # Try to initialize baseline comparator
        if get_baseline_comparator:
            try:
                self.baseline_comparator = get_baseline_comparator()
            except Exception as e:
                logger.warning(f"Could not initialize baseline comparator: {e}")
                self.baseline_comparator = None

    async def capture_equipment_baseline(
        self,
        equipment_id: str,
        source: BaselineSource,
        data: dict[str, Any] | None = None,
        captured_by: str = "unknown",
        baseline_type: BaselineType = BaselineType.INITIAL,
        notes: str | None = None,
        measurement_conditions: dict[str, Any] | None = None,
    ) -> EquipmentBaseline:
        """
        Capture baseline from specified source.

        Args:
            equipment_id: Equipment identifier (e.g., "S002-CHILLER-B1-001")
            source: Data source (manual, device, sensor_analysis)
            data: Source-specific data:
                - manual: Dict of baseline_values
                - device: Optional dict with specific point_names to read
                - sensor_analysis: Optional dict with recording_id
            captured_by: Engineer name or 'automated'
            baseline_type: Type of baseline (initial, periodic, post_repair)
            notes: Engineer notes
            measurement_conditions: Context (load, ambient, etc.)

        Returns:
            EquipmentBaseline model with normalized data

        Raises:
            EquipmentNotFound: If equipment_id doesn't exist
            InvalidBaselineData: If data is malformed
            DeviceNotAvailable: If device source and device_manager not ready
            SensorDataNotAvailable: If sensor_analysis source and no baseline exists
        """
        logger.info(f"Capturing {source} baseline for equipment {equipment_id}")

        # Validate equipment exists (try to fetch from repository or device manager)
        equipment_exists = await self._validate_equipment_exists(equipment_id)
        if not equipment_exists:
            raise EquipmentNotFound(f"Equipment {equipment_id} not found")

        # Normalize data based on source
        if source == BaselineSource.MANUAL:
            baseline_elements = await self._normalize_from_manual(equipment_id, data or {})
        elif source == BaselineSource.BMS_AVERAGE:
            baseline_elements = await self._normalize_from_device(equipment_id, data or {})
        elif source == BaselineSource.MOBILE_SENSOR:
            baseline_elements = await self._normalize_from_sensor_analysis(equipment_id, data or {})
        else:
            raise InvalidBaselineData(f"Unsupported source: {source}")

        # Apply default tolerances if not provided
        equipment_type = await self._get_equipment_type(equipment_id)
        baseline_elements = self._apply_default_tolerances(equipment_type, baseline_elements)

        # Convert to baseline_values dict format for EquipmentBaseline
        baseline_values = {}
        for element_name, element in baseline_elements.items():
            baseline_values[element_name] = {
                "value": element.value,
                "unit": element.unit,
                "tolerance": element.tolerance,
                "tolerance_type": element.tolerance_type,
            }

        # Create EquipmentBaseline model (will be saved by caller via baseline_service)
        baseline = EquipmentBaseline(
            id=f"baseline-{equipment_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            equipment_id=equipment_id,
            baseline_date=datetime.now(),
            captured_by=captured_by,
            baseline_type=baseline_type,
            status=BaselineStatus.ACTIVE,
            baseline_values=baseline_values,
            measurement_conditions=measurement_conditions or {},
            source_type=source,
            notes=notes,
            attachment_urls=[],
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        logger.info(f"Baseline captured for {equipment_id}: {len(baseline_elements)} elements")
        return baseline

    async def _validate_equipment_exists(self, equipment_id: str) -> bool:
        """Validate that equipment exists in the system."""
        # Try device manager first
        if self.device_manager and self.device_manager.initialized:
            try:
                device = await self.device_manager.get_device(equipment_id)
                if device:
                    return True
            except Exception as e:
                logger.debug(f"Could not fetch device from device_manager: {e}")

        # Try repository
        try:
            from app.database.repositories.equipment_repository import EquipmentRepository

            repo = EquipmentRepository()
            equipment = await repo.get_equipment(equipment_id)
            if equipment:
                return True
        except Exception as e:
            logger.debug(f"Could not fetch equipment from repository: {e}")

        # Try JSON fallback (reference devices in bms_simulator/data/)
        try:
            import json as _json
            from pathlib import Path as _Path

            _ref_path = _Path(__file__).parent / "bms_simulator" / "data" / "reference_devices.json"
            if _ref_path.exists():
                devices = _json.loads(_ref_path.read_text())
                for device in devices:
                    if device.get("device_id") == equipment_id or device.get("id") == equipment_id:
                        return True
        except Exception as e:
            logger.debug(f"Could not fetch equipment from JSON: {e}")

        return False

    async def _normalize_from_manual(
        self, equipment_id: str, manual_data: dict[str, Any]
    ) -> dict[str, BaselineElement]:
        """
        Normalize manual entry data to baseline elements.

        Args:
            equipment_id: Equipment identifier
            manual_data: Manual measurements with values and optional units/tolerances

        Returns:
            Dict of element_name -> BaselineElement
        """
        elements = {}

        for key, value in manual_data.items():
            if not isinstance(value, (int, float, dict)):
                logger.warning(f"Skipping invalid manual data: {key}={value}")
                continue

            # Extract value, unit, tolerance from dict or scalar
            if isinstance(value, dict):
                val = value.get("value")
                unit = value.get("unit", "")
                tolerance = value.get("tolerance")
                tolerance_type = value.get("tolerance_type", "percent")
            else:
                val = value
                unit = ""  # Unknown unit from manual entry
                tolerance = None  # Will apply default later
                tolerance_type = "percent"

            if val is None:
                continue

            # Create element (tolerance will be applied by _apply_default_tolerances)
            elements[key] = BaselineElement(
                value=float(val),
                unit=unit,
                tolerance=tolerance or 0,  # Placeholder
                tolerance_type=tolerance_type,
            )

        logger.info(f"Normalized {len(elements)} manual baseline elements for {equipment_id}")
        return elements

    async def _normalize_from_device(
        self, equipment_id: str, device_data: dict[str, Any] | None
    ) -> dict[str, BaselineElement]:
        """
        Normalize BMS device readings to baseline elements.

        Args:
            equipment_id: Equipment identifier
            device_data: Optional dict with 'point_names' list to read specific points

        Returns:
            Dict of element_name -> BaselineElement

        Raises:
            DeviceNotAvailable: If device_manager not initialized
        """
        if not self.device_manager or not self.device_manager.initialized:
            raise DeviceNotAvailable("Device manager not initialized. Cannot capture baseline from device source.")

        elements = {}
        points_to_read = None

        # Extract specific points if provided
        if device_data and "point_names" in device_data:
            points_to_read = device_data["point_names"]

        try:
            # Get device
            device = await self.device_manager.get_device(equipment_id)
            if not device:
                raise EquipmentNotFound(f"Device {equipment_id} not found in device manager")

            # Get all points
            points_dict = await device.get_points()

            # Filter to requested points or read all
            if points_to_read:
                points_to_read_filtered = {k: v for k, v in points_dict.items() if k in points_to_read}
            else:
                points_to_read_filtered = points_dict

            # Read each point and map to baseline element
            for point_name, point_info in points_to_read_filtered.items():
                try:
                    # Read current value
                    device_value = await device.read_value(point_name)
                    if device_value is None or device_value.value is None:
                        logger.warning(f"Could not read point {point_name} for {equipment_id}")
                        continue

                    # Map to baseline element using point mappings
                    mapping = self.DEVICE_POINT_MAPPINGS.get(point_name)
                    if not mapping:
                        # Use point_name as-is with unknown unit
                        logger.debug(f"No mapping for point {point_name}, using raw name")
                        element_name = point_name
                        unit = point_info.unit if hasattr(point_info, "unit") else ""
                        _metric_type = "generic"
                    else:
                        element_name = mapping["element"]
                        unit = mapping["unit"]
                        _metric_type = mapping["type"]

                    # Create element (tolerance will be applied later)
                    elements[element_name] = BaselineElement(
                        value=float(device_value.value),
                        unit=unit,
                        tolerance=0,  # Placeholder
                        tolerance_type="percent",
                    )

                except Exception as e:
                    logger.error(f"Error reading point {point_name}: {e}")
                    # Continue with other points
                    continue

            logger.info(f"Normalized {len(elements)} device baseline elements for {equipment_id}")
            return elements

        except Exception as e:
            logger.error(f"Error normalizing from device for {equipment_id}: {e}")
            raise InvalidBaselineData(f"Failed to read device data: {e}")

    async def _normalize_from_sensor_analysis(
        self, equipment_id: str, sensor_data: dict[str, Any] | None
    ) -> dict[str, BaselineElement]:
        """
        Normalize phone sensor baseline data to baseline elements.

        Args:
            equipment_id: Equipment identifier
            sensor_data: Optional dict with 'recording_id' to fetch specific recording

        Returns:
            Dict of element_name -> BaselineElement

        Raises:
            SensorDataNotAvailable: If no baseline exists in sensor_analysis
        """
        if not self.baseline_comparator:
            raise SensorDataNotAvailable("Baseline comparator not available. Cannot capture sensor baseline.")

        try:
            # Try to get sensor baseline from sensor_analysis service
            from app.services.sensor_analysis.baseline_comparator import get_baseline_comparator

            comparator = get_baseline_comparator()
            baseline = await comparator.get_baseline(equipment_id)

            if not baseline:
                raise SensorDataNotAvailable(
                    f"No sensor baseline found for equipment {equipment_id}. "
                    f"Capture sensor baseline first via /api/sensor-analysis/baseline/{equipment_id}"
                )

            elements = {}

            # Extract vibration data
            if "vibration" in baseline:
                vib = baseline["vibration"]
                if "overall_rms" in vib:
                    elements["vibration_rms"] = BaselineElement(
                        value=float(vib["overall_rms"]),
                        unit="mm/s",
                        tolerance=self.SENSOR_TOLERANCES["vibration_rms"],
                        tolerance_type="percent",
                    )

                # Extract frequency peaks
                if "peaks" in vib and isinstance(vib["peaks"], list):
                    for i, peak in enumerate(vib["peaks"]):
                        if isinstance(peak, dict) and "frequency" in peak:
                            peak_name = f"vibration_peak_{i + 1}"
                            elements[peak_name] = BaselineElement(
                                value=float(peak["frequency"]),
                                unit="Hz",
                                tolerance=self.SENSOR_TOLERANCES["frequency_peak"],
                                tolerance_type="percent",
                            )

            # Extract audio data
            if "audio" in baseline:
                audio = baseline["audio"]
                if "decibel_level" in audio:
                    elements["audio_level"] = BaselineElement(
                        value=float(audio["decibel_level"]),
                        unit="dBA",
                        tolerance=self.SENSOR_TOLERANCES["audio_level"],
                        tolerance_type="percent",
                    )

                if "noise_floor" in audio:
                    elements["noise_floor"] = BaselineElement(
                        value=float(audio["noise_floor"]),
                        unit="dBA",
                        tolerance=self.SENSOR_TOLERANCES["noise_floor"],
                        tolerance_type="percent",
                    )

            logger.info(f"Normalized {len(elements)} sensor baseline elements for {equipment_id}")
            return elements

        except SensorDataNotAvailable:
            raise
        except Exception as e:
            logger.error(f"Error normalizing from sensor analysis for {equipment_id}: {e}")
            raise InvalidBaselineData(f"Failed to read sensor data: {e}")

    def _apply_default_tolerances(
        self, equipment_type: str, elements: dict[str, BaselineElement]
    ) -> dict[str, BaselineElement]:
        """
        Apply default tolerances based on equipment type and metric type.

        Args:
            equipment_type: Equipment type (chiller, ahu, generator, etc.)
            elements: Dict of baseline elements (may have placeholder tolerances)

        Returns:
            Dict with tolerances applied
        """
        # Get tolerance config for equipment type
        tolerance_config = self.DEFAULT_TOLERANCES.get(equipment_type, self.DEFAULT_TOLERANCES["default"])

        # Apply tolerances to elements without explicit tolerances
        for element_name, element in elements.items():
            # Skip if tolerance already set (explicitly provided)
            if element.tolerance != 0:
                continue

            # Determine metric type from element name or unit
            metric_type = self._determine_metric_type(element_name, element.unit)

            # Get default tolerance
            default_tolerance = tolerance_config.get(metric_type)
            if default_tolerance is None:
                default_tolerance = tolerance_config.get("generic", 10)

            # Update element with default tolerance
            element.tolerance = default_tolerance

            # Use absolute tolerance for temperature and filter_dp
            if metric_type in ["temperature", "filter_dp"]:
                element.tolerance_type = "absolute"
            else:
                element.tolerance_type = "percent"

        return elements

    def _determine_metric_type(self, element_name: str, unit: str) -> str:
        """Determine metric type from element name or unit."""
        element_lower = element_name.lower()

        # Check by name
        if "temp" in element_lower:
            return "temperature"
        elif "pressure" in element_lower:
            return "pressure"
        elif "vibration" in element_lower or "vib" in element_lower:
            return "vibration"
        elif "current" in element_lower:
            return "current"
        elif "flow" in element_lower:
            return "flow_rate"
        elif "filter_dp" in element_lower or "filter_dp" in element_lower:
            return "filter_dp"
        elif "freq" in element_lower:
            return "frequency"
        elif "voltage" in element_lower:
            return "voltage"

        # Check by unit
        if unit == "°C" or unit == "C":
            return "temperature"
        elif unit == "PSI" or unit == "Pa" or unit == "Bar":
            return "pressure"
        elif unit == "mm/s":
            return "vibration"
        elif unit == "A" or unit == "Amps":
            return "current"
        elif unit == "L/s" or unit == "m3/h":
            return "flow_rate"
        elif unit == "Hz":
            return "frequency"
        elif unit == "V" or unit == "Volts":
            return "voltage"

        return "generic"

    async def _get_equipment_type(self, equipment_id: str) -> str:
        """Get equipment type from device or repository."""
        # Try device manager first
        if self.device_manager and self.device_manager.initialized:
            try:
                device = await self.device_manager.get_device(equipment_id)
                if device and hasattr(device, "device"):
                    # Extract equipment type from device properties
                    device_type = device.device.type if hasattr(device.device, "type") else None
                    if device_type:
                        # Map device type to equipment type
                        return self._map_device_type_to_equipment_type(device_type.value)
            except Exception as e:
                logger.debug(f"Could not get equipment type from device manager: {e}")

        # Try repository
        try:
            from app.database.repositories.equipment_repository import EquipmentRepository

            repo = EquipmentRepository()
            equipment = await repo.get_equipment(equipment_id)
            if equipment and hasattr(equipment, "equipment_type"):
                return self._map_device_type_to_equipment_type(equipment.equipment_type)
        except Exception as e:
            logger.debug(f"Could not get equipment type from repository: {e}")

        # Try JSON fallback (reference devices in bms_simulator/data/)
        try:
            import json as _json
            from pathlib import Path as _Path

            _ref_path = _Path(__file__).parent / "bms_simulator" / "data" / "reference_devices.json"
            if _ref_path.exists():
                devices = _json.loads(_ref_path.read_text())
                for device in devices:
                    if device.get("device_id") == equipment_id or device.get("id") == equipment_id:
                        device_type = device.get("type", "")
                        return self._map_device_type_to_equipment_type(device_type)
        except Exception as e:
            logger.debug(f"Could not get equipment type from JSON: {e}")

        return "default"

    def _map_device_type_to_equipment_type(self, device_type: str) -> str:
        """Map device type to equipment type for tolerance lookup."""
        device_lower = device_type.lower()

        if "chiller" in device_lower:
            return "chiller"
        elif "generator" in device_lower:
            return "generator"
        elif "ahu" in device_lower or "air_handler" in device_lower:
            return "ahu"
        elif "fcu" in device_lower or "fan_coil" in device_lower:
            return "fcu"
        elif "pump" in device_lower:
            return "pump"
        else:
            return "default"


# ============================================================================
# Singleton Factory
# ============================================================================

_baseline_capture_service_instance: BaselineCaptureService | None = None


def get_baseline_capture_service() -> BaselineCaptureService:
    """Get or create the singleton baseline capture service instance."""
    global _baseline_capture_service_instance
    if _baseline_capture_service_instance is None:
        _baseline_capture_service_instance = BaselineCaptureService()
        logger.info("BaselineCaptureService singleton initialized")
    return _baseline_capture_service_instance
