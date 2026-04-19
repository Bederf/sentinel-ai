"""Tests for SentinelWriteWhitelist — Phase 185 Wave 2.

Tests:
- Equipment type extraction from SENTINEL naming convention
- Catch-all points allow generic names (setpoint, on_off, mode)
- Equipment type not in whitelist → denied
- Point not whitelisted for valid equipment type → denied
- Valid equipment + whitelisted point → allowed
- Version tracking
- Missing whitelist file → all writes blocked
"""

import json

import pytest

from app.services.sentinel_write_whitelist import (
    SentinelWriteWhitelist,
    WhitelistResult,
    _extract_equipment_type,
    get_sentinel_write_whitelist,
)

# ----------------------------------------------------------------------------- #
# Equipment type extraction
# ----------------------------------------------------------------------------- #


class TestExtractEquipmentType:
    @pytest.mark.parametrize(
        "equipment_id,expected",
        [
            ("S002-CHILLER-B1-001", "CHILLER"),
            ("S002-AHU-MX-001", "AHU"),
            ("S002-VAV-L1-001", "VAV"),
            ("S002-FCU-101", "FCU"),
            ("S002-DALI-L1-001", "DALI"),
            ("S002-BESS-001", "BESS"),
            ("S002-GEN-001", "GEN"),
            ("S002-PUMP-B1-001", "PUMP"),
            ("S002-BOILER-B1-001", "BOILER"),
            ("S001-ACCESS-001", "ACCESS"),
            ("S001-FIRE-001", "FIRE"),
        ],
    )
    def test_extracts_correct_type(self, equipment_id, expected):
        assert _extract_equipment_type(equipment_id) == expected

    def test_unknown_format_returns_uppercase(self):
        assert _extract_equipment_type("SOMEID") == "SOMEID"


# ----------------------------------------------------------------------------- #
# Whitelist loading and querying
# ----------------------------------------------------------------------------- #


class TestWhitelistLoad:
    def test_loads_valid_json_file(self, tmp_path):
        whitelist_file = tmp_path / "whitelist.json"
        whitelist_file.write_text('{"version": "test-v1", "rules": [], "catch_all_points": []}')

        wl = SentinelWriteWhitelist(whitelist_file=whitelist_file)
        wl.load()

        assert wl.version == "test-v1"

    def test_missing_file_logs_warning_and_blocks_all(self, tmp_path, caplog):
        import logging

        caplog.set_level(logging.WARNING)

        wl = SentinelWriteWhitelist(whitelist_file=tmp_path / "nonexistent.json")
        result = wl.can_write("S002-AHU-001", "occupied_cooling_setpoint")

        assert result.allowed is False
        assert "not found" in result.reason

    def test_reload_forces_reload(self, tmp_path):
        whitelist_file = tmp_path / "wl.json"
        whitelist_file.write_text('{"version": "v1", "rules": [], "catch_all_points": []}')

        wl = SentinelWriteWhitelist(whitelist_file=whitelist_file)
        wl.load()
        assert wl.version == "v1"

        whitelist_file.write_text('{"version": "v2", "rules": [], "catch_all_points": []}')
        wl.reload()

        assert wl.version == "v2"


# ----------------------------------------------------------------------------- #
# Point matching and catch-all
# ----------------------------------------------------------------------------- #


class TestPointMatching:
    @pytest.fixture
    def whitelist_file(self, tmp_path):
        f = tmp_path / "whitelist.json"
        f.write_text(
            json.dumps(
                {
                    "version": "1",
                    "catch_all_points": ["setpoint", "on_off", "mode"],
                    "rules": [
                        {"equipment_type": "AHU", "points": ["occupied_cooling_setpoint", "ahu_on_off"]},
                        {"equipment_type": "CHILLER", "points": ["supply_water_temperature_setpoint"]},
                    ],
                }
            )
        )
        return f

    def test_catch_all_point_allowed(self, whitelist_file):
        wl = SentinelWriteWhitelist(whitelist_file=whitelist_file)
        # "setpoint" is in catch_all_points even though AHU has no explicit rule for it
        result = wl.can_write("S002-AHU-001", "setpoint")
        assert result.allowed is True

    def test_non_catch_all_point_requires_explicit_rule(self, whitelist_file):
        wl = SentinelWriteWhitelist(whitelist_file=whitelist_file)
        result = wl.can_write("S002-AHU-001", "occupied_cooling_setpoint")
        assert result.allowed is True

    def test_equipment_type_not_in_whitelist(self, whitelist_file):
        wl = SentinelWriteWhitelist(whitelist_file=whitelist_file)
        result = wl.can_write("S002-VAV-001", "setpoint")
        assert result.allowed is False
        assert "not in the write whitelist" in result.reason

    def test_point_not_whitelisted_for_equipment(self, whitelist_file):
        wl = SentinelWriteWhitelist(whitelist_file=whitelist_file)
        result = wl.can_write("S002-AHU-001", "some_weird_point")
        assert result.allowed is False
        assert "not whitelisted" in result.reason

    def test_whitelist_version_returned(self, whitelist_file):
        wl = SentinelWriteWhitelist(whitelist_file=whitelist_file)
        result = wl.can_write("S002-AHU-001", "occupied_cooling_setpoint")
        assert result.whitelist_version == "1"


# ----------------------------------------------------------------------------- #
# WhitelistResult dataclass
# ----------------------------------------------------------------------------- #


class TestWhitelistResult:
    def test_allowed_result_has_ok_reason(self):
        r = WhitelistResult(
            allowed=True, equipment_type="AHU", point_name="setpoint", reason="ok", whitelist_version="1"
        )
        assert r.allowed is True
        assert r.reason == "ok"

    def test_denied_result_has_explanation(self):
        r = WhitelistResult(
            allowed=False,
            equipment_type="AHU",
            point_name="bad_point",
            reason="Point 'bad_point' is not whitelisted for AHU writes",
            whitelist_version="1",
        )
        assert r.allowed is False
        assert "not whitelisted" in r.reason


# ----------------------------------------------------------------------------- #
# Singleton
# ----------------------------------------------------------------------------- #


class TestSingleton:
    def test_get_sentinel_write_whitelist_returns_same_instance(self):
        # Reset module-level singleton
        import app.services.sentinel_write_whitelist as mod

        mod._whitelist = None

        wl1 = get_sentinel_write_whitelist()
        wl2 = get_sentinel_write_whitelist()
        assert wl1 is wl2
