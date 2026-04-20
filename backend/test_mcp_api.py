"""
Test script for SIMBIOT MCP API endpoints.

Run with: python test_mcp_api.py (backend must be running on port 9095)

Tests all MCP endpoints:
- GET  /api/mcp/simbiot/info - Server manifest
- GET  /api/mcp/simbiot/tools - List all tools
- GET  /api/mcp/simbiot/tools/{name} - Get specific tool schema
- POST /api/mcp/simbiot/call - Execute tools
"""

import sys

import requests

BASE_URL = "http://localhost:9095/api/mcp/simbiot"


def test_server_info():
    """Test GET /info endpoint."""
    print("Testing GET /info...")
    response = requests.get(f"{BASE_URL}/info")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    data = response.json()
    assert data["name"] == "simbiot-mcp"
    assert data["tool_count"] >= 12
    print(f"  OK: Server: {data['name']} v{data['version']} ({data['tool_count']} tools)")


def test_list_tools():
    """Test GET /tools endpoint."""
    print("Testing GET /tools...")
    response = requests.get(f"{BASE_URL}/tools")
    assert response.status_code == 200
    tools = response.json()
    assert len(tools) >= 12
    print(f"  OK: {len(tools)} tools available")
    for tool in tools[:5]:
        print(f"    - {tool['name']}")
    print("    ...")


def test_get_tool_schema():
    """Test GET /tools/{name} endpoint."""
    print("Testing GET /tools/get_buildings...")
    response = requests.get(f"{BASE_URL}/tools/get_buildings")
    assert response.status_code == 200
    schema = response.json()
    assert schema["name"] == "get_buildings"
    assert "input_schema" in schema
    print("  OK: Schema retrieved for 'get_buildings'")


def test_get_tool_schema_not_found():
    """Test GET /tools/{name} with unknown tool."""
    print("Testing GET /tools/unknown_tool (404 expected)...")
    response = requests.get(f"{BASE_URL}/tools/unknown_tool")
    assert response.status_code == 404
    print("  OK: Unknown tool returns 404")


def test_call_get_buildings():
    """Test POST /call with get_buildings tool."""
    print("Testing POST /call (get_buildings)...")
    response = requests.post(f"{BASE_URL}/call", json={"tool_name": "get_buildings", "arguments": {}})
    assert response.status_code == 200
    data = response.json()
    assert data["tool_name"] == "get_buildings"
    assert data["error"] is None
    buildings = data["result"].get("buildings", [])
    print(f"  OK: {len(buildings)} buildings returned")


def test_call_get_devices():
    """Test POST /call with get_devices tool."""
    print("Testing POST /call (get_devices)...")
    response = requests.post(f"{BASE_URL}/call", json={"tool_name": "get_devices", "arguments": {}})
    assert response.status_code == 200
    data = response.json()
    assert data["tool_name"] == "get_devices"
    devices = data["result"].get("devices", [])
    print(f"  OK: {len(devices)} devices returned")


def test_call_get_alarms():
    """Test POST /call with get_alarms tool."""
    print("Testing POST /call (get_alarms)...")
    response = requests.post(f"{BASE_URL}/call", json={"tool_name": "get_alarms", "arguments": {"limit": 10}})
    assert response.status_code == 200
    data = response.json()
    assert data["tool_name"] == "get_alarms"
    alarms = data["result"].get("alarms", [])
    print(f"  OK: {len(alarms)} alarms returned (limit 10)")


def test_call_read_device_point():
    """Test POST /call with read_device_point tool."""
    print("Testing POST /call (read_device_point)...")
    response = requests.post(
        f"{BASE_URL}/call",
        json={
            "tool_name": "read_device_point",
            "arguments": {"device_id": "S001-CHILLER-B1-001", "point_name": "chw_supply_temp"},
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["tool_name"] == "read_device_point"
    # Either we get a value or an error message (if device not found)
    result = data["result"]
    if "error" in result:
        print(f"  OK: Device not found response: {result['error']}")
    else:
        print(f"  OK: Point value: {result['value']} {result.get('unit', '')}")


def test_call_unknown_tool():
    """Test POST /call with unknown tool returns 400 error."""
    print("Testing POST /call (unknown_tool, 400 expected)...")
    response = requests.post(f"{BASE_URL}/call", json={"tool_name": "unknown_tool", "arguments": {}})
    assert response.status_code == 400
    print("  OK: Unknown tool returns 400")


def test_call_get_health_score():
    """Test POST /call with get_health_score tool."""
    print("Testing POST /call (get_health_score)...")
    response = requests.post(
        f"{BASE_URL}/call", json={"tool_name": "get_health_score", "arguments": {"building_id": "site-001"}}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["tool_name"] == "get_health_score"
    result = data["result"]
    if "error" in result:
        print(f"  OK: Building not found response: {result['error']}")
    else:
        print(f"  OK: Health score: {result['score']} ({result['status']})")


if __name__ == "__main__":
    print("=" * 60)
    print("SIMBIOT MCP API Tests")
    print("=" * 60)
    print()

    try:
        test_server_info()
        test_list_tools()
        test_get_tool_schema()
        test_get_tool_schema_not_found()
        test_call_get_buildings()
        test_call_get_devices()
        test_call_get_alarms()
        test_call_read_device_point()
        test_call_unknown_tool()
        test_call_get_health_score()

        print()
        print("=" * 60)
        print("All tests passed!")
        print("=" * 60)
        sys.exit(0)

    except requests.exceptions.ConnectionError:
        print()
        print("ERROR: Backend not running!")
        print("Start with: cd backend && source venv/bin/activate && uvicorn app.main:app --port 9095")
        sys.exit(1)
    except AssertionError as e:
        print()
        print(f"TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print()
        print(f"ERROR: {e}")
        sys.exit(1)
