"""
Point List Exporter

Reads equipment from mock_devices.json and exports point lists
in vendor-specific CSV formats for BMS onboarding.
"""

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

from ..models import (
    VendorType,
    SimulationConfig,
    RICKARD_DIFFUSER_TEMPLATE,
    SITE_CODE_MAP,
    HOSPITAL_DIFFUSER_CONFIG,
)
from ..vendors.base import VendorAdapter
from ..vendors.siemens_desigo import SiemensDesigoAdapter
from ..vendors.niagara import NiagaraAdapter
from ..vendors.rickard import RickardAdapter


class PointListExporter:
    """Exports point lists from mock devices to vendor CSV formats."""

    # Base paths
    DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"
    MOCK_DEVICES_PATH = DATA_DIR / "mock_devices.json"
    OUTPUT_DIR = DATA_DIR / "bms_simulator" / "exports"

    # Vendor adapter mapping
    VENDOR_ADAPTERS: Dict[VendorType, Type[VendorAdapter]] = {
        VendorType.SIEMENS_DESIGO: SiemensDesigoAdapter,
        VendorType.NIAGARA: NiagaraAdapter,
        VendorType.RICKARD: RickardAdapter,
    }

    def __init__(self, config: Optional[SimulationConfig] = None):
        """
        Initialize the point list exporter.

        Args:
            config: Simulation configuration
        """
        self.config = config or SimulationConfig()
        self.adapter = self._get_adapter(VendorType(self.config.vendor))
        self._devices_cache: Optional[List[Dict]] = None

    def _get_adapter(self, vendor: VendorType) -> VendorAdapter:
        """Get the vendor adapter instance."""
        adapter_class = self.VENDOR_ADAPTERS.get(vendor, SiemensDesigoAdapter)
        return adapter_class()

    def _load_devices_from_buildings(self, equipment_path: Path) -> List[Dict[str, Any]]:
        """
        Load devices from individual JSON files in a buildings/site/equipment directory.

        Args:
            equipment_path: Path to equipment directory

        Returns:
            List of device dictionaries
        """
        devices = []
        for json_file in equipment_path.glob("*.json"):
            try:
                with open(json_file, "r") as f:
                    device = json.load(f)
                    # Convert equipment_type to hvac_type for consistency
                    if "equipment_type" in device and "hvac_type" not in device:
                        device["hvac_type"] = device["equipment_type"]
                    devices.append(device)
            except (json.JSONDecodeError, IOError) as e:
                print(f"Warning: Could not load {json_file}: {e}")
        return devices

    def load_devices(self, site_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Load devices from mock_devices.json and/or buildings directory.

        First checks the buildings/{site_id}/equipment/ directory for equipment files.
        Falls back to mock_devices.json for sites not in buildings directory.

        Args:
            site_id: Filter to specific site (e.g., "site-002", "site-004")

        Returns:
            List of device dictionaries
        """
        if self._devices_cache is not None and site_id is None:
            return self._devices_cache

        # First try to load from buildings directory (preferred for newer sites)
        if site_id:
            buildings_path = self.DATA_DIR / "buildings" / site_id / "equipment"
            if buildings_path.exists():
                devices = self._load_devices_from_buildings(buildings_path)
                if devices:
                    return devices

        # Fall back to mock_devices.json
        with open(self.MOCK_DEVICES_PATH, "r") as f:
            all_devices = json.load(f)

        if site_id:
            devices = [d for d in all_devices if d.get("site_id") == site_id]
        else:
            devices = all_devices

        if site_id is None:
            self._devices_cache = devices

        return devices

    def generate_diffusers(self, site_id: str = "site-002") -> List[Dict[str, Any]]:
        """
        Generate Rickard VAV diffuser equipment linked to existing VAVs.

        Creates diffusers for each VAV zone with:
        - Rickard VVD-Series diffusers
        - MLM controller (master/slave)
        - MCU2 gateway for BACnet output

        For hospital sites (site-004), uses HOSPITAL_DIFFUSER_CONFIG for layout.

        Args:
            site_id: Site to generate diffusers for

        Returns:
            List of diffuser device dictionaries
        """
        # Check for hospital-specific diffuser configuration
        if site_id in HOSPITAL_DIFFUSER_CONFIG:
            return self._generate_hospital_diffusers(site_id)

        # Standard VAV-linked diffuser generation for other sites
        devices = self.load_devices(site_id)
        vavs = [d for d in devices if d.get("hvac_type") == "vav"]

        diffusers = []
        rickard_adapter = RickardAdapter()

        for vav in vavs:
            vav_id = vav.get("id", "")
            location = vav.get("device_location", {})
            floor = location.get("floor", "L1")
            zone = location.get("zone", "Zone-A")

            # Parse zone letter from VAV ID (e.g., S002-VAV-L2-A -> A)
            parts = vav_id.split("-")
            zone_letter = parts[-1] if len(parts) >= 4 else "A"

            # Generate 2-3 diffusers per VAV zone
            n_diffusers = 2 if zone_letter in ["A", "B"] else 3

            for seq in range(1, n_diffusers + 1):
                # Generate diffuser ID
                site_code = parts[0] if parts else "S002"
                diffuser_id = f"{site_code}-DIFF-{floor}-{zone_letter}{seq:02d}"

                # Create diffuser from template
                diffuser = {
                    "id": diffuser_id,
                    "name": f"Rickard Diffuser {floor}-{zone_letter}{seq:02d}",
                    "device_type": "hvac",
                    "protocol": "bacnet",
                    "site_id": site_id,
                    "hvac_type": "diffuser",
                    "capacity": 350,  # CFM capacity
                    "points": dict(RICKARD_DIFFUSER_TEMPLATE["points"]),
                    "device_location": {
                        "building": location.get("building", "Sandton City Office Tower"),
                        "floor": floor,
                        "zone": f"Zone-{floor}-{zone_letter}",
                        "room": f"Ceiling {floor}",
                        "description": f"{floor}, Zone {zone_letter}, Diffuser {seq}",
                        "zone_type": location.get("zone_type", "open_office"),
                        "exposure": "interior",
                        "zone_priority": location.get("zone_priority", 3),
                    },
                    "equipment": {
                        "manufacturer": "Rickard",
                        "model": "VVD-Series",
                        "serial_number": f"RKD-{diffuser_id}",
                        "installation_year": datetime.now().year,
                        "controller_type": "MLM",
                        "mlm_role": "master" if seq == 1 else "slave",
                        "gateway": f"MCU2-{self._get_gateway_number(floor):02d}",
                        "capacity_kw": 0.35,  # Convert CFM to rough kW
                        "replaces_legacy": True,
                        "legacy_age_years": 18,
                    },
                    "metadata": {
                        "building": location.get("building", "Sandton City Office Tower"),
                        "building_id": site_id,
                        "floor": self._floor_to_number(floor),
                        "zone": f"Zone-{floor}-{zone_letter}",
                        "location": f"{floor} Zone {zone_letter} Ceiling",
                        "serves": f"Zone {zone_letter} workstations",
                        "connected_vav": vav_id,
                        "safety_status": "safe",
                        "safety_note": "Operating normally",
                        "network": "segregated",  # NOT on banking network initially
                        "bacnet_interface": "documented",
                    },
                }

                diffusers.append(diffuser)

        return diffusers

    def _generate_hospital_diffusers(self, site_id: str) -> List[Dict[str, Any]]:
        """
        Generate Rickard diffusers for hospital sites using predefined configuration.

        For site-004 (uMhlanga Private Hospital):
        - 30 diffusers across 3 MCU2 gateways
        - L2 (Admin): 10 diffusers
        - L5 (Maternity): 10 diffusers
        - L8 (Private Suites): 10 diffusers

        Args:
            site_id: Hospital site ID

        Returns:
            List of diffuser device dictionaries
        """
        config = HOSPITAL_DIFFUSER_CONFIG.get(site_id)
        if not config:
            return []

        diffusers = []
        site_code = SITE_CODE_MAP.get(site_id, "UMH")

        # Building name based on site
        building_names = {
            "site-004": "uMhlanga Private Hospital",
        }
        building_name = building_names.get(site_id, "Hospital")

        # Zone type descriptions for hospitals
        zone_descriptions = {
            "office": "Administration offices",
            "ward": "Patient ward areas",
            "patient_room": "Private patient rooms",
        }

        for gateway_id, gateway_config in config.get("gateways", {}).items():
            floor = gateway_config["floor"]
            zone = gateway_config["zone"]
            n_diffusers = gateway_config["diffuser_count"]
            zone_type = gateway_config.get("zone_type", "ward")

            for seq in range(1, n_diffusers + 1):
                # Generate diffuser ID: UMH-DIFF-L2-01, UMH-DIFF-L2-02, etc.
                diffuser_id = f"{site_code}-DIFF-{floor}-{seq:02d}"

                # Create diffuser from template
                diffuser = {
                    "id": diffuser_id,
                    "name": f"Rickard Diffuser {floor}-{seq:02d}",
                    "device_type": "hvac",
                    "protocol": "bacnet",
                    "site_id": site_id,
                    "hvac_type": "diffuser",
                    "capacity": 300,  # CFM capacity (hospital typically lower)
                    "points": dict(RICKARD_DIFFUSER_TEMPLATE["points"]),
                    "device_location": {
                        "building": building_name,
                        "floor": floor,
                        "zone": zone,
                        "room": f"Room {floor}-{seq:02d}",
                        "description": f"{floor}, {zone}, Diffuser {seq}",
                        "zone_type": zone_type,
                        "exposure": "interior",
                        "zone_priority": 2 if zone_type == "patient_room" else 3,
                    },
                    "equipment": {
                        "manufacturer": "Rickard",
                        "model": "VVD-Series",
                        "serial_number": f"RKD-{diffuser_id}",
                        "installation_year": 2022,
                        "controller_type": "MLM",
                        "mlm_role": "master" if seq % 5 == 1 else "slave",  # Master every 5th
                        "gateway": gateway_id,
                        "capacity_kw": 0.30,
                        "replaces_legacy": False,  # New installation
                        "legacy_age_years": 0,
                    },
                    "metadata": {
                        "building": building_name,
                        "building_id": site_id,
                        "floor": self._floor_to_number(floor),
                        "zone": zone,
                        "location": f"{floor} {zone} Ceiling",
                        "serves": zone_descriptions.get(zone_type, zone),
                        "connected_gateway": gateway_id,
                        "safety_status": "safe",
                        "safety_note": "Operating normally",
                        "network": "hospital_bms",
                        "bacnet_interface": "documented",
                        "hospital_zone": True,
                    },
                }

                diffusers.append(diffuser)

        return diffusers

    def _get_gateway_number(self, floor: str) -> int:
        """Get MCU2 gateway number for floor."""
        floor_gateway_map = {
            "B2": 1, "B1": 1, "G": 2, "L0": 2,
            "L1": 3, "L2": 4, "L3": 5, "L4": 6,
            "L5": 7, "L6": 8, "L7": 9, "L8": 10,
            "L9": 11, "R": 12,
        }
        return floor_gateway_map.get(floor, 1)

    def _floor_to_number(self, floor: str) -> int:
        """Convert floor code to numeric level."""
        floor_map = {
            "B2": -2, "B1": -1, "G": 0, "L0": 0,
            "L1": 1, "L2": 2, "L3": 3, "L4": 4,
            "L5": 5, "L6": 6, "L7": 7, "L8": 8,
            "L9": 9, "R": 99,
        }
        return floor_map.get(floor, 0)

    def export_point_list(
        self,
        site_id: Optional[str] = None,
        include_diffusers: bool = True,
        output_path: Optional[Path] = None,
    ) -> str:
        """
        Export point list as vendor-formatted CSV.

        Args:
            site_id: Filter to specific site
            include_diffusers: Include generated Rickard diffusers
            output_path: Custom output path (optional)

        Returns:
            Path to exported CSV file
        """
        site_id = site_id or self.config.site_id

        # Load devices
        devices = self.load_devices(site_id)

        # Add generated diffusers if requested
        if include_diffusers and self.config.include_diffusers:
            diffusers = self.generate_diffusers(site_id)
            devices = devices + diffusers

        # Export points
        points = []
        instance_counter = 1000  # Starting BACnet instance number

        for device in devices:
            device_points = device.get("points", {})
            for point_name, point_def in device_points.items():
                point_export = self.adapter.format_point_for_export(
                    device=device,
                    point_name=point_name,
                    point_def=point_def,
                    instance_base=instance_counter,
                )
                points.append(point_export)
                instance_counter += 1

        # Determine output path
        if output_path is None:
            vendor_name = self.config.vendor.replace("_", "-")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"point_list_{site_id}_{vendor_name}_{timestamp}.csv"
            output_path = self.OUTPUT_DIR / filename

        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Write CSV
        self._write_csv(points, output_path)

        return str(output_path)

    def _write_csv(self, points: List[Dict[str, Any]], output_path: Path) -> None:
        """
        Write points to CSV file.

        Args:
            points: List of point dictionaries
            output_path: Output file path
        """
        if not points:
            return

        # Determine fieldnames from first point + standard fields
        standard_fields = [
            "name", "object_type", "instance", "units", "present_value",
            "description", "min_value", "max_value", "writable"
        ]

        # Get all unique fields across points
        all_fields = set()
        for point in points:
            all_fields.update(point.keys())

        # Order fields: standard first, then extras
        fieldnames = [f for f in standard_fields if f in all_fields]
        extra_fields = sorted(all_fields - set(fieldnames))
        fieldnames.extend(extra_fields)

        with open(output_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(points)

    def get_point_summary(self, site_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get summary statistics of points by device type.

        Args:
            site_id: Filter to specific site

        Returns:
            Summary dictionary with counts by type
        """
        site_id = site_id or self.config.site_id
        devices = self.load_devices(site_id)

        if self.config.include_diffusers:
            diffusers = self.generate_diffusers(site_id)
            devices = devices + diffusers

        summary = {
            "site_id": site_id,
            "total_devices": len(devices),
            "total_points": 0,
            "devices_by_type": {},
            "points_by_type": {},
        }

        for device in devices:
            device_type = device.get("hvac_type", device.get("device_type", "unknown"))
            n_points = len(device.get("points", {}))

            # Count devices
            if device_type not in summary["devices_by_type"]:
                summary["devices_by_type"][device_type] = 0
            summary["devices_by_type"][device_type] += 1

            # Count points
            if device_type not in summary["points_by_type"]:
                summary["points_by_type"][device_type] = 0
            summary["points_by_type"][device_type] += n_points
            summary["total_points"] += n_points

        return summary
