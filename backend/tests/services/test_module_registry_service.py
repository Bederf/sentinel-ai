"""Unit tests for module registry base-vs-add-on rules."""

import pytest

from app.models.module_registry import ModuleType
from app.services.module_registry_service import (
    MODULE_DEPENDENCIES,
    NON_DEACTIVATABLE_MODULES,
    ModuleRegistryService,
)


def _new_registry_service(monkeypatch) -> ModuleRegistryService:
    """Build isolated service instance without file I/O side effects."""
    monkeypatch.setattr(ModuleRegistryService, "_load_configs", lambda self: None)
    monkeypatch.setattr(ModuleRegistryService, "_load_presets", lambda self: None)
    service = ModuleRegistryService()
    monkeypatch.setattr(service, "_save_configs", lambda: None)
    service._site_configs = {}
    return service


def test_base_pack_modules_are_non_deactivatable():
    """Core modules should remain protected and control should remain optional."""
    assert ModuleType.HVAC in NON_DEACTIVATABLE_MODULES
    assert ModuleType.ML in NON_DEACTIVATABLE_MODULES
    assert ModuleType.SIMBIOT in NON_DEACTIVATABLE_MODULES
    assert ModuleType.CONTROL not in NON_DEACTIVATABLE_MODULES


def test_addon_dependencies_require_control():
    """Automation add-ons should depend on CONTROL."""
    assert MODULE_DEPENDENCIES[ModuleType.SOLAR] == ModuleType.CONTROL
    assert MODULE_DEPENDENCIES[ModuleType.LIGHTING] == ModuleType.CONTROL


def test_activate_solar_requires_control(monkeypatch):
    """SOLAR activation must fail until CONTROL is active."""
    service = _new_registry_service(monkeypatch)

    with pytest.raises(ValueError):
        service.activate_module("site-test", "Test Site", ModuleType.SOLAR)

    service.activate_module("site-test", "Test Site", ModuleType.CONTROL)
    solar = service.activate_module("site-test", "Test Site", ModuleType.SOLAR)
    assert solar.module_type == ModuleType.SOLAR


def test_deactivate_base_module_blocked(monkeypatch):
    """Base-pack modules cannot be deactivated."""
    service = _new_registry_service(monkeypatch)

    with pytest.raises(ValueError):
        service.deactivate_module("site-test", ModuleType.HVAC)
