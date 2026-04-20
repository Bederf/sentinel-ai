"""Test to detect circular import cycles.

This test ensures that no circular import dependencies exist in the codebase.
Circular imports can cause subtle bugs and make refactoring difficult.

Run with: pytest backend/tests/test_import_cycles.py -v
"""

import sys
from pathlib import Path

import pytest


def _check_circular_imports(base_path: Path, label: str):
    """Check for circular imports without polluting sys.modules.

    Saves and restores original module references so singletons
    and closures in other tests are not broken.
    """
    results = []
    py_files = list(base_path.rglob("*.py"))
    saved_modules: dict[str, object] = {}

    for py_file in py_files:
        if py_file.name.startswith("__") or py_file.name.startswith("test_"):
            continue

        rel_path = py_file.relative_to(Path(__file__).parent.parent)
        module_path = str(rel_path).replace("/", ".")[:-3]

        if module_path in sys.modules:
            saved_modules[module_path] = sys.modules[module_path]
            del sys.modules[module_path]

        try:
            __import__(module_path)
            results.append((module_path, True, None))
        except ImportError as e:
            results.append((module_path, False, str(e)))

    # Restore original modules to prevent singleton pollution
    for mod_path, original_mod in saved_modules.items():
        sys.modules[mod_path] = original_mod

    return results


def _check_import_order(modules: list[str]):
    """Check modules can be imported in any order without circular deps.

    Saves and restores original module references after each attempt.
    """
    for service in modules:
        saved = {}
        for mod in modules:
            if mod in sys.modules:
                saved[mod] = sys.modules[mod]
                del sys.modules[mod]

        try:
            __import__(service)
        except ImportError as e:
            if "circular import" in str(e).lower():
                pytest.fail(f"Circular import detected when importing {service}: {e}")
        finally:
            # Restore original modules
            for mod_path, original_mod in saved.items():
                sys.modules[mod_path] = original_mod


def test_no_circular_imports_in_services():
    """Check for circular imports in services modules."""
    services_path = Path(__file__).parent.parent / "app" / "services"
    results = _check_circular_imports(services_path, "services")

    circular_import_failures = [
        (path, error)
        for path, success, error in results
        if not success and ("circular import" in error.lower() or "partially initialized" in error.lower())
    ]

    if circular_import_failures:
        pytest.fail(
            f"Circular import errors detected in {len(circular_import_failures)} module(s):\n"
            + "\n".join(f"  - {path}: {error}" for path, error in circular_import_failures)
        )


def test_ai_services_import_order():
    """Test that AI services can be imported in any order."""
    _check_import_order(
        [
            "app.services.ai_optimizer",
            "app.services.chat_tools",
            "app.services.claude_service",
        ]
    )


def test_device_abstraction_import_order():
    """Test that device abstraction modules can be imported in any order."""
    _check_import_order(
        [
            "app.services.device_abstraction",
            "app.services.bms_simulator.adapters.simulated_adapter",
            "app.services.niagara.bacnet_adapter",
        ]
    )


def test_api_imports():
    """Test that API modules can be imported without circular dependencies."""
    api_path = Path(__file__).parent.parent / "app" / "api"
    results = _check_circular_imports(api_path, "api")

    circular_failures = [
        (path, error) for path, success, error in results if not success and "circular import" in error.lower()
    ]

    if circular_failures:
        pytest.fail(
            "Circular import errors detected in API modules:\n"
            + "\n".join(f"  - {path}: {error}" for path, error in circular_failures)
        )
