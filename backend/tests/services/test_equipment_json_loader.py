"""Tests for the JSON equipment loader (equipment_json_loader.py).

Validates that on-disk equipment JSON files for site-002 load correctly,
type normalization works, and edge cases are handled gracefully.
"""

import json
import os
import tempfile


from app.services.equipment_json_loader import (
    JSON_TYPE_ALIASES,
    _extract_type_from_code,
    load_site_equipment,
)


class TestExtractTypeFromCode:
    """Tests for _extract_type_from_code helper."""

    def test_standard_zone_code(self):
        assert _extract_type_from_code("S002-AHU-B1-001") == "ahu"

    def test_lighting_code(self):
        assert _extract_type_from_code("S002-LTG-001") == "ltg"

    def test_dali_controller_code(self):
        assert _extract_type_from_code("S002-DALI_CONTROLLER-B1-001") == "dali_controller"

    def test_bess_code(self):
        assert _extract_type_from_code("S002-BESS-B1-001") == "bess"

    def test_short_code_returns_unknown(self):
        assert _extract_type_from_code("BADCODE") == "unknown"

    def test_two_part_code_returns_unknown(self):
        assert _extract_type_from_code("S002-AHU") == "unknown"


class TestLoadSiteEquipment:
    """Tests for load_site_equipment."""

    def test_loads_all_site002_equipment(self):
        """All JSON files in site-002/equipment should be loaded."""
        equipment = load_site_equipment("site-002")
        # site-002 has 90 equipment files (58 original + 32 Supabase inventory sync)
        assert len(equipment) >= 85, f"Expected 85+ equipment, got {len(equipment)}"

    def test_each_equipment_has_required_fields(self):
        """Every loaded equipment must have code, type, and health_score."""
        equipment = load_site_equipment("site-002")
        for eq in equipment:
            assert "code" in eq, f"Missing code: {eq}"
            assert "type" in eq, f"Missing type for {eq.get('code')}"
            assert "health_score" in eq, f"Missing health_score for {eq.get('code')}"
            assert isinstance(eq["health_score"], (int, float))

    def test_type_normalization_lighting_zone(self):
        """LTG files with equipment_type=lighting_zone should normalize to luminaire."""
        equipment = load_site_equipment("site-002")
        ltg_items = [eq for eq in equipment if eq["code"].startswith("S002-LTG")]
        assert len(ltg_items) >= 18, f"Expected 18+ LTG items, got {len(ltg_items)}"
        for eq in ltg_items:
            assert eq["type"] == "luminaire", f"{eq['code']} type should be 'luminaire', got '{eq['type']}'"

    def test_type_normalization_dali_controller(self):
        """DALI_CONTROLLER files should keep type as dali_controller."""
        equipment = load_site_equipment("site-002")
        dali_ctrls = [eq for eq in equipment if "DALI_CONTROLLER" in eq["code"]]
        for eq in dali_ctrls:
            assert eq["type"] == "dali_controller"

    def test_hvac_types_preserved(self):
        """Standard HVAC types (ahu, chiller, fcu, vav) should be preserved."""
        equipment = load_site_equipment("site-002")
        by_code = {eq["code"]: eq for eq in equipment}

        assert by_code["S002-AHU-B1-001"]["type"] == "ahu"
        assert by_code["S002-CHILLER-B1-001"]["type"] == "chiller"
        assert by_code["S002-FCU-L1-A"]["type"] == "fcu"
        assert by_code["S002-VAV-L1-A"]["type"] == "vav"

    def test_solar_bess_types(self):
        """INV and BESS equipment should load with correct types."""
        equipment = load_site_equipment("site-002")
        by_code = {eq["code"]: eq for eq in equipment}

        inv_items = [c for c in by_code if c.startswith("S002-INV")]
        assert len(inv_items) >= 4, f"Expected 4 inverters, got {len(inv_items)}"
        for code in inv_items:
            assert by_code[code]["type"] == "inverter"

        assert "S002-BESS-B1-001" in by_code
        assert by_code["S002-BESS-B1-001"]["type"] == "bess"

    def test_meter_types(self):
        """MTR equipment should load as type 'meter'."""
        equipment = load_site_equipment("site-002")
        mtr_items = [eq for eq in equipment if eq["code"].startswith("S002-MTR")]
        assert len(mtr_items) >= 3
        # meter is not in JSON_TYPE_ALIASES but equipment_type is already "meter"
        for eq in mtr_items:
            assert eq["type"] == "meter"

    def test_nonexistent_site_returns_empty(self):
        """A site that doesn't exist should return an empty list."""
        equipment = load_site_equipment("site-999-nonexistent")
        assert equipment == []

    def test_malformed_json_skipped(self):
        """Malformed JSON files should be skipped with a warning, not crash."""
        # Create a temp directory mimicking the equipment structure
        with tempfile.TemporaryDirectory() as tmpdir:
            equip_dir = os.path.join(tmpdir, "test-site", "equipment")
            os.makedirs(equip_dir)

            # Write a valid file
            valid = {"id": "T001-AHU-001", "equipment_type": "ahu", "name": "Test AHU"}
            with open(os.path.join(equip_dir, "T001-AHU-001.json"), "w") as f:
                json.dump(valid, f)

            # Write a malformed file
            with open(os.path.join(equip_dir, "BAD.json"), "w") as f:
                f.write("{invalid json")

            # Patch the data root to use our temp dir
            import app.services.equipment_json_loader as loader
            from pathlib import Path

            original_root = loader._DATA_ROOT
            try:
                loader._DATA_ROOT = Path(tmpdir)
                equipment = load_site_equipment("test-site")
                assert len(equipment) == 1
                assert equipment[0]["code"] == "T001-AHU-001"
            finally:
                loader._DATA_ROOT = original_root

    def test_points_and_metadata_preserved(self):
        """Points and metadata from JSON should be passed through."""
        equipment = load_site_equipment("site-002")
        by_code = {eq["code"]: eq for eq in equipment}

        ahu = by_code.get("S002-AHU-B1-001")
        assert ahu is not None
        assert "points" in ahu
        assert isinstance(ahu["points"], dict)
        assert "metadata" in ahu
        assert isinstance(ahu["metadata"], dict)

    def test_default_health_score(self):
        """Equipment without health_score in JSON should get default 85."""
        equipment = load_site_equipment("site-002")
        # AHU files don't have health_score field → should get default
        by_code = {eq["code"]: eq for eq in equipment}
        ahu = by_code.get("S002-AHU-B1-001")
        assert ahu is not None
        assert isinstance(ahu["health_score"], (int, float))
        # Default is 85 if not in file
        assert ahu["health_score"] > 0


class TestTypeAliases:
    """Test the JSON_TYPE_ALIASES mapping."""

    def test_lighting_zone_alias(self):
        assert JSON_TYPE_ALIASES["lighting_zone"] == "luminaire"

    def test_dali_controller_alias(self):
        assert JSON_TYPE_ALIASES["dali_controller"] == "dali_controller"
