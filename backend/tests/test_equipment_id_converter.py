"""Tests for EquipmentIDConverter service."""

import pytest
from app.services.equipment_id_converter import EquipmentIDConverter


@pytest.fixture
def converter():
    """Create a converter instance for testing."""
    return EquipmentIDConverter()


class TestEquipmentTypeNormalization:
    """Test equipment type normalization."""

    def test_normalize_chiller_variations(self, converter):
        """Test normalization of chiller type variations."""
        assert converter._normalize_equipment_type("chiller") == "CHILLER"
        assert converter._normalize_equipment_type("CHILLER") == "CHILLER"
        assert converter._normalize_equipment_type("ch") == "CHILLER"
        assert converter._normalize_equipment_type("chill") == "CHILLER"
        assert converter._normalize_equipment_type("chw") == "CHILLER"

    def test_normalize_ahu(self, converter):
        """Test normalization of AHU type variations."""
        assert converter._normalize_equipment_type("ahu") == "AHU"
        assert converter._normalize_equipment_type("AHU") == "AHU"
        assert converter._normalize_equipment_type("air_handler") == "AHU"
        assert converter._normalize_equipment_type("ah") == "AHU"

    def test_normalize_fcu(self, converter):
        """Test normalization of FCU type variations."""
        assert converter._normalize_equipment_type("fcu") == "FCU"
        assert converter._normalize_equipment_type("FCU") == "FCU"
        assert converter._normalize_equipment_type("fan_coil") == "FCU"

    def test_normalize_vav(self, converter):
        """Test normalization of VAV type variations."""
        assert converter._normalize_equipment_type("vav") == "VAV"
        assert converter._normalize_equipment_type("VAV") == "VAV"

    def test_normalize_dali(self, converter):
        """Test normalization of DALI type variations."""
        assert converter._normalize_equipment_type("dali") == "DALI"
        assert converter._normalize_equipment_type("DALI") == "DALI"


class TestFloorZoneParsing:
    """Test floor and zone extraction from BMS IDs."""

    def test_parse_floor_zone_with_letter_zone(self, converter):
        """Test parsing floor-letter zone (e.g., FCU-L2-A)."""
        floor, zone = converter.parse_floor_zone("FCU-L2-A")
        assert floor == "L2"
        assert zone == "A"

    def test_parse_floor_zone_with_numeric_zone(self, converter):
        """Test parsing floor-numeric zone (e.g., VAV-L1-05)."""
        floor, zone = converter.parse_floor_zone("VAV-L1-05")
        assert floor == "L1"
        assert zone == "05"

    def test_parse_floor_zone_ground(self, converter):
        """Test parsing ground floor (e.g., AHU-G-01)."""
        floor, zone = converter.parse_floor_zone("AHU-G-01")
        assert floor == "G"
        assert zone == "01"

    def test_parse_floor_zone_basement(self, converter):
        """Test parsing basement (e.g., CH-B1-01)."""
        floor, zone = converter.parse_floor_zone("CH-B1-01")
        assert floor == "B1"
        assert zone == "01"

    def test_parse_floor_zone_simple(self, converter):
        """Test parsing simple format without floor (e.g., 001)."""
        floor, zone = converter.parse_floor_zone("EQUIP-001")
        # Should not match "R" from "EQUIP", should use default B1
        assert floor == "B1"  # Default floor
        assert zone == "001"

    def test_parse_floor_zone_underscore_separator(self, converter):
        """Test parsing with underscore separator."""
        floor, zone = converter.parse_floor_zone("FCU_L2_A")
        assert floor == "L2"
        assert zone == "A"


class TestSitePrefixExtraction:
    """Test site prefix generation."""

    def test_extract_site_002(self, converter):
        """Test extraction from site-002."""
        prefix = converter._extract_site_prefix("site-002")
        assert prefix == "S002"

    def test_extract_site_013(self, converter):
        """Test extraction from site-013."""
        prefix = converter._extract_site_prefix("site-013")
        assert prefix == "S013"

    def test_extract_plain_number(self, converter):
        """Test extraction from plain number."""
        prefix = converter._extract_site_prefix("002")
        assert prefix == "S002"

    def test_extract_s_prefix(self, converter):
        """Test extraction from S### format."""
        prefix = converter._extract_site_prefix("S002")
        assert prefix == "S002"


class TestZoneNumberToLetterMapping:
    """Test numeric zone to letter conversion."""

    def test_map_zone_01_to_a(self, converter):
        """Test 01 maps to A."""
        result = converter.map_zone_number_to_letter("01", "site-002")
        assert result == "A"

    def test_map_zone_05_to_e(self, converter):
        """Test 05 maps to E."""
        result = converter.map_zone_number_to_letter("05", "site-002")
        assert result == "E"

    def test_map_zone_20_to_t(self, converter):
        """Test 20 maps to T."""
        result = converter.map_zone_number_to_letter("20", "site-002")
        assert result == "T"

    def test_map_with_override(self, converter):
        """Test override mapping takes precedence."""
        override = {"01": "Z"}  # Override 01 to map to Z instead of A
        result = converter.map_zone_number_to_letter("01", "site-002", override)
        assert result == "Z"


class TestBMSToV2Conversion:
    """Test full BMS ID to v2.0 conversion."""

    def test_convert_chiller_simple(self, converter):
        """Test simple chiller conversion."""
        result = converter.convert_bms_to_v2("CH-1", "chiller", "site-002")
        assert result == "S002-CHILLER-B1-001"

    def test_convert_vav_with_zone(self, converter):
        """Test VAV with floor and zone."""
        result = converter.convert_bms_to_v2("VAV-L1-05", "vav", "site-002")
        assert result == "S002-VAV-L1-E"

    def test_convert_fcu_letter_zone(self, converter):
        """Test FCU with letter zone."""
        result = converter.convert_bms_to_v2("FCU-L2-A", "fcu", "site-002")
        assert result == "S002-FCU-L2-A"

    def test_convert_ahu_ground(self, converter):
        """Test AHU on ground floor with zone mapping."""
        # With default zone mapping, 01→A
        result = converter.convert_bms_to_v2("AHU-G-01", "ahu", "site-002")
        # Since zone mapping exists for 01→A, it should use A
        assert result == "S002-AHU-G-A"

    def test_convert_different_site(self, converter):
        """Test conversion for different site."""
        result = converter.convert_bms_to_v2("CH-1", "chiller", "site-013")
        assert result == "S013-CHILLER-B1-001"

    def test_convert_with_custom_zone_mapping(self, converter):
        """Test conversion with custom zone mapping."""
        zone_mapping = {"05": "Z"}
        result = converter.convert_bms_to_v2(
            "VAV-L1-05", "vav", "site-002", zone_mapping=zone_mapping
        )
        assert result == "S002-VAV-L1-Z"


class TestBMSFormatDetection:
    """Test BMS format auto-detection."""

    def test_detect_legacy_sandton(self, converter):
        """Test detection of legacy Sandton format."""
        format_type = converter.detect_bms_format("011-stc-ahu-001")
        assert format_type == "LEGACY_SANDTON"

    def test_detect_equipment_floor_zone(self, converter):
        """Test detection of equipment-floor-zone format."""
        format_type = converter.detect_bms_format("FCU-L2-A")
        assert format_type == "EQUIPMENT-FLOOR-ZONE"

    def test_detect_equipment_number(self, converter):
        """Test detection of equipment-number format."""
        format_type = converter.detect_bms_format("CH-1")
        assert format_type == "EQUIPMENT-NUMBER"

    def test_detect_unknown(self, converter):
        """Test detection of unknown format."""
        format_type = converter.detect_bms_format("XYZABC123XYZ")
        assert format_type == "UNKNOWN"
