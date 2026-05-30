from __future__ import annotations

import pytest

from app.adapters.residential import SUPPORTED_PLATFORMS, build_adapter
from app.adapters.residential.solarman import SolarmanAdapter
from app.adapters.residential.victron_vrm import VictronVRMAdapter

# ── SUPPORTED_PLATFORMS content ───────────────────────────────────────────────

def test_both_platforms_present():
    assert "solarman" in SUPPORTED_PLATFORMS
    assert "victron" in SUPPORTED_PLATFORMS


def test_solarman_entry_has_required_fields():
    entry = SUPPORTED_PLATFORMS["solarman"]
    assert "name" in entry
    assert "adapter_class" in entry
    assert "brands" in entry
    assert entry["adapter_class"] is SolarmanAdapter


def test_victron_entry_has_required_fields():
    entry = SUPPORTED_PLATFORMS["victron"]
    assert "name" in entry
    assert "adapter_class" in entry
    assert "brands" in entry
    assert entry["adapter_class"] is VictronVRMAdapter


def test_victron_brands_includes_victron_energy():
    assert "Victron Energy" in SUPPORTED_PLATFORMS["victron"]["brands"]


def test_no_adapter_class_exposed_in_name_field():
    for pid, entry in SUPPORTED_PLATFORMS.items():
        assert "adapter_class" in entry
        assert isinstance(entry["name"], str), f"{pid}: name must be str"


# ── build_adapter ─────────────────────────────────────────────────────────────

def test_build_adapter_solarman_returns_correct_type():
    adapter = build_adapter(
        "solarman",
        site_config={"email": "test@example.com", "password": "pw", "site_id": "s"},
        app_id="aid",
        app_secret="sec",
    )
    assert isinstance(adapter, SolarmanAdapter)


def test_build_adapter_victron_returns_correct_type():
    adapter = build_adapter(
        "victron",
        site_config={"username": "user@example.com", "password": "pw", "site_id": "s"},
    )
    assert isinstance(adapter, VictronVRMAdapter)


def test_build_adapter_unknown_platform_raises_value_error():
    with pytest.raises(ValueError) as exc_info:
        build_adapter("growatt", site_config={})
    assert "Unsupported platform" in str(exc_info.value)
    assert "growatt" in str(exc_info.value)


def test_build_adapter_unknown_platform_never_returns_none():
    with pytest.raises(ValueError):
        build_adapter("fronius", site_config={})


def test_build_adapter_empty_string_raises_value_error():
    with pytest.raises(ValueError):
        build_adapter("", site_config={})
