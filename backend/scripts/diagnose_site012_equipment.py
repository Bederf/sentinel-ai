#!/usr/bin/env python3
"""Diagnostic script to check what equipment is actually in Supabase for site-012."""

import sys
from pathlib import Path

from dotenv import load_dotenv

# Load .env file
load_dotenv(Path(__file__).parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from app.database.repositories import SiteRepository
    from app.database.supabase_client import get_supabase_client

    client = get_supabase_client()
    building_repo = SiteRepository()

    print("=" * 70)
    print("SITE-012 EQUIPMENT DIAGNOSTIC")
    print("=" * 70)

    # Step 1: Get building info
    print("\n[1] Getting building info for site-012...")
    building = building_repo.get_by_id("site-012")
    if not building:
        print("❌ Building not found!")
        sys.exit(1)

    site_id = building["id"]
    print(f"✓ Building UUID: {site_id}")
    print(f"✓ Building Name: {building['name']}")

    # Step 2: Query equipment directly from Supabase
    print("\n[2] Querying equipment table directly...")
    equipment_result = (
        client.table("equipment")
        .select("id, code, name, status, health_score, type, site_id", count="exact")
        .eq("site_id", site_id)
        .execute()
    )

    print(f"✓ Total equipment in table: {equipment_result.count}")

    # Step 3: Use SiteRepository.get_equipment()
    print("\n[3] Using SiteRepository.get_equipment()...")
    equipment_list = building_repo.get_equipment("site-012")
    print(f"✓ Equipment from repository: {len(equipment_list)}")

    # Step 4: Show all equipment
    print("\n[4] Equipment breakdown by status:")
    status_counts = {}
    for eq in equipment_result.data:
        status = eq.get("status", "unknown")
        if status not in status_counts:
            status_counts[status] = []
        status_counts[status].append({"code": eq["code"], "name": eq["name"], "health": eq.get("health_score", "N/A")})

    for status in sorted(status_counts.keys()):
        items = status_counts[status]
        print(f"\n  Status: {status.upper()} ({len(items)} items)")
        for item in items[:5]:  # Show first 5
            print(f"    - {item['code']}: {item['name']} (health: {item['health']})")
        if len(items) > 5:
            print(f"    ... and {len(items) - 5} more")

    # Step 5: Check for duplicates
    print("\n[5] Checking for duplicate codes...")
    codes = [eq["code"] for eq in equipment_result.data]
    duplicates = [code for code in set(codes) if codes.count(code) > 1]
    if duplicates:
        print(f"⚠️  Found {len(duplicates)} duplicate codes:")
        for dup in duplicates:
            print(f"    - {dup} appears {codes.count(dup)} times")
    else:
        print("✓ No duplicate codes found")

    # Step 6: Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Equipment Count: {equipment_result.count}")
    print("Expected Count: 19")
    print(f"Difference: {equipment_result.count - 19}")

    if equipment_result.count > 19:
        print("\n⚠️  ISSUE: Supabase has more equipment than expected!")
        print("Possible causes:")
        print("  1. Seeding script added duplicates")
        print("  2. Equipment was added after initial seeding")
        print("  3. Multiple seeding runs without deletion")

except Exception as e:
    print(f"❌ Error: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)
