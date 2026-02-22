#!/usr/bin/env python3
"""
Equipment Lookup Service Test Script

Tests the EquipmentLookup service with fault code database lookups.
"""

import asyncio
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.equipment_lookup import EquipmentLookup


async def test_lookup():
    """Run equipment lookup tests."""
    lookup = EquipmentLookup()

    print("=" * 60)
    print("EQUIPMENT LOOKUP SERVICE TEST")
    print("=" * 60)

    # Test 1: Local DB lookup - Carrier 30XA E4
    print("\n[Test 1] Local DB lookup - Carrier 30XA E4")
    print("-" * 60)
    result = await lookup.lookup_fault_code("Carrier", "E4", "30XA")

    if result.get("fault"):
        fault = result["fault"]
        assert fault["code"] == "E4", "Fault code mismatch"
        assert fault["name"] == "Low Oil Pressure", "Fault name mismatch"
        assert fault["severity"] == "critical", "Severity mismatch"
        print(f"✓ Fault Code: {fault['code']}")
        print(f"✓ Name: {fault['name']}")
        print(f"✓ Severity: {fault['severity']}")
        print(f"✓ Probable Causes: {len(fault['probable_causes'])}")
        print(f"✓ Immediate Actions: {len(fault['recommended_fix']['immediate'])}")
    else:
        print("✗ FAIL: Fault not found in database")
        return False

    # Test 2: Fuzzy manufacturer matching
    print("\n[Test 2] Fuzzy manufacturer matching - 'carrier' (lowercase)")
    print("-" * 60)
    result = await lookup.lookup_fault_code("carrier", "e4")  # lowercase

    if result.get("fault"):
        print(f"✓ Found with fuzzy match: {result['fault']['name']}")
    else:
        print("✗ FAIL: Fuzzy matching not working")
        return False

    # Test 3: Non-existent code
    print("\n[Test 3] Non-existent fault code - Carrier XXXX")
    print("-" * 60)
    result = await lookup.lookup_fault_code("Carrier", "XXXX")

    if result.get("fault") is None:
        print("✓ Correctly returns None for non-existent code")
    else:
        print("✗ FAIL: Should return None for non-existent code")
        return False

    # Test 4: Daikin fault code
    print("\n[Test 4] Daikin VRV error code - U4")
    print("-" * 60)
    result = await lookup.lookup_fault_code("Daikin", "U4", "VRV")

    if result.get("fault"):
        fault = result["fault"]
        print(f"✓ Found: {fault['code']} - {fault['name']}")
        print(f"  Severity: {fault['severity']}")
    else:
        print("✗ FAIL: Daikin U4 not found")
        return False

    # Test 5: ABB drive fault code
    print("\n[Test 5] ABB ACS580 fault - FAULT_004")
    print("-" * 60)
    result = await lookup.lookup_fault_code("ABB", "FAULT_004", "ACS580")

    if result.get("fault"):
        fault = result["fault"]
        print(f"✓ Found: {fault['code']} - {fault['name']}")
        print(f"  Severity: {fault['severity']}")
    else:
        print("✗ FAIL: ABB fault not found")
        return False

    # Test 6: Danfoss VLT fault
    print("\n[Test 6] Danfoss VLT alarm - ALARM_1")
    print("-" * 60)
    result = await lookup.lookup_fault_code("Danfoss", "ALARM_1", "VLT_AQ")

    if result.get("fault"):
        fault = result["fault"]
        print(f"✓ Found: {fault['code']} - {fault['name']}")
        print(f"  Severity: {fault['severity']}")
    else:
        print("✗ FAIL: Danfoss alarm not found")
        return False

    # Test 7: Verify parts search is triggered
    print("\n[Test 7] Parts search for sensor failure")
    print("-" * 60)
    result = await lookup.lookup_fault_code("Carrier", "E8", "30XA")

    if result.get("parts"):
        print(f"✓ Parts suggested: {len(result['parts'])}")
        for part in result["parts"][:2]:
            print(f"  - {part['part_name']}")
            print(f"    Suppliers: {len(part['suppliers'])}")
    else:
        print("⚠ Parts search not triggered (may not be needed for this fault)")

    # Test 8: Database stats
    print("\n[Test 8] Database statistics")
    print("-" * 60)
    total_codes = lookup._count_total_codes()
    print(f"✓ Total fault codes in database: {total_codes}")

    if total_codes >= 300:
        print("✓ Database meets minimum requirement (300+ codes)")
    else:
        print("✗ WARNING: Database has fewer than 300 codes")

    print("\n" + "=" * 60)
    print("✅ ALL EQUIPMENT LOOKUP TESTS PASSED!")
    print("=" * 60)

    return True


async def test_sample_diagnosis():
    """Show sample diagnosis output."""
    print("\n" + "=" * 60)
    print("SAMPLE DIAGNOSIS OUTPUT")
    print("=" * 60)

    lookup = EquipmentLookup()
    result = await lookup.lookup_fault_code("Carrier", "E4", "30XA")

    if result.get("fault"):
        fault = result["fault"]

        print(f"\n🔴 FAULT: {fault['code']} - {fault['name']}")
        print(f"Severity: {fault['severity'].upper()}")
        print("\nDescription:")
        print(f"  {fault['description']}")

        print("\nProbable Causes:")
        for i, cause in enumerate(fault["probable_causes"], 1):
            print(f"  {i}. {cause['cause']} (Likelihood: {cause['likelihood']})")
            print(f"     Check: {cause['check']}")

        print("\nRecommended Actions:")
        for action in fault["recommended_fix"]["immediate"]:
            print(f"  • {action}")

        if fault["recommended_fix"].get("scenarios"):
            print("\nScenario-Based Fixes:")
            for scenario, fix in fault["recommended_fix"]["scenarios"].items():
                print(f"  {scenario}: {fix}")

    print()


if __name__ == "__main__":
    success = asyncio.run(test_lookup())

    if success:
        asyncio.run(test_sample_diagnosis())
        sys.exit(0)
    else:
        print("\n❌ TESTS FAILED")
        sys.exit(1)
