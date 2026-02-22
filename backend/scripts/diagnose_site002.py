#!/usr/bin/env python3
"""
Diagnostic script: Check Supabase data for site-002
Shows: buildings, equipment, zones, desks, technicians
"""

import sys
from pathlib import Path
from datetime import datetime

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database.supabase_client import get_supabase_client  # noqa: E402


def check_building(client):
    """Check if site-002 building record exists."""
    print("\n" + "=" * 60)
    print("1️⃣  BUILDING CHECK")
    print("=" * 60)

    try:
        result = client.table("buildings").select("*").eq("code", "site-002").execute()

        if result.data:
            building = result.data[0]
            print("✅ Building found:")
            print(f"   ID: {building.get('id')}")
            print(f"   Code: {building.get('code')}")
            print(f"   Name: {building.get('name')}")
            print(f"   Address: {building.get('address')}")
            print(f"   Floors: {building.get('floors')}")
            print(f"   SQM: {building.get('sqm')}")
            return building.get("id")
        else:
            print("❌ Building 'site-002' NOT FOUND in Supabase")
            return None

    except Exception as e:
        print(f"❌ Error querying buildings: {e}")
        return None


def check_equipment(client, building_id):
    """Check equipment records for site-002."""
    print("\n" + "=" * 60)
    print("2️⃣  EQUIPMENT CHECK")
    print("=" * 60)

    try:
        result = (
            client.table("equipment")
            .select("code, name, type, status, health_score")
            .eq("building_id", building_id)
            .execute()
        )

        count = len(result.data) if result.data else 0
        print(f"Equipment records found: {count}")

        if count > 0:
            print("\n✅ Sample equipment (first 10):")
            for i, eq in enumerate(result.data[:10], 1):
                print(f"   {i}. {eq.get('code')} - {eq.get('name')} ({eq.get('type')}) [Status: {eq.get('status')}]")

            if count > 10:
                print(f"   ... and {count - 10} more")

            # Group by type
            types = {}
            for eq in result.data:
                eq_type = eq.get("type", "unknown")
                types[eq_type] = types.get(eq_type, 0) + 1

            print("\nEquipment by type:")
            for eq_type, count in sorted(types.items()):
                print(f"   - {eq_type}: {count}")
        else:
            print("❌ NO equipment records found for site-002")

        return count

    except Exception as e:
        print(f"❌ Error querying equipment: {e}")
        return 0


def check_zones(client, building_id):
    """Check zones for site-002."""
    print("\n" + "=" * 60)
    print("3️⃣  ZONES CHECK")
    print("=" * 60)

    try:
        result = (
            client.table("zones").select("zone_id, floor, zone_type, area_sqm").eq("building_id", building_id).execute()
        )

        count = len(result.data) if result.data else 0
        print(f"Zone records found: {count}")

        if count > 0:
            print("\n✅ Zones:")
            for zone in result.data:
                print(
                    f"   - {zone.get('zone_id')} ({zone.get('floor')}) "
                    f"{zone.get('zone_type')} - {zone.get('area_sqm')} sqm"
                )
        else:
            print("❌ NO zones found for site-002")

        return count

    except Exception as e:
        print(f"❌ Error querying zones: {e}")
        return 0


def check_desks(client, building_id):
    """Check desks for site-002."""
    print("\n" + "=" * 60)
    print("4️⃣  DESKS CHECK")
    print("=" * 60)

    try:
        result = client.table("desks").select("desk_id, floor, zone_id").eq("building_id", building_id).execute()

        count = len(result.data) if result.data else 0
        print(f"Desk records found: {count}")

        if count > 0:
            print("\n✅ Sample desks (first 5):")
            for i, desk in enumerate(result.data[:5], 1):
                print(f"   {i}. {desk.get('desk_id')} (Floor: {desk.get('floor')}, Zone: {desk.get('zone_id')})")

            if count > 5:
                print(f"   ... and {count - 5} more")
        else:
            print("❌ NO desks found for site-002")

        return count

    except Exception as e:
        print(f"❌ Error querying desks: {e}")
        return 0


def check_technicians(client, building_id):
    """Check technician assignments for site-002."""
    print("\n" + "=" * 60)
    print("5️⃣  TECHNICIANS CHECK")
    print("=" * 60)

    try:
        # Get technicians assigned to this building
        result = (
            client.table("site_technicians")
            .select("id, technician_id, specialty, is_primary")
            .eq("building_id", building_id)
            .execute()
        )

        count = len(result.data) if result.data else 0
        print(f"Technician assignments found: {count}")

        if count > 0:
            print("\n✅ Technician assignments:")
            for assignment in result.data:
                primary = "PRIMARY" if assignment.get("is_primary") else "secondary"
                print(f"   - Technician {assignment.get('technician_id')}: {assignment.get('specialty')} ({primary})")
        else:
            print("❌ NO technician assignments found for site-002")

        return count

    except Exception as e:
        print(f"❌ Error querying technicians: {e}")
        return 0


def check_technician_details(client):
    """Get technician details."""
    print("\n" + "=" * 60)
    print("6️⃣  TECHNICIAN DETAILS")
    print("=" * 60)

    try:
        result = client.table("technicians").select("*").execute()

        count = len(result.data) if result.data else 0
        print(f"Total technicians in system: {count}")

        if count > 0:
            print("\n✅ All technicians:")
            for tech in result.data:
                print(
                    f"   - {tech.get('code')}: {tech.get('name')} ({tech.get('email')}) - Active: {tech.get('active')}"
                )

        return count

    except Exception as e:
        print(f"❌ Error querying technician details: {e}")
        return 0


def main():
    """Main diagnostic function."""
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 12 + "SUPABASE DIAGNOSTIC: SITE-002" + " " * 17 + "║")
    print("║" + " " * 58 + "║")
    print("║" + f" Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}" + " " * 29 + "║")
    print("╚" + "=" * 58 + "╝")

    try:
        client = get_supabase_client()
        print("\n✅ Connected to Supabase")
    except Exception as e:
        print(f"\n❌ Failed to connect to Supabase: {e}")
        print("\n   Make sure:")
        print("   1. SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are set in .env")
        print("   2. Supabase instance is accessible")
        return False

    # Run checks
    building_id = check_building(client)

    if building_id:
        eq_count = check_equipment(client, building_id)
        zone_count = check_zones(client, building_id)
        desk_count = check_desks(client, building_id)
        tech_count = check_technicians(client, building_id)
    else:
        print("\n⚠️  Skipping equipment/zone/desk checks (building not found)")
        eq_count = zone_count = desk_count = tech_count = 0

    check_technician_details(client)

    # Summary
    print("\n" + "=" * 60)
    print("📊 SUMMARY")
    print("=" * 60)

    if building_id:
        print(f"✅ Building: EXISTS (ID: {building_id})")
        print(f"{'✅' if eq_count > 0 else '❌'} Equipment: {eq_count} records")
        print(f"{'✅' if zone_count > 0 else '❌'} Zones: {zone_count} records")
        print(f"{'✅' if desk_count > 0 else '❌'} Desks: {desk_count} records")
        print(f"{'✅' if tech_count > 0 else '❌'} Technicians: {tech_count} assignments")

        if eq_count == 0:
            print("\n⚠️  PROBLEM IDENTIFIED:")
            print("   Equipment data is missing from Supabase for site-002")
            print("\n   To fix, run one of:")
            print("   1. python scripts/sync_to_supabase_final.py")
            print("      (syncs zones and desks from local JSON)")
            print("   2. Create equipment seeding script for site-002")
            print("      (needed to sync 68+ equipment records)")
            return False
        else:
            print("\n✅ Site-002 appears properly configured in Supabase!")
            return True
    else:
        print("❌ Building: NOT FOUND")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
