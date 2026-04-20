#!/usr/bin/env python3
"""Seed all Sandton building equipment to PostgreSQL via Supabase.

Equipment count: ~80 items
- HVAC: 3 AHUs, 15 FCUs, 15 VAVs, 30 sensors
- Energy Centre: 1 MV, 2 TX, 1 MSB, 1 ATS, 2 UPS, 3 meters, 1 PFC, 5 feeders
- Generators: 4 generators, 1 group, 1 diesel tank

Usage:
    cd /opt/bms-intelligence/backend
    source venv/bin/activate
    python scripts/seed_sandton_equipment.py
"""

import json
import os
import sys
import uuid

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database.supabase_client import get_supabase_client

BASE_PATH = "/opt/bms-intelligence/backend/app/data/buildings/sandton"


def load_json(filepath):
    with open(filepath) as f:
        return json.load(f)


def get_or_create_building(client):
    """Get or create the Sandton building record."""
    result = client.table("sites").select("id").eq("code", "sandton").execute()

    if result.data:
        print(f"Building 'sandton' exists with ID: {result.data[0]['id']}")
        return result.data[0]["id"]

    site_id = str(uuid.uuid4())
    client.table("sites").insert(
        {
            "id": site_id,
            "code": "sandton",
            "name": "Sandton Office Tower",
            "address": "144 Katherine Street, Sandton, 2196",
            "region": "Gauteng",
            "type": "regional_office",
            "floors": 3,
            "sqm": 15000,
            "optimization_enabled": True,
        }
    ).execute()

    print(f"Created building 'sandton' with ID: {site_id}")
    return site_id


def seed_hvac_equipment(client, site_id):
    """Seed HVAC equipment from zones.json."""
    zones = load_json(f"{BASE_PATH}/zones.json")
    count = 0
    ahus_created = set()

    for zone in zones:
        floor = zone["floor"]
        zone_id = zone["zone_id"]

        # AHU (one per floor)
        ahu_id = zone["ahu_id"]
        if ahu_id not in ahus_created:
            client.table("equipment").upsert(
                {
                    "id": str(uuid.uuid4()),
                    "code": ahu_id,
                    "name": f"Air Handling Unit {floor}",
                    "type": "ahu",
                    "site_id": site_id,
                    "location": f"{floor} Mechanical Room",
                    "status": "normal",
                    "health_score": 92,
                    "manufacturer": "Carrier",
                    "model": "39HQ",
                    "metadata": {"supply_cfm": 12000, "return_cfm": 11500},
                },
                on_conflict="code",
            ).execute()
            ahus_created.add(ahu_id)
            count += 1

        # FCU
        client.table("equipment").upsert(
            {
                "id": str(uuid.uuid4()),
                "code": zone["fcu_id"],
                "name": f"Fan Coil Unit {zone_id}",
                "type": "fcu",
                "site_id": site_id,
                "location": zone["zone_name"],
                "status": "normal" if zone["status"] == "running" else "warning",
                "health_score": 88 if zone["status"] == "running" else 65,
                "manufacturer": "Trane",
                "model": "WSHP-42",
                "metadata": {"zone_id": zone_id, "setpoint": zone["setpoint"]},
            },
            on_conflict="code",
        ).execute()
        count += 1

        # VAV
        client.table("equipment").upsert(
            {
                "id": str(uuid.uuid4()),
                "code": zone["vav_id"],
                "name": f"Variable Air Volume {zone_id}",
                "type": "vav",
                "site_id": site_id,
                "location": zone["zone_name"],
                "status": "normal",
                "health_score": 95,
                "manufacturer": "Belimo",
                "model": "LMV-D3",
                "metadata": {"zone_id": zone_id, "max_cfm": 800},
            },
            on_conflict="code",
        ).execute()
        count += 1

        # Temp sensor
        client.table("equipment").upsert(
            {
                "id": str(uuid.uuid4()),
                "code": zone["temp_sensor"],
                "name": f"Temperature Sensor {zone_id}",
                "type": "sensor",
                "site_id": site_id,
                "location": zone["zone_name"],
                "status": "normal",
                "health_score": 100,
                "manufacturer": "Siemens",
                "model": "QAM2120.040",
                "metadata": {"sensor_type": "temperature", "zone_id": zone_id},
            },
            on_conflict="code",
        ).execute()
        count += 1

        # CO2 sensor
        client.table("equipment").upsert(
            {
                "id": str(uuid.uuid4()),
                "code": zone["co2_sensor"],
                "name": f"CO2 Sensor {zone_id}",
                "type": "sensor",
                "site_id": site_id,
                "location": zone["zone_name"],
                "status": "normal",
                "health_score": 100,
                "manufacturer": "Siemens",
                "model": "QPA2062D",
                "metadata": {"sensor_type": "co2", "zone_id": zone_id},
            },
            on_conflict="code",
        ).execute()
        count += 1

    print(f"Seeded {count} HVAC equipment items")
    return count


def seed_generators(client, site_id):
    """Seed generators from generators.json."""
    gen_data = load_json(f"{BASE_PATH}/generators.json")
    count = 0

    for gen in gen_data["generators"]:
        client.table("equipment").upsert(
            {
                "id": str(uuid.uuid4()),
                "code": gen["generator_id"],
                "name": gen["name"],
                "type": "generator",
                "site_id": site_id,
                "location": gen["location"],
                "status": "normal",
                "health_score": 90,
                "manufacturer": "Cummins",
                "model": gen["controller_model"],
                "serial_number": f"GEN-{gen['generator_id'][-3:]}",
                "capacity": f"{gen['rated_power_kw']}kW",
                "metadata": {
                    "rated_power_kw": gen["rated_power_kw"],
                    "rated_power_kva": gen["rated_power_kva"],
                    "run_hours": gen["engine"]["run_hours"],
                    "fuel_level_pct": gen["fuel_level_pct"],
                    "controller_ip": gen["controller_ip"],
                },
            },
            on_conflict="code",
        ).execute()
        count += 1

    for group in gen_data["groups"]:
        client.table("equipment").upsert(
            {
                "id": str(uuid.uuid4()),
                "code": group["group_id"],
                "name": group["name"],
                "type": "generator_group",
                "site_id": site_id,
                "location": "Basement Level 2",
                "status": "normal",
                "health_score": 95,
                "capacity": f"{group['total_capacity_kw']}kW",
                "metadata": {"total_generators": group["total_generators"], "transfer_mode": group["transfer_mode"]},
            },
            on_conflict="code",
        ).execute()
        count += 1

    for tank in gen_data["diesel_tanks"]:
        client.table("equipment").upsert(
            {
                "id": str(uuid.uuid4()),
                "code": tank["tank_id"],
                "name": tank["name"],
                "type": "diesel_tank",
                "site_id": site_id,
                "location": "Basement Level 2",
                "status": "normal",
                "health_score": 100,
                "capacity": f"{tank['capacity_liters']}L",
                "metadata": {
                    "current_level_pct": tank["current_level_pct"],
                    "days_remaining": tank["days_remaining"],
                    "supplier": tank["supplier"],
                },
            },
            on_conflict="code",
        ).execute()
        count += 1

    print(f"Seeded {count} generator equipment items")
    return count


def seed_energy_centre(client, site_id):
    """Seed energy centre equipment from energy_centre.json."""
    ec = load_json(f"{BASE_PATH}/energy_centre.json")
    count = 0

    # MV Incomer
    for i in ec["mv_incomers"]:
        client.table("equipment").upsert(
            {
                "id": str(uuid.uuid4()),
                "code": i["incomer_id"],
                "name": i["name"],
                "type": "mv_incomer",
                "site_id": site_id,
                "location": i["location"],
                "status": "normal" if i["healthy"] else "critical",
                "health_score": 95 if i["healthy"] else 50,
                "manufacturer": "Siemens",
                "model": i["protection_relay_model"],
                "capacity": f"{i['nominal_voltage_kv']}kV",
                "metadata": {"rated_current_a": i["rated_current_a"], "breaker_state": i["breaker_state"]},
            },
            on_conflict="code",
        ).execute()
        count += 1

    # Transformers
    for tx in ec["transformers"]:
        client.table("equipment").upsert(
            {
                "id": str(uuid.uuid4()),
                "code": tx["transformer_id"],
                "name": tx["name"],
                "type": "transformer",
                "site_id": site_id,
                "location": tx["location"],
                "status": "normal" if tx["healthy"] else "warning",
                "health_score": 90 if tx["healthy"] else 70,
                "manufacturer": "ABB",
                "model": tx["vector_group"],
                "capacity": f"{tx['rated_power_kva']}kVA",
                "metadata": {
                    "load_percent": tx["load_percent"],
                    "oil_temp_c": tx["oil_temp_c"],
                    "winding_temp_c": tx["winding_temp_c"],
                    "cooling_type": tx["cooling_type"],
                },
            },
            on_conflict="code",
        ).execute()
        count += 1

    # LV Switchboard
    for sb in ec["lv_switchboards"]:
        client.table("equipment").upsert(
            {
                "id": str(uuid.uuid4()),
                "code": sb["switchboard_id"],
                "name": sb["name"],
                "type": "lv_switchboard",
                "site_id": site_id,
                "location": sb["location"],
                "status": "normal" if sb["healthy"] else "warning",
                "health_score": 92,
                "manufacturer": "Schneider Electric",
                "capacity": f"{sb['rated_current_a']}A",
                "metadata": {
                    "total_power_kw": sb["total_power_kw"],
                    "power_factor": sb["power_factor"],
                    "bus_sections": sb["bus_sections"],
                },
            },
            on_conflict="code",
        ).execute()
        count += 1

    # ATS
    for ats in ec["ats_units"]:
        client.table("equipment").upsert(
            {
                "id": str(uuid.uuid4()),
                "code": ats["ats_id"],
                "name": ats["name"],
                "type": "ats",
                "site_id": site_id,
                "location": ats["location"],
                "status": "normal",
                "health_score": 95,
                "manufacturer": "Socomec",
                "model": ats["controller_model"],
                "capacity": f"{ats['rated_current_a']}A",
                "metadata": {
                    "position": ats["position"],
                    "transfer_count": ats["transfer_count"],
                    "controller_ip": ats["controller_ip"],
                },
            },
            on_conflict="code",
        ).execute()
        count += 1

    # UPS
    for ups in ec["ups_systems"]:
        client.table("equipment").upsert(
            {
                "id": str(uuid.uuid4()),
                "code": ups["ups_id"],
                "name": ups["name"],
                "type": "ups",
                "site_id": site_id,
                "location": ups["location"],
                "status": "normal",
                "health_score": 95 if ups["battery_health_pct"] > 90 else 80,
                "manufacturer": ups["manufacturer"],
                "model": ups["model"],
                "serial_number": f"UPS-{ups['ups_id'][-3:]}",
                "capacity": f"{ups['rated_power_kva']}kVA",
                "metadata": {
                    "load_percent": ups["load_percent"],
                    "battery_charge_pct": ups["battery_charge_pct"],
                    "battery_runtime_min": ups["battery_runtime_min"],
                    "battery_health_pct": ups["battery_health_pct"],
                    "ip_address": ups["ip_address"],
                },
            },
            on_conflict="code",
        ).execute()
        count += 1

    # Power Meters
    for m in ec["power_meters"]:
        client.table("equipment").upsert(
            {
                "id": str(uuid.uuid4()),
                "code": m["meter_id"],
                "name": m["name"],
                "type": "power_meter",
                "site_id": site_id,
                "location": m["location"],
                "status": "normal",
                "health_score": 100,
                "manufacturer": m["manufacturer"],
                "model": m["model"],
                "serial_number": m["serial_number"],
                "metadata": {"meter_type": m["meter_type"], "ct_ratio": m["ct_ratio"], "ip_address": m["ip_address"]},
            },
            on_conflict="code",
        ).execute()
        count += 1

    # PFC Bank
    for pfc in ec["pfc_banks"]:
        client.table("equipment").upsert(
            {
                "id": str(uuid.uuid4()),
                "code": pfc["pfc_id"],
                "name": pfc["name"],
                "type": "pfc_bank",
                "site_id": site_id,
                "location": pfc["location"],
                "status": "normal" if pfc["healthy"] else "warning",
                "health_score": 95,
                "manufacturer": "Schneider",
                "model": pfc["controller_model"],
                "capacity": f"{pfc['total_kvar']}kVAr",
                "metadata": {
                    "steps": pfc["steps"],
                    "active_steps": pfc["active_steps"],
                    "target_power_factor": pfc["target_power_factor"],
                },
            },
            on_conflict="code",
        ).execute()
        count += 1

    # Feeders
    for f in ec["feeders"]:
        client.table("equipment").upsert(
            {
                "id": str(uuid.uuid4()),
                "code": f["feeder_id"],
                "name": f["name"],
                "type": "feeder",
                "site_id": site_id,
                "location": "LV Switchroom",
                "status": "normal" if f["breaker_state"] == "closed" else "offline",
                "health_score": 100 if f["breaker_state"] == "closed" else 0,
                "capacity": f"{f['rated_current_a']}A",
                "metadata": {
                    "current_a": f["current_a"],
                    "power_kw": f["power_kw"],
                    "breaker_state": f["breaker_state"],
                },
            },
            on_conflict="code",
        ).execute()
        count += 1

    print(f"Seeded {count} energy centre equipment items")
    return count


def main():
    print("=" * 60)
    print("Sandton Equipment Seeding Script (Supabase)")
    print("=" * 60)

    client = get_supabase_client()
    print("Connected to Supabase")

    site_id = get_or_create_building(client)

    total = 0
    total += seed_hvac_equipment(client, site_id)
    total += seed_generators(client, site_id)
    total += seed_energy_centre(client, site_id)

    print("=" * 60)
    print(f"Total equipment seeded: {total}")

    # Verify
    result = client.table("equipment").select("id").eq("site_id", site_id).execute()
    print(f"Verified: {len(result.data)} equipment records in database")
    print("=" * 60)


if __name__ == "__main__":
    main()
