#!/usr/bin/env python3
"""
Migrate Sandton building assets from JSON to Supabase.

This script reads the Sandton-specific JSON files and inserts them into the
Supabase database. It handles:
- HVAC Zones (zones.json)
- Desks (desks.json)
- Diesel Tanks, Generator Groups, Generators (generators.json)
- Energy Centre and all components (energy_centre.json)

Usage:
    cd backend && python3 -m scripts.migrate_sandton_assets

Requirements:
    - SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env
    - The building 'sandton' must already exist in the buildings table
    - Migrations 013-016 must be applied first
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from decimal import Decimal
import uuid

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from supabase import create_client, Client
from dotenv import load_dotenv
import os

# Load environment
load_dotenv()

# Data directory
DATA_DIR = Path(__file__).parent.parent / "app" / "data"
BUILDINGS_DIR = DATA_DIR / "buildings"
SANDTON_DIR = BUILDINGS_DIR / "sandton"


def get_supabase() -> Client:
    """Get Supabase client."""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
    return create_client(url, key)


def load_json(filepath: Path) -> dict | list:
    """Load JSON file."""
    if filepath.exists():
        with open(filepath) as f:
            return json.load(f)
    return {}


def generate_uuid(seed: str) -> str:
    """Generate deterministic UUID from seed for consistent IDs."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"sandton-{seed}"))


def get_or_create_building(supabase: Client) -> str:
    """Get or create the Sandton building. Returns UUID."""
    print("\n🏢 Checking Sandton building...")

    # Check if exists
    response = supabase.table("buildings").select("id").eq("code", "sandton").execute()
    if response.data:
        building_id = response.data[0]["id"]
        print(f"  ✓ Found existing building: {building_id}")
        return building_id

    # Create if not exists
    building_id = generate_uuid("building")
    record = {
        "id": building_id,
        "code": "sandton",
        "name": "Sandton Office Tower",
        "address": "Sandton City, Johannesburg",
        "region": "Gauteng",
        "type": "data_center",
        "sqm": 15000,
        "floors": 12,
        "optimization_enabled": True,
    }

    try:
        supabase.table("buildings").insert(record).execute()
        print(f"  ✓ Created building: {building_id}")
    except Exception as e:
        print(f"  ✗ Failed to create building: {e}")
        raise

    return building_id


def migrate_hvac_zones(supabase: Client, building_id: str) -> dict:
    """Migrate zones.json to hvac_zones table. Returns zone_id -> UUID mapping."""
    print("\n🌡️ Migrating HVAC zones...")
    zones = load_json(SANDTON_DIR / "zones.json")
    id_map = {}

    if not isinstance(zones, list):
        print("  ⚠ zones.json not found or invalid")
        return id_map

    for zone in zones:
        zone_uuid = generate_uuid(f"zone-{zone['zone_id']}")
        id_map[zone["zone_id"]] = zone_uuid

        record = {
            "id": zone_uuid,
            "zone_id": zone["zone_id"],
            "zone_name": zone["zone_name"],
            "building_id": building_id,
            "floor": zone["floor"],
            "fcu_id": zone.get("fcu_id"),
            "vav_id": zone.get("vav_id"),
            "ahu_id": zone.get("ahu_id"),
            "temp_sensor": zone.get("temp_sensor"),
            "co2_sensor": zone.get("co2_sensor"),
            "typical_occupancy": zone.get("typical_occupancy"),
            "area_sqm": zone.get("area_sqm"),
            "setpoint": zone.get("setpoint", 22.0),
            "current_temp": zone.get("current_temp"),
            "status": zone.get("status", "idle"),
        }

        try:
            supabase.table("hvac_zones").upsert(record).execute()
            print(f"  ✓ {zone['zone_name']}")
        except Exception as e:
            print(f"  ✗ {zone['zone_id']}: {e}")

    print(f"  Migrated {len(id_map)} HVAC zones")
    return id_map


def migrate_desks(supabase: Client, building_id: str, zone_map: dict) -> int:
    """Migrate desks.json to desks table. Returns count."""
    print("\n🪑 Migrating desks...")
    desks = load_json(SANDTON_DIR / "desks.json")
    count = 0

    if not isinstance(desks, list):
        print("  ⚠ desks.json not found or invalid")
        return 0

    for desk in desks:
        desk_uuid = generate_uuid(f"desk-{desk['desk_id']}")

        # Look up hvac_zone UUID
        hvac_zone_id = zone_map.get(desk.get("zone_id"))

        record = {
            "id": desk_uuid,
            "desk_id": desk["desk_id"],
            "building_id": building_id,
            "hvac_zone_id": hvac_zone_id,
            "floor": desk.get("floor", "Unknown"),
            "x_coord": desk.get("x_coord"),
            "y_coord": desk.get("y_coord"),
            "orientation": desk.get("orientation"),
            "near_window": desk.get("near_window", False),
            "near_diffuser": desk.get("near_diffuser") is not None,
            "diffuser_id": desk.get("near_diffuser"),
            "near_printer": desk.get("near_printer", False),
            "near_kitchen": desk.get("near_kitchen", False),
            "department": desk.get("department"),
            "dali_zone": desk.get("dali_zone"),
            "dali_controller": desk.get("dali_controller"),
            "luminaire_ids": desk.get("luminaire_ids", []),
            "sensor_id": desk.get("sensor_id"),
        }

        try:
            supabase.table("desks").upsert(record).execute()
            count += 1
        except Exception as e:
            if count < 5:  # Only print first few errors
                print(f"  ✗ {desk['desk_id']}: {e}")

    print(f"  Migrated {count} desks")
    return count


def migrate_diesel_tanks(supabase: Client, building_id: str, data: dict) -> dict:
    """Migrate diesel_tanks from generators.json. Returns tank_id -> UUID mapping."""
    tanks = data.get("diesel_tanks", [])
    id_map = {}

    for tank in tanks:
        tank_uuid = generate_uuid(f"tank-{tank['tank_id']}")
        id_map[tank["tank_id"]] = tank_uuid

        record = {
            "id": tank_uuid,
            "tank_id": tank["tank_id"],
            "name": tank.get("name", tank["tank_id"]),
            "building_id": building_id,
            "capacity_liters": tank.get("capacity_liters"),
            "current_level_liters": tank.get("current_level_liters"),
            "current_level_pct": tank.get("current_level_pct"),
            "low_level_alarm_pct": tank.get("low_level_alarm_pct", 20.0),
            "reorder_level_pct": tank.get("reorder_level_pct", 30.0),
            "daily_consumption_avg": tank.get("daily_consumption_avg"),
            "days_remaining": tank.get("days_remaining"),
            "supplier": tank.get("supplier"),
            "last_fill_date": tank.get("last_fill_date"),
            "last_fill_liters": tank.get("last_fill_liters"),
        }

        try:
            supabase.table("diesel_tanks").upsert(record).execute()
            print(f"  ✓ Tank: {tank['tank_id']}")
        except Exception as e:
            print(f"  ✗ Tank {tank['tank_id']}: {e}")

    return id_map


def migrate_generator_groups(supabase: Client, building_id: str, data: dict, tank_map: dict) -> dict:
    """Migrate groups from generators.json. Returns group_id -> UUID mapping."""
    groups = data.get("groups", [])
    id_map = {}

    for group in groups:
        group_uuid = generate_uuid(f"group-{group['group_id']}")
        id_map[group["group_id"]] = group_uuid

        # Look up diesel tank UUID
        diesel_tank_id = tank_map.get(group.get("diesel_tank_id"))

        # Get SCADA config for timing
        scada = data.get("scada_config", {})

        record = {
            "id": group_uuid,
            "group_id": group["group_id"],
            "name": group.get("name", group["group_id"]),
            "building_id": building_id,
            "diesel_tank_id": diesel_tank_id,
            "total_generators": group.get("total_generators"),
            "required_running": group.get("required_running"),
            "transfer_mode": group.get("transfer_mode", "closed"),
            "load_share_enabled": scada.get("load_share_enabled", True),
            "auto_start_delay_sec": scada.get("auto_start_delay_sec", 5),
            "cooldown_period_sec": scada.get("cooldown_period_sec", 300),
            "rotation_interval_hours": scada.get("rotation_interval_hours", 168),
            "generators_running": group.get("generators_running", 0),
            "total_load_kw": group.get("total_load_kw", 0),
            "total_capacity_kw": group.get("total_capacity_kw"),
            "load_percent": group.get("load_percent", 0),
            "ats_position": group.get("ats_position", "mains"),
            "mains_healthy": group.get("mains_healthy", True),
        }

        try:
            supabase.table("generator_groups").upsert(record).execute()
            print(f"  ✓ Group: {group['group_id']}")
        except Exception as e:
            print(f"  ✗ Group {group['group_id']}: {e}")

    return id_map


def migrate_generators(supabase: Client, building_id: str, data: dict, group_map: dict, tank_map: dict) -> int:
    """Migrate generators from generators.json. Returns count."""
    generators = data.get("generators", [])
    count = 0

    for gen in generators:
        gen_uuid = generate_uuid(f"gen-{gen['generator_id']}")

        # Look up group and tank UUIDs
        group_id = group_map.get(gen.get("group_id"))
        diesel_tank_id = tank_map.get(gen.get("fuel_tank_id"))

        # Engine data
        engine = gen.get("engine", {})

        record = {
            "id": gen_uuid,
            "generator_id": gen["generator_id"],
            "name": gen.get("name", gen["generator_id"]),
            "building_id": building_id,
            "group_id": group_id,
            "diesel_tank_id": diesel_tank_id,
            "location": gen.get("location"),
            "controller_model": gen.get("controller_model"),
            "controller_ip": gen.get("controller_ip"),
            "modbus_port": gen.get("modbus_port", 502),
            "modbus_unit_id": gen.get("modbus_unit_id"),
            "rated_power_kw": gen.get("rated_power_kw"),
            "rated_power_kva": gen.get("rated_power_kva"),
            "rated_voltage": gen.get("rated_voltage", 400),
            "rated_frequency": gen.get("rated_frequency", 50),
            "status": gen.get("status", "standby"),
            "mains_available": gen.get("mains_available", True),
            "engine_running": gen.get("engine_running", False),
            "on_load": gen.get("on_load", False),
            "rpm": engine.get("rpm", 0),
            "oil_pressure_kpa": engine.get("oil_pressure_kpa"),
            "coolant_temp_c": engine.get("coolant_temp_c"),
            "run_hours": engine.get("run_hours", 0),
            "total_starts": engine.get("total_starts", 0),
            "start_attempts": gen.get("start_attempts", 0),
            "fuel_rate_lph": engine.get("fuel_rate_lph", 0),
            "battery_voltage": gen.get("battery_voltage"),
            "charger_current": gen.get("charger_current"),
            "fuel_level_pct": gen.get("fuel_level_pct"),
            "alarms": gen.get("alarms", []),
            "last_service_date": gen.get("last_service_date"),
            "next_service_hours": gen.get("next_service_hours"),
            "priority": gen.get("priority", 1),
            "last_poll": gen.get("last_poll"),
        }

        try:
            supabase.table("generators").upsert(record).execute()
            print(f"  ✓ Generator: {gen['generator_id']}")
            count += 1
        except Exception as e:
            print(f"  ✗ Generator {gen['generator_id']}: {e}")

    return count


def migrate_generators_all(supabase: Client, building_id: str) -> dict:
    """Migrate all generator-related data. Returns counts."""
    print("\n⚡ Migrating generators...")
    data = load_json(SANDTON_DIR / "generators.json")

    if not data:
        print("  ⚠ generators.json not found or invalid")
        return {"tanks": 0, "groups": 0, "generators": 0}

    # Migrate in dependency order
    tank_map = migrate_diesel_tanks(supabase, building_id, data)
    group_map = migrate_generator_groups(supabase, building_id, data, tank_map)
    gen_count = migrate_generators(supabase, building_id, data, group_map, tank_map)

    return {
        "tanks": len(tank_map),
        "groups": len(group_map),
        "generators": gen_count,
    }


def migrate_energy_centre(supabase: Client, building_id: str) -> dict:
    """Migrate energy centre and all components. Returns counts."""
    print("\n🔌 Migrating energy centre...")
    data = load_json(SANDTON_DIR / "energy_centre.json")

    if not data:
        print("  ⚠ energy_centre.json not found or invalid")
        return {}

    counts = {}

    # Create energy centre
    ec = data.get("energy_centre", {})
    ec_uuid = generate_uuid(f"ec-{ec.get('centre_id', 'SAN-EC-001')}")

    ec_record = {
        "id": ec_uuid,
        "centre_id": ec.get("centre_id", "SAN-EC-001"),
        "name": ec.get("name", "Sandton Energy Centre"),
        "building_id": building_id,
        "location": ec.get("location"),
        "mains_healthy": ec.get("mains_healthy", True),
        "on_generator": ec.get("on_generator", False),
        "total_load_kw": ec.get("total_load_kw"),
        "total_capacity_kw": ec.get("total_capacity_kw"),
        "scada_config": data.get("scada_network"),
    }

    try:
        supabase.table("energy_centres").upsert(ec_record).execute()
        print(f"  ✓ Energy Centre: {ec_record['centre_id']}")
        counts["energy_centres"] = 1
    except Exception as e:
        print(f"  ✗ Energy Centre: {e}")
        return counts

    # Migrate MV Incomers
    mv_incomers = data.get("mv_incomers", [])
    for mv in mv_incomers:
        mv_uuid = generate_uuid(f"mv-{mv['incomer_id']}")
        record = {
            "id": mv_uuid,
            "incomer_id": mv["incomer_id"],
            "name": mv.get("name", mv["incomer_id"]),
            "energy_centre_id": ec_uuid,
            "location": mv.get("location"),
            "nominal_voltage_kv": mv.get("nominal_voltage_kv"),
            "rated_current_a": mv.get("rated_current_a"),
            "fault_level_mva": mv.get("fault_level_mva"),
            "voltage_kv": mv.get("voltage_kv"),
            "current_a": mv.get("current_a"),
            "power_kw": mv.get("power_kw"),
            "power_factor": mv.get("power_factor"),
            "frequency_hz": mv.get("frequency_hz"),
            "breaker_state": mv.get("breaker_state", "open"),
            "healthy": mv.get("healthy", True),
            "protection_relay_model": mv.get("protection_relay_model"),
            "overcurrent_pickup_a": mv.get("overcurrent_pickup_a"),
            "earth_fault_pickup_a": mv.get("earth_fault_pickup_a"),
            "supply_point_id": mv.get("supply_point_id"),
            "tariff_type": mv.get("tariff_type"),
        }
        try:
            supabase.table("mv_incomers").upsert(record).execute()
            print(f"  ✓ MV Incomer: {mv['incomer_id']}")
        except Exception as e:
            print(f"  ✗ MV Incomer {mv['incomer_id']}: {e}")
    counts["mv_incomers"] = len(mv_incomers)

    # Migrate Transformers
    transformers = data.get("transformers", [])
    for tx in transformers:
        tx_uuid = generate_uuid(f"tx-{tx['transformer_id']}")
        record = {
            "id": tx_uuid,
            "transformer_id": tx["transformer_id"],
            "name": tx.get("name", tx["transformer_id"]),
            "energy_centre_id": ec_uuid,
            "location": tx.get("location"),
            "rated_power_kva": tx.get("rated_power_kva"),
            "primary_voltage_kv": tx.get("primary_voltage_kv"),
            "secondary_voltage_v": tx.get("secondary_voltage_v"),
            "vector_group": tx.get("vector_group"),
            "impedance_pct": tx.get("impedance_pct"),
            "load_kva": tx.get("load_kva"),
            "load_percent": tx.get("load_percent"),
            "oil_temp_c": tx.get("oil_temp_c"),
            "winding_temp_c": tx.get("winding_temp_c"),
            "ambient_temp_c": tx.get("ambient_temp_c"),
            "tap_position": tx.get("tap_position", 0),
            "tap_range_pct": tx.get("tap_range_pct"),
            "on_load_tap_changer": tx.get("on_load_tap_changer", False),
            "healthy": tx.get("healthy", True),
            "oil_level_ok": tx.get("oil_level_ok", True),
            "buchholz_alarm": tx.get("buchholz_alarm", False),
            "pressure_relief_ok": tx.get("pressure_relief_ok", True),
            "cooling_type": tx.get("cooling_type"),
            "fans_running": tx.get("fans_running", 0),
        }
        try:
            supabase.table("transformers").upsert(record).execute()
            print(f"  ✓ Transformer: {tx['transformer_id']}")
        except Exception as e:
            print(f"  ✗ Transformer {tx['transformer_id']}: {e}")
    counts["transformers"] = len(transformers)

    # Migrate LV Switchboards
    switchboards = data.get("lv_switchboards", [])
    switchboard_map = {}
    for sb in switchboards:
        sb_uuid = generate_uuid(f"sb-{sb['switchboard_id']}")
        switchboard_map[sb["switchboard_id"]] = sb_uuid
        record = {
            "id": sb_uuid,
            "switchboard_id": sb["switchboard_id"],
            "name": sb.get("name", sb["switchboard_id"]),
            "energy_centre_id": ec_uuid,
            "location": sb.get("location"),
            "rated_voltage": sb.get("rated_voltage", 400),
            "rated_current_a": sb.get("rated_current_a"),
            "fault_rating_ka": sb.get("fault_rating_ka"),
            "bus_sections": sb.get("bus_sections", 1),
            "voltage_l1_n": sb.get("voltage_l1_n"),
            "voltage_l2_n": sb.get("voltage_l2_n"),
            "voltage_l3_n": sb.get("voltage_l3_n"),
            "voltage_l1_l2": sb.get("voltage_l1_l2"),
            "voltage_l2_l3": sb.get("voltage_l2_l3"),
            "voltage_l3_l1": sb.get("voltage_l3_l1"),
            "frequency_hz": sb.get("frequency_hz"),
            "mains_incomer_closed": sb.get("mains_incomer_closed", True),
            "gen_incomer_closed": sb.get("gen_incomer_closed", False),
            "bus_coupler_closed": sb.get("bus_coupler_closed", True),
            "total_power_kw": sb.get("total_power_kw"),
            "total_power_kva": sb.get("total_power_kva"),
            "power_factor": sb.get("power_factor"),
            "total_kwh": sb.get("total_kwh"),
            "healthy": sb.get("healthy", True),
            "temperature_c": sb.get("temperature_c"),
        }
        try:
            supabase.table("lv_switchboards").upsert(record).execute()
            print(f"  ✓ Switchboard: {sb['switchboard_id']}")
        except Exception as e:
            print(f"  ✗ Switchboard {sb['switchboard_id']}: {e}")
    counts["lv_switchboards"] = len(switchboards)

    # Migrate ATS Units
    ats_units = data.get("ats_units", [])
    for ats in ats_units:
        ats_uuid = generate_uuid(f"ats-{ats['ats_id']}")
        record = {
            "id": ats_uuid,
            "ats_id": ats["ats_id"],
            "name": ats.get("name", ats["ats_id"]),
            "energy_centre_id": ec_uuid,
            "location": ats.get("location"),
            "ats_type": ats.get("ats_type", "mechanical"),
            "rated_current_a": ats.get("rated_current_a"),
            "rated_voltage": ats.get("rated_voltage", 400),
            "poles": ats.get("poles", 4),
            "transfer_mode": ats.get("transfer_mode", "closed"),
            "position": ats.get("position", "mains"),
            "mains_available": ats.get("mains_available", True),
            "generator_available": ats.get("generator_available", False),
            "mains_breaker": ats.get("mains_breaker", "closed"),
            "gen_breaker": ats.get("gen_breaker", "open"),
            "last_transfer_time_ms": ats.get("last_transfer_time_ms"),
            "transfer_count": ats.get("transfer_count", 0),
            "last_transfer_timestamp": ats.get("last_transfer_timestamp"),
            "last_transfer_reason": ats.get("last_transfer_reason"),
            "mechanical_interlock_ok": ats.get("mechanical_interlock_ok", True),
            "electrical_interlock_ok": ats.get("electrical_interlock_ok", True),
            "controller_model": ats.get("controller_model"),
            "controller_ip": ats.get("controller_ip"),
            "protocol": ats.get("protocol", "modbus"),
            "last_poll": ats.get("last_poll"),
        }
        try:
            supabase.table("ats_units").upsert(record).execute()
            print(f"  ✓ ATS: {ats['ats_id']}")
        except Exception as e:
            print(f"  ✗ ATS {ats['ats_id']}: {e}")
    counts["ats_units"] = len(ats_units)

    # Migrate Power Meters
    meters = data.get("power_meters", [])
    for meter in meters:
        meter_uuid = generate_uuid(f"meter-{meter['meter_id']}")
        record = {
            "id": meter_uuid,
            "meter_id": meter["meter_id"],
            "name": meter.get("name", meter["meter_id"]),
            "energy_centre_id": ec_uuid,
            "location": meter.get("location"),
            "meter_type": meter.get("meter_type", "main"),
            "manufacturer": meter.get("manufacturer"),
            "model": meter.get("model"),
            "serial_number": meter.get("serial_number"),
            "ct_ratio": meter.get("ct_ratio"),
            "vt_ratio": meter.get("vt_ratio"),
            "voltage_l1_n": meter.get("voltage_l1_n"),
            "voltage_l2_n": meter.get("voltage_l2_n"),
            "voltage_l3_n": meter.get("voltage_l3_n"),
            "current_l1": meter.get("current_l1"),
            "current_l2": meter.get("current_l2"),
            "current_l3": meter.get("current_l3"),
            "current_n": meter.get("current_n"),
            "active_power_kw": meter.get("active_power_kw"),
            "reactive_power_kvar": meter.get("reactive_power_kvar"),
            "apparent_power_kva": meter.get("apparent_power_kva"),
            "power_factor": meter.get("power_factor"),
            "frequency_hz": meter.get("frequency_hz"),
            "kwh_import": meter.get("kwh_import"),
            "kwh_export": meter.get("kwh_export"),
            "kvarh_import": meter.get("kvarh_import"),
            "kvarh_export": meter.get("kvarh_export"),
            "max_demand_kw": meter.get("max_demand_kw"),
            "max_demand_timestamp": meter.get("max_demand_timestamp"),
            "thd_voltage_pct": meter.get("thd_voltage_pct"),
            "thd_current_pct": meter.get("thd_current_pct"),
            "voltage_unbalance_pct": meter.get("voltage_unbalance_pct"),
            "tariff_type": meter.get("tariff_type"),
            "tou_period": meter.get("tou_period"),
            "protocol": meter.get("protocol", "modbus"),
            "ip_address": meter.get("ip_address"),
            "last_poll": meter.get("last_poll"),
        }
        try:
            supabase.table("power_meters").upsert(record).execute()
            print(f"  ✓ Meter: {meter['meter_id']}")
        except Exception as e:
            print(f"  ✗ Meter {meter['meter_id']}: {e}")
    counts["power_meters"] = len(meters)

    # Migrate PFC Banks
    pfc_banks = data.get("pfc_banks", [])
    for pfc in pfc_banks:
        pfc_uuid = generate_uuid(f"pfc-{pfc['pfc_id']}")
        record = {
            "id": pfc_uuid,
            "pfc_id": pfc["pfc_id"],
            "name": pfc.get("name", pfc["pfc_id"]),
            "energy_centre_id": ec_uuid,
            "location": pfc.get("location"),
            "total_kvar": pfc.get("total_kvar"),
            "steps": pfc.get("steps"),
            "step_size_kvar": pfc.get("step_size_kvar"),
            "active_steps": pfc.get("active_steps", 0),
            "active_kvar": pfc.get("active_kvar", 0),
            "target_power_factor": pfc.get("target_power_factor", 0.95),
            "current_power_factor": pfc.get("current_power_factor"),
            "controller_model": pfc.get("controller_model"),
            "auto_mode": pfc.get("auto_mode", True),
            "healthy": pfc.get("healthy", True),
            "capacitor_temps_ok": pfc.get("capacitor_temps_ok", True),
            "fuse_status_ok": pfc.get("fuse_status_ok", True),
        }
        try:
            supabase.table("pfc_banks").upsert(record).execute()
            print(f"  ✓ PFC Bank: {pfc['pfc_id']}")
        except Exception as e:
            print(f"  ✗ PFC Bank {pfc['pfc_id']}: {e}")
    counts["pfc_banks"] = len(pfc_banks)

    # Migrate UPS Systems
    ups_systems = data.get("ups_systems", [])
    for ups in ups_systems:
        ups_uuid = generate_uuid(f"ups-{ups['ups_id']}")
        record = {
            "id": ups_uuid,
            "ups_id": ups["ups_id"],
            "name": ups.get("name", ups["ups_id"]),
            "energy_centre_id": ec_uuid,
            "location": ups.get("location"),
            "rated_power_kva": ups.get("rated_power_kva"),
            "rated_power_kw": ups.get("rated_power_kw"),
            "topology": ups.get("topology", "online"),
            "manufacturer": ups.get("manufacturer"),
            "model": ups.get("model"),
            "input_voltage": ups.get("input_voltage"),
            "input_frequency": ups.get("input_frequency"),
            "input_healthy": ups.get("input_healthy", True),
            "output_voltage": ups.get("output_voltage"),
            "output_frequency": ups.get("output_frequency"),
            "load_kw": ups.get("load_kw"),
            "load_percent": ups.get("load_percent"),
            "battery_voltage": ups.get("battery_voltage"),
            "battery_current": ups.get("battery_current"),
            "battery_charge_pct": ups.get("battery_charge_pct"),
            "battery_runtime_min": ups.get("battery_runtime_min"),
            "battery_temp_c": ups.get("battery_temp_c"),
            "battery_health_pct": ups.get("battery_health_pct"),
            "battery_test_date": ups.get("battery_test_date"),
            "battery_replace_date": ups.get("battery_replace_date"),
            "mode": ups.get("mode", "online"),
            "on_battery": ups.get("on_battery", False),
            "on_bypass": ups.get("on_bypass", False),
            "overload": ups.get("overload", False),
            "alarms": ups.get("alarms", []),
            "protocol": ups.get("protocol", "snmp"),
            "ip_address": ups.get("ip_address"),
            "last_poll": ups.get("last_poll"),
        }
        try:
            supabase.table("ups_systems").upsert(record).execute()
            print(f"  ✓ UPS: {ups['ups_id']}")
        except Exception as e:
            print(f"  ✗ UPS {ups['ups_id']}: {e}")
    counts["ups_systems"] = len(ups_systems)

    # Migrate Feeders
    feeders = data.get("feeders", [])
    for feeder in feeders:
        feeder_uuid = generate_uuid(f"feeder-{feeder['feeder_id']}")

        # Try to find switchboard
        switchboard_id = switchboard_map.get("SAN-MSB-001")  # Main switchboard

        record = {
            "id": feeder_uuid,
            "feeder_id": feeder["feeder_id"],
            "name": feeder.get("name", feeder["feeder_id"]),
            "energy_centre_id": ec_uuid,
            "switchboard_id": switchboard_id,
            "rated_current_a": feeder.get("rated_current_a"),
            "breaker_state": feeder.get("breaker_state", "closed"),
            "current_a": feeder.get("current_a"),
            "power_kw": feeder.get("power_kw"),
        }
        try:
            supabase.table("feeders").upsert(record).execute()
            print(f"  ✓ Feeder: {feeder['feeder_id']}")
        except Exception as e:
            print(f"  ✗ Feeder {feeder['feeder_id']}: {e}")
    counts["feeders"] = len(feeders)

    return counts


def verify_asset_summary(supabase: Client, building_id: str):
    """Verify asset counts by querying the view."""
    print("\n📊 Verifying asset summary...")

    try:
        response = supabase.table("v_building_asset_summary").select("*").eq(
            "building_id", building_id
        ).execute()

        if response.data:
            summary = response.data[0]
            print(f"\n  Asset Summary for {summary['building_name']}:")
            print(f"  ────────────────────────────────────")
            print(f"  Equipment:       {summary.get('equipment_count', 0):>5}")
            print(f"  HVAC Zones:      {summary.get('hvac_zone_count', 0):>5}")
            print(f"  Generators:      {summary.get('generator_count', 0):>5}")
            print(f"  Gen Groups:      {summary.get('generator_group_count', 0):>5}")
            print(f"  Diesel Tanks:    {summary.get('diesel_tank_count', 0):>5}")
            print(f"  Energy Centres:  {summary.get('energy_centre_count', 0):>5}")
            print(f"  MV Incomers:     {summary.get('mv_incomer_count', 0):>5}")
            print(f"  Transformers:    {summary.get('transformer_count', 0):>5}")
            print(f"  Switchboards:    {summary.get('lv_switchboard_count', 0):>5}")
            print(f"  ATS Units:       {summary.get('ats_count', 0):>5}")
            print(f"  Power Meters:    {summary.get('power_meter_count', 0):>5}")
            print(f"  PFC Banks:       {summary.get('pfc_bank_count', 0):>5}")
            print(f"  UPS Systems:     {summary.get('ups_count', 0):>5}")
            print(f"  Feeders:         {summary.get('feeder_count', 0):>5}")
            print(f"  DALI Controllers:{summary.get('dali_controller_count', 0):>5}")
            print(f"  ────────────────────────────────────")
            print(f"  TOTAL ASSETS:    {summary.get('total_assets', 0):>5}")
            print(f"\n  (Supplementary - not in total):")
            print(f"  Desks:           {summary.get('desk_count', 0):>5}")
            print(f"  Luminaires:      {summary.get('luminaire_count', 0):>5}")
            print(f"  DALI Sensors:    {summary.get('dali_sensor_count', 0):>5}")
        else:
            print("  ⚠ View returned no data (migrations may not be applied yet)")

    except Exception as e:
        print(f"  ⚠ Could not query view: {e}")
        print("  (View may not exist yet - run migrations 013-017 first)")


def main():
    """Run the Sandton migration."""
    print("=" * 60)
    print("BMS Intelligence - Sandton Assets Migration")
    print("=" * 60)

    supabase = get_supabase()
    print(f"\n✓ Connected to Supabase at {os.getenv('SUPABASE_URL')}")

    # Get or create building
    building_id = get_or_create_building(supabase)

    # Migrate in dependency order
    zone_map = migrate_hvac_zones(supabase, building_id)
    migrate_desks(supabase, building_id, zone_map)
    gen_counts = migrate_generators_all(supabase, building_id)
    ec_counts = migrate_energy_centre(supabase, building_id)

    # Verify
    verify_asset_summary(supabase, building_id)

    print("\n" + "=" * 60)
    print("✅ Sandton migration complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
