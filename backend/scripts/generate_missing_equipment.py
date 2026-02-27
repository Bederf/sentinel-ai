#!/usr/bin/env python3
"""Generate missing equipment JSON files to match Supabase inventory.

Creates 32 equipment files for site-002:
- 25 FCU (fan coil units)
- 5 VAV (variable air volume)
- 1 DALI controller
- 1 Generator

Templates derived from existing equipment files.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

EQUIP_DIR = Path(__file__).resolve().parent.parent / "app" / "data" / "buildings" / "site-002" / "equipment"
NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")


def fcu_template(code: str, name: str) -> dict:
    """FCU template matching S002-FCU-L1-A structure."""
    short = code.replace("S002-", "")
    return {
        "id": code,
        "name": f"{name} ({code})",
        "device_type": "hvac",
        "equipment_type": "fcu",
        "site_id": "site-002",
        "protocol": "bacnet",
        "points": {
            "temperature": {
                "bacnet_ref": f"{short}_Room_Temp",
                "object_type": "analogInput",
                "instance": 0,
                "unit": "degC",
                "writable": False,
                "point_type": "sensor",
                "default_value": None,
            },
            "speed": {
                "bacnet_ref": f"{short}_Fan_Speed",
                "object_type": "analogOutput",
                "instance": 0,
                "unit": "%",
                "writable": False,
                "point_type": "sensor",
                "default_value": None,
            },
            "valve_position": {
                "bacnet_ref": f"{short}_Valve_Pos",
                "object_type": "analogOutput",
                "instance": 0,
                "unit": "%",
                "writable": False,
                "point_type": "sensor",
                "default_value": None,
            },
        },
        "metadata": {
            "source": "supabase_inventory_sync",
            "discovery_confidence": "high",
            "auto_generated": True,
            "created_at": NOW,
        },
    }


def vav_template(code: str, name: str) -> dict:
    """VAV template matching S002-VAV-L1-A structure."""
    short = code.replace("S002-", "")
    return {
        "id": code,
        "name": f"{name} ({code})",
        "device_type": "hvac",
        "equipment_type": "vav",
        "site_id": "site-002",
        "protocol": "bacnet",
        "points": {
            "room_temperature": {
                "bacnet_ref": f"{short}.RoomTemp",
                "object_type": "analogInput",
                "instance": 2000,
                "unit": "\u00b0C",
                "writable": False,
                "point_type": "sensor",
                "default_value": 22.5,
            },
            "damper_position": {
                "bacnet_ref": f"{short}.DamperPos",
                "object_type": "analogInput",
                "instance": 2001,
                "unit": "%",
                "writable": False,
                "point_type": "sensor",
                "default_value": 50.0,
            },
            "temperature_setpoint": {
                "bacnet_ref": f"{short}.Setpoint",
                "object_type": "analogValue",
                "instance": 2002,
                "unit": "\u00b0C",
                "writable": True,
                "point_type": "setpoint",
                "default_value": 22.0,
            },
        },
        "metadata": {
            "source": "supabase_inventory_sync",
            "discovery_confidence": "high",
            "auto_generated": True,
            "created_at": NOW,
        },
    }


def dali_controller_template(code: str, name: str) -> dict:
    """DALI controller template matching S002-DALI-L1-CTRL structure."""
    short = code.replace("S002-", "")
    return {
        "id": code,
        "name": f"{name} ({code})",
        "device_type": "lighting",
        "equipment_type": "dali_controller",
        "site_id": "site-002",
        "protocol": "bacnet",
        "points": {
            "status": {
                "bacnet_ref": f"{short}_Status",
                "object_type": "binaryInput",
                "instance": 0,
                "unit": "",
                "writable": False,
                "point_type": "status",
                "default_value": None,
            },
            "alarm": {
                "bacnet_ref": f"{short}_Bus_Fault",
                "object_type": "binaryInput",
                "instance": 0,
                "unit": "",
                "writable": False,
                "point_type": "alarm",
                "default_value": None,
            },
        },
        "metadata": {
            "source": "supabase_inventory_sync",
            "discovery_confidence": "high",
            "auto_generated": True,
            "created_at": NOW,
        },
    }


def generator_template(code: str, name: str) -> dict:
    """Generator template matching S002-GEN-B1-001 structure."""
    short = code.replace("S002-", "")
    return {
        "id": code,
        "name": f"{name} ({code})",
        "device_type": "power",
        "equipment_type": "generator",
        "site_id": "site-002",
        "protocol": "bacnet",
        "points": {
            "status": {
                "bacnet_ref": f"{short}_Status",
                "object_type": "binaryInput",
                "instance": 0,
                "unit": "",
                "writable": False,
                "point_type": "status",
                "default_value": None,
            },
            "level": {
                "bacnet_ref": f"{short}_Fuel_Level",
                "object_type": "analogInput",
                "instance": 0,
                "unit": "%",
                "writable": False,
                "point_type": "sensor",
                "default_value": None,
            },
            "power": {
                "bacnet_ref": f"{short}_Output_kW",
                "object_type": "analogInput",
                "instance": 0,
                "unit": "kW",
                "writable": False,
                "point_type": "sensor",
                "default_value": None,
            },
        },
        "metadata": {
            "source": "supabase_inventory_sync",
            "discovery_confidence": "high",
            "auto_generated": True,
            "created_at": NOW,
        },
    }


# Equipment to create: (code, name, template_fn)
EQUIPMENT = [
    # === FCU — 25 files ===
    # L0 (zone 001-099)
    ("S002-FCU-001", "L0 North FCU", fcu_template),
    ("S002-FCU-021", "L0 South FCU", fcu_template),
    ("S002-FCU-041", "L0 East FCU", fcu_template),
    ("S002-FCU-061", "L0 West FCU", fcu_template),
    ("S002-FCU-081", "L0 Central FCU", fcu_template),
    # L1 (zone 100-199)
    ("S002-FCU-101", "Level 1 Zone A FCU", fcu_template),
    ("S002-FCU-105", "Level 1 Zone E FCU", fcu_template),
    ("S002-FCU-121", "L1 North FCU", fcu_template),
    ("S002-FCU-141", "L1 South FCU", fcu_template),
    ("S002-FCU-161", "L1 East FCU", fcu_template),
    ("S002-FCU-181", "L1 West FCU", fcu_template),
    ("S002-FCU-L1-B", "Level 1 Zone B FCU", fcu_template),
    # L2 (zone 200-299)
    ("S002-FCU-201", "Level 2 Zone A FCU", fcu_template),
    ("S002-FCU-205", "Level 2 Zone E FCU", fcu_template),
    ("S002-FCU-221", "L2 North FCU", fcu_template),
    ("S002-FCU-241", "L2 South FCU", fcu_template),
    ("S002-FCU-261", "L2 East FCU", fcu_template),
    ("S002-FCU-281", "L2 West FCU", fcu_template),
    ("S002-FCU-L2-A", "Level 2 Zone A FCU", fcu_template),
    ("S002-FCU-L2-D", "Level 2 Zone D FCU", fcu_template),
    # L3 (zone 300-399)
    ("S002-FCU-301", "L3 North FCU", fcu_template),
    ("S002-FCU-321", "L3 South FCU", fcu_template),
    ("S002-FCU-341", "L3 East FCU", fcu_template),
    ("S002-FCU-361", "L3 West FCU", fcu_template),
    ("S002-FCU-381", "L3 Central FCU", fcu_template),
    # === VAV — 5 files ===
    ("S002-VAV-105", "Level 1 Zone E VAV", vav_template),
    ("S002-VAV-205", "Level 2 Zone E VAV", vav_template),
    ("S002-VAV-L0-A", "Level 0 Zone A VAV", vav_template),
    ("S002-VAV-L2-C", "Level 2 Zone C VAV", vav_template),
    ("S002-VAV-L2-D", "Level 2 Zone D VAV", vav_template),
    # === DALI controller — 1 file ===
    ("S002-DALI-B1-CTRL", "Level 1 DALI Controller", dali_controller_template),
    # === Generator — 1 file ===
    ("S002-GEN-B1-002", "Standby Generator 2", generator_template),
]


def main():
    created = 0
    skipped = 0

    for code, name, template_fn in EQUIPMENT:
        filepath = EQUIP_DIR / f"{code}.json"
        if filepath.exists():
            print(f"  SKIP  {code} (already exists)")
            skipped += 1
            continue

        data = template_fn(code, name)
        filepath.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print(f"  CREATE  {filepath.name}")
        created += 1

    total = len(list(EQUIP_DIR.glob("*.json")))
    print(f"\nDone: {created} created, {skipped} skipped. Total files: {total}")


if __name__ == "__main__":
    main()
