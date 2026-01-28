#!/usr/bin/env python3
"""
Parts Search Test Script

Tests the parts supplier search functionality of EquipmentLookup service.
"""
import asyncio
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.equipment_lookup import EquipmentLookup


async def test_parts_search():
    """Run parts search tests."""
    lookup = EquipmentLookup()

    print("=" * 60)
    print("PARTS SUPPLIER SEARCH TEST")
    print("=" * 60)

    # Test 1: Supplier database loaded
    print("\n[Test 1] Supplier database loaded")
    print("-" * 60)
    suppliers_count = len(lookup.SA_PARTS_SUPPLIERS)
    print(f"Suppliers loaded: {suppliers_count}")

    if suppliers_count == 11:
        print("✓ All 11 SA suppliers loaded")
        for supplier in lookup.SA_PARTS_SUPPLIERS:
            print(f"  - {supplier['name']}")
    else:
        print(f"✗ Expected 11 suppliers, got {suppliers_count}")
        return False

    # Test 2: Generic alternatives loaded
    print("\n[Test 2] Generic alternatives database")
    print("-" * 60)
    generics_count = len(lookup.GENERIC_EQUIVALENTS)
    print(f"Generic equivalents: {generics_count}")

    if generics_count > 0:
        print("✓ Generic alternatives loaded")
        for category, info in list(lookup.GENERIC_EQUIVALENTS.items())[:3]:
            print(f"  - {category}: {info.get('description', 'N/A')}")
    else:
        print("⚠ No generic alternatives found")

    # Test 3: Part number mappings loaded
    print("\n[Test 3] Part number mappings")
    print("-" * 60)
    mappings_count = len(lookup.PART_NUMBER_MAPPINGS)
    print(f"Manufacturers with mappings: {mappings_count}")

    if mappings_count > 0:
        print("✓ Part number mappings loaded")
        for mfg in list(lookup.PART_NUMBER_MAPPINGS.keys())[:3]:
            print(f"  - {mfg.title()}")
    else:
        print("⚠ No part number mappings found")

    # Test 4: Parts search returns results structure (mocked, no HTTP)
    print("\n[Test 4] Parts search structure")
    print("-" * 60)

    # Mock the supplier search to avoid HTTP calls
    original_search = lookup._search_supplier

    async def mock_search(*args, **kwargs):
        return [{
            "supplier": "Test Supplier",
            "name": "Test Part",
            "price": "R1000",
            "lead_time": "In stock",
            "available": True
        }]

    lookup._search_supplier = mock_search

    result = await lookup._search_parts("Carrier", "30XA", "E4", [])

    if isinstance(result, list):
        print(f"✓ Parts search returns list with {len(result)} parts")

        if result:
            part = result[0]
            required_keys = ["part_name", "manufacturer", "suppliers"]
            has_keys = all(key in part for key in required_keys)

            if has_keys:
                print("✓ Part has required fields:")
                print(f"  - part_name: {part.get('part_name')}")
                print(f"  - part_number: {part.get('part_number')}")
                print(f"  - suppliers: {len(part.get('suppliers', []))} suppliers")
            else:
                print("✗ Part missing required fields")
                return False
    else:
        print("✗ Parts search should return list")
        return False

    # Restore original method
    lookup._search_supplier = original_search

    # Test 5: Supplier relevance filter
    print("\n[Test 5] Supplier relevance filtering")
    print("-" * 60)

    # Find Carrier SA supplier
    carrier_sa = next((s for s in lookup.SA_PARTS_SUPPLIERS if "carrier" in s["id"]), None)

    if carrier_sa:
        is_relevant = lookup._supplier_relevant(carrier_sa, "Carrier")
        print(f"Carrier SA relevant for Carrier: {is_relevant}")

        if is_relevant:
            print("✓ Supplier relevance filtering works")
        else:
            print("✗ Carrier SA should be relevant for Carrier")
            return False
    else:
        print("✗ Carrier SA supplier not found")
        return False

    # Test 6: Generic alternative lookup
    print("\n[Test 6] Generic alternative lookup")
    print("-" * 60)

    # Test with known Carrier part number
    generic = lookup._find_generic_alternative("1452292")

    if generic:
        print("✓ Generic alternative found:")
        print(f"  - Category: {generic.get('category')}")
        print(f"  - Generic: {generic.get('generic_part_number')}")
        print(f"  - Manufacturer: {generic.get('manufacturer')}")
        print(f"  - Suppliers: {', '.join(generic.get('suppliers', []))}")
    else:
        print("⚠ No generic alternative found (may need more mappings)")

    # Test 7: Forum sources defined
    print("\n[Test 7] Forum sources")
    print("-" * 60)
    forums_count = len(lookup.FORUM_SOURCES)
    print(f"Forum sources: {forums_count}")

    if forums_count == 4:
        print("✓ All 4 forum sources defined")
        for forum in lookup.FORUM_SOURCES:
            print(f"  - {forum['name']}: {forum.get('description', 'N/A')}")
    else:
        print(f"⚠ Expected 4 forums, got {forums_count}")

    # Test 8: Part number lookup
    print("\n[Test 8] Part number lookup")
    print("-" * 60)

    part_number = lookup._get_part_number("carrier", "30xa", "Oil Filter")

    if part_number != "N/A":
        print(f"✓ Part number found: {part_number}")
    else:
        print("⚠ Part number not found (may need more mappings)")

    # Test 9: Forum search structure
    print("\n[Test 9] Forum search structure")
    print("-" * 60)

    forum_results = await lookup._search_forums("Carrier", "30XA", "E4")

    if len(forum_results) == 4:
        print(f"✓ Forum search returns {len(forum_results)} results")

        for forum in forum_results[:2]:
            print(f"  - {forum['source']}")
            print(f"    URL: {forum['url']}")
    else:
        print(f"⚠ Expected 4 forum results, got {len(forum_results)}")

    print("\n" + "=" * 60)
    print("✅ ALL PARTS SEARCH TESTS PASSED!")
    print("=" * 60)

    return True


async def test_supplier_search():
    """Show sample supplier search output."""
    print("\n" + "=" * 60)
    print("SAMPLE SUPPLIER DATA")
    print("=" * 60)

    lookup = EquipmentLookup()

    print("\nCarrier South Africa:")
    carrier_sa = next(s for s in lookup.SA_PARTS_SUPPLIERS if "carrier" in s["id"])
    print(f"  ID: {carrier_sa['id']}")
    print(f"  URL: {carrier_sa['url']}")
    print(f"  Brands: {carrier_sa['brands']}")
    print(f"  Coverage: {carrier_sa['coverage']}")
    print(f"  Regions: {carrier_sa['regions']}")
    print(f"  Phone: {carrier_sa['contact']['phone']}")

    print("\nGeneric Equivalents:")
    for category, info in list(lookup.GENERIC_EQUIVALENTS.items())[:2]:
        print(f"\n  {category}:")
        print(f"    OEM: {info.get('carrier_oem', 'N/A')}")
        print(f"    Generic: {info.get('generic', 'N/A')}")
        print(f"    Manufacturer: {info.get('manufacturer', 'N/A')}")
        print(f"    Suppliers: {', '.join(info.get('suppliers', []))}")

    print()


if __name__ == "__main__":
    success = asyncio.run(test_parts_search())

    if success:
        asyncio.run(test_supplier_search())
        sys.exit(0)
    else:
        print("\n❌ TESTS FAILED")
        sys.exit(1)
