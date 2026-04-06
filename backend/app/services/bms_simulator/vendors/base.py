"""
Base Vendor Adapter

Abstract base class for BMS vendor naming adapters.
"""

from abc import ABC, abstractmethod
from typing import Any


class VendorAdapter(ABC):
    """Abstract base class for vendor-specific naming adapters."""

    @property
    @abstractmethod
    def vendor_name(self) -> str:
        """Return the vendor name."""
        pass

    @abstractmethod
    def format_device_name(
        self,
        device_id: str,
        device_type: str,
        floor: str,
        zone: str,
    ) -> str:
        """
        Format device name according to vendor conventions.

        Args:
            device_id: Original equipment ID (e.g., S002-CHILLER-B1-001)
            device_type: Equipment type (chiller, ahu, vav, etc.)
            floor: Floor code (B1, G, L1, L2, R)
            zone: Zone identifier

        Returns:
            Vendor-formatted device name
        """
        pass

    @abstractmethod
    def format_point_name(
        self,
        device_name: str,
        point_name: str,
        point_type: str,
    ) -> str:
        """
        Format point name according to vendor conventions.

        Args:
            device_name: Vendor-formatted device name
            point_name: Original point name (e.g., chw_supply_temp)
            point_type: BACnet point type

        Returns:
            Vendor-formatted point name
        """
        pass

    @abstractmethod
    def format_point_for_export(
        self,
        device: dict[str, Any],
        point_name: str,
        point_def: dict[str, Any],
        instance_base: int,
    ) -> dict[str, Any]:
        """
        Format a point for CSV export.

        Args:
            device: Device definition from reference_devices.json
            point_name: Point name
            point_def: Point definition
            instance_base: Base instance number for this device

        Returns:
            Dictionary with export fields (name, object_type, instance, units, present_value)
        """
        pass

    def camel_case(self, snake_str: str) -> str:
        """Convert snake_case to CamelCase."""
        components = snake_str.split("_")
        return "".join(x.title() for x in components)

    def parse_equipment_id(self, equipment_id: str) -> dict[str, str]:
        """
        Parse equipment ID into components.

        Format: {site}-{type}-{floor}-{zone_or_seq}
        Example: S002-CHILLER-B1-001 -> {site: S002, type: CHILLER, floor: B1, zone: 001}

        Args:
            equipment_id: Equipment ID string

        Returns:
            Dictionary with site, type, floor, zone components
        """
        parts = equipment_id.split("-")
        if len(parts) >= 4:
            return {
                "site": parts[0],
                "type": parts[1],
                "floor": parts[2],
                "zone": "-".join(parts[3:]),  # Handle multi-part zone IDs
            }
        elif len(parts) == 3:
            return {
                "site": parts[0],
                "type": parts[1],
                "floor": parts[2],
                "zone": "001",
            }
        else:
            return {
                "site": parts[0] if parts else "UNK",
                "type": parts[1] if len(parts) > 1 else "UNK",
                "floor": "G",
                "zone": "001",
            }

    def get_bacnet_object_type(self, point_type: str) -> str:
        """Map point_type to BACnet object type."""
        mapping = {
            "analog_input": "analogInput",
            "analog_value": "analogValue",
            "analog_output": "analogOutput",
            "binary_input": "binaryInput",
            "binary_value": "binaryValue",
            "binary_output": "binaryOutput",
            "multistate_input": "multistateInput",
            "multistate_value": "multistateValue",
            "multistate_output": "multistateOutput",
        }
        return mapping.get(point_type, "analogInput")

    def get_unit_string(self, unit: str) -> str:
        """Convert unit to BACnet-compatible unit string."""
        unit_mapping = {
            "°C": "degC",
            "°F": "degF",
            "%": "percent",
            "A": "amps",
            "V": "volts",
            "Pa": "pascals",
            "bar": "bars",
            "L/s": "litersPerSecond",
            "CFM": "cubicFeetPerMinute",
            "lux": "lux",
            "ppm": "partsPerMillion",
        }
        return unit_mapping.get(unit, unit) if unit else ""
