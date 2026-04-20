"""
Test SSE MCP server.

Run with: python test_mcp_sse.py (backend must be running on port 9095)
"""

import json
import sys

import requests

BASE_URL = "http://localhost:9095/api/mcp/sse"


def test_sse_request_endpoint():
    """Test SSE POST request endpoint."""
    print("=" * 60)
    print("Testing SSE MCP server (POST endpoint)")
    print("=" * 60)
    print()

    # Test 1: Initialize
    print("Test 1: Initialize")
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": "2024-11-05", "clientInfo": {"name": "test-client", "version": "1.0.0"}},
    }
    response = requests.post(f"{BASE_URL}/request", json=request)
    assert response.status_code == 200
    result = response.json()
    print(f"  OK: Server: {result['result']['serverInfo']['name']} v{result['result']['serverInfo']['version']}")
    print()

    # Test 2: List tools
    print("Test 2: List tools")
    request = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
    response = requests.post(f"{BASE_URL}/request", json=request)
    assert response.status_code == 200
    result = response.json()
    tools = result["result"]["tools"]
    print(f"  OK: {len(tools)} tools available")
    for tool in tools[:5]:
        print(f"    - {tool['name']}")
    print("    ...")
    print()

    # Test 3: Call tool - get_buildings
    print("Test 3: Call get_buildings tool")
    request = {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "get_buildings", "arguments": {}}}
    response = requests.post(f"{BASE_URL}/request", json=request)
    assert response.status_code == 200
    result = response.json()
    content = result["result"]["content"][0]["text"]
    data = json.loads(content)
    buildings = data.get("buildings", [])
    print(f"  OK: {len(buildings)} buildings returned")
    print()

    # Test 4: Call tool - get_devices
    print("Test 4: Call get_devices tool")
    request = {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "get_devices", "arguments": {}}}
    response = requests.post(f"{BASE_URL}/request", json=request)
    assert response.status_code == 200
    result = response.json()
    content = result["result"]["content"][0]["text"]
    data = json.loads(content)
    devices = data.get("devices", [])
    print(f"  OK: {len(devices)} devices returned")
    print()

    # Test 5: Unknown method error
    print("Test 5: Unknown method (error handling)")
    request = {"jsonrpc": "2.0", "id": 5, "method": "unknown_method"}
    response = requests.post(f"{BASE_URL}/request", json=request)
    assert response.status_code == 200
    result = response.json()
    assert result["result"]["error"] is not None
    print(f"  OK: Unknown method returns error - {result['result']['error']['code']}")
    print()

    print("=" * 60)
    print("All tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    try:
        test_sse_request_endpoint()
    except requests.exceptions.ConnectionError:
        print()
        print("ERROR: Backend not running!")
        print("Start with: cd backend && uvicorn app.main:app --port 9095")
        sys.exit(1)
    except AssertionError as e:
        print()
        print(f"TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print()
        print(f"ERROR: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
