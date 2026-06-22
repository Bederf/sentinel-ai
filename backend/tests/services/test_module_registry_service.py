"""Unit tests for module registry base-vs-add-on rules."""

import pytest

from app.models.module_registry import MODULE_DEFINITIONS, ModuleType
from app.services.module_registry_service import (
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
    """15 base modules should be non-deactivatable; add-ons should be optional."""
    assert len(NON_DEACTIVATABLE_MODULES) == 15
    # Platform base
    assert ModuleType.KPI in NON_DEACTIVATABLE_MODULES
    assert ModuleType.ML in NON_DEACTIVATABLE_MODULES
    assert ModuleType.SIMBIOT in NON_DEACTIVATABLE_MODULES
    assert ModuleType.LOGGING in NON_DEACTIVATABLE_MODULES
    # Building system base
    assert ModuleType.HVAC in NON_DEACTIVATABLE_MODULES
    assert ModuleType.ENERGY in NON_DEACTIVATABLE_MODULES
    assert ModuleType.LIGHTING in NON_DEACTIVATABLE_MODULES
    assert ModuleType.SOLAR in NON_DEACTIVATABLE_MODULES
    assert ModuleType.WATER in NON_DEACTIVATABLE_MODULES
    assert ModuleType.FIRE in NON_DEACTIVATABLE_MODULES
    assert ModuleType.SECURITY in NON_DEACTIVATABLE_MODULES
    assert ModuleType.DIGITAL_TWIN in NON_DEACTIVATABLE_MODULES
    # Control add-ons should NOT be in base
    assert ModuleType.HVAC_CONTROL not in NON_DEACTIVATABLE_MODULES
    assert ModuleType.ENERGY_CONTROL not in NON_DEACTIVATABLE_MODULES
    assert ModuleType.SOLAR_CONTROL not in NON_DEACTIVATABLE_MODULES


def test_activate_control_addon(monkeypatch):
    """Control add-ons can be activated without dependencies."""
    service = _new_registry_service(monkeypatch)

    result = service.activate_module("site-test", "Test Site", ModuleType.HVAC_CONTROL)
    assert result.module_type == ModuleType.HVAC_CONTROL


def test_fire_module_defaults_to_monitoring_only(monkeypatch):
    """New Fire module activations must not enable cause/effect control by default."""
    service = _new_registry_service(monkeypatch)

    result = service.activate_module("site-test", "Test Site", ModuleType.FIRE)

    assert result.config["auto_mode"] is False
    assert result.config["commissioned_cause_effect"] is False
    assert result.config["authority"] == "fire_panel_and_bms"
    assert result.config["sentinel_role"] == "monitoring_only"


def test_deactivate_base_module_blocked(monkeypatch):
    """Base-pack modules cannot be deactivated."""
    service = _new_registry_service(monkeypatch)

    with pytest.raises(ValueError):
        service.deactivate_module("site-test", ModuleType.HVAC)


def test_deactivate_addon_succeeds(monkeypatch):
    """Add-on modules can be deactivated."""
    service = _new_registry_service(monkeypatch)

    service.activate_module("site-test", "Test Site", ModuleType.MAINTENANCE)
    result = service.deactivate_module("site-test", ModuleType.MAINTENANCE)
    assert result is True


def test_module_type_count():
    """There should be exactly 34 module types and all must be defined in the registry."""
    assert len(ModuleType.__members__) == 34


def test_module_definitions_cover_all_module_types():
    """Registry definitions should exist for every persisted module ID."""
    assert set(MODULE_DEFINITIONS) == set(ModuleType)
    assert ModuleType.BLOCK_BOOKING in MODULE_DEFINITIONS
    assert MODULE_DEFINITIONS[ModuleType.HVAC].mandatory is True
    assert MODULE_DEFINITIONS[ModuleType.MAINTENANCE].mandatory is False
