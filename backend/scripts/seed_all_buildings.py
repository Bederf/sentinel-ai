#!/usr/bin/env python3
"""
Seed all buildings with equipment, zones, and desks.
Based on Sandton (site-002) ratios, with variations for building types.
"""

import os
import sys
import uuid
from datetime import datetime

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database.supabase_client import get_supabase_client


# Building configurations with desk multipliers
# Retail buildings have fewer desks, offices/hospitals have more
BUILDING_CONFIG = {
    "site-001": {"name": "Rosebank Towers", "type": "office", "desk_mult": 1.15, "floors": ["L1", "L2", "L3", "L4", "L5"]},
    "site-003": {"name": "Centurion Mall", "type": "retail", "desk_mult": 0.3, "floors": ["G", "L1", "L2"]},
    "site-004": {"name": "V&A Waterfront Retail", "type": "retail", "desk_mult": 0.25, "floors": ["G", "L1"]},
    "site-005": {"name": "Gateway Theatre", "type": "retail", "desk_mult": 0.2, "floors": ["G", "L1", "L2", "L3"]},
    "site-006": {"name": "Mediclinic Sandton", "type": "hospital", "desk_mult": 0.8, "floors": ["G", "L1", "L2", "L3", "L4"]},
    "site-007": {"name": "Mediclinic Constantiaberg", "type": "hospital", "desk_mult": 0.8, "floors": ["G", "L1", "L2", "L3"]},
    "site-008": {"name": "Standard Bank Centre", "type": "office", "desk_mult": 1.25, "floors": ["G", "L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8"]},
    "site-009": {"name": "Standard Bank Rosebank", "type": "office", "desk_mult": 1.0, "floors": ["G", "L1"]},
    "site-010": {"name": "Standard Bank Durban", "type": "office", "desk_mult": 1.0, "floors": ["G", "L1", "L2"]},
}

# Equipment types per zone (HVAC + Lighting + Sensors)
ZONE_EQUIPMENT = [
    ("fcu", "Fan Coil Unit"),
    ("vav", "Variable Air Volume"),
    ("dali_controller", "DALI Controller"),
    ("luminaire_group", "LED Luminaires"),
    ("daylight_sensor", "Daylight Sensor"),
    ("occupancy_sensor", "Occupancy Sensor"),
]

# Building-wide equipment (scaled by size)
BUILDING_EQUIPMENT = [
    ("ahu", "Air Handling Unit", 3000),  # 1 per 3000 sqm
    ("generator", "Backup Generator", 4000),  # 1 per 4000 sqm
    ("transformer", "Transformer", 7000),  # 1 per 7000 sqm
    ("ups", "UPS System", 5000),  # 1 per 5000 sqm
    ("power_meter", "Power Meter", 2500),  # 1 per 2500 sqm
    ("feeder", "Electrical Feeder", 3000),  # 1 per 3000 sqm
]

# Single items per building
SINGLE_EQUIPMENT = [
    ("mv_incomer", "MV Incomer"),
    ("lv_switchboard", "LV Switchboard"),
    ("ats", "Automatic Transfer Switch"),
    ("pfc_bank", "Power Factor Correction"),
    ("diesel_tank", "Diesel Tank"),
]


def get_buildings(client):
    """Get all buildings from Supabase."""
    result = client.table('buildings').select('id, code, name, sqm').execute()
    return {b['code']: b for b in result.data}


def clear_existing_data(client, building_id, building_code):
    """Clear existing equipment, zones, desks for a building."""
    print(f"  Clearing existing data for {building_code}...")

    # Delete equipment (except generators which may have special config)
    client.table('equipment').delete().eq('building_id', building_id).execute()

    # Delete zones
    client.table('hvac_zones').delete().eq('building_id', building_id).execute()

    # Delete desks
    client.table('desks').delete().eq('building_id', building_id).execute()


def create_zones(client, building_id, building_code, config, sqm):
    """Create HVAC zones for a building."""
    # 1 zone per 300 sqm
    num_zones = max(3, int(sqm / 300))
    floors = config["floors"]
    zones_per_floor = max(1, num_zones // len(floors))

    zones = []
    zone_records = []
    zone_num = 1

    # Use building code prefix for unique zone_ids
    bldg_prefix = building_code.upper().replace("SITE-", "S")  # e.g., S001, S002

    for floor in floors:
        for z in range(zones_per_floor):
            zone_letter = chr(65 + z)  # A, B, C...
            zone_id = f"{bldg_prefix}-Zone-{floor}-{zone_letter}"
            priority = f"P{min(5, 1 + (z // 2))}"  # P1-P5

            zone_record = {
                "building_id": building_id,
                "zone_id": zone_id,
                "zone_name": f"{floor} Zone {zone_letter}",
                "floor": floor,
                "area_sqm": int(sqm / num_zones),
                "setpoint": 21.0 + (z * 0.5),
                "current_temp": 20.5 + (z * 0.3),
                "current_humidity": 45 + (z * 2),
                "current_co2": 400 + (zone_num * 10),
                "typical_occupancy": 15 + (z * 5),
                "priority": priority,
                "status": "running",
                "mode": "auto",
                "fcu_id": f"{bldg_prefix}-FCU-{floor}-{zone_letter}",
                "vav_id": f"{bldg_prefix}-VAV-{floor}-{zone_letter}",
                "temp_sensor": f"{bldg_prefix}-TS-{floor}-{zone_letter}",
                "co2_sensor": f"{bldg_prefix}-CO2-{floor}-{zone_letter}",
            }
            zone_records.append(zone_record)
            zones.append({"zone_id": zone_id, "floor": floor})
            zone_num += 1

            if zone_num > num_zones:
                break
        if zone_num > num_zones:
            break

    if zone_records:
        result = client.table('hvac_zones').insert(zone_records).execute()
        # Get the inserted zone UUIDs for desk linking
        for i, inserted in enumerate(result.data):
            zones[i]["uuid"] = inserted["id"]

    print(f"  Created {len(zones)} zones")
    return zones


def create_equipment(client, building_id, building_code, config, sqm, zones):
    """Create equipment for a building."""
    equipment = []
    eq_num = 1

    # Use building code prefix for unique equipment codes
    bldg_prefix = building_code.upper().replace("SITE-", "S")  # e.g., S001, S002

    # Zone equipment (per zone)
    for zone in zones:
        floor = zone["floor"]
        zone_letter = zone["zone_id"].split("-")[-1]

        for eq_type, eq_name in ZONE_EQUIPMENT:
            code = f"{bldg_prefix}-{eq_type.upper()}-{floor}-{zone_letter}"
            equipment.append({
                "building_id": building_id,
                "code": code,
                "name": f"{eq_name} {zone['zone_id']}",
                "type": eq_type,
                "manufacturer": "Generic",
                "status": "normal",
                "health_score": 85 + (eq_num % 15),
            })
            eq_num += 1

        # Add 2 sensors per zone (temp + CO2)
        for sensor_type in ["temp", "co2"]:
            code = f"{bldg_prefix}-{sensor_type.upper()}-{floor}-{zone_letter}"
            equipment.append({
                "building_id": building_id,
                "code": code,
                "name": f"{sensor_type.upper()} Sensor {zone['zone_id']}",
                "type": "sensor",
                "manufacturer": "Generic",
                "status": "normal",
                "health_score": 90 + (eq_num % 10),
            })
            eq_num += 1

    # Building-wide equipment (scaled by sqm)
    for eq_type, eq_name, sqm_per_unit in BUILDING_EQUIPMENT:
        count = max(1, int(sqm / sqm_per_unit))
        for i in range(count):
            code = f"{building_code.upper()}-{eq_type.upper()}-{i+1:03d}"
            equipment.append({
                "building_id": building_id,
                "code": code,
                "name": f"{eq_name} {i+1}",
                "type": eq_type,
                "manufacturer": "Generic",
                "status": "normal",
                "health_score": 80 + (eq_num % 20),
            })
            eq_num += 1

    # Single equipment items
    for eq_type, eq_name in SINGLE_EQUIPMENT:
        code = f"{building_code.upper()}-{eq_type.upper()}-001"
        equipment.append({
            "building_id": building_id,
            "code": code,
            "name": f"{eq_name}",
            "type": eq_type,
            "manufacturer": "Generic",
            "status": "normal",
            "health_score": 90,
        })

    if equipment:
        # Batch insert in chunks of 50
        for i in range(0, len(equipment), 50):
            batch = equipment[i:i+50]
            client.table('equipment').insert(batch).execute()

    print(f"  Created {len(equipment)} equipment items")
    return equipment


def create_desks(client, building_id, building_code, config, sqm, zones):
    """Create desks for a building."""
    # Base: 1 desk per 15 sqm, modified by desk_mult
    base_desks = int(sqm / 15)
    num_desks = int(base_desks * config["desk_mult"])
    num_desks = max(10, num_desks)  # Minimum 10 desks

    desks = []
    desk_num = 1

    floors = config["floors"]
    desks_per_floor = max(1, num_desks // len(floors))

    for floor in floors:
        # Find zones on this floor with their UUIDs
        floor_zones = [z for z in zones if z["floor"] == floor and "uuid" in z]
        if not floor_zones:
            floor_zones = [z for z in zones if "uuid" in z][:1]  # Fallback
        if not floor_zones:
            continue

        for d in range(desks_per_floor):
            # Use building code prefix to ensure unique desk_id across buildings
            bldg_num = building_code.replace("site-", "")
            desk_id = f"{bldg_num}-{desk_num + 1000}"  # e.g., "001-1001"
            zone = floor_zones[d % len(floor_zones)]
            zone_uuid = zone.get("uuid")

            # Vary desk contexts
            near_window = (d % 6) == 0
            near_diffuser = (d % 6) == 1
            near_printer = (d % 6) == 2

            desks.append({
                "building_id": building_id,
                "desk_id": desk_id,
                "hvac_zone_id": zone_uuid,
                "floor": floor,
                "near_window": near_window,
                "near_diffuser": near_diffuser,
                "near_printer": near_printer,
                "near_kitchen": (d % 10) == 0,
                "occupied": False,
            })
            desk_num += 1

            if desk_num > num_desks:
                break
        if desk_num > num_desks:
            break

    if desks:
        # Batch insert in chunks of 100
        for i in range(0, len(desks), 100):
            batch = desks[i:i+100]
            client.table('desks').insert(batch).execute()

    print(f"  Created {len(desks)} desks")
    return desks


def seed_building(client, building_code, building_data, config):
    """Seed a single building with all data."""
    building_id = building_data["id"]
    sqm = building_data["sqm"] or 5000

    print(f"\nSeeding {building_code}: {building_data['name']} ({sqm} sqm)")

    # Clear existing data
    clear_existing_data(client, building_id, building_code)

    # Create zones
    zones = create_zones(client, building_id, building_code, config, sqm)

    # Create equipment
    equipment = create_equipment(client, building_id, building_code, config, sqm, zones)

    # Create desks
    desks = create_desks(client, building_id, building_code, config, sqm, zones)

    return {
        "zones": len(zones),
        "equipment": len(equipment),
        "desks": len(desks),
    }


def main():
    """Main seeding function."""
    print("=" * 60)
    print("Building Data Seeder")
    print("=" * 60)

    client = get_supabase_client()
    buildings = get_buildings(client)

    print(f"\nFound {len(buildings)} buildings in Supabase")

    results = {}

    for building_code, config in BUILDING_CONFIG.items():
        if building_code in buildings:
            building_data = buildings[building_code]
            results[building_code] = seed_building(client, building_code, building_data, config)
        else:
            print(f"\nSkipping {building_code}: not found in Supabase")

    # Summary
    print("\n" + "=" * 60)
    print("SEEDING COMPLETE")
    print("=" * 60)

    total_zones = 0
    total_equipment = 0
    total_desks = 0

    for code, data in results.items():
        print(f"{code}: {data['zones']} zones, {data['equipment']} equipment, {data['desks']} desks")
        total_zones += data['zones']
        total_equipment += data['equipment']
        total_desks += data['desks']

    print("-" * 60)
    print(f"TOTAL: {total_zones} zones, {total_equipment} equipment, {total_desks} desks")

    # Re-seed energy consumption with updated equipment
    print("\n" + "=" * 60)
    print("Re-seeding energy consumption data...")
    print("=" * 60)

    import subprocess
    result = subprocess.run(
        ["curl", "-s", "-X", "POST", "http://localhost:9095/api/energy/seed?days=90"],
        capture_output=True,
        text=True
    )
    print(result.stdout)


if __name__ == "__main__":
    main()
