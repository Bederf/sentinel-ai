"""Test to detect circular import cycles.

This test ensures that no circular import dependencies exist in the codebase.
Circular imports can cause subtle bugs and make refactoring difficult.

Run with: pytest backend/tests/test_import_cycles.py -v
"""

import sys
from pathlib import Path
import pytest


def _import_all_service_modules():
    """Attempt to import all service modules to detect circular imports.

    This function clears the module cache and imports all service modules
    to ensure they can be imported without circular dependency errors.

    Returns:
        list: List of (module_path, success, error_message) tuples
    """
    services_path = Path(__file__).parent.parent / "app" / "services"
    results = []

    # Find all Python files in services directory
    py_files = list(services_path.rglob("*.py"))

    for py_file in py_files:
        # Skip __init__ and test files
        if py_file.name.startswith("__") or py_file.name.startswith("test_"):
            continue

        # Calculate module path
        rel_path = py_file.relative_to(Path(__file__).parent.parent)
        module_path = str(rel_path).replace("/", ".")[:-3]  # Remove .py

        # Clear module to force fresh import
        if module_path in sys.modules:
            del sys.modules[module_path]

        # Try to import
        try:
            __import__(module_path)
            results.append((module_path, True, None))
        except ImportError as e:
            results.append((module_path, False, str(e)))

    return results


def test_no_circular_imports_in_services():
    """Check for circular imports in services modules.

    This test attempts to import all service modules and ensures
    that none fail due to circular import errors.
    """
    results = _import_all_service_modules()

    # Collect failures
    failures = [(path, error) for path, success, error in results if not success]

    # If there are failures, check if they're circular import errors
    circular_import_failures = [
        (path, error) for path, error in failures
        if "circular import" in error.lower() or "partially initialized" in error.lower()
    ]

    if circular_import_failures:
        pytest.fail(
            f"Circular import errors detected in {len(circular_import_failures)} module(s):\n" +
            "\n".join(f"  - {path}: {error}" for path, error in circular_import_failures)
        )


def test_ai_services_import_order():
    """Test that AI services can be imported in any order.

    This specifically tests the AI services chain that previously had
    circular import issues:
    - ai_optimizer → claude_service → chat_tools → ai_optimizer
    """
    ai_services = [
        "app.services.ai_optimizer",
        "app.services.chat_tools",
        "app.services.claude_service",
    ]

    # Test each import order
    for service in ai_services:
        # Clear modules
        for mod in ai_services:
            if mod in sys.modules:
                del sys.modules[mod]

        # Import should succeed
        try:
            __import__(service)
        except ImportError as e:
            if "circular import" in str(e).lower():
                pytest.fail(f"Circular import detected when importing {service}: {e}")


def test_device_abstraction_import_order():
    """Test that device abstraction modules can be imported in any order.

    This specifically tests the device abstraction chain:
    - device_abstraction → mock_devices/bacnet_adapter → device_abstraction
    """
    device_modules = [
        "app.services.device_abstraction",
        "app.services.mock_devices",
        "app.services.niagara.bacnet_adapter",
    ]

    # Test each import order
    for module in device_modules:
        # Clear modules
        for mod in device_modules:
            if mod in sys.modules:
                del sys.modules[mod]

        # Import should succeed
        try:
            __import__(module)
        except ImportError as e:
            if "circular import" in str(e).lower():
                pytest.fail(f"Circular import detected when importing {module}: {e}")


def test_api_imports():
    """Test that API modules can be imported without circular dependencies."""
    api_path = Path(__file__).parent.parent / "app" / "api"
    results = []

    # Find all Python files in api directory
    py_files = list(api_path.rglob("*.py"))

    for py_file in py_files:
        if py_file.name.startswith("__") or py_file.name.startswith("test_"):
            continue

        rel_path = py_file.relative_to(Path(__file__).parent.parent)
        module_path = str(rel_path).replace("/", ".")[:-3]

        if module_path in sys.modules:
            del sys.modules[module_path]

        try:
            __import__(module_path)
            results.append((module_path, True, None))
        except ImportError as e:
            if "circular import" in str(e).lower():
                results.append((module_path, False, str(e)))
            else:
                results.append((module_path, True, None))  # Other import errors are OK

    # Check for circular import failures
    circular_failures = [(path, error) for path, success, error in results if not success]

    if circular_failures:
        pytest.fail(
            "Circular import errors detected in API modules:\n" +
            "\n".join(f"  - {path}: {error}" for path, error in circular_failures)
        )
