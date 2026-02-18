#!/usr/bin/env python3
"""
Generate realistic BACnet points for site-013 demo.

Creates 195 BACnet points representing a 4-floor office building with:
- 2 Chillers
- 4 Air Handling Units (AHU)
- 12 Fan Coil Units (FCU)
- 3 Variable Air Volume (VAV) boxes
"""

import json
from pathlib import Path


def generate_office_points():
    """Generate realistic BACnet points for 4-floor office building."""
    points = []

    # =========================================================================
    # Chillers (2 units) - 6 points each = 12 total
    # =========================================================================
    print("Generating Chiller points...")
    for i in [1, 2]:
        chiller_id = f"CH-B1-{i:02d}"
        base_instance = 1000 + (i * 20)

        points.extend([
            {
                "name": f"{chiller_id}.ChwSupplyTemp",
                "description": f"Chiller {i} CHW Supply Temperature",
                "object_type": "analogInput",
                "instance": base_instance,
                "units": "degC",
                "present_value": 7.0,
                "writable": False,
                "bacnet_class": "sensor",
            },
            {
                "name": f"{chiller_id}.ChwReturnTemp",
                "description": f"Chiller {i} CHW Return Temperature",
                "object_type": "analogInput",
                "instance": base_instance + 1,
                "units": "degC",
                "present_value": 12.5,
                "writable": False,
                "bacnet_class": "sensor",
            },
            {
                "name": f"{chiller_id}.ChwFlowRate",
                "description": f"Chiller {i} CHW Flow Rate",
                "object_type": "analogInput",
                "instance": base_instance + 2,
                "units": "L/s",
                "present_value": 15.0,
                "writable": False,
                "bacnet_class": "sensor",
            },
            {
                "name": f"{chiller_id}.CompressorStatus",
                "description": f"Chiller {i} Compressor Status",
                "object_type": "binaryInput",
                "instance": base_instance + 3,
                "units": "",
                "present_value": True,
                "writable": False,
                "bacnet_class": "status",
            },
            {
                "name": f"{chiller_id}.Enable",
                "description": f"Chiller {i} Enable Command",
                "object_type": "binaryOutput",
                "instance": base_instance + 4,
                "units": "",
                "present_value": True,
                "writable": True,
                "bacnet_class": "command",
            },
            {
                "name": f"{chiller_id}.SetpointTemp",
                "description": f"Chiller {i} CHW Setpoint",
                "object_type": "analogValue",
                "instance": base_instance + 5,
                "units": "degC",
                "present_value": 7.0,
                "writable": True,
                "bacnet_class": "setpoint",
            },
        ])

    # =========================================================================
    # AHUs (4 units, one per floor) - 6 points each = 24 total
    # =========================================================================
    print("Generating AHU points...")
    floors = ["G", "L1", "L2", "L3"]
    for floor_idx, floor in enumerate(floors):
        ahu_id = f"AHU-{floor}-01"
        base_instance = 2000 + (floor_idx * 20)

        points.extend([
            {
                "name": f"{ahu_id}.SupplyAirTemp",
                "description": f"AHU {floor} Supply Air Temperature",
                "object_type": "analogInput",
                "instance": base_instance,
                "units": "degC",
                "present_value": 18.0,
                "writable": False,
                "bacnet_class": "sensor",
            },
            {
                "name": f"{ahu_id}.ReturnAirTemp",
                "description": f"AHU {floor} Return Air Temperature",
                "object_type": "analogInput",
                "instance": base_instance + 1,
                "units": "degC",
                "present_value": 24.0,
                "writable": False,
                "bacnet_class": "sensor",
            },
            {
                "name": f"{ahu_id}.FanSpeed",
                "description": f"AHU {floor} Supply Fan Speed",
                "object_type": "analogInput",
                "instance": base_instance + 2,
                "units": "%",
                "present_value": 75.0,
                "writable": False,
                "bacnet_class": "sensor",
            },
            {
                "name": f"{ahu_id}.FanStatus",
                "description": f"AHU {floor} Fan Status",
                "object_type": "binaryInput",
                "instance": base_instance + 3,
                "units": "",
                "present_value": True,
                "writable": False,
                "bacnet_class": "status",
            },
            {
                "name": f"{ahu_id}.FanEnable",
                "description": f"AHU {floor} Fan Enable",
                "object_type": "binaryOutput",
                "instance": base_instance + 4,
                "units": "",
                "present_value": True,
                "writable": True,
                "bacnet_class": "command",
            },
            {
                "name": f"{ahu_id}.ChwValve",
                "description": f"AHU {floor} CHW Valve Position",
                "object_type": "analogOutput",
                "instance": base_instance + 5,
                "units": "%",
                "present_value": 65.0,
                "writable": True,
                "bacnet_class": "command",
            },
        ])

    # =========================================================================
    # FCUs (12 units total) - 5 points each = 60 total
    # =========================================================================
    # G (2), L1 (3), L2 (3), L3 (4)
    print("Generating FCU points...")
    fcu_configs = [
        ("G", ["A", "B"]),
        ("L1", ["A", "B", "C"]),
        ("L2", ["A", "B", "C"]),
        ("L3", ["A", "B", "C", "D"])
    ]

    instance_counter = 3000
    for floor, zones in fcu_configs:
        for zone in zones:
            fcu_id = f"FCU-{floor}-{zone}"

            points.extend([
                {
                    "name": f"{fcu_id}.RoomTemp",
                    "description": f"FCU {floor} Zone {zone} Room Temperature",
                    "object_type": "analogInput",
                    "instance": instance_counter,
                    "units": "degC",
                    "present_value": 22.0,
                    "writable": False,
                    "bacnet_class": "sensor",
                },
                {
                    "name": f"{fcu_id}.Setpoint",
                    "description": f"FCU {floor} Zone {zone} Setpoint",
                    "object_type": "analogValue",
                    "instance": instance_counter + 1,
                    "units": "degC",
                    "present_value": 22.0,
                    "writable": True,
                    "bacnet_class": "setpoint",
                },
                {
                    "name": f"{fcu_id}.FanSpeed",
                    "description": f"FCU {floor} Zone {zone} Fan Speed",
                    "object_type": "analogOutput",
                    "instance": instance_counter + 2,
                    "units": "",
                    "present_value": 2,  # 0=Off, 1=Low, 2=Med, 3=High
                    "writable": True,
                    "bacnet_class": "command",
                },
                {
                    "name": f"{fcu_id}.FanStatus",
                    "description": f"FCU {floor} Zone {zone} Fan Status",
                    "object_type": "binaryInput",
                    "instance": instance_counter + 3,
                    "units": "",
                    "present_value": True,
                    "writable": False,
                    "bacnet_class": "status",
                },
                {
                    "name": f"{fcu_id}.ValvePosition",
                    "description": f"FCU {floor} Zone {zone} Valve Position",
                    "object_type": "analogInput",
                    "instance": instance_counter + 4,
                    "units": "%",
                    "present_value": 50.0,
                    "writable": False,
                    "bacnet_class": "sensor",
                }
            ])
            instance_counter += 10

    # =========================================================================
    # VAVs (3 units, one per floor L1-L3) - 7 points each = 21 total
    # =========================================================================
    print("Generating VAV points...")
    for floor_idx, floor in enumerate(["L1", "L2", "L3"]):
        vav_id = f"VAV-{floor}-01"
        base_instance = 4000 + (floor_idx * 15)

        points.extend([
            {
                "name": f"{vav_id}.Airflow",
                "description": f"VAV {floor} Airflow",
                "object_type": "analogInput",
                "instance": base_instance,
                "units": "L/s",
                "present_value": 120.0,
                "writable": False,
                "bacnet_class": "sensor",
            },
            {
                "name": f"{vav_id}.DamperPosition",
                "description": f"VAV {floor} Damper Position",
                "object_type": "analogInput",
                "instance": base_instance + 1,
                "units": "%",
                "present_value": 60.0,
                "writable": False,
                "bacnet_class": "sensor",
            },
            {
                "name": f"{vav_id}.RoomTemp",
                "description": f"VAV {floor} Zone Temperature",
                "object_type": "analogInput",
                "instance": base_instance + 2,
                "units": "degC",
                "present_value": 22.5,
                "writable": False,
                "bacnet_class": "sensor",
            },
            {
                "name": f"{vav_id}.Setpoint",
                "description": f"VAV {floor} Setpoint",
                "object_type": "analogValue",
                "instance": base_instance + 3,
                "units": "degC",
                "present_value": 22.0,
                "writable": True,
                "bacnet_class": "setpoint",
            },
            {
                "name": f"{vav_id}.DamperCommand",
                "description": f"VAV {floor} Damper Command",
                "object_type": "analogOutput",
                "instance": base_instance + 4,
                "units": "%",
                "present_value": 60.0,
                "writable": True,
                "bacnet_class": "command",
            },
            {
                "name": f"{vav_id}.OccupancyStatus",
                "description": f"VAV {floor} Occupancy Status",
                "object_type": "binaryInput",
                "instance": base_instance + 5,
                "units": "",
                "present_value": True,
                "writable": False,
                "bacnet_class": "status",
            },
            {
                "name": f"{vav_id}.MaintenanceAlarm",
                "description": f"VAV {floor} Maintenance Alarm",
                "object_type": "binaryInput",
                "instance": base_instance + 6,
                "units": "",
                "present_value": False,
                "writable": False,
                "bacnet_class": "status",
            },
        ])

    return points


def main():
    """Generate and save BACnet points."""
    points = generate_office_points()
    print(f"\n✓ Generated {len(points)} BACnet points")

    # Verify counts by type
    type_counts = {}
    for p in points:
        obj_type = p["object_type"]
        type_counts[obj_type] = type_counts.get(obj_type, 0) + 1

    print("\nPoint types:")
    for obj_type, count in sorted(type_counts.items()):
        print(f"  {obj_type}: {count}")

    # Verify class distribution
    class_counts = {}
    for p in points:
        cls = p.get("bacnet_class", "unknown")
        class_counts[cls] = class_counts.get(cls, 0) + 1

    print("\nBACnet point classes:")
    for cls, count in sorted(class_counts.items()):
        print(f"  {cls}: {count}")

    # Save to JSON
    output = {
        "building": "site-013",
        "vendor": "niagara",
        "total_points": len(points),
        "points": points
    }

    output_file = Path(__file__).parent.parent / "app" / "data" / "niagara" / "site-013-bacnet-points.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n✓ Saved to {output_file}")

    # Print sample
    print("\nSample points (first 10):")
    for p in points[:10]:
        writable = "R/W" if p["writable"] else "RO"
        print(f"  {p['name']:40} {p['object_type']:15} ({writable})")


if __name__ == "__main__":
    main()
