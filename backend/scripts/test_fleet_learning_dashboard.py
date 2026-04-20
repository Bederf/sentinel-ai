#!/usr/bin/env python
"""
Test script for Fleet Learning API.

Tests all /api/fleet/* endpoints to verify the complete infrastructure works.
Run after starting backend: ./start-backend.sh
"""

import asyncio
import json
import sys
from typing import Any

import httpx

BASE_URL = "http://localhost:9095"
TIMEOUT = 30


class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    END = "\033[0m"


async def test_endpoint(
    name: str, method: str = "GET", endpoint: str = "", expected_fields: list | None = None
) -> bool:
    """Test a single endpoint."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            url = f"{BASE_URL}{endpoint}"
            print(f"\n{Colors.CYAN}Testing:{Colors.END} {method} {endpoint}")

            if method == "GET":
                response = await client.get(url)
            elif method == "POST":
                response = await client.post(url)
            else:
                raise ValueError(f"Unsupported method: {method}")

            status_ok = 200 <= response.status_code < 300
            status_color = Colors.GREEN if status_ok else Colors.RED
            print(f"  Status: {status_color}{response.status_code}{Colors.END}")

            if response.status_code >= 400:
                print(f"  Error: {response.text[:200]}")
                return False

            try:
                data = response.json()
                print(f"  Response keys: {list(data.keys())}")

                if expected_fields:
                    missing = [f for f in expected_fields if f not in data]
                    if missing:
                        print(f"  {Colors.YELLOW}Warning:{Colors.END} Missing fields: {missing}")
                        return False

                print(f"  {Colors.GREEN}✓ OK{Colors.END}")
                return True
            except json.JSONDecodeError:
                print(f"  {Colors.RED}Error: Invalid JSON response{Colors.END}")
                return False

    except httpx.ConnectError:
        print(f"  {Colors.RED}Error: Cannot connect to {BASE_URL}{Colors.END}")
        print("  Please ensure backend is running: ./start-backend.sh")
        return False
    except Exception as e:
        print(f"  {Colors.RED}Error: {e}{Colors.END}")
        return False


async def run_all_tests() -> dict[str, Any]:
    """Run all Fleet Learning API tests."""
    print(f"\n{Colors.CYAN}{'=' * 60}")
    print("Fleet Learning API Test Suite")
    print(f"{'=' * 60}{Colors.END}\n")

    tests = [
        # Fleet aggregation
        ("Fleet Summary", "GET", "/api/fleet/summary", ["fleet_overview", "type_distribution", "top_failure_patterns"]),
        ("Failure Patterns", "GET", "/api/fleet/failure-patterns", ["patterns", "total"]),
        (
            "Risk Distribution",
            "GET",
            "/api/fleet/risk-distribution",
            ["total_equipment", "distribution", "sites_with_critical"],
        ),
        ("Benchmarks", "GET", "/api/fleet/benchmarks", ["benchmarks", "total"]),
        # Global models
        ("Global Models List", "GET", "/api/fleet/global-models", ["models", "total"]),
        # Fine-tuned models
        ("Fine-Tuned Models List", "GET", "/api/fleet/fine-tuned", ["models", "total"]),
        ("Improvement Summary", "GET", "/api/fleet/fine-tuned/improvement", ["models_count", "avg_improvement_pct"]),
        ("Fine-Tune History", "GET", "/api/fleet/fine-tuned/history", ["history"]),
        # Global model history
        ("Global Models History", "GET", "/api/fleet/global-models/history", ["history"]),
    ]

    results = {"passed": 0, "failed": 0, "errors": []}

    for name, method, endpoint, expected_fields in tests:
        success = await test_endpoint(name, method, endpoint, expected_fields)
        if success:
            results["passed"] += 1
        else:
            results["failed"] += 1
            results["errors"].append(name)

    # Print summary
    print(f"\n{Colors.CYAN}{'=' * 60}")
    print("Test Summary")
    print(f"{'=' * 60}{Colors.END}")
    print(f"{Colors.GREEN}Passed: {results['passed']}{Colors.END}")
    print(f"{Colors.RED}Failed: {results['failed']}{Colors.END}")

    if results["errors"]:
        print(f"\n{Colors.YELLOW}Failed tests:{Colors.END}")
        for err in results["errors"]:
            print(f"  - {err}")

    print()
    return results


async def test_imports() -> bool:
    """Test that all backend modules can be imported."""
    print(f"\n{Colors.CYAN}Testing module imports...{Colors.END}\n")

    modules = [
        ("ml.fleet.aggregator", "get_fleet_aggregator"),
        ("ml.fleet.global_model", "get_global_model_trainer"),
        ("ml.fleet.fine_tuning", "get_local_fine_tuner"),
    ]

    import_errors = []

    for module_name, func_name in modules:
        try:
            print(f"  Importing {module_name}.{func_name}...", end=" ")
            exec(f"from {module_name} import {func_name}")
            print(f"{Colors.GREEN}✓{Colors.END}")
        except ImportError as e:
            print(f"{Colors.RED}✗ Error: {e}{Colors.END}")
            import_errors.append((module_name, str(e)))

    if import_errors:
        print(f"\n{Colors.RED}Import failures detected!{Colors.END}")
        for mod, err in import_errors:
            print(f"  {mod}: {err}")
        return False

    return True


async def main():
    """Main test runner."""
    # First test imports
    imports_ok = await test_imports()

    # Then test API endpoints
    results = await run_all_tests()

    # Exit code
    sys.exit(0 if results["failed"] == 0 and imports_ok else 1)


if __name__ == "__main__":
    asyncio.run(main())
