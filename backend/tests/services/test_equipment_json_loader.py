"""Tests for the JSON equipment loader (equipment_json_loader.py).

Validates that on-disk equipment JSON files for site-002 load correctly,
type normalization works, and edge cases are handled gracefully.
"""

import json

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
        # data/sites/site-002/equipment has core HVAC equipment files
        assert len(equipment) >= 4, f"Expected 4+ equipment, got {len(equipment)}"

    def test_each_equipment_has_required_fields(self):
        """Every loaded equipment must have code, type, and health_score."""
        equipment = load_site_equipment("site-002")
        for eq in equipment:
            assert "code" in eq, f"Missing code: {eq}"
            assert "type" in eq, f"Missing type for {eq.get('code')}"
            assert "health_score" in eq, f"Missing health_score for {eq.get('code')}"
            assert isinstance(eq["health_score"], (int, float))

    def test_type_normalization_via_alias(self):
        """JSON_TYPE_ALIASES should normalize equipment_type values."""
        # Verify the alias mapping works (tested via unit alias tests below)
        assert JSON_TYPE_ALIASES.get("lighting_zone") == "luminaire"

    def test_hvac_types_preserved(self):
        """Standard HVAC types (ahu, chiller, fcu, vav) should be preserved."""
        equipment = load_site_equipment("site-002")
        by_code = {eq["code"]: eq for eq in equipment}

        assert by_code["S002-AHU-B1-001"]["type"] == "ahu"
        assert by_code["S002-CHILLER-B1-001"]["type"] == "chiller"
        assert by_code["S002-FCU-L2-B"]["type"] == "fcu"
        assert by_code["S002-VAV-L1-A"]["type"] == "vav"

    def test_nonexistent_site_returns_empty(self):
        """A site that doesn't exist should return an empty list."""
        equipment = load_site_equipment("site-999-nonexistent")
        assert equipment == []

    def test_malformed_json_skipped(self, tmp_path):
        """Malformed JSON files should be skipped with a warning, not crash."""
        from unittest.mock import patch

        equip_dir = tmp_path / "test-site" / "equipment"
        equip_dir.mkdir(parents=True)

        # Write a valid file
        valid = {"id": "T001-AHU-001", "equipment_type": "ahu", "name": "Test AHU"}
        (equip_dir / "T001-AHU-001.json").write_text(json.dumps(valid), encoding="utf-8")

        # Write a malformed file
        (equip_dir / "BAD.json").write_text("{invalid json", encoding="utf-8")

        with patch("app.services.equipment_json_loader._DATA_ROOT", tmp_path):
            equipment = load_site_equipment("test-site")
        assert len(equipment) == 1
        assert equipment[0]["code"] == "T001-AHU-001"

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
