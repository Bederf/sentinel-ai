"""
Equipment Lookup API Integration Tests

Tests for /api/equipment-lookup endpoints:
- GET /fault-code - Fault code lookup
- GET /parts - Parts search
- POST /search - Natural language search

Run tests:
    cd backend
    python test_equipment_api.py

Requires backend server running on localhost:9095
"""

import asyncio
import sys

try:
    import httpx
except ImportError:
    print("ERROR: httpx not installed. Run: pip install httpx")
    sys.exit(1)


BASE_URL = "http://localhost:9095"
TIMEOUT = 30.0  # seconds


async def test_fault_code_lookup():
    """Test fault code lookup endpoint."""
    print("=" * 60)
    print("Testing GET /api/equipment-lookup/fault-code")
    print("=" * 60)

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        # Test 1: Valid fault code lookup
        print("\n1. Testing valid Carrier E4 fault code...")
        response = await client.get(
            f"{BASE_URL}/api/equipment-lookup/fault-code",
            params={"manufacturer": "Carrier", "fault_code": "E4", "model": "30XA"},
        )

        if response.status_code == 200:
            data = response.json()
            fault = data.get("fault", {})
            print(f"   ✓ Status: {response.status_code}")
            print(f"   ✓ Fault name: {fault.get('name', 'N/A')}")
            print(f"   ✓ Severity: {fault.get('severity', 'N/A')}")
            print(f"   ✓ Causes: {len(fault.get('probable_causes', []))}")
            print(f"   ✓ Parts: {len(data.get('parts', []))}")
            print(f"   ✓ Forums: {len(data.get('forum_solutions', []))}")
        else:
            print(f"   ✗ FAILED: Status {response.status_code}")
            print(f"   Response: {response.text}")
            return False

        # Test 2: Case-insensitive lookup
        print("\n2. Testing case-insensitive lookup (carrier, e4)...")
        response = await client.get(
            f"{BASE_URL}/api/equipment-lookup/fault-code", params={"manufacturer": "carrier", "fault_code": "e4"}
        )

        if response.status_code == 200:
            data = response.json()
            print(f"   ✓ Status: {response.status_code}")
            print(f"   ✓ Found fault: {data.get('fault', {}).get('name', 'N/A')}")
        else:
            print(f"   ✗ FAILED: Status {response.status_code}")
            return False

        # Test 3: ABB VSD fault code
        print("\n3. Testing ABB VSD fault code (FAULT_001)...")
        response = await client.get(
            f"{BASE_URL}/api/equipment-lookup/fault-code",
            params={"manufacturer": "ABB", "fault_code": "FAULT_001", "model": "ACS580"},
        )

        if response.status_code == 200:
            data = response.json()
            fault = data.get("fault", {})
            print(f"   ✓ Status: {response.status_code}")
            print(f"   ✓ Fault name: {fault.get('name', 'N/A')}")
        else:
            print(f"   ✗ FAILED: Status {response.status_code}")
            return False

        # Test 4: 404 for unknown fault code
        print("\n4. Testing 404 for unknown fault code...")
        response = await client.get(
            f"{BASE_URL}/api/equipment-lookup/fault-code", params={"manufacturer": "Carrier", "fault_code": "XXXX999"}
        )

        if response.status_code == 404:
            print(f"   ✓ Status: {response.status_code} (expected)")
        else:
            print(f"   ✗ FAILED: Expected 404, got {response.status_code}")
            return False

    print("\n✅ Fault code lookup tests PASSED")
    return True


async def test_parts_search():
    """Test parts search endpoint."""
    print("\n" + "=" * 60)
    print("Testing GET /api/equipment-lookup/parts")
    print("=" * 60)

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        # Test 1: Search by part number
        print("\n1. Testing search by part number...")
        response = await client.get(
            f"{BASE_URL}/api/equipment-lookup/parts", params={"part_number": "30HX-405-332", "manufacturer": "Carrier"}
        )

        if response.status_code == 200:
            data = response.json()
            print(f"   ✓ Status: {response.status_code}")
            print(f"   ✓ Results: {len(data)} part(s)")
            if data:
                print(f"   ✓ First result: {data[0].get('part_name', 'N/A')}")
        else:
            print(f"   ✗ FAILED: Status {response.status_code}")
            return False

        # Test 2: Search by description
        print("\n2. Testing search by description...")
        response = await client.get(f"{BASE_URL}/api/equipment-lookup/parts", params={"part_description": "oil filter"})

        if response.status_code == 200:
            data = response.json()
            print(f"   ✓ Status: {response.status_code}")
            print(f"   ✓ Results: {len(data)} part(s)")
        else:
            print(f"   ✗ FAILED: Status {response.status_code}")
            return False

        # Test 3: 400 for missing parameters
        print("\n3. Testing 400 for missing parameters...")
        response = await client.get(f"{BASE_URL}/api/equipment-lookup/parts")

        if response.status_code == 400:
            print(f"   ✓ Status: {response.status_code} (expected)")
        else:
            print(f"   ✗ FAILED: Expected 400, got {response.status_code}")
            return False

    print("\n✅ Parts search tests PASSED")
    return True


async def test_natural_language_search():
    """Test natural language search endpoint."""
    print("\n" + "=" * 60)
    print("Testing POST /api/equipment-lookup/search")
    print("=" * 60)

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        # Test 1: Fault code in query
        print("\n1. Testing fault code detection (carrier fault E4)...")
        response = await client.post(f"{BASE_URL}/api/equipment-lookup/search", params={"query": "carrier fault E4"})

        if response.status_code == 200:
            data = response.json()
            print(f"   ✓ Status: {response.status_code}")
            print(f"   ✓ Query type: {data.get('query_type', 'N/A')}")
            if data.get("fault"):
                print(f"   ✓ Found fault: {data['fault'].get('name', 'N/A')}")
        else:
            print(f"   ✗ FAILED: Status {response.status_code}")
            return False

        # Test 2: Keyword search
        print("\n2. Testing keyword search (chiller making loud noise)...")
        response = await client.post(
            f"{BASE_URL}/api/equipment-lookup/search", params={"query": "chiller making loud noise"}
        )

        if response.status_code == 200:
            data = response.json()
            print(f"   ✓ Status: {response.status_code}")
            print(f"   ✓ Query type: {data.get('query_type', 'N/A')}")
            print(f"   ✓ Suggestions: {len(data.get('suggestions', []))}")
            print(f"   ✓ Forums: {len(data.get('forum_solutions', []))}")
        else:
            print(f"   ✗ FAILED: Status {response.status_code}")
            return False

        # Test 3: Search with manufacturer
        print("\n3. Testing search with manufacturer parameter...")
        response = await client.post(
            f"{BASE_URL}/api/equipment-lookup/search", params={"query": "VSD showing fault 29", "manufacturer": "ABB"}
        )

        if response.status_code == 200:
            data = response.json()
            print(f"   ✓ Status: {response.status_code}")
            print(f"   ✓ Manufacturer: {data.get('manufacturer', 'N/A')}")
        else:
            print(f"   ✗ FAILED: Status {response.status_code}")
            return False

    print("\n✅ Natural language search tests PASSED")
    return True


async def test_api_docs():
    """Test that API documentation is accessible."""
    print("\n" + "=" * 60)
    print("Testing API Documentation")
    print("=" * 60)

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(f"{BASE_URL}/docs")

        if response.status_code == 200:
            print(f"   ✓ OpenAPI docs available at {BASE_URL}/docs")
        else:
            print(f"   ✗ Docs not accessible: {response.status_code}")
            return False

    print("\n✅ API documentation test PASSED")
    return True


async def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("EQUIPMENT LOOKUP API INTEGRATION TESTS")
    print("=" * 60)
    print(f"\nBase URL: {BASE_URL}")
    print(f"Timeout: {TIMEOUT}s")

    # Check server is running
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{BASE_URL}/")
            if response.status_code != 200:
                print(f"\n❌ Server not responding correctly at {BASE_URL}")
                sys.exit(1)
    except httpx.ConnectError:
        print(f"\n❌ Cannot connect to server at {BASE_URL}")
        print("   Make sure the backend is running: uvicorn app.main:app --port 9095")
        sys.exit(1)

    # Run tests
    results = []

    results.append(await test_fault_code_lookup())
    results.append(await test_parts_search())
    results.append(await test_natural_language_search())
    results.append(await test_api_docs())

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = sum(results)
    total = len(results)

    if passed == total:
        print(f"\n✅ All {total} test suites PASSED!")
        print("\nAPI Endpoints Ready:")
        print(f"  GET  {BASE_URL}/api/equipment-lookup/fault-code")
        print("       ?manufacturer=Carrier&fault_code=E4&model=30XA")
        print(f"  GET  {BASE_URL}/api/equipment-lookup/parts")
        print("       ?part_number=30HX-405-332")
        print(f"  POST {BASE_URL}/api/equipment-lookup/search")
        print("       ?query=carrier+fault+E4")
        print(f"\nAPI Docs: {BASE_URL}/docs")
    else:
        print(f"\n❌ {total - passed} of {total} test suites FAILED")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
