"""
Siemens Desigo CC Vendor Adapter

Formats equipment and point names according to Siemens Desigo CC conventions.
Pattern: {Site}/{Floor}/{Device-Code}/{PointName}
Example: STC/B1/CH-01/ChwSupplyTemp
"""

from typing import Any

from ..models import FLOOR_CODE_MAP, SITE_CODE_MAP
from .base import VendorAdapter


class SiemensDesigoAdapter(VendorAdapter):
    """Adapter for Siemens Desigo CC naming conventions."""

    # Equipment type abbreviations for Desigo
    DEVICE_TYPE_CODES = {
        "chiller": "CH",
        "ahu": "AHU",
        "fcu": "FCU",
        "vav": "VAV",
        "diffuser": "DIFF",
        "zone_controller": "ZC",
        "fire_safety": "FP",
        "security": "SEC",
        "damper": "DAMP",
        "pressure_sensor": "PS",
        "camera": "CAM",
        "access_control": "ACC",
        "lighting": "LT",
        "dali_controller": "DALI",
        "mlm_controller": "MLM",
        "mcu2_gateway": "MCU",
    }

    @property
    def vendor_name(self) -> str:
        return "Siemens Desigo CC"

    def format_device_name(
        self,
        device_id: str,
        device_type: str,
        floor: str,
        zone: str,
    ) -> str:
        """
        Format device name for Siemens Desigo.

        Pattern: {Site}/{Floor}/{DeviceType}-{Sequence}
        Example: STC/B1/CH-01

        Args:
            device_id: Original equipment ID (e.g., S002-CHILLER-B1-001)
            device_type: Equipment type
            floor: Floor code
            zone: Zone identifier

        Returns:
            Desigo-formatted device path
        """
        # Parse equipment ID
        parts = self.parse_equipment_id(device_id)
        site_code = SITE_CODE_MAP.get(f"site-{parts['site'][1:]}", parts["site"])
        floor_code = FLOOR_CODE_MAP.get(floor, floor)

        # Get device type code
        device_code = self.DEVICE_TYPE_CODES.get(device_type.lower(), device_type[:3].upper())

        # Format sequence number
        seq = parts.get("zone", "01")
        if seq.isdigit():
            seq = f"{int(seq):02d}"
        elif len(seq) == 1 and seq.isalpha():
            # Convert zone letter to number (A=01, B=02, etc.)
            seq = f"{ord(seq.upper()) - ord('A') + 1:02d}"

        return f"{site_code}/{floor_code}/{device_code}-{seq}"

    def format_point_name(
        self,
        device_name: str,
        point_name: str,
        point_type: str,
    ) -> str:
        """
        Format point name for Siemens Desigo.

        Pattern: {DevicePath}/{CamelCasePointName}
        Example: STC/B1/CH-01/ChwSupplyTemp

        Args:
            device_name: Vendor-formatted device name
            point_name: Original point name (snake_case)
            point_type: BACnet point type (not used in Desigo format)

        Returns:
            Desigo-formatted full point path
        """
        # Convert snake_case to CamelCase
        camel_name = self.camel_case(point_name)
        return f"{device_name}/{camel_name}"

    def format_point_for_export(
        self,
        device: dict[str, Any],
        point_name: str,
        point_def: dict[str, Any],
        instance_base: int,
    ) -> dict[str, Any]:
        """
        Format a point for CSV export in Desigo format.

        Args:
            device: Device definition
            point_name: Point name
            point_def: Point definition
            instance_base: Base instance number

        Returns:
            Export dictionary with name, object_type, instance, units, present_value
        """
        # Get device info
        device_id = device.get("id", "")
        device_type = device.get("hvac_type", device.get("device_type", "unknown"))
        location = device.get("device_location", {})
        floor = location.get("floor", "G")
        zone = location.get("zone", "")

        # Format device and point names
        device_name = self.format_device_name(device_id, device_type, floor, zone)
        full_point_name = self.format_point_name(device_name, point_name, point_def.get("point_type", "analog_input"))

        # Get BACnet object type
        point_type = point_def.get("point_type", "analog_input")
        object_type = self.get_bacnet_object_type(point_type)

        # Get unit string
        unit = point_def.get("unit", "")
        unit_string = self.get_unit_string(unit)

        # Get present value
        present_value = point_def.get("default_value", 0)
        if isinstance(present_value, bool):
            present_value = 1 if present_value else 0

        return {
            "name": full_point_name,
            "object_type": object_type,
            "instance": instance_base,
            "units": unit_string,
            "present_value": present_value,
            "description": point_def.get("description", ""),
            "min_value": point_def.get("min_value"),
            "max_value": point_def.get("max_value"),
            "writable": point_def.get("writable", False),
        }
