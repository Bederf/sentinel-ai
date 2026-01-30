"""
Test stdio MCP server.

Run with: python test_mcp_stdio.py
"""

import subprocess
import json
import sys
import os

# Set up environment
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ['PYTHONPATH'] = os.path.dirname(os.path.abspath(__file__))

def test_stdio_server():
    """Test stdio transport with JSON-RPC requests."""
    print("=" * 60)
    print("Testing stdio MCP server")
    print("=" * 60)
    print()

    # Start server
    proc = subprocess.Popen(
        [sys.executable, "-m", "app.mcp.simbiot_stdio"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=os.path.dirname(os.path.abspath(__file__))
    )

    try:
        # Test 1: Initialize
        print("Test 1: Initialize")
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "clientInfo": {"name": "test-client", "version": "1.0.0"}
            }
        }
        proc.stdin.write(json.dumps(request) + "\n")
        proc.stdin.flush()
        response_line = proc.stdout.readline()
        response = json.loads(response_line)
        print(f"  OK: Server: {response['result']['serverInfo']['name']} v{response['result']['serverInfo']['version']}")
        print()

        # Test 2: List tools
        print("Test 2: List tools")
        request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list"
        }
        proc.stdin.write(json.dumps(request) + "\n")
        proc.stdin.flush()
        response_line = proc.stdout.readline()
        response = json.loads(response_line)
        tools = response['result']['tools']
        print(f"  OK: {len(tools)} tools available")
        for tool in tools[:5]:
            print(f"    - {tool['name']}")
        print("    ...")
        print()

        # Test 3: Call tool
        print("Test 3: Call get_buildings tool")
        request = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "get_buildings",
                "arguments": {}
            }
        }
        proc.stdin.write(json.dumps(request) + "\n")
        proc.stdin.flush()
        response_line = proc.stdout.readline()
        response = json.loads(response_line)
        content = response['result']['content'][0]['text']
        result = json.loads(content)
        buildings = result.get('buildings', [])
        print(f"  OK: {len(buildings)} buildings returned")
        print()

        # Test 4: Unknown method error
        print("Test 4: Unknown method (error handling)")
        request = {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "unknown_method"
        }
        proc.stdin.write(json.dumps(request) + "\n")
        proc.stdin.flush()
        response_line = proc.stdout.readline()
        response = json.loads(response_line)
        assert 'error' in response
        print(f"  OK: Unknown method returns error - {response['error']['code']}")
        print()

        print("=" * 60)
        print("All tests passed!")
        print("=" * 60)

    finally:
        # Cleanup
        proc.terminate()
        proc.wait(timeout=5)


if __name__ == "__main__":
    test_stdio_server()
