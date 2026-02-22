"""
Tests for Zone Ingestion Validation Logic

Tests zone ingestion validation without Supabase dependencies.
For integration tests, run: pytest tests/test_zone_ingestion_api.py
"""

import pytest
from typing import List, Dict, Optional


# ============= Validation Utilities =============


def validate_zone_id(zone_id: str) -> bool:
    """Validate zone ID format: Zone-FLOOR-LETTER"""
    parts = zone_id.split("-")
    if len(parts) != 3:
        return False
    prefix, floor, letter = parts
    if prefix != "Zone":
        return False
    # Floor validation: B#, G, L#, R
    if not validate_floor_code(floor):
        return False
    # Zone letter must be single uppercase letter
    if len(letter) != 1 or not letter.isalpha() or not letter.isupper():
        return False
    return True


def validate_floor_code(floor: str) -> bool:
    """Validate floor code: B#, G, L#, R, R#"""
    if floor == "G" or floor == "R":
        return True
    if floor[0] in ["B", "L", "R"] and len(floor) > 1:
        return floor[1:].isdigit()
    return False


def validate_zone_type(zone_type: str) -> bool:
    """Validate zone type is one of the allowed types"""
    valid_types = {
        "open_office",
        "meeting_room",
        "plant_room",
        "storage",
        "stairwell",
        "corridor",
        "lobby",
        "restroom",
        "cafeteria",
        "server_room",
        "comms_room",
        "mechanical",
        "electrical",
    }
    return zone_type in valid_types


def validate_desk_context(context: str) -> bool:
    """Validate desk context type"""
    valid_contexts = {"near_diffuser", "near_window", "near_printer", "corner", "open_plan"}
    return context in valid_contexts


def check_duplicate_zone_ids(zones: List[Dict]) -> bool:
    """Return True if no duplicates found, False if duplicates exist"""
    zone_ids = [z.get("zone_id") for z in zones]
    return len(zone_ids) == len(set(zone_ids))


def check_duplicate_desk_ids(desks: List[Dict]) -> bool:
    """Return True if no duplicates found, False if duplicates exist"""
    desk_ids = [d.get("desk_id") for d in desks]
    return len(desk_ids) == len(set(desk_ids))


def validate_desk_zone_references(desks: List[Dict], valid_zones: set) -> bool:
    """Return True if all desk zone references are valid"""
    for desk in desks:
        zone_id = desk.get("zone_id")
        if zone_id not in valid_zones:
            return False
    return True


def calculate_zone_centroid(desks: List[Dict]) -> Optional[Dict[str, float]]:
    """Calculate zone centroid from desk positions"""
    if not desks:
        return None

    coords = [d.get("coordinates") for d in desks if d.get("coordinates")]
    if not coords:
        return None

    avg_x = sum(c.get("x", 0) for c in coords) / len(coords)
    avg_z = sum(c.get("z", 0) for c in coords) / len(coords)

    return {"x": avg_x, "z": avg_z}


def validate_coordinate_bounds(x: float, z: float, min_val: float = 0, max_x: float = 30, max_z: float = 20) -> bool:
    """Validate coordinates are within building bounds"""
    return min_val <= x <= max_x and min_val <= z <= max_z


# ============= Tests =============


class TestZoneValidation:
    """Test zone validation logic"""

    def test_valid_zone_id_format(self):
        """Test valid zone IDs are recognized"""
        valid_ids = [
            "Zone-L0-A",
            "Zone-L1-B",
            "Zone-L2-Z",
            "Zone-B1-C",
            "Zone-G-D",
            "Zone-R-E",
        ]
        for zone_id in valid_ids:
            assert validate_zone_id(zone_id), f"Zone ID {zone_id} should be valid"

    def test_invalid_zone_id_format(self):
        """Test invalid zone IDs are rejected"""
        invalid_ids = [
            "Zone-X-A",  # Invalid floor letter
            "Zone-L0-1",  # Zone letter must be a letter
            "Zone-L0",  # Missing zone letter
            "L0-A",  # Missing Zone prefix
            "Zone-L0-AB",  # Zone letter must be single char
            "Zone-L0-a",  # Zone letter must be uppercase
        ]
        for zone_id in invalid_ids:
            assert not validate_zone_id(zone_id), f"Zone ID {zone_id} should be invalid"

    def test_valid_floor_codes(self):
        """Test valid floor codes"""
        valid_floors = ["B1", "B2", "G", "L0", "L1", "L2", "R"]
        for floor in valid_floors:
            assert validate_floor_code(floor), f"Floor code {floor} should be valid"

    def test_invalid_floor_codes(self):
        """Test invalid floor codes"""
        invalid_floors = ["X", "L", "B", "L10A", "Z0", "RX"]
        for floor in invalid_floors:
            assert not validate_floor_code(floor), f"Floor code {floor} should be invalid"

    def test_valid_zone_types(self):
        """Test valid zone types"""
        zone_types = [
            "open_office",
            "meeting_room",
            "plant_room",
            "storage",
            "stairwell",
            "corridor",
            "lobby",
            "restroom",
            "cafeteria",
            "server_room",
            "comms_room",
            "mechanical",
            "electrical",
        ]
        for zone_type in zone_types:
            assert validate_zone_type(zone_type), f"Zone type {zone_type} should be valid"

    def test_invalid_zone_types(self):
        """Test invalid zone types are rejected"""
        invalid_types = ["office", "meeting", "plant", "invalid_zone", ""]
        for zone_type in invalid_types:
            assert not validate_zone_type(zone_type), f"Zone type {zone_type} should be invalid"

    def test_duplicate_zone_ids_detected(self):
        """Test duplicate zone IDs are detected"""
        zones = [
            {"zone_id": "Zone-L1-A"},
            {"zone_id": "Zone-L1-B"},
            {"zone_id": "Zone-L1-A"},  # Duplicate
        ]
        assert not check_duplicate_zone_ids(zones), "Duplicates should be detected"

    def test_no_duplicate_zone_ids(self):
        """Test valid zone IDs pass validation"""
        zones = [
            {"zone_id": "Zone-L1-A"},
            {"zone_id": "Zone-L1-B"},
            {"zone_id": "Zone-L1-C"},
        ]
        assert check_duplicate_zone_ids(zones), "No duplicates should be found"

    def test_zone_centroid_calculation(self):
        """Test zone centroid calculation from desk coordinates"""
        desks = [
            {"coordinates": {"x": 2.0, "y": 3.5, "z": 8.0}},
            {"coordinates": {"x": 4.0, "y": 3.5, "z": 12.0}},
        ]
        centroid = calculate_zone_centroid(desks)
        assert centroid is not None
        assert centroid["x"] == 3.0  # (2 + 4) / 2
        assert centroid["z"] == 10.0  # (8 + 12) / 2

    def test_zone_centroid_empty_zone(self):
        """Test centroid calculation returns None for empty zone"""
        centroid = calculate_zone_centroid([])
        assert centroid is None

    def test_zone_centroid_20_desks(self):
        """Test centroid with 20 desks (standard zone)"""
        desks = [{"coordinates": {"x": 3.0 + (i % 5) * 1.2, "y": 3.5, "z": 2.5 + (i // 5) * 5.0}} for i in range(20)]
        centroid = calculate_zone_centroid(desks)
        assert centroid is not None
        # Centroid should be near middle of zone
        assert 4.0 < centroid["x"] < 8.0
        assert 8.0 < centroid["z"] < 12.0

    def test_coordinate_bounds_validation(self):
        """Test coordinate bounds checking"""
        # Valid coordinates
        assert validate_coordinate_bounds(3.0, 10.0)
        assert validate_coordinate_bounds(0.5, 0.5)
        assert validate_coordinate_bounds(29.5, 19.5)

        # Invalid coordinates
        assert not validate_coordinate_bounds(-1.0, 10.0)
        assert not validate_coordinate_bounds(31.0, 10.0)
        assert not validate_coordinate_bounds(3.0, -1.0)
        assert not validate_coordinate_bounds(3.0, 21.0)

    def test_desk_context_validation(self):
        """Test desk context types"""
        valid_contexts = ["near_diffuser", "near_window", "near_printer", "corner", "open_plan"]
        for context in valid_contexts:
            assert validate_desk_context(context), f"Context {context} should be valid"

        invalid_contexts = ["diffuser", "window", "invalid", ""]
        for context in invalid_contexts:
            assert not validate_desk_context(context), f"Context {context} should be invalid"

    def test_desk_zone_reference_validation(self):
        """Test desk zone references are valid"""
        valid_zones = {"Zone-L1-A", "Zone-L1-B", "Zone-L1-C"}

        # Valid references
        desks = [
            {"zone_id": "Zone-L1-A"},
            {"zone_id": "Zone-L1-B"},
        ]
        assert validate_desk_zone_references(desks, valid_zones)

        # Invalid reference
        desks = [
            {"zone_id": "Zone-L1-A"},
            {"zone_id": "Zone-L99-Z"},  # Invalid zone
        ]
        assert not validate_desk_zone_references(desks, valid_zones)

    def test_multi_building_zone_configurations(self):
        """Test different zone configurations for different buildings"""
        # Building A: 15 zones (5 per floor × 3 floors)
        zones_a = [
            {
                "zone_id": f"Zone-L{floor}-{chr(65 + zone)}",
                "floor": f"L{floor}",
                "zone_type": "open_office",
            }
            for floor in range(3)
            for zone in range(5)
        ]

        # Building B: 6 zones (3 per floor × 2 floors)
        zones_b = [
            {
                "zone_id": f"Zone-L{floor}-{chr(65 + zone)}",
                "floor": f"L{floor}",
                "zone_type": "open_office",
            }
            for floor in range(1, 3)
            for zone in range(3)
        ]

        # Validate both configurations
        assert check_duplicate_zone_ids(zones_a), "Building A zones should be unique"
        assert check_duplicate_zone_ids(zones_b), "Building B zones should be unique"
        assert len(zones_a) == 15
        assert len(zones_b) == 6

    def test_desk_duplicate_detection(self):
        """Test duplicate desk ID detection"""
        desks_with_duplicates = [
            {"desk_id": "1001"},
            {"desk_id": "1002"},
            {"desk_id": "1001"},  # Duplicate
        ]
        assert not check_duplicate_desk_ids(desks_with_duplicates)

        desks_unique = [
            {"desk_id": "1001"},
            {"desk_id": "1002"},
            {"desk_id": "1003"},
        ]
        assert check_duplicate_desk_ids(desks_unique)

    def test_floor_code_standardization(self):
        """Test floor code standardization (L0/L1/L2)"""
        # These should all be valid
        floor_codes = ["L0", "L1", "L2", "B1", "G", "R"]
        for floor in floor_codes:
            assert validate_floor_code(floor), f"Floor {floor} should be valid"

    def test_15_zone_site002_structure(self):
        """Test site-002 standard configuration: 15 zones (5 per floor × 3 floors)"""
        zones = [
            {
                "zone_id": f"Zone-L{floor}-{chr(65 + zone)}",
                "zone_name": f"Level {floor} Zone {chr(65 + zone)}",
                "floor": f"L{floor}",
                "zone_letter": chr(65 + zone),
                "zone_type": "open_office",
                "typical_occupancy": 20,
                "area_sqm": 200,
            }
            for floor in range(3)
            for zone in range(5)
        ]

        # Validate structure
        assert len(zones) == 15
        assert check_duplicate_zone_ids(zones)

        # Check all zones are properly formatted
        for zone in zones:
            assert validate_zone_id(zone["zone_id"])
            assert validate_floor_code(zone["floor"])
            assert validate_zone_type(zone["zone_type"])

    def test_20_desks_per_zone(self):
        """Test full zone configuration: 20 desks per zone"""
        desks = [
            {
                "desk_id": f"{1000 + i}",
                "desk_name": f"Desk {1000 + i}",
                "floor": "L1",
                "zone_id": "Zone-L1-A",
                "context": "open_plan" if i % 2 == 0 else "near_window",
                "coordinates": {
                    "x": 3.0 + (i % 5) * 1.2,
                    "y": 3.5,
                    "z": 2.5 + (i // 5) * 5.0,
                },
            }
            for i in range(20)
        ]

        # Validate structure
        assert len(desks) == 20
        assert check_duplicate_desk_ids(desks)

        # Check all desks are properly formatted
        for desk in desks:
            assert validate_desk_context(desk["context"])
            coords = desk["coordinates"]
            assert validate_coordinate_bounds(coords["x"], coords["z"])

    def test_300_desks_15_zones(self):
        """Test full site-002 structure: 300 desks across 15 zones"""
        desks = [
            {
                "desk_id": f"{1000 + (zone * 20) + (i % 20)}",
                "zone_id": f"Zone-L{zone // 5}-{chr(65 + (zone % 5))}",
                "coordinates": {"x": 3.0 + (i % 5) * 1.2, "y": 3.5, "z": 2.5 + (i // 5) * 5.0},
            }
            for zone in range(15)
            for i in range(20)
        ]

        assert len(desks) == 300
        assert check_duplicate_desk_ids(desks)

        # All zones should be present
        zones = {d["zone_id"] for d in desks}
        assert len(zones) == 15


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
