"""Tests for _resolve_point_name in AIOptimizerService.

Covers alias table, exact match, fuzzy fallback, dropped points,
and edge cases across equipment types.
"""

from datetime import UTC, datetime

import pytest

from app.services.ai_optimizer import AIOptimizerService


class TestResolvePointName:
    """Tests for _resolve_point_name."""

    @pytest.fixture
    def service(self):
        return AIOptimizerService()

    @pytest.fixture
    def points_index(self):
        """Canonical point names per equipment code.

        Models the operating_data keys available on each equipment type.
        """
        return {
            "S002-AHU-101": {"setpoint", "temperature", "fan_speed", "humidity"},
            "S002-AHU-201": {"setpoint", "temperature", "fan_speed", "temperature_setpoint"},
            "S002-FCU-101": {"setpoint", "temperature", "fan_speed"},
            "S002-VAV-101": {"temperature_setpoint", "temperature", "valve_position"},
            "S002-CHILLER-B01": {"setpoint", "temperature"},
            "S002-CHILLER-B02": {"setpoint", "temperature"},
        }

    @pytest.fixture
    def time_zero(self):
        return datetime.now(UTC).isoformat()

    # ── Canonical point names  ──

    def _check_provenance_shape(self, provenance: dict):
        """Verify provenance dict has expected fields."""
        for key in ("raw", "resolved", "method", "confidence", "unit_raw", "unit_resolved", "note", "resolved_at"):
            assert key in provenance, f"Missing provenance field: {key}"

    # ── Test cases from the plan ──

    @pytest.mark.asyncio
    async def test_supply_setpoint_on_ahu(self, service, points_index):
        """supply_setpoint on AHU (has setpoint) → (setpoint, confidence=alias)."""
        resolved, provenance = await service._resolve_point_name("supply_setpoint", "S002-AHU-101", points_index)
        assert resolved == "setpoint"
        assert provenance["confidence"] == "alias"
        assert provenance["method"] == "alias_table"
        assert "global alias" in provenance["note"]

    @pytest.mark.asyncio
    async def test_supply_setpoint_on_fcu(self, service, points_index):
        """supply_setpoint on FCU (has setpoint) → (setpoint, confidence=alias)."""
        resolved, provenance = await service._resolve_point_name("supply_setpoint", "S002-FCU-101", points_index)
        assert resolved == "setpoint"
        assert provenance["confidence"] == "alias"

    @pytest.mark.asyncio
    async def test_chws_setpoint_on_chiller(self, service, points_index):
        """chws_setpoint on chiller (has setpoint) → (setpoint, confidence=alias)."""
        resolved, provenance = await service._resolve_point_name("chws_setpoint", "S002-CHILLER-B01", points_index)
        assert resolved == "setpoint"
        assert provenance["confidence"] == "alias"
        assert "global alias" in provenance["note"]

    @pytest.mark.asyncio
    async def test_chwr_setpoint_on_chiller_dropped(self, service, points_index):
        """chwr_setpoint on chiller → (None, confidence=dropped, note=dropped list)."""
        resolved, provenance = await service._resolve_point_name("chwr_setpoint", "S002-CHILLER-B01", points_index)
        assert resolved is None
        assert provenance["confidence"] == "dropped"
        assert "dropped list" in provenance["note"].lower()

    @pytest.mark.asyncio
    async def test_zone_setpoint_on_vav(self, service, points_index):
        """zone_setpoint on VAV (has temperature_setpoint) → (temperature_setpoint, confidence=alias)."""
        resolved, provenance = await service._resolve_point_name("zone_setpoint", "S002-VAV-101", points_index)
        assert resolved == "temperature_setpoint"
        assert provenance["confidence"] == "alias"
        assert "type-specific alias" in provenance["note"]
        assert "vav" in provenance["note"]

    @pytest.mark.asyncio
    async def test_zone_setpoint_on_fcu(self, service, points_index):
        """zone_setpoint on FCU (has only setpoint) → (setpoint, confidence=alias)."""
        resolved, provenance = await service._resolve_point_name("zone_setpoint", "S002-FCU-101", points_index)
        assert resolved == "setpoint"
        assert provenance["confidence"] == "alias"
        # FCU has no type-specific alias for zone_setpoint → falls through to global
        assert "global alias" in provenance["note"]

    @pytest.mark.asyncio
    async def test_damper_position_on_vav(self, service, points_index):
        """damper_position_pct on VAV (has valve_position) → (valve_position, confidence=alias)."""
        resolved, provenance = await service._resolve_point_name("damper_position_pct", "S002-VAV-101", points_index)
        assert resolved == "valve_position"
        assert provenance["confidence"] == "alias"
        assert "global alias" in provenance["note"]

    @pytest.mark.asyncio
    async def test_indoor_temp_on_ahu(self, service, points_index):
        """indoor_temp on AHU (has temperature) → (temperature, confidence=alias)."""
        resolved, provenance = await service._resolve_point_name("indoor_temp", "S002-AHU-101", points_index)
        assert resolved == "temperature"
        assert provenance["confidence"] == "alias"

    @pytest.mark.asyncio
    async def test_temperature_exact_match(self, service, points_index):
        """temperature on AHU (direct match) → (temperature, confidence=exact)."""
        resolved, provenance = await service._resolve_point_name("temperature", "S002-AHU-101", points_index)
        assert resolved == "temperature"
        assert provenance["confidence"] == "exact"
        assert provenance["method"] == "exact"

    @pytest.mark.asyncio
    async def test_fan_speed_pct_dropped(self, service, points_index):
        """fan_speed_pct on AHU (strips to 'fan_speed', exact match found) → (fan_speed, confidence=fuzzy).

        NOTE: fan_speed exists on S002-AHU-101 and fan_speed_pct aliases to
        fan_speed via the global alias table, so this gives alias, not fuzzy.
        """
        resolved, provenance = await service._resolve_point_name("fan_speed_pct", "S002-AHU-101", points_index)
        assert resolved == "fan_speed"
        assert provenance["confidence"] == "alias"

    @pytest.mark.asyncio
    async def test_temp_ambiguous_fuzzy(self, service, points_index):
        """temp on AHU (has both temperature and temperature_setpoint) → ambiguous fuzzy match."""
        resolved, provenance = await service._resolve_point_name("temp", "S002-AHU-201", points_index)
        # temp is not in any alias table; stripping makes it "temp" which is unchanged
        # available points: setpoint, temperature, fan_speed, temperature_setpoint
        # No suffix/prefix strips to a single match — should be dropped
        assert resolved is None
        assert provenance["confidence"] == "dropped"

    @pytest.mark.asyncio
    async def test_temp_on_ahu_101(self, service, points_index):
        """temp on AHU-101 (no temperature_setpoint) → drops (no fuzzy match)."""
        resolved, provenance = await service._resolve_point_name("temp", "S002-AHU-101", points_index)
        # S002-AHU-101 has: setpoint, temperature, fan_speed, humidity
        # "temp" stripped = "temp", no change → no fuzzy match found
        assert resolved is None
        assert provenance["confidence"] == "dropped"

    @pytest.mark.asyncio
    async def test_empty_points(self, service, points_index):
        """Equipment code with no points in the index → (None, confidence=dropped)."""
        resolved, provenance = await service._resolve_point_name("setpoint", "NONEXISTENT-EQUIPMENT", points_index)
        assert resolved is None
        assert provenance["confidence"] == "dropped"
        assert "no points" in provenance["note"].lower()

    @pytest.mark.asyncio
    async def test_no_point_in_action(self, service, points_index):
        """When raw_point_name is empty but code is resolved → direct pass-through handled by caller."""
        resolved, provenance = await service._resolve_point_name("", "S002-AHU-101", points_index)
        # empty string won't match anything available
        assert resolved is None
        assert "no match" in provenance["note"].lower()

    @pytest.mark.asyncio
    async def test_exact_match_case_insensitive(self, service, points_index):
        """Point names should match case-insensitively."""
        resolved, provenance = await service._resolve_point_name("TEMPERATURE", "S002-AHU-101", points_index)
        assert resolved == "temperature"
        assert provenance["confidence"] == "exact"

    @pytest.mark.asyncio
    async def test_humidity_no_match(self, service, points_index):
        """humidity_setpoint on AHU (has humidity, not humidity_setpoint) → fuzzy match to humidity."""
        resolved, provenance = await service._resolve_point_name("humidity_setpoint", "S002-AHU-101", points_index)
        # S002-AHU-101 has "humidity" but not "humidity_setpoint"
        # humidity_setpoint → alias table → humidity_setpoint (not in available)
        # → fuzzy strips "_setpoint" → "humidity" which IS in available
        assert resolved == "humidity"
        assert provenance["confidence"] == "fuzzy"

    @pytest.mark.asyncio
    async def test_dropped_point_chw_return_temp_sp(self, service, points_index):
        """chw_return_temp_sp → dropped unconditionally."""
        resolved, provenance = await service._resolve_point_name("chw_return_temp_sp", "S002-CHILLER-B01", points_index)
        assert resolved is None
        assert provenance["confidence"] == "dropped"
        assert "dropped list" in provenance["note"].lower()

    @pytest.mark.asyncio
    async def test_provenance_shape(self, service, points_index):
        """Every provenance dict has the expected schema shape."""
        _, provenance = await service._resolve_point_name("setpoint", "S002-AHU-101", points_index)
        self._check_provenance_shape(provenance)

    @pytest.mark.asyncio
    async def test_dropped_provenance_shape(self, service, points_index):
        """Dropped provenance dict also has full shape."""
        _, provenance = await service._resolve_point_name("chwr_setpoint", "S002-CHILLER-B01", points_index)
        self._check_provenance_shape(provenance)
        assert provenance["resolved"] is None

    @pytest.mark.asyncio
    async def test_resolved_at_iso8601(self, service, points_index):
        """resolved_at is ISO8601 UTC."""
        _, provenance = await service._resolve_point_name("setpoint", "S002-AHU-101", points_index)
        assert provenance["resolved_at"].endswith("Z") or "+" in provenance["resolved_at"]
        assert "T" in provenance["resolved_at"]

    @pytest.mark.asyncio
    async def test_unit_fields_stubbed(self, service, points_index):
        """unit_raw and unit_resolved are None (stubbed for future validation)."""
        _, provenance = await service._resolve_point_name("setpoint", "S002-AHU-101", points_index)
        assert provenance["unit_raw"] is None
        assert provenance["unit_resolved"] is None
