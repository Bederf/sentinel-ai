"""
Rickard DALI Vendor Adapter

Formats equipment and point names according to Rickard DALI conventions.
Supports:
- Rickard Variable Volume Diffusers (VVD)
- MLM Controllers (Master/Slave configuration)
- MCU2 Gateways (BACnet output)

Pattern: RKD/{Site}/{Gateway}/{Controller}/{Point}
Example: RKD/STC/MCU2-01/MLM-L2-A/AirflowCfm

Network notes:
- Initially on segregated network (NOT on banking network)
- BACnet interface documented for future BACS onboarding
"""

from typing import Any, Dict

from .base import VendorAdapter
from ..models import SITE_CODE_MAP, FLOOR_CODE_MAP


class RickardAdapter(VendorAdapter):
    """Adapter for Rickard DALI naming conventions."""

    @property
    def vendor_name(self) -> str:
        return "Rickard DALI"

    def format_device_name(
        self,
        device_id: str,
        device_type: str,
        floor: str,
        zone: str,
    ) -> str:
        """
        Format device name for Rickard DALI.

        Pattern: RKD/{Site}/MCU2-{GatewayNum}/MLM-{Floor}-{Zone}
        Example: RKD/STC/MCU2-01/MLM-L2-A

        Args:
            device_id: Original equipment ID (e.g., S002-DIFF-L2-A01)
            device_type: Equipment type
            floor: Floor code
            zone: Zone identifier

        Returns:
            Rickard-formatted device path
        """
        # Parse equipment ID
        parts = self.parse_equipment_id(device_id)
        site_code = SITE_CODE_MAP.get(f"site-{parts['site'][1:]}", parts['site'])
        floor_code = FLOOR_CODE_MAP.get(floor, floor)

        # Determine gateway number (one per floor typically)
        gateway_num = self._get_gateway_number(floor)

        # Format zone identifier
        zone_id = parts.get("zone", "01")
        if zone_id.isdigit():
            # Numeric zone - pad to 2 digits
            zone_id = f"{int(zone_id):02d}"

        return f"RKD/{site_code}/MCU2-{gateway_num:02d}/MLM-{floor_code}-{zone_id}"

    def _get_gateway_number(self, floor: str) -> int:
        """
        Get MCU2 gateway number based on floor.

        Typically one gateway per floor for segregated network.
        """
        floor_gateway_map = {
            "B2": 1,
            "B1": 1,
            "G": 2,
            "L0": 2,
            "L1": 3,
            "L2": 4,
            "L3": 5,
            "R": 6,
        }
        return floor_gateway_map.get(floor, 1)

    def format_point_name(
        self,
        device_name: str,
        point_name: str,
        point_type: str,
    ) -> str:
        """
        Format point name for Rickard DALI.

        Pattern: {DevicePath}/{CamelCasePointName}
        Example: RKD/STC/MCU2-01/MLM-L2-A/AirflowCfm

        Args:
            device_name: Rickard-formatted device name
            point_name: Original point name (snake_case)
            point_type: BACnet point type

        Returns:
            Rickard-formatted full point path
        """
        # Convert snake_case to CamelCase
        camel_name = self.camel_case(point_name)
        return f"{device_name}/{camel_name}"

    def format_point_for_export(
        self,
        device: Dict[str, Any],
        point_name: str,
        point_def: Dict[str, Any],
        instance_base: int,
    ) -> Dict[str, Any]:
        """
        Format a point for CSV export in Rickard format.

        Includes Rickard-specific metadata:
        - MLM controller address (master/slave)
        - MCU2 gateway ID
        - BACnet interface info for future BACS onboarding

        Args:
            device: Device definition
            point_name: Point name
            point_def: Point definition
            instance_base: Base instance number

        Returns:
            Export dictionary with Rickard-specific fields
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

        # Rickard-specific metadata
        equipment_info = device.get("equipment", {})
        gateway_num = self._get_gateway_number(floor)

        # Determine MLM controller role (master for first diffuser in zone, slave for rest)
        zone_id = self.parse_equipment_id(device_id).get("zone", "01")
        mlm_role = "master" if zone_id.endswith("01") or zone_id.endswith("A") else "slave"

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
            # Rickard-specific fields
            "manufacturer": equipment_info.get("manufacturer", "Rickard"),
            "model": equipment_info.get("model", "VVD-Series"),
            "controller_type": "MLM",
            "mlm_role": mlm_role,
            "gateway": f"MCU2-{gateway_num:02d}",
            "network": "segregated",  # NOT on banking network initially
            "bacnet_interface": "documented",  # For future BACS onboarding
            # Legacy diffuser replacement info
            "replaces_legacy": True,
            "legacy_age_years": 18,
        }

    def format_diffuser_id(
        self,
        site: str,
        floor: str,
        zone: str,
        sequence: int,
    ) -> str:
        """
        Generate a Rickard diffuser equipment ID.

        Pattern: {Site}-DIFF-{Floor}-{Zone}{Seq}
        Example: S002-DIFF-L2-A01

        Args:
            site: Site code (e.g., S002)
            floor: Floor code (e.g., L2)
            zone: Zone letter (e.g., A)
            sequence: Diffuser number within zone (1, 2, 3...)

        Returns:
            Equipment ID for the diffuser
        """
        return f"{site}-DIFF-{floor}-{zone}{sequence:02d}"

    def format_mlm_controller_id(
        self,
        site: str,
        floor: str,
        zone: str,
    ) -> str:
        """
        Generate an MLM controller equipment ID.

        Pattern: {Site}-MLM-{Floor}-{Zone}
        Example: S002-MLM-L2-A

        Args:
            site: Site code
            floor: Floor code
            zone: Zone letter

        Returns:
            Equipment ID for the MLM controller
        """
        return f"{site}-MLM-{floor}-{zone}"

    def format_mcu2_gateway_id(
        self,
        site: str,
        gateway_num: int,
    ) -> str:
        """
        Generate an MCU2 gateway equipment ID.

        Pattern: {Site}-MCU2-{Num}
        Example: S002-MCU2-01

        Args:
            site: Site code
            gateway_num: Gateway number

        Returns:
            Equipment ID for the MCU2 gateway
        """
        return f"{site}-MCU2-{gateway_num:02d}"
