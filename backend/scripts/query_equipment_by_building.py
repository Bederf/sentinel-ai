#!/usr/bin/env python3
"""
Query Supabase equipment table to diagnose data population per building.
"""

import sys

sys.path.insert(0, "/opt/bms-intelligence/backend")

import json

from app.database.supabase_client import get_supabase_client

client = get_supabase_client()

print("=" * 70)
print("EQUIPMENT TABLE DIAGNOSIS")
print("=" * 70)

# 1. Check equipment table structure and count
try:
    print("\n1. EQUIPMENT TABLE STRUCTURE & COUNT")
    print("-" * 70)
    result = client.table("equipment").select("*", count="exact").limit(1).execute()
    if result.count is not None:
        print(f"   Total equipment records: {result.count}")
    else:
        print("   Count: Unable to retrieve")
except Exception as e:
    print(f"   ERROR: {e}")

# 2. Check buildings table
try:
    print("\n2. BUILDINGS TABLE")
    print("-" * 70)
    buildings = client.table("sites").select("id, code, name").execute()
    building_list = buildings.data
    if building_list:
        print(f"   Total buildings: {len(building_list)}")
        for b in building_list:
            print(f"     - {b['code']}: {b['name']} (id: {b['id'][:8]}...)")
    else:
        print("   No buildings found")
except Exception as e:
    print(f"   ERROR: {e}")

# 3. Check equipment per building
try:
    print("\n3. EQUIPMENT PER BUILDING")
    print("-" * 70)

    # Get all buildings first
    buildings = client.table("sites").select("id, code, name").execute()

    for building in buildings.data:
        site_id = building["id"]
        site_code = building["code"]
        site_name = building["name"]

        # Query equipment by building
        try:
            equip = client.table("equipment").select("*").eq("site_id", site_id).execute()
            count = len(equip.data) if equip.data else 0
            print(f"\n   {site_code} ({site_name})")
            print(f"     Equipment count: {count}")

            if equip.data and count > 0:
                for eq in equip.data[:3]:  # Show first 3
                    print(
                        f"       - {eq.get('code', 'N/A')}: {eq.get('name', 'N/A')} "
                        f"(type: {eq.get('equipment_type', 'N/A')})"
                    )
                if count > 3:
                    print(f"       ... and {count - 3} more")
        except Exception as e:
            print(f"     ERROR querying equipment: {e}")

except Exception as e:
    print(f"   ERROR: {e}")

# 4. Check equipment with missing site_id
try:
    print("\n4. EQUIPMENT WITH POTENTIALLY MISSING BUILDING_ID")
    print("-" * 70)
    equip = client.table("equipment").select("id, code, name, site_id").is_("site_id", "null").execute()
    orphan_count = len(equip.data) if equip.data else 0
    print(f"   Orphaned equipment (null site_id): {orphan_count}")
    if equip.data and orphan_count > 0:
        for eq in equip.data[:5]:
            print(f"     - {eq.get('code', 'N/A')}: {eq.get('name', 'N/A')}")
        if orphan_count > 5:
            print(f"     ... and {orphan_count - 5} more")
except Exception as e:
    print(f"   ERROR: {e}")

# 5. Check JSON fallback data
print("\n5. JSON FALLBACK DATA")
print("-" * 70)
from pathlib import Path  # noqa: E402

json_equipment_file = Path("/opt/bms-intelligence/backend/app/data/equipment.json")
if json_equipment_file.exists():
    with open(json_equipment_file) as f:
        json_data = json.load(f)
    print(f"   equipment.json exists with {len(json_data)} records")
    # Show building distribution
    building_dist = {}
    for eq in json_data:
        building = eq.get("site_code", "UNKNOWN")
        building_dist[building] = building_dist.get(building, 0) + 1
    for building, count in sorted(building_dist.items()):
        print(f"     - {building}: {count} equipment")
else:
    print("   equipment.json not found")

# 6. Repository test
print("\n6. EQUIPMENT REPOSITORY TEST")
print("-" * 70)
from app.database.repositories.equipment_repository import EquipmentRepository  # noqa: E402

repo = EquipmentRepository()

# Test get_by_site_code for site-002
try:
    equipment = repo.get_by_site_code("site-002")
    print(f"   repo.get_by_site_code('site-002'): {len(equipment)} items")
    if equipment:
        for eq in equipment[:3]:
            print(f"     - {eq.get('code', 'N/A')}: {eq.get('name', 'N/A')}")
        if len(equipment) > 3:
            print(f"     ... and {len(equipment) - 3} more")
except Exception as e:
    print(f"   ERROR: {e}")

print("\n" + "=" * 70)
