"""
Niagara (Tridium) Vendor Adapter

Formats equipment and point names according to Niagara/Tridium conventions.
Pattern: slot:/{DeviceName}/Points/{PointName}
Example: slot:/Chiller_01/Points/ChwSupplyTemp
"""

from typing import Any, Dict

from .base import VendorAdapter


class NiagaraAdapter(VendorAdapter):
    """Adapter for Niagara (Tridium) naming conventions."""

    # Equipment type prefixes for Niagara
    DEVICE_TYPE_PREFIXES = {
        "chiller": "Chiller",
        "ahu": "AHU",
        "fcu": "FCU",
        "vav": "VAV",
        "diffuser": "Diffuser",
        "zone_controller": "ZoneCtrl",
        "fire_safety": "FirePanel",
        "security": "Security",
        "damper": "Damper",
        "pressure_sensor": "PressureSensor",
        "camera": "Camera",
        "access_control": "AccessCtrl",
        "lighting": "Lighting",
        "dali_controller": "DALI",
        "mlm_controller": "MLM",
        "mcu2_gateway": "MCU2",
    }

    @property
    def vendor_name(self) -> str:
        return "Niagara (Tridium)"

    def format_device_name(
        self,
        device_id: str,
        device_type: str,
        floor: str,
        zone: str,
    ) -> str:
        """
        Format device name for Niagara.

        Pattern: {DeviceType}_{Floor}_{Sequence}
        Example: Chiller_B1_01

        Args:
            device_id: Original equipment ID
            device_type: Equipment type
            floor: Floor code
            zone: Zone identifier

        Returns:
            Niagara-formatted device name (without slot: prefix)
        """
        # Parse equipment ID
        parts = self.parse_equipment_id(device_id)

        # Get device type prefix
        device_prefix = self.DEVICE_TYPE_PREFIXES.get(device_type.lower(), device_type.replace("_", "").title())

        # Format sequence number
        seq = parts.get("zone", "01")
        if seq.isdigit():
            seq = f"{int(seq):02d}"
        elif len(seq) == 1 and seq.isalpha():
            seq = seq.upper()

        return f"{device_prefix}_{floor}_{seq}"

    def format_point_name(
        self,
        device_name: str,
        point_name: str,
        point_type: str,
    ) -> str:
        """
        Format point name for Niagara.

        Pattern: slot:/{DeviceName}/Points/{CamelCasePointName}
        Example: slot:/Chiller_B1_01/Points/ChwSupplyTemp

        Args:
            device_name: Niagara-formatted device name
            point_name: Original point name (snake_case)
            point_type: BACnet point type (not used in basic format)

        Returns:
            Niagara-formatted full point path with slot: prefix
        """
        # Convert snake_case to CamelCase
        camel_name = self.camel_case(point_name)
        return f"slot:/{device_name}/Points/{camel_name}"

    def format_point_for_export(
        self,
        device: Dict[str, Any],
        point_name: str,
        point_def: Dict[str, Any],
        instance_base: int,
    ) -> Dict[str, Any]:
        """
        Format a point for CSV export in Niagara format.

        Args:
            device: Device definition
            point_name: Point name
            point_def: Point definition
            instance_base: Base instance number

        Returns:
            Export dictionary
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

        # Niagara also includes ORD (object reference descriptor)
        ord_path = f"station:|{full_point_name.replace('slot:/', '')}"

        return {
            "name": full_point_name,
            "ord": ord_path,
            "object_type": object_type,
            "instance": instance_base,
            "units": unit_string,
            "present_value": present_value,
            "description": point_def.get("description", ""),
            "min_value": point_def.get("min_value"),
            "max_value": point_def.get("max_value"),
            "writable": point_def.get("writable", False),
            "facets": self._get_facets(point_def),
        }

    def _get_facets(self, point_def: Dict[str, Any]) -> str:
        """Generate Niagara facets string for the point."""
        facets = []

        if point_def.get("min_value") is not None:
            facets.append(f"min={point_def['min_value']}")
        if point_def.get("max_value") is not None:
            facets.append(f"max={point_def['max_value']}")
        if point_def.get("unit"):
            facets.append(f"units={self.get_unit_string(point_def['unit'])}")

        return "|".join(facets) if facets else ""
